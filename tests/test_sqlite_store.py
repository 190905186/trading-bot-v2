"""Tests for SQLite event store and market session."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trading_bot_v2.infrastructure.storage.sqlite_store import SqliteEventStore
from trading_bot_v2.services.market_session import is_within_session


def test_sqlite_store_ticks_and_candles(tmp_path):
    db = tmp_path / "test.db"
    store = SqliteEventStore(db_path=db)
    assert store.insert_tick({"payload": {"broker": "zerodha", "token": "22", "last_price": 100.0}})
    assert store.insert_candle(
        {
            "payload": {
                "broker": "zerodha",
                "token": "22",
                "candle_start": "2026-05-19T09:16:00+05:30",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 10,
            }
        }
    )
    assert store.count_ticks() == 1
    assert store.count_candles() == 1
    store.close()


def test_is_within_session():
    tz = ZoneInfo("Asia/Kolkata")
    inside = datetime(2026, 5, 19, 10, 0, tzinfo=tz)
    outside = datetime(2026, 5, 19, 16, 0, tzinfo=tz)
    assert is_within_session(inside, start_h=9, start_m=15, end_h=15, end_m=30)
    assert not is_within_session(outside, start_h=9, start_m=15, end_h=15, end_m=30)
