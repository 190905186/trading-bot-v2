"""Construct :class:`CandleProvider` implementations from ``TB2_*`` environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from trading_bot_v2.infrastructure.candles.angelone_provider import (
    DEFAULT_INSTRUMENT_URL,
    AngelOneCandleProvider,
)
from trading_bot_v2.infrastructure.candles.finvasia_provider import (
    FinvasiaCandleProvider,
    load_token_exchange_map_pickle,
)
from trading_bot_v2.infrastructure.candles.zerodha_provider import ZerodhaCandleProvider
from trading_bot_v2.interfaces.candles import CandleProvider


def _truthy_env(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def build_candle_provider_from_env(
    source: Optional[str] = None,
    *,
    broker_instance_id: Optional[str] = None,
) -> Optional[CandleProvider]:
    """
    Mirror ``scripts/run_ticks_service.py`` broker env vars where possible.

    Returns ``None`` for ``mock`` / empty / unknown sources so live aggregation can
    run without a historical provider.
    """
    raw = source if source is not None else os.getenv("TB2_MARKET_DATA_SOURCE", "")
    src = raw.strip().lower()
    bid = (broker_instance_id or os.getenv("TB2_BROKER_INSTANCE_ID") or os.getenv("TB2_BROKER_NAME", "default")).strip()

    if src in {"", "none", "mock"}:
        return None

    tz = os.getenv("TB2_MARKET_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"

    if src == "zerodha":
        api_key = os.getenv("TB2_ZERODHA_API_KEY", "").strip()
        access_token = os.getenv("TB2_ZERODHA_ACCESS_TOKEN", "").strip()
        if not api_key or not access_token:
            raise RuntimeError("TB2_ZERODHA_API_KEY and TB2_ZERODHA_ACCESS_TOKEN are required for Zerodha candles.")
        return ZerodhaCandleProvider(
            bid,
            api_key=api_key,
            access_token=access_token,
            continuous=_truthy_env("TB2_ZERODHA_HISTORICAL_CONTINUOUS", "1"),
        )

    if src == "finvasia":
        user_id = os.getenv("TB2_FINVASIA_USER_ID", "").strip()
        access_token = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()
        susertoken = os.getenv("TB2_FINVASIA_SUSER_TOKEN", "").strip() or access_token
        if not user_id or not access_token:
            raise RuntimeError(
                "TB2_FINVASIA_USER_ID and TB2_FINVASIA_ACCESS_TOKEN are required for Finvasia candles "
                "(OAuth header inject, same as websocket path)."
            )
        map_path = os.getenv("TB2_FINVASIA_TOKEN_EXCH_MAP_PKL", "").strip()
        token_map = load_token_exchange_map_pickle(map_path) if map_path else {}
        return FinvasiaCandleProvider(
            bid,
            user_id=user_id,
            susertoken=susertoken,
            access_token=access_token,
            host=os.getenv("TB2_FINVASIA_HOST", "https://api.shoonya.com/NorenWClientAPI").strip(),
            websocket=os.getenv("TB2_FINVASIA_WEBSOCKET", "wss://api.shoonya.com/NorenWSAPI/").strip(),
            default_exchange=os.getenv("TB2_FINVASIA_DEFAULT_EXCHANGE", "NSE").strip() or "NSE",
            timezone=tz,
            token_exchange_map=token_map or None,
        )

    if src in {"angelone", "angel_one"}:
        api_key = os.getenv("TB2_ANGELONE_API_KEY", "").strip()
        client_code = os.getenv("TB2_ANGELONE_CLIENT_CODE", "").strip()
        password = os.getenv("TB2_ANGELONE_PASSWORD", "").strip()
        totp_secret = os.getenv("TB2_ANGELONE_TOTP_SECRET", "").strip()
        if not all([api_key, client_code, password, totp_secret]):
            raise RuntimeError(
                "TB2_ANGELONE_API_KEY, TB2_ANGELONE_CLIENT_CODE, TB2_ANGELONE_PASSWORD, "
                "and TB2_ANGELONE_TOTP_SECRET are required for Angel One candles."
            )
        cache_pkl = os.getenv("TB2_ANGELONE_INSTRUMENT_CACHE_PKL", "").strip()
        cache_path: Optional[str] = str(Path(cache_pkl).resolve()) if cache_pkl else None
        inst_url = os.getenv("TB2_ANGELONE_INSTRUMENT_URL", "").strip() or DEFAULT_INSTRUMENT_URL
        default_exch = os.getenv("TB2_ANGELONE_DEFAULT_EXCHANGE", "NSE").strip() or "NSE"
        margin_csv = os.getenv("TB2_ANGELONE_MARGIN_CSV", "").strip()
        margin_path: Optional[str] = str(Path(margin_csv).resolve()) if margin_csv else None
        eq_override_s = os.getenv("TB2_ANGELONE_EQUITY_INSTRUMENT_TOKEN", "").strip()
        eq_override: Optional[int] = int(eq_override_s) if eq_override_s.isdigit() else None
        fut_pref_raw = os.getenv("TB2_ANGELONE_FUTURES_EXCHANGE_PREF", "").strip()
        fut_pref = tuple(x.strip().upper() for x in fut_pref_raw.split(",") if x.strip()) if fut_pref_raw else (
            "NFO",
            "BFO",
        )
        return AngelOneCandleProvider(
            bid,
            api_key=api_key,
            client_code=client_code,
            password=password,
            totp_secret=totp_secret,
            timezone=tz,
            instrument_url=inst_url,
            default_exchange=default_exch,
            instrument_cache_path=cache_path,
            margin_csv_path=margin_path,
            equity_instrument_token_override=eq_override,
            futures_exchange_preference=fut_pref,
        )

    raise ValueError(f"Unsupported TB2_MARKET_DATA_SOURCE for candles: {raw!r}")


def build_candle_provider_from_env_safe(
    source: Optional[str] = None,
    *,
    broker_instance_id: Optional[str] = None,
) -> Optional[CandleProvider]:
    """Like :func:`build_candle_provider_from_env` but returns ``None`` on error instead of raising."""
    try:
        return build_candle_provider_from_env(source, broker_instance_id=broker_instance_id)
    except (RuntimeError, ValueError):
        return None
