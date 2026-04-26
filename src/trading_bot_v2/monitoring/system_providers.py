"""System and process health providers."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict

import psutil

from trading_bot_v2.interfaces.dashboard import HealthProvider


class ProcessResourceHealthProvider(HealthProvider):
    """Reports CPU and memory utilization for the current service process."""

    def __init__(self, service_name: str) -> None:
        self._service_name = service_name
        self._process = psutil.Process(os.getpid())

    def get_health(self) -> Dict[str, Any]:
        cpu_percent = self._process.cpu_percent(interval=0.0)
        rss_mb = self._process.memory_info().rss / (1024 * 1024)
        return {
            "service_name": self._service_name,
            "status": "up",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": round(cpu_percent, 3),
            "memory_mb": round(rss_mb, 3),
            "pid": self._process.pid,
        }
