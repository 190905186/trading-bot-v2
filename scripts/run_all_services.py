"""Launch full local pipeline as child processes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _start(name: str, script_path: str, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("TB2_REDIS_URL", "redis://localhost:6380/0")
    if extra_env:
        env.update(extra_env)
    cmd = [str(VENV_PYTHON), script_path]
    print(f"[start] {name}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env)


def main() -> None:
    if not VENV_PYTHON.exists():
        raise RuntimeError("Virtual environment python not found. Create .venv first.")

    processes: list[tuple[str, subprocess.Popen]] = []
    try:
        processes.append(("ticks", _start("ticks", "scripts/run_ticks_service.py")))
        processes.append(("candle", _start("candle", "scripts/run_candle_service.py")))
        processes.append(("storage", _start("storage", "scripts/run_storage_service.py")))
        processes.append(("signal", _start("signal", "scripts/run_signal_service.py")))
        processes.append(("order", _start("order", "scripts/run_order_service.py")))
        processes.append(
            (
                "dashboard",
                _start(
                    "dashboard",
                    "scripts/run_dashboard_api.py",
                    extra_env={"TB2_DASHBOARD_PORT": "8088"},
                ),
            )
        )

        print("[info] Services started. Dashboard: http://127.0.0.1:8088/dashboard")
        print("[info] Press Ctrl+C to stop all services.")
        while True:
            time.sleep(1.0)
            for name, proc in processes:
                rc = proc.poll()
                if rc is not None:
                    raise RuntimeError(f"Service '{name}' exited unexpectedly with code {rc}.")

    except KeyboardInterrupt:
        print("\n[stop] Keyboard interrupt received.")
    finally:
        for name, proc in reversed(processes):
            if proc.poll() is None:
                print(f"[stop] terminating {name}")
                proc.terminate()
        time.sleep(1.0)
        for name, proc in reversed(processes):
            if proc.poll() is None:
                print(f"[stop] killing {name}")
                proc.kill()


if __name__ == "__main__":
    main()
