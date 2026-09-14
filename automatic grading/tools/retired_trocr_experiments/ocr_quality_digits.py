"""Isolated MNIST feasibility experiment, NOT an automatic grading engine.

Install ONNX Runtime only in artifacts/digit-eval-deps. Model setup downloads
only a pinned 26kB ONNX asset and checks its official Git-LFS SHA256. Evaluation
blocks networking, reads the same three anonymous prepared fields and six
constructed fixtures, and never reads a database, expected key or identity.
MNIST has only ten digit classes: high softmax scores do NOT prove an input is
a digit. Three simple synthetic symbol controls illustrate this limitation.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import argparse
import hashlib
import json
import socket
import sys
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "artifacts" / "digit-eval-deps"))
from app import ocr
from tools.ocr_quality_gaps import cases

OUTPUT = ROOT / "artifacts" / "ocr-quality-actual-private" / "digit-model"
REVISION = "4c46cd00fbdb7cd30b6c1c17ab54f2e1f4f7b177"
MODEL_SHA256 = "5c688690f8bacf667d4c2074af5ad0646ca328d7ab03eccf944a65b320171bdd"
MODEL_SIZE = 26143
MODEL_RELPATH = "validated/vision/classification/mnist/model/mnist-12.onnx"
POINTER_URL = f"https://raw.githubusercontent.com/onnx/models/{REVISION}/{MODEL_RELPATH}"
MODEL_URL = f"https://media.githubusercontent.com/media/onnx/models/{REVISION}/{MODEL_RELPATH}"
DOCUMENTATION = f"https://github.com/onnx/models/blob/{REVISION}/validated/vision/classification/mnist/README.md"


def download():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pointer = urllib.request.urlopen(POINTER_URL, timeout=30).read(2048).decode("ascii")
    if f"oid sha256:{MODEL_SHA256}" not in pointer or f"size {MODEL_SIZE}" not in pointer:
        raise ValueError("Pinned official LFS pointer did not match expected model")
    model = urllib.request.urlopen(MODEL_URL, timeout=30).read(MODEL_SIZE + 1)
    if len(model) != MODEL_SIZE or hashlib.sha256(model).hexdigest() != MODEL_SHA256:
        raise ValueError("Pinned official model content did not match size/hash")
    (OUTPUT / "mnist-12.onnx").write_bytes(model)
    metadata = {"model": "ONNX Model Zoo mnist-12", "revision": REVISION,
                "sha256": MODEL_SHA256, "size": MODEL_SIZE, "pointer_url": POINTER_URL,
                "download_url": MODEL_URL, "documentation": DOCUMENTATION,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "license_note": "MNIST README declares MIT; Hugging Face metadata says Apache-2.0 while its body says MIT. Verify redistribution notices before adoption.",
                "runtime": "onnxruntime==1.22.1 installed only with --target artifacts/digit-eval-deps --no-deps"}
    (OUTPUT / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata), flush=True)


def segments(image):
    """Split only at completely white column runs; retain every nonwhite pixel."""
    source = np.asarray(image.convert("L"))
    occupied = np.any(source != 255, axis=0)
    spans = []
    start = None
    for column, ink in enumerate(list(occupied) + [False]):
        if ink and start is None:
            start = column
        elif not ink and start is not None:
            spans.append((start, column))
            start = None
    output = []
    for start, end in spans:
        part = image.crop((start, 0, end, image.height))
        bounds = ImageOps.invert(part).getbbox()
        if bounds is None:
            raise AssertionError("An ink span cannot be empty")
        output.append(part.crop(bounds))
    if sum(np.count_nonzero(np.asarray(part) != 255) for part in output) != np.count_nonzero(source != 255):
        raise AssertionError("Segmentation must preserve all nonwhite pixels")
    return output


def prepare_digit(image, dx=0, dy=0):
    foreground = ImageOps.invert(image.convert("L"))
    foreground.thumbnail((20, 20), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (28, 28), 0)
    canvas.paste(foreground, ((28 - foreground.width) // 2 + dx, (28 - foreground.height) // 2 + dy))
    return canvas


def evaluate_image(session, image):
    parts = segments(image)
    glyphs = []
    for part in parts:
        views = []
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            prepared = prepare_digit(part, dx, dy)
            tensor = np.asarray(prepared, dtype=np.float32)[None, None, :, :] / 255
            logits = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
            scores = np.exp(logits - np.max(logits))
            scores /= np.sum(scores)
            digit = int(np.argmax(scores))
            views.append({"digit": str(digit), "score": round(float(scores[digit]), 8)})
        glyphs.append({"size": list(part.size), "views": views,
                       "stable": len({item["digit"] for item in views}) == 1,
                       "minimum_score": min(item["score"] for item in views)})
    # These crude geometry checks are NOT an open-set recognizer. They merely
    # prevent a known tiny dot / flat mark being enlarged then treated as a digit.
    geometric_reasons = []
    if not 1 <= len(parts) <= 12:
        geometric_reasons.append("Unexpected number of gap-separated components")
    if image.height < 12:
        geometric_reasons.append("Too little absolute ink height")
    for part in parts:
        if part.height < image.height * .45:
            geometric_reasons.append("A small component may be punctuation; none was dropped")
        if part.width > part.height * 1.25:
            geometric_reasons.append("A component may be a symbol or touching digits")
    raw_text = "".join(item["views"][0]["digit"] for item in glyphs)
    confidence = min((item["minimum_score"] for item in glyphs), default=0)
    stable = bool(glyphs) and all(item["stable"] for item in glyphs)
    return {"text": raw_text, "minimum_score": confidence, "all_five_views_stable": stable,
            "experimental_gate": stable and confidence >= .98 and not geometric_reasons,
            "geometry_reasons": geometric_reasons, "segments": glyphs}, parts


def controls():
    for label in ("plus", "minus", "dot"):
        image = Image.new("L", (90, 90), 255)
        drawing = ImageDraw.Draw(image)
        if label == "dot":
            drawing.ellipse((40, 40, 48, 48), fill=0)
        else:
            drawing.line((10, 45, 80, 45), fill=0, width=8)
            if label == "plus":
                drawing.line((45, 10, 45, 80), fill=0, width=8)
        image = image.crop(ImageOps.invert(image).getbbox())
        yield {"name": f"symbol-{label}", "group": "symbol_control", "label": label, "image": image}


def evaluate():
    import onnxruntime as ort
    model_path = OUTPUT / "mnist-12.onnx"
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("Local diagnostic model hash mismatch")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    report = {"provenance": json.loads((OUTPUT / "provenance.json").read_text(encoding="utf-8")),
              "network_blocked_during_evaluation": True, "answer_keys_used": False,
              "scope": "Tiny feasibility diagnostic, not a validated accuracy or open-set benchmark.",
              "preprocessing": "All-ink vertical gap segmentation; aspect-preserving fit within 20x20; center 28x28; white-on-black float32/255; five shifts center/left/right/up/down 1px.",
              "results": []}
    with patch.object(socket.socket, "connect", side_effect=RuntimeError("Network blocked during digit diagnostic")):
        session = ort.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        report["runtime"] = {"version": ort.__version__, "providers": session.get_providers(),
                             "input": [item.name for item in session.get_inputs()]}
        for case in [*cases(), *controls()]:
            started = time.monotonic()
            reading, parts = evaluate_image(session, case["image"])
            for number, part in enumerate(parts, 1):
                prepare_digit(part).save(OUTPUT / f"{case['name']}-glyph-{number}.png")
            reading.update(name=case["name"], group=case["group"],
                           human_visual_transcription=case["label"],
                           matches_visual_transcription=reading["text"] == case["label"],
                           milliseconds=round((time.monotonic() - started) * 1000, 2))
            report["results"].append(reading)
            print(json.dumps(reading), flush=True)
    report["summary"] = {}
    for group in ("anonymous_actual", "constructed", "symbol_control"):
        items = [item for item in report["results"] if item["group"] == group]
        report["summary"][group] = {
            "count": len(items),
            "exact_transcriptions": sum(item["matches_visual_transcription"] for item in items),
            "gate_correct": sum(item["experimental_gate"] and item["matches_visual_transcription"] for item in items),
            "gate_incorrect": sum(item["experimental_gate"] and not item["matches_visual_transcription"] for item in items),
            "minimum_score_of_any_incorrect": [item["minimum_score"] for item in items if not item["matches_visual_transcription"]],
        }
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    download() if args.download else evaluate()
