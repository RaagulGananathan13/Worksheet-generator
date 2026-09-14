"""Reports distinguish repeated submissions without changing worksheet pages."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import MagicMock

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import documents
from app.documents_permissive import _draw_answer


class RetryReportTests(unittest.TestCase):
    def test_report_uses_browser_pressure_curve_and_keeps_decimal_dot(self):
        canvas = MagicMock()
        question = {"rect": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1}}
        answer = {"strokes": [
            {"width": 0.05, "points": [{"x": 0.1, "y": 0.2, "p": 0.2}, {"x": 0.5, "y": 0.8, "p": 0.8}]},
            {"width": 0.05, "points": [{"x": 0.8, "y": 0.8, "p": 0.5}]},
        ]}
        _draw_answer(canvas, question, answer, None, 612, 792)
        widths = [call.args[0] for call in canvas.setLineWidth.call_args_list]
        self.assertAlmostEqual(widths[0], 0.05 * (0.3 * 612) * 0.52)
        self.assertAlmostEqual(widths[1], 0.05 * (0.3 * 612) * 0.7)
        self.assertAlmostEqual(widths[2], widths[1])
        self.assertEqual(canvas.circle.call_count, 2)
        self.assertEqual(canvas.line.call_count, 1)

    def test_report_identifies_attempt_number_and_immutable_id(self):
        source = BytesIO()
        canvas = Canvas(source, pagesize=(612, 792))
        canvas.drawString(42, 720, "Original worksheet")
        canvas.showPage()
        canvas.save()
        with TemporaryDirectory(prefix=".retry-report-tests-", dir=ROOT) as directory:
            folder = Path(directory)
            metadata = documents.import_pdf(source.getvalue(), folder)
            for number in (1, 2, 12):
                with self.subTest(attempt=number):
                    attempt = {
                        "id": f"attempt-{number}", "attempt_number": number,
                        "title": "Practice", "student_name": "Demo Student",
                        "pages": metadata["pages"], "questions": [],
                        "answers": {}, "results": [], "summary": {},
                    }
                    report = documents.report_pdf(folder / metadata["filename"], attempt)
                    reader = PdfReader(BytesIO(report))
                    summary = reader.pages[-1].extract_text()
                    self.assertIn(f"Attempt number: {number}", summary)
                    self.assertIn(f"Attempt ID: attempt-{number}", summary)
                    self.assertEqual(len(reader.pages), 2)
            self.assertEqual((folder / metadata["filename"]).read_bytes(), source.getvalue())


if __name__ == "__main__":
    unittest.main()
