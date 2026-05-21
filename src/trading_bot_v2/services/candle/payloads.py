"""Normalize broker OHLC rows into closed 1m candle payloads for ``CandleEvent``."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger("trading_bot_v2.candles.payloads")


def _minute_bucket_start(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(second=0, microsecond=0)


def normalized_ohlc_row_to_closed_payload(
    row: Mapping[str, Any],
    *,
    broker: str,
    token: str,
) -> Optional[Dict[str, Any]]:
    """
    Map a provider-normalized row (``date`` + OHLCV) to the same dict shape as
    :class:`MinuteCandleAggregator` emits for ``candles.1m.closed`` consumers.
    """
    raw_dt = row.get("date")
    if raw_dt is None:
        return None
    if isinstance(raw_dt, datetime):
        minute_start = _minute_bucket_start(raw_dt)
    else:
        try:
            minute_start = _minute_bucket_start(datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00")))
        except ValueError:
            logger.debug("Skip candle row with unparseable date: %r", raw_dt)
            return None

    try:
        o = float(row.get("open", 0.0) or 0.0)
        h = float(row.get("high", 0.0) or 0.0)
        lo = float(row.get("low", 0.0) or 0.0)
        c = float(row.get("close", 0.0) or 0.0)
        v_raw = row.get("volume", 0)
        volume = int(float(v_raw)) if v_raw is not None else 0
    except (TypeError, ValueError):
        return None

    oi = row.get("oi")
    if oi is not None:
        try:
            oi = float(oi)
        except (TypeError, ValueError):
            oi = None

    candle_end = minute_start + timedelta(minutes=1)
    payload: Dict[str, Any] = {
        "broker": broker,
        "token": str(token),
        "instrument_id": str(token),
        "timeframe": "1m",
        "candle_start": minute_start.isoformat(),
        "candle_end": candle_end.isoformat(),
        "open": round(o, 4),
        "high": round(h, 4),
        "low": round(lo, 4),
        "close": round(c, 4),
        "volume": volume,
        "oi": oi,
    }

    raw_ceq = row.get("close_eq")
    if raw_ceq is not None:
        try:
            payload["close_eq"] = round(float(raw_ceq), 4)
        except (TypeError, ValueError):
            pass

    for k in ("avg_rolling_volume_5", "oi_change", "avg_rolling_oi_change_5"):
        v = row.get(k)
        if v is None:
            continue
        try:
            payload[k] = round(float(v), 6)
        except (TypeError, ValueError):
            pass

    fed = row.get("fut_eq_close_diff")
    if fed is not None:
        try:
            payload["fut_eq_close_diff"] = round(float(fed), 4)
        except (TypeError, ValueError):
            pass

    pdisc = row.get("premium_discount")
    if pdisc is not None and str(pdisc).strip():
        payload["premium_discount"] = str(pdisc).strip()

    return payload
