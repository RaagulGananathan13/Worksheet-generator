"""Replay labelled synthetic pen strokes through the normal local student API.

This is a test-data helper, not a completed-PDF importer or an OCR shortcut.
It never writes to the database, uploads a marking key, or supplies a score.
Run with --help. Passwords are prompted, never accepted as command arguments.
"""

import argparse
import getpass
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.samples import HASHES
from app.schemas import AnswersUpdate, Option, Rect, StrictModel

MAX_FIXTURE_BYTES = 24 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024


class ReplayError(Exception):
    """A safe refusal or actionable API failure."""


class PublicQuestion(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=0, le=9)
    rect: Rect
    kind: Literal["number", "text", "choice", "manual"]
    points: float = Field(gt=0, le=100)
    options: list[Option] = Field(default_factory=list, max_length=30)


class Fixture(StrictModel):
    format: Literal["geniusbees-synthetic-ink-v1"]
    synthetic: Literal[True]
    source_filename: str
    source_sha256: str
    scenario: Literal["correct", "mixed"]
    questions: list[PublicQuestion] = Field(min_length=1, max_length=100)
    answers: dict

    @model_validator(mode="after")
    def validate_fixture(self):
        if HASHES.get(self.source_filename) != self.source_sha256:
            raise ValueError("Fixture must identify one of the six unchanged original sample PDFs.")
        ids = {question.id for question in self.questions}
        if len(ids) != len(self.questions):
            raise ValueError("Fixture question IDs must be unique.")
        if set(self.answers) - ids:
            raise ValueError("Fixture contains answers for unknown questions.")
        validated = AnswersUpdate.model_validate({"version": 1, "answers": self.answers})
        self.answers = validated.model_dump()["answers"]
        return self


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def load_fixture(path):
    try:
        with Path(path).open("rb") as handle:
            content = handle.read(MAX_FIXTURE_BYTES + 1)
        if len(content) > MAX_FIXTURE_BYTES:
            raise ReplayError("Fixture exceeds the 24 MB safety limit.")
        return Fixture.model_validate(json.loads(content, object_pairs_hook=_unique_json_object))
    except (OSError, UnicodeError, ValueError, ValidationError) as error:
        raise ReplayError(f"Cannot load synthetic fixture: {error}") from error


