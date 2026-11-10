"""Atomic JSON storage for interview sessions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from interview_models import InterviewSession, SCHEMA_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTERVIEW_DIR = PROJECT_ROOT / "data" / "interviews"


class InterviewStorageError(RuntimeError):
    """Base class for safe, user-facing storage failures."""


class InvalidSessionIdError(InterviewStorageError):
    pass


class SessionNotFoundError(InterviewStorageError):
    pass


class CorruptSessionError(InterviewStorageError):
    pass


class UnsupportedSchemaVersionError(InterviewStorageError):
    pass


class SessionSaveError(InterviewStorageError):
    pass


def normalize_session_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise InvalidSessionIdError("session_id must be a valid UUID") from exc


class InterviewStorage:
    """Load and atomically replace records inside one fixed directory."""

    def __init__(self, directory: Path = DEFAULT_INTERVIEW_DIR) -> None:
        self.directory = Path(directory).resolve()

    def path_for(self, session_id: str) -> Path:
        normalized = normalize_session_id(session_id)
        return self.directory / f"{normalized}.json"

    def save(self, session: InterviewSession) -> Path:
        target = self.path_for(session.session_id)
        temporary_path: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{session.session_id}.",
                suffix=".tmp",
                dir=self.directory,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(session.model_dump_json(indent=2, by_alias=True))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace(temporary_path, target)
            return target
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise SessionSaveError(f"could not save interview record: {exc}") from exc

    def _replace(self, source: Path, target: Path) -> None:
        os.replace(source, target)

    def load(self, session_id: str) -> InterviewSession:
        target = self.path_for(session_id)
        try:
            raw = target.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SessionNotFoundError(f"interview session not found: {session_id}") from exc
        except OSError as exc:
            raise InterviewStorageError(f"could not read interview record: {exc}") from exc

        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptSessionError("interview record contains invalid JSON") from exc
        if not isinstance(payload, dict):
            raise CorruptSessionError("interview record must contain a JSON object")

        version = payload.get("schema_version")
        if version is None:
            raise CorruptSessionError("interview record is missing schema_version")
        if version != SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"unsupported schema_version {version!r}; expected {SCHEMA_VERSION}"
            )

        try:
            return InterviewSession.model_validate(payload)
        except ValidationError as exc:
            raise CorruptSessionError(f"interview record failed validation: {exc}") from exc
