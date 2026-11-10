"""Validated data contracts for persistent terminal interviews."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from diagnostic_questions import DiagnosticQuestion


SCHEMA_VERSION = 1
SessionStatus = Literal["in_progress", "paused", "completed"]


class SourceSnapshot(BaseModel):
    """Immutable source text used to generate this interview."""

    resume: str = Field(min_length=1)
    job_description: str = Field(min_length=1)


class ModelConfigSnapshot(BaseModel):
    """Non-secret model settings needed to interpret a saved session."""

    provider: str
    model: str
    reasoning_effort: str
    max_retries: int = Field(ge=0)
    langsmith_tracing: bool


class SessionQuestion(DiagnosticQuestion):
    """A generated diagnostic question with a stable session-local ID."""

    question_id: str = Field(min_length=1)


class InterviewAnswer(BaseModel):
    """One committed answer for a session question."""

    question_id: str = Field(min_length=1)
    answer: str
    submitted_at: datetime

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value

    @field_validator("submitted_at")
    @classmethod
    def submitted_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("submitted_at must include a timezone")
        return value


class InterviewSession(BaseModel):
    """Versioned, self-contained interview record."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    session_id: str
    created_at: datetime
    updated_at: datetime
    status: SessionStatus
    source_snapshot: SourceSnapshot
    model_settings: ModelConfigSnapshot = Field(alias="model_config")
    prompt_version: str = Field(min_length=1)
    questions: list[SessionQuestion] = Field(min_length=3, max_length=3)
    answers: list[InterviewAnswer] = Field(default_factory=list, max_length=3)

    @field_validator("session_id")
    @classmethod
    def session_id_must_be_uuid(cls, value: str) -> str:
        try:
            return str(UUID(value))
        except (ValueError, AttributeError) as exc:
            raise ValueError("session_id must be a UUID") from exc

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_progress(self) -> "InterviewSession":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

        question_ids = [item.question_id for item in self.questions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("question_id values must be unique")

        answer_ids = [item.question_id for item in self.answers]
        if answer_ids != question_ids[: len(answer_ids)]:
            raise ValueError("answers must correspond to questions in order")

        all_answered = len(self.answers) == len(self.questions)
        if all_answered != (self.status == "completed"):
            raise ValueError("completed status must match whether all questions are answered")
        return self

    @property
    def next_question_index(self) -> int:
        return len(self.answers)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"
