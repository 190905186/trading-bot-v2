"""Closed-candle payload mapping with optional Angel enrichment fields."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_bot_v2.services.candle.payloads import normalized_ohlc_row_to_closed_payload


def test_payload_passes_enriched_fields() -> None:
    dt = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    row = {
        "date": dt,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 10,
        "oi": 100.0,
        "close_eq": 1.4,
        "avg_rolling_volume_5": 12.3,
        "oi_change": 1.0,
        "avg_rolling_oi_change_5": 0.5,
        "fut_eq_close_diff": 0.1,
        "premium_discount": "Premium",
    }
    out = normalized_ohlc_row_to_closed_payload(row, broker="angelone", token="66693")
    assert out is not None
    assert out["close_eq"] == 1.4
    assert out["premium_discount"] == "Premium"
    assert "fut_eq_close_diff" in out
