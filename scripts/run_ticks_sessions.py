"""Launch one run_ticks_service.py child process per broker batch (e.g. 9 processes)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
TICKS_SCRIPT = ROOT / "scripts" / "run_ticks_service.py"

# Default full layout: 3 Zerodha + 3 AngelOne + 3 Finvasia
DEFAULT_SESSIONS = ",".join(
    [
        "zerodha:batch1",
        "zerodha:batch2",
        "zerodha:batch3",
        "angelone:batch4",
        "angelone:batch5",
        "angelone:batch6",
        "finvasia:batch7",
        "finvasia:batch8",
        "finvasia:batch9",
    ]
)


def _parse_sessions(raw: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Invalid session spec {part!r}; use broker:batch (e.g. zerodha:batch1)")
        broker, batch = part.split(":", 1)
        out.append((broker.strip().lower(), batch.strip()))
    if not out:
        raise ValueError("No sessions configured")
    return out


def _python_exe() -> str:
    return str(VENV_PYTHON) if VENV_PYTHON.is_file() else sys.executable


def main() -> None:
    raw = os.getenv("TB2_TICK_SESSIONS", DEFAULT_SESSIONS).strip()
    sessions = _parse_sessions(raw)
    py = _python_exe()
    children: list[tuple[str, subprocess.Popen]] = []

    for broker, batch in sessions:
        env = os.environ.copy()
        env["TB2_MARKET_DATA_SOURCE"] = broker
        env["TB2_TICK_BATCH"] = batch
        env["TB2_TICK_SESSION_ID"] = batch
        env["TB2_SERVICE_NAME"] = f"ticks-{broker}-{batch}"
        name = f"{broker}:{batch}"
        print(f"[start] {name}")
        proc = subprocess.Popen([py, str(TICKS_SCRIPT)], cwd=str(ROOT), env=env)
        children.append((name, proc))

    print(f"[info] Started {len(children)} tick processes. Ctrl+C to stop all.")
    try:
        while True:
            time.sleep(1.0)
            for name, proc in children:
                rc = proc.poll()
                if rc is not None:
                    raise RuntimeError(f"Tick process {name} exited with code {rc}")
    except KeyboardInterrupt:
        print("\n[stop] Shutting down tick children...")
    finally:
        for name, proc in reversed(children):
            if proc.poll() is None:
                print(f"[stop] terminate {name}")
                proc.terminate()
        time.sleep(1.0)
        for name, proc in reversed(children):
            if proc.poll() is None:
                print(f"[stop] kill {name}")
                proc.kill()


if __name__ == "__main__":
    main()
