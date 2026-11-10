"""Terminal interaction orchestration for saved interview sessions."""

from __future__ import annotations

from collections.abc import Callable

from _config import ConfigurationError
from diagnostic_questions import print_usage, read_fixture
from interview_models import InterviewSession
from interview_service import (
    CompletedSessionError,
    EmptyAnswerError,
    OpenAIQuestionProvider,
    QuestionProvider,
    create_session,
    pause_session,
    submit_answer,
)
from interview_storage import (
    CorruptSessionError,
    InterviewStorage,
    InterviewStorageError,
    InvalidSessionIdError,
    SessionNotFoundError,
    SessionSaveError,
    UnsupportedSchemaVersionError,
)


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def recovery_command(session_id: str) -> str:
    return (
        ".\\.venv\\Scripts\\python.exe "
        f".\\examples\\interview_session.py --resume '{session_id}'"
    )


def print_recovery(session: InterviewSession, output_fn: OutputFunction) -> None:
    output_fn(f"Session ID: {session.session_id}")
    output_fn(f"Resume with: {recovery_command(session.session_id)}")


def pause_and_report(
    session: InterviewSession,
    storage: InterviewStorage,
    output_fn: OutputFunction,
) -> InterviewSession:
    """Pause safely; a failed save leaves the previously committed record intact."""
    paused = pause_session(session)
    try:
        path = storage.save(paused)
    except SessionSaveError as exc:
        output_fn(f"Could not save paused status: {exc}")
        output_fn("Previously committed answers remain in the existing record.")
    else:
        session = paused
        output_fn(f"Interview paused. Record: {path}")
    print_recovery(session, output_fn)
    return session


def conduct_interview(
    session: InterviewSession,
    storage: InterviewStorage,
    *,
    input_fn: InputFunction = input,
    output_fn: OutputFunction = print,
) -> int:
    """Ask one question at a time and save before advancing."""
    if session.is_completed:
        output_fn(f"Interview {session.session_id} is already completed.")
        output_fn(f"Record: {storage.path_for(session.session_id)}")
        return 0

    pending_answer: str | None = None
    while not session.is_completed:
        index = session.next_question_index
        question = session.questions[index]
        output_fn("")
        output_fn(f"Question {index + 1}/{len(session.questions)}")
        output_fn(question.question)

        prompt = "Answer (or /exit): "
        if pending_answer is not None:
            output_fn("The previous save failed; that answer is still pending.")
            prompt = "Enter /retry, a replacement answer, or /exit: "

        try:
            raw_answer = input_fn(prompt)
        except KeyboardInterrupt:
            output_fn("")
            output_fn("Interrupted by Ctrl+C.")
            pause_and_report(session, storage, output_fn)
            return 130

        command = raw_answer.strip()
        if command.lower() == "/exit":
            if pending_answer is not None:
                output_fn("The pending answer was not committed.")
            pause_and_report(session, storage, output_fn)
            return 0
        if not command:
            output_fn("Blank answers are not saved. Please answer or enter /exit.")
            continue

        answer_to_save = pending_answer if command.lower() == "/retry" else raw_answer
        try:
            candidate = submit_answer(session, answer_to_save)
        except (EmptyAnswerError, CompletedSessionError) as exc:
            output_fn(f"Answer rejected: {exc}")
            continue

        try:
            path = storage.save(candidate)
        except SessionSaveError as exc:
            pending_answer = answer_to_save
            output_fn(f"Save failed; the interview did not advance: {exc}")
            continue

        session = candidate
        pending_answer = None
        output_fn(f"Answer saved. Record: {path}")

    output_fn("")
    output_fn(f"Interview {session.session_id} is completed.")
    output_fn(f"Record: {storage.path_for(session.session_id)}")
    return 0


def run_application(
    *,
    resume_session_id: str | None = None,
    storage: InterviewStorage | None = None,
    provider: QuestionProvider | None = None,
    input_fn: InputFunction = input,
    output_fn: OutputFunction = print,
) -> int:
    """Start or resume an interview without constructing a model on resume."""
    storage = storage or InterviewStorage()

    if resume_session_id is not None:
        try:
            session = storage.load(resume_session_id)
        except (
            InvalidSessionIdError,
            SessionNotFoundError,
            CorruptSessionError,
            UnsupportedSchemaVersionError,
            InterviewStorageError,
        ) as exc:
            output_fn(f"Cannot resume interview: {exc}")
            return 2

        output_fn(f"Loaded interview {session.session_id}.")
        return conduct_interview(
            session,
            storage,
            input_fn=input_fn,
            output_fn=output_fn,
        )

    resume = read_fixture("resume.txt")
    job_description = read_fixture("jd.txt")
    provider = provider or OpenAIQuestionProvider()
    try:
        generation = provider.generate(resume, job_description)
        session = create_session(resume, job_description, generation)
    except ConfigurationError as exc:
        output_fn(f"Configuration error: {exc}")
        return 2
    except Exception as exc:
        output_fn(
            f"Question generation failed ({type(exc).__name__}). "
            "No interview record was created."
        )
        return 1

    try:
        path = storage.save(session)
    except SessionSaveError as exc:
        output_fn(f"Initial save failed; the interview will not start: {exc}")
        return 1

    output_fn(f"Created interview {session.session_id}.")
    output_fn(f"Initial record saved: {path}")
    if generation.messages:
        print_usage(generation.messages)
    return conduct_interview(
        session,
        storage,
        input_fn=input_fn,
        output_fn=output_fn,
    )
