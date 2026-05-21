"""Build token_batches.pkl from tokens.pkl using TB2 batch profile rules."""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.token_universe.batch_rules import (  # noqa: E402
    build_token_batches,
    validate_batches_no_overlap_within_broker,
)
from trading_bot_v2.token_universe.loader import load_all_tokens, universe_dir_from_env  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Build token_batches.pkl from tokens.pkl.")
    p.add_argument("--output-dir", default="", help="Universe directory")
    p.add_argument(
        "--profile",
        default=os.getenv("TB2_BATCH_PROFILE", "production"),
        choices=("production", "test"),
    )
    args = p.parse_args()

    out = Path(args.output_dir).resolve() if args.output_dir else universe_dir_from_env()
    tokens = load_all_tokens(out)
    batches = build_token_batches(tokens, profile=args.profile)
    validate_batches_no_overlap_within_broker(batches)

    path = out / "token_batches.pkl"
    out.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(batches, f)

    for name, toks in sorted(batches.items()):
        print(f"  {name}: {len(toks)} tokens")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
