"""Offline M1 tests using a fake question provider and temporary storage."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLES_DIR))

from diagnostic_questions import DiagnosticQuestion, DiagnosticQuestionSet  # noqa: E402
from interview_cli import run_application  # noqa: E402
from interview_models import ModelConfigSnapshot  # noqa: E402
from interview_service import QuestionGeneration  # noqa: E402
from interview_storage import (  # noqa: E402
    DEFAULT_INTERVIEW_DIR,
    InterviewStorage,
)


@contextmanager
def workspace_temp_directory():
    """Create a sandbox-friendly temporary directory and remove it safely."""
    root = (PROJECT_ROOT / "tests" / ".tmp").resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / f"case-{uuid4()}").resolve()
    if root not in path.parents:
        raise RuntimeError("temporary test path escaped its dedicated root")
    path.mkdir()
    try:
        yield path
    finally:
        if path.exists() and root in path.parents:
            shutil.rmtree(path)
        if root.exists() and not any(root.iterdir()):
            root.rmdir()


class FakeQuestionProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, resume: str, job_description: str) -> QuestionGeneration:
        self.calls += 1
        evidence = (
            "Automated weekly ticket categorization with Python, reducing manual "
            "review by 4 hours per week."
        )
        assert evidence in resume
        assert "Junior Automation Analyst" in job_description
        questions = DiagnosticQuestionSet(
            questions=[
                DiagnosticQuestion(
                    question="Describe the ticket automation.",
                    purpose="Assess Python automation.",
                    resume_evidence=evidence,
                    needs_confirmation="",
                ),
                DiagnosticQuestion(
                    question="How did you use SQL findings?",
                    purpose="Assess analysis communication.",
                    resume_evidence=(
                        "Created SQL reports that summarized recurring customer "
                        "issues for the support manager."
                    ),
                    needs_confirmation="",
                ),
                DiagnosticQuestion(
                    question="How do you test an automated workflow?",
                    purpose="Assess workflow testing.",
                    resume_evidence="",
                    needs_confirmation="Testing experience is not stated.",
                ),
            ]
        )
        return QuestionGeneration(
            questions=questions,
            model_config=ModelConfigSnapshot(
                provider="fake",
                model="fake-interview-model",
                reasoning_effort="none",
                max_retries=0,
                langsmith_tracing=False,
            ),
            messages=[],
        )


class ExplodingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, resume: str, job_description: str) -> QuestionGeneration:
        self.calls += 1
        raise AssertionError("resume must never call the model provider")


class FailSecondReplaceStorage(InterviewStorage):
    """Allow initial save, fail the first answer save, then recover."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory)
        self.replace_calls = 0

    def _replace(self, source: Path, target: Path) -> None:
        self.replace_calls += 1
        if self.replace_calls == 2:
            raise OSError("simulated replace failure")
        super()._replace(source, target)


class AlwaysFailStorage(InterviewStorage):
    def _replace(self, source: Path, target: Path) -> None:
        raise OSError("simulated storage failure")


