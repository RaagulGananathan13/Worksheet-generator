"""Printed-worksheet uploads through the real API, background marking and upgrades."""

from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import samples
from app.database import Database, PAPER_COLUMNS, SCHEMA
from app.server import create_app
import test_api as api_helpers
from test_paper import photograph, render_sample, write_answer


def reading(text, reliable=True, certain=True, reason=""):
    return {"text": text, "confidence": 0.99, "reliable": reliable, "certain": certain,
            "exact_agreement": True, "reason": reason, "source": "test-reader"}


class PaperAPITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api_helpers.APITests.asyncSetUp
    asyncTearDown = api_helpers.APITests.asyncTearDown
    client = api_helpers.APITests.client
    register = api_helpers.APITests.register
    question = api_helpers.APITests.question
    pdf = api_helpers.APITests.pdf
    worksheet = api_helpers.APITests.worksheet
    attempt = api_helpers.APITests.attempt
    save = api_helpers.APITests.save
    submit = api_helpers.APITests.submit

    async def published_sample(self, filename="35879581.pdf"):
        response = await self.teacher.post("/api/samples/import", json={"filename": filename})
        self.assertEqual(response.status_code, 201, response.text)
        worksheet = response.json()
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": worksheet["title"], "questions": worksheet["questions"], "published": True,
            "keys_confirmed": True, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def photo(self, filename, answers, seed=0):
        with TemporaryDirectory(prefix=".paper-api-render-", dir=ROOT) as folder:
            page, questions = render_sample(filename, folder)
        for question in questions:
            if question["id"] in answers:
                write_answer(page, question["rect"], answers[question["id"]])
        return photograph(page, seed=seed)

    def reader(self, readings):
        calls = []

        def recognize(**arguments):
            calls.append(arguments)
            return readings[len(calls) - 1]

        self.app.state.image_recognizer = recognize
        return calls

    async def upload(self, attempt, contents, client=None, expected=200):
        files = [("files", (f"page-{index}.jpg", content, "image/jpeg")) for index, content in enumerate(contents)]
        response = await (client or self.student).post(f"/api/attempts/{attempt['id']}/paper", data={"version": str(attempt["version"])}, files=files)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    async def test_student_paper_is_marked_from_isolated_writing_without_keys(self):
        worksheet = await self.published_sample()
        attempt = await self.attempt(worksheet)
        calls = self.reader([reading("80"), reading("3"), reading("55", reliable=False, certain=False, reason="Unclear.")])
        marked = await self.upload(attempt, [self.photo("35879581.pdf", {"subtract-1": "80", "subtract-2": "3", "subtract-3": "55"})])
        self.assertEqual(marked["submission_mode"], "paper")
        self.assertEqual(marked["status"], "review")
        self.assertEqual(len(marked["paper"]["pages"]), 1)
        results = {result["question_id"]: result for result in marked["results"]}
        self.assertEqual((results["subtract-1"]["status"], results["subtract-1"]["awarded"]), ("correct", 1))
        self.assertEqual((results["subtract-2"]["status"], results["subtract-2"]["awarded"]), ("incorrect", 0))
        self.assertEqual((results["subtract-3"]["status"], results["subtract-3"]["awarded"]), ("pending_review", None))
        for number in range(4, 21):
            self.assertEqual((results[f"subtract-{number}"]["status"], results[f"subtract-{number}"]["source"]), ("incorrect", "blank"))
        self.assertEqual(marked["summary"], {**marked["summary"], "earned": 1, "pending": 1, "final": False})
        self.assertEqual(len(calls), 3)
        for arguments in calls:
            # The isolated marks, plus the untouched photo of the same area for a second opinion.
            self.assertEqual(set(arguments), {"image", "kind", "confirm_image"})
            self.assertEqual(arguments["kind"], "number")
            self.assertEqual(arguments["image"].size, arguments["confirm_image"].size)
        self.assertNotIn("expected", marked["questions"][0])

        page = await self.student.get(f"/api/attempts/{attempt['id']}/paper/pages/0.png")
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.content.startswith(b"\x89PNG"))
        answer = await self.teacher.get(f"/api/attempts/{attempt['id']}/paper/answers/subtract-1.png")
        self.assertEqual(answer.status_code, 200)
        other = await self.register("paper-other")
        for path in ("/paper/pages/0.png", "/paper/answers/subtract-1.png", "/report.pdf"):
            self.assertEqual((await other.get(f"/api/attempts/{attempt['id']}{path}")).status_code, 404)
        self.assertEqual((await self.student.get(f"/api/attempts/{attempt['id']}/paper/pages/1.png")).status_code, 404)
        report = await self.student.get(f"/api/attempts/{attempt['id']}/report.pdf")
        self.assertEqual(report.status_code, 200)
        pages = PdfReader(BytesIO(report.content)).pages
        # Page 1 is the student's aligned paper; the results summary may span several pages.
        summary = "\n".join(page.extract_text() for page in pages[1:])
        self.assertIn("Submitted as a printed worksheet", summary)
        self.assertIn("Confirmed marks (provisional): 1 / 20", summary)
        self.assertIn("Paper upload", (await self.teacher.get("/api/results.csv")).text)
        stored = self.app.state.database.one("SELECT paper FROM attempts WHERE id=?", (attempt["id"],))
        record = json.loads(stored["paper"])
        folder = Path(self.temporary.name) / "submissions" / attempt["id"] / record["upload_id"]
        self.assertTrue((folder / "upload-1.jpg").is_file())
        self.assertTrue((folder / "page-0.png").is_file())

        review = await self.teacher.post(f"/api/attempts/{attempt['id']}/review", json={
            "version": marked["version"], "reviews": [{"question_id": "subtract-3", "awarded": 1, "feedback": "Checked the paper."}],
        })
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["summary"]["percentage"], 10)

    async def test_wrong_page_or_worksheet_leaves_the_draft_unchanged(self):
        worksheet = await self.published_sample()
        attempt = await self.attempt(worksheet)
        saved = await self.save(attempt, {"subtract-1": {"text": "80"}})
        self.reader([])
        wrong = self.photo("48544102.pdf", {})
        response = await self.upload(saved, [wrong], expected=422)
        self.assertIn("could not be matched", response["detail"])
        right = self.photo("35879581.pdf", {})
        response = await self.upload(saved, [right, right], expected=422)
        self.assertIn("2 pages were uploaded", response["detail"])
        current = (await self.student.get(f"/api/attempts/{attempt['id']}")).json()
        self.assertEqual((current["status"], current["version"], current["submission_mode"]), ("draft", saved["version"], "online"))
        self.assertEqual(current["answers"], saved["answers"])
        response = await self.student.post(f"/api/attempts/{attempt['id']}/paper", data={"version": str(saved["version"])},
                                           files=[("files", ("notes.txt", b"hello", "text/plain"))])
        self.assertEqual(response.status_code, 422)

    async def test_upload_permissions_versions_and_submitted_attempts(self):
        worksheet = await self.published_sample()
        attempt = await self.attempt(worksheet)
        photo = self.photo("35879581.pdf", {})
        self.reader([])
        response = await self.student.post(f"/api/attempts/{attempt['id']}/paper", data={"version": "99"},
                                           files=[("files", ("page.jpg", photo, "image/jpeg"))])
        self.assertEqual(response.status_code, 409)
        response = await self.teacher.post(f"/api/attempts/{attempt['id']}/paper", data={"version": str(attempt["version"])},
                                           files=[("files", ("page.jpg", photo, "image/jpeg"))])
        self.assertEqual(response.status_code, 403)
        response = await self.student.post(f"/api/worksheets/{worksheet['id']}/paper", data={"student_id": "x"},
                                           files=[("files", ("page.jpg", photo, "image/jpeg"))])
        self.assertEqual(response.status_code, 403)
        response = await self.student.post(f"/api/attempts/{attempt['id']}/paper", data={"version": str(attempt["version"])},
                                           files=[("files", ("page.jpg", photo, "image/jpeg"))], headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        marked = await self.upload(attempt, [photo])
        self.assertEqual(marked["status"], "graded")
        self.assertEqual(marked["summary"]["earned"], 0)
        response = await self.student.post(f"/api/attempts/{attempt['id']}/paper", data={"version": str(marked["version"])},
                                           files=[("files", ("page.jpg", photo, "image/jpeg"))])
        self.assertEqual(response.status_code, 409)
        retry = await self.student.post(f"/api/attempts/{attempt['id']}/retry", json={"version": marked["version"]})
        self.assertEqual(retry.status_code, 201, retry.text)
        self.assertEqual(retry.json()["submission_mode"], "online")
        self.assertIsNone(retry.json()["paper"])

    async def test_teacher_uploads_paper_for_a_student(self):
        worksheet = await self.published_sample()
        students = (await self.teacher.get("/api/students")).json()["students"]
        self.assertEqual([student["username"] for student in students], ["student-one"])
        student_id = students[0]["id"]
        photo = self.photo("35879581.pdf", {"subtract-1": "80"})
        self.reader([reading("80")] * 3)

        async def teacher_upload(expected, **fields):
            data = {"student_id": student_id, **{key: str(value).lower() for key, value in fields.items()}}
            response = await self.teacher.post(f"/api/worksheets/{worksheet['id']}/paper", data=data,
                                               files=[("files", ("scan.jpg", photo, "image/jpeg"))])
            self.assertEqual(response.status_code, expected, response.text)
            return response.json()

        first = await teacher_upload(201)
        self.assertEqual((first["attempt_number"], first["submission_mode"], first["status"]), (1, "paper", "graded"))
        self.assertEqual(first["summary"]["earned"], 1)
        self.assertEqual(first["paper"]["uploaded_by_role"], "teacher")
        second = await teacher_upload(201)
        self.assertEqual((second["attempt_number"], second["previous_attempt_id"]), (2, first["id"]))

        draft = await self.retry_draft(second)
        await self.save(draft, {"subtract-1": {"text": "80"}})
        conflict = await teacher_upload(409)
        self.assertIn("unfinished online attempt", conflict["detail"])
        replaced = await teacher_upload(201, replace_draft=True)
        self.assertEqual(replaced["id"], draft["id"])
        self.assertEqual(replaced["submission_mode"], "paper")

        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='grading' WHERE id=?", (replaced["id"],))
        self.assertIn("still being marked", (await teacher_upload(409))["detail"])
        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='graded' WHERE id=?", (replaced["id"],))

        response = await self.teacher.post(f"/api/worksheets/{worksheet['id']}/paper", data={"student_id": self.teacher_user["id"]},
                                           files=[("files", ("scan.jpg", photo, "image/jpeg"))])
        self.assertEqual(response.status_code, 404)
        unpublished = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": worksheet["title"], "questions": worksheet["questions"], "published": False,
            "keys_confirmed": False, "revision": worksheet["revision"],
        })
        self.assertEqual(unpublished.status_code, 200)
        self.assertIn("Publish this worksheet", (await teacher_upload(409))["detail"])

    async def retry_draft(self, attempt):
        response = await self.student.post(f"/api/attempts/{attempt['id']}/retry", json={"version": attempt["version"]})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def test_background_queue_marks_after_submit(self):
        self.app.state.inline_grading = False
        attempt = await self.attempt(await self.worksheet())
        submitted = await self.submit(await self.save(attempt, {"q1": {"text": "9"}}))
        self.assertEqual(submitted["status"], "grading")
        self.assertTrue(self.app.state.grading_queue.wait(30))
        marked = (await self.student.get(f"/api/attempts/{attempt['id']}")).json()
        self.assertEqual((marked["status"], marked["summary"]["earned"]), ("graded", 2))

    async def test_restart_resumes_marking_but_repeated_failures_go_to_review(self):
        worksheet = await self.worksheet(questions=[self.question()])
        resumed = await self.save(await self.attempt(worksheet), {"q1": {"text": "9"}})
        stuck = await self.attempt(worksheet, await self.register("stuck-student"))
        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='grading',grading_tries=1 WHERE id=?", (resumed["id"],))
            connection.execute("UPDATE attempts SET status='grading',grading_tries=3 WHERE id=?", (stuck["id"],))
        restarted = create_app(self.temporary.name, testing=True)
        async with restarted.router.lifespan_context(restarted):
            self.assertTrue(restarted.state.grading_queue.wait(30))
            first = restarted.state.database.one("SELECT * FROM attempts WHERE id=?", (resumed["id"],))
            second = restarted.state.database.one("SELECT * FROM attempts WHERE id=?", (stuck["id"],))
        self.assertEqual((first["status"], json.loads(first["summary"])["earned"]), ("graded", 2))
        self.assertEqual(second["status"], "review")
        self.assertIsNone(json.loads(second["results"])[0]["awarded"])


