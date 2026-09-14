"""Deterministic grading: recognizing an answer is separate from evaluating it."""
import re
import time
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction


def normalize_text(value, case_sensitive=False):
    text = " ".join(unicodedata.normalize("NFKC", str(value)).split())
    return text if case_sensitive else text.casefold()


def parse_number(value):
    """Parse a whole answer, never a substring or Python expression.

    Keep negative signs, decimals, and fractions meaningful. Thousands separators
    are allowed only in groups of three; units and OCR letter substitutions are not.
    """
    text = unicodedata.normalize("NFKC", str(value)).strip().replace("−", "-")
    if len(text) > 100:
        return None
    if re.fullmatch(r"[+-]?\d+\s*/\s*[+-]?\d+", text):
        numerator, denominator = text.split("/")
        try:
            return Fraction(int(numerator), int(denominator))
        except (ValueError, ZeroDivisionError):
            return None
    if "," in text:
        if not re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", text):
            return None
        text = text.replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return None
    try:
        return Fraction(Decimal(text))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def matches(question, answer):
    if question["kind"] == "number":
        actual = parse_number(answer)
        tolerance = Fraction(Decimal(str(question.get("tolerance", 0))))
        return actual is not None and any(
            expected is not None and abs(actual - expected) <= tolerance
            for expected in (parse_number(v) for v in question.get("expected", []))
        )
    if question["kind"] == "choice":
        return answer in question.get("expected", [])
    return normalize_text(answer, question.get("case_sensitive", False)) in {
        normalize_text(v, question.get("case_sensitive", False)) for v in question.get("expected", [])
    }


def _within_one_edit(first, second):
    """True when one insertion, deletion or substitution turns one string into the other."""
    if first == second:
        return True
    if abs(len(first) - len(second)) > 1:
        return False
    shorter, longer = sorted((first, second), key=len)
    index = 0
    while index < len(shorter) and shorter[index] == longer[index]:
        index += 1
    if len(shorter) == len(longer):
        return shorter[index + 1:] == longer[index + 1:]
    return shorter[index:] == longer[index + 1:]


def near_miss(question, text):
    """A reading too close to an accepted answer to justify an automatic zero.

    A difference only in spacing or punctuation ("17.8" for 178, "teddy-bear") is
    usually a stray mark. For words, one letter ("BEAK" for BEAR, "d" for b) is
    as likely a misread as a spelling mistake. A teacher decides these.
    """
    def compact(value):
        return re.sub(r"[\W_]+", "", normalize_text(value, question.get("case_sensitive", False)))

    reading = compact(text)
    if not reading:
        return False
    accepted = [compact(value) for value in question.get("expected", [])]
    if question["kind"] == "text":
        return any(_within_one_edit(reading, value) for value in accepted)
    return reading in accepted


def summarize(results):
    total = sum(Decimal(str(r["max_points"])) for r in results)
    earned = sum(Decimal(str(r["awarded"])) for r in results if r.get("awarded") is not None)
    pending = sum(r.get("awarded") is None for r in results)
    return {
        "earned": float(earned), "total": float(total), "pending": pending,
        "graded": len(results) - pending, "total_questions": len(results),
        "percentage": round(float(earned / total * 100), 2) if total and not pending else None,
        "final": pending == 0,
    }


def apply_reading(result, question, reading):
    """Turn a handwriting reading into a mark only when the evidence is sufficient."""
    text = (reading.get("text") or "").strip()
    result.update(recognized_text=text, confidence=reading.get("confidence"),
                  source=reading.get("source", result["source"]))
    if not reading.get("reliable") or not text:
        result["feedback"] = reading.get("reason") or "The writing could not be read confidently. A teacher will check it; this is not a wrong mark."
        return result
    if question["kind"] == "number" and parse_number(text) is None:
        result["feedback"] = f"The writing was read as “{text}”, which is not a clear number. A teacher will check it."
        return result
    if matches(question, text):
        result.update(awarded=question["points"], status="correct", feedback="Correct.")
        return result
    if near_miss(question, text):
        result["feedback"] = (f"Read as “{text}”, which differs from the answer key only by spacing or punctuation. "
                              "A teacher will check it.")
        return result
    decision = reading
    if not reading.get("certain") and callable(reading.get("confirm")):
        # Only a differing reading needs an independent second model. It reads the
        # same image; the answer key is still never given to recognition.
        try:
            decision = reading["confirm"]() or {}
        except Exception:
            decision = {"certain": False, "reason": "The second handwriting model could not check this answer."}
    exact_needed = question["kind"] == "text" and question.get("case_sensitive", False)
    if decision.get("certain") and (not exact_needed or decision.get("exact_agreement")):
        result.update(awarded=0, status="incorrect",
                      feedback=f"Read as “{text}” by two independent handwriting models. This does not match the answer key.")
        return result
    detail = decision.get("reason", "") if decision is not reading else ""
    result["feedback"] = " ".join(part for part in (
        f"Read as “{text}”, which differs from the answer key but is not certain enough to mark wrong.",
        detail, "A teacher will check it.") if part)
    return result


