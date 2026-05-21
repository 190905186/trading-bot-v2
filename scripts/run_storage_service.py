"""Consume ticks.raw and candles.1m.closed from Redis and persist to SQLite."""

from __future__ import annotations

import logging
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

from trading_bot_v2.domain.contracts.events import EventName  # noqa: E402
from trading_bot_v2.infrastructure.messaging import RedisStreamConsumer, RedisStreamPublisher  # noqa: E402
from trading_bot_v2.infrastructure.storage.sqlite_store import SqliteEventStore, sqlite_path_from_env  # noqa: E402
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter  # noqa: E402
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider  # noqa: E402


def main() -> None:
    log_level = getattr(logging, os.getenv("TB2_LOG_LEVEL", "INFO").strip().upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("storage-service")

    redis_url = os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0")
    consumer_start = os.getenv("TB2_CONSUMER_START_ID", "0")
    service_name = os.getenv("TB2_SERVICE_NAME", "").strip() or "storage-service"

    store = SqliteEventStore()
    log.info("SQLite store: %s", store.db_path)

    counters = {"ticks_written": 0, "candles_written": 0}

    publisher = RedisStreamPublisher(redis_url=redis_url)
    consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)

    def _metadata() -> dict:
        return {
            "role": "storage",
            "sqlite_path": str(store.db_path),
            "ticks_written_session": counters["ticks_written"],
            "candles_written_session": counters["candles_written"],
            "ticks_stored_total": store.count_ticks(),
            "candles_stored_total": store.count_candles(),
        }

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name=service_name,
        resource_provider=ProcessResourceHealthProvider(service_name).get_health,
        metadata_factory=_metadata,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    def on_tick(event: dict) -> None:
        if store.insert_tick(event):
            counters["ticks_written"] += 1

    def on_candle(event: dict) -> None:
        if store.insert_candle(event):
            counters["candles_written"] += 1

    tick_thread = threading.Thread(
        target=consumer.subscribe,
        args=(EventName.TICKS_RAW.value, on_tick),
        daemon=True,
    )
    candle_consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)
    candle_thread = threading.Thread(
        target=candle_consumer.subscribe,
        args=(EventName.CANDLES_1M_CLOSED.value, on_candle),
        daemon=True,
    )
    tick_thread.start()
    candle_thread.start()
    log.info("Storage service consuming %s and %s", EventName.TICKS_RAW.value, EventName.CANDLES_1M_CLOSED.value)

    try:
        while True:
            threading.Event().wait(timeout=3600)
    except KeyboardInterrupt:
        log.info("Stopping storage service")
        store.close()


if __name__ == "__main__":
    main()
