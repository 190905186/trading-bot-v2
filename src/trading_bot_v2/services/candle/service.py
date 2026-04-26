"""Candle production service skeleton."""

from __future__ import annotations

from typing import Any, Dict

from trading_bot_v2.domain.contracts import CandleEvent
from trading_bot_v2.interfaces.messaging import EventPublisher


class CandleService:
    """Publishes closed candle events from tick aggregation/backfill pipeline."""

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def publish_closed_candle(self, candle_payload: Dict[str, Any]) -> None:
        event = CandleEvent(producer="candle-service", payload=candle_payload)
        self._publisher.publish(event.event_name, event.to_dict())