class PaperMigrationTests(unittest.TestCase):
    def test_existing_database_gains_paper_columns_without_changing_rows(self):
        schema = SCHEMA
        for name, definition in PAPER_COLUMNS:
            schema = schema.replace(f"    {name} {definition},\n", "")
        self.assertNotIn("submission_mode", schema)
        with TemporaryDirectory(prefix=".paper-migration-", dir=ROOT) as folder:
            database = Database(Path(folder))
            with closing(sqlite3.connect(database.path)) as connection, connection:
                connection.executescript(schema)
                connection.execute("INSERT INTO users(id,name,username,password_hash,role,class_code,created_at) VALUES ('t','T','t','h','teacher','C','now')")
                connection.execute("INSERT INTO users(id,name,username,password_hash,role,teacher_id,created_at) VALUES ('s','S','s','h','student','t','now')")
                connection.execute("INSERT INTO worksheets(id,owner_id,title,sha256,pages,questions,created_at,updated_at) VALUES ('w','t','W','x','[]','[]','now','now')")
                connection.execute("INSERT INTO attempts(id,worksheet_id,student_id,teacher_id,title,sha256,pages,questions,worksheet_revision,status,answers,created_at,updated_at) "
                                   "VALUES ('a','w','s','t','W','x','[]','[]',1,'graded','{\"q\":{\"text\":\"1\"}}','now','now')")
            before = database.one("SELECT * FROM attempts WHERE id='a'")
            database.initialize()
            after = database.one("SELECT * FROM attempts WHERE id='a'")
            self.assertEqual({key: after[key] for key in before}, before)
            self.assertEqual((after["submission_mode"], after["paper"], after["grading_tries"]), ("online", "{}", 0))
            database.initialize()
            self.assertEqual(list((Path(folder) / "backups").glob("*")) if (Path(folder) / "backups").exists() else [], [])


if __name__ == "__main__":
    unittest.main()
