"""Measure the real handwriting pipeline on labelled examples, including safety.

Every example runs through the installed offline recognizer with network
connections blocked. Grading is then simulated twice: with the label as the
answer key (the student was right) and with a different key (the student was
wrong). Recognition never receives either key. The report separates automatic
marks from teacher review and counts the two unsafe outcomes: a right answer
marked wrong, and a wrong answer marked right.

Sources (all optional; at least one is needed):
  --photos     photographed printed worksheets in ../OCR/test cases (2), aligned
               to their blank templates with the printing removed
  --demos      constructed digital-ink fixtures in ../sample-worksheets
  --labels F   a private JSON list of {"image": "path.png", "kind": "number"|"text", "label": "..."}

Results are written to artifacts/handwriting-evaluation.json (ignored by Git).
Small labelled sets are diagnostics, not a promise of classroom accuracy.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import grading, ocr, paper

LEGACY = ROOT.parent / "OCR" / "Grading worksheet" / "Grading worksheet" / "data"
CASES = ROOT.parent / "OCR" / "test cases (2)" / "test cases"
DEMOS = ROOT.parent / "sample-worksheets" / "student-written-demos"
# Visual transcriptions of the photographed sheets, checked by eye; used only after recognition.
PHOTO_LABELS = [
    ("box test -tpl_1757837807.jpg", "tpl_1757837807", ["3", "4", "9", "5", "5", "7", "4", "10"]),
    ("box test-tpl_1757571776.jpg", "tpl_1757571776", ["b", "b", "b", "k", "k", "P", "p", "p", "p"]),
    ("dotted test -dotted_1757854072.jpg", "dotted_1757854072", ["3", "4", "2", "1", "4"]),
    ("dotted test-dotted_1757574803.jpg", "dotted_1757574803", ["round", "legs", "fur", "chocolate", "year", "year"]),
    ("blank line test-blank_1757572093.jpg", "blank_1757572093", ["4", "2", "2", "2", "3", "3"]),
    ("blank line test -blank_1757855157.jpg", "blank_1757855157", ["ROBOT", "YOYO", "TEDDY BEAR", "SCOOTER"]),
]


def kind_of(label: str) -> str:
    return "number" if grading.parse_number(label) is not None else "text"


def wrong_key(label: str, kind: str) -> str:
    """A different accepted answer, so the simulated student is wrong."""
    if kind == "number":
        value = grading.parse_number(label) + 1
        return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    return "zebra" if grading.normalize_text(label) != "zebra" else "apple"


def classify(student_correct: bool, status: str) -> str:
    if status == "pending_review":
        return "review"
    if student_correct:
        return "auto-correct" if status == "correct" else "UNSAFE right marked wrong"
    return "auto-wrong" if status == "incorrect" else "UNSAFE wrong marked right"


def _legacy_regions(template_id: str):
    """Answer rectangles (page-relative) from the prototype's saved templates."""
    from PIL import Image

    if template_id.startswith("tpl_"):
        data = json.loads((LEGACY / "answer_templates" / f"{template_id}.json").read_text(encoding="utf-8"))
        regions = [{"x": q["relative_position"]["x"], "y": q["relative_position"]["y"],
                    "w": q["relative_position"]["width"], "h": q["relative_position"]["height"]} for q in data["questions"]]
        return regions, CASES / "setup templates" / f"worksheet_{template_id}.png"
    if template_id.startswith("dotted_"):
        data = json.loads((LEGACY / "dotted_templates" / f"{template_id}.json").read_text(encoding="utf-8"))
        width, height = data["image_dimensions"]["width"], data["image_dimensions"]["height"]
        regions = [{"x": q["position"]["x"] / width, "y": (q["position"]["y"] - 70) / height,
                    "w": (q["position"]["x2"] - q["position"]["x"]) / width, "h": 90 / height} for q in data["questions"]]
        return regions, CASES / "setup templates" / f"worksheet_{template_id}.png"
    data = json.loads((LEGACY / "blank_templates" / f"{template_id}.json").read_text(encoding="utf-8"))
    template = CASES / "setup templates" / f"{template_id}.png"
    with Image.open(template) as image:
        width, height = image.size
    regions = [{"x": line["x"] / width, "y": (line["y"] - 75) / height, "w": line["width"] / width, "h": 85 / height}
               for line in data["lines"]]
    return regions, template


