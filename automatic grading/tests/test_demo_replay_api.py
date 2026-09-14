"""Exercise demo replay against the real app in an isolated, in-process server.

The recognizer is deliberately unavailable: this tests saved ink, authorization,
grading fallback and report export, not handwriting-recognition accuracy.
"""

from io import BytesIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.server import create_app
from tools.replay_demo_submission import ReplayError, load_fixture, replay


class DemoReplayAPITests(unittest.TestCase):
    def test_real_api_save_refusal_replace_submit_and_report(self):
        fixture_dir = ROOT.parent / "sample-worksheets" / "student-written-demos"
        correct = load_fixture(fixture_dir / "48544102-correct.synthetic.json")
        mixed = load_fixture(fixture_dir / "48544102-mixed.synthetic.json")
        recognizer_calls = []

        def unavailable_recognizer(**kwargs):
            recognizer_calls.append(kwargs)
            self.assertEqual(set(kwargs), {"strokes", "kind", "aspect_ratio"})
            return {"text": "", "confidence": 0, "reliable": False,
                    "reason": "Unavailable recognizer injected by integration test.", "source": "test-unavailable"}

        with TemporaryDirectory(prefix=".demo-api-tests-", dir=ROOT) as directory:
            with patch.dict("os.environ", {"AG_SECURE_COOKIES": "0"}):
                app = create_app(directory, testing=True)
            app.state.recognizer = unavailable_recognizer
            with TestClient(app, base_url="http://127.0.0.1:8001") as client:
                response = client.post("/api/bootstrap", json={
                    "token": app.state.bootstrap_token, "name": "Demo test teacher",
                    "username": "demo.teacher", "password": "Teacher-test-password-123",
                })
                self.assertEqual(response.status_code, 201, response.text)
                class_code = response.json()["user"]["class_code"]
                client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                response = client.post("/api/samples/import", json={"filename": "48544102.pdf"})
                self.assertEqual(response.status_code, 201, response.text)
                worksheet = response.json()
                response = client.put(f"/api/worksheets/{worksheet['id']}", json={
                    "title": worksheet["title"], "questions": worksheet["questions"],
                    "published": True, "keys_confirmed": True, "revision": worksheet["revision"],
                })
                self.assertEqual(response.status_code, 200, response.text)
                response = client.post("/api/register", json={
                    "name": "Synthetic demo student", "username": "demo.student",
                    "password": "Student-test-password-123", "class_code": class_code,
                })
                self.assertEqual(response.status_code, 201, response.text)

                output = []
                saved = replay(client, correct, "demo.student", "Student-test-password-123", output=output.append)
                self.assertEqual(saved["status"], "draft")
                self.assertEqual(len(saved["answers"]), 16)
                self.assertEqual(saved["answers"], correct.answers)
                self.assertEqual(recognizer_calls, [])
                self.assertIsNone(client.get("/api/session").json()["user"])

                with self.assertRaisesRegex(ReplayError, "already contains"):
                    replay(client, mixed, "demo.student", "Student-test-password-123", output=output.append)
                self.assertIsNone(client.get("/api/session").json()["user"])
                response = client.post("/api/login", json={"username": "demo.student", "password": "Student-test-password-123"})
                self.assertEqual(response.status_code, 200, response.text)
                state = client.get(f"/api/attempts/{saved['id']}").json()
                self.assertEqual(state["answers"], correct.answers)
                self.assertEqual(state["version"], saved["version"])
                self.assertNotIn("expected", state["questions"][0])

                marked = replay(client, mixed, "demo.student", "Student-test-password-123",
                                replace_draft=True, submit=True, output=output.append)
                self.assertEqual(marked["id"], saved["id"])
                self.assertEqual(marked["answers"], mixed.answers)
                self.assertEqual(marked["status"], "review")
                self.assertEqual(marked["summary"]["total"], 16)
                self.assertEqual(marked["summary"]["earned"], 0)
                self.assertEqual(marked["summary"]["pending"], 15)
                self.assertFalse(marked["summary"]["final"])
                self.assertIsNone(marked["summary"]["percentage"])
                self.assertEqual(len(recognizer_calls), 15)
                incorrect = [result for result in marked["results"] if result["status"] == "incorrect"]
                self.assertEqual(len(incorrect), 1)
                self.assertEqual(incorrect[0]["question_id"], "add-2")
                self.assertEqual(incorrect[0]["awarded"], 0)
                self.assertIsNone(client.get("/api/session").json()["user"])

                response = client.post("/api/login", json={"username": "demo.teacher", "password": "Teacher-test-password-123"})
                self.assertEqual(response.status_code, 200, response.text)
                client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                state_response = client.get(f"/api/attempts/{saved['id']}")
                self.assertEqual(state_response.status_code, 200, state_response.text)
                self.assertEqual(state_response.json()["summary"], marked["summary"])
                self.assertEqual(state_response.json()["answers"], mixed.answers)
                self.assertEqual(state_response.json()["status"], "review")
                self.assertIn("expected", state_response.json()["questions"][0])
                report = client.get(f"/api/attempts/{saved['id']}/report.pdf")
                self.assertEqual(report.status_code, 200, report.text[:200] if not report.content.startswith(b"%PDF") else "")
                self.assertIn("application/pdf", report.headers["content-type"])
                reader = PdfReader(BytesIO(report.content))
                self.assertGreaterEqual(len(reader.pages), 2)
                self.assertIn("Synthetic demo student", "\n".join(page.extract_text() for page in reader.pages))
                self.assertEqual(client.post("/api/logout", json={}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
