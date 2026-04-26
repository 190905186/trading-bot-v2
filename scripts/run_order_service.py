"""Run order execution service consuming generated signals."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.infrastructure.execution import PaperExecutionAdapter
from trading_bot_v2.infrastructure.messaging import RedisStreamConsumer, RedisStreamPublisher
from trading_bot_v2.infrastructure.risk import BasicRiskManager
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.services.order.service import OrderService


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://localhost:6379/0")
    consumer_start = os.getenv("TB2_CONSUMER_START_ID", "$")
    broker_name = os.getenv("TB2_BROKER_NAME", "zerodha")

    publisher = RedisStreamPublisher(redis_url=redis_url)
    consumer = RedisStreamConsumer(redis_url=redis_url, start_id=consumer_start)
    adapter = PaperExecutionAdapter(broker_name=broker_name)
    risk_manager = BasicRiskManager(max_notional=float(os.getenv("TB2_MAX_NOTIONAL", "1000000")))
    order_service = OrderService(execution_adapter=adapter, risk_manager=risk_manager, publisher=publisher)

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name="order-service",
        resource_provider=ProcessResourceHealthProvider("order-service").get_health,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    def on_signal(signal_event: dict) -> None:
        payload = signal_event.get("payload", signal_event)
        order_service.place_from_signal(payload)

    consumer.subscribe("signals.generated", on_signal)


if __name__ == "__main__":
    main()
