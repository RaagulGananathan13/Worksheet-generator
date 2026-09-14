"""Validated boundary types. Coordinates refer to the actual PDF page, not CSS pixels."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Rect(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def within_page(self):
        if self.x + self.w > 1.000001 or self.y + self.h > 1.000001:
            raise ValueError("Answer region must fit inside its page.")
        return self


class Option(StrictModel):
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    rect: Rect | None = None


class Question(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=0, le=9)
    rect: Rect
    kind: Literal["number", "text", "choice", "manual"] = "number"
    expected: list[str] = Field(default_factory=list, max_length=30)
    points: float = Field(default=1, gt=0, le=100)
    tolerance: float = Field(default=0, ge=0, le=100)
    case_sensitive: bool = False
    options: list[Option] = Field(default_factory=list, max_length=30)

    @field_validator("expected")
    @classmethod
    def expected_limits(cls, values):
        if any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in values):
            raise ValueError("Accepted answers must be nonempty text of at most 1000 characters.")
        return [v.strip() for v in values]

    @model_validator(mode="after")
    def options_unique(self):
        values = [o.value for o in self.options]
        if len(set(values)) != len(values):
            raise ValueError("Choice option values must be unique.")
        if self.kind == "choice" and self.expected and any(v not in values for v in self.expected):
            raise ValueError("Correct choices must be included in the option list.")
        return self


class WorksheetUpdate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    questions: list[Question] = Field(max_length=100)
    published: bool = False
    keys_confirmed: bool = False
    revision: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_questions(self):
        if not self.title.strip():
            raise ValueError("A worksheet needs a title.")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Question IDs must be unique.")
        if self.published:
            if not self.keys_confirmed or not self.questions:
                raise ValueError("Review the answer key and confirm it before publishing.")
            from .grading import parse_number
            for q in self.questions:
                if q.kind != "manual" and not q.expected:
                    raise ValueError(f"{q.label}: add at least one accepted answer.")
                if q.kind == "number" and any(parse_number(v) is None for v in q.expected):
                    raise ValueError(f"{q.label}: numeric keys must be a number, decimal or fraction.")
                if q.kind == "choice" and len(q.options) < 2:
                    raise ValueError(f"{q.label}: add at least two choices.")
        return self


class Point(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    p: float = Field(default=0.5, ge=0, le=1)


class Stroke(StrictModel):
    points: list[Point] = Field(min_length=1, max_length=4000)
    width: float = Field(default=0.009, ge=0.001, le=0.1)


class Answer(StrictModel):
    text: str = Field(default="", max_length=2000)
    strokes: list[Stroke] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def one_modality(self):
        if self.text.strip() and self.strokes:
            raise ValueError("Use either handwriting or text for an answer, not both.")
        if sum(len(s.points) for s in self.strokes) > 20000:
            raise ValueError("This answer contains too many handwriting points.")
        return self


class AnswersUpdate(StrictModel):
    version: int = Field(ge=1)
    answers: dict[str, Answer]

    @model_validator(mode="after")
    def bounded_payload(self):
        if len(self.answers) > 100:
            raise ValueError("Too many answers.")
        if sum(len(s.points) for a in self.answers.values() for s in a.strokes) > 150000:
            raise ValueError("Worksheet contains too many ink points; simplify handwriting before saving.")
        return self


class Review(StrictModel):
    question_id: str = Field(min_length=1, max_length=80)
    awarded: float = Field(ge=0, le=100)
    feedback: str = Field(default="", max_length=2000)
    recognized_text: str | None = Field(default=None, max_length=2000)


class ReviewUpdate(StrictModel):
    version: int = Field(ge=1)
    reviews: list[Review] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_reviews(self):
        if len({r.question_id for r in self.reviews}) != len(self.reviews):
            raise ValueError("Review each question only once per request.")
        return self
