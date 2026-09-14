"""Offline preprocessing comparison; labels are checked only after inference.

Uses six existing constructed digital strokes and four previously inspected
legacy handwriting crops. These small diagnostics are not classroom accuracy
benchmarks. No worksheet answer key is loaded or passed into the recognizer.
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import argparse
import json
import socket
import sys
import time

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import ocr


def legacy_variants(image):
    variants = []
    for fraction in (0.08, 0.20):
        pad = max(8, round(image.height * fraction))
        padded = ImageOps.expand(image, border=pad, fill=255)
        target_width = min(1600, max(128, round(padded.width * 128 / padded.height)))
        padded = padded.resize((target_width, 128), Image.Resampling.LANCZOS)
        if fraction > 0.1:
            padded = padded.filter(ImageFilter.MedianFilter(3)).point(lambda value: 0 if value < 180 else 255)
        variants.append(padded.convert("RGB"))
    return variants


def square_variants(image):
    variants = []
    for fraction in (0.08, 0.20):
        longest = max(image.size)
        margin = max(8, round(longest * fraction))
        side = longest + margin * 2
        padded = Image.new("L", (side, side), 255)
        padded.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
        variants.append(padded.resize((384, 384), Image.Resampling.LANCZOS).convert("RGB"))
    return variants


def cases(include_legacy=True):
    fixture = json.loads((ROOT / "artifacts" / "ocr-stylus-evaluation.json").read_text(encoding="utf-8"))
    output = [{"name": f"digital-{entry['human_transcription']}", "label": entry["human_transcription"],
               "kind": "number", "image": ocr.render_ink(entry["strokes"], 1.2)} for entry in fixture["results"]]
    if include_legacy:
        legacy = json.loads((ROOT / "artifacts" / "ocr-evaluation.json").read_text(encoding="utf-8"))
        folder = ROOT.parent / "OCR" / "test cases (2)" / "test cases" / "handwritten images"
        for entry in legacy["results"][:4]:
            with Image.open(folder / entry["input"]) as source:
                image = ImageOps.autocontrast(source.crop(entry["crop"]).convert("L"))
            output.append({"name": f"legacy-{entry['human_transcription']}", "label": entry["human_transcription"], "kind": "number", "image": image})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digital-only", action="store_true")
    parser.add_argument("--output", default="ocr-quality-comparison.json")
    args = parser.parse_args()
    if Path(args.output).name != args.output:
        parser.error("Use an artifact filename, not a path.")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "model": ocr.MODEL_ID,
              "revision": ocr.MODEL_REVISION, "scope": "Small selected preprocessing diagnostic, not a classroom benchmark.",
              "outbound_connections_blocked": True, "confidence_threshold_changed": False, "results": []}
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Network disabled during OCR quality diagnostic")):
        for case in cases(not args.digital_only):
            item = {"name": case["name"], "human_transcription": case["label"], "policies": {}}
            for name, variant_function in (("legacy-stretched", legacy_variants), ("square-letterbox", square_variants)):
                started = time.monotonic()
                with ExitStack() as stack:
                    stack.enter_context(patch.object(ocr, "_variants", side_effect=variant_function))
                    if hasattr(ocr, "_number_variants"):
                        stack.enter_context(patch.object(ocr, "_number_variants", side_effect=variant_function))
                    with ocr._lock:
                        reading = ocr._infer_image(case["image"], case["kind"])
                reading["seconds"] = round(time.monotonic() - started, 3)
                reading["matches_transcription"] = reading["text"] == case["label"]
                item["policies"][name] = reading
                print(json.dumps({"case": case["name"], "policy": name, **reading}), flush=True)
            report["results"].append(item)
    output = ROOT / "artifacts" / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {output}", flush=True)


if __name__ == "__main__":
    main()
