"""Simple candle-based strategy for pipeline integration."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from trading_bot_v2.interfaces.strategy import TradingStrategy


class SimpleCandleMomentumStrategy(TradingStrategy):
    """Generates BUY/SELL when close deviates from open by threshold."""

    def __init__(self, threshold_percent: float = 0.15) -> None:
        self._threshold_percent = threshold_percent

    @property
    def strategy_id(self) -> str:
        return "simple_candle_momentum"

    def on_candle(self, candle_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        payload = candle_event.get("payload", candle_event)
        try:
            open_price = float(payload["open"])
            close_price = float(payload["close"])
        except (KeyError, TypeError, ValueError):
            return None

        if open_price <= 0:
            return None
        move_pct = ((close_price - open_price) / open_price) * 100.0
        if abs(move_pct) < self._threshold_percent:
            return None

        signal_type = "BUY" if move_pct > 0 else "SELL"
        confidence = min(1.0, abs(move_pct) / (self._threshold_percent * 2))
        token = str(payload.get("token", payload.get("instrument_id", "UNKNOWN")))
        broker = str(payload.get("broker", "unknown"))
        quantity = int(payload.get("quantity", 1) or 1)

        return {
            "broker": broker,
            "strategy": self.strategy_id,
            "token": token,
            "instrument_id": token,
            "signal_type": signal_type,
            "confidence": round(confidence, 4),
            "last_price": close_price,
            "order_request": {
                "symbol": token,
                "transaction_type": signal_type,
                "quantity": quantity,
                "price": close_price,
                "order_type": "MARKET",
            },
        }
