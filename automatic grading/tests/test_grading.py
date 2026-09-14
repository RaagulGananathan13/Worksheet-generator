import copy
from fractions import Fraction
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from app.grading import grade_answers, matches, parse_number, summarize
from app.schemas import Answer, Question, WorksheetUpdate
from app.samples import PRESETS, HASHES, load_sample, preset_for_content


def q(kind="number", expected=None):
    return {"id":"q1", "label":"One", "page":0, "rect":{"x":.1,"y":.2,"w":.3,"h":.1},
            "kind":kind,"points":2,"expected":expected or ["2"],"tolerance":0,"options":[]}


INK = [{"points":[{"x":.1,"y":.1,"p":.5},{"x":.8,"y":.8,"p":.5}],"width":.009}]


class GradingTests(unittest.TestCase):
    def test_whole_numeric_answers_only(self):
        self.assertTrue(matches(q(),"2.0"))
        for answer in ["12","-2","2 apples","x2","2+0","2e0","2,0","two","__import__('os')"]:
            with self.subTest(answer=answer):
                self.assertFalse(matches(q(),answer))
        self.assertEqual(parse_number("−2.5"),Fraction(-5,2))
        self.assertEqual(parse_number("1,234.50"),Fraction(2469,2))
        self.assertEqual(parse_number("1 / 2"),Fraction(1,2))
        self.assertIsNone(parse_number("1/0"))
        self.assertIsNone(parse_number("NaN"))
        self.assertIsNone(parse_number("Infinity"))

    def test_tolerance_and_text(self):
        numeric=q(); numeric["tolerance"]=.01
        self.assertTrue(matches(numeric,"2.01"))
        self.assertFalse(matches(numeric,"2.011"))
        self.assertTrue(matches(q("text",["The Sun"]),"  THE   sun "))
        self.assertFalse(matches(q("text",["The Sun"]),"not the sun"))
        self.assertFalse(matches(q("choice"),"12"))

    def test_missing_ocr_is_pending_not_wrong(self):
        result=grade_answers([q()],{"q1":{"strokes":INK}},recognizer=Mock(side_effect=RuntimeError("offline")))
        self.assertIsNone(result["results"][0]["awarded"])
        self.assertIsNone(result["summary"]["percentage"])
        self.assertFalse(result["summary"]["final"])

    def test_recognition_cannot_see_key(self):
        recognizer=Mock(return_value={"text":"2","reliable":True,"confidence":.999})
        result=grade_answers([q()],{"q1":{"strokes":INK}},recognizer)
        self.assertEqual(result["summary"]["earned"],2)
        self.assertEqual(set(recognizer.call_args.kwargs),{"strokes","kind","aspect_ratio"})
        self.assertNotIn("expected",recognizer.call_args.kwargs)

    def test_total_ocr_budget_leaves_remaining_answers_pending(self):
        recognizer=Mock()
        with patch("app.grading.time.monotonic",side_effect=[0,91]):
            result=grade_answers([q()],{"q1":{"strokes":INK}},recognizer)
        recognizer.assert_not_called()
        self.assertIsNone(result["results"][0]["awarded"])

    def test_handwritten_mismatch_or_low_confidence_requires_review(self):
        for text,reliable in [("12",True),("2",False),("",True),("two",True)]:
            result=grade_answers([q()],{"q1":{"strokes":INK}},lambda **kwargs:{"text":text,"reliable":reliable})
            self.assertIsNone(result["results"][0]["awarded"])

    def test_manual_never_auto_graded_and_blank_zero(self):
        recognizer=Mock(side_effect=AssertionError("must not OCR tracing"))
        manual=grade_answers([q("manual")],{"q1":{"strokes":INK}},recognizer)
        self.assertEqual(manual["summary"]["pending"],1)
        blank=grade_answers([q()],{},recognizer)
        self.assertEqual(blank["summary"]["earned"],0)
        self.assertTrue(blank["summary"]["final"])
        recognizer.assert_not_called()

    def test_fractional_mark_totals(self):
        result=summarize([{"max_points":.1,"awarded":.1},{"max_points":.2,"awarded":.2}])
        self.assertEqual(result["earned"],.3)
        self.assertEqual(result["percentage"],100)

    def test_schema_rejects_unsafe_or_mixed_inputs(self):
        for value in [float("nan"),-1,1.1]:
            invalid=q();invalid["rect"]["x"]=value
            with self.assertRaises(ValidationError): Question(**invalid)
        with self.assertRaises(ValidationError): Answer(text="2",strokes=INK)
        with self.assertRaises(ValidationError):
            WorksheetUpdate(title="Example",questions=[q()],published=True,keys_confirmed=False,revision=1)


