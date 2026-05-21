"""Run candle aggregation service consuming ticks.raw."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.infrastructure.candles import build_candle_provider_from_env_safe
from trading_bot_v2.infrastructure.messaging import RedisStreamConsumer, RedisStreamPublisher
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.services.candle.aggregator import MinuteCandleAggregator
from trading_bot_v2.services.candle.service import CandleService


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0")
    consumer_start = os.getenv("TB2_CONSUMER_START_ID", "$")
    publisher = RedisStreamPublisher(redis_url=redis_url)
    consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)
    aggregator = MinuteCandleAggregator()
    candle_provider = build_candle_provider_from_env_safe()
    candle_service = CandleService(publisher=publisher, provider=candle_provider)

    market_source = os.getenv("TB2_MARKET_DATA_SOURCE", "").strip() or "mock"

    def _candle_heartbeat_metadata() -> dict:
        return {
            "tb2_market_data_source": market_source,
            **candle_service.dashboard_runtime_metadata(),
        }

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name="candle-service",
        resource_provider=ProcessResourceHealthProvider("candle-service").get_health,
        metadata_factory=_candle_heartbeat_metadata,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    def on_tick(tick_event: dict) -> None:
        closed = aggregator.process_tick_event(tick_event)
        if closed:
            candle_service.publish_closed_candle(closed)

    consumer.subscribe("ticks.raw", on_tick)


if __name__ == "__main__":
    main()