class InterviewSessionTests(unittest.TestCase):
    def test_blank_unknown_exit_resume_and_completed_session(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = InterviewStorage(Path(temporary) / "interviews")
            provider = FakeQuestionProvider()
            outputs: list[str] = []
            responses = iter(["   ", "不知道", "/exit"])

            result = run_application(
                storage=storage,
                provider=provider,
                input_fn=lambda prompt: next(responses),
                output_fn=outputs.append,
            )
            self.assertEqual(result, 0)
            self.assertEqual(provider.calls, 1)
            paths = list(storage.directory.glob("*.json"))
            self.assertEqual(len(paths), 1, "new questions must be saved immediately")

            session_id = paths[0].stem
            paused = storage.load(session_id)
            self.assertEqual(paused.schema_version, 1)
            self.assertEqual(paused.status, "paused")
            self.assertEqual(len(paused.answers), 1)
            self.assertEqual(paused.answers[0].answer, "不知道")
            self.assertIn("Jordan Lee", paused.source_snapshot.resume)
            self.assertIn(
                "Junior Automation Analyst",
                paused.source_snapshot.job_description,
            )
            self.assertIsNotNone(paused.created_at.utcoffset())
            self.assertIsNotNone(paused.updated_at.utcoffset())
            self.assertTrue(any("Blank answers" in line for line in outputs))
            saved_text = paths[0].read_text(encoding="utf-8")
            self.assertIn('"model_config"', saved_text)
            self.assertNotIn("OPENAI_API_KEY", saved_text)

            resume_provider = ExplodingProvider()
            resume_answers = iter(["SQL answer", "testing answer"])
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False),
                patch(
                    "interview_service.build_model",
                    side_effect=AssertionError("resume must not construct a model"),
                ),
            ):
                resumed_result = run_application(
                    resume_session_id=session_id,
                    storage=storage,
                    provider=resume_provider,
                    input_fn=lambda prompt: next(resume_answers),
                    output_fn=outputs.append,
                )
            self.assertEqual(resumed_result, 0)
            self.assertEqual(resume_provider.calls, 0)
            completed = storage.load(session_id)
            self.assertEqual(completed.status, "completed")
            self.assertEqual(len(completed.answers), 3)

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError("completed sessions must not prompt")

            completed_result = run_application(
                resume_session_id=session_id,
                storage=storage,
                provider=resume_provider,
                input_fn=fail_if_prompted,
                output_fn=outputs.append,
            )
            self.assertEqual(completed_result, 0)
            self.assertEqual(resume_provider.calls, 0)

    def test_failed_answer_save_does_not_advance_and_retry_keeps_answer(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = FailSecondReplaceStorage(Path(temporary) / "interviews")
            provider = FakeQuestionProvider()
            outputs: list[str] = []
            prompt_count = 0

            def input_with_assertion(prompt: str) -> str:
                nonlocal prompt_count
                prompt_count += 1
                if prompt_count == 1:
                    return "answer kept for retry"
                paths = list(storage.directory.glob("*.json"))
                session = storage.load(paths[0].stem)
                if prompt_count == 2:
                    self.assertEqual(
                        len(session.answers),
                        0,
                        "failed replacement must leave the old record unchanged",
                    )
                    return "/retry"
                return "/exit"

            result = run_application(
                storage=storage,
                provider=provider,
                input_fn=input_with_assertion,
                output_fn=outputs.append,
            )
            self.assertEqual(result, 0)
            path = next(storage.directory.glob("*.json"))
            session = storage.load(path.stem)
            self.assertEqual(len(session.answers), 1)
            self.assertEqual(session.answers[0].answer, "answer kept for retry")
            self.assertTrue(any("did not advance" in line for line in outputs))

    def test_initial_save_failure_never_prompts(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = AlwaysFailStorage(Path(temporary) / "interviews")

            def fail_if_prompted(prompt: str) -> str:
                raise AssertionError("an unsaved session must not start")

            result = run_application(
                storage=storage,
                provider=FakeQuestionProvider(),
                input_fn=fail_if_prompted,
                output_fn=lambda line: None,
            )
            self.assertEqual(result, 1)
            self.assertEqual(list(storage.directory.glob("*.json")), [])
            self.assertEqual(list(storage.directory.glob("*.tmp")), [])

    def test_ctrl_c_pauses_and_prints_recovery(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = InterviewStorage(Path(temporary) / "interviews")
            outputs: list[str] = []

            def interrupt(prompt: str) -> str:
                raise KeyboardInterrupt

            result = run_application(
                storage=storage,
                provider=FakeQuestionProvider(),
                input_fn=interrupt,
                output_fn=outputs.append,
            )
            self.assertEqual(result, 130)
            path = next(storage.directory.glob("*.json"))
            self.assertEqual(storage.load(path.stem).status, "paused")
            self.assertTrue(any("Resume with:" in line for line in outputs))

    def test_corrupt_and_unsupported_records_are_not_overwritten(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = InterviewStorage(Path(temporary) / "interviews")
            storage.directory.mkdir(parents=True)
            cases = [
                ("{not-json", "invalid JSON"),
                ('{"schema_version": 999}', "unsupported schema_version"),
            ]
            for content, expected_message in cases:
                session_id = str(uuid4())
                path = storage.path_for(session_id)
                path.write_text(content, encoding="utf-8")
                outputs: list[str] = []
                before = path.read_bytes()
                result = run_application(
                    resume_session_id=session_id,
                    storage=storage,
                    provider=ExplodingProvider(),
                    input_fn=lambda prompt: (_ for _ in ()).throw(
                        AssertionError("invalid records must not prompt")
                    ),
                    output_fn=outputs.append,
                )
                self.assertEqual(result, 2)
                self.assertEqual(path.read_bytes(), before)
                self.assertTrue(any(expected_message in line for line in outputs))

    def test_invalid_and_missing_ids_are_rejected(self) -> None:
        with workspace_temp_directory() as temporary:
            storage = InterviewStorage(Path(temporary) / "interviews")
            for session_id, expected in [
                ("../../escape", "valid UUID"),
                (str(uuid4()), "not found"),
            ]:
                outputs: list[str] = []
                result = run_application(
                    resume_session_id=session_id,
                    storage=storage,
                    provider=ExplodingProvider(),
                    input_fn=lambda prompt: "should not be used",
                    output_fn=outputs.append,
                )
                self.assertEqual(result, 2)
                self.assertTrue(any(expected in line for line in outputs))

    def test_default_storage_is_project_relative_not_cwd_relative(self) -> None:
        expected = Path(__file__).resolve().parents[1] / "data" / "interviews"
        original = Path.cwd()
        with workspace_temp_directory() as temporary:
            os.chdir(temporary)
            try:
                self.assertEqual(DEFAULT_INTERVIEW_DIR, expected)
                self.assertTrue(DEFAULT_INTERVIEW_DIR.is_absolute())
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
