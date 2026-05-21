#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -d "$ROOT/.venv" ]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi

# Optional: scripts also call load_dotenv(repo/.env) via trading_bot_v2.bootstrap.repo_dotenv
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT/.env"
  set +a
fi

export TB2_REDIS_URL="${TB2_REDIS_URL:-redis://127.0.0.1:6381/0}"
export TB2_MARKET_DATA_SOURCE="${TB2_MARKET_DATA_SOURCE:-mock}"

exec python scripts/run_ticks_service.py
