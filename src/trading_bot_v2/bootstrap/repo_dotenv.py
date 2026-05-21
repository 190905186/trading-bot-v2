"""Load ``trading-bot-v2/.env`` into the process environment for local runs."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[3]


def load_repo_dotenv() -> None:
    load_dotenv(_REPO_ROOT / ".env")
