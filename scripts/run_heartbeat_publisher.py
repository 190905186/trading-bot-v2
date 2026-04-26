"""Publish service heartbeat events to Redis."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.infrastructure.messaging import RedisStreamPublisher
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://localhost:6379/0")
    service_name = os.getenv("TB2_SERVICE_NAME", "unknown-service")
    interval = float(os.getenv("TB2_HEARTBEAT_INTERVAL_SECONDS", "2.0"))

    publisher = RedisStreamPublisher(redis_url=redis_url)
    process_health = ProcessResourceHealthProvider(service_name)
    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name=service_name,
        resource_provider=process_health.get_health,
    )
    emitter.run_forever(interval_seconds=interval)


if __name__ == "__main__":
    main()
