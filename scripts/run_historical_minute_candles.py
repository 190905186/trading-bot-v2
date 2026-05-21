"""Historical 1m candles: one-shot session backfill or poll mode with rps/rpm/rpd batching."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.infrastructure.candles.factory import build_candle_provider_from_env  # noqa: E402
from trading_bot_v2.infrastructure.messaging import RedisStreamPublisher  # noqa: E402
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter  # noqa: E402
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider  # noqa: E402
from trading_bot_v2.services.market_session import is_within_session  # noqa: E402
from trading_bot_v2.services.candle.historical_batching import (  # noqa: E402
    HistoricalBatchPlan,
    HistoricalRateLimits,
    apply_num_batches_override,
    compute_batch_plan,
)
from trading_bot_v2.services.candle.payloads import normalized_ohlc_row_to_closed_payload  # noqa: E402
from trading_bot_v2.services.candle.service import CandleService  # noqa: E402

logger = logging.getLogger("trading_bot_v2.historical_minute_candles")

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _parse_tokens(raw: str) -> List[int]:
    out: List[int] = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        out.append(int(part, 10))
    return out


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return float(str(raw).strip())


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip(), 10)


def _parse_hhmm(raw: str, *, label: str) -> Tuple[int, int]:
    m = _HHMM_RE.match(raw.strip())
    if not m:
        raise ValueError(f"{label} must be HH:MM, got {raw!r}")
    h, mi = int(m.group(1), 10), int(m.group(2), 10)
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        raise ValueError(f"Invalid time for {label}: {raw!r}")
    return h, mi


def _session_bounds_for_date(
    d: datetime,
    *,
    start_h: int,
    start_m: int,
    end_h: int,
    end_m: int,
) -> Tuple[datetime, datetime]:
    tz = d.tzinfo
    if tz is None:
        raise ValueError("session date must be timezone-aware")
    start = d.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = d.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if end <= start:
        raise ValueError("session end must be after session start")
    return start, end


def _minutes_between(a: datetime, b: datetime) -> int:
    return max(1, int(math.ceil((b - a).total_seconds() / 60.0)))


def _parse_iso_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _load_state(path: Path) -> Tuple[Dict[str, str], Set[Tuple[str, str]]]:
    if not path.is_file():
        return {}, set()
    data = json.loads(path.read_text(encoding="utf-8"))
    wm_raw = data.get("watermarks") or {}
    watermarks: Dict[str, str] = {str(k): str(v) for k, v in wm_raw.items()}
    dedupe_raw = data.get("dedupe") or []
    dedupe: Set[Tuple[str, str]] = set()
    for item in dedupe_raw:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            dedupe.add((str(item[0]), str(item[1])))
    return watermarks, dedupe


def _save_state(path: Path, watermarks: Mapping[str, str], dedupe: Set[Tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "watermarks": dict(watermarks),
        "dedupe": [list(x) for x in sorted(dedupe)],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class _UsageCounters:
    """Rolling minute and calendar-day request counts in a timezone."""

    def __init__(self, *, rpm: int, rpd: int, tz: ZoneInfo) -> None:
        self._rpm = rpm
        self._rpd = rpd
        self._tz = tz
        self._minute_key: Optional[int] = None
        self._minute_count = 0
        self._day_key: Optional[str] = None
        self._day_count = 0

    def _rollover(self, now: datetime) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=self._tz)
        slot = int(now.timestamp() // 60)
        if self._minute_key != slot:
            self._minute_key = slot
            self._minute_count = 0
        day = now.astimezone(self._tz).strftime("%Y-%m-%d")
        if self._day_key != day:
            self._day_key = day
            self._day_count = 0

    async def acquire_slot(self, now: datetime) -> None:
        self._rollover(now)
        if self._rpd > 0 and self._day_count >= self._rpd:
            next_midnight = now.astimezone(self._tz).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            wait = max(0.0, (next_midnight - now.astimezone(self._tz)).total_seconds())
            logger.warning("Daily request cap reached (rpd=%s); sleeping %.0fs", self._rpd, wait)
            await asyncio.sleep(wait + 0.25)
            self._rollover(datetime.now(self._tz))
        while self._minute_count >= self._rpm:
            wake = (int(now.timestamp() // 60) + 1) * 60
            wait = max(0.05, wake - now.timestamp() + 0.05)
            logger.debug("Minute rpm cap reached; sleeping %.2fs", wait)
            await asyncio.sleep(wait)
            now = datetime.now(self._tz)
            self._rollover(now)

    def record(self, now: datetime) -> None:
        self._rollover(now)
        self._minute_count += 1
        self._day_count += 1


def _is_rate_limited_exc(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or ("rate" in msg and "limit" in msg)


def _maybe_persist_state(
    path: Optional[Path],
    watermarks: Mapping[str, str],
    dedupe: Set[Tuple[str, str]],
    persist_counter: List[int],
    persist_every: int,
) -> None:
    if path is None or persist_every <= 0:
        return
    persist_counter[0] += 1
    if persist_counter[0] % persist_every == 0:
        _save_state(path, watermarks, dedupe)


async def _publish_rows_for_token(
    *,
    token: int,
    rows: Iterable[Mapping[str, Any]],
    broker: str,
    dedupe: Set[Tuple[str, str]],
    service: CandleService,
    watermarks: Dict[str, str],
    state_path: Optional[Path],
    persist_every: int,
    persist_counter: List[int],
) -> None:
    tok_s = str(token)
    last_start: Optional[datetime] = None
    for row in rows:
        row_d: Mapping[str, Any]
        if isinstance(row, dict):
            row_d = dict(row)
        else:
            row_d = row
        pub = row_d.get("__publish_token__") if isinstance(row_d, dict) else None
        effective = pub if isinstance(pub, str) and pub else tok_s
        if isinstance(row_d, dict) and "__publish_token__" in row_d:
            row_d = {k: v for k, v in row_d.items() if k != "__publish_token__"}
        payload = normalized_ohlc_row_to_closed_payload(row_d, broker=broker, token=effective)
        if payload is None:
            continue
        cs = str(payload.get("candle_start", ""))
        key = (effective, cs)
        if key in dedupe:
            continue
        dedupe.add(key)
        service.publish_closed_candle(payload)
        try:
            last_start = _parse_iso_dt(cs)
        except ValueError:
            last_start = None
    if last_start is not None:
        nxt = (last_start + timedelta(minutes=1)).isoformat()
        watermarks[tok_s] = nxt
    _maybe_persist_state(state_path, watermarks, dedupe, persist_counter, persist_every)


async def _fetch_with_retry(
    provider: Any,
    token: int,
    from_dt: datetime,
    to_dt: datetime,
    *,
    max_retries: int = 4,
) -> List[Dict[str, Any]]:
    delay = 1.0
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return await provider.fetch_minute_candles(token, from_dt, to_dt)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limited_exc(exc) and attempt + 1 < max_retries:
                logger.warning("Rate limited for token %s; retry in %.1fs: %s", token, delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, 60.0)
                continue
            raise
    assert last_exc is not None
    raise last_exc


async def _sleep_until_next_minute_plus_offset(*, tz: ZoneInfo, offset_sec: float) -> None:
    now = datetime.now(tz)
    next_minute_start = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    target = next_minute_start + timedelta(seconds=offset_sec)
    wait = (target - now).total_seconds()
    if wait > 0:
        await asyncio.sleep(wait)


def _interval_sec(rps: float) -> float:
    return max(1.0 / rps, 1e-6)


def _resolve_tokens(cli_tokens: Optional[str]) -> str:
    if cli_tokens and cli_tokens.strip():
        return cli_tokens.strip()
    env_hist = os.getenv("TB2_HIST_TOKENS", "").strip()
    if env_hist:
        return env_hist
    hist_batches = os.getenv("TB2_HIST_BATCHES", "").strip() or os.getenv("TB2_TICK_BATCH", "").strip()
    if hist_batches:
        from trading_bot_v2.token_universe.loader import batch_token_ints, load_batches, universe_dir_from_env

        universe = universe_dir_from_env()
        names = [b.strip() for b in hist_batches.split(",") if b.strip()]
        if len(names) == 1:
            ints = batch_token_ints(names[0], universe)
        else:
            all_b = load_batches(universe)
            seen: set[int] = set()
            ints = []
            for name in names:
                for t in all_b.get(name, []):
                    if t not in seen:
                        seen.add(t)
                        ints.append(t)
        if not ints:
            raise SystemExit(f"No tokens in batch(es) {hist_batches!r}")
        source = os.getenv("TB2_MARKET_DATA_SOURCE", "").strip().lower()
        if source == "zerodha":
            from trading_bot_v2.token_universe.loader import resolve_zerodha_instrument_token_ints

            ints = resolve_zerodha_instrument_token_ints(ints, directory=universe)
        return ",".join(str(t) for t in ints)
    env_inst = os.getenv("TB2_INSTRUMENTS", "").strip()
    if not env_inst:
        raise SystemExit(
            "No tokens: pass --tokens or set TB2_HIST_TOKENS (instrument_token ints, comma-separated)"
        )
    pairs = [p for p in env_inst.split(",") if p.strip()]
    nums: List[str] = []
    for p in pairs:
        if "|" in p:
            _, right = p.split("|", 1)
            nums.append(right.strip())
        else:
            nums.append(p.strip())
    return ",".join(nums)


def _default_session_minutes(
    *,
    tz: ZoneInfo,
    start_h: int,
    start_m: int,
    end_h: int,
    end_m: int,
) -> int:
    anchor = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    s, e = _session_bounds_for_date(
        anchor.replace(tzinfo=tz), start_h=start_h, start_m=start_m, end_h=end_h, end_m=end_m
    )
    return _minutes_between(s, e)


async def _run_poll(
    *,
    tokens: List[int],
    plan: HistoricalBatchPlan,
    limits: HistoricalRateLimits,
    tz: ZoneInfo,
    poll_offset_sec: float,
    session_start_h: int,
    session_start_m: int,
    session_end_h: int,
    session_end_m: int,
    service: CandleService,
    provider: Any,
    state_path: Optional[Path],
    persist_every: int,
    fail_on_error: bool,
) -> None:
    watermarks, dedupe = _load_state(state_path) if state_path else ({}, set())
    persist_counter = [0]
    counters = _UsageCounters(rpm=limits.rpm, rpd=limits.rpd, tz=tz)
    broker = provider.provider_name
    interval = _interval_sec(limits.rps)

    logger.info(
        "Poll mode: batches=%s budget/min=%s rps=%s rpm=%s rpd=%s tokens=%s",
        plan.num_batches,
        plan.per_minute_budget,
        limits.rps,
        limits.rpm,
        limits.rpd,
        len(tokens),
    )

    while True:
        await _sleep_until_next_minute_plus_offset(tz=tz, offset_sec=poll_offset_sec)
        now = datetime.now(tz)
        if not is_within_session(
            now,
            start_h=session_start_h,
            start_m=session_start_m,
            end_h=session_end_h,
            end_m=session_end_m,
        ):
            logger.info(
                "Outside market session (%02d:%02d–%02d:%02d %s), skipping poll fetch",
                session_start_h,
                session_start_m,
                session_end_h,
                session_end_m,
                tz.key if hasattr(tz, "key") else tz,
            )
            continue
        minute_floor = now.replace(second=0, microsecond=0)
        to_dt = minute_floor
        epoch_min = int(now.timestamp() // 60)
        batch_idx = epoch_min % plan.num_batches
        batch_tokens = plan.batches[batch_idx]
        if not batch_tokens:
            continue
        logger.debug("Active batch %s/%s size=%s", batch_idx, plan.num_batches, len(batch_tokens))

        session_open_today, _ = _session_bounds_for_date(
            minute_floor,
            start_h=session_start_h,
            start_m=session_start_m,
            end_h=session_end_h,
            end_m=session_end_m,
        )

        for tok in batch_tokens:
            await counters.acquire_slot(datetime.now(tz))
            tok_s = str(tok)
            if tok_s in watermarks:
                try:
                    from_dt = _parse_iso_dt(watermarks[tok_s])
                except ValueError:
                    from_dt = session_open_today
            else:
                from_dt = session_open_today

            if from_dt >= to_dt:
                await asyncio.sleep(interval)
                continue

            try:
                rows = await _fetch_with_retry(provider, tok, from_dt, to_dt)
            except Exception as exc:  # noqa: BLE001
                logger.exception("fetch failed for token %s", tok)
                counters.record(datetime.now(tz))
                await asyncio.sleep(interval)
                if fail_on_error:
                    raise
                continue

            await _publish_rows_for_token(
                token=tok,
                rows=rows,
                broker=broker,
                dedupe=dedupe,
                service=service,
                watermarks=watermarks,
                state_path=state_path,
                persist_every=persist_every,
                persist_counter=persist_counter,
            )
            counters.record(datetime.now(tz))
            await asyncio.sleep(interval)

        if state_path and persist_every > 0:
            _save_state(state_path, watermarks, dedupe)


async def _run_oneshot(
    *,
    tokens: List[int],
    limits: HistoricalRateLimits,
    session_start: datetime,
    session_end: datetime,
    tz: ZoneInfo,
    service: CandleService,
    provider: Any,
    state_path: Optional[Path],
    persist_every: int,
    fail_on_error: bool,
) -> None:
    watermarks, dedupe = _load_state(state_path) if state_path else ({}, set())
    persist_counter = [0]
    counters = _UsageCounters(rpm=limits.rpm, rpd=limits.rpd, tz=tz)
    broker = provider.provider_name
    interval = _interval_sec(limits.rps)

    logger.info(
        "One-shot: %s..%s rps=%s rpm=%s rpd=%s tokens=%s",
        session_start.isoformat(),
        session_end.isoformat(),
        limits.rps,
        limits.rpm,
        limits.rpd,
        len(tokens),
    )

    for tok in tokens:
        await counters.acquire_slot(datetime.now(tz))
        tok_s = str(tok)
        if tok_s in watermarks:
            try:
                from_dt = max(_parse_iso_dt(watermarks[tok_s]), session_start)
            except ValueError:
                from_dt = session_start
        else:
            from_dt = session_start
        to_dt = session_end
        if from_dt >= to_dt:
            counters.record(datetime.now(tz))
            await asyncio.sleep(interval)
            continue
        try:
            rows = await _fetch_with_retry(provider, tok, from_dt, to_dt)
        except Exception:  # noqa: BLE001
            logger.exception("fetch failed for token %s", tok)
            counters.record(datetime.now(tz))
            await asyncio.sleep(interval)
            if fail_on_error:
                raise
            continue
        await _publish_rows_for_token(
            token=tok,
            rows=rows,
            broker=broker,
            dedupe=dedupe,
            service=service,
            watermarks=watermarks,
            state_path=state_path,
            persist_every=persist_every,
            persist_counter=persist_counter,
        )
        counters.record(datetime.now(tz))
        await asyncio.sleep(interval)

    if state_path and persist_every > 0:
        _save_state(state_path, watermarks, dedupe)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Publish historical 1m candles to Redis (rate-limited).")
    p.add_argument("--mode", choices=("poll", "one-shot"), default=os.getenv("TB2_HIST_MODE", "poll"))
    p.add_argument("--tokens", default=None, help="Comma-separated instrument_token ints (or TB2_HIST_TOKENS)")
    p.add_argument("--timezone", default=os.getenv("TB2_MARKET_TIMEZONE", "Asia/Kolkata"))
    p.add_argument("--redis-url", default=os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0"))
    p.add_argument(
        "--session-start",
        default=os.getenv("TB2_HIST_SESSION_START", "09:15"),
        help="Session open HH:MM in market TZ (also used to derive default session minutes)",
    )
    p.add_argument(
        "--session-end",
        default=os.getenv("TB2_HIST_SESSION_END", "15:30"),
        help="Session close HH:MM in market TZ",
    )
    p.add_argument(
        "--session-minutes",
        type=int,
        default=_env_int("TB2_HIST_SESSION_MINUTES", 0),
        help="Trading minutes T for rpd batch sizing (0 = derive from session-start/end)",
    )
    p.add_argument("--date", default=os.getenv("TB2_HIST_DATE", ""), help="YYYY-MM-DD for one-shot (market TZ day)")
    p.add_argument("--rps", type=float, default=None, help="Override TB2_HIST_RPS")
    p.add_argument("--rpm", type=int, default=None, help="Override TB2_HIST_RPM")
    p.add_argument("--rpd", type=int, default=None, help="Override TB2_HIST_RPD (0 disables)")
    p.add_argument(
        "--poll-offset-sec",
        type=float,
        default=_env_float("TB2_HIST_POLL_OFFSET_SEC", 3.0),
        help="Sleep this many seconds after each minute boundary before fetching",
    )
    p.add_argument(
        "--num-batches",
        type=int,
        default=0,
        help="Override computed batch count (must be >= computed minimum)",
    )
    p.add_argument("--state-path", default=os.getenv("TB2_HIST_STATE_PATH", "").strip() or None)
    p.add_argument("--persist-every", type=int, default=_env_int("TB2_HIST_PERSIST_EVERY", 20))
    p.add_argument("--fail-on-error", action="store_true", default=False)
    p.add_argument("--log-level", default=os.getenv("TB2_HIST_LOG_LEVEL", "INFO"))
    return p


def main() -> None:
    args = _build_arg_parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    tz = ZoneInfo(args.timezone)
    rps = float(args.rps) if args.rps is not None else _env_float("TB2_HIST_RPS", 2.0)
    rpm = int(args.rpm) if args.rpm is not None else _env_int("TB2_HIST_RPM", 60)
    rpd = int(args.rpd) if args.rpd is not None else _env_int("TB2_HIST_RPD", 0)
    limits = HistoricalRateLimits(rps=rps, rpm=rpm, rpd=max(0, rpd))

    tokens_raw = _resolve_tokens(args.tokens)
    tokens = _parse_tokens(tokens_raw)
    if not tokens:
        raise SystemExit("No instrument tokens after parsing")

    sh, sm = _parse_hhmm(args.session_start, label="--session-start")
    eh, em = _parse_hhmm(args.session_end, label="--session-end")
    session_minutes = int(args.session_minutes)
    if session_minutes <= 0:
        session_minutes = _default_session_minutes(
            tz=tz, start_h=sh, start_m=sm, end_h=eh, end_m=em
        )

    base_plan = compute_batch_plan(tokens, session_minutes=session_minutes, limits=limits)
    plan = (
        apply_num_batches_override(base_plan, tokens, int(args.num_batches))
        if int(args.num_batches) > 0
        else base_plan
    )

    state_path = Path(args.state_path).resolve() if args.state_path else None

    provider = build_candle_provider_from_env()
    if provider is None:
        raise SystemExit("No historical CandleProvider (set TB2_MARKET_DATA_SOURCE to zerodha/finvasia/angelone)")

    publisher = RedisStreamPublisher(redis_url=args.redis_url)
    service = CandleService(publisher=publisher, provider=provider, producer_label="historical-minute-candles")

    service_name = os.getenv("TB2_SERVICE_NAME", "").strip() or "historical-minute-candles"
    poll_mode = args.mode == "poll"

    def _heartbeat_metadata() -> dict:
        meta: dict = {
            "role": "historical_candles",
            "mode": args.mode,
            "token_count": len(tokens),
            "batch_plan_batches": plan.num_batches,
            "session_start": args.session_start,
            "session_end": args.session_end,
            **service.dashboard_runtime_metadata(),
        }
        if poll_mode:
            meta["poll_active"] = is_within_session(
                datetime.now(tz),
                start_h=sh,
                start_m=sm,
                end_h=eh,
                end_m=em,
            )
        return meta

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name=service_name,
        resource_provider=ProcessResourceHealthProvider(service_name).get_health,
        metadata_factory=_heartbeat_metadata,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    if args.mode == "poll":
        asyncio.run(
            _run_poll(
                tokens=tokens,
                plan=plan,
                limits=limits,
                tz=tz,
                poll_offset_sec=float(args.poll_offset_sec),
                session_start_h=sh,
                session_start_m=sm,
                session_end_h=eh,
                session_end_m=em,
                service=service,
                provider=provider,
                state_path=state_path,
                persist_every=int(args.persist_every),
                fail_on_error=bool(args.fail_on_error),
            )
        )
        return

    date_s = str(args.date).strip()
    if not date_s:
        raise SystemExit("one-shot requires --date YYYY-MM-DD (or TB2_HIST_DATE)")
    day = datetime.fromisoformat(date_s).replace(tzinfo=tz)
    session_start, session_end = _session_bounds_for_date(day, start_h=sh, start_m=sm, end_h=eh, end_m=em)
    asyncio.run(
        _run_oneshot(
            tokens=tokens,
            limits=limits,
            session_start=session_start,
            session_end=session_end,
            tz=tz,
            service=service,
            provider=provider,
            state_path=state_path,
            persist_every=int(args.persist_every),
            fail_on_error=bool(args.fail_on_error),
        )
    )


if __name__ == "__main__":
    main()
