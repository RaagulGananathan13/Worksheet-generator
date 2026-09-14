"""Printed worksheets: align a photo or scan to the original page, then isolate
only the marks the student added.

The original rendered page is the reference. Everything printed on it - text,
boxes, guide lines, pictures and pale tracing digits - is removed by comparing
the aligned photo with that reference, so recognition never mistakes printing
for student writing. Every step reports its quality; weak alignment, hidden
regions and faint marks are uncertain evidence, never answers or zero marks.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
MAX_SOURCE_PIXELS = 50_000_000
WORK_LONG_SIDE = 2200
IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
MIN_CONTENT_TILES = 0.60
MIN_CONTENT_MEDIAN = 0.70
NOT_FOUND = ("This page could not be matched to the worksheet. Photograph the whole printed page, "
             "flat and in good light, or upload the correct worksheet.")


class PaperError(ValueError):
    """A problem the student or teacher can fix by retaking or re-scanning."""


def load_pages(uploads: list[bytes]) -> list[np.ndarray]:
    """Decode uploaded PDF/JPEG/PNG bytes into bounded grayscale pages, in order."""
    from . import documents

    pages = []
    for content in uploads:
        if not content:
            raise PaperError("One of the uploaded files is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise PaperError("Each uploaded file must be 20 MB or smaller.")
        if content.lstrip()[:5] == b"%PDF-":
            try:
                rendered = documents.render_upload_pages(content, WORK_LONG_SIDE, MAX_PAGES - len(pages))
            except ValueError as error:
                raise PaperError(str(error)) from None
            pages.extend(_bounded(np.asarray(image)) for image in rendered)
        else:
            pages.append(_decode_image(content))
        if len(pages) > MAX_PAGES:
            raise PaperError("Upload at most 10 pages.")
    if not pages:
        raise PaperError("Upload a PDF, JPG or PNG of the completed worksheet.")
    return pages


def _decode_image(content: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in IMAGE_FORMATS:
                raise PaperError("Use a PDF, JPG or PNG file.")
            if image.width * image.height > MAX_SOURCE_PIXELS:
                raise PaperError("This image is too large. Use a photo of at most 50 megapixels.")
            image.draft("L", (WORK_LONG_SIDE, WORK_LONG_SIDE))
            upright = ImageOps.exif_transpose(image)
            if upright.mode in {"RGBA", "LA", "PA"} or "transparency" in upright.info:
                white = Image.new("RGBA", upright.size, (255, 255, 255, 255))
                upright = Image.alpha_composite(white, upright.convert("RGBA"))
            gray = np.asarray(upright.convert("L"))
    except PaperError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise PaperError("The image could not be read. Upload a JPG or PNG photo, or a PDF scan.") from None
    return _bounded(gray)


def _bounded(gray: np.ndarray) -> np.ndarray:
    if gray.ndim != 2 or min(gray.shape) < 200:
        raise PaperError("The uploaded page is too small to read. Use a clearer photo or scan.")
    scale = WORK_LONG_SIDE / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(gray, dtype=np.uint8)


def flatten(gray: np.ndarray) -> np.ndarray:
    """Remove uneven lighting and paper tint so that white paper is close to 255."""
    size = max(15, round(max(gray.shape) / 60)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (0, 0), size / 2)
    return cv2.divide(gray, np.maximum(background, 1), scale=255)


@dataclass
class Alignment:
    image: np.ndarray       # flattened photo, warped into the reference pixel frame
    visible: np.ndarray     # reference pixels that the photo actually covers
    inliers: int
    inlier_ratio: float
    error: float            # median feature reprojection error, reference pixels
    refined: bool
    content: float = 1.0    # share of printed tiles whose printing is present in the photo

    def quality(self) -> dict:
        return {"inliers": self.inliers, "inlier_ratio": round(self.inlier_ratio, 3),
                "error_px": round(self.error, 2), "refined": self.refined,
                "visible": round(float(self.visible.mean()), 3), "content": round(self.content, 3)}


def _features(gray: np.ndarray, long_side: int = 1600):
    scale = min(1.0, long_side / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    small = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(small)
    keypoints, descriptors = cv2.SIFT_create(nfeatures=8000).detectAndCompute(small, None)
    points = np.float32([keypoint.pt for keypoint in keypoints]).reshape(-1, 2) / scale
    return points, descriptors


def _convex_positive(quad: np.ndarray) -> bool:
    signs = []
    for index in range(4):
        a, b, c = quad[index], quad[(index + 1) % 4], quad[(index + 2) % 4]
        signs.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    return all(value > 0 for value in signs) or all(value < 0 for value in signs)


def align(reference: np.ndarray, photo: np.ndarray) -> Alignment:
    """Find the printed page inside the photo using the reference page's own features."""
    reference_points, reference_descriptors = _features(reference)
    photo_points, photo_descriptors = _features(photo)
    if (reference_descriptors is None or photo_descriptors is None
            or len(reference_descriptors) < 50 or len(photo_descriptors) < 50):
        raise PaperError(NOT_FOUND)
    matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})
    pairs = matcher.knnMatch(photo_descriptors, reference_descriptors, k=2)
    good = [first for first, second in (pair for pair in pairs if len(pair) == 2)
            if first.distance < 0.75 * second.distance]
    if len(good) < 40:
        raise PaperError(NOT_FOUND)
    source = photo_points[[match.queryIdx for match in good]]
    target = reference_points[[match.trainIdx for match in good]]
    height, width = reference.shape
    diagonal = math.hypot(width, height)
    homography, mask = cv2.findHomography(source, target, cv2.USAC_MAGSAC, max(3.0, diagonal * 0.003),
                                          maxIters=10000, confidence=0.9995)
    if homography is None or mask is None:
        raise PaperError(NOT_FOUND)
    inlying = mask.ravel().astype(bool)
    inliers, ratio = int(inlying.sum()), float(inlying.mean())
    if inliers < 30 or ratio < 0.15:
        raise PaperError(NOT_FOUND)
    # The page must appear once, unmirrored and plausibly large in the photo.
    page_corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]]).reshape(-1, 1, 2)
    in_photo = cv2.perspectiveTransform(page_corners, np.linalg.inv(homography)).reshape(-1, 2)
    photo_area = photo.shape[0] * photo.shape[1]
    if (not _convex_positive(in_photo) or np.linalg.det(homography[:2, :2]) <= 0
            or cv2.contourArea(in_photo) < 0.12 * photo_area):
        raise PaperError(NOT_FOUND)
    projected = cv2.perspectiveTransform(source[inlying].reshape(-1, 1, 2), homography).reshape(-1, 2)
    error = float(np.median(np.linalg.norm(projected - target[inlying], axis=1)))
    warped = cv2.warpPerspective(flatten(photo), homography, (width, height), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    covered = cv2.warpPerspective(np.full(photo.shape, 255, np.uint8), homography, (width, height),
                                  flags=cv2.INTER_NEAREST, borderValue=0)
    visible = cv2.erode(covered, np.ones((9, 9), np.uint8)) > 0
    flat_reference = flatten(reference)
    warped, refined = _refine(flat_reference, warped, visible)
    # Every GeniusBees worksheet shares its header, logo and footer, so features
    # alone can align the wrong worksheet. The page's own printing must be there.
    passing, median = content_presence(flat_reference, warped, visible)
    if passing < MIN_CONTENT_TILES or median < MIN_CONTENT_MEDIAN:
        raise PaperError(NOT_FOUND)
    return Alignment(warped, visible, inliers, ratio, error, refined, passing)


def content_presence(reference: np.ndarray, aligned: np.ndarray, visible: np.ndarray, rows: int = 8, columns: int = 6):
    """How much of the original page's printing appears in the aligned photo, tile by tile.

    Returns (fraction of printed tiles with at least half their printing present,
    median presence). Student writing adds marks but never removes printing.
    """
    printed = reference < 160
    present = cv2.dilate((aligned < 215).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    height, width = reference.shape
    scores = []
    for row in range(rows):
        for column in range(columns):
            window = (slice(row * height // rows, (row + 1) * height // rows),
                      slice(column * width // columns, (column + 1) * width // columns))
            mask = printed[window] & visible[window]
            count = int(mask.sum())
            if count >= 150:
                scores.append(float((mask & present[window]).sum() / count))
    if len(scores) < 3:
        return 1.0, 1.0
    return sum(score >= 0.5 for score in scores) / len(scores), float(np.median(scores))


def _refine(reference: np.ndarray, warped: np.ndarray, visible: np.ndarray):
    """Sub-pixel whole-page correction; rejected unless it is a small adjustment."""
    height, width = reference.shape
    scale = 0.5
    size = (round(width * scale), round(height * scale))
    template = cv2.GaussianBlur(cv2.resize(reference, size, interpolation=cv2.INTER_AREA), (5, 5), 0)
    moved = cv2.GaussianBlur(cv2.resize(warped, size, interpolation=cv2.INTER_AREA), (5, 5), 0)
    mask = cv2.resize(visible.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST)
    matrix = np.eye(3, dtype=np.float32)
    try:
        _, matrix = cv2.findTransformECC(template, moved, matrix, cv2.MOTION_HOMOGRAPHY,
                                         (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6), mask, 5)
    except cv2.error:
        return warped, False
    shrink = np.diag([scale, scale, 1]).astype(np.float64)
    full = np.linalg.inv(shrink) @ matrix.astype(np.float64) @ shrink
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]]).reshape(-1, 1, 2)
    shift = np.linalg.norm(cv2.perspectiveTransform(corners, full) - corners, axis=2).max()
    if not np.isfinite(shift) or shift > 0.015 * math.hypot(width, height):
        return warped, False
    refined = cv2.warpPerspective(warped, full, (width, height), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return refined, True


@dataclass
class Region:
    ink: Image.Image        # the student's marks only, dark on white
    raw: Image.Image        # the aligned photo crop, printing included
    ink_pixels: int
    darkened_pixels: int    # pixels clearly darker than the original, even over printing
    area: int
    visible: float
    status: str             # "ink", "faint", "blank" or "hidden"


def _box(rect: dict, shape: tuple, margin: float) -> tuple[int, int, int, int]:
    height, width = shape
    left = (rect["x"] - rect["w"] * margin) * width
    top = (rect["y"] - rect["h"] * margin) * height
    right = (rect["x"] + rect["w"] * (1 + margin)) * width
    bottom = (rect["y"] + rect["h"] * (1 + margin)) * height
    return (max(0, math.floor(left)), max(0, math.floor(top)),
            min(width, math.ceil(right)), min(height, math.ceil(bottom)))


def _local_shift(reference: np.ndarray, photo: np.ndarray, limit: float):
    """Correct paper curl and lens distortion near one answer area."""
    if reference.std() < 12:
        return photo
    matrix = np.eye(2, 3, dtype=np.float32)
    try:
        _, matrix = cv2.findTransformECC(cv2.GaussianBlur(reference, (5, 5), 0), cv2.GaussianBlur(photo, (5, 5), 0),
                                         matrix, cv2.MOTION_TRANSLATION,
                                         (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 1)
    except cv2.error:
        return photo
    if not np.all(np.isfinite(matrix)) or math.hypot(matrix[0, 2], matrix[1, 2]) > limit:
        return photo
    return cv2.warpAffine(photo, matrix, (photo.shape[1], photo.shape[0]),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


def extract_region(reference: np.ndarray, alignment: Alignment, rect: dict, margin: float = 0.06) -> Region:
    """Isolate new marks inside one answer area of an aligned page.

    `reference` is the flattened original page in the same pixel frame.
    """
    height, width = reference.shape
    left, top, right, bottom = _box(rect, reference.shape, margin)
    area = max(1, round(rect["w"] * width * rect["h"] * height))
    visible = float(alignment.visible[top:bottom, left:right].mean()) if right > left and bottom > top else 0.0
    # Work in a surrounding patch so the local correction has printed context.
    pad_x, pad_y = round((right - left) * 0.6) + 12, round((bottom - top) * 0.6) + 12
    outer = (max(0, left - pad_x), max(0, top - pad_y), min(width, right + pad_x), min(height, bottom + pad_y))
    reference_patch = reference[outer[1]:outer[3], outer[0]:outer[2]]
    photo_patch = alignment.image[outer[1]:outer[3], outer[0]:outer[2]]
    photo_patch = _local_shift(reference_patch, photo_patch, limit=max(6.0, 0.01 * math.hypot(width, height)))
    inner = (slice(top - outer[1], bottom - outer[1]), slice(left - outer[0], right - outer[0]))
    reference_crop, photo_crop = reference_patch[inner], photo_patch[inner]
    raw = Image.fromarray(np.ascontiguousarray(photo_crop))
    if visible < 0.97:
        blank = Image.new("L", raw.size, 255)
        return Region(blank, raw, 0, 0, area, visible, "hidden")

    radius = max(2, round(max(height, width) * 0.0025))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    printed_pixels = (reference_crop < 225).astype(np.uint8)
    printed = cv2.dilate(printed_pixels, disk) > 0
    wide = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6 * radius + 1, 6 * radius + 1))
    near_printing = cv2.dilate(printed_pixels, wide) > 0
    candidate = (photo_crop < 228) & ~printed
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), connectivity=8)
    strong = set(np.unique(labels[(photo_crop < 170) & candidate]).tolist())
    keep_labels, faint_labels = [], set()
    for label in range(1, count):
        size = stats[label, cv2.CC_STAT_AREA]
        component_width, component_height = stats[label, cv2.CC_STAT_WIDTH], stats[label, cv2.CC_STAT_HEIGHT]
        component = labels == label
        # Residue of slightly misaligned printed lines or dots lies almost
        # entirely beside printing and is dropped.
        beside_printing = near_printing[component].mean()
        if beside_printing > 0.85 and size < 12 * radius * radius + 60:
            continue
        if beside_printing > 0.6 and component_height <= 2 * radius + 3 and component_width >= 6 * component_height:
            continue  # a sliver of a printed underline or border
        # Light pencil segments have no very dark pixels but are still strokes;
        # isolated JPEG speckles are tiny.
        if (label in strong and size >= 6) or (size >= 20 and photo_crop[component].mean() < 205):
            keep_labels.append(label)
        elif size >= 4:
            faint_labels.add(label)
    keep = np.isin(labels, keep_labels)
    # Faint pencil that continues a kept stroke (such as the light leg of an R)
    # belongs to the writing; losing it could turn one letter into another.
    for _ in range(3):
        grown = cv2.dilate(keep.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        touching = faint_labels.intersection(np.unique(labels[grown]).tolist())
        if not touching:
            break
        faint_labels -= touching
        keep_labels.extend(touching)
        keep = np.isin(labels, keep_labels)
    # Reconnect student strokes that cross printed lines, but only where the
    # photo is clearly darker than the original and touches kept ink.
    darker = photo_crop.astype(np.int16) < reference_crop.astype(np.int16) - 70
    near = cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=radius + 1) > 0
    keep |= printed & darker & near
    # Writing over pale dotted guides (tracing letters or digits) is kept when the
    # photo is much darker than the pale guide. Strong printing, such as coloured
    # boxes that a black-and-white printer darkens, is excluded by the pale band.
    traced = (reference_crop > 185) & (reference_crop < 235) & darker & (photo_crop < 170)
    keep |= cv2.morphologyEx(traced.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    ink = np.where(keep, photo_crop, 255).astype(np.uint8)
    ink_pixels, darkened = int(keep.sum()), int(darker.sum())
    evidence = max(ink_pixels, darkened)
    if evidence < max(8, area * 0.0005):
        status = "blank"
    elif evidence < max(25, area * 0.002):
        status = "faint"
    else:
        status = "ink"
    return Region(Image.fromarray(ink), raw, ink_pixels, darkened, area, visible, status)


def detect_choice(reference: np.ndarray, alignment: Alignment, question: dict) -> dict:
    """Decide which printed option was circled, ticked or crossed; never guess."""
    options = [option for option in question.get("options", []) if option.get("rect")]
    if len(options) < 2:
        return {"status": "unsupported", "value": None, "scores": {}}
    scores = {}
    for option in options:
        region = extract_region(reference, alignment, option["rect"], margin=0.35)
        if region.status == "hidden":
            return {"status": "hidden", "value": None, "scores": {}}
        scores[option["value"]] = max(region.ink_pixels, region.darkened_pixels) / region.area
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_value, top = ranked[0]
    second = ranked[1][1]
    rounded = {key: round(value, 4) for key, value in scores.items()}
    if top < 0.02:
        return {"status": "blank", "value": None, "scores": rounded}
    if top >= 0.05 and top >= 2.5 * max(second, 0.004):
        return {"status": "selected", "value": top_value, "scores": rounded}
    return {"status": "ambiguous", "value": None, "scores": rounded}


def ink_box(image: Image.Image, margin: float = 0.12):
    """Bounding box of the marks with a margin, or None when there are no marks."""
    array = np.asarray(image)
    rows, columns = np.nonzero(array < 230)
    if columns.size == 0:
        return None
    left, right, top, bottom = columns.min(), columns.max() + 1, rows.min(), rows.max() + 1
    pad = max(6, round(max(right - left, bottom - top) * margin))
    return (max(0, left - pad), max(0, top - pad), min(image.width, right + pad), min(image.height, bottom + pad))


def crop_to_ink(image: Image.Image, margin: float = 0.12) -> Image.Image:
    """Trim empty paper around the marks so recognition sees the writing at a useful size."""
    box = ink_box(image, margin)
    return image if box is None else image.crop(box)


def question_evidence(reference: np.ndarray, alignment: Alignment, question: dict) -> dict:
    """Evidence for one question on an aligned page. `reference` is the flattened original page.

    `image` holds the isolated marks. `confirm_image` is the untouched photo over the
    same area: a second reader looking at it cannot inherit a mark-isolation error.
    """
    if question["kind"] == "choice":
        choice = detect_choice(reference, alignment, question)
        return {"status": "hidden" if choice["status"] == "hidden" else "ink", "image": None,
                "confirm_image": None, "choice": choice}
    region = extract_region(reference, alignment, question["rect"])
    box = ink_box(region.ink) if region.status == "ink" else None
    return {
        "status": region.status, "image": region.ink.crop(box) if box else region.ink,
        "confirm_image": region.raw.crop(box) if box else None,
        "choice": None, "ink_pixels": region.ink_pixels,
    }


def match_pages(references: list, photos: list) -> list:
    """Pair each worksheet page with one uploaded page; tolerate pages uploaded out of order."""
    if len(photos) != len(references):
        raise PaperError(f"This worksheet has {len(references)} page{'s' if len(references) != 1 else ''}, but "
                         f"{len(photos)} page{'s were' if len(photos) != 1 else ' was'} uploaded. Upload every page once.")
    unused = list(range(len(photos)))
    matched = []
    for page_index, reference in enumerate(references):
        for candidate in sorted(unused, key=lambda index: (index != page_index, index)):
            try:
                alignment = align(reference, photos[candidate])
            except PaperError:
                continue
            matched.append(alignment)
            unused.remove(candidate)
            break
        else:
            prefix = f"Page {page_index + 1} of the worksheet could not be found in the upload. " if len(references) > 1 else ""
            raise PaperError(prefix + NOT_FOUND)
    return matched


def load_gray(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8) if Path(path).is_file() else np.empty(0, np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE) if data.size else None
    if image is None:
        raise PaperError("A stored page image is missing or unreadable.")
    return image


def _write_png(path: Path, array: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", array)
    if not ok:
        raise OSError("A page image could not be encoded.")
    temporary = path.with_name(path.name + ".writing")
    temporary.write_bytes(encoded.tobytes())
    os.replace(temporary, path)


def save_alignment(alignment: Alignment, directory: Path, index: int) -> dict:
    """Store the aligned page and its visible area as the evidence that grading reads."""
    _write_png(directory / f"page-{index}.png", alignment.image)
    _write_png(directory / f"page-{index}-visible.png", alignment.visible.astype(np.uint8) * 255)
    return {"index": index, **alignment.quality()}


def load_alignment(directory: Path, quality: dict) -> Alignment:
    index = int(quality["index"])
    image = load_gray(directory / f"page-{index}.png")
    visible = load_gray(directory / f"page-{index}-visible.png") > 0
    if image.shape != visible.shape:
        raise PaperError("A stored paper page is inconsistent.")
    return Alignment(image, visible, int(quality.get("inliers", 0)), float(quality.get("inlier_ratio", 0)),
                     float(quality.get("error_px", 0)), bool(quality.get("refined", False)),
                     float(quality.get("content", 1.0)))
