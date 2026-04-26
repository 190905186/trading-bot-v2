"""Run signal service consuming closed candles."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.infrastructure.messaging import RedisStreamConsumer, RedisStreamPublisher
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.services.signal.service import SignalService
from trading_bot_v2.strategies import SimpleCandleMomentumStrategy


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://localhost:6379/0")
    consumer_start = os.getenv("TB2_CONSUMER_START_ID", "$")
    threshold_percent = float(os.getenv("TB2_SIGNAL_THRESHOLD_PERCENT", "0.15"))

    publisher = RedisStreamPublisher(redis_url=redis_url)
    consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)
    strategy = SimpleCandleMomentumStrategy(threshold_percent=threshold_percent)
    signal_service = SignalService(strategy=strategy, publisher=publisher)

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name="signal-service",
        resource_provider=ProcessResourceHealthProvider("signal-service").get_health,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    def on_candle(candle_event: dict) -> None:
        signal_service.process_candle(candle_event)

    consumer.subscribe("candles.1m.closed", on_candle)


if __name__ == "__main__":
    main()
