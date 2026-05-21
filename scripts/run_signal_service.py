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

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.infrastructure.messaging import RedisStreamConsumer, RedisStreamPublisher
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.services.signal.service import SignalService
from trading_bot_v2.strategies import OhlcOpenRangeStrategy, SimpleCandleMomentumStrategy


def _build_strategy():
    kind = os.getenv("TB2_SIGNAL_STRATEGY", "simple_candle_momentum").strip().lower()
    if kind in {"ohlc_open_range", "open_range", "ohlc"}:
        tick_size = float(os.getenv("TB2_SIGNAL_TICK_SIZE", "0.05"))
        multiplier = float(os.getenv("TB2_SIGNAL_TICK_MULTIPLIER", "1.0"))
        abs_tol = float(os.getenv("TB2_SIGNAL_PRICE_TOLERANCE", "0"))
        return OhlcOpenRangeStrategy(
            tick_size=tick_size,
            multiplier=multiplier,
            abs_tolerance=abs_tol,
        )
    threshold_percent = float(os.getenv("TB2_SIGNAL_THRESHOLD_PERCENT", "0.15"))
    return SimpleCandleMomentumStrategy(threshold_percent=threshold_percent)


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0")
    consumer_start = os.getenv("TB2_CONSUMER_START_ID", "$")

    publisher = RedisStreamPublisher(redis_url=redis_url)
    consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)
    strategy = _build_strategy()
    signal_service = SignalService(strategy=strategy, publisher=publisher)
    strategy_env = os.getenv("TB2_SIGNAL_STRATEGY", "simple_candle_momentum").strip()

    def _signal_heartbeat_metadata() -> dict:
        return {
            "tb2_signal_strategy": strategy_env,
            **strategy.dashboard_metadata(),
            **signal_service.dashboard_runtime_metadata(),
        }

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name="signal-service",
        resource_provider=ProcessResourceHealthProvider("signal-service").get_health,
        metadata_factory=_signal_heartbeat_metadata,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    def on_candle(candle_event: dict) -> None:
        signal_service.process_candle(candle_event)

    consumer.subscribe("candles.1m.closed", on_candle)


if __name__ == "__main__":
    main()
