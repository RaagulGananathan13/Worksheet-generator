"""Local OCR rendering, decision and readiness checks; no weights, Hub connection or inference."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from app import ocr


class InkRenderingTests(unittest.TestCase):
    def test_empty_and_single_point_strokes_are_not_readable_answers(self):
        self.assertIsNone(ocr.render_ink([]))
        self.assertIsNone(ocr.render_ink([{"width": 0.005, "points": [{"x": .5, "y": .5, "p": .5}]}]))

    def test_only_saved_ink_is_drawn_and_output_is_bounded(self):
        stroke = {"width": .008, "points": [{"x": .1, "y": .2, "p": .5}, {"x": .8, "y": .8, "p": .5}]}
        image = ocr.render_ink([stroke], aspect_ratio=300)
        self.assertLessEqual(image.width, 2048)
        self.assertLessEqual(image.height, 256)
        self.assertEqual(image.mode, "L")
        self.assertEqual(image.getextrema()[0], 0)
        self.assertGreater(image.getextrema()[1], 240)

    def test_out_of_bounds_nan_and_oversized_strokes_are_rejected(self):
        for x in (-.01, 1.01, float("nan"), float("inf")):
            with self.subTest(x=x), self.assertRaises(ValueError):
                ocr.render_ink([{"width": .008, "points": [{"x": x, "y": .5}]}])
        with self.assertRaises(ValueError):
            ocr.render_ink([{"points": []}] * 601)
        with self.assertRaises(ValueError):
            ocr.render_ink([{"width": -1, "points": []}])
        with self.assertRaises(ValueError):
            ocr.render_ink([], aspect_ratio=float("nan"))

    def test_mouse_ink_thickness_matches_browser_pressure_formula(self):
        stroke = {"width": .04, "points": [{"x": .2, "y": .5, "p": .5}, {"x": .8, "y": .5, "p": .5}]}
        image = ocr.render_ink([stroke], aspect_ratio=3)
        self.assertGreaterEqual(image.height, 21)
        self.assertLessEqual(image.height, 24)

    def test_segment_pressure_uses_both_endpoints_like_browser(self):
        varying = {"width": .04, "points": [{"x": .2, "y": .5, "p": .1}, {"x": .8, "y": .5, "p": .9}]}
        constant = copy.deepcopy(varying)
        for point in constant["points"]:
            point["p"] = .5
        self.assertEqual(ocr.render_ink([varying]).tobytes(), ocr.render_ink([constant]).tobytes())

    def test_single_point_marks_are_preserved_beside_other_ink(self):
        line = {"width": .01, "points": [{"x": .2, "y": .2, "p": .5}, {"x": .2, "y": .8, "p": .5}]}
        dot = {"width": .01, "points": [{"x": .7, "y": .8, "p": .5}]}
        strokes = [dot, line]
        original = copy.deepcopy(strokes)
        self.assertGreater(ocr.render_ink(strokes).width, ocr.render_ink([line]).width * 5)
        self.assertEqual(strokes, original)

    def test_prepare_adds_margin_and_readable_height_without_changing_ink(self):
        image = Image.new("L", (40, 20), 255)
        image.paste(0, (10, 5, 30, 15))
        prepared = ocr.prepare(image)
        self.assertEqual(prepared.mode, "RGB")
        self.assertGreaterEqual(prepared.height, 96)
        self.assertEqual(prepared.getpixel((0, 0)), (255, 255, 255))


def reading(text, confidence=.99, completed=True, engine="glm-ocr"):
    return {"engine": engine, "text": text, "confidence": confidence, "completed": completed}


class RecognitionGateTests(unittest.TestCase):
    def test_a_complete_confident_well_formed_reading_can_count_but_is_never_certain_alone(self):
        result = ocr.assess(reading("384"), "number")
        self.assertTrue(result["reliable"])
        self.assertFalse(result["certain"])
        self.assertEqual(result["text"], "384")

    def test_first_reading_must_be_complete_well_formed_and_confident(self):
        cases = [
            (reading("3", completed=False), "number"), (reading("3", .5), "number"), (reading(""), "number"),
            (reading("3 + 4"), "number"), (reading("1 2 1"), "number"), (reading("අ"), "text"),
            (reading("3", float("nan")), "number"), (reading("3", 1.5), "number"),
        ]
        for first, kind in cases:
            with self.subTest(first=first):
                self.assertFalse(ocr.assess(first, kind)["reliable"])
        self.assertIn("not a wrong mark", ocr.assess(reading("3", .5), "number")["reason"])

    def test_independent_exact_agreement_makes_a_confident_reading_certain(self):
        first = ocr.assess(reading("384"), "number")
        result = ocr.confirm(first, reading("384", .8, engine="paddleocr-vl-1.5"), "number")
        self.assertFalse(ocr.confirm(first, reading("384", .7, engine="paddleocr-vl-1.5"), "number")["certain"])
        self.assertTrue(result["certain"])
        self.assertTrue(result["exact_agreement"])
        self.assertEqual(len(result["readings"]), 2)
        self.assertNotIn("confirm", result)
        forms = ocr.confirm(ocr.assess(reading("2.0"), "number"), reading("2"), "number")
        self.assertTrue(forms["certain"])
        self.assertFalse(forms["exact_agreement"])
        case = ocr.confirm(ocr.assess(reading("Cat"), "text"), reading("cat"), "text")
        self.assertTrue(case["certain"])
        self.assertFalse(case["exact_agreement"])

    def test_disagreement_weak_second_reading_or_unconfident_first_is_not_certain(self):
        first = ocr.assess(reading("1"), "number")
        for second in (reading("7"), reading("1", .4), reading("1", completed=False), reading("1?"), None):
            with self.subTest(second=second):
                self.assertFalse(ocr.confirm(first, second, "number")["certain"])
        self.assertIn("read this as “7”", ocr.confirm(first, reading("7"), "number")["reason"])
        self.assertFalse(ocr.confirm(ocr.assess(reading("1", .93), "number"), reading("1"), "number")["certain"])
        self.assertFalse(ocr.confirm(ocr.assess(reading("1", .5), "number"), reading("1"), "number")["certain"])

    def test_thresholds_cannot_be_disabled_by_environment(self):
        settings = {"OCR_MIN_CONFIDENCE": None, "OCR_CERTAIN_CONFIDENCE": None, "OCR_CONFIRM_CONFIDENCE": None}
        for value in ("0", "-1", "nan", "invalid"):
            with self.subTest(value=value), patch.dict(os.environ, {key: value for key in settings}):
                self.assertFalse(ocr.assess(reading("384", .7), "number")["reliable"])
                # The wrong-mark floor can be configured, but never below 0.90.
                self.assertFalse(ocr.confirm(ocr.assess(reading("384", .89), "number"), reading("384"), "number")["certain"])
                self.assertFalse(ocr.confirm(ocr.assess(reading("384"), "number"), reading("384", .4), "number")["certain"])

    def test_cleaning_removes_formatting_but_keeps_written_symbols(self):
        self.assertEqual(ocr.clean("```markdown\n\n```"), "")
        self.assertEqual(ocr.clean("$3.5$"), "3.5")
        self.assertEqual(ocr.clean("\\(1/2\\)"), "1/2")
        self.assertEqual(ocr.clean("  2 −1 \n"), "2 -1")
        self.assertEqual(ocr.clean("17.8"), "17.8")
        self.assertTrue(ocr.well_formed("teddy bear", "text"))
        self.assertTrue(ocr.well_formed("don't", "text"))
        self.assertFalse(ocr.well_formed("3 4", "number"))
        self.assertTrue(ocr.well_formed("-3.5", "number"))


class OfflineReadinessTests(unittest.TestCase):
    def install_fake(self, folder, engine, revision=None, weights=None):
        folder.mkdir(parents=True, exist_ok=True)
        for name in engine.files:
            (folder / name).write_text("placeholder", encoding="utf-8")
        hashes = {name: "0" * 64 for name in engine.files}
        hashes[engine.weights] = weights or engine.weights_sha256
        (folder / "verified-model.json").write_text(json.dumps({
            "model": engine.repo, "revision": revision or engine.revision, "sha256": hashes,
        }), encoding="utf-8")

    def test_status_is_cheap_and_reports_missing_models(self):
        with tempfile.TemporaryDirectory(dir=ocr.ROOT) as temporary, patch.dict(os.environ, {"OCR_MODEL_PATH": temporary}):
            with patch.object(ocr, "_load", side_effect=AssertionError("status must not load models")):
                result = ocr.status()
        self.assertFalse(result["available"])
        self.assertFalse(result["configured"])
        self.assertFalse(result["cross_check"])
        self.assertIn("not installed", result["message"])

    def test_manifest_must_match_pinned_revision_and_weights(self):
        with tempfile.TemporaryDirectory(dir=ocr.ROOT) as temporary:
            folder = Path(temporary) / "engine"
            self.install_fake(folder, ocr.PRIMARY, revision="main")
            self.assertFalse(ocr.files_ready(ocr.PRIMARY, folder))
            self.install_fake(folder, ocr.PRIMARY, weights="1" * 64)
            self.assertFalse(ocr.files_ready(ocr.PRIMARY, folder))
            self.install_fake(folder, ocr.PRIMARY)
            self.assertTrue(ocr.files_ready(ocr.PRIMARY, folder))
            (folder / "tokenizer.json").unlink()
            self.assertFalse(ocr.files_ready(ocr.PRIMARY, folder))

    def test_status_reports_single_model_mode_honestly(self):
        # Independent of whether the optional OCR packages are installed on this computer.
        with tempfile.TemporaryDirectory(dir=ocr.ROOT) as temporary, patch.dict(os.environ, {"OCR_MODEL_PATH": temporary}), \
                patch.object(ocr, "_dependencies_missing", return_value=[]):
            self.install_fake(Path(temporary) / ocr.PRIMARY.name, ocr.PRIMARY)
            result = ocr.status()
        self.assertTrue(result["configured"])
        self.assertFalse(result["cross_check"])
        self.assertIn("nothing is marked wrong automatically", result["message"])

    def test_tampered_files_fail_integrity_before_loading(self):
        with tempfile.TemporaryDirectory(dir=ocr.ROOT) as temporary:
            folder = Path(temporary) / "engine"
            self.install_fake(folder, ocr.PRIMARY)
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                ocr._verify_files(ocr.PRIMARY, folder)

    def test_runtime_enforces_offline_local_cache_and_no_implicit_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            ocr._environment()
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")
            self.assertEqual(os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"], "1")
            self.assertTrue(Path(os.environ["HF_HOME"]).is_relative_to(ocr.ROOT))

    def test_missing_models_manual_and_bad_ink_never_load_a_model(self):
        with patch.object(ocr, "_load", side_effect=AssertionError("must not load")), \
                patch.object(ocr, "files_ready", return_value=False):
            self.assertFalse(ocr.recognize_image(Image.new("L", (50, 50), 255), "number")["reliable"])
            self.assertFalse(ocr.recognize([], "manual")["reliable"])
            self.assertFalse(ocr.recognize([], "number")["reliable"])
            self.assertFalse(ocr.recognize([{"points": [{"x": 2, "y": 2}]}], "number")["reliable"])
            self.assertFalse(ocr.recognize_image(Image.new("L", (50, 50), 255), "choice")["reliable"])

    def test_inference_failure_returns_review_and_releases_lock(self):
        with patch.object(ocr, "files_ready", return_value=True), patch.object(ocr, "_dependencies_missing", return_value=[]), \
                patch.object(ocr, "_read", side_effect=RuntimeError("broken local dependency")):
            result = ocr.recognize_image(Image.new("L", (80, 40), 255), "number")
        self.assertFalse(result["reliable"])
        self.assertIn("teacher", result["reason"])
        self.assertFalse(ocr._inference_lock.locked())

    def test_second_model_reads_only_when_grading_asks_to_confirm(self):
        image = Image.new("L", (80, 40), 255)
        with patch.object(ocr, "files_ready", return_value=True), patch.object(ocr, "_dependencies_missing", return_value=[]):
            with patch.object(ocr, "_read", side_effect=[reading("?", .4)]) as read:
                weak = ocr.recognize_image(image, "number")
            self.assertFalse(weak["reliable"])
            self.assertNotIn("confirm", weak)
            self.assertEqual(read.call_count, 1)
            with patch.object(ocr, "_read", side_effect=[reading("12"), reading("12", .8, engine="second")]) as read:
                result = ocr.recognize_image(image, "number")
                self.assertEqual(read.call_count, 1)
                self.assertFalse(result["certain"])
                confirmed = result["confirm"]()
            self.assertEqual(read.call_count, 2)
            self.assertEqual([call.args[0] for call in read.call_args_list], [ocr.PRIMARY, ocr.SECONDARY])
            self.assertIs(read.call_args_list[0].args[1], read.call_args_list[1].args[1])
            self.assertEqual([call.args[2] for call in read.call_args_list], ["number", "number"])
            self.assertTrue(confirmed["certain"])
            self.assertFalse(ocr._inference_lock.locked())

    def test_confirmation_without_second_model_is_never_certain(self):
        image = Image.new("L", (80, 40), 255)
        ready = lambda engine, path=None: engine is ocr.PRIMARY
        with patch.object(ocr, "files_ready", side_effect=ready), patch.object(ocr, "_dependencies_missing", return_value=[]), \
                patch.object(ocr, "_read", side_effect=[reading("12")]) as read:
            confirmed = ocr.recognize_image(image, "number")["confirm"]()
        self.assertEqual(read.call_count, 1)
        self.assertFalse(confirmed["certain"])
        self.assertIn("not available", confirmed["reason"])


if __name__ == "__main__":
    unittest.main()
