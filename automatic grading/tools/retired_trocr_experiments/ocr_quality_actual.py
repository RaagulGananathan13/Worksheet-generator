"""Private, read-only diagnosis of at most three local handwritten answers.

Preparation queries no student names, account IDs, attempt IDs, or expected
answers. It saves anonymous ink evidence under this app's private artifacts.
Evaluation uses human transcriptions only AFTER each model result. Removing a
first single-point selection mark is a diagnostic variant, never a data change.
"""

from pathlib import Path
from unittest.mock import patch
import argparse
import json
import socket
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import ocr

OUTPUT = ROOT / "artifacts" / "ocr-quality-actual-private"


def prepare():
    database = ROOT / "data" / "grading.sqlite3"
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("""
            SELECT answers, pages,
              (SELECT json_group_array(json_object(
                'id',json_extract(value,'$.id'),
                'rect',json_extract(value,'$.rect'),
                'page',json_extract(value,'$.page')))
               FROM json_each(attempts.questions))
            FROM attempts WHERE status='review' ORDER BY updated_at DESC LIMIT 1
        """).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("No review attempt is available for this local diagnostic.")
    answers, pages, geometry = map(json.loads, row)
    cases = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for question in geometry:
        answer = answers.get(question["id"], {})
        strokes = answer.get("strokes", [])
        if not strokes or sum(len(stroke.get("points", [])) for stroke in strokes) < 3:
            continue
        rect, page = question["rect"], pages[question["page"]]
        aspect = rect["w"] * page["width"] / (rect["h"] * page["height"])
        variants = {"saved": strokes}
        if len(strokes) > 1 and len(strokes[0].get("points", [])) == 1:
            variants["without_first_selection_point"] = strokes[1:]
        name = f"field-{len(cases) + 1}"
        for variant, ink in variants.items():
            image = ocr.render_ink(ink, aspect)
            if image is not None:
                image.save(OUTPUT / f"{name}-{variant}.png")
        cases.append({"field": name, "aspect": aspect, "variants": variants})
        print(json.dumps({"field": name, "stroke_count": len(strokes), "single_point_count": sum(len(stroke.get('points', [])) == 1 for stroke in strokes), "aspect": round(aspect, 4)}), flush=True)
        if len(cases) == 3:
            break
    (OUTPUT / "inputs.json").write_text(json.dumps(cases) + "\n", encoding="utf-8")
    print("Inspect these private images and record visual transcriptions before evaluating.", flush=True)


def evaluate(transcriptions, policy_name="baseline"):
    cases = json.loads((OUTPUT / "inputs.json").read_text(encoding="utf-8"))
    labels = transcriptions.split(",")
    if len(labels) != len(cases):
        raise ValueError("Provide exactly one visual transcription per prepared field.")
    results = []
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Network blocked during private OCR diagnostic")):
        for case, label in zip(cases, labels):
            item = {"field": case["field"], "human_visual_transcription": label, "readings": {}}
            for name, strokes in case["variants"].items():
                started = time.monotonic()
                ink_image = ocr.render_ink(strokes, aspect_ratio=case["aspect"])
                if ink_image is not None:
                    ink_image.save(OUTPUT / f"{case['field']}-{name}-{policy_name}.png")
                reading = ocr.recognize(strokes=strokes, kind="number", aspect_ratio=case["aspect"])
                reading["seconds"] = round(time.monotonic() - started, 3)
                reading["matches_visual_transcription"] = reading["text"] == label
                item["readings"][name] = reading
                print(json.dumps({"field": case["field"], "variant": name, **reading}), flush=True)
            results.append(item)
    report = {"scope": "Three anonymous local ink fields; visual labels used only after model inference.", "policy": policy_name, "database_writes": False, "outbound_connections_blocked": True, "results": results}
    (OUTPUT / f"results-{policy_name}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--transcriptions", default="")
    parser.add_argument("--policy-name", choices=("baseline", "browser-matched"), default="baseline")
    options = parser.parse_args()
    if options.evaluate:
        evaluate(options.transcriptions, options.policy_name)
    else:
        prepare()