def validate_base_url(value):
    """Do not send a student's password to an arbitrary host or environment proxy."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Use an http:// or https:// URL.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Use only the server origin, without credentials, path, query or fragment.")
        host = parsed.hostname.lower()
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError("Only localhost or a loopback IP address is allowed.")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid server port.")
    except ValueError as error:
        raise ReplayError(f"Unsafe --base-url: {error}") from error
    return value.rstrip("/")


def _response_json(response):
    if not 200 <= response.status_code < 300:
        # Avoid dumping server bodies, cookies or credentials into logs.
        hints = {
            401: "Check the student username and password, and that the server is running with the intended data folder.",
            403: "This account or session cannot perform this action. Use a student in the correct classroom.",
            404: "The worksheet or attempt is no longer accessible to this student.",
            409: "The work changed or was submitted. Reload it; use Try again in the student browser for a new attempt, or ask the teacher to return the latest submission.",
            429: "Too many login attempts. Wait 15 minutes before trying again.",
            503: "Marking is busy. Saved work is retained; submit from the student page later.",
        }
        raise ReplayError(f"Server returned HTTP {response.status_code}. " + hints.get(response.status_code, "Check the server terminal for details."))
    try:
        result = response.json()
    except ValueError as error:
        raise ReplayError("Server returned an invalid JSON response.") from error
    if not isinstance(result, dict):
        raise ReplayError("Server returned an unexpected response shape.")
    return result


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ReplayError("Server returned an invalid worksheet or attempt identifier.")
    return value


def _pdf_digest(client, worksheet_id):
    digest, size = hashlib.sha256(), 0
    with client.stream("GET", f"/api/worksheets/{worksheet_id}/pdf", follow_redirects=False) as response:
        if response.status_code != 200:
            raise ReplayError(f"Cannot verify worksheet PDF (HTTP {response.status_code}).")
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ReplayError("Server PDF exceeds the 20 MB safety limit.")
            digest.update(chunk)
    return digest.hexdigest()


def _same_rect(left, right):
    if left is None or right is None:
        return left is right
    return all(math.isclose(left[key], right[key], rel_tol=0, abs_tol=1e-8) for key in ("x", "y", "w", "h"))


def check_geometry(fixture, attempt):
    try:
        current = [PublicQuestion.model_validate(question) for question in attempt["questions"]]
    except (KeyError, TypeError, ValidationError) as error:
        raise ReplayError("Server returned invalid public question data. No ink was saved.") from error
    by_id = {question.id: question for question in current}
    if len(by_id) != len(current) or set(by_id) != {question.id for question in fixture.questions}:
        raise ReplayError("Attempt questions differ from the demo. Use the unchanged sample preset; no ink was saved.")
    for question in fixture.questions:
        live = by_id[question.id]
        compatible = question.page == live.page and question.kind == live.kind and _same_rect(question.rect.model_dump(), live.rect.model_dump())
        # Choice hit boxes are page-relative and must match as well.
        if len(question.options) != len(live.options):
            compatible = False
        else:
            expected_options = {option.value: option for option in question.options}
            live_options = {option.value: option for option in live.options}
            if len(expected_options) != len(question.options) or len(live_options) != len(live.options) or set(expected_options) != set(live_options):
                compatible = False
            else:
                for value, option in expected_options.items():
                    other = live_options[value]
                    if not _same_rect(option.rect.model_dump() if option.rect else None, other.rect.model_dump() if other.rect else None):
                        compatible = False
        if not compatible:
            raise ReplayError(f"Answer region/type for {question.id} differs from the demo. No ink was saved.")


def _has_answers(answers):
    return any(answer.get("text", "").strip() or answer.get("strokes") for answer in answers.values())


def replay(client, fixture, username, password, *, submit=False, replace_draft=False, output=print):
    """Use the real authenticated API; injected httpx clients support isolated tests."""
    validate_base_url(str(client.base_url))
    authenticated = False
    try:
        session = _response_json(client.post("/api/login", json={"username": username, "password": password}, follow_redirects=False))
        authenticated = True
        csrf = session.get("csrf_token")
        if not isinstance(csrf, str) or not csrf:
            raise ReplayError("Login did not return a CSRF token.")
        client.headers["X-CSRF-Token"] = csrf
        if session.get("user", {}).get("role") != "student":
            raise ReplayError("This helper only accepts a student account. It will not change a teacher's classroom.")
        listing = _response_json(client.get("/api/worksheets", follow_redirects=False))
        matches = []
        for worksheet in listing.get("worksheets", []):
            if not worksheet.get("published"):
                continue
            worksheet_id = _identifier(worksheet.get("id"))
            if _pdf_digest(client, worksheet_id) == fixture.source_sha256:
                matches.append(worksheet_id)
        if len(matches) != 1:
            raise ReplayError("No unique published original sample matches this fixture. Ask the teacher to import and publish " + fixture.source_filename + " in this student's classroom.")
        attempt = _response_json(client.post(f"/api/worksheets/{matches[0]}/attempts", json={}, follow_redirects=False))
        attempt_id = _identifier(attempt.get("id"))
        if attempt.get("status") != "draft":
            raise ReplayError("This student already submitted this worksheet. Use Try again in the student browser to create a new draft, ask the teacher to return the latest submission, or use a fresh demo student. Nothing was overwritten.")
        check_geometry(fixture, attempt)
        if _has_answers(attempt.get("answers", {})) and not replace_draft:
            raise ReplayError("The draft already contains answers. Use a fresh demo student, or explicitly pass --replace-draft to replace ALL draft answers.")
        payload = AnswersUpdate.model_validate({"version": attempt.get("version"), "answers": fixture.answers}).model_dump()
        saved = _response_json(client.put(f"/api/attempts/{attempt_id}/answers", json=payload, follow_redirects=False))
        output(f"Saved SYNTHETIC demo ink to student attempt {attempt_id}.")
        if not submit:
            output("Not submitted. Log in as this student, open the worksheet, inspect the ink, then choose Submit worksheet.")
            return saved
        output("Submitting through the real marking service. Synthetic writing is not proof of real handwriting accuracy; pending review is expected when OCR is uncertain.")
        try:
            return _response_json(client.post(f"/api/attempts/{attempt_id}/submit", json={"version": saved["version"]}, timeout=180, follow_redirects=False))
        except httpx.TimeoutException:
            output("Submission response timed out. Ink was saved. Checking the attempt once; do not assume grading failed or resubmit blindly.")
            try:
                return _response_json(client.get(f"/api/attempts/{attempt_id}", follow_redirects=False))
            except (httpx.HTTPError, ReplayError) as error:
                raise ReplayError("Could not confirm grading status after the timeout. Open this student's worksheet to check the saved result; no automatic retry was sent.") from error
    except httpx.HTTPError as error:
        raise ReplayError("Could not reach the local server. Start run.py and check the --base-url. If work was already saved, check it in the browser before retrying.") from error
    finally:
        if authenticated:
            try:
                response = client.post("/api/logout", json={}, timeout=10, follow_redirects=False)
                if not 200 <= response.status_code < 300:
                    raise ReplayError("Logout rejected.")
            except (httpx.HTTPError, ReplayError):
                output("Warning: could not revoke the helper's login session because logout failed. No password was saved; the server session will expire normally.")
            client.cookies.clear()
            client.headers.pop("X-CSRF-Token", None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path, help="Paired .synthetic.json from sample-worksheets/student-written-demos")
    parser.add_argument("--username", required=True, help="An already registered demo STUDENT username")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Local grading server only (default: http://127.0.0.1:8001)")
    parser.add_argument("--submit", action="store_true", help="Also submit for real marking; otherwise only save the draft")
    parser.add_argument("--replace-draft", action="store_true", help="Explicitly replace all existing draft answers for this student/sample")
    args = parser.parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url)
        fixture = load_fixture(args.fixture)
        print("This loads synthetic test data, not genuine student handwriting. Use a DEMO student; close their worksheet in other browser tabs first.")
        password = getpass.getpass("Demo student password (hidden): ")
        with httpx.Client(base_url=base_url, timeout=30, follow_redirects=False, trust_env=False) as client:
            result = replay(client, fixture, args.username, password, submit=args.submit, replace_draft=args.replace_draft)
        print(f"Attempt status: {result.get('status', 'unknown')}")
        summary = result.get("summary", {})
        if args.submit and result.get("status") in {"graded", "review"}:
            print(f"Server-confirmed marks: {summary.get('earned', 0)} / {summary.get('total', 0)}; pending teacher review: {summary.get('pending', 0)}.")
        if args.submit and result.get("status") == "grading":
            print("Grading is still running. Check the student or teacher results page shortly.")
        return 0
    except (ReplayError, ValidationError) as error:
        print(f"Stopped: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Cancelled. No password was stored.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
