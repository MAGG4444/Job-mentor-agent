"""Business logic and question-provider adapters for terminal interviews."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from _config import build_model
from diagnostic_questions import (
    DiagnosticQuestionSet,
    PROMPT_VERSION,
    generate_diagnostic_questions,
    validate_resume_evidence,
)
from interview_models import (
    InterviewAnswer,
    InterviewSession,
    ModelConfigSnapshot,
    SessionQuestion,
    SourceSnapshot,
)


Clock = Callable[[], datetime]
SessionIdFactory = Callable[[], str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class QuestionGeneration:
    questions: DiagnosticQuestionSet
    model_config: ModelConfigSnapshot
    messages: list[object]


class QuestionProvider(Protocol):
    def generate(self, resume: str, job_description: str) -> QuestionGeneration:
        """Generate the validated question set for a new session."""


class OpenAIQuestionProvider:
    """Production provider that reuses the existing LangChain question generator."""

    def generate(self, resume: str, job_description: str) -> QuestionGeneration:
        model = build_model()
        questions, messages = generate_diagnostic_questions(
            model,
            resume,
            job_description,
        )
        return QuestionGeneration(
            questions=questions,
            model_config=ModelConfigSnapshot(
                provider="openai",
                model=model.model_name,
                reasoning_effort=model.reasoning_effort or "medium",
                max_retries=model.max_retries,
                langsmith_tracing=False,
            ),
            messages=messages,
        )


class EmptyAnswerError(ValueError):
    """Raised when an answer contains only whitespace."""


class CompletedSessionError(RuntimeError):
    """Raised when code attempts to answer an already completed session."""


def create_session(
    resume: str,
    job_description: str,
    generation: QuestionGeneration,
    *,
    clock: Clock = utc_now,
    session_id_factory: SessionIdFactory = lambda: str(uuid4()),
) -> InterviewSession:
    """Create a new validated session without performing storage I/O."""
    validate_resume_evidence(generation.questions, resume)
    timestamp = clock()
    questions = [
        SessionQuestion(question_id=f"q{index}", **question.model_dump())
        for index, question in enumerate(generation.questions.questions, start=1)
    ]
    return InterviewSession(
        session_id=session_id_factory(),
        created_at=timestamp,
        updated_at=timestamp,
        status="in_progress",
        source_snapshot=SourceSnapshot(
            resume=resume,
            job_description=job_description,
        ),
        model_config=generation.model_config,
        prompt_version=PROMPT_VERSION,
        questions=questions,
        answers=[],
    )


def submit_answer(
    session: InterviewSession,
    answer: str,
    *,
    clock: Clock = utc_now,
) -> InterviewSession:
    """Return a new session with one answer committed in memory."""
    if session.is_completed:
        raise CompletedSessionError("the interview is already completed")
    if not answer.strip():
        raise EmptyAnswerError("answer cannot be blank")

    timestamp = clock()
    question = session.questions[session.next_question_index]
    answers = [*session.answers, InterviewAnswer(
        question_id=question.question_id,
        answer=answer,
        submitted_at=timestamp,
    )]
    status = "completed" if len(answers) == len(session.questions) else "in_progress"
    data = session.model_dump(mode="python", by_alias=True)
    data.update(updated_at=timestamp, status=status, answers=answers)
    return InterviewSession.model_validate(data)


def pause_session(
    session: InterviewSession,
    *,
    clock: Clock = utc_now,
) -> InterviewSession:
    """Return a paused copy, leaving completed sessions unchanged."""
    if session.is_completed:
        return session
    data = session.model_dump(mode="python", by_alias=True)
    data.update(updated_at=clock(), status="paused")
    return InterviewSession.model_validate(data)
