"""Generate token universe pickles (runs trading-bot v1 token_list.py by default)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.token_universe.generate import (  # noqa: E402
    copy_pickles_from_dir,
    default_v1_token_list_script,
    run_v1_token_list,
)
from trading_bot_v2.token_universe.loader import universe_dir_from_env  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Generate tokens.pkl and related pickles for TB2.")
    p.add_argument(
        "--output-dir",
        default="",
        help="Output directory (default: TB2_TOKEN_UNIVERSE_DIR or data/token_universe)",
    )
    p.add_argument(
        "--script",
        default=os.getenv("TB2_TOKEN_LIST_SCRIPT", "").strip(),
        help="Path to v1 token_list.py (default: ../trading-bot/src/token_objects/token_list.py)",
    )
    p.add_argument(
        "--copy-from",
        default=os.getenv("TB2_TOKEN_COPY_FROM", "").strip(),
        help="Skip generation; copy pickles from this directory instead",
    )
    args = p.parse_args()

    out = Path(args.output_dir).resolve() if args.output_dir else universe_dir_from_env()

    if args.copy_from:
        copy_pickles_from_dir(Path(args.copy_from).resolve(), out)
        print(f"Copied pickles to {out}")
        return

    script = Path(args.script).resolve() if args.script else default_v1_token_list_script()
    print(f"Running v1 token list generator: {script}")
    print(f"Output directory: {out}")
    run_v1_token_list(out, script_path=script)
    print("Done. Run scripts/build_token_batches.py next.")


if __name__ == "__main__":
    main()
