"""The handwriting evaluation tool must count unsafe outcomes separately from review."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.evaluate_handwriting import classify, summarize, wrong_key


class EvaluationToolTests(unittest.TestCase):
    def test_outcomes_separate_automatic_review_and_unsafe_marks(self):
        self.assertEqual(classify(True, "correct"), "auto-correct")
        self.assertEqual(classify(True, "pending_review"), "review")
        self.assertEqual(classify(True, "incorrect"), "UNSAFE right marked wrong")
        self.assertEqual(classify(False, "incorrect"), "auto-wrong")
        self.assertEqual(classify(False, "pending_review"), "review")
        self.assertEqual(classify(False, "correct"), "UNSAFE wrong marked right")

    def test_wrong_keys_really_differ_from_the_label(self):
        self.assertEqual(wrong_key("384", "number"), "385")
        self.assertEqual(wrong_key("1/2", "number"), "3/2")
        self.assertEqual(wrong_key("year", "text"), "zebra")
        self.assertEqual(wrong_key("Zebra", "text"), "apple")

    def test_summary_counts_unsafe_marks_per_source(self):
        rows = [
            {"source": "a", "exact_read": True, "right_key": "auto-correct", "wrong_key": "auto-wrong", "seconds": 2},
            {"source": "a", "exact_read": False, "right_key": "UNSAFE right marked wrong", "wrong_key": "review", "seconds": 4},
            {"source": "b", "exact_read": True, "right_key": "review", "wrong_key": "UNSAFE wrong marked right", "seconds": 1},
        ]
        summary = summarize(rows)
        self.assertEqual(summary["a"]["unsafe"], 1)
        self.assertEqual(summary["a"]["exact_first_reading"], 1)
        self.assertEqual(summary["b"]["unsafe"], 1)
        self.assertEqual(summary["b"]["student_right"], {"review": 1})


if __name__ == "__main__":
    unittest.main()
