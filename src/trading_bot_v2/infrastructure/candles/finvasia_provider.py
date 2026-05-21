"""Finvasia / Shoonya minute candles via ``get_time_price_series`` (TPSeries)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from zoneinfo import ZoneInfo

from trading_bot_v2.interfaces.candles import CandleProvider

logger = logging.getLogger("trading_bot_v2.candles.finvasia")

_SHOONYA_TIME_FMT = "%d-%m-%Y %H:%M:%S"


def _parse_shoonya_time(s: str, tz: ZoneInfo) -> datetime:
    s = (s or "").strip()
    dt_naive = datetime.strptime(s, _SHOONYA_TIME_FMT)
    return dt_naive.replace(tzinfo=tz)


def _safe_float(x: Any) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(x: Any) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def load_token_exchange_map_pickle(path: str | Path) -> Dict[str, str]:
    import pickle

    p = Path(path)
    if not p.is_file():
        logger.warning("token_exchange_map pickle not found: %s", p)
        return {}
    with p.open("rb") as f:
        data = pickle.load(f)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


class FinvasiaCandleProvider(CandleProvider):
    """
    ``instrument_token`` is the **Shoonya scrip token** (numeric), not Zerodha's token.

    Uses ``NorenApi.get_time_price_series`` with ``intrv=1`` (1-minute candles).
    """

    def __init__(
        self,
        broker_instance_id: str,
        *,
        user_id: str,
        susertoken: str,
        access_token: str,
        host: str = "https://api.shoonya.com/NorenWClientAPI",
        websocket: str = "wss://api.shoonya.com/NorenWSAPI/",
        default_exchange: str = "NSE",
        timezone: str = "Asia/Kolkata",
        token_exchange_map: Optional[Dict[str, str]] = None,
    ) -> None:
        try:
            from NorenRestApiPy.NorenApi import NorenApi  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "NorenRestApiPy is required for FinvasiaCandleProvider. Install project dependencies."
            ) from exc

        self._broker_instance_id = broker_instance_id
        self._user_id = user_id
        self._default_exchange = (default_exchange or "NSE").upper()
        self._tz = ZoneInfo(timezone)
        self._token_exchange_map = dict(token_exchange_map or {})

        h = (host or "").strip().rstrip("/")
        self._noren_host = (h + "/") if h else "https://api.shoonya.com/NorenWClientAPI/"
        self._api = NorenApi(host=self._noren_host, websocket=websocket)
        self._login_lock = asyncio.Lock()
        self._logged_in = False
        self._susertoken = susertoken
        self._access_token = access_token

    @property
    def broker_instance_id(self) -> str:
        return self._broker_instance_id

    @property
    def provider_name(self) -> str:
        return "finvasia"

    def _exchange_for_token(self, token: int) -> str:
        return self._token_exchange_map.get(str(token), self._default_exchange)

    def _login_sync(self) -> None:
        try:
            self._api.__susertoken = self._susertoken
            self._api.__username = self._user_id
            self._api.__accountid = self._user_id
            self._api.__access_token = self._access_token
            self._api.injectOAuthHeader(self._access_token, self._user_id, self._user_id)
        except Exception as e:
            raise RuntimeError(
                f"Finvasia NorenApi OAuth inject failed (host={self._noren_host!r}): {e}"
            ) from e

    async def _ensure_login(self) -> None:
        if self._logged_in:
            return
        async with self._login_lock:
            if self._logged_in:
                return
            await asyncio.to_thread(self._login_sync)
            self._logged_in = True
            logger.info("[%s] Finvasia candle API session ready", self.broker_instance_id)

    def _tp_row_to_candle(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(row, dict):
            return None
        if row.get("stat") != "Ok":
            return None
        t = row.get("time")
        if not t:
            return None
        try:
            ts = _parse_shoonya_time(str(t), self._tz)
        except ValueError:
            logger.debug("Bad Shoonya time field: %r", t)
            return None
        return {
            "date": ts,
            "open": _safe_float(row.get("into")),
            "high": _safe_float(row.get("inth")),
            "low": _safe_float(row.get("intl")),
            "close": _safe_float(row.get("intc")),
            "volume": _safe_int(row.get("intv")) or _safe_int(row.get("v")),
            "oi": _safe_int(row.get("oi")),
        }

    async def fetch_minute_candles(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> List[Dict[str, Any]]:
        started_at = time.perf_counter()
        await self._ensure_login()

        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=self._tz)
        if to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=self._tz)

        st = int(from_dt.timestamp())
        et = int(to_dt.timestamp())
        exch = self._exchange_for_token(int(instrument_token))
        token_str = str(int(instrument_token))

        def _sync_call() -> Optional[List[Dict[str, Any]]]:
            return self._api.get_time_price_series(
                exch,
                token_str,
                str(st),
                str(et),
                interval="1",
            )

        try:
            raw = await asyncio.to_thread(_sync_call)
        except Exception as e:  # pragma: no cover - network
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.warning(
                "[%s] TPSeries failed exch=%s token=%s %s..%s took_ms=%.1f: %s",
                self.broker_instance_id,
                exch,
                token_str,
                from_dt,
                to_dt,
                elapsed_ms,
                e,
            )
            return []
        if not raw:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            logger.info(
                "[%s] token=%s exch=%s from=%s to=%s raw_rows=0 took_ms=%.1f",
                self.broker_instance_id,
                token_str,
                exch,
                from_dt,
                to_dt,
                elapsed_ms,
            )
            return []

        out: List[Dict[str, Any]] = []
        for row in raw:
            c = self._tp_row_to_candle(row)
            if c is None:
                continue
            ts = c["date"]
            if ts < from_dt or ts >= to_dt:
                continue
            out.append(c)
        out.sort(key=lambda x: x["date"])
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        logger.info(
            "[%s] token=%s exch=%s from=%s to=%s raw_rows=%s parsed_rows=%s took_ms=%.1f",
            self.broker_instance_id,
            token_str,
            exch,
            from_dt,
            to_dt,
            len(raw),
            len(out),
            elapsed_ms,
        )
        return out
