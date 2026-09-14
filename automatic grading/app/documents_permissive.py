"""PDFium rendering and ReportLab reports, with no PyMuPDF runtime dependency.

Original PDFs remain byte-identical. Reports intentionally use the displayed PNG
worksheet pages as a raster background (144 DPI, capped at 1800 pixels) and add
vector handwriting, marks, and a searchable score summary. This also means no
original PDF JavaScript, attachments, or interactive form actions enter reports.
"""

from functools import wraps
from io import BytesIO
from pathlib import Path
from threading import RLock
import hashlib
import math
import os
import tempfile
import textwrap

import pypdfium2 as pdfium
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas


MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
MAX_PAGE_POINTS = 2000
LOGO = Path(__file__).resolve().parents[1] / "static" / "brand" / "gb-logo.jpg"
_pdf_lock = RLock()


def _serialized(function):
    # PDFium forbids concurrent calls, even for different documents. Keep object
    # construction, rendering, bitmap conversion, and disposal within one mutex.
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _pdf_lock:
            return function(*args, **kwargs)
    return wrapped


def _atomic_bytes(target: Path, content: bytes):
    descriptor, temporary = tempfile.mkstemp(prefix=".writing-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _describe(document):
    if not 1 <= len(document) <= MAX_PAGES:
        raise ValueError("Use an unlocked PDF with 1 to 10 pages.")
    pages = []
    for index in range(len(document)):
        width, height = document.get_page_size(index)
        if not all(math.isfinite(value) and 36 <= value <= MAX_PAGE_POINTS for value in (width, height)):
            raise ValueError("PDF page dimensions are outside the supported range.")
        pages.append({"width": width, "height": height})
    return pages


@_serialized
def import_pdf(content: bytes, directory: Path) -> dict:
    if not content or len(content) > MAX_BYTES or not content.lstrip().startswith(b"%PDF-"):
        raise ValueError("Upload a valid PDF no larger than 20 MB.")
    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as error:
        raise ValueError("The PDF is damaged, password-protected, or cannot be opened.") from error
    try:
        pages = _describe(document)
        digest = hashlib.sha256(content).hexdigest()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{digest}.pdf"
        target = directory / filename
        if not target.exists():
            _atomic_bytes(target, content)
        for index, dimensions in enumerate(pages):
            image_path = directory / f"{digest}-{index}.png"
            if image_path.exists():
                continue
            page = document.get_page(index)
            try:
                scale = min(2.0, 1800 / max(dimensions["width"], dimensions["height"]))
                bitmap = page.render(
                    scale=scale, draw_annots=False, may_draw_forms=False,
                    limit_image_cache=True, fill_color=(255, 255, 255, 255),
                )
                try:
                    image = bitmap.to_pil()
                    try:
                        output = BytesIO()
                        image.save(output, format="PNG")
                        _atomic_bytes(image_path, output.getvalue())
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return {"sha256": digest, "pages": pages, "filename": filename}
    except pdfium.PdfiumError as error:
        raise ValueError("The PDF could not be rendered safely.") from error
    finally:
        document.close()


@_serialized
def render_upload_pages(content: bytes, long_side: int, max_pages: int) -> list:
    """Render a completed worksheet PDF (scan or annotated copy) to grayscale images.

    Annotations are drawn: a pupil may have written on the PDF with a stylus.
    Uploaded submissions are evidence copies, never worksheet backgrounds.
    """
    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as error:
        raise ValueError("The PDF is damaged, password-protected, or cannot be opened.") from error
    try:
        if not 1 <= len(document) <= max_pages:
            raise ValueError("Upload a PDF with at most 10 pages.")
        images = []
        for index in range(len(document)):
            width, height = document.get_page_size(index)
            if not all(math.isfinite(value) and 36 <= value <= 14400 for value in (width, height)):
                raise ValueError("PDF page dimensions are outside the supported range.")
            page = document.get_page(index)
            try:
                bitmap = page.render(
                    scale=long_side / max(width, height), grayscale=True, draw_annots=True,
                    may_draw_forms=True, limit_image_cache=True, fill_color=(255, 255, 255, 255),
                )
                try:
                    image = bitmap.to_pil()
                    try:
                        images.append(image.convert("L"))
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        return images
    except pdfium.PdfiumError as error:
        raise ValueError("The PDF could not be rendered safely.") from error
    finally:
        document.close()


def _display(value):
    # Keep the existing report's explicit font fallback. The raster worksheet
    # preserves its embedded fonts/scripts; only unsupported report text uses ?.
    return str(value).encode("latin-1", errors="replace").decode("latin-1")


def _region(question, page_width, page_height):
    rectangle = question["rect"]
    return (
        rectangle["x"] * page_width,
        rectangle["y"] * page_height,
        rectangle["w"] * page_width,
        rectangle["h"] * page_height,
    )


def _typed_answer(canvas, text, x, top, width, height, page_height):
    text = _display(text)
    size = min(18, max(7, height / 2.5))
    lines = []
    while size >= 6:
        lines = simpleSplit(text, "Helvetica", size, max(1, width - 4))
        if (len(lines) * size * 1.2 <= max(1, height - 2)
                and all(stringWidth(line, "Helvetica", size) <= max(1, width - 4) for line in lines)):
            break
        size -= 1
    if size < 6:
        size, lines = 6, ["[See answer in summary]"]
    canvas.setFont("Helvetica", size)
    line_height = size * 1.2
    start = top + max(size, (height - len(lines) * line_height) / 2 + size)
    for index, line in enumerate(lines):
        # PDF text uses a bottom-left origin; stored ink uses top-left origin.
        left = x + max(0, (width - stringWidth(line, "Helvetica", size)) / 2)
        canvas.drawString(left, page_height - start - index * line_height, line)


def _draw_answer(canvas, question, answer, result, page_width, page_height):
    x, top, width, height = _region(question, page_width, page_height)
    canvas.saveState()
    try:
        canvas.setFillColorRGB(0.12, 0.2, 0.42)
        canvas.setStrokeColorRGB(0.12, 0.2, 0.42)
        canvas.setLineCap(1)
        canvas.setLineJoin(1)
        for stroke in answer.get("strokes", []):
            previous = None
            previous_pressure = None
            for point in stroke.get("points", []):
                position = (x + point["x"] * width, page_height - top - point["y"] * height)
                pressure = point.get("p", 0.5)
                average_pressure = pressure if previous_pressure is None else (previous_pressure + pressure) / 2
                # Match the browser/OCR pressure curve; exporting a response must
                # not inflate the stroke compared with what the student wrote.
                pen = max(0.5, stroke.get("width", 0.009) * width * (0.4 + 0.6 * average_pressure))
                canvas.setLineWidth(pen)
                if previous is None:
                    canvas.circle(position[0], position[1], pen / 2, stroke=0, fill=1)
                else:
                    canvas.line(previous[0], previous[1], position[0], position[1])
                previous = position
                previous_pressure = pressure
        if answer.get("text"):
            chosen = next((option for option in question.get("options", []) if option["value"] == answer["text"] and option.get("rect")), None)
            if chosen:
                ox, otop, ow, oh = _region(chosen, page_width, page_height)
                canvas.setLineWidth(2)
                canvas.ellipse(ox, page_height - otop - oh, ox + ow, page_height - otop, stroke=1, fill=0)
            else:
                _typed_answer(canvas, answer["text"], x, top, width, height, page_height)
        if result:
            color = (0.10, 0.48, 0.31) if result["status"] == "correct" else (0.75, 0.23, 0.21)
            if result["status"] in {"pending_review", "partial"}:
                color = (0.75, 0.47, 0.06)
            canvas.setStrokeColorRGB(*color)
            canvas.setFillColorRGB(*color)
            canvas.setLineWidth(0.8)
            canvas.rect(x, page_height - top - height, width, height, stroke=1, fill=0)
            mark = "Review" if result.get("awarded") is None else f"{result['awarded']:g}/{result['max_points']:g}"
            canvas.setFont("Helvetica", 7)
            canvas.drawString(x, page_height - max(9, top - 2), mark)
    finally:
        canvas.restoreState()


def _draw_summary(canvas, attempt):
    page_height, y = 792, 48
    canvas.setPageSize((612, page_height))

    def line(text, size=11):
        nonlocal y
        for part in textwrap.wrap(_display(text), width=85 if size <= 11 else 52) or [""]:
            if y > 744:
                canvas.showPage()
                canvas.setPageSize((612, page_height))
                y = 48
            canvas.setFillColorRGB(0.16, 0.20, 0.28)
            canvas.setFont("Helvetica", size)
            canvas.drawString(42, page_height - y, part)
            y += size + 6

    if LOGO.is_file():
        # The same GeniusBees wordmark used by the worksheet generator (1000 x 312 px).
        logo_width = 150
        logo_height = logo_width * 312 / 1000
        canvas.drawImage(str(LOGO), 42, page_height - y - logo_height + 12, width=logo_width, height=logo_height)
        y += logo_height + 2
    line("Worksheet results", 20)
    line(attempt.get("title", "Worksheet"), 14)
    line(f"Student: {attempt.get('student_name', '')}")
    line(f"Attempt number: {attempt.get('attempt_number', 1)}")
    line(f"Attempt ID: {attempt.get('id', '')}")
    if attempt.get("submission_mode") == "paper":
        line("Submitted as a printed worksheet (uploaded photo or scan). Page backgrounds show the student's paper.")
    summary = attempt.get("summary") or {}
    if summary:
        label = "Final marks" if summary.get("final") else "Confirmed marks (provisional)"
        line(f"{label}: {summary.get('earned', 0):g} / {summary.get('total', 0):g}", 14)
        line(f"Awaiting review: {summary.get('pending', 0)} question(s)")
        if summary.get("percentage") is not None:
            line(f"Percentage: {summary['percentage']:g}%")
    y += 12
    result_ids = set()
    for result in attempt.get("results", []):
        result_ids.add(result["question_id"])
        mark = "Pending teacher review" if result.get("awarded") is None else f"{result['awarded']:g} / {result['max_points']:g}"
        line(f"{result['label']}: {mark}", 12)
        if result.get("recognized_text"):
            line(f"Answer recorded: {result['recognized_text']}")
        line(result.get("feedback", ""))
        y += 7
    # A draft report can still retain long typed answers that do not fit a box.
    for question in attempt.get("questions", []):
        text = attempt.get("answers", {}).get(question["id"], {}).get("text", "")
        if question["id"] not in result_ids and text:
            line(f"{question['label']}: {text}")
    canvas.showPage()


@_serialized
def report_pdf(pdf_path: Path, attempt: dict, backgrounds: list | None = None) -> bytes:
    """Annotated results. `backgrounds` replaces worksheet renders, e.g. a student's aligned paper pages."""
    pdf_path = Path(pdf_path)
    # Reuse existing renderings; repair a missing rendering from immutable bytes.
    pages = attempt.get("pages")
    if not pages or any(not pdf_path.with_name(f"{pdf_path.stem}-{index}.png").is_file() for index in range(len(pages))):
        metadata = import_pdf(pdf_path.read_bytes(), pdf_path.parent)
        pages = metadata["pages"]
        pdf_path = pdf_path.parent / metadata["filename"]
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792), pageCompression=1)
    canvas.setTitle(_display(attempt.get("title", "Worksheet results")))
    canvas.setAuthor("GeniusBees")
    results = {result["question_id"]: result for result in attempt.get("results", [])}
    for index, page in enumerate(pages):
        width, height = page["width"], page["height"]
        canvas.setPageSize((width, height))
        background = pdf_path.with_name(f"{pdf_path.stem}-{index}.png")
        if backgrounds and index < len(backgrounds) and Path(backgrounds[index]).is_file():
            background = Path(backgrounds[index])
        canvas.drawImage(str(background), 0, 0, width=width, height=height)
        for question in attempt.get("questions", []):
            if question["page"] == index:
                _draw_answer(canvas, question, attempt.get("answers", {}).get(question["id"], {}), results.get(question["id"]), width, height)
        canvas.showPage()
    _draw_summary(canvas, attempt)
    canvas.save()
    return output.getvalue()
