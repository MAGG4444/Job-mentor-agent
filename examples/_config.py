"""Shared local configuration for the examples."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


class ConfigurationError(RuntimeError):
    """Raised when local model configuration is missing or unsupported."""


def build_model() -> ChatOpenAI:
    """Load the project .env explicitly and create the configured OpenAI model."""
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    os.environ["LANGSMITH_TRACING"] = "false"

    provider = os.getenv("MODEL_PROVIDER", "").strip().lower()
    model_name = os.getenv("MODEL_NAME", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if provider != "openai":
        raise ConfigurationError(
            "MODEL_PROVIDER must be 'openai' for these examples. "
            "Copy .env.example to .env and edit it locally."
        )
    if not model_name:
        raise ConfigurationError(
            "MODEL_NAME is missing. Add a model ID that your account can access "
            "to the project .env file."
        )
    if not api_key or api_key == "replace-with-your-openai-api-key":
        raise ConfigurationError(
            "OPENAI_API_KEY is missing. Add it to the project .env file; "
            "do not put it in source code or send it in chat."
        )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        timeout=30.0,
        max_retries=0,
        reasoning_effort="medium",
        use_responses_api=True,
    )