def _grade_paper(result, question, evidence, image_recognizer):
    kind, status = question["kind"], evidence.get("status")
    result["source"] = "paper"
    if status == "hidden":
        result["feedback"] = "This answer area was cut off, covered or out of view in the uploaded page. A teacher will check the paper."
    elif kind == "choice":
        choice = evidence.get("choice") or {}
        if choice.get("status") == "selected":
            correct = matches(question, choice["value"])
            result.update(recognized_text=choice["value"], source="paper-choice",
                          awarded=question["points"] if correct else 0,
                          status="correct" if correct else "incorrect",
                          feedback="Correct." if correct else "The marked option does not match the answer key.")
        elif choice.get("status") == "blank":
            result.update(awarded=0, status="incorrect", source="blank", feedback="No option was marked.")
        elif choice.get("status") == "ambiguous":
            result["feedback"] = "More than one option looks marked, or the mark is unclear. A teacher will check the paper."
        else:
            result["feedback"] = "This choice has no printed option positions to check, so a teacher will mark it."
    elif status == "blank":
        if kind == "manual":
            result["feedback"] = "No new marks were found in this area. A teacher will confirm the mark."
        else:
            result.update(awarded=0, status="incorrect", source="blank", feedback="No answer was written in this area.")
    elif kind == "manual":
        result["feedback"] = "Teacher review required for this drawing, tracing, or written response."
    elif not question.get("expected"):
        result["feedback"] = "Answer key missing; a teacher must review this question."
    elif status == "faint":
        result["feedback"] = "Only very light marks were found here. A teacher will check the paper."
    else:
        try:
            views = {"confirm_image": evidence["confirm_image"]} if evidence.get("confirm_image") is not None else {}
            reading = image_recognizer(image=evidence["image"], kind=kind, **views)
        except Exception:
            reading = {"text": "", "reliable": False, "reason": "Handwriting recognition could not complete. A teacher will check the paper."}
        apply_reading(result, question, reading)
        result["source"] = "paper"
    return result


def grade_answers(questions, answers, recognizer=None, image_recognizer=None, paper=None, budget_seconds=90):
    """Grade stored answers. `paper(question)` supplies printed-worksheet evidence instead of answers."""
    if recognizer is None or image_recognizer is None:
        from . import ocr
        recognizer = recognizer or ocr.recognize
        image_recognizer = image_recognizer or ocr.recognize_image
    results = []
    deadline = time.monotonic() + budget_seconds
    for question in questions:
        qid = question["id"]
        result = {
            "question_id": qid, "label": question["label"],
            "awarded": None, "max_points": question["points"],
            "status": "pending_review", "recognized_text": "",
            "feedback": "", "source": "typed", "confidence": None,
        }
        if paper is not None:
            needs_reading = question["kind"] in {"number", "text"}
            if needs_reading and time.monotonic() >= deadline:
                result.update(source="paper", feedback="The automatic marking time limit was reached. A teacher will check this answer on the paper.")
            else:
                try:
                    evidence = paper(question)
                except Exception:
                    evidence = {"status": "hidden"}
                _grade_paper(result, question, evidence, image_recognizer)
            results.append(result)
            continue
        answer = answers.get(qid, {})
        strokes = answer.get("strokes", [])
        text = answer.get("text", "").strip()
        result.update(recognized_text=text, source="handwriting" if strokes else "typed")
        if not text and not strokes:
            result.update(awarded=0, status="incorrect", feedback="No answer submitted.", source="blank")
        elif question["kind"] == "manual":
            result["feedback"] = "Teacher review required for this drawing, tracing, or written response."
        elif not question.get("expected"):
            result["feedback"] = "Answer key missing; a teacher must review this question."
        elif text and strokes:
            result["feedback"] = "Conflicting answer formats; a teacher must review."
        elif strokes:
            if time.monotonic() >= deadline:
                result["feedback"] = "The automatic marking time limit was reached. Saved handwriting awaits teacher review."
            else:
                try:
                    region = question["rect"]
                    aspect = region["w"] / region["h"] * question.get("_page_aspect", 612 / 792)
                    reading = recognizer(strokes=strokes, kind=question["kind"], aspect_ratio=aspect)
                except Exception:
                    reading = {"text": "", "reliable": False, "reason": "Handwriting recognition could not complete."}
                apply_reading(result, question, reading)
        else:
            if question["kind"] == "choice":
                result["source"] = "choice"
            correct = matches(question, text)
            result.update(
                awarded=question["points"] if correct else 0,
                status="correct" if correct else "incorrect",
                feedback="Correct." if correct else "This answer does not match the approved answer key.",
            )
        results.append(result)
    return {"results": results, "summary": summarize(results)}
