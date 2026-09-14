"""Synthetic replay stays inside the real student API and refuses unsafe inputs."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.replay_demo_submission import Fixture, ReplayError, load_fixture, replay, validate_base_url

PDF = b"%PDF-1.7 test-only original bytes"
DIGEST = hashlib.sha256(PDF).hexdigest()


def fixture_dict():
    return {
        "format": "geniusbees-synthetic-ink-v1", "synthetic": True,
        "source_filename": "48544102.pdf", "source_sha256": DIGEST, "scenario": "correct",
        "questions": [{"id": "add-1", "label": "2 + 1", "page": 0,
                       "rect": {"x": .1, "y": .2, "w": .2, "h": .1},
                       "kind": "number", "points": 1, "options": []}],
        "answers": {"add-1": {"text": "", "strokes": [
            {"width": .009, "points": [{"x": .1, "y": .1, "p": .5}, {"x": .6, "y": .6, "p": .5}]}]}},
    }


class FakeServer:
    def __init__(self, fixture):
        self.calls = []
        self.role = "student"
        self.published = True
        self.pdf = PDF
        self.save_status = 200
        self.submit_timeout = False
        self.logout_status = 200
        self.attempt = {"id": "attempt-1", "status": "draft", "version": 1, "answers": {},
                        "questions": copy.deepcopy(fixture["questions"]), "summary": {"earned": 0, "total": 1, "pending": 1}}

    def handle(self, request):
        payload = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, payload))
        path = request.url.path
        if path == "/api/login":
            return httpx.Response(200, json={"user": {"role": self.role}, "csrf_token": "csrf-test"}, headers={"set-cookie": "ag_session=test-session; Path=/; HttpOnly"})
        if path != "/api/login":
            if "ag_session=test-session" not in request.headers.get("cookie", ""):
                return httpx.Response(401, json={"detail": "No cookie"})
            if request.method in {"POST", "PUT"} and request.headers.get("x-csrf-token") != "csrf-test":
                return httpx.Response(403, json={"detail": "No CSRF"})
        if path == "/api/logout":
            return httpx.Response(self.logout_status, json={"ok": True})
        if path == "/api/worksheets":
            return httpx.Response(200, json={"worksheets": [{"id": "worksheet-1", "published": self.published}]})
        if path == "/api/worksheets/worksheet-1/pdf":
            return httpx.Response(200, content=self.pdf)
        if path == "/api/worksheets/worksheet-1/attempts":
            return httpx.Response(201, json=self.attempt)
        if path == "/api/attempts/attempt-1/answers":
            if self.save_status != 200:
                return httpx.Response(self.save_status, json={"detail": "Conflict"})
            assert payload["version"] == self.attempt["version"]
            self.attempt["answers"] = payload["answers"]
            self.attempt["version"] += 1
            return httpx.Response(200, json=self.attempt)
        if path == "/api/attempts/attempt-1/submit":
            assert payload == {"version": self.attempt["version"]}
            self.attempt["status"] = "review"
            self.attempt["version"] += 2
            if self.submit_timeout:
                raise httpx.ReadTimeout("Test timeout", request=request)
            return httpx.Response(200, json=self.attempt)
        if path == "/api/attempts/attempt-1":
            return httpx.Response(200, json=self.attempt)
        return httpx.Response(404, json={"detail": "Unknown path"})


class DemoReplayTests(unittest.TestCase):
    def setUp(self):
        self.hash_patch = patch.dict("tools.replay_demo_submission.HASHES", {"48544102.pdf": DIGEST})
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)
        self.raw = fixture_dict()
        self.fixture = Fixture.model_validate(self.raw)
        self.server = FakeServer(self.raw)
        self.client = httpx.Client(base_url="http://127.0.0.1:8001", transport=httpx.MockTransport(self.server.handle))
        self.addCleanup(self.client.close)
        self.output = []

    def run_replay(self, **kwargs):
        return replay(self.client, self.fixture, "demo.student", "test-password-not-logged", output=self.output.append, **kwargs)

    def assert_no_save(self):
        self.assertFalse(any(method == "PUT" for method, _, _ in self.server.calls))
        self.assertEqual(self.server.calls[-1][1], "/api/logout")

    def test_default_only_saves_real_api_draft_and_logs_out(self):
        result = self.run_replay()
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["answers"], self.fixture.answers)
        self.assertFalse(any(path.endswith("/submit") for _, path, _ in self.server.calls))
        self.assertEqual(self.server.calls[-1][1], "/api/logout")
        self.assertFalse(self.client.cookies)
        self.assertNotIn("x-csrf-token", self.client.headers)
        self.assertNotIn("test-password-not-logged", "\n".join(self.output))
        saved = next(payload for method, _, payload in self.server.calls if method == "PUT")
        self.assertEqual(set(saved), {"answers", "version"})
        self.assertNotIn("expected", json.dumps(saved))
        self.assertNotIn("awarded", json.dumps(saved))

    def test_submit_sends_current_version_and_uses_server_summary(self):
        result = self.run_replay(submit=True)
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["summary"]["pending"], 1)
        submit = next(payload for _, path, payload in self.server.calls if path.endswith("/submit"))
        self.assertEqual(submit, {"version": 2})

    def test_teacher_role_refused_and_session_revoked(self):
        self.server.role = "teacher"
        with self.assertRaisesRegex(ReplayError, "student account"):
            self.run_replay()
        self.assert_no_save()
        self.assertEqual(len(self.server.calls), 2)

    def test_original_pdf_hash_must_match(self):
        self.server.pdf = b"%PDF altered"
        with self.assertRaisesRegex(ReplayError, "No unique published"):
            self.run_replay()
        self.assert_no_save()

    def test_unpublished_sample_not_started(self):
        self.server.published = False
        with self.assertRaisesRegex(ReplayError, "No unique published"):
            self.run_replay()
        self.assert_no_save()
        self.assertFalse(any(path.endswith("/attempts") for _, path, _ in self.server.calls))

    def test_geometry_change_refused(self):
        self.server.attempt["questions"][0]["rect"]["x"] += .01
        with self.assertRaisesRegex(ReplayError, "region/type"):
            self.run_replay()
        self.assert_no_save()

    def test_question_identity_change_refused(self):
        self.server.attempt["questions"][0]["id"] = "another"
        with self.assertRaisesRegex(ReplayError, "questions differ"):
            self.run_replay()
        self.assert_no_save()

    def test_private_keys_in_server_question_data_refused(self):
        self.server.attempt["questions"][0]["expected"] = ["3"]
        with self.assertRaisesRegex(ReplayError, "invalid public"):
            self.run_replay()
        self.assert_no_save()

    def test_nonempty_draft_not_overwritten(self):
        self.server.attempt["answers"] = {"add-1": {"text": "8", "strokes": []}}
        with self.assertRaisesRegex(ReplayError, "already contains"):
            self.run_replay()
        self.assert_no_save()
        self.assertEqual(self.server.attempt["answers"]["add-1"]["text"], "8")

    def test_explicit_replace_draft(self):
        self.server.attempt["answers"] = {"add-1": {"text": "8", "strokes": []}}
        self.run_replay(replace_draft=True)
        self.assertEqual(self.server.attempt["answers"], self.fixture.answers)

    def test_submitted_attempt_never_reopened_by_helper(self):
        self.server.attempt["status"] = "graded"
        with self.assertRaisesRegex(ReplayError, "already submitted"):
            self.run_replay(replace_draft=True, submit=True)
        self.assert_no_save()
        self.assertFalse(any(path.endswith("/reopen") for _, path, _ in self.server.calls))

    def test_save_conflict_not_retried_or_submitted(self):
        self.server.save_status = 409
        with self.assertRaisesRegex(ReplayError, "HTTP 409"):
            self.run_replay(submit=True)
        self.assertEqual(sum(method == "PUT" for method, _, _ in self.server.calls), 1)
        self.assertFalse(any(path.endswith("/submit") for _, path, _ in self.server.calls))
        self.assertEqual(self.server.calls[-1][1], "/api/logout")

    def test_submit_timeout_refetches_but_does_not_resubmit(self):
        self.server.submit_timeout = True
        result = self.run_replay(submit=True)
        self.assertEqual(result["status"], "review")
        self.assertEqual(sum(path.endswith("/submit") for _, path, _ in self.server.calls), 1)
        self.assertIn("timed out", "\n".join(self.output))
        self.assertTrue(any(path == "/api/attempts/attempt-1" for _, path, _ in self.server.calls))

    def test_logout_failure_warns_without_leaking_session(self):
        self.server.logout_status = 503
        self.run_replay()
        self.assertIn("could not revoke", "\n".join(self.output))
        self.assertFalse(self.client.cookies)

    def test_fixture_rejects_keys_scores_unknown_ids_and_nonfinite_ink(self):
        for mutation in (
            lambda data: data["questions"][0].update(expected=["3"]),
            lambda data: data.update(earned=1),
            lambda data: data["answers"].update(unknown={"text": "1", "strokes": []}),
            lambda data: data["answers"]["add-1"]["strokes"][0]["points"][0].update(x=float("nan")),
            lambda data: data.update(source_sha256="0" * 64),
        ):
            data = copy.deepcopy(self.raw)
            mutation(data)
            with self.assertRaises(ValidationError):
                Fixture.model_validate(data)

    def test_duplicate_json_fields_rejected(self):
        with tempfile.TemporaryDirectory(prefix=".demo-test-", dir=ROOT) as directory:
            path = Path(directory) / "fixture.json"
            path.write_text('{"format":"one","format":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(ReplayError, "Duplicate JSON field"):
                load_fixture(path)

    def test_external_urls_credentials_paths_and_redirect_origins_rejected(self):
        for value in ("https://example.com", "http://192.168.1.20:8001", "http://localhost@evil.example", "http://user:pass@localhost", "http://127.0.0.1:8001/api", "http://localhost?url=example", "file:///tmp/demo", "http://localhost:99999"):
            with self.subTest(value=value), self.assertRaises(ReplayError):
                validate_base_url(value)
        for value in ("http://127.0.0.1:8001", "http://localhost:8001/", "https://[::1]:8001"):
            self.assertEqual(validate_base_url(value), value.rstrip("/"))


if __name__ == "__main__":
    unittest.main()
