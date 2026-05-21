"""Tick ingestion service skeleton."""

from __future__ import annotations

from typing import Any, Mapping

from trading_bot_v2.domain.contracts import TickEvent
from trading_bot_v2.interfaces.broker import MarketDataAdapter
from trading_bot_v2.interfaces.messaging import EventPublisher
from trading_bot_v2.services.ticks.serialize import prepare_tick_payload


class TickIngestionService:
    """Consumes broker ticks and publishes canonical tick events."""

    def __init__(
        self,
        adapter: MarketDataAdapter,
        publisher: EventPublisher,
        *,
        tick_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._adapter = adapter
        self._publisher = publisher
        self._tick_metadata = dict(tick_metadata or {})

    def _on_tick(self, tick_payload: Mapping[str, Any]) -> None:
        payload = prepare_tick_payload(tick_payload)
        if self._tick_metadata:
            payload.update(self._tick_metadata)
        event = TickEvent(
            producer=f"ticks-service:{self._adapter.broker_name}",
            payload=payload,
        )
        self._publisher.publish(event.event_name, event.to_dict())

    def run(self, instruments: list[str]) -> None:
        self._adapter.set_tick_handler(self._on_tick)
        self._adapter.subscribe(instruments)
        self._adapter.connect()
