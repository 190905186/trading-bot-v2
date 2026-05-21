"""Generate token universe pickles (delegates to trading-bot v1 script when available)."""

from __future__ import annotations

import pickle
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

_PICKLES_TO_COPY = (
    "tokens.pkl",
    "subscribe_list.pkl",
    "token_exch_map.pkl",
    "token_symbol_map.pkl",
    "token_tick_size_map.pkl",
    "amxidx_dict.pkl",
)


def default_v1_token_list_script() -> Path:
    """Path to trading-bot ``token_list.py`` (sibling repo)."""
    # src/trading_bot_v2/token_universe/generate.py -> trading-bot-v2 -> code -> trading-bot
    code_root = Path(__file__).resolve().parents[4]
    return code_root / "trading-bot" / "src" / "token_objects" / "token_list.py"


def run_v1_token_list(
    output_dir: Path,
    *,
    script_path: Path | None = None,
    python_exe: str | None = None,
) -> None:
    """
    Run the v1 token_list.py generator and copy tick-related pickles into ``output_dir``.
    """
    script = script_path or default_v1_token_list_script()
    if not script.is_file():
        raise FileNotFoundError(
            f"v1 token_list.py not found at {script}. "
            "Set TB2_TOKEN_LIST_SCRIPT or place trading-bot alongside trading-bot-v2."
        )

    py = python_exe or sys.executable
    # token_list.py expects trading-bot repo root as cwd
    v1_root = script.parent.parent.parent
    subprocess.run([py, str(script)], check=True, cwd=str(v1_root))

    v1_objects = script.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in _PICKLES_TO_COPY:
        src = v1_objects / name
        if src.is_file():
            shutil.copy2(src, output_dir / name)


def copy_pickles_from_dir(source_dir: Path, output_dir: Path, names: Iterable[str] = _PICKLES_TO_COPY) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, output_dir / name)


def import_tokens_from_list(tokens: list[int], output_dir: Path) -> None:
    """Write a minimal tokens.pkl (for dev without running full v1 generator)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "tokens.pkl").open("wb") as f:
        pickle.dump([int(t) for t in tokens], f)
