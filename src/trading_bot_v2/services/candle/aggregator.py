"""Minute candle aggregator that consumes tick events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CandleState:
    broker: str
    token: str
    minute_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class MinuteCandleAggregator:
    """Builds 1-minute candles from tick events."""

    def __init__(self) -> None:
        self._state: Dict[str, CandleState] = {}

    def process_tick_event(self, tick_event: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        payload = tick_event.get("payload", tick_event)
        broker = str(payload.get("broker", "unknown"))
        token = str(payload.get("token", payload.get("instrument_id", "UNKNOWN")))
        price = float(payload.get("last_price", 0.0) or 0.0)
        volume = int(payload.get("volume", 0) or 0)
        ts = _parse_ts(payload.get("timestamp"))
        minute_start = ts.replace(second=0, microsecond=0)
        key = f"{broker}:{token}"

        current = self._state.get(key)
        if current is None:
            self._state[key] = CandleState(
                broker=broker,
                token=token,
                minute_start=minute_start,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
            )
            return None

        if minute_start == current.minute_start:
            current.high = max(current.high, price)
            current.low = min(current.low, price)
            current.close = price
            current.volume += volume
            return None

        closed_candle = {
            "broker": current.broker,
            "token": current.token,
            "instrument_id": current.token,
            "timeframe": "1m",
            "candle_start": current.minute_start.isoformat(),
            "candle_end": (current.minute_start + timedelta(minutes=1)).isoformat(),
            "open": round(current.open, 4),
            "high": round(current.high, 4),
            "low": round(current.low, 4),
            "close": round(current.close, 4),
            "volume": current.volume,
            "oi": None,
        }

        self._state[key] = CandleState(
            broker=broker,
            token=token,
            minute_start=minute_start,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=volume,
        )
        return closed_candle
