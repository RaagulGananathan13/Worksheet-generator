"""Teacher publishing, student practice, printed-worksheet uploads and private server-side marking."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
import queue
from threading import BoundedSemaphore, Event, Lock, Thread
from typing import Annotated
from uuid import uuid4
import csv
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from . import documents, grading, ocr, paper, samples
from .auth import (
    COOKIE_NAME, LoginLimiter, create_session, hash_password, lookup_session,
    public_user, require_student, require_teacher, require_user, session_hash,
    verify_password,
)
from .database import Database
from .schemas import AnswersUpdate, ReviewUpdate, WorksheetUpdate


ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PAPER_BYTES = 60 * 1024 * 1024
GRADING_BUDGET_SECONDS = 30 * 60
MAX_GRADING_TRIES = 3
IDENTIFIER = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
LOGGER = logging.getLogger("automatic_grading")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class LoginBody(StrictBody):
    username: Username
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._@+\-]{2,79}", value):
            raise ValueError("Use 3–80 letters, numbers, dots, underscores, or email characters.")
        return value


class BootstrapBody(LoginBody):
    token: Annotated[str, StringConstraints(min_length=16, max_length=200)]
    name: Name
    password: Password


class RegisterBody(LoginBody):
    name: Name
    password: Password
    class_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=30)]


class SampleBody(StrictBody):
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)]


class VersionBody(StrictBody):
    version: int = Field(ge=1, strict=True)


class PayloadTooLarge(Exception):
    pass


class RequestGuard:
    """Bound all bodies, reject cross-origin writes, and set browser protections."""

    def __init__(self, app, allowed_origins=()):
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get("origin")
            host_origin = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            if ((origin and origin.rstrip("/") not in self.allowed_origins | {host_origin})
                    or headers.get("sec-fetch-site") == "cross-site"):
                return await JSONResponse({"detail": "Cross-origin requests are not allowed."}, 403)(scope, receive, send)
        try:
            if int(headers.get("content-length", "0")) > MAX_REQUEST_BYTES:
                return await JSONResponse({"detail": "Request exceeds the 64 MB limit."}, 413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length."}, 400)(scope, receive, send)
        received = 0
        started = False

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BYTES:
                    raise PayloadTooLarge()
            return message

        async def protected_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
                ]
                if scope["path"].startswith("/api"):
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        try:
            await self.app(scope, bounded_receive, protected_send)
        except PayloadTooLarge:
            if started:
                raise
            await JSONResponse({"detail": "Request exceeds the 64 MB limit."}, 413)(scope, receive, protected_send)


class GradingQueue:
    """One background worker: the local handwriting models mark one attempt at a time."""

    def __init__(self, process):
        self.process = process
        self.items = queue.Queue()
        self.stopping = Event()
        self.thread = None

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stopping.clear()
            self.thread = Thread(target=self.run, name="grading-worker", daemon=True)
            self.thread.start()

    def put(self, attempt_id):
        self.items.put(attempt_id)

    def run(self):
        while not self.stopping.is_set():
            try:
                attempt_id = self.items.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self.process(attempt_id)
            except Exception:
                LOGGER.exception("Background marking failed for attempt %s", attempt_id)
            finally:
                self.items.task_done()

    def wait(self, timeout=60):
        """Wait until queued work has finished (used by tests and orderly shutdown)."""
        deadline = time.monotonic() + timeout
        while self.items.unfinished_tasks:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.05)
        return True

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join(timeout=5)


def public_questions(questions, teacher=False):
    private = {"expected", "tolerance", "case_sensitive"}
    return questions if teacher else [{key: value for key, value in question.items() if key not in private} for question in questions]


def public_paper(value):
    record = json.loads(value or "{}")
    if not record.get("upload_id"):
        return None
    return {
        "uploaded_at": record.get("uploaded_at"), "uploaded_by_role": record.get("uploaded_by_role"),
        "files": len(record.get("files", [])),
        "pages": [{"index": page["index"], "visible": page.get("visible")} for page in record.get("pages", [])],
    }


def worksheet_object(row, user):
    return {
        "id": row["id"], "title": row["title"], "published": bool(row["published"]),
        "revision": row["revision"], "pages": json.loads(row["pages"]),
        "questions": public_questions(json.loads(row["questions"]), user["role"] == "teacher"),
        "notes": row["notes"] if user["role"] == "teacher" else "",
    }


def attempt_object(row, user):
    return {
        "id": row["id"], "worksheet_id": row["worksheet_id"],
        "attempt_number": row["attempt_number"], "previous_attempt_id": row["previous_attempt_id"],
        "latest_attempt_id": row.get("latest_attempt_id", row["id"]),
        "worksheet_published": bool(row.get("worksheet_published", False)),
        "student_name": row.get("student_name", ""), "student_id": row["student_id"],
        "status": row["status"], "version": row["version"],
        "submission_mode": row.get("submission_mode") or "online",
        "paper": public_paper(row.get("paper")),
        "answers": json.loads(row["answers"]),
        "questions": public_questions(json.loads(row["questions"]), user["role"] == "teacher"),
        "results": json.loads(row["results"]), "summary": json.loads(row["summary"]),
        "title": row["title"], "pages": json.loads(row["pages"]),
        "worksheet_revision": row["worksheet_revision"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "submitted_at": row["submitted_at"],
    }


def authorized_worksheet(database, worksheet_id, user):
    row = database.one("SELECT * FROM worksheets WHERE id=?", (worksheet_id,))
    if row is None:
        raise HTTPException(404, "Worksheet not found.")
    if user["role"] == "teacher":
        allowed = row["owner_id"] == user["id"]
    else:
        allowed = row["owner_id"] == user["teacher_id"] and bool(row["published"])
        # Existing attempts retain access to their immutable source after unpublishing.
        if not allowed and row["owner_id"] == user["teacher_id"]:
            allowed = database.one(
                "SELECT id FROM attempts WHERE worksheet_id=? AND student_id=?",
                (worksheet_id, user["id"]),
            ) is not None
    if not allowed:
        raise HTTPException(404, "Worksheet not found.")
    return row


def authorized_attempt(database, attempt_id, user):
    row = database.one(
        "SELECT a.*,u.name AS student_name,w.published AS worksheet_published,"
        "(SELECT newest.id FROM attempts newest WHERE newest.worksheet_id=a.worksheet_id AND newest.student_id=a.student_id "
        "ORDER BY newest.attempt_number DESC LIMIT 1) AS latest_attempt_id "
        "FROM attempts a JOIN users u ON u.id=a.student_id JOIN worksheets w ON w.id=a.worksheet_id WHERE a.id=?",
        (attempt_id,),
    )
    if row is None or (
        user["role"] == "teacher" and row["teacher_id"] != user["id"]
    ) or (user["role"] == "student" and row["student_id"] != user["id"]):
        raise HTTPException(404, "Attempt not found.")
    return row


def require_version(row, version):
    if row["version"] != version:
        raise HTTPException(409, "This work changed in another tab. Reload the saved version before continuing.")


def pending_results(questions, reason):
    return [{
        "question_id": question["id"], "label": question["label"],
        "awarded": None, "max_points": question["points"], "status": "pending_review",
        "recognized_text": "", "feedback": reason, "source": "review",
        "confidence": None,
    } for question in questions]


def safe_csv(value):
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


def file_type(content):
    if content.lstrip()[:5] == b"%PDF-":
        return "pdf"
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return "bin"


def create_app(data_dir=None, testing=False):
    directory = Path(data_dir or os.environ.get("AG_DATA_DIR") or ROOT / "data").resolve()
    database = Database(directory)

    @asynccontextmanager
    async def lifespan(application):
        database.initialize()
        (directory / "documents").mkdir(parents=True, exist_ok=True)
        (directory / "submissions").mkdir(parents=True, exist_ok=True)
        upload_temporary = directory / "tmp"
        upload_temporary.mkdir(parents=True, exist_ok=True)
        previous_temporary = tempfile.tempdir
        # Starlette's multipart parser uses SpooledTemporaryFile without a dir
        # argument. Keep larger uploaded student/teacher documents in this app's
        # data directory rather than the operating system's shared temp folder.
        tempfile.tempdir = str(upload_temporary)
        try:
            resume_interrupted()
            application.state.grading_queue.start()
            yield
        finally:
            application.state.grading_queue.stop()
            tempfile.tempdir = previous_temporary

    application = FastAPI(
        title="GeniusBees automatic grading", version="2.0.0", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    application.state.database = database
    application.state.data_dir = directory
    application.state.bootstrap_token = os.environ.get("AG_BOOTSTRAP_TOKEN") or secrets.token_urlsafe(32)
    application.state.secure_cookies = os.environ.get("AG_SECURE_COOKIES", "0") == "1"
    application.state.recognizer = None
    application.state.image_recognizer = None
    application.state.testing = testing
    # Tests mark synchronously; a running server marks in the background queue.
    application.state.inline_grading = testing
    application.state.grading_queue = GradingQueue(lambda attempt_id: grade_attempt(attempt_id))
    application.state.document_slots = BoundedSemaphore(2)
    application.state.import_lock = Lock()
    application.state.login_limiter = LoginLimiter()
    application.state.dummy_password_hash = hash_password(secrets.token_urlsafe(32))
    application.add_middleware(
        RequestGuard,
        allowed_origins=[item.strip().rstrip("/") for item in os.environ.get("AG_ALLOWED_ORIGINS", "").split(",") if item.strip()],
    )

    @application.exception_handler(sqlite3.OperationalError)
    async def database_unavailable(_request, error):
        LOGGER.exception("Database operation failed", exc_info=error)
        return JSONResponse({"detail": "Storage is temporarily busy. Please try again."}, 503)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request, error):
        # Framework defaults echo raw input, which can contain passwords, NaN,
        # or invalid Unicode. NaN/surrogates themselves break JSON error output.
        def printable(value):
            return str(value).encode("utf-8", errors="replace").decode("utf-8")

        details = [{
            "loc": [printable(part)[:100] if not isinstance(part, int) else part for part in item["loc"]],
            "msg": printable(item["msg"])[:1000], "type": item["type"],
        } for item in error.errors()[:20]]
        return JSONResponse({"detail": details}, 422)

    def document_path(sha256, suffix):
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise HTTPException(500, "Document identifier is invalid.")
        path = directory / "documents" / f"{sha256}{suffix}"
        if not path.is_file():
            raise HTTPException(404, "Document file is missing. Ask your teacher to restore the server backup.")
        return path

    def submission_directory(attempt_id, upload_id):
        if not IDENTIFIER.fullmatch(attempt_id or "") or not IDENTIFIER.fullmatch(upload_id or ""):
            raise HTTPException(404, "The paper submission is unavailable.")
        return directory / "submissions" / attempt_id / upload_id

    def paper_evidence(row):
        """Per-question evidence from the stored aligned pages; printing is removed by paper.py."""
        record = json.loads(row["paper"] or "{}")
        folder = submission_directory(row["id"], record.get("upload_id"))
        stored = {page["index"]: page for page in record.get("pages", [])}
        cache = {}

        def evidence(question):
            index = question["page"]
            if index not in cache:
                reference = paper.flatten(paper.load_gray(document_path(row["sha256"], f"-{index}.png")))
                cache[index] = (reference, paper.load_alignment(folder, stored[index]))
            reference, alignment = cache[index]
            return paper.question_evidence(reference, alignment, question)

        return evidence

    def grade_attempt(attempt_id):
        with database.transaction() as connection:
            row = connection.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if row is None or row["status"] != "grading":
                return
            connection.execute("UPDATE attempts SET grading_tries=grading_tries+1,grading_started=? WHERE id=?", (time.time(), attempt_id))
        row = dict(row)
        pages = json.loads(row["pages"])
        questions = [{**question, "_page_aspect": pages[question["page"]]["width"] / pages[question["page"]]["height"]}
                     for question in json.loads(row["questions"])]
        try:
            evidence = paper_evidence(row) if row["submission_mode"] == "paper" else None
            marked = grading.grade_answers(
                questions, json.loads(row["answers"]), recognizer=application.state.recognizer,
                image_recognizer=application.state.image_recognizer, paper=evidence,
                budget_seconds=GRADING_BUDGET_SECONDS,
            )
            results, summary = marked["results"], marked["summary"]
        except Exception:
            LOGGER.exception("Marking failed for attempt %s", attempt_id)
            results = pending_results(questions, "Automatic marking could not finish. The saved work needs teacher review.")
            summary = grading.summarize(results)
        with database.transaction() as connection:
            connection.execute(
                "UPDATE attempts SET status=?,results=?,summary=?,version=version+1,grading_started=NULL,updated_at=? WHERE id=? AND status='grading'",
                ("graded" if summary["final"] else "review", encode(results), encode(summary), now_iso(), attempt_id),
            )

    def schedule_grading(attempt_id):
        if application.state.inline_grading:
            grade_attempt(attempt_id)
        else:
            application.state.grading_queue.put(attempt_id)

    def resume_interrupted():
        """Resume marking after a restart; repeated failures go to teacher review, never zero."""
        waiting = []
        with database.transaction() as connection:
            for row in connection.execute("SELECT id,questions,grading_tries FROM attempts WHERE status='grading'").fetchall():
                if row["grading_tries"] >= MAX_GRADING_TRIES:
                    results = pending_results(json.loads(row["questions"]), "Marking was interrupted. The saved work needs teacher review.")
                    connection.execute(
                        "UPDATE attempts SET status='review',version=version+1,results=?,summary=?,grading_started=NULL,updated_at=? WHERE id=?",
                        (encode(results), encode(grading.summarize(results)), now_iso(), row["id"]),
                    )
                else:
                    waiting.append(row["id"])
        for attempt_id in waiting:
            application.state.grading_queue.put(attempt_id)

    @application.get("/api/health")
    def health():
        return {
            "ok": True, "ocr": ocr.status(),
            "setup_required": database.one("SELECT id FROM users WHERE role='teacher' LIMIT 1") is None,
        }

    @application.get("/api/session")
    def session(request: Request):
        user = lookup_session(request)
        return {"user": public_user(user) if user else None, "csrf_token": user["csrf_token"] if user else ""}

    def limit_auth(request, username):
        host = request.client.host if request.client else "unknown"
        key = f"{host}:{username}"
        application.state.login_limiter.check(key)
        application.state.login_limiter.check(f"ip:{host}", maximum=120)
        return key

    @application.post("/api/bootstrap", status_code=201)
    def bootstrap(payload: BootstrapBody, request: Request, response: Response):
        limit_auth(request, "bootstrap")
        if not hmac.compare_digest(payload.token.encode("utf-8"), application.state.bootstrap_token.encode("utf-8")):
            raise HTTPException(403, "Invalid setup token. Use the token shown in the server terminal.")
        user = {
            "id": str(uuid4()), "name": payload.name, "username": payload.username,
            "role": "teacher", "teacher_id": None, "class_code": secrets.token_hex(5).upper(),
        }
        password_hash = hash_password(payload.password)
        with database.transaction() as connection:
            if connection.execute("SELECT id FROM users WHERE role='teacher' LIMIT 1").fetchone():
                raise HTTPException(409, "Teacher setup is already complete. Please log in.")
            connection.execute(
                "INSERT INTO users(id,name,username,password_hash,role,teacher_id,class_code,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (user["id"], user["name"], user["username"], password_hash, "teacher", None, user["class_code"], now_iso()),
            )
        return create_session(request, response, user)

    @application.post("/api/login")
    def login(payload: LoginBody, request: Request, response: Response):
        key = limit_auth(request, payload.username)
        user = database.one("SELECT * FROM users WHERE username=?", (payload.username,))
        valid = verify_password(payload.password, user["password_hash"] if user else application.state.dummy_password_hash)
        if not user or not valid:
            raise HTTPException(401, "Username or password is incorrect.")
        application.state.login_limiter.clear(key)
        return create_session(request, response, user)

    @application.post("/api/register", status_code=201)
    def register(payload: RegisterBody, request: Request, response: Response):
        limit_auth(request, payload.username)
        teacher = database.one("SELECT id FROM users WHERE class_code=? AND role='teacher'", (payload.class_code.upper(),))
        if teacher is None:
            raise HTTPException(400, "That class code is not valid. Check the code from your teacher.")
        user = {
            "id": str(uuid4()), "name": payload.name, "username": payload.username,
            "role": "student", "teacher_id": teacher["id"], "class_code": None,
        }
        password_hash = hash_password(payload.password)
        try:
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO users(id,name,username,password_hash,role,teacher_id,class_code,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (user["id"], user["name"], user["username"], password_hash, "student", teacher["id"], None, now_iso()),
                )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "That username is already taken.") from None
        return create_session(request, response, user)

    @application.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(require_user)):
        with database.transaction() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (session_hash(request.cookies[COOKIE_NAME]),))
        response.delete_cookie(COOKIE_NAME, path="/", secure=application.state.secure_cookies, httponly=True, samesite="strict")
        return {"ok": True}

    @application.get("/api/worksheets")
    def list_worksheets(user=Depends(require_user)):
        if user["role"] == "teacher":
            rows = database.all("SELECT * FROM worksheets WHERE owner_id=? ORDER BY updated_at DESC", (user["id"],))
        else:
            rows = database.all("SELECT * FROM worksheets WHERE owner_id=? AND published=1 ORDER BY updated_at DESC", (user["teacher_id"],))
        output = []
        for row in rows:
            questions = json.loads(row["questions"])
            item = {
                "id": row["id"], "title": row["title"], "published": bool(row["published"]),
                "revision": row["revision"], "question_count": len(questions),
                "total_points": sum(question["points"] for question in questions),
                "pages": json.loads(row["pages"]),
            }
            if user["role"] == "student":
                attempt = database.one(
                    "SELECT id,status,summary,attempt_number,submission_mode FROM attempts WHERE worksheet_id=? AND student_id=? ORDER BY attempt_number DESC LIMIT 1",
                    (row["id"], user["id"]),
                )
                if attempt:
                    item["attempt"] = {"id": attempt["id"], "status": attempt["status"], "attempt_number": attempt["attempt_number"],
                                       "submission_mode": attempt["submission_mode"], "summary": json.loads(attempt["summary"])}
            output.append(item)
        result = {"worksheets": output}
        if user["role"] == "teacher":
            result["class_code"] = user["class_code"]
        return result

    @application.get("/api/students")
    def list_students(user=Depends(require_teacher)):
        return {"students": database.all(
            "SELECT id,name,username FROM users WHERE role='student' AND teacher_id=? ORDER BY name COLLATE NOCASE, username",
            (user["id"],),
        )}

    @application.get("/api/samples")
    def available_samples(user=Depends(require_teacher)):
        return {"samples": samples.list_samples()}

    def import_content(content, title, questions, notes, user):
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(413, "PDF exceeds the 20 MB limit.")
        sha256 = hashlib.sha256(content).hexdigest()
        existing = database.one("SELECT * FROM worksheets WHERE owner_id=? AND sha256=?", (user["id"], sha256))
        if existing:
            return worksheet_object(existing, user)
        if not application.state.document_slots.acquire(blocking=False):
            raise HTTPException(503, "Document processing is busy. Please retry this import shortly.")
        try:
            try:
                with application.state.import_lock:
                    metadata = documents.import_pdf(content, directory / "documents")
            except (ValueError, RuntimeError) as error:
                raise HTTPException(400, str(error)) from None
        finally:
            application.state.document_slots.release()
        if questions:
            # Presets pass the same validation path as teacher-authored keys.
            validated = WorksheetUpdate.model_validate({
                "title": title, "questions": questions, "published": False,
                "keys_confirmed": False, "revision": 1,
            }).model_dump()
            questions = validated["questions"]
        if any(question["page"] >= len(metadata["pages"]) for question in questions):
            raise HTTPException(400, "An answer area refers to a missing PDF page.")
        worksheet_id, timestamp = str(uuid4()), now_iso()
        with database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO worksheets(id,owner_id,title,sha256,pages,questions,notes,published,revision,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,0,1,?,?)",
                (worksheet_id, user["id"], title, sha256, encode(metadata["pages"]), encode(questions), notes, timestamp, timestamp),
            )
        return worksheet_object(database.one("SELECT * FROM worksheets WHERE owner_id=? AND sha256=?", (user["id"], sha256)), user)

    @application.post("/api/samples/import", status_code=201)
    def import_sample(payload: SampleBody, user=Depends(require_teacher)):
        try:
            content, preset = samples.load_sample(payload.filename)
        except (ValueError, FileNotFoundError, KeyError) as error:
            raise HTTPException(404, str(error)) from None
        return import_content(content, preset["title"], preset["questions"], preset.get("notes", ""), user)

    @application.post("/api/worksheets/upload", status_code=201)
    def upload_worksheet(
        file: UploadFile = File(...), title: str = Form(...), user=Depends(require_teacher),
    ):
        title = title.strip()
        if not title or len(title) > 200:
            raise HTTPException(422, "Enter a worksheet title of 1–200 characters.")
        try:
            content = file.file.read(MAX_PDF_BYTES + 1)
        finally:
            file.file.close()
        preset = samples.preset_for_content(content)
        return import_content(
            content, title, preset["questions"] if preset else [],
            preset.get("notes", "") if preset else "Draw answer areas and confirm a marking key before publishing.", user,
        )

    @application.get("/api/worksheets/{worksheet_id}")
    def get_worksheet(worksheet_id: str, user=Depends(require_user)):
        return worksheet_object(authorized_worksheet(database, worksheet_id, user), user)

    @application.get("/api/worksheets/{worksheet_id}/pages/{page}.png")
    def get_page(worksheet_id: str, page: int, user=Depends(require_user)):
        row = authorized_worksheet(database, worksheet_id, user)
        if page < 0 or page >= len(json.loads(row["pages"])):
            raise HTTPException(404, "Page not found.")
        return FileResponse(document_path(row["sha256"], f"-{page}.png"), media_type="image/png")

    @application.get("/api/worksheets/{worksheet_id}/pdf")
    def get_pdf(worksheet_id: str, user=Depends(require_user)):
        row = authorized_worksheet(database, worksheet_id, user)
        return FileResponse(document_path(row["sha256"], ".pdf"), media_type="application/pdf", filename="worksheet.pdf")

    @application.put("/api/worksheets/{worksheet_id}")
    def update_worksheet(worksheet_id: str, payload: WorksheetUpdate, user=Depends(require_teacher)):
        data = payload.model_dump()
        row = authorized_worksheet(database, worksheet_id, user)
        if any(question["page"] >= len(json.loads(row["pages"])) for question in data["questions"]):
            raise HTTPException(422, "An answer area refers to a missing PDF page.")
        if data["published"] and (not data["questions"] or not data["keys_confirmed"]):
            raise HTTPException(422, "Add answer areas and confirm the marking key before publishing.")
        with database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE worksheets SET title=?,questions=?,published=?,revision=revision+1,updated_at=? WHERE id=? AND owner_id=? AND revision=?",
                (data["title"], encode(data["questions"]), int(data["published"]), now_iso(), worksheet_id, user["id"], data["revision"]),
            )
            if cursor.rowcount != 1:
                raise HTTPException(409, "This worksheet changed in another tab. Reload before saving.")
        return worksheet_object(authorized_worksheet(database, worksheet_id, user), user)

    def insert_attempt(connection, worksheet, user, previous=None, attempt_id=None):
        """Snapshot the published rubric while holding the database write lock."""
        attempt_id, timestamp = attempt_id or str(uuid4()), now_iso()
        questions = json.loads(worksheet["questions"])
        summary = grading.summarize(pending_results(questions, "Not submitted yet."))
        connection.execute(
            "INSERT INTO attempts(id,worksheet_id,student_id,teacher_id,title,sha256,pages,questions,worksheet_revision,summary,created_at,updated_at,attempt_number,previous_attempt_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, worksheet["id"], user["id"], user["teacher_id"], worksheet["title"], worksheet["sha256"], worksheet["pages"],
             worksheet["questions"], worksheet["revision"], encode(summary), timestamp, timestamp,
             previous["attempt_number"] + 1 if previous else 1, previous["id"] if previous else None),
        )
        return attempt_id

    @application.post("/api/worksheets/{worksheet_id}/attempts", status_code=201)
    def start_attempt(worksheet_id: str, user=Depends(require_student)):
        worksheet = authorized_worksheet(database, worksheet_id, user)
        with database.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM attempts WHERE worksheet_id=? AND student_id=? ORDER BY attempt_number DESC LIMIT 1",
                (worksheet_id, user["id"]),
            ).fetchone()
            if existing:
                attempt_id = existing["id"]
            else:
                # Fetch the key under the write lock so its revision is a coherent snapshot.
                worksheet = dict(connection.execute("SELECT * FROM worksheets WHERE id=?", (worksheet_id,)).fetchone())
                if not worksheet["published"]:
                    raise HTTPException(403, "This worksheet is not currently published.")
                attempt_id = insert_attempt(connection, worksheet, user)
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.post("/api/attempts/{attempt_id}/retry", status_code=201)
    def retry_attempt(attempt_id: str, payload: VersionBody, user=Depends(require_student)):
        authorized_attempt(database, attempt_id, user)
        with database.transaction() as connection:
            previous = dict(connection.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            require_version(previous, payload.version)
            if previous["status"] not in {"review", "graded"}:
                raise HTTPException(409, "Finish submitting this attempt before starting another. Marking must finish first.")
            worksheet = dict(connection.execute("SELECT * FROM worksheets WHERE id=?", (previous["worksheet_id"],)).fetchone())
            if worksheet["owner_id"] != user["teacher_id"] or not worksheet["published"]:
                raise HTTPException(403, "This worksheet is not currently published. Your previous work remains available.")
            latest = dict(connection.execute(
                "SELECT * FROM attempts WHERE worksheet_id=? AND student_id=? ORDER BY attempt_number DESC LIMIT 1",
                (previous["worksheet_id"], user["id"]),
            ).fetchone())
            if latest["id"] != previous["id"]:
                if latest["status"] != "draft":
                    raise HTTPException(409, "A newer attempt already exists. Open your latest attempt before trying again.")
                # Double-clicks, lost responses, and another tab reuse the same
                # active draft; never clear its answers or create a second one.
                next_id = latest["id"]
            else:
                next_id = insert_attempt(connection, worksheet, user, previous)
        return attempt_object(authorized_attempt(database, next_id, user), user)

    @application.get("/api/attempts")
    def list_attempts(user=Depends(require_user)):
        condition = "a.teacher_id=?" if user["role"] == "teacher" else "a.student_id=?"
        rows = database.all(
            f"SELECT a.*,u.name AS student_name FROM attempts a JOIN users u ON u.id=a.student_id WHERE {condition} ORDER BY a.updated_at DESC",
            (user["id"],),
        )
        return {"attempts": [{
            "id": row["id"], "worksheet_id": row["worksheet_id"], "student_name": row["student_name"],
            "attempt_number": row["attempt_number"], "previous_attempt_id": row["previous_attempt_id"],
            "student_id": row["student_id"], "title": row["title"], "worksheet_title": row["title"],
            "status": row["status"], "version": row["version"], "summary": json.loads(row["summary"]),
            "submission_mode": row["submission_mode"],
            "updated_at": row["updated_at"], "submitted_at": row["submitted_at"],
        } for row in rows]}

    @application.get("/api/attempts/{attempt_id}")
    def get_attempt(attempt_id: str, user=Depends(require_user)):
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.put("/api/attempts/{attempt_id}/answers")
    def save_answers(attempt_id: str, payload: AnswersUpdate, user=Depends(require_student)):
        row = authorized_attempt(database, attempt_id, user)
        data = payload.model_dump()
        ids = {question["id"] for question in json.loads(row["questions"])}
        if set(data["answers"]) - ids:
            raise HTTPException(422, "An answer refers to a question that is not on this worksheet.")
        with database.transaction() as connection:
            current = dict(connection.execute("SELECT status,version FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            require_version(current, data["version"])
            if current["status"] != "draft":
                raise HTTPException(409, "This attempt has been submitted. Use Try again for a new attempt, or ask your teacher to reopen the latest one.")
            connection.execute(
                "UPDATE attempts SET answers=?,version=version+1,updated_at=? WHERE id=?",
                (encode(data["answers"]), now_iso(), attempt_id),
            )
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.post("/api/attempts/{attempt_id}/submit")
    def submit_attempt(attempt_id: str, payload: VersionBody, user=Depends(require_student)):
        row = authorized_attempt(database, attempt_id, user)
        if row["status"] != "draft":
            return attempt_object(row, user)
        with database.transaction() as connection:
            current = dict(connection.execute("SELECT status,version FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            if current["status"] != "draft":
                return attempt_object(authorized_attempt(database, attempt_id, user), user)
            require_version(current, payload.version)
            timestamp = now_iso()
            connection.execute(
                "UPDATE attempts SET status='grading',submission_mode='online',version=version+1,submitted_at=?,updated_at=?,grading_started=?,grading_tries=0 WHERE id=?",
                (timestamp, timestamp, time.time(), attempt_id),
            )
        schedule_grading(attempt_id)
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    def read_uploads(files):
        if not files:
            raise HTTPException(422, "Choose the photo or scan of the completed worksheet.")
        if len(files) > paper.MAX_PAGES:
            for upload in files:
                upload.file.close()
            raise HTTPException(422, "Upload at most 10 files.")
        contents, total = [], 0
        try:
            for upload in files:
                content = upload.file.read(paper.MAX_FILE_BYTES + 1)
                if len(content) > paper.MAX_FILE_BYTES:
                    raise HTTPException(413, "Each uploaded file must be 20 MB or smaller.")
                total += len(content)
                if total > MAX_PAPER_BYTES:
                    raise HTTPException(413, "The uploaded files are larger than 60 MB in total.")
                contents.append(content)
        finally:
            for upload in files:
                upload.file.close()
        return contents

    def prepare_paper(attempt_id, source, contents, user):
        """Match every uploaded page before any attempt changes, then keep the evidence."""
        page_count = len(json.loads(source["pages"]))
        if not application.state.document_slots.acquire(blocking=False):
            raise HTTPException(503, "Page processing is busy. Please upload again in a moment.")
        try:
            references = [paper.load_gray(document_path(source["sha256"], f"-{index}.png")) for index in range(page_count)]
            try:
                alignments = paper.match_pages(references, paper.load_pages(contents))
            except paper.PaperError as error:
                raise HTTPException(422, str(error)) from None
        finally:
            application.state.document_slots.release()
        upload_id = str(uuid4())
        folder = submission_directory(attempt_id, upload_id)
        folder.mkdir(parents=True, exist_ok=False)
        files = []
        for number, content in enumerate(contents, start=1):
            name = f"upload-{number}.{file_type(content)}"
            (folder / name).write_bytes(content)
            files.append({"name": name, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
        return {
            "upload_id": upload_id, "uploaded_at": now_iso(), "uploaded_by": user["id"],
            "uploaded_by_role": user["role"], "files": files,
            "pages": [paper.save_alignment(alignment, folder, index) for index, alignment in enumerate(alignments)],
        }

    def claim_paper(connection, attempt_id, record):
        timestamp = now_iso()
        connection.execute(
            "UPDATE attempts SET submission_mode='paper',paper=?,status='grading',version=version+1,submitted_at=?,updated_at=?,grading_started=?,grading_tries=0 WHERE id=?",
            (encode(record), timestamp, timestamp, time.time(), attempt_id),
        )

    @application.post("/api/attempts/{attempt_id}/paper")
    def upload_paper(attempt_id: str, version: Annotated[int, Form(ge=1)], files: list[UploadFile] = File(...),
                     user=Depends(require_student)):
        row = authorized_attempt(database, attempt_id, user)
        if row["status"] != "draft":
            raise HTTPException(409, "This attempt has already been handed in. Use Try again to hand in a new paper copy.")
        require_version(row, version)
        record = prepare_paper(attempt_id, row, read_uploads(files), user)
        with database.transaction() as connection:
            current = dict(connection.execute("SELECT status,version FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            if current["status"] != "draft":
                raise HTTPException(409, "This attempt was handed in from another tab.")
            require_version(current, version)
            claim_paper(connection, attempt_id, record)
        schedule_grading(attempt_id)
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.post("/api/worksheets/{worksheet_id}/paper", status_code=201)
    def teacher_upload_paper(worksheet_id: str, student_id: Annotated[str, Form(min_length=1, max_length=80)],
                             files: list[UploadFile] = File(...), replace_draft: Annotated[bool, Form()] = False,
                             user=Depends(require_teacher)):
        worksheet = authorized_worksheet(database, worksheet_id, user)
        student = database.one("SELECT id,teacher_id FROM users WHERE id=? AND role='student' AND teacher_id=?", (student_id, user["id"]))
        if student is None:
            raise HTTPException(404, "That student is not in your class.")
        if not worksheet["published"]:
            raise HTTPException(409, "Publish this worksheet with a confirmed marking key before uploading student papers.")

        def latest_attempt(source):
            row = source.execute(
                "SELECT * FROM attempts WHERE worksheet_id=? AND student_id=? ORDER BY attempt_number DESC LIMIT 1",
                (worksheet_id, student_id),
            ).fetchone()
            return dict(row) if row else None

        with database.connection() as connection:
            latest = latest_attempt(connection)
        if latest and latest["status"] == "grading":
            raise HTTPException(409, "This student's latest attempt is still being marked. Upload again when marking finishes.")
        use_draft = bool(latest and latest["status"] == "draft")
        if use_draft and json.loads(latest["answers"]) and not replace_draft:
            raise HTTPException(409, "This student has an unfinished online attempt with saved answers. Confirm that the paper copy should be marked instead.")
        attempt_id = latest["id"] if use_draft else str(uuid4())
        record = prepare_paper(attempt_id, latest if use_draft else worksheet, read_uploads(files), user)
        with database.transaction() as connection:
            current = latest_attempt(connection)
            planned = (latest["id"], latest["status"], latest["version"]) if latest else None
            observed = (current["id"], current["status"], current["version"]) if current else None
            if observed != planned:
                raise HTTPException(409, "This student's work changed while the pages were being checked. Please upload again.")
            if not use_draft:
                fresh = dict(connection.execute("SELECT * FROM worksheets WHERE id=?", (worksheet_id,)).fetchone())
                if not fresh["published"]:
                    raise HTTPException(409, "This worksheet was unpublished. Publish it again before uploading papers.")
                insert_attempt(connection, fresh, student, current, attempt_id=attempt_id)
            claim_paper(connection, attempt_id, record)
        schedule_grading(attempt_id)
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    def paper_record(row):
        record = json.loads(row["paper"] or "{}")
        if row.get("submission_mode") != "paper" or not record.get("upload_id"):
            raise HTTPException(404, "This attempt has no paper submission.")
        return record

    @application.get("/api/attempts/{attempt_id}/paper/pages/{page}.png")
    def paper_page(attempt_id: str, page: int, user=Depends(require_user)):
        row = authorized_attempt(database, attempt_id, user)
        record = paper_record(row)
        if not any(item["index"] == page for item in record.get("pages", [])):
            raise HTTPException(404, "Page not found.")
        path = submission_directory(row["id"], record["upload_id"]) / f"page-{page}.png"
        if not path.is_file():
            raise HTTPException(404, "The paper page is missing. Ask your teacher to restore the server backup.")
        return FileResponse(path, media_type="image/png")

    @application.get("/api/attempts/{attempt_id}/paper/answers/{question_id}.png")
    def paper_answer(attempt_id: str, question_id: str, user=Depends(require_user)):
        row = authorized_attempt(database, attempt_id, user)
        paper_record(row)
        question = next((item for item in json.loads(row["questions"]) if item["id"] == question_id), None)
        if question is None or question["kind"] not in {"number", "text"}:
            raise HTTPException(404, "No isolated writing is available for this answer.")
        try:
            evidence = paper_evidence(row)(question)
        except (paper.PaperError, KeyError, OSError, ValueError):
            raise HTTPException(404, "The paper evidence is unavailable.") from None
        output = BytesIO()
        evidence["image"].save(output, format="PNG")
        return Response(output.getvalue(), media_type="image/png")

    @application.post("/api/attempts/{attempt_id}/review")
    def review_attempt(attempt_id: str, payload: ReviewUpdate, user=Depends(require_teacher)):
        authorized_attempt(database, attempt_id, user)
        data = payload.model_dump()
        with database.transaction() as connection:
            row = dict(connection.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            require_version(row, data["version"])
            if row["status"] not in {"review", "graded"}:
                raise HTTPException(409, "Only a submitted, completed attempt can be reviewed.")
            results = json.loads(row["results"])
            by_id = {item["question_id"]: item for item in results}
            seen = set()
            for review in data["reviews"]:
                question_id = review["question_id"]
                if question_id not in by_id or question_id in seen:
                    raise HTTPException(422, "Review contains an unknown or repeated question.")
                seen.add(question_id)
                result = by_id[question_id]
                awarded = review["awarded"]
                if awarded < 0 or awarded > result["max_points"]:
                    raise HTTPException(422, "Awarded marks must be between zero and the question's maximum.")
                result.update({
                    "awarded": awarded,
                    "status": "correct" if awarded == result["max_points"] else "incorrect" if awarded == 0 else "partial",
                    "feedback": review["feedback"], "source": "teacher", "confidence": None,
                })
                if review.get("recognized_text") is not None:
                    result["recognized_text"] = review["recognized_text"]
            summary = grading.summarize(results)
            connection.execute(
                "UPDATE attempts SET results=?,summary=?,status=?,version=version+1,updated_at=? WHERE id=?",
                (encode(results), encode(summary), "graded" if summary["final"] else "review", now_iso(), attempt_id),
            )
            connection.execute(
                "INSERT INTO review_audit(id,attempt_id,teacher_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid4()), attempt_id, user["id"], "review", encode({**data, "previous_results": json.loads(row["results"])}), now_iso()),
            )
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.post("/api/attempts/{attempt_id}/reopen")
    def reopen_attempt(attempt_id: str, payload: VersionBody, user=Depends(require_teacher)):
        authorized_attempt(database, attempt_id, user)
        with database.transaction() as connection:
            row = dict(connection.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone())
            require_version(row, payload.version)
            if row["status"] not in {"review", "graded"}:
                raise HTTPException(409, "Only a submitted, completed attempt can be reopened.")
            if connection.execute(
                "SELECT id FROM attempts WHERE worksheet_id=? AND student_id=? AND attempt_number>? LIMIT 1",
                (row["worksheet_id"], row["student_id"], row["attempt_number"]),
            ).fetchone():
                raise HTTPException(409, "A newer attempt exists. Only the student's latest attempt can be reopened; previous results are preserved.")
            summary = grading.summarize(pending_results(json.loads(row["questions"]), "Not submitted yet."))
            # A returned attempt is edited online; its earlier paper upload stays on record.
            connection.execute(
                "UPDATE attempts SET status='draft',submission_mode='online',results='[]',summary=?,version=version+1,submitted_at=NULL,grading_started=NULL,updated_at=? WHERE id=?",
                (encode(summary), now_iso(), attempt_id),
            )
            connection.execute(
                "INSERT INTO review_audit(id,attempt_id,teacher_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
                (str(uuid4()), attempt_id, user["id"], "reopen", encode({
                    "previous_results": json.loads(row["results"]), "previous_summary": json.loads(row["summary"]),
                    "previous_submission_mode": row["submission_mode"], "previous_paper": json.loads(row["paper"] or "{}"),
                }), now_iso()),
            )
        return attempt_object(authorized_attempt(database, attempt_id, user), user)

    @application.get("/api/attempts/{attempt_id}/report.pdf")
    def report(attempt_id: str, user=Depends(require_user)):
        row = authorized_attempt(database, attempt_id, user)
        output = attempt_object(row, user)
        backgrounds = None
        if output["submission_mode"] == "paper":
            record = paper_record(row)
            folder = submission_directory(row["id"], record["upload_id"])
            backgrounds = [folder / f"page-{index}.png" for index in range(len(output["pages"]))]
            output = {**output, "answers": {}}
        if not application.state.document_slots.acquire(blocking=False):
            raise HTTPException(503, "Document processing is busy. Please download the report again shortly.")
        try:
            content = documents.report_pdf(document_path(row["sha256"], ".pdf"), output, backgrounds=backgrounds)
        finally:
            application.state.document_slots.release()
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="worksheet-results.pdf"'})

    @application.get("/api/results.csv")
    def results_csv(user=Depends(require_teacher)):
        rows = database.all(
            "SELECT a.*,u.name AS student_name,u.username FROM attempts a JOIN users u ON u.id=a.student_id WHERE a.teacher_id=? ORDER BY a.updated_at DESC",
            (user["id"],),
        )
        stream = StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["Student", "Username", "Worksheet", "Status", "Confirmed marks", "Maximum marks", "Pending questions", "Final percentage", "Submitted at", "Attempt number", "Attempt ID", "Previous attempt ID", "Submission type"])
        for row in rows:
            summary = json.loads(row["summary"])
            writer.writerow([safe_csv(value) for value in (
                row["student_name"], row["username"], row["title"], row["status"], summary.get("earned"),
                summary.get("total"), summary.get("pending"), summary.get("percentage"), row["submitted_at"],
                row["attempt_number"], row["id"], row["previous_attempt_id"],
                "Paper upload" if row["submission_mode"] == "paper" else "Online",
            )])
        return Response("\ufeff" + stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="worksheet-marks.csv"'})

    application.mount("/static", StaticFiles(directory=ROOT / "static", check_dir=False), name="assets")
    application.mount("/", StaticFiles(directory=ROOT / "static", html=True, check_dir=False), name="static")
    return application
