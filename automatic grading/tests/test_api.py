"""Real HTTP-boundary tests; use ASGITransport to avoid TestClient version coupling."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from io import BytesIO
import asyncio
import hashlib
import json
import sys
import tempfile
import unittest

import httpx
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import hash_password
from app.server import create_app, encode, now_iso
from app import samples


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 1.0
        self.temporary = TemporaryDirectory(prefix=".api-tests-", dir=ROOT)
        self.app = create_app(self.temporary.name, testing=True)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.clients = []
        self.teacher = await self.client()
        response = await self.teacher.post("/api/bootstrap", json={
            "token": self.app.state.bootstrap_token, "name": "Teacher One",
            "username": "teacher", "password": "Teacher-password-123",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.teacher_user = response.json()["user"]
        self.teacher.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        self.student = await self.register("student-one")

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.temporary.cleanup()

    async def client(self):
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        self.clients.append(client)
        return client

    async def register(self, username):
        client = await self.client()
        response = await client.post("/api/register", json={
            "name": username, "username": username, "password": "Student-password-123",
            "class_code": self.teacher_user["class_code"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return client

    def question(self, identifier="q1", kind="number", expected=None, points=2):
        return {
            "id": identifier, "label": f"Question {identifier}", "page": 0,
            "rect": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.1},
            "kind": kind, "expected": ["9"] if expected is None else expected,
            "points": points, "tolerance": 0, "case_sensitive": False, "options": [],
        }

    def pdf(self):
        output = BytesIO()
        document = Canvas(output, pagesize=(612, 792))
        document.setTitle(str(uuid4()))
        document.drawString(100, 692, "4 + 5 =")
        document.showPage()
        document.save()
        return output.getvalue()

    async def worksheet(self, questions=None, published=True, title="Addition"):
        response = await self.teacher.post("/api/worksheets/upload", data={"title": title}, files={"file": ("worksheet.pdf", self.pdf(), "application/pdf")})
        self.assertEqual(response.status_code, 201, response.text)
        worksheet = response.json()
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": title, "questions": questions if questions is not None else [self.question()],
            "published": published, "keys_confirmed": published, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def attempt(self, worksheet, client=None):
        response = await (client or self.student).post(f"/api/worksheets/{worksheet['id']}/attempts", json={})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def save(self, attempt, answers, client=None):
        response = await (client or self.student).put(f"/api/attempts/{attempt['id']}/answers", json={"version": attempt["version"], "answers": answers})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def submit(self, attempt, client=None):
        response = await (client or self.student).post(f"/api/attempts/{attempt['id']}/submit", json={"version": attempt["version"]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_session_logout_and_password_storage(self):
        response = await self.teacher.get("/api/session")
        self.assertEqual(response.json()["user"]["role"], "teacher")
        self.assertNotIn("password_hash", response.text)
        row = self.app.state.database.one("SELECT * FROM users WHERE username='teacher'")
        self.assertTrue(row["password_hash"].startswith("scrypt:"))
        self.assertNotIn("Teacher-password", row["password_hash"])
        response = await self.teacher.post("/api/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.teacher.get("/api/session")).json()["user"], None)
        self.assertEqual((await self.teacher.get("/api/worksheets")).status_code, 401)

    async def test_origin_and_csrf_enforced(self):
        response = await self.teacher.post("/api/logout", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        response = await self.teacher.post("/api/logout", headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        stranger = await self.client()
        response = await stranger.post("/api/login", headers={"Origin": "null"}, json={"username": "teacher", "password": "Teacher-password-123"})
        self.assertEqual(response.status_code, 403)

    async def test_bootstrap_single_teacher_and_class_validation(self):
        response = await self.teacher.get("/api/health")
        self.assertFalse(response.json()["setup_required"])
        self.assertNotIn(self.app.state.bootstrap_token, response.text)
        response = await self.teacher.post("/api/bootstrap", json={"token": self.app.state.bootstrap_token, "name": "New", "username": "newteacher", "password": "long-password-123"})
        self.assertEqual(response.status_code, 409)
        stranger = await self.client()
        response = await stranger.post("/api/register", json={"name": "Bad class", "username": "bad-class", "password": "long-password-123", "class_code": "UNKNOWN"})
        self.assertEqual(response.status_code, 400)
        response = await stranger.post("/api/register", json={"name": "Bad role", "username": "bad-role", "password": "long-password-123", "class_code": self.teacher_user["class_code"], "role": "teacher"})
        self.assertEqual(response.status_code, 422)

    async def test_cookie_and_http_headers(self):
        client = await self.client()
        response = await client.post("/api/login", json={"username": "teacher", "password": "Teacher-password-123"})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    async def test_private_keys_and_unpublished_access(self):
        worksheet = await self.worksheet(published=False)
        self.assertEqual((await self.student.get(f"/api/worksheets/{worksheet['id']}")).status_code, 404)
        self.assertEqual((await self.student.get(f"/api/worksheets/{worksheet['id']}/pdf")).status_code, 404)
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": worksheet["title"], "questions": worksheet["questions"], "published": True,
            "keys_confirmed": True, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200)
        data = (await self.student.get(f"/api/worksheets/{worksheet['id']}")).json()
        for field in ("expected", "tolerance", "case_sensitive"):
            self.assertNotIn(field, data["questions"][0])
        attempt = await self.attempt(worksheet)
        self.assertNotIn("expected", attempt["questions"][0])
        teacher_view = (await self.teacher.get(f"/api/attempts/{attempt['id']}")).json()
        self.assertEqual(teacher_view["questions"][0]["expected"], ["9"])

    async def test_student_attempt_ownership_and_teacher_role(self):
        worksheet = await self.worksheet()
        attempt = await self.attempt(worksheet)
        other = await self.register("student-two")
        for suffix in ("", "/report.pdf"):
            self.assertEqual((await other.get(f"/api/attempts/{attempt['id']}{suffix}")).status_code, 404)
        response = await other.put(f"/api/attempts/{attempt['id']}/answers", json={"version": attempt["version"], "answers": {}})
        self.assertEqual(response.status_code, 404)
        self.assertEqual((await self.student.get("/api/samples")).status_code, 403)
        self.assertEqual((await self.student.get("/api/results.csv")).status_code, 403)
        response = await self.student.post(f"/api/attempts/{attempt['id']}/reopen", json={"version": attempt["version"]})
        self.assertEqual(response.status_code, 403)

    async def test_cross_teacher_isolation(self):
        worksheet = await self.worksheet()
        attempt = await self.attempt(worksheet)
        with self.app.state.database.transaction() as connection:
            connection.execute(
                "INSERT INTO users(id,name,username,password_hash,role,class_code,created_at) VALUES (?,?,?,?,?,?,?)",
                (str(uuid4()), "Other teacher", "other-teacher", hash_password("other-password-123"), "teacher", "OTHER12345", now_iso()),
            )
        other = await self.client()
        response = await other.post("/api/login", json={"username": "other-teacher", "password": "other-password-123"})
        self.assertEqual(response.status_code, 200)
        other.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        self.assertEqual((await other.get(f"/api/worksheets/{worksheet['id']}")).status_code, 404)
        self.assertEqual((await other.get(f"/api/attempts/{attempt['id']}")).status_code, 404)
        self.assertEqual((await other.get("/api/attempts")).json()["attempts"], [])

    async def test_optimistic_versions_and_unknown_answers(self):
        worksheet = await self.worksheet()
        attempt = await self.attempt(worksheet)
        saved = await self.save(attempt, {"q1": {"text": "9", "strokes": []}})
        response = await self.student.put(f"/api/attempts/{attempt['id']}/answers", json={"version": attempt["version"], "answers": {}})
        self.assertEqual(response.status_code, 409)
        response = await self.student.post(f"/api/attempts/{attempt['id']}/submit", json={"version": attempt["version"]})
        self.assertEqual(response.status_code, 409)
        response = await self.student.put(f"/api/attempts/{attempt['id']}/answers", json={"version": saved["version"], "answers": {"unknown": {"text": "9"}}})
        self.assertEqual(response.status_code, 422)
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={"title": "stale", "questions": worksheet["questions"], "published": True, "keys_confirmed": True, "revision": 1})
        self.assertEqual(response.status_code, 409)

    async def test_answer_validation_rejects_mixed_modalities_and_geometry(self):
        attempt = await self.attempt(await self.worksheet())
        for answer in (
            {"text": "9", "strokes": [{"points": [{"x": 0.1, "y": 0.2, "p": 0.5}], "width": 0.01}]},
            {"strokes": [{"points": [{"x": -0.1, "y": 0.2}]}]},
            {"text": "9", "awarded": 2},
        ):
            response = await self.student.put(f"/api/attempts/{attempt['id']}/answers", json={"version": attempt["version"], "answers": {"q1": answer}})
            self.assertEqual(response.status_code, 422, response.text)

    async def test_grading_is_server_side_and_submit_idempotent(self):
        attempt = await self.attempt(await self.worksheet())
        saved = await self.save(attempt, {"q1": {"text": "9"}})
        graded = await self.submit(saved)
        self.assertEqual(graded["status"], "graded")
        self.assertEqual(graded["summary"]["earned"], 2)
        self.assertEqual(graded["summary"]["percentage"], 100)
        again = await self.submit(saved)
        self.assertEqual(again["version"], graded["version"])
        response = await self.student.put(f"/api/attempts/{attempt['id']}/answers", json={"version": graded["version"], "answers": {}})
        self.assertEqual(response.status_code, 409)
        second = await self.attempt({"id": attempt["worksheet_id"]})
        self.assertEqual(second["id"], attempt["id"])

    async def test_attempt_key_snapshot_survives_teacher_edits(self):
        worksheet = await self.worksheet()
        attempt = await self.attempt(worksheet)
        changed = self.question(expected=["10"], points=8)
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": "Changed worksheet", "questions": [changed], "published": True,
            "keys_confirmed": True, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        graded = await self.submit(await self.save(attempt, {"q1": {"text": "9"}}))
        self.assertEqual(graded["summary"]["earned"], 2)
        self.assertEqual(graded["summary"]["total"], 2)
        self.assertEqual(graded["title"], "Addition")

    async def test_ocr_receives_ink_without_keys_and_correct_page_aspect(self):
        captured = []

        def recognize(strokes, kind, aspect_ratio=3):
            captured.append((strokes, kind, aspect_ratio))
            return {"text": "9", "confidence": 0.99, "reliable": True, "reason": "", "source": "test-recognizer"}

        self.app.state.recognizer = recognize
        attempt = await self.attempt(await self.worksheet())
        stroke = {"points": [{"x": 0.1, "y": 0.1, "p": 0.5}, {"x": 0.7, "y": 0.9, "p": 0.7}], "width": 0.01}
        graded = await self.submit(await self.save(attempt, {"q1": {"strokes": [stroke]}}))
        self.assertEqual(graded["summary"]["earned"], 2)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][1], "number")
        self.assertAlmostEqual(captured[0][2], (0.3 / 0.1) * (612 / 792))

    async def test_uncertain_ocr_remains_pending_and_teacher_review_audited(self):
        self.app.state.recognizer = lambda *args, **kwargs: {"text": "9", "confidence": 0.4, "reliable": False, "reason": "uncertain", "source": "test"}
        attempt = await self.attempt(await self.worksheet())
        saved = await self.save(attempt, {"q1": {"strokes": [{"points": [{"x": 0.2, "y": 0.3}]}]}})
        review = await self.submit(saved)
        self.assertEqual(review["status"], "review")
        self.assertIsNone(review["results"][0]["awarded"])
        self.assertIsNone(review["summary"]["percentage"])
        response = await self.teacher.post(f"/api/attempts/{attempt['id']}/review", json={"version": review["version"], "reviews": [{"question_id": "q1", "awarded": 3, "feedback": "too high"}]})
        self.assertEqual(response.status_code, 422)
        response = await self.teacher.post(f"/api/attempts/{attempt['id']}/review", json={"version": review["version"], "reviews": [{"question_id": "q1", "awarded": 1, "feedback": "Partial credit", "recognized_text": "9"}]})
        self.assertEqual(response.status_code, 200, response.text)
        final = response.json()
        self.assertTrue(final["summary"]["final"])
        self.assertEqual(final["summary"]["percentage"], 50)
        self.assertEqual(final["results"][0]["status"], "partial")
        audits = self.app.state.database.all("SELECT * FROM review_audit WHERE attempt_id=?", (attempt["id"],))
        self.assertEqual(len(audits), 1)
        evidence = json.loads(audits[0]["details"])
        self.assertEqual(evidence["previous_results"][0]["source"], "test")
        self.assertEqual(evidence["previous_results"][0]["recognized_text"], "9")
        self.assertEqual(evidence["previous_results"][0]["confidence"], 0.4)
        self.assertEqual(evidence["reviews"][0]["awarded"], 1)
        response = await self.teacher.post(f"/api/attempts/{attempt['id']}/reopen", json={"version": final["version"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["answers"], saved["answers"])
        self.assertEqual(response.json()["results"], [])

    async def test_pdf_integrity_rendering_and_report(self):
        content = self.pdf()
        response = await self.teacher.post("/api/worksheets/upload", data={"title": "Original"}, files={"file": ("original.pdf", content, "application/pdf")})
        worksheet = response.json()
        fetched = await self.teacher.get(f"/api/worksheets/{worksheet['id']}/pdf")
        self.assertEqual(fetched.content, content)
        self.assertEqual(hashlib.sha256(fetched.content).hexdigest(), hashlib.sha256(content).hexdigest())
        image = await self.teacher.get(f"/api/worksheets/{worksheet['id']}/pages/0.png")
        self.assertEqual(image.status_code, 200)
        self.assertTrue(image.content.startswith(b"\x89PNG"))
        self.assertEqual((await self.teacher.get(f"/api/worksheets/{worksheet['id']}/pages/-1.png")).status_code, 404)
        self.assertEqual((await self.teacher.get(f"/api/worksheets/{worksheet['id']}/pages/1.png")).status_code, 404)
        attempt = await self.attempt(await self.worksheet())
        graded = await self.submit(await self.save(attempt, {"q1": {"text": "9"}}))
        report = await self.student.get(f"/api/attempts/{graded['id']}/report.pdf")
        self.assertEqual(report.status_code, 200)
        document = PdfReader(BytesIO(report.content))
        self.assertGreaterEqual(len(document.pages), 2)
        self.assertIn("Final marks: 2 / 2", document.pages[-1].extract_text())

    async def test_invalid_pdf_publish_and_missing_page_rejected(self):
        response = await self.teacher.post("/api/worksheets/upload", data={"title": "Invalid"}, files={"file": ("fake.pdf", b"<script>bad</script>", "application/pdf")})
        self.assertEqual(response.status_code, 400)
        worksheet = await self.worksheet(published=False)
        for questions, confirm in (([], True), ([self.question()], False), ([{**self.question(), "page": 1}], True)):
            response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={"title": "Invalid", "questions": questions, "published": True, "keys_confirmed": confirm, "revision": worksheet["revision"]})
            self.assertEqual(response.status_code, 422, response.text)

    async def test_csv_formula_escape_and_finality(self):
        attempt = await self.attempt(await self.worksheet(title="=SUM(1,2)"))
        await self.submit(attempt)
        response = await self.teacher.get("/api/results.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=SUM(1,2)", response.text)
        self.assertIn("Confirmed marks", response.text)

    async def test_restart_recovers_claimed_grading_without_zero_marks(self):
        attempt = await self.attempt(await self.worksheet())
        with self.app.state.database.transaction() as connection:
            # Repeated interrupted marking must end in teacher review, never zero marks.
            connection.execute("UPDATE attempts SET status='grading',grading_started=1,grading_tries=3 WHERE id=?", (attempt["id"],))
        restarted = create_app(self.temporary.name, testing=True)
        async with restarted.router.lifespan_context(restarted):
            row = restarted.state.database.one("SELECT * FROM attempts WHERE id=?", (attempt["id"],))
            self.assertEqual(row["status"], "review")
            self.assertIsNone(json.loads(row["results"])[0]["awarded"])
            self.assertIsNone(json.loads(row["summary"])["percentage"])

    async def test_all_six_actual_samples_import_publish_and_score(self):
        listing = (await self.teacher.get("/api/samples")).json()["samples"]
        self.assertEqual(len(listing), 6)
        for sample in listing:
            with self.subTest(sample=sample["filename"]):
                response = await self.teacher.post("/api/samples/import", json={"filename": sample["filename"]})
                self.assertEqual(response.status_code, 201, response.text)
                worksheet = response.json()
                self.assertFalse(worksheet["published"])
                self.assertEqual(len(worksheet["questions"]), sample["question_count"])
                duplicate = await self.teacher.post("/api/samples/import", json={"filename": sample["filename"]})
                self.assertEqual(duplicate.json()["id"], worksheet["id"])
                response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={"title": worksheet["title"], "questions": worksheet["questions"], "published": True, "keys_confirmed": True, "revision": worksheet["revision"]})
                self.assertEqual(response.status_code, 200, response.text)
                attempt = await self.attempt(worksheet)
                answers = {
                    question["id"]: {"text": question["expected"][0]} if question["kind"] != "manual"
                    else {"strokes": [{"points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.8}]}]}
                    for question in worksheet["questions"]
                }
                marked = await self.submit(await self.save(attempt, answers))
                manual = [question for question in worksheet["questions"] if question["kind"] == "manual"]
                self.assertEqual(marked["summary"]["pending"], len(manual))
                self.assertEqual(marked["summary"]["earned"], sum(question["points"] for question in worksheet["questions"] if question["kind"] != "manual"))
                if not manual:
                    self.assertEqual(marked["summary"]["percentage"], 100)

    async def test_known_sample_upload_is_hash_based(self):
        source, preset = samples.load_sample("48544102.pdf")
        response = await self.teacher.post("/api/worksheets/upload", data={"title": "Renamed sample"}, files={"file": ("renamed.pdf", source, "application/pdf")})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(response.json()["questions"]), len(preset["questions"]))
        self.assertFalse(response.json()["published"])

    async def test_invalid_nonfinite_and_unicode_inputs_return_safe_errors(self):
        body = '{"title":"Invalid","revision":1,"questions":[{"id":"q1","label":"Q1","page":0,"rect":{"x":NaN,"y":0,"w":0.1,"h":0.1}}]}'
        response = await self.teacher.put("/api/worksheets/missing", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn('"input"', response.text)
        body = '{"token": "' + self.app.state.bootstrap_token + '", "name":"\\ud800","username":"invalid","password":"secret-password-123"}'
        response = await self.teacher.post("/api/bootstrap", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn("secret-password", response.text)
        self.assertNotIn(self.app.state.bootstrap_token, response.text)

    async def test_non_ascii_secret_tokens_are_rejected_without_crashing(self):
        response = await self.teacher.post("/api/bootstrap", json={
            "token": "\u00e9" * 30, "name": "Invalid", "username": "invalid", "password": "long-password-123",
        })
        self.assertEqual(response.status_code, 403, response.text)
        response = await self.teacher.post("/api/logout", headers={b"X-CSRF-Token": b"\xff"})
        self.assertEqual(response.status_code, 403, response.text)

    async def test_negative_or_nonfinite_review_marks_are_rejected(self):
        attempt = await self.submit(await self.attempt(await self.worksheet()))
        for mark in ("-1", "NaN", "Infinity", "3"):
            body = '{"version":' + str(attempt["version"]) + ',"reviews":[{"question_id":"q1","awarded":' + mark + ',"feedback":"test"}]}'
            response = await self.teacher.post(f"/api/attempts/{attempt['id']}/review", content=body, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422, response.text)
        unchanged = (await self.teacher.get(f"/api/attempts/{attempt['id']}")).json()
        self.assertEqual(unchanged["summary"]["earned"], 0)
        self.assertEqual(unchanged["version"], attempt["version"])

    async def test_document_backpressure_preserves_other_api_access(self):
        attempt = await self.attempt(await self.worksheet())
        slots = self.app.state.document_slots
        slots.acquire()
        slots.acquire()
        try:
            response = await self.student.get(f"/api/attempts/{attempt['id']}/report.pdf")
            self.assertEqual(response.status_code, 503)
            self.assertEqual((await self.student.get("/api/session")).status_code, 200)
            response = await self.teacher.post("/api/worksheets/upload", data={"title": "Busy"}, files={"file": ("busy.pdf", self.pdf(), "application/pdf")})
            self.assertEqual(response.status_code, 503)
        finally:
            slots.release()
            slots.release()

    async def test_request_body_limit_before_parsing(self):
        response = await self.teacher.post("/api/login", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": str(65 * 1024 * 1024)})
        self.assertEqual(response.status_code, 413)

    async def test_rotated_pdf_report_matches_displayed_ink_and_preserves_original(self):
        source = PdfReader(BytesIO(self.pdf()))
        writer = PdfWriter()
        source.pages[0].rotate(90)
        writer.add_page(source.pages[0])
        output = BytesIO()
        writer.write(output)
        original = output.getvalue()
        response = await self.teacher.post("/api/worksheets/upload", data={"title": "Rotated"}, files={"file": ("rotated.pdf", original, "application/pdf")})
        self.assertEqual(response.status_code, 201, response.text)
        worksheet = response.json()
        self.assertEqual(worksheet["pages"], [{"width": 792.0, "height": 612.0}])
        question = self.question(kind="manual", expected=[])
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": "Rotated", "questions": [question], "published": True,
            "keys_confirmed": True, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        attempt = await self.attempt(worksheet)
        await self.save(attempt, {"q1": {"strokes": [{"width": 0.05, "points": [{"x": 0.2, "y": 0.5, "p": 0.5}, {"x": 0.8, "y": 0.5, "p": 0.5}]}]}})
        response = await self.student.get(f"/api/attempts/{attempt['id']}/report.pdf")
        self.assertEqual(response.status_code, 200)
        result = pdfium.PdfDocument(response.content)
        try:
            page = result.get_page(0)
            try:
                self.assertEqual(page.get_rotation(), 0)
                self.assertEqual(page.get_size(), (792, 612))
                bitmap = page.render(scale=1)
                try:
                    image = bitmap.to_pil()
                    try:
                        # Same displayed, normalized midpoint as the browser.
                        red, green, blue = image.convert("RGB").getpixel((round((0.2 + 0.3 * 0.5) * 792), round((0.2 + 0.1 * 0.5) * 612)))
                        self.assertLess(red, 80)
                        self.assertLess(green, 100)
                        self.assertGreater(blue, red)
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            result.close()
        fetched = await self.teacher.get(f"/api/worksheets/{worksheet['id']}/pdf")
        self.assertEqual(fetched.content, original)

    async def test_large_upload_spooling_stays_inside_application_data(self):
        expected = Path(self.temporary.name).resolve() / "tmp"
        self.assertEqual(Path(tempfile.gettempdir()).resolve(), expected)
        # SpooledTemporaryFile is the mechanism used by Starlette's multipart
        # parser. On Windows its rolled file has an inspectable absolute path.
        with tempfile.SpooledTemporaryFile(max_size=10) as spool:
            spool.write(b"a" * 20)
            self.assertTrue(spool._rolled)
            if isinstance(spool.name, str):
                self.assertTrue(Path(spool.name).resolve().is_relative_to(expected))


if __name__ == "__main__":
    unittest.main()
