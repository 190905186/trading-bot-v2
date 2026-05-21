"""Angel One (SmartAPI) minute candles via ``getCandleData``."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import pickle
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from zoneinfo import ZoneInfo

from trading_bot_v2.infrastructure.candles.futures_equity_features import (
    enrich_futures_equity_features,
    equity_close_by_minute,
    merge_equity_close_onto_futures,
)
from trading_bot_v2.infrastructure.candles.margin_contract_index import (
    FutSegmentPlan,
    InstrumentKind,
    MarginContractIndex,
)
from trading_bot_v2.interfaces.candles import CandleProvider

logger = logging.getLogger("trading_bot_v2.candles.angelone")

DEFAULT_INSTRUMENT_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)


def _fmt_angel_datetime(dt: datetime, tz: ZoneInfo) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt.strftime("%Y-%m-%d %H:%M")


def _build_token_exchange_map(instruments: List[Dict[str, Any]]) -> Dict[int, str]:
    priority = {"NSE": 0, "NFO": 1, "BSE": 2, "MCX": 3, "CDS": 4, "BFO": 5}
    best: Dict[int, Tuple[int, str]] = {}
    for inst in instruments:
        try:
            t = int(inst.get("token"))
        except (TypeError, ValueError):
            continue
        exch = str(inst.get("exch_seg") or "").strip().upper()
        if not exch:
            continue
        pr = priority.get(exch, 50)
        cur = best.get(t)
        if cur is None or pr < cur[0]:
            best[t] = (pr, exch)
    return {t: v[1] for t, v in best.items()}


def _parse_angel_timestamp(date_s: Any, tz: ZoneInfo) -> Optional[datetime]:
    s = str(date_s).strip()
    if not s:
        return None
    normalized = s.replace("Z", "+00:00")
    if " " in normalized and "T" not in normalized[:11]:
        normalized = normalized.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt


def _parse_candle_row(row: List[Any], *, tz: ZoneInfo) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    n = len(row)
    if n == 7:
        date_s, o, h, l, c, v, oi = row
    elif n == 6:
        date_s, o, h, l, c, v = row
        oi = 0
    else:
        return None
    ts = _parse_angel_timestamp(date_s, tz)
    if ts is None:
        return None
    try:
        return {
            "date": ts,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": int(float(v)) if v is not None else 0,
            "oi": float(oi) if oi is not None else None,
        }
    except (TypeError, ValueError):
        return None


def _fetch_instruments_json(url: str, *, timeout_s: int = 120) -> List[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-v2/candles"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - configurable URL
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected instrument master JSON (expected list): {type(data)}")
    return data


def _iso_key(dt: datetime, tz: ZoneInfo) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)
    return dt.isoformat(timespec="seconds")


def _normalize_bounds(from_dt: datetime, to_dt: datetime, tz: ZoneInfo) -> Tuple[datetime, datetime]:
    fd = from_dt if from_dt.tzinfo else from_dt.replace(tzinfo=tz)
    td = to_dt if to_dt.tzinfo else to_dt.replace(tzinfo=tz)
    fd = fd.astimezone(tz) if fd.tzinfo else fd.replace(tzinfo=tz)
    td = td.astimezone(tz) if td.tzinfo else td.replace(tzinfo=tz)
    return fd, td


class AngelOneCandleProvider(CandleProvider):
    """
    ``instrument_token`` is Angel One **exchange token** (numeric).

    Exchange segment (``NSE`` / ``NFO`` / …) is resolved from the Angel master JSON.

    Optional ``margin_csv_path`` aligns futures with sibling cash symbols (margin CSV): merges
    ``close_eq``, adds rolling metrics and premium / discount classification.
    """

    def __init__(
        self,
        broker_instance_id: str,
        *,
        api_key: str,
        client_code: str,
        password: str,
        totp_secret: str,
        timezone: str = "Asia/Kolkata",
        instrument_url: str = DEFAULT_INSTRUMENT_URL,
        default_exchange: str = "NSE",
        instrument_cache_path: Optional[str] = None,
        margin_csv_path: Optional[str] = None,
        equity_instrument_token_override: Optional[int] = None,
        futures_exchange_preference: Sequence[str] = ("NFO", "BFO"),
    ) -> None:
        try:
            from SmartApi import SmartConnect  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "smartapi-python is required for AngelOneCandleProvider. Install project dependencies."
            ) from exc

        try:
            from pyotp import TOTP  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pyotp is required for AngelOneCandleProvider login.") from exc

        self._SmartConnect = SmartConnect
        self._TOTP = TOTP
        self._broker_instance_id = broker_instance_id
        self._api_key = api_key
        self._client_code = client_code
        self._password = password
        self._totp_secret = totp_secret
        self._tz = ZoneInfo(timezone)
        self._instrument_url = instrument_url
        self._default_exchange = (default_exchange or "NSE").upper()
        self._instrument_cache_path = instrument_cache_path
        self._margin_csv_path = str(Path(margin_csv_path).resolve()) if margin_csv_path else None
        self._equity_manual_token = (
            int(equity_instrument_token_override) if equity_instrument_token_override is not None else None
        )
        self._futures_exch_pref: Tuple[str, ...] = tuple(
            x.strip().upper() for x in futures_exchange_preference if str(x).strip()
        ) or ("NFO", "BFO")

        self._client: Any = None
        self._token_exchange: Dict[int, str] = {}
        self._lock = asyncio.Lock()
        self._instruments_loaded = False
        self._margin_index_obj: Optional[MarginContractIndex] = None
        self._margin_index_lock = asyncio.Lock()
        self._candle_fetch_cache: Dict[Tuple[int, str, str], List[Dict[str, Any]]] = {}
        self._fetch_cache_lock = threading.Lock()

    @property
    def broker_instance_id(self) -> str:
        return self._broker_instance_id

    @property
    def provider_name(self) -> str:
        return "angelone"

    def _load_instruments_sync(self) -> None:
        if self._instrument_cache_path:
            p = Path(self._instrument_cache_path)
            if p.is_file():
                with p.open("rb") as f:
                    data = pickle.load(f)
                instruments = data if isinstance(data, list) else []
            else:
                logger.warning("Instrument cache missing %s; fetching URL", p)
                instruments = _fetch_instruments_json(self._instrument_url)
        else:
            instruments = _fetch_instruments_json(self._instrument_url)
        self._token_exchange = _build_token_exchange_map(instruments)
        self._instruments_loaded = True
        logger.info(
            "[%s] Loaded Angel instrument map: %s tokens",
            self.broker_instance_id,
            len(self._token_exchange),
        )

    def _ensure_client_sync(self) -> None:
        if self._client is not None:
            return
        obj = self._SmartConnect(api_key=self._api_key)
        session = obj.generateSession(
            self._client_code,
            self._password,
            self._TOTP(self._totp_secret).now(),
        )
        if (
            not isinstance(session, dict)
            or not session.get("data")
            or not session["data"].get("jwtToken")
        ):
            raise RuntimeError(f"Angel One login failed: {session}")
        self._client = obj

    async def _ensure_ready(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._ensure_client_sync)
            if not self._instruments_loaded:
                await asyncio.to_thread(self._load_instruments_sync)

    async def _ensure_margin_index(self) -> Optional[MarginContractIndex]:
        if not self._margin_csv_path:
            return None
        async with self._margin_index_lock:
            if self._margin_index_obj is None:
                self._margin_index_obj = await asyncio.to_thread(
                    MarginContractIndex.from_csv_path,
                    self._margin_csv_path,
                )
            return self._margin_index_obj

    def _exchange_for(self, token: int) -> str:
        return self._token_exchange.get(int(token), self._default_exchange)

    def _sync_fetch_uncached_parse(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Tuple[List[Dict[str, Any]], int]:
        assert self._client is not None
        exch = self._exchange_for(int(instrument_token))
        from_s = _fmt_angel_datetime(from_dt, self._tz)
        to_s = _fmt_angel_datetime(to_dt, self._tz)
        params: Dict[str, Any] = {
            "exchange": exch,
            "symboltoken": str(int(instrument_token)),
            "interval": "ONE_MINUTE",
            "fromdate": from_s,
            "todate": to_s,
        }
        raw = self._client.getCandleData(params)
        if not raw or raw.get("status") is not True:
            logger.warning(
                "[%s] Angel getCandleData failed token=%s exch=%s %s..%s: %s",
                self.broker_instance_id,
                instrument_token,
                exch,
                from_s,
                to_s,
                raw,
            )
            return [], 0
        candles = raw.get("data") or []
        fd, td = _normalize_bounds(from_dt, to_dt, self._tz)
        out: List[Dict[str, Any]] = []
        for row in candles:
            if not isinstance(row, (list, tuple)):
                continue
            parsed = _parse_candle_row(list(row), tz=self._tz)
            if parsed is None:
                continue
            ts = parsed["date"]
            if ts < fd or ts >= td:
                continue
            out.append(parsed)
        out.sort(key=lambda x: x["date"])
        return out, len(candles)

    async def _fetch_candles_cached(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Tuple[List[Dict[str, Any]], int]:
        fd, td = _normalize_bounds(from_dt, to_dt, self._tz)
        ck = (
            int(instrument_token),
            _iso_key(fd, self._tz),
            _iso_key(td, self._tz),
        )
        with self._fetch_cache_lock:
            hit = self._candle_fetch_cache.get(ck)
            if hit is not None:
                return [copy.copy(r) for r in hit], 0

        assert self._client is not None
        parsed, raw_n = await asyncio.to_thread(
            self._sync_fetch_uncached_parse,
            int(instrument_token),
            fd,
            td,
        )

        freeze = copy.deepcopy(parsed)
        with self._fetch_cache_lock:
            self._candle_fetch_cache[ck] = freeze
        return [copy.copy(r) for r in parsed], raw_n

    async def fetch_minute_candles(
        self,
        instrument_token: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> List[Dict[str, Any]]:
        started_at = time.perf_counter()
        await self._ensure_ready()
        assert self._client is not None

        if from_dt > to_dt:
            from_dt, to_dt = to_dt, from_dt

        fd, td = _normalize_bounds(from_dt, to_dt, self._tz)

        if not self._margin_csv_path:
            bars, raw_count = await self._fetch_candles_cached(int(instrument_token), fd, td)
            self._log_fetch(instrument_token, fd, td, raw_count, len(bars), started_at, suffix="legacy")
            return bars

        try:
            index = await self._ensure_margin_index()
        except OSError:
            bars, raw_count = await self._fetch_candles_cached(int(instrument_token), fd, td)
            self._log_fetch(
                instrument_token,
                fd,
                td,
                raw_count,
                len(bars),
                started_at,
                suffix="fallback_no_margin_index",
            )
            return bars

        if index is None:
            bars, raw_count = await self._fetch_candles_cached(int(instrument_token), fd, td)
            self._log_fetch(instrument_token, fd, td, raw_count, len(bars), started_at, suffix="fallback")
            return bars

        kind, mrow = index.classify(int(instrument_token))
        segments: List[FutSegmentPlan] = []
        eq_token: Optional[int] = self._equity_manual_token
        underlying_name: Optional[str] = None

        if kind == InstrumentKind.FUT and mrow is not None:
            underlying_name = mrow.name
            segments = [
                FutSegmentPlan(fut_token=int(instrument_token), effective_from=fd, effective_to=td),
            ]
            if eq_token is None:
                eq_token = index.resolve_eq_token_for_underlying(underlying_name)

        elif kind == InstrumentKind.EQ and mrow is not None:
            underlying_name = mrow.name
            if eq_token is None:
                eq_token = int(instrument_token)
            segments = index.plan_fut_segments_for_range(
                underlying_name,
                fd,
                td,
                self._tz,
                prefer_exchanges=self._futures_exch_pref,
            )

        elif kind == InstrumentKind.UNKNOWN:
            bars, raw_count = await self._fetch_candles_cached(int(instrument_token), fd, td)
            self._log_fetch(
                instrument_token,
                fd,
                td,
                raw_count,
                len(bars),
                started_at,
                suffix="unknown_margin_class",
            )
            return bars

        if not segments:
            logger.warning("[%s] No futures segments resolved for token=%s", self.broker_instance_id, instrument_token)
            return []

        stitched: List[Dict[str, Any]] = []

        if kind == InstrumentKind.EQ:
            for seg in segments:
                chunk, _ = await self._fetch_candles_cached(seg.fut_token, seg.effective_from, seg.effective_to)
                for b in chunk:
                    b["__publish_token__"] = str(seg.fut_token)
                stitched.extend(chunk)
        else:
            chunk, _ = await self._fetch_candles_cached(int(instrument_token), fd, td)
            for b in chunk:
                b["__publish_token__"] = str(instrument_token)
            stitched = chunk

        stitched.sort(key=lambda x: x["date"])

        if eq_token is not None:
            eq_bars, _ = await self._fetch_candles_cached(eq_token, fd, td)
            eq_map = equity_close_by_minute(eq_bars)
            merge_equity_close_onto_futures(stitched, eq_map)
        else:
            logger.warning("[%s] No EQ token resolved for underlying=%s; skip close_eq merge", self.broker_instance_id, underlying_name)
            for r in stitched:
                r["close_eq"] = None

        enrich_futures_equity_features(stitched)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        logger.info(
            "[%s] enriched token=%s segments=%s eq_token=%s from=%s to=%s stitched=%s took_ms=%.1f",
            self.broker_instance_id,
            instrument_token,
            len(segments),
            eq_token,
            _iso_key(fd, self._tz),
            _iso_key(td, self._tz),
            len(stitched),
            elapsed_ms,
        )
        return stitched

    def _log_fetch(
        self,
        instrument_token: int,
        fd: datetime,
        td: datetime,
        raw_count: int,
        parsed_n: int,
        started_at: float,
        *,
        suffix: str = "",
    ) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        tail = (" " + suffix) if suffix else ""
        logger.info(
            "[%s] token=%s exch=%s from=%s to=%s raw_rows=%s parsed_rows=%s took_ms=%.1f%s",
            self.broker_instance_id,
            instrument_token,
            self._exchange_for(int(instrument_token)),
            _fmt_angel_datetime(fd, self._tz),
            _fmt_angel_datetime(td, self._tz),
            raw_count,
            parsed_n,
            elapsed_ms,
            tail,
        )
