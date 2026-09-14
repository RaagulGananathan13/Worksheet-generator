"""Compatibility and geometry tests for the permissive PDF implementation."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import sys
import unittest

from PIL import Image
from pypdf import PdfReader, PdfWriter
import pypdfium2 as pdfium
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import documents_permissive as documents
from app import samples


def make_pdf(rotation=0, pages=1):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    for _ in range(pages):
        canvas.drawString(100, 650, "Original worksheet text")
        canvas.showPage()
    canvas.save()
    if not rotation:
        return output.getvalue()
    source = PdfReader(BytesIO(output.getvalue()))
    writer = PdfWriter()
    for page in source.pages:
        page.rotate(rotation)
        writer.add_page(page)
    rotated = BytesIO()
    writer.write(rotated)
    return rotated.getvalue()


class PermissiveDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix=".pdf-tests-", dir=ROOT)
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_all_six_sample_pdfs_render_with_source_bytes_preserved(self):
        for sample in samples.list_samples():
            with self.subTest(sample=sample["filename"]):
                source, _ = samples.load_sample(sample["filename"])
                result = documents.import_pdf(source, self.directory)
                self.assertEqual((self.directory / result["filename"]).read_bytes(), source)
                self.assertEqual(result["sha256"], hashlib.sha256(source).hexdigest())
                self.assertEqual(len(result["pages"]), 1)
                self.assertAlmostEqual(result["pages"][0]["width"], 612, places=2)
                with Image.open(self.directory / f"{result['sha256']}-0.png") as image:
                    self.assertLessEqual(max(image.size), 1800)
                    self.assertGreater(image.width, 1000)
                    self.assertLess(image.convert("L").getextrema()[0], 100)

    def test_rotated_background_and_vector_ink_alignment(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                source = make_pdf(rotation)
                result = documents.import_pdf(source, self.directory)
                width, height = (792, 612) if rotation in (90, 270) else (612, 792)
                self.assertEqual(result["pages"], [{"width": width, "height": height}])
                question = {"id": "q1", "label": "Q1", "page": 0, "kind": "manual", "points": 2, "rect": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.1}, "options": []}
                attempt = {"id": "a1", "title": "Rotation", "student_name": "Pupil", "pages": result["pages"], "questions": [question], "results": [], "summary": {}, "answers": {"q1": {"strokes": [{"width": 0.05, "points": [{"x": 0.2, "y": 0.5, "p": 0.5}, {"x": 0.8, "y": 0.5, "p": 0.5}]}]}}}
                report = documents.report_pdf(self.directory / result["filename"], attempt)
                document = pdfium.PdfDocument(report)
                try:
                    self.assertEqual(len(document), 2)
                    self.assertEqual(document.get_page_size(0), (width, height))
                    page = document.get_page(0)
                    try:
                        self.assertEqual(page.get_rotation(), 0)
                        bitmap = page.render(scale=1)
                        try:
                            image = bitmap.to_pil()
                            try:
                                red, green, blue = image.convert("RGB").getpixel((round(0.35 * width), round(0.25 * height)))
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
                    document.close()
                self.assertEqual((self.directory / result["filename"]).read_bytes(), source)

    def test_searchable_summary_choice_and_typed_answer(self):
        result = documents.import_pdf(make_pdf(), self.directory)
        questions = [
            {"id": "q1", "label": "Number", "page": 0, "kind": "number", "points": 2, "rect": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.1}, "options": []},
            {"id": "q2", "label": "Choice", "page": 0, "kind": "choice", "points": 1, "rect": {"x": 0.2, "y": 0.5, "w": 0.3, "h": 0.1}, "options": [{"value": "yes", "label": "Yes", "rect": {"x": 0.2, "y": 0.5, "w": 0.1, "h": 0.1}}]},
        ]
        attempt = {
            "id": "a1", "title": "Marked", "student_name": "Pupil", "pages": result["pages"], "questions": questions,
            "answers": {"q1": {"text": "9"}, "q2": {"text": "yes"}},
            "results": [{"question_id": "q1", "label": "Number", "awarded": 2, "max_points": 2, "status": "correct", "recognized_text": "9", "feedback": "Correct."}, {"question_id": "q2", "label": "Choice", "awarded": 1, "max_points": 1, "status": "correct", "recognized_text": "yes", "feedback": "Correct."}],
            "summary": {"earned": 3, "total": 3, "pending": 0, "percentage": 100, "final": True},
        }
        report = documents.report_pdf(self.directory / result["filename"], attempt)
        reader = PdfReader(BytesIO(report))
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("Final marks: 3 / 3", reader.pages[-1].extract_text())
        self.assertIn("Answer recorded: yes", reader.pages[-1].extract_text())
        self.assertIn("9", reader.pages[0].extract_text())

    def test_limits_corruption_encryption_and_missing_cache(self):
        for content in (b"invalid", b"%PDF-broken", make_pdf(pages=11)):
            with self.assertRaises(ValueError):
                documents.import_pdf(content, self.directory)
        writer = PdfWriter()
        writer.add_page(PdfReader(BytesIO(make_pdf())).pages[0])
        writer.encrypt("password")
        encrypted = BytesIO()
        writer.write(encrypted)
        with self.assertRaises(ValueError):
            documents.import_pdf(encrypted.getvalue(), self.directory)
        # A valid original can rebuild a missing page cache without mutation.
        original = make_pdf()
        path = self.directory / "original.pdf"
        path.write_bytes(original)
        report = documents.report_pdf(path, {"title": "Repair", "questions": [], "answers": {}, "results": [], "summary": {}})
        self.assertTrue(report.startswith(b"%PDF-"))
        self.assertEqual(path.read_bytes(), original)

    def test_parallel_requests_are_serialized_around_native_pdfium(self):
        inputs = [make_pdf(rotation) for rotation in (0, 90, 180, 270)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda data: documents.import_pdf(data, self.directory), inputs))
        self.assertEqual(len(results), 4)
        self.assertTrue(all((self.directory / result["filename"]).is_file() for result in results))


if __name__ == "__main__":
    unittest.main()
