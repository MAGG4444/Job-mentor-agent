"""Generate three interview questions from fictional resume and JD fixtures."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from pydantic import BaseModel, Field

from _config import ConfigurationError, build_model


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PROMPT_VERSION = "diagnostic-questions-v1"
SYSTEM_PROMPT = (
    "You create grounded diagnostic interview questions. Return exactly "
    "three questions. Use only facts present in the supplied resume and job "
    "description. Never invent skills, duties, achievements, scores, hiring "
    "probabilities, or a training plan. Every non-empty resume_evidence must "
    "be copied verbatim from the resume; otherwise use an empty string and "
    "state what must be confirmed in needs_confirmation."
)


class DiagnosticQuestion(BaseModel):
    """One evidence-grounded diagnostic interview question."""

    question: str = Field(description="The interview question to ask.")
    purpose: str = Field(description="What the question is intended to assess.")
    resume_evidence: str = Field(
        description=(
            "An exact, verbatim substring from the resume supporting the question, "
            "or an empty string when the resume provides no evidence."
        )
    )
    needs_confirmation: str = Field(
        description=(
            "Information the candidate still needs to confirm, or an empty string "
            "when no confirmation is needed."
        )
    )


class DiagnosticQuestionSet(BaseModel):
    """Exactly three diagnostic interview questions."""

    questions: list[DiagnosticQuestion] = Field(min_length=3, max_length=3)


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8").strip()


def validate_resume_evidence(result: DiagnosticQuestionSet, resume: str) -> None:
    """Reject any non-empty evidence that is not copied from the resume."""
    for index, item in enumerate(result.questions, start=1):
        if item.resume_evidence and item.resume_evidence not in resume:
            raise ValueError(
                f"Question {index} contains resume_evidence that is not an exact "
                "substring of the resume."
            )


def generate_diagnostic_questions(
    model: Any,
    resume: str,
    job_description: str,
) -> tuple[DiagnosticQuestionSet, list[object]]:
    """Generate and validate exactly three evidence-grounded questions."""
    agent = create_agent(
        model=model,
        tools=[],
        response_format=ProviderStrategy(DiagnosticQuestionSet, strict=True),
        system_prompt=SYSTEM_PROMPT,
    )
    prompt = f"""Create three diagnostic interview questions for this fictional candidate.

<resume>
{resume}
</resume>

<job_description>
{job_description}
</job_description>
"""
    state = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 4},
    )
    result = DiagnosticQuestionSet.model_validate(state["structured_response"])
    validate_resume_evidence(result, resume)
    return result, state["messages"]


def print_usage(messages: list[object]) -> None:
    """Print token totals returned by the API without request or credential data."""
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    found = False
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            continue
        found = True
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value

    if found:
        summary = ", ".join(f"{key}={value}" for key, value in totals.items())
        print(f"API usage: {summary}", file=sys.stderr)
    else:
        print("API usage: unknown (not returned)", file=sys.stderr)


def main() -> int:
    try:
        model = build_model()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    resume = read_fixture("resume.txt")
    job_description = read_fixture("jd.txt")
    try:
        result, messages = generate_diagnostic_questions(
            model,
            resume,
            job_description,
        )
    except ValueError as exc:
        print(f"Output validation failed: {exc}")
        return 1
    except Exception as exc:
        print(
            f"Structured model call failed ({type(exc).__name__}). Confirm that "
            "the API key can access MODEL_NAME and that the model supports native "
            "structured output. This example does not fall back to unvalidated text."
        )
        return 1

    print_usage(messages)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
