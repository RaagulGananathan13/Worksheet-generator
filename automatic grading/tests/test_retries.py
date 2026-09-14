"""Student retakes preserve history, enforce isolation, and migrate legacy data."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import Database, SCHEMA
from app.server import encode, now_iso
import test_api as api_helpers


class RetryAPITests(unittest.IsolatedAsyncioTestCase):
    # Reuse request-boundary fixtures without inheriting/rerunning unrelated tests.
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

    async def marked(self, worksheet=None):
        attempt = await self.attempt(worksheet or await self.worksheet())
        return await self.submit(await self.save(attempt, {"q1": {"text": "9"}}))

    async def retry(self, previous, client=None):
        response = await (client or self.student).post(
            f"/api/attempts/{previous['id']}/retry", json={"version": previous["version"]},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def test_retry_preserves_all_prior_rows_and_starts_blank(self):
        first = await self.marked()
        self.assertEqual(first["attempt_number"], 1)
        self.assertIsNone(first["previous_attempt_id"])
        before = self.app.state.database.one("SELECT * FROM attempts WHERE id=?", (first["id"],))
        second = await self.retry(first)
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(second["attempt_number"], 2)
        self.assertEqual(second["previous_attempt_id"], first["id"])
        self.assertEqual(second["latest_attempt_id"], second["id"])
        self.assertTrue(second["worksheet_published"])
        self.assertEqual(second["status"], "draft")
        self.assertEqual(second["answers"], {})
        self.assertEqual(second["results"], [])
        self.assertIsNone(second["submitted_at"])
        self.assertEqual(second["version"], 1)
        self.assertEqual(before, self.app.state.database.one("SELECT * FROM attempts WHERE id=?", (first["id"],)))
        previous = (await self.student.get(f"/api/attempts/{first['id']}")).json()
        self.assertEqual(previous["summary"]["earned"], 2)
        self.assertEqual(previous["latest_attempt_id"], second["id"])
        self.assertEqual((await self.student.get(f"/api/attempts/{first['id']}/report.pdf")).status_code, 200)
        final = await self.submit(await self.save(second, {"q1": {"text": "1"}}))
        self.assertEqual(final["summary"]["earned"], 0)
        third = await self.retry(final)
        self.assertEqual(third["attempt_number"], 3)
        self.assertEqual(third["previous_attempt_id"], second["id"])

    async def test_review_retry_keeps_pending_marks_and_teacher_can_finish_old_review(self):
        worksheet = await self.worksheet(questions=[self.question(kind="manual", expected=[])])
        first = await self.marked(worksheet)
        self.assertEqual(first["status"], "review")
        second = await self.retry(first)
        reviewed = await self.teacher.post(f"/api/attempts/{first['id']}/review", json={
            "version": first["version"], "reviews": [{"question_id": "q1", "awarded": 2, "feedback": "Reviewed original work"}],
        })
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["summary"]["earned"], 2)
        self.assertEqual((await self.student.get(f"/api/attempts/{second['id']}")).json()["answers"], {})
        self.assertEqual(len(self.app.state.database.all("SELECT * FROM review_audit WHERE attempt_id=?", (first["id"],))), 1)
        latest = (await self.student.get("/api/worksheets")).json()["worksheets"][0]["attempt"]
        self.assertEqual(latest["id"], second["id"], "Reviewing history must not move the library back to an older attempt.")

    async def test_retry_uses_current_published_rubric_not_previous_key(self):
        worksheet = await self.worksheet()
        first = await self.marked(worksheet)
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": "Updated addition", "questions": [self.question(expected=["10"], points=7)],
            "published": True, "keys_confirmed": True, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        second = await self.retry(first)
        self.assertEqual(second["worksheet_revision"], response.json()["revision"])
        self.assertEqual(second["title"], "Updated addition")
        for question in second["questions"]:
            self.assertFalse({"expected", "tolerance", "case_sensitive"} & set(question))
        marked = await self.submit(await self.save(second, {"q1": {"text": "10"}}))
        self.assertEqual(marked["summary"]["earned"], 7)
        unchanged = (await self.teacher.get(f"/api/attempts/{first['id']}")).json()
        self.assertEqual(unchanged["questions"][0]["expected"], ["9"])
        self.assertEqual(unchanged["summary"]["earned"], 2)

    async def test_double_click_concurrency_reuses_draft_without_overwrite(self):
        first = await self.marked()
        responses = await asyncio.gather(*(
            self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
            for _ in range(4)
        ))
        self.assertEqual({response.status_code for response in responses}, {201})
        self.assertEqual(len({response.json()["id"] for response in responses}), 1)
        second = await self.save(responses[0].json(), {"q1": {"text": "8"}})
        repeated = await self.retry(first)
        self.assertEqual(repeated["id"], second["id"])
        self.assertEqual(repeated["version"], second["version"])
        self.assertEqual(repeated["answers"]["q1"]["text"], "8")
        reopened = await self.attempt({"id": first["worksheet_id"]})
        self.assertEqual(reopened["id"], second["id"])
        self.assertEqual(len(self.app.state.database.all("SELECT id FROM attempts")), 2)

    async def test_retry_requires_own_student_role_csrf_and_valid_version(self):
        first = await self.marked()
        other = await self.register("other-student")
        stranger = await self.client()
        for client, expected in ((other, 404), (self.teacher, 403), (stranger, 401)):
            response = await client.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
            self.assertEqual(response.status_code, expected, response.text)
        response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]}, headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(response.status_code, 403)
        response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]}, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        for body, expected in (({"version": 1}, 409), ({"version": True}, 422), ({"version": first["version"], "student_id": "other"}, 422)):
            response = await self.student.post(f"/api/attempts/{first['id']}/retry", json=body)
            self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(len(self.app.state.database.all("SELECT id FROM attempts")), 1)

    async def test_unpublished_worksheet_disallows_retry_but_history_remains_visible(self):
        worksheet = await self.worksheet()
        first = await self.marked(worksheet)
        response = await self.teacher.put(f"/api/worksheets/{worksheet['id']}", json={
            "title": worksheet["title"], "questions": worksheet["questions"], "published": False,
            "keys_confirmed": False, "revision": worksheet["revision"],
        })
        self.assertEqual(response.status_code, 200)
        response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
        self.assertEqual(response.status_code, 403)
        history = (await self.student.get(f"/api/attempts/{first['id']}")).json()
        self.assertFalse(history["worksheet_published"])
        self.assertEqual(history["summary"], first["summary"])
        self.assertEqual((await self.student.get(f"/api/worksheets/{worksheet['id']}/pdf")).status_code, 200)
        self.assertEqual((await self.student.get("/api/worksheets")).json()["worksheets"], [])

    async def test_draft_and_grading_retry_rejected_and_old_closed_attempt_cannot_branch(self):
        first = await self.attempt(await self.worksheet())
        for status in ("draft", "grading"):
            with self.app.state.database.transaction() as connection:
                connection.execute("UPDATE attempts SET status=? WHERE id=?", (status, first["id"]))
            response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
            self.assertEqual(response.status_code, 409)
        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='draft' WHERE id=?", (first["id"],))
        first = await self.submit(first)
        second = await self.retry(first)
        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='grading' WHERE id=?", (second["id"],))
        response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
        self.assertEqual(response.status_code, 409)
        with self.app.state.database.transaction() as connection:
            connection.execute("UPDATE attempts SET status='draft' WHERE id=?", (second["id"],))
        second = await self.submit(second)
        response = await self.student.post(f"/api/attempts/{first['id']}/retry", json={"version": first["version"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.app.state.database.all("SELECT id FROM attempts")), 2)

    async def test_teacher_may_only_reopen_latest_attempt_and_csv_identifies_history(self):
        first = await self.marked()
        second = await self.submit(await self.retry(first))
        response = await self.teacher.post(f"/api/attempts/{first['id']}/reopen", json={"version": first["version"]})
        self.assertEqual(response.status_code, 409)
        response = await self.teacher.post(f"/api/attempts/{second['id']}/reopen", json={"version": second["version"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["attempt_number"], 2)
        rows = list(csv.DictReader(StringIO((await self.teacher.get("/api/results.csv")).text.lstrip("\ufeff"))))
        self.assertEqual({row["Attempt number"] for row in rows}, {"1", "2"})
        self.assertEqual({row["Attempt ID"] for row in rows}, {first["id"], second["id"]})
        for client in (self.student, self.teacher):
            history = (await client.get("/api/attempts")).json()["attempts"]
            self.assertEqual({row["attempt_number"] for row in history}, {1, 2})
        other = await self.register("private-history")
        self.assertEqual((await other.get("/api/attempts")).json()["attempts"], [])
        self.assertEqual((await other.get(f"/api/attempts/{second['id']}")).status_code, 404)


LEGACY_SCHEMA = SCHEMA.replace(
    "    attempt_number INTEGER NOT NULL DEFAULT 1 CHECK(attempt_number >= 1),\n"
    "    previous_attempt_id TEXT REFERENCES attempts(id),\n"
    "    UNIQUE(student_id, worksheet_id, attempt_number),\n"
    "    UNIQUE(previous_attempt_id)",
    "    UNIQUE(student_id, worksheet_id)",
)


class RetryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix=".retry-migration-", dir=ROOT)
        self.database = Database(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def legacy(self, orphan_audit=False):
        with closing(sqlite3.connect(self.database.path)) as connection, connection:
            connection.executescript(LEGACY_SCHEMA)
            timestamp = now_iso()
            connection.executemany(
                "INSERT INTO users(id,name,username,password_hash,role,teacher_id,class_code,created_at) VALUES (?,?,?,?,?,?,?,?)",
                [("teacher", "Teacher", "teacher", "test-hash", "teacher", None, "CLASS", timestamp),
                 ("student", "Student", "student", "test-hash", "student", "teacher", None, timestamp)],
            )
            connection.execute(
                "INSERT INTO worksheets(id,owner_id,title,sha256,pages,questions,published,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                ("worksheet", "teacher", "Original title", "a" * 64, "[]", "[]", 1, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO attempts(id,worksheet_id,student_id,teacher_id,title,sha256,pages,questions,worksheet_revision,status,version,answers,results,summary,created_at,updated_at,submitted_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("attempt-one", "worksheet", "student", "teacher", "Original title", "a" * 64, "[]", "[]", 1,
                 "graded", 7, '{"q1":{"text":"9"}}', '[{"awarded":2}]', '{"earned":2,"total":2}', timestamp, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO review_audit(id,attempt_id,teacher_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
                ("audit-one", "missing" if orphan_audit else "attempt-one", "teacher", "review", '{"previous_results":[]}', timestamp),
            )
        return self.database.one("SELECT * FROM attempts WHERE id='attempt-one'")

    def backups(self):
        return list((self.database.directory / "backups").glob("before-attempt-history-*.sqlite3"))

    def test_migration_preserves_attempt_ids_answers_marks_sessions_and_audit_with_valid_backup(self):
        original = self.legacy()
        audit = self.database.one("SELECT * FROM review_audit")
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES ('session','student','csrf',9999999999)")
        self.database.initialize()
        migrated = self.database.one("SELECT * FROM attempts WHERE id='attempt-one'")
        self.assertEqual({key: migrated[key] for key in original}, original)
        self.assertEqual(migrated["attempt_number"], 1)
        self.assertIsNone(migrated["previous_attempt_id"])
        self.assertEqual(audit, self.database.one("SELECT * FROM review_audit"))
        self.assertEqual(self.database.one("SELECT user_id FROM sessions WHERE token_hash='session'")["user_id"], "student")
        self.assertEqual(len(self.backups()), 1)
        with closing(sqlite3.connect(self.backups()[0])) as backup:
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertNotIn("attempt_number", [row[1] for row in backup.execute("PRAGMA table_info(attempts)")])
            self.assertEqual(backup.execute("SELECT answers FROM attempts").fetchone()[0], original["answers"])
            self.assertEqual(backup.execute("SELECT attempt_id FROM review_audit").fetchone()[0], "attempt-one")
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.database.initialize()
        self.assertEqual(len(self.backups()), 1, "A completed upgrade must not rebuild or repeatedly back up the database.")

    def test_new_database_needs_no_migration_backup(self):
        self.database.initialize()
        self.assertEqual(self.backups(), [])
        columns = self.database.all("PRAGMA table_info(attempts)")
        self.assertIn("attempt_number", [row["name"] for row in columns])

    def test_importing_server_has_no_database_or_classroom_side_effects(self):
        nonexistent = self.database.directory / "not-created-on-import"
        environment = {**os.environ, "AG_DATA_DIR": str(nonexistent)}
        result = subprocess.run(
            [sys.executable, "-c", "import app.server; assert not hasattr(app.server, 'app')"],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(nonexistent.exists())

    def test_migrated_constraints_allow_history_but_only_one_active_attempt(self):
        self.legacy()
        self.database.initialize()
        original = self.database.one("SELECT * FROM attempts WHERE id='attempt-one'")

        def insert(**changes):
            row = {**original, **changes}
            columns = ",".join(row)
            with self.database.transaction() as connection:
                connection.execute(f"INSERT INTO attempts({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))

        insert(id="attempt-two", attempt_number=2, previous_attempt_id="attempt-one", status="draft")
        self.assertEqual(self.database.one("SELECT previous_attempt_id FROM attempts WHERE id='attempt-two'")["previous_attempt_id"], "attempt-one")
        for changes in (
            {"id": "duplicate-number", "attempt_number": 2, "status": "review"},
            {"id": "competing-draft", "attempt_number": 3, "previous_attempt_id": "attempt-two", "status": "draft"},
            {"id": "competing-grading", "attempt_number": 3, "previous_attempt_id": "attempt-two", "status": "grading"},
            {"id": "missing-link", "attempt_number": 3, "previous_attempt_id": "missing", "status": "review"},
            {"id": "branched-link", "attempt_number": 3, "previous_attempt_id": "attempt-one", "status": "review"},
        ):
            with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                insert(**changes)
        self.assertEqual(self.database.all("PRAGMA foreign_key_check"), [])

    def test_failed_relationship_check_rolls_back_schema_and_all_original_data(self):
        original = self.legacy(orphan_audit=True)
        with self.assertRaisesRegex(RuntimeError, "rolled back"):
            self.database.initialize()
        self.assertEqual(self.database.one("SELECT * FROM attempts WHERE id='attempt-one'"), original)
        self.assertNotIn("attempt_number", [row["name"] for row in self.database.all("PRAGMA table_info(attempts)")])
        self.assertEqual(self.database.one("SELECT attempt_id FROM review_audit")["attempt_id"], "missing")
        self.assertEqual(len(self.backups()), 1)
        self.assertIsNone(self.database.one("SELECT name FROM sqlite_master WHERE name='attempts_retry_migration'"))

    def test_backup_failure_aborts_before_any_attempt_change(self):
        original = self.legacy()
        with patch.object(self.database, "_backup_before_attempt_migration", side_effect=OSError("Disk full")):
            with self.assertRaisesRegex(OSError, "Disk full"):
                self.database.initialize()
        self.assertEqual(self.database.one("SELECT * FROM attempts WHERE id='attempt-one'"), original)
        self.assertEqual(self.backups(), [])

    def test_two_initializers_migrate_once_under_sqlite_lock(self):
        original = self.legacy()
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: Database(self.database.directory).initialize(), range(2)))
        self.assertEqual(len(self.backups()), 1)
        migrated = self.database.one("SELECT * FROM attempts WHERE id='attempt-one'")
        self.assertEqual({key: migrated[key] for key in original}, original)
        self.assertEqual(self.database.all("PRAGMA foreign_key_check"), [])


if __name__ == "__main__":
    unittest.main()
