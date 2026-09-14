"""One bounded, offline numeric blank-gap compression experiment.

This is deliberately NOT a production OCR preprocessing path. It compares
the same nine preselected images at the same two-reading/0.98 gate. Anonymous
actual ink and already-recorded visual transcriptions come from private local
diagnostic files; no database, worksheet keys or student identities are read.
All ink pixels (including punctuation and dots) must survive unchanged.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import json
import os
import socket
import sys
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import ocr

PRIVATE = ROOT / "artifacts" / "ocr-quality-actual-private"
OUTPUT = PRIVATE / "gap-compression"


def compress_white_gaps(image):
    """Shorten interior fully-white column runs, never a column containing ink."""
    source = np.asarray(image.convert("L"))
    occupied = np.any(source != 255, axis=0)
    cap = max(2, round(image.height * .06))
    keep = np.ones(image.width, dtype=bool)
    column = 0
    while column < image.width:
        if occupied[column]:
            column += 1
            continue
        start = column
        while column < image.width and not occupied[column]:
            column += 1
        if start > 0 and column < image.width and column - start > cap:
            keep[start + cap:column] = False
    compressed = source[:, keep]
    # Exact per-row, per-value equality after removing white pixels proves no
    # faint antialiasing, decimal point, punctuation or other ink disappeared.
    for before, after in zip(source, compressed):
        if not np.array_equal(before[before != 255], after[after != 255]):
            raise AssertionError("Gap experiment must preserve every ink pixel")
    return Image.fromarray(compressed)


def cases():
    actual = json.loads((PRIVATE / "inputs.json").read_text(encoding="utf-8"))
    labels = json.loads((PRIVATE / "results.json").read_text(encoding="utf-8"))
    visual = {item["field"]: item["human_visual_transcription"] for item in labels["results"]}
    if len(actual) != 3:
        raise ValueError("This diagnostic is restricted to the original three anonymous fields")
    for item in actual:
        yield {"name": item["field"], "group": "anonymous_actual", "label": visual[item["field"]],
               "image": ocr.render_ink(item["variants"]["saved"], item["aspect"])}
    fixture = json.loads((ROOT / "artifacts" / "ocr-stylus-evaluation.json").read_text(encoding="utf-8"))
    if len(fixture["results"]) != 6:
        raise ValueError("This diagnostic is restricted to the existing six constructed digit fixtures")
    for number, item in enumerate(fixture["results"], 1):
        yield {"name": f"fixture-{number}", "group": "constructed", "label": item["human_transcription"],
               "image": ocr.render_ink(item["strokes"], 1.2)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "model": ocr.MODEL_ID,
              "revision": ocr.MODEL_REVISION, "confidence_threshold": .98,
              "scope": "One bounded input experiment, not a classroom accuracy benchmark.",
              "database_access": False, "outbound_connections_blocked": True,
              "answer_keys_used": False, "results": []}
    assess = ocr._assess_readings
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Network blocked for OCR experiment")), patch.dict(os.environ, {"OCR_MIN_CONFIDENCE": "0.98"}):
        for case in cases():
            item = {"name": case["name"], "group": case["group"], "human_visual_transcription": case["label"], "policies": {}}
            for name, image in (("unchanged", case["image"]), ("white-gap-cap-006", compress_white_gaps(case["image"]))):
                readings = {}

                def recording_assess(texts, scores, kind):
                    readings.update(texts=texts, token_scores=scores)
                    return assess(texts, scores, kind)

                image.save(OUTPUT / f"{case['name']}-{name}.png")
                started = time.monotonic()
                with patch.object(ocr, "_assess_readings", side_effect=recording_assess), ocr._lock:
                    reading = ocr._infer_image(image, "number")
                reading.update(seconds=round(time.monotonic() - started, 3),
                               matches_visual_transcription=reading["text"] == case["label"],
                               two_readings=readings, dimensions=list(image.size))
                item["policies"][name] = reading
                print(json.dumps({"case": case["name"], "policy": name, **reading}), flush=True)
            report["results"].append(item)
    report["summary"] = {}
    for group in ("anonymous_actual", "constructed"):
        items = [item for item in report["results"] if item["group"] == group]
        report["summary"][group] = {policy: {
            "count": len(items),
            "exact_transcriptions": sum(item["policies"][policy]["matches_visual_transcription"] for item in items),
            "reliable_correct": sum(item["policies"][policy]["reliable"] and item["policies"][policy]["matches_visual_transcription"] for item in items),
            "reliable_incorrect": sum(item["policies"][policy]["reliable"] and not item["policies"][policy]["matches_visual_transcription"] for item in items),
        } for policy in ("unchanged", "white-gap-cap-006")}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"]}), flush=True)


if __name__ == "__main__":
    main()
