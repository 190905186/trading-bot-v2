"""OHLC open-at-extremes signal (ported from ``angelone_async_old/utils.generate_signals``)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from trading_bot_v2.interfaces.strategy import TradingStrategy


def generate_ohlc_open_range_signal(
    open_price: float,
    high: float,
    low: float,
    tick_size: float,
    multiplier: float = 1.0,
    *,
    abs_tolerance: float = 0.0,
) -> str:
    """
    Classify a single OHLC bar using open proximity to low/high and a tick-derived band.

    With ``abs_tolerance == 0`` (default), comparisons match the legacy ``==`` semantics.
    With a small positive tolerance, float OHLC from brokers can still match reliably.

    Returns one of: ``Hold``, ``Buy``, ``Sell``, ``Donottrade``.
    """
    delta = (tick_size or 0.0) * multiplier
    if delta <= 0:
        delta = 0.05
    tol = float(abs_tolerance)

    def eq(a: float, b: float) -> bool:
        if tol <= 0.0:
            return a == b
        return abs(a - b) <= tol

    if (eq(open_price, low) or eq(open_price, high)) and eq(low, high):
        return "Hold"
    if eq(open_price, low + delta) and eq(open_price, high - delta):
        return "Hold"
    if (eq(open_price, low) or eq(open_price, low + delta)) and (high - open_price >= delta):
        return "Buy"
    if (eq(open_price, high) or eq(open_price, high - delta)) and (open_price - low >= delta):
        return "Sell"
    return "Donottrade"


class OhlcOpenRangeStrategy(TradingStrategy):
    """
    Emits a tradable signal only on ``Buy`` / ``Sell`` from :func:`generate_ohlc_open_range_signal`.

    Constructor arguments match the nature of this rule: ``tick_size`` and ``multiplier``.
    If the candle payload includes a numeric ``tick_size``, it overrides the instance default
    for that bar only (instrument-specific ticks).
    """

    def __init__(
        self,
        tick_size: float = 0.05,
        multiplier: float = 1.0,
        *,
        abs_tolerance: float = 0.0,
    ) -> None:
        self._tick_size = float(tick_size)
        self._multiplier = float(multiplier)
        self._abs_tolerance = float(abs_tolerance)

    @property
    def strategy_id(self) -> str:
        return "ohlc_open_range"

    def dashboard_metadata(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_kind": "ohlc_open_range",
            "tick_size": self._tick_size,
            "multiplier": self._multiplier,
            "abs_tolerance": self._abs_tolerance,
        }

    def configure(self, options: Mapping[str, Any]) -> None:
        if "tick_size" in options:
            self._tick_size = float(options["tick_size"])
        if "multiplier" in options:
            self._multiplier = float(options["multiplier"])
        if "abs_tolerance" in options:
            self._abs_tolerance = float(options["abs_tolerance"])

    def on_candle(self, candle_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        payload = candle_event.get("payload", candle_event)
        try:
            o = float(payload["open"])
            h = float(payload["high"])
            l = float(payload["low"])
            c = float(payload["close"])
        except (KeyError, TypeError, ValueError):
            return None

        tick = self._tick_size
        raw_ts = payload.get("tick_size")
        if raw_ts is not None:
            try:
                tick = float(raw_ts)
            except (TypeError, ValueError):
                pass

        label = generate_ohlc_open_range_signal(
            o,
            h,
            l,
            tick,
            self._multiplier,
            abs_tolerance=self._abs_tolerance,
        )
        if label not in {"Buy", "Sell"}:
            return None

        signal_type = "BUY" if label == "Buy" else "SELL"
        token = str(payload.get("token", payload.get("instrument_id", "UNKNOWN")))
        broker = str(payload.get("broker", "unknown"))
        quantity = int(payload.get("quantity", 1) or 1)

        return {
            "broker": broker,
            "strategy": self.strategy_id,
            "token": token,
            "instrument_id": token,
            "signal_type": signal_type,
            "confidence": 1.0,
            "last_price": c,
            "order_request": {
                "symbol": token,
                "transaction_type": signal_type,
                "quantity": quantity,
                "price": c,
                "order_type": "MARKET",
            },
            "meta": {
                "ohlc_signal": label,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "tick_size_used": tick,
                "multiplier": self._multiplier,
                "abs_tolerance": self._abs_tolerance,
            },
        }
