"""Signal generation service skeleton."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from trading_bot_v2.domain.contracts import SignalEvent
from trading_bot_v2.interfaces.messaging import EventPublisher
from trading_bot_v2.interfaces.strategy import TradingStrategy


class SignalService:
    """Runs strategies and emits signal events."""

    def __init__(self, strategy: TradingStrategy, publisher: EventPublisher) -> None:
        self._strategy = strategy
        self._publisher = publisher
        self._candles_processed = 0
        self._signals_emitted = 0

    def process_candle(self, candle_event: Mapping[str, object]) -> None:
        self._candles_processed += 1
        signal_payload = self._strategy.on_candle(candle_event)
        if not signal_payload:
            return
        self._signals_emitted += 1
        event = SignalEvent(
            producer=f"signal-service:{self._strategy.strategy_id}",
            payload=signal_payload,
        )
        self._publisher.publish(event.event_name, event.to_dict())

    def dashboard_runtime_metadata(self) -> Dict[str, Any]:
        """Counters for dashboard heartbeats (``metadata`` on ``service.heartbeat``)."""
        return {
            "role": "signals",
            "candles_processed": self._candles_processed,
            "signals_emitted": self._signals_emitted,
            "active_strategy_id": self._strategy.strategy_id,
        }