def photo_examples():
    import cv2

    for photo_name, template_id, labels in PHOTO_LABELS:
        photo_path = CASES / "handwritten images" / photo_name
        if not photo_path.is_file():
            continue
        regions, template = _legacy_regions(template_id)
        reference = paper.load_gray(template)
        scale = 1584 / max(reference.shape)
        reference = cv2.resize(reference, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        alignment = paper.align(reference, paper.load_pages([photo_path.read_bytes()])[0])
        flattened = paper.flatten(reference)
        for number, (rect, label) in enumerate(zip(regions, labels), start=1):
            evidence = paper.question_evidence(flattened, alignment, {"kind": kind_of(label), "rect": rect})
            yield {"id": f"photo:{template_id}:{number}", "source": "photographed paper", "kind": kind_of(label),
                   "label": label, "evidence": evidence}


def demo_examples():
    manifest = json.loads((DEMOS / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        fixture = json.loads((DEMOS / record["fixture"]).read_text(encoding="utf-8"))
        intended = {row["question_id"]: row["intended_written_value"] for row in record["responses"]}
        for question in fixture["questions"]:
            strokes = fixture["answers"][question["id"]]["strokes"]
            if question["kind"] != "number" or not strokes:
                continue
            aspect = question["rect"]["w"] / question["rect"]["h"] * 612 / 792
            yield {"id": f"demo:{record['fixture']}:{question['id']}", "source": "constructed digital ink",
                   "kind": "number", "label": intended[question["id"]],
                   "evidence": {"status": "ink", "image": ocr.render_ink(strokes, aspect)}}


def label_examples(path: Path):
    from PIL import Image

    # utf-8-sig: label files saved by Windows tools often start with a byte-order mark.
    for number, item in enumerate(json.loads(path.read_text(encoding="utf-8-sig")), start=1):
        image_path = (path.parent / item["image"]).resolve()
        with Image.open(image_path) as image:
            loaded = image.convert("L")
        kind = item.get("kind") or kind_of(item["label"])
        yield {"id": f"labels:{number}", "source": "private labelled answers", "kind": kind,
               "label": item["label"], "evidence": {"status": "ink", "image": loaded}}


def evaluate(example: dict) -> dict:
    """One recognition, graded against a right key and a wrong key."""
    started = time.monotonic()
    evidence = example["evidence"]
    cache = {}

    def recognizer(image, kind, confirm_image=None):
        if "reading" not in cache:
            cache["reading"] = ocr.recognize_image(image, kind, confirm_image)
            original = cache["reading"].get("confirm")
            if callable(original):
                cache["reading"]["confirm"] = lambda: cache.setdefault("confirmed", original())
        return cache["reading"]

    outcomes = {}
    for student_correct in (True, False):
        key = example["label"] if student_correct else wrong_key(example["label"], example["kind"])
        question = {"id": "q", "label": example["id"], "page": 0, "rect": {"x": 0, "y": 0, "w": 1, "h": 1},
                    "kind": example["kind"], "expected": [key], "points": 1, "tolerance": 0,
                    "case_sensitive": False, "options": []}
        marked = grading.grade_answers([question], {}, recognizer=ocr.recognize, image_recognizer=recognizer,
                                       paper=lambda _question: evidence, budget_seconds=3600)
        outcomes["right_key" if student_correct else "wrong_key"] = classify(student_correct, marked["results"][0]["status"])
    reading = cache.get("reading", {})
    confirmed = cache.get("confirmed", {})
    return {
        "id": example["id"], "source": example["source"], "kind": example["kind"], "label": example["label"],
        "evidence_status": evidence.get("status"), "read": reading.get("text", ""),
        "confidence": reading.get("confidence"), "reliable": reading.get("reliable", False),
        "second_reading": (confirmed.get("readings") or [{}, {}])[-1].get("text") if confirmed else None,
        "exact_read": grading.normalize_text(reading.get("text", "")) == grading.normalize_text(example["label"]),
        **outcomes, "seconds": round(time.monotonic() - started, 2),
    }


def summarize(rows: list) -> dict:
    by_source = defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)
    summary = {}
    for source, items in by_source.items():
        right, wrong = Counter(item["right_key"] for item in items), Counter(item["wrong_key"] for item in items)
        summary[source] = {
            "examples": len(items), "exact_first_reading": sum(item["exact_read"] for item in items),
            "student_right": dict(right), "student_wrong": dict(wrong),
            "unsafe": right["UNSAFE right marked wrong"] + wrong["UNSAFE wrong marked right"],
            "median_seconds": sorted(item["seconds"] for item in items)[len(items) // 2],
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--photos", action="store_true")
    parser.add_argument("--demos", action="store_true")
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="Evaluate at most this many examples per source")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "handwriting-evaluation.json",
                        help="Where to save the JSON report (default: artifacts/handwriting-evaluation.json)")
    args = parser.parse_args()
    sources = []
    if args.photos:
        sources.append(photo_examples)
    if args.demos:
        sources.append(demo_examples)
    if args.labels:
        sources.append(lambda: label_examples(args.labels))
    if not sources:
        parser.error("Choose --photos, --demos and/or --labels FILE.")
    status = ocr.status()
    if not status["configured"]:
        parser.error(status["message"])
    rows = []
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Network blocked during evaluation")):
        for source in sources:
            for count, example in enumerate(source(), start=1):
                if args.limit and count > args.limit:
                    break
                row = evaluate(example)
                rows.append(row)
                print(f"{row['id']:<52} label={row['label']!s:<11} read={row['read']!r:<12} "
                      f"right-key={row['right_key']:<26} wrong-key={row['wrong_key']:<26} {row['seconds']}s", flush=True)
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "engines": [{"model": engine.repo, "revision": engine.revision} for engine in ocr.ENGINES],
        "cross_check": status["cross_check"], "thresholds": ocr.thresholds(),
        "summary": summarize(rows), "rows": rows,
        "scope": "Small labelled diagnostic sets. Not a calibrated or population-level classroom accuracy estimate.",
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
