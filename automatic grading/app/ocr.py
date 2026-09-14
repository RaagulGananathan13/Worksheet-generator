"""Free, offline handwriting recognition with an independent second opinion.

Recognition receives only the student's own marks - digital ink drawn on a
blank background, or a printed-worksheet crop with the printing removed - and
the answer type. It never receives an answer key, and no image leaves the
server.

GLM-OCR reads every handwritten answer. A reading can earn marks only when it
is complete, well formed and confident. When a confident reading differs from
the answer key, grading asks PaddleOCR-VL - a separately trained model - to read
the same image. An automatic zero requires the two models to agree exactly.
Everything else goes to teacher review. Token probabilities are screening
signals, not calibrated accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import threading
import time

from .grading import normalize_text, parse_number


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Engine:
    name: str
    label: str
    repo: str
    revision: str
    weights_sha256: str
    license: str
    prompt: str
    files: tuple
    weights: str = "model.safetensors"


PRIMARY = Engine(
    name="glm-ocr", label="GLM-OCR", repo="zai-org/GLM-OCR",
    revision="2e85a62840ccac27daa451df36c736c4636b8628",
    weights_sha256="a16eb0de98d199293371c560f95f83130d2a2c9612449df16839f08ff9498815",
    license="MIT", prompt="Text Recognition:",
    files=("config.json", "generation_config.json", "preprocessor_config.json", "processor_config.json",
           "chat_template.jinja", "tokenizer.json", "tokenizer_config.json", "model.safetensors"),
)
SECONDARY = Engine(
    name="paddleocr-vl-1.5", label="PaddleOCR-VL", repo="PaddlePaddle/PaddleOCR-VL-1.5",
    revision="2a4195faa5e7914c12f2fc601d72c81caf8d2da5",
    weights_sha256="d557c9d8997ae57ed3b1b33bdf347be878cc335687f32ca105341c16973f8958",
    license="Apache-2.0", prompt="OCR:",
    files=("config.json", "generation_config.json", "preprocessor_config.json", "processor_config.json",
           "chat_template.jinja", "tokenizer.json", "tokenizer.model", "tokenizer_config.json",
           "special_tokens_map.json", "added_tokens.json", "model.safetensors"),
)
ENGINES = (PRIMARY, SECONDARY)
SOURCE = "local-ocr"
TEXT_PATTERN = re.compile(r"[A-Za-z]+(?:[ '\-][A-Za-z]+)*[.!?]?")

_inference_lock = threading.Lock()
_load_lock = threading.Lock()
_loaded: dict = {}
_failures: dict = {}


def models_directory() -> Path:
    """An explicit local directory holding one folder per engine; never a Hub identifier."""
    configured = Path(os.environ.get("OCR_MODEL_PATH", "data/models"))
    return (configured if configured.is_absolute() else ROOT / configured).resolve()


def engine_path(engine: Engine) -> Path:
    return models_directory() / engine.name


def _environment() -> None:
    # Set before the optional libraries import. Runtime has no network fallback,
    # Hub credentials, remote Python code, or caches in a user's home directory.
    cache = ROOT / "data" / "cache"
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(cache / "huggingface" / "hub")
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"


def _manifest(path: Path):
    try:
        return json.loads((path / "verified-model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def files_ready(engine: Engine, path: Path | None = None) -> bool:
    path = path or engine_path(engine)
    if not all((path / name).is_file() for name in engine.files):
        return False
    manifest = _manifest(path)
    return bool(
        isinstance(manifest, dict) and manifest.get("model") == engine.repo
        and manifest.get("revision") == engine.revision
        and isinstance(manifest.get("sha256"), dict)
        and manifest["sha256"].get(engine.weights) == engine.weights_sha256
        and all(isinstance(manifest["sha256"].get(name), str) for name in engine.files)
    )


def _dependencies_missing() -> list:
    return [name for name in ("torch", "transformers", "safetensors", "PIL")
            if importlib.util.find_spec(name) is None]


def status() -> dict:
    """Cheap readiness probe. Large libraries and weights load only on first use."""
    missing = _dependencies_missing()
    engines = [{"name": engine.name, "label": engine.label,
                "configured": not missing and files_ready(engine),
                "loaded": engine.name in _loaded} for engine in ENGINES]
    configured = engines[0]["configured"]
    cross_check = configured and engines[1]["configured"]
    available = configured and engines[0]["loaded"]
    failure = next((_failures[engine.name][0] for engine in ENGINES if engine.name in _failures), None)
    if missing:
        message = "Local handwriting recognition is not installed. Install requirements-ocr.txt; handwritten answers wait for teacher review."
    elif not configured:
        message = "The local handwriting models are not installed or verified. Run python tools/download_model.py; handwritten answers wait for teacher review."
    elif failure:
        message = failure
    elif not cross_check:
        message = "Only GLM-OCR is installed. Matching handwriting can be marked correct, but nothing is marked wrong automatically until PaddleOCR-VL is installed."
    elif not available:
        message = "GLM-OCR and PaddleOCR-VL are installed and verified. They load on the first handwritten submission; no network is used."
    else:
        message = "GLM-OCR and PaddleOCR-VL are ready. Uncertain readings still wait for teacher review."
    return {"available": available, "configured": configured, "cross_check": cross_check,
            "provider": SOURCE, "engines": engines, "message": message}


def _result(text="", confidence=0.0, reliable=False, reason="", readings=()) -> dict:
    return {"text": text, "confidence": round(float(confidence), 6), "reliable": reliable,
            "certain": False, "exact_agreement": False, "reason": reason,
            "source": SOURCE, "readings": list(readings)}


def _number_setting(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return default
    return min(high, max(low, value)) if math.isfinite(value) else default


def thresholds() -> dict:
    minimum = _number_setting("OCR_MIN_CONFIDENCE", 0.90, 0.80, 1.0)
    return {
        "count": minimum,
        "wrong": max(minimum, _number_setting("OCR_CERTAIN_CONFIDENCE", 0.95, 0.90, 1.0)),
        "confirm": _number_setting("OCR_CONFIRM_CONFIDENCE", 0.75, 0.60, 1.0),
    }


def render_ink(strokes: list, aspect_ratio: float = 3.0):
    """Render only normalized digital ink to a bounded PIL image.

    No background or expected text is accepted, so printed worksheet answers
    can never leak into recognition.
    """
    from PIL import Image, ImageDraw, ImageOps

    if not isinstance(strokes, list) or len(strokes) > 600:
        raise ValueError("Invalid or excessive ink strokes")
    aspect = float(aspect_ratio)
    if not math.isfinite(aspect) or aspect <= 0:
        raise ValueError("Invalid answer-region aspect ratio")
    aspect = min(32.0, max(0.1, aspect))
    height = 256
    width = round(height * aspect)
    if width > 2048:
        width, height = 2048, max(64, round(2048 / aspect))
    elif width < 96:
        width, height = 96, min(960, round(96 / aspect))
    scale = 2
    canvas = Image.new("L", (width * scale, height * scale), 255)
    draw = ImageDraw.Draw(canvas)
    count = 0
    for stroke in strokes:
        if not isinstance(stroke, dict):
            raise ValueError("Invalid stroke")
        points = stroke.get("points", [])
        if not isinstance(points, list):
            raise ValueError("Invalid stroke points")
        count += len(points)
        if count > 60000:
            raise ValueError("Too many ink points")
        thickness = float(stroke.get("width", 0.006))
        if not math.isfinite(thickness) or not 0 < thickness <= 0.1:
            raise ValueError("Invalid stroke width")
        normalized = []
        for point in points:
            if not isinstance(point, dict):
                raise ValueError("Invalid ink point")
            x, y, pressure = (float(point.get(k, 0.5 if k == "p" else -1)) for k in ("x", "y", "p"))
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y, pressure)):
                raise ValueError("Ink points must be normalized")
            position = (round(x * (width * scale - 1)), round(y * (height * scale - 1)))
            normalized.append((position, pressure))
        # Match static/ink.js: segment pressure is the average of its two
        # endpoints, with a 0.4 + 0.6*p multiplier and round caps.
        base = max(0.8, thickness * width) * scale
        segments = zip(normalized, normalized[1:]) if len(normalized) > 1 else ((item, item) for item in normalized)
        for (start, previous_pressure), (position, pressure) in segments:
            pen = max(1, round(base * (0.4 + 0.6 * (previous_pressure + pressure) / 2)))
            radius = pen / 2
            draw.line([start, position], fill=0, width=pen)
            for endpoint in (start, position):
                draw.ellipse((endpoint[0] - radius, endpoint[1] - radius,
                              endpoint[0] + radius, endpoint[1] + radius), fill=0)
    bbox = ImageOps.invert(canvas).getbbox()
    if bbox is None or count < 2:
        return None
    image = canvas.crop(bbox)
    if image.width < 4 or image.height < 4:
        return None
    return image.resize((max(1, image.width // scale), max(1, image.height // scale)), Image.Resampling.LANCZOS)


def prepare(image):
    """White margin and a readable minimum height; the ink itself is unchanged."""
    from PIL import Image, ImageOps

    gray = image.convert("L")
    pad = max(8, round(max(gray.size) * 0.15))
    padded = ImageOps.expand(gray, border=pad, fill=255)
    if padded.height < 96:
        padded = padded.resize((max(1, round(padded.width * 96 / padded.height)), 96), Image.Resampling.LANCZOS)
    longest = max(padded.size)
    if longest > 1540:
        padded = padded.resize((max(1, round(padded.width * 1540 / longest)), max(1, round(padded.height * 1540 / longest))),
                               Image.Resampling.LANCZOS)
    return padded.convert("RGB")


def clean(text: str) -> str:
    """Remove document-formatting wrappers the OCR models may add; keep every character written."""
    text = (text or "").strip()
    text = re.sub(r"^```[A-Za-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "$":
        text = text.strip("$")
    if text.startswith("\\(") and text.endswith("\\)"):
        text = text[2:-2]
    return " ".join(text.replace("−", "-").split())


def _verify_files(engine: Engine, path: Path) -> None:
    if not files_ready(engine, path):
        raise RuntimeError(f"{engine.label} is missing or not verified. Run python tools/download_model.py.")
    manifest = _manifest(path)
    # Verify every required file once per model load. No pickle loading.
    for name in engine.files:
        digest = hashlib.sha256()
        with (path / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != manifest["sha256"].get(name):
            raise RuntimeError(f"{engine.label} failed its integrity check. Run python tools/download_model.py again.")


def _load(engine: Engine):
    with _load_lock:
        if engine.name in _loaded:
            return _loaded[engine.name]
        failure = _failures.get(engine.name)
        if failure and time.monotonic() - failure[1] < 30:
            raise RuntimeError(failure[0])
        try:
            path = engine_path(engine)
            _verify_files(engine, path)
            _environment()
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor

            torch.set_num_threads(int(_number_setting("OCR_CPU_THREADS", 4, 1, 16)))
            processor = AutoProcessor.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, token=False)
            model = AutoModelForImageTextToText.from_pretrained(
                str(path), local_files_only=True, trust_remote_code=False, token=False,
                use_safetensors=True, dtype=torch.float32,
            ).to("cpu").eval()
        except Exception:
            message = (f"{engine.label} could not load. Check the dependencies and the verified local model "
                       "installation; handwritten answers wait for teacher review.")
            _failures[engine.name] = (message, time.monotonic())
            raise RuntimeError(message) from None
        _failures.pop(engine.name, None)
        _loaded[engine.name] = (torch, processor, model)
        return _loaded[engine.name]


def _read(engine: Engine, image, kind: str) -> dict:
    torch, processor, model = _load(engine)
    content = [{"type": "image", "image": image}, {"type": "text", "text": engine.prompt}]
    inputs = processor.apply_chat_template(
        [{"role": "user", "content": content}], add_generation_prompt=True, tokenize=True,
        return_dict=True, return_tensors="pt",
    )
    with torch.inference_mode():
        output = model.generate(
            **inputs, do_sample=False, num_beams=1, use_cache=True,
            max_new_tokens=24 if kind == "number" else 96, max_time=60.0,
            output_scores=True, return_dict_in_generate=True,
        )
    generated = output.sequences[0, inputs["input_ids"].shape[1]:].tolist()
    stops = model.generation_config.eos_token_id
    stops = set(stops if isinstance(stops, (list, tuple)) else [stops])
    special = set(processor.tokenizer.all_special_ids) | stops
    probabilities = [float(torch.softmax(scores[0].float(), dim=-1)[token])
                     for token, scores in zip(generated, output.scores) if token not in special]
    return {
        "engine": engine.name,
        "text": clean(processor.decode(generated, skip_special_tokens=True)),
        "confidence": round(min(probabilities), 6) if probabilities else 0.0,
        "completed": any(token in stops for token in generated),
    }


def well_formed(text: str, kind: str) -> bool:
    if kind == "number":
        return parse_number(text) is not None
    return len(text) <= 200 and TEXT_PATTERN.fullmatch(text) is not None


def same_reading(first: str, second: str, kind: str) -> bool:
    if kind == "number":
        left, right = parse_number(first), parse_number(second)
        return left is not None and left == right
    return normalize_text(first) == normalize_text(second)


def _valid_score(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1


def assess(reading: dict, kind: str) -> dict:
    """Whether one GLM-OCR reading may count. Deterministic; no answer key is involved."""
    limits = thresholds()
    text, confidence = reading.get("text", ""), reading.get("confidence", 0.0)
    if not _valid_score(confidence):
        return _result(text, reason="Recognition scores were invalid; a teacher will check this answer.", readings=[reading])
    if not text:
        return _result(reason="No readable writing was found. A teacher will check the answer; this is not a wrong mark.", readings=[reading])
    if not reading.get("completed"):
        return _result(text, confidence, reason="The reading did not finish cleanly. A teacher will check the writing.", readings=[reading])
    if not well_formed(text, kind):
        expected = "a single clear number" if kind == "number" else "plain English words"
        return _result(text, confidence, readings=[reading],
                       reason=f"The writing was read as “{text}”, which is not {expected}. A teacher will check it; nothing was removed or corrected.")
    if confidence < limits["count"]:
        return _result(text, confidence, readings=[reading],
                       reason=f"The handwriting model is not confident about this writing (read as “{text}”). A teacher will check it; this is not a wrong mark.")
    return _result(text, confidence, reliable=True, readings=[reading], reason=f"Read as “{text}”.")


def confirm(result: dict, second: dict | None, kind: str) -> dict:
    """Decide whether an independent second reading makes a differing answer certain."""
    base = {key: value for key, value in result.items() if key != "confirm"}
    limits = thresholds()
    if not base.get("reliable") or base.get("confidence", 0) < limits["wrong"]:
        return {**base, "certain": False, "exact_agreement": False,
                "reason": "The first reading is not confident enough to mark an answer wrong."}
    if second is None:
        return {**base, "certain": False, "exact_agreement": False,
                "reason": "The second handwriting model is not available to confirm this reading."}
    second_text = second.get("text", "")
    agree = (bool(second.get("completed")) and _valid_score(second.get("confidence"))
             and second["confidence"] >= limits["confirm"] and well_formed(second_text, kind)
             and same_reading(base["text"], second_text, kind))
    readings = list(base.get("readings", [])) + [second]
    if not agree:
        return {**base, "certain": False, "exact_agreement": False, "readings": readings,
                "reason": f"The second handwriting model read this as “{second_text or 'nothing'}”, so the reading is not certain."}
    return {**base, "certain": True, "exact_agreement": second_text == base["text"], "readings": readings,
            "reason": f"GLM-OCR and PaddleOCR-VL both read “{base['text']}”."}


def _second_opinion(prepared, kind: str, result: dict) -> dict:
    if result.get("confidence", 0) < thresholds()["wrong"]:
        return confirm(result, None, kind)
    if _dependencies_missing() or not files_ready(SECONDARY):
        return confirm(result, None, kind)
    if not _inference_lock.acquire(timeout=300):
        return confirm(result, None, kind)
    try:
        second = _read(SECONDARY, prepared, kind)
    except Exception:
        second = None
    finally:
        _inference_lock.release()
    return confirm(result, second, kind)


def recognize_image(image, kind: str, confirm_image=None) -> dict:
    """Read one isolated answer image (ink only, printing removed).

    A reliable result carries `confirm`: grading calls it only when the reading
    differs from the key. It runs the second model on `confirm_image` when given
    (for paper, the untouched photo of the same area, so a mark-isolation error
    cannot be repeated) and otherwise on the same image. Neither model ever
    receives the answer key.
    """
    if kind not in {"text", "number"}:
        return _result(reason="This answer type requires teacher review or a structured selection.")
    if _dependencies_missing() or not files_ready(PRIMARY):
        return _result(reason="Local handwriting recognition is not installed; a teacher will check this answer.")
    try:
        prepared = prepare(image)
        second_view = prepare(confirm_image) if confirm_image is not None else prepared
    except Exception:
        return _result(reason="The answer image could not be prepared; a teacher will check this answer.")
    if not _inference_lock.acquire(timeout=300):
        return _result(reason="The local handwriting models are busy; a teacher will check this answer.")
    try:
        result = assess(_read(PRIMARY, prepared, kind), kind)
    except Exception:
        failure = _failures.get(PRIMARY.name, ("",))[0]
        return _result(reason=failure or "Local recognition failed; a teacher will check this answer.")
    finally:
        _inference_lock.release()
    if result["reliable"]:
        result["confirm"] = lambda: _second_opinion(second_view, kind, result)
    return result


def recognize(strokes: list, kind: str, aspect_ratio: float = 3.0) -> dict:
    """Recognize isolated digital ink. Unsupported cases and errors are never reliable."""
    if kind not in {"text", "number"}:
        return _result(reason="This answer type requires teacher review or a structured selection.")
    try:
        ink = render_ink(strokes, aspect_ratio)
    except Exception:
        return _result(reason="The saved ink could not be rendered; a teacher will check this answer.")
    if ink is None:
        return _result(reason="There is too little ink to read; a teacher will check this answer.")
    return recognize_image(ink, kind)
