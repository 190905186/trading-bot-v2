"""Unified tick mapper tests."""

from __future__ import annotations

from datetime import datetime

from trading_bot_v2.domain.contracts.unified_schema import UNIFIED_COLUMNS
from trading_bot_v2.services.ticks.serialize import prepare_tick_payload
from trading_bot_v2.services.ticks.tick_context import TickMappingContext
from trading_bot_v2.services.ticks.unified_mapper import (
    map_angelone_tick,
    map_finvasia_tick,
    map_zerodha_tick,
)


def test_map_zerodha_uses_exchange_token_and_preserves_naive_timestamp():
    ctx = TickMappingContext(
        token_symbol_map={"738561": "RELIANCE"},
        token_tick_size_map={"738561": 5},
        token_exch_map={"738561": "NSE"},
        instrument_to_exchange_token={256265: "738561"},
    )
    ts = datetime(2026, 5, 19, 10, 30, 0)
    raw = {
        "instrument_token": 256265,
        "exchange_timestamp": ts,
        "last_price": 2500.5,
        "volume_traded": 1000,
        "ohlc": {"open": 2490, "high": 2510, "low": 2485, "close": 2495},
        "depth": {
            "buy": [{"quantity": 10, "price": 2500.0, "orders": 2}],
            "sell": [{"quantity": 5, "price": 2501.0, "orders": 1}],
        },
    }
    unified = map_zerodha_tick(raw, ctx, batch="batch1")
    assert unified["token"] == "738561"
    assert unified["exchange_token"] == "738561"
    assert unified["instrument_token"] == "256265"
    assert unified["broker"] == "zerodha"
    assert unified["batch"] == "batch1"
    assert unified["symbol_name"] == "RELIANCE"
    assert unified["timestamp"] is ts
    assert unified["depth_buy_1_price"] == 2500.0

    serialized = prepare_tick_payload(unified)
    assert serialized["timestamp"] == ts.isoformat()
    assert "astimezone" not in serialized["timestamp"]


def test_map_zerodha_covers_all_unified_columns():
    ctx = TickMappingContext(instrument_to_exchange_token={1: "22"})
    raw = {"instrument_token": 1, "last_price": 1.0}
    unified = map_zerodha_tick(raw, ctx)
    for col in UNIFIED_COLUMNS:
        assert col in unified


def test_map_finvasia_basic_fields():
    ctx = TickMappingContext(token_symbol_map={"22": "ACC"})
    raw = {
        "tk": "22",
        "e": "NSE",
        "lp": 100.5,
        "v": 500,
        "ft": "1716100000",
        "bp1": 100.0,
        "sp1": 101.0,
        "bq1": 10,
    }
    unified = map_finvasia_tick(raw, ctx, batch="batch7")
    assert unified["token"] == "22"
    assert unified["exchange_token"] == "22"
    assert unified["instrument_token"] == "NSE|22"
    assert unified["volume_traded"] == 500
    assert isinstance(unified["timestamp"], datetime)


def test_map_angelone_exchange_and_depth():
    ctx = TickMappingContext()
    message = {
        "token": "1594",
        "exchange_type": 1,
        "exchange_timestamp": datetime(2026, 5, 19, 9, 15, 0),
        "last_traded_price": 100.0,
        "volume_trade_for_the_day": 200,
        "best_5_buy_data": [{"quantity": 1, "price": 99.5, "no of orders": 2}],
        "best_5_sell_data": [{"quantity": 2, "price": 100.5, "no of orders": 3}],
    }
    unified = map_angelone_tick(message, ctx, batch="batch4")
    assert unified["token"] == "1594"
    assert unified["exchange"] == "NSE"
    assert unified["depth_buy_1_price"] == 99.5
    assert unified["volume_traded"] == 200
