#!/usr/bin/env python3
"""Minimal Finvasia tick smoke test — same path as trading-bot-v2 run_ticks_service.

Usage (from trading-bot-v2/):
    python scripts/finvasia_tick_smoke.py
    python scripts/finvasia_tick_smoke.py --instrument NSE|1594
    python scripts/finvasia_tick_smoke.py --feed-type d --max-ticks 5

Requires TB2_FINVASIA_* in .env (same as run_ticks_service.py).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.infrastructure.brokers.finvasia_market_data import (  # noqa: E402
    FinvasiaMarketDataAdapter,
)
from trading_bot_v2.services.ticks.tick_context import TickMappingContext  # noqa: E402

LOG = logging.getLogger("finvasia_tick_smoke")


def _first_instrument(cli: str | None) -> str:
    if cli and cli.strip():
        return cli.strip()
    raw = os.getenv("TB2_INSTRUMENTS", "NSE|1594").strip()
    first = raw.split(",")[0].strip()
    if not first:
        return "NSE|1594"
    if "|" not in first:
        return f"NSE|{first}"
    return first


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finvasia single-token tick smoke test (v2 adapter)")
    parser.add_argument("--instrument", default=None, help="One scrip, e.g. NSE|1594 (default: first TB2_INSTRUMENTS)")
    parser.add_argument("--feed-type", default=_env("TB2_FINVASIA_FEED_TYPE", "t"), help="t=trade, d=depth (v1 used d)")
    parser.add_argument("--max-ticks", type=int, default=10, help="Stop after this many ticks (0 = run until Ctrl+C)")
    parser.add_argument("--timeout-sec", type=float, default=120.0, help="Give up if no tick within this many seconds")
    parser.add_argument("--log-level", default=_env("TB2_LOG_LEVEL", "INFO"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    instrument = _first_instrument(args.instrument)
    user_id = _env("TB2_FINVASIA_USER_ID")
    password = _env("TB2_FINVASIA_PASSWORD")
    access_token = _env("TB2_FINVASIA_ACCESS_TOKEN")
    susertoken = _env("TB2_FINVASIA_SUSER_TOKEN")
    api_key = _env("TB2_FINVASIA_API_KEY")
    account_id = _env("TB2_FINVASIA_ACTID") or user_id

    LOG.info("=== Finvasia tick smoke (v2 FinvasiaMarketDataAdapter) ===")
    LOG.info("instrument=%r feed_type=%r max_ticks=%s timeout=%ss", instrument, args.feed_type, args.max_ticks, args.timeout_sec)
    LOG.info("user_id=%r actid=%r access_token_set=%s susertoken_set=%s", user_id, account_id or user_id, bool(access_token), bool(susertoken))

    if not user_id:
        raise SystemExit("Set TB2_FINVASIA_USER_ID in .env")
    if not access_token and not susertoken:
        raise SystemExit("Set TB2_FINVASIA_ACCESS_TOKEN and/or TB2_FINVASIA_SUSER_TOKEN in .env")

    tick_count = 0
    started = time.monotonic()

    def on_tick(payload: dict) -> None:
        nonlocal tick_count
        tick_count += 1
        LOG.info(
            "TICK #%s token=%s symbol=%s lp=%s ts=%s exchange=%s",
            tick_count,
            payload.get("token"),
            payload.get("symbol_name"),
            payload.get("last_price"),
            payload.get("timestamp"),
            payload.get("exchange"),
        )
        if tick_count <= 2:
            LOG.info("TICK #%s full payload keys: %s", tick_count, sorted(payload.keys()))

    ctx = TickMappingContext.load()
    adapter = FinvasiaMarketDataAdapter(
        user_id=user_id,
        password=password,
        twofa=_env("TB2_FINVASIA_TOTP_KEY"),
        api_key=api_key,
        access_token=access_token,
        susertoken=susertoken,
        account_id=account_id,
        feed_type=args.feed_type,
        tick_context=ctx,
        batch="smoke",
    )
    adapter.set_tick_handler(on_tick)
    adapter.subscribe([instrument])
    adapter.connect()

    LOG.info("WebSocket thread started; waiting for ticks (Ctrl+C to stop)...")

    try:
        while True:
            time.sleep(0.5)
            if args.max_ticks > 0 and tick_count >= args.max_ticks:
                LOG.info("Received %s tick(s); done.", tick_count)
                break
            if tick_count == 0 and (time.monotonic() - started) >= args.timeout_sec:
                LOG.error(
                    "No ticks within %ss. Check: (1) market hours IST 09:15-15:30, "
                    "(2) instrument format NSE|token not 1|token, (3) fresh OAuth tokens, "
                    "(4) try --feed-type d",
                    args.timeout_sec,
                )
                break
    except KeyboardInterrupt:
        LOG.info("Interrupted.")
    finally:
        adapter.disconnect()
        LOG.info("Total ticks received: %s", tick_count)


if __name__ == "__main__":
    main()
