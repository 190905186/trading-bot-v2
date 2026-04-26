"""Signal generation service skeleton."""

from __future__ import annotations

from typing import Mapping

from trading_bot_v2.domain.contracts import SignalEvent
from trading_bot_v2.interfaces.messaging import EventPublisher
from trading_bot_v2.interfaces.strategy import TradingStrategy


class SignalService:
    """Runs strategies and emits signal events."""

    def __init__(self, strategy: TradingStrategy, publisher: EventPublisher) -> None:
        self._strategy = strategy
        self._publisher = publisher

    def process_candle(self, candle_event: Mapping[str, object]) -> None:
        signal_payload = self._strategy.on_candle(candle_event)
        if not signal_payload:
            return
        event = SignalEvent(
            producer=f"signal-service:{self._strategy.strategy_id}",
            payload=signal_payload,
        )
        self._publisher.publish(event.event_name, event.to_dict())
