"""Map broker raw ticks to the unified schema (ported from trading-bot v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional
from uuid import uuid4

from trading_bot_v2.domain.contracts.unified_schema import UNIFIED_COLUMNS, UNIFIED_SCHEMA
from trading_bot_v2.services.ticks.tick_context import TickMappingContext, normalize_exchange_token


def _new_tick_id() -> str:
    return str(uuid4())


def _tick_size(ctx: TickMappingContext, exchange_token: Any) -> float:
    return ctx.tick_size_for_exchange_token(exchange_token)


def attach_broker_token_fields(
    unified: dict[str, Any],
    *,
    exchange_token: Optional[str],
    instrument_token: Optional[str],
) -> dict[str, Any]:
    """Add explicit exchange/instrument token fields and instrument_id for consumers."""
    ex = str(exchange_token) if exchange_token is not None else None
    inst = str(instrument_token) if instrument_token is not None else None
    unified["exchange_token"] = ex
    unified["instrument_token"] = inst
    if ex:
        exch = unified.get("exchange")
        if exch:
            unified["instrument_id"] = f"{exch}|{ex}"
        elif inst and "|" in inst:
            unified["instrument_id"] = inst
        else:
            unified["instrument_id"] = ex
    return unified


def map_zerodha_tick(
    tick: Mapping[str, Any],
    ctx: TickMappingContext,
    *,
    batch: str | int | None = None,
) -> dict[str, Any]:
    """Convert a Kite raw tick dict into unified schema (v1 map_tick_to_unified_zerodha)."""
    instrument_raw = tick.get("instrument_token")
    try:
        instrument_token_int = int(float(str(instrument_raw).strip())) if instrument_raw is not None else None
    except (TypeError, ValueError):
        instrument_token_int = None

    exchange_token: Optional[str] = None
    if instrument_token_int is not None:
        exchange_token = normalize_exchange_token(
            ctx.exchange_token_for_instrument(instrument_token_int)
        )

    unified: dict[str, Any] = {}
    for col in UNIFIED_COLUMNS:
        broker_field = UNIFIED_SCHEMA.get(col, {}).get("zerodha")
        if col == "symbol_name":
            value = ctx.symbol_for_exchange_token(exchange_token)
        elif col == "tick_size":
            value = _tick_size(ctx, exchange_token)
        elif col == "exchange":
            value = ctx.exchange_for_exchange_token(exchange_token)
        elif col == "tick_id":
            value = _new_tick_id()
        elif col == "batch":
            value = batch
        elif col == "token":
            value = exchange_token
        elif col == "broker":
            value = "zerodha"
        elif broker_field and broker_field.startswith("ohlc_"):
            ohlc_field = broker_field.split("_", 1)[1]
            value = (tick.get("ohlc") or {}).get(ohlc_field)
        elif broker_field and broker_field.startswith("depth_buy_"):
            parts = broker_field.split("_")
            idx = int(parts[2]) - 1
            field = parts[3]
            buy = (tick.get("depth") or {}).get("buy") or []
            value = buy[idx].get(field) if idx < len(buy) else None
        elif broker_field and broker_field.startswith("depth_sell_"):
            parts = broker_field.split("_")
            idx = int(parts[2]) - 1
            field = parts[3]
            sell = (tick.get("depth") or {}).get("sell") or []
            value = sell[idx].get(field) if idx < len(sell) else None
        else:
            value = tick.get(broker_field) if broker_field else None
        unified[col] = value

    inst_str = str(instrument_token_int) if instrument_token_int is not None else None
    return attach_broker_token_fields(
        unified,
        exchange_token=exchange_token,
        instrument_token=inst_str,
    )


def map_finvasia_tick(
    raw_tick: Mapping[str, Any],
    ctx: TickMappingContext,
    *,
    batch: str | int | None = None,
) -> dict[str, Any]:
    """Convert Shoonya tick dict into unified schema (v1 map_tick_to_unified_finvasia)."""
    token = normalize_exchange_token(raw_tick.get("tk", "")) or ""
    unified: dict[str, Any] = {
        "tick_id": _new_tick_id(),
        "token": token,
        "symbol_name": ctx.symbol_for_exchange_token(token),
        "tick_size": _tick_size(ctx, token),
        "last_price": float(raw_tick.get("lp", 0.0) or 0.0),
        "last_traded_quantity": float(raw_tick.get("ltq", 0.0) or 0.0),
        "average_traded_price": float(raw_tick.get("ap", 0.0) or 0.0),
        "volume_traded": int(float(raw_tick.get("v", 0) or 0)),
        "total_buy_quantity": int(float(raw_tick.get("tbq", 0) or 0)),
        "total_sell_quantity": int(float(raw_tick.get("tsq", 0) or 0)),
        "open_price": float(raw_tick.get("o", 0.0) or 0.0),
        "high_price": float(raw_tick.get("h", 0.0) or 0.0),
        "low_price": float(raw_tick.get("l", 0.0) or 0.0),
        "close_price": float(raw_tick.get("c", 0.0) or 0.0),
        "oi": int(float(raw_tick.get("oi", 0) or 0)),
        "change": float(raw_tick.get("pc", 0.0) or 0.0),
        "exchange": raw_tick.get("e", ""),
        "batch": batch,
        "broker": "finvasia",
    }

    tick_ts = raw_tick.get("ft")
    last_trade_ts = raw_tick.get("ltt")
    if tick_ts is not None:
        try:
            unified["timestamp"] = datetime.fromtimestamp(int(tick_ts))
        except (ValueError, TypeError, OSError):
            unified["timestamp"] = None
    else:
        unified["timestamp"] = None

    if last_trade_ts is not None:
        try:
            unified["last_trade_time"] = datetime.fromtimestamp(int(last_trade_ts))
        except (ValueError, TypeError, OSError):
            unified["last_trade_time"] = None
    else:
        unified["last_trade_time"] = None

    for i in range(1, 6):
        unified[f"depth_buy_{i}_quantity"] = int(float(raw_tick.get(f"bq{i}", 0) or 0))
        unified[f"depth_buy_{i}_price"] = float(raw_tick.get(f"bp{i}", 0.0) or 0.0)
        unified[f"depth_buy_{i}_orders"] = int(float(raw_tick.get(f"bo{i}", 0) or 0))
        unified[f"depth_sell_{i}_quantity"] = int(float(raw_tick.get(f"sq{i}", 0) or 0))
        unified[f"depth_sell_{i}_price"] = float(raw_tick.get(f"sp{i}", 0.0) or 0.0)
        unified[f"depth_sell_{i}_orders"] = int(float(raw_tick.get(f"so{i}", 0) or 0))

    final = {col: unified.get(col) for col in UNIFIED_COLUMNS}
    final["token"] = str(final.get("token") or token)
    final["batch"] = batch
    final["broker"] = "finvasia"

    exchange = str(raw_tick.get("e", "NSE") or "NSE")
    final["exchange"] = exchange
    inst_id = f"{exchange}|{token}" if token else None
    return attach_broker_token_fields(
        final,
        exchange_token=token or None,
        instrument_token=inst_id,
    )


def _angel_exchange_name(exchange_type: Any) -> Optional[str]:
    mapping = {
        1: "NSE",
        2: "NFO",
        3: "BSE",
        4: "BFO",
        5: "MCX",
        7: "NCX_FO",
        13: "CDE_FO",
    }
    try:
        return mapping.get(int(exchange_type))
    except (TypeError, ValueError):
        return None


def map_angelone_tick(
    tick: Mapping[str, Any],
    ctx: TickMappingContext,
    *,
    batch: str | int | None = None,
) -> dict[str, Any]:
    """Convert Angel SmartAPI decoded tick dict into unified schema (v1 map_tick_to_unified)."""
    unified: dict[str, Any] = {}
    token = normalize_exchange_token(tick.get("token", "")) or ""

    for col in UNIFIED_COLUMNS:
        broker_field = UNIFIED_SCHEMA.get(col, {}).get("angelone")
        if col == "symbol_name":
            value = ctx.symbol_for_exchange_token(token) or ""
        elif col == "tick_size":
            value = _tick_size(ctx, token)
        elif col == "tick_id":
            value = _new_tick_id()
        elif col == "batch":
            value = batch
        elif col == "broker":
            value = "angelone"
        elif col == "exchange":
            value = _angel_exchange_name(tick.get("exchange_type"))
        elif broker_field and "best_5_buy_data" in broker_field:
            idx = int(broker_field.split("_")[4]) - 1
            field_type = "_".join(broker_field.split("_")[5:])
            arr = tick.get("best_5_buy_data") or []
            key = field_type.replace("no_of_orders", "no of orders")
            value = arr[idx].get(key) if idx < len(arr) else None
        elif broker_field and "best_5_sell_data" in broker_field:
            idx = int(broker_field.split("_")[4]) - 1
            field_type = "_".join(broker_field.split("_")[5:])
            arr = tick.get("best_5_sell_data") or []
            key = field_type.replace("no_of_orders", "no of orders")
            value = arr[idx].get(key) if idx < len(arr) else None
        else:
            value = tick.get(broker_field) if broker_field else None
        unified[col] = value

    exchange_type = int(tick.get("exchange_type", 1) or 1)
    inst_id = f"{exchange_type}|{token}" if token else None
    return attach_broker_token_fields(
        unified,
        exchange_token=token or None,
        instrument_token=inst_id,
    )
