"""Unit tests for merged futures + equity feature columns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_bot_v2.infrastructure.candles.futures_equity_features import enrich_futures_equity_features


def utc_at(y, m, d, hh, mi) -> datetime:
    return datetime(y, m, d, hh, mi, tzinfo=timezone.utc)


def test_enrich_under_five_volume_window_zero() -> None:
    base = utc_at(2026, 1, 1, 10, 0)
    rows: list = []
    for i in range(3):
        rows.append({"date": base + timedelta(minutes=i), "close": 100.0 + i, "volume": 10 + i, "oi": 100})
    enrich_futures_equity_features(rows)
    for j in range(3):
        assert rows[j]["avg_rolling_volume_5"] == 0.0
        assert rows[j]["avg_rolling_oi_change_5"] == 0.0


def test_enrich_roll_volume_and_premium_discount() -> None:
    base = utc_at(2026, 1, 1, 10, 0)
    rows = []
    for i in range(5):
        rows.append(
            {
                "date": base + timedelta(minutes=i),
                "close": 100.0 + i,
                "volume": 100 * (i + 1),
                "oi": 1000 + 10 * i,
                "close_eq": 99.0 if i % 2 == 0 else 101.0,
            }
        )
    enrich_futures_equity_features(rows)
    last = rows[4]
    assert last["avg_rolling_volume_5"] == sum(100 * (j + 1) for j in range(5)) / 5.0
    assert rows[0]["oi_change"] == 0.0
    assert rows[1]["oi_change"] == 10.0
    assert last["fut_eq_close_diff"] == last["close"] - last["close_eq"]
    assert last["premium_discount"] in {"Premium", "Discount", "No Change"}