def reading(text, **flags):
    return {"text": text, "confidence": .99, "source": "test", **flags}


class HandwritingDecisionTests(unittest.TestCase):
    def grade(self, question, result):
        return grade_answers([question], {"q1": {"strokes": INK}}, lambda **kwargs: result)["results"][0]

    def test_certain_mismatch_is_marked_wrong_and_final(self):
        marked = grade_answers([q()], {"q1": {"strokes": INK}}, lambda **kwargs: reading("7", reliable=True, certain=True))
        self.assertEqual((marked["results"][0]["awarded"], marked["results"][0]["status"]), (0, "incorrect"))
        self.assertEqual(marked["results"][0]["recognized_text"], "7")
        self.assertTrue(marked["summary"]["final"])

    def test_uncertain_or_near_miss_mismatch_waits_for_teacher(self):
        near = q(expected=["178"])
        for question, result in ((q(), reading("7", reliable=True, certain=False)),
                                 (near, reading("17.8", reliable=True, certain=True)),
                                 (q("text", ["teddy bear"]), reading("teddy-bear", reliable=True, certain=True))):
            with self.subTest(result=result):
                graded = self.grade(question, result)
                self.assertIsNone(graded["awarded"])
                self.assertEqual(graded["status"], "pending_review")

    def test_second_opinion_is_requested_only_for_a_differing_reading(self):
        confirm = Mock(return_value={"certain": True, "exact_agreement": True, "reason": "Both read 7."})
        wrong = self.grade(q(), reading("7", reliable=True, confirm=confirm))
        self.assertEqual((wrong["awarded"], wrong["status"]), (0, "incorrect"))
        confirm.assert_called_once_with()
        for text in ("2", "2.0"):
            unused = Mock(side_effect=AssertionError("a matching reading needs no second opinion"))
            self.assertEqual(self.grade(q(), reading(text, reliable=True, confirm=unused))["awarded"], 2)
        unused = Mock(side_effect=AssertionError("a near miss is never confirmed as wrong"))
        self.assertIsNone(self.grade(q(expected=["178"]), reading("17.8", reliable=True, confirm=unused))["awarded"])
        disputed = self.grade(q(), reading("7", reliable=True, confirm=lambda: {"certain": False, "reason": "The second model read 1."}))
        self.assertIsNone(disputed["awarded"])
        self.assertIn("The second model read 1.", disputed["feedback"])
        failed = self.grade(q(), reading("7", reliable=True, confirm=Mock(side_effect=RuntimeError("model crashed"))))
        self.assertIsNone(failed["awarded"])
        unreliable = Mock(side_effect=AssertionError("an unreliable reading is never confirmed"))
        self.assertIsNone(self.grade(q(), reading("7", reliable=False, confirm=unreliable))["awarded"])

    def test_one_letter_from_an_accepted_word_is_never_an_automatic_zero(self):
        for key, text in (("teddy bear", "TEDDY BEAK"), ("b", "d"), ("scooter", "scoter"), ("round", "rounds")):
            with self.subTest(key=key, text=text):
                graded = self.grade(q("text", [key]), reading(text, reliable=True, certain=True))
                self.assertIsNone(graded["awarded"])
        self.assertEqual(self.grade(q("text", ["cat"]), reading("dog", reliable=True, certain=True))["awarded"], 0)
        # Numbers keep the strict rule: 13 for 14 is a real wrong answer when both models agree.
        self.assertEqual(self.grade(q(expected=["14"]), reading("13", reliable=True, certain=True))["awarded"], 0)

    def test_paper_second_opinion_uses_the_untouched_photo(self):
        reader = Mock(return_value=reading("7", reliable=False))
        grade_answers([q()], {}, image_recognizer=reader, recognizer=Mock(),
                      paper=lambda _question: {"status": "ink", "image": "MARKS", "confirm_image": "PHOTO"})
        reader.assert_called_once_with(image="MARKS", kind="number", confirm_image="PHOTO")

    def test_case_sensitive_zero_needs_exact_agreement(self):
        question = {**q("text", ["Cat"]), "case_sensitive": True}
        self.assertIsNone(self.grade(question, reading("Dog", reliable=True, certain=True, exact_agreement=False))["awarded"])
        self.assertEqual(self.grade(question, reading("Dog", reliable=True, certain=True, exact_agreement=True))["awarded"], 0)
        # A capital-letter difference is one letter: handwritten c/C look alike, so a teacher decides.
        self.assertIsNone(self.grade(question, reading("cat", reliable=True, certain=True, exact_agreement=True))["awarded"])
        self.assertEqual(self.grade(question, reading("Cat", reliable=True, certain=False))["awarded"], 2)

    def test_paper_evidence_rules(self):
        image_reader = Mock(return_value=reading("2", reliable=True, certain=True))
        choice = {**q("choice", ["b"]), "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]}
        cases = [
            (q(), {"status": "hidden"}, None), (q(), {"status": "blank"}, 0), (q("manual"), {"status": "blank"}, None),
            (q("manual"), {"status": "ink"}, None), (q(), {"status": "faint"}, None), (q(), {"status": "ink", "image": "IMAGE"}, 2),
            (choice, {"status": "ink", "choice": {"status": "selected", "value": "b"}}, 2),
            (choice, {"status": "ink", "choice": {"status": "selected", "value": "a"}}, 0),
            (choice, {"status": "ink", "choice": {"status": "blank"}}, 0),
            (choice, {"status": "ink", "choice": {"status": "ambiguous"}}, None),
            (choice, {"status": "hidden"}, None),
        ]
        online_reader = Mock(side_effect=AssertionError("paper grading must not read online ink"))
        for question, evidence, awarded in cases:
            with self.subTest(kind=question["kind"], evidence=evidence):
                result = grade_answers([question], {"q1": {"strokes": INK}}, recognizer=online_reader,
                                       image_recognizer=image_reader, paper=lambda _question, value=evidence: value)
                self.assertEqual(result["results"][0]["awarded"], awarded)
        image_reader.assert_called_once_with(image="IMAGE", kind="number")
        failing = grade_answers([q()], {}, recognizer=online_reader, image_recognizer=image_reader,
                                paper=Mock(side_effect=OSError("missing page")))
        self.assertIsNone(failing["results"][0]["awarded"])


class SampleTests(unittest.TestCase):
    def test_all_presets_validate_and_keys_score(self):
        counts=[11,20,15,16,10,10]
        self.assertEqual([len(p["questions"]) for p in PRESETS.values()],counts)
        for name,preset in PRESETS.items():
            with self.subTest(name=name):
                WorksheetUpdate(title=preset["title"],questions=preset["questions"],published=True,keys_confirmed=True,revision=1)
                auto=[item for item in preset["questions"] if item["kind"]!="manual"]
                answers={item["id"]:{"text":item["expected"][0]} for item in auto}
                result=grade_answers(auto,answers)
                self.assertEqual(result["summary"]["percentage"],100)

    def test_hash_binding_and_path_traversal(self):
        for name in HASHES:
            content,preset=load_sample(name)
            self.assertEqual(preset_for_content(content)["title"],preset["title"])
        self.assertIsNone(preset_for_content(b"different PDF"))
        with self.assertRaises(ValueError):load_sample("../OCR/.env")


if __name__ == "__main__":
    unittest.main()
