"""Run tick ingestion service with selectable market-data adapter."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.infrastructure.brokers import MockMarketDataAdapter, ZerodhaMarketDataAdapter
from trading_bot_v2.infrastructure.messaging import RedisStreamPublisher
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.services.ticks.service import TickIngestionService


def _build_adapter(source: str, broker_name: str, tick_interval: float):
    normalized = source.strip().lower()
    if normalized == "zerodha":
        api_key = os.getenv("TB2_ZERODHA_API_KEY", "").strip()
        access_token = os.getenv("TB2_ZERODHA_ACCESS_TOKEN", "").strip()
        if not api_key or not access_token:
            raise RuntimeError(
                "TB2_ZERODHA_API_KEY and TB2_ZERODHA_ACCESS_TOKEN are required for zerodha source."
            )
        return ZerodhaMarketDataAdapter(api_key=api_key, access_token=access_token)
    return MockMarketDataAdapter(broker_name=broker_name, tick_interval_seconds=tick_interval)


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://localhost:6379/0")
    source = os.getenv("TB2_MARKET_DATA_SOURCE", "mock")
    broker_name = os.getenv("TB2_BROKER_NAME", "zerodha")
    default_instruments = "NSE:RELIANCE,NSE:INFY,NSE:TCS" if source != "zerodha" else "256265,738561,2953217"
    instruments_env = os.getenv("TB2_INSTRUMENTS", default_instruments)
    instruments = [item.strip() for item in instruments_env.split(",") if item.strip()]
    tick_interval = float(os.getenv("TB2_TICK_INTERVAL_SECONDS", "0.2"))

    publisher = RedisStreamPublisher(redis_url=redis_url)
    adapter = _build_adapter(source=source, broker_name=broker_name, tick_interval=tick_interval)
    service = TickIngestionService(adapter=adapter, publisher=publisher)

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name="ticks-service",
        resource_provider=ProcessResourceHealthProvider("ticks-service").get_health,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    service.run(instruments)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        adapter.disconnect()


if __name__ == "__main__":
    main()
