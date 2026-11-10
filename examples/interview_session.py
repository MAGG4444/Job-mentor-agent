"""Command-line entry point for a persistent three-question interview."""

from __future__ import annotations

import argparse

from interview_cli import run_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start or resume a saved Job Mentor terminal interview."
    )
    parser.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="Resume an existing interview without calling the model.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_application(resume_session_id=args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
