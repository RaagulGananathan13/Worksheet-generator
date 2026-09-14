"""Printed-worksheet alignment and mark isolation on realistic synthetic phone photos."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import cv2
import numpy as np
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import documents, paper, samples


def render_sample(filename, directory):
    content, preset = samples.load_sample(filename)
    metadata = documents.import_pdf(content, directory)
    return paper.load_gray(Path(directory) / f"{metadata['sha256']}-0.png"), preset["questions"]


def write_answer(page, rect, text, thickness=3):
    """Dark pen-like script lettering inside one answer area."""
    height, width = page.shape
    left, top, box_width, box_height = rect["x"] * width, rect["y"] * height, rect["w"] * width, rect["h"] * height
    font = cv2.FONT_HERSHEY_SCRIPT_SIMPLEX
    (text_width, text_height), _ = cv2.getTextSize(text, font, 1.0, thickness)
    scale = min(box_width * 0.7 / text_width, box_height * 0.6 / text_height)
    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
    origin = (round(left + (box_width - text_width) / 2), round(top + (box_height + text_height) / 2))
    cv2.putText(page, text, origin, font, scale, 55, thickness, cv2.LINE_AA)


def circle_option(page, rect):
    height, width = page.shape
    center = (round((rect["x"] + rect["w"] / 2) * width), round((rect["y"] + rect["h"] / 2) * height))
    radius = round(max(rect["w"] * width, rect["h"] * height) * 0.62)
    cv2.circle(page, center, radius, 45, 4, cv2.LINE_AA)


def photograph(page, seed=0, quality=82):
    """Perspective, a darker table, uneven light, blur, sensor noise and JPEG compression."""
    rng = np.random.default_rng(seed)
    height, width = page.shape
    canvas_width, canvas_height = round(width * 1.25), round(height * 1.2)
    source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    target = np.float32([[80, 60], [canvas_width - 120, 110], [canvas_width - 60, canvas_height - 90], [130, canvas_height - 50]])
    photo = cv2.warpPerspective(page, cv2.getPerspectiveTransform(source, target), (canvas_width, canvas_height), borderValue=110)
    light = np.linspace(0.8, 1.0, canvas_width)[None, :] * np.linspace(0.92, 1.0, canvas_height)[:, None]
    photo = np.clip(photo.astype(np.float32) * light + rng.normal(0, 3, photo.shape), 0, 255).astype(np.uint8)
    photo = cv2.GaussianBlur(photo, (3, 3), 0)
    return cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


class PaperPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix=".paper-tests-", dir=ROOT)
        cls.directory = Path(cls.temporary.name)
        cls.reference, cls.questions = render_sample("35879581.pdf", cls.directory)
        cls.other_reference, _ = render_sample("48544102.pdf", cls.directory)
        cls.page = cls.reference.copy()
        for question in cls.questions[:10]:
            write_answer(cls.page, question["rect"], question["expected"][0])
        cls.photo = photograph(cls.page)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_phone_photo_aligns_and_only_new_writing_counts(self):
        photo = paper.load_pages([self.photo])[0]
        alignment = paper.align(self.reference, photo)
        self.assertGreater(alignment.inliers, 50)
        self.assertLess(alignment.error, 3)
        self.assertGreater(alignment.visible.mean(), 0.97)
        flattened = paper.flatten(self.reference)
        for index, question in enumerate(self.questions):
            evidence = paper.question_evidence(flattened, alignment, question)
            with self.subTest(question=question["id"]):
                self.assertEqual(evidence["status"], "ink" if index < 10 else "blank")
                if index < 10:
                    # The isolated image holds the writing, trimmed, not the printed worksheet.
                    ink = np.asarray(evidence["image"])
                    self.assertLess(ink.shape[1], question["rect"]["w"] * self.reference.shape[1] * 1.2)
                    self.assertGreater(int((ink < 150).sum()), 30)

    def test_isolated_writing_matches_the_pen_strokes_not_the_printing(self):
        alignment = paper.align(self.reference, paper.load_pages([self.photo])[0])
        question = self.questions[0]
        region = paper.extract_region(paper.flatten(self.reference), alignment, question["rect"])
        clean = np.full_like(self.reference, 255)
        write_answer(clean, question["rect"], question["expected"][0])
        left, top, right, bottom = paper._box(question["rect"], self.reference.shape, 0.06)
        written = clean[top:bottom, left:right] < 200
        found = np.asarray(region.ink) < 200
        self.assertEqual(found.shape, written.shape)
        overlap = (cv2.dilate(written.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & found
        self.assertGreater(overlap.sum() / max(1, found.sum()), 0.9, "Isolated marks must be the student's writing")
        self.assertGreater(found.sum() / max(1, written.sum()), 0.5, "Most of the writing must survive")

    def test_wrong_worksheet_is_rejected(self):
        with self.assertRaisesRegex(paper.PaperError, "could not be matched"):
            paper.align(self.other_reference, paper.load_pages([self.photo])[0])

    def test_page_count_and_out_of_order_pages(self):
        photo = paper.load_pages([self.photo])[0]
        with self.assertRaisesRegex(paper.PaperError, "has 1 page, but 2 pages were uploaded"):
            paper.match_pages([self.reference], [photo, photo])
        other_photo = paper.load_pages([photograph(self.other_reference, seed=3)])[0]
        matched = paper.match_pages([self.reference, self.other_reference], [other_photo, photo])
        self.assertEqual(len(matched), 2)
        self.assertTrue(all(alignment.error < 3 for alignment in matched))
        with self.assertRaisesRegex(paper.PaperError, "Page 2 of the worksheet could not be found"):
            paper.match_pages([self.reference, self.other_reference], [photo, photo])

    def test_scanned_pdf_upload_is_rendered_and_aligned(self):
        output = BytesIO()
        canvas = Canvas(output, pagesize=(612, 792))
        canvas.drawImage(ImageReader(BytesIO(cv2.imencode(".png", self.page)[1].tobytes())), 0, 0, width=612, height=792)
        canvas.showPage()
        canvas.save()
        pages = paper.load_pages([output.getvalue()])
        self.assertEqual(len(pages), 1)
        self.assertLess(paper.align(self.reference, pages[0]).error, 3)

    def test_exif_rotation_transparency_and_bad_files(self):
        stored = Image.fromarray(np.rot90(self.page))
        exif = Image.Exif()
        exif[0x0112] = 6
        output = BytesIO()
        stored.save(output, format="JPEG", exif=exif)
        upright = paper.load_pages([output.getvalue()])[0]
        self.assertGreater(upright.shape[0], upright.shape[1])
        self.assertLess(paper.align(self.reference, upright).error, 3)

        transparent = Image.new("RGBA", (600, 800), (0, 0, 0, 0))
        output = BytesIO()
        transparent.save(output, format="PNG")
        self.assertGreater(paper.load_pages([output.getvalue()])[0].mean(), 250)

        gif = BytesIO()
        Image.new("L", (400, 500), 255).save(gif, format="GIF")
        tiny = BytesIO()
        Image.new("L", (120, 150), 255).save(tiny, format="PNG")
        huge = BytesIO()
        Image.new("L", (8000, 7000), 255).save(huge, format="PNG")
        for content, message in ((b"not an image", "could not be read"), (gif.getvalue(), "PDF, JPG or PNG"),
                                 (tiny.getvalue(), "too small"), (huge.getvalue(), "too large"), (b"", "empty")):
            with self.subTest(message=message), self.assertRaisesRegex(paper.PaperError, message):
                paper.load_pages([content])
        with self.assertRaisesRegex(paper.PaperError, "at most 10 pages"):
            paper.load_pages([self.photo] * 11)

    def test_crop_and_evidence_storage_round_trip(self):
        image = Image.new("L", (400, 200), 255)
        image.paste(0, (190, 90, 210, 110))
        cropped = paper.crop_to_ink(image)
        self.assertLess(cropped.width, 60)
        self.assertEqual(paper.crop_to_ink(Image.new("L", (50, 50), 255)).size, (50, 50))
        alignment = paper.align(self.reference, paper.load_pages([self.photo])[0])
        folder = self.directory / "stored"
        folder.mkdir(exist_ok=True)
        quality = paper.save_alignment(alignment, folder, 0)
        restored = paper.load_alignment(folder, quality)
        self.assertTrue(np.array_equal(restored.image, alignment.image))
        self.assertTrue(np.array_equal(restored.visible, alignment.visible))
        with self.assertRaises(paper.PaperError):
            paper.load_alignment(folder, {**quality, "index": 5})


class ChoiceDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix=".paper-tests-", dir=ROOT)
        cls.reference, questions = render_sample("91903282.pdf", Path(cls.temporary.name))
        cls.choices = [question for question in questions if question["kind"] == "choice"]
        cls.flattened = paper.flatten(cls.reference)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def detect(self, marks):
        page = self.reference.copy()
        for question_index, value in marks:
            option = next(option for option in self.choices[question_index]["options"] if option["value"] == value)
            circle_option(page, option["rect"])
        alignment = paper.align(self.reference, paper.load_pages([photograph(page, seed=7)])[0])
        return [paper.detect_choice(self.flattened, alignment, question) for question in self.choices]

    def test_circled_blank_and_double_marked_options(self):
        results = self.detect([(0, "7"), (1, "4"), (1, "5")])
        self.assertEqual((results[0]["status"], results[0]["value"]), ("selected", "7"))
        self.assertEqual(results[1]["status"], "ambiguous")
        self.assertEqual(results[2]["status"], "blank")
        self.assertEqual(results[3]["status"], "blank")


if __name__ == "__main__":
    unittest.main()
