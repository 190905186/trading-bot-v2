"""Tick mapping context tests."""

from __future__ import annotations

from trading_bot_v2.services.ticks.tick_context import TickMappingContext, normalize_exchange_token
from trading_bot_v2.services.ticks.unified_mapper import map_zerodha_tick


def test_normalize_exchange_token_strips_float_form():
    assert normalize_exchange_token("2885.0") == "2885"
    assert normalize_exchange_token(2885) == "2885"


def test_symbol_lookup_uses_exchange_token_not_instrument_token():
    ctx = TickMappingContext(
        token_symbol_map={"2885": "RELIANCE-EQ"},
        instrument_to_exchange_token={738561: "2885"},
    )
    raw = {"instrument_token": 738561, "last_price": 100.0}
    unified = map_zerodha_tick(raw, ctx)
    assert unified["token"] == "2885"
    assert unified["symbol_name"] == "RELIANCE-EQ"
    assert unified["instrument_token"] == "738561"


def test_symbol_fallback_from_instruments_csv_map():
    ctx = TickMappingContext(
        token_symbol_map={},
        instrument_to_exchange_token={738561: "2885"},
        exchange_token_to_symbol={"2885": "RELIANCE"},
    )
    unified = map_zerodha_tick({"instrument_token": 738561, "last_price": 1.0}, ctx)
    assert unified["symbol_name"] == "RELIANCE"
