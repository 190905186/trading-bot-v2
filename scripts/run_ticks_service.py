"""Run tick ingestion service with selectable market-data adapter."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.infrastructure.brokers import (  # noqa: E402
    AngelOneMarketDataAdapter,
    FinvasiaMarketDataAdapter,
    MockMarketDataAdapter,
    ZerodhaMarketDataAdapter,
)
from trading_bot_v2.infrastructure.messaging import RedisStreamPublisher  # noqa: E402
from trading_bot_v2.monitoring.heartbeat import HeartbeatEmitter  # noqa: E402
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider  # noqa: E402
from trading_bot_v2.services.ticks.service import TickIngestionService  # noqa: E402
from trading_bot_v2.services.ticks.tick_context import TickMappingContext  # noqa: E402
from trading_bot_v2.token_universe.loader import (  # noqa: E402
    batch_token_ints,
    resolve_tick_instruments,
    universe_dir_from_env,
    zerodha_subscribe_reverse_map,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(str(raw).strip(), 10)


def _build_adapter(
    source: str,
    broker_name: str,
    tick_interval: float,
    *,
    session_label: str,
    tick_context: TickMappingContext,
    batch: str | None,
):
    normalized = source.strip().lower()
    if normalized == "zerodha":
        api_key = os.getenv("TB2_ZERODHA_API_KEY", "").strip()
        access_token = os.getenv("TB2_ZERODHA_ACCESS_TOKEN", "").strip()
        if not api_key or not access_token:
            raise RuntimeError(
                "TB2_ZERODHA_API_KEY and TB2_ZERODHA_ACCESS_TOKEN are required for zerodha source."
            )
        max_tokens = _env_int("TB2_ZERODHA_MAX_TOKENS_PER_SESSION", 3000)
        return ZerodhaMarketDataAdapter(
            api_key=api_key,
            access_token=access_token,
            session_label=session_label,
            max_tokens_per_session=max_tokens,
            tick_context=tick_context,
            batch=batch,
        )
    if normalized == "finvasia":
        user_id = os.getenv("TB2_FINVASIA_USER_ID", "").strip()
        password = os.getenv("TB2_FINVASIA_PASSWORD", "").strip()
        twofa = os.getenv("TB2_FINVASIA_TOTP_KEY", "").strip()
        api_key = os.getenv("TB2_FINVASIA_API_KEY", "").strip()
        access_token = os.getenv("TB2_FINVASIA_ACCESS_TOKEN", "").strip()
        susertoken = os.getenv("TB2_FINVASIA_SUSER_TOKEN", "").strip()
        return FinvasiaMarketDataAdapter(
            user_id=user_id,
            password=password,
            twofa=twofa,
            api_key=api_key,
            access_token=access_token,
            susertoken=susertoken,
            account_id=os.getenv("TB2_FINVASIA_ACTID", "").strip(),
            feed_type=os.getenv("TB2_FINVASIA_FEED_TYPE", "t").strip() or "t",
            tick_context=tick_context,
            batch=batch,
        )
    if normalized in {"angelone", "angel_one"}:
        return AngelOneMarketDataAdapter(
            api_key=os.getenv("TB2_ANGELONE_API_KEY", "").strip(),
            client_code=os.getenv("TB2_ANGELONE_CLIENT_CODE", "").strip(),
            password=os.getenv("TB2_ANGELONE_PASSWORD", "").strip(),
            totp_secret=os.getenv("TB2_ANGELONE_TOTP_SECRET", "").strip(),
            feed_token=os.getenv("TB2_ANGELONE_FEED_TOKEN", "").strip(),
            jwt_token=os.getenv("TB2_ANGELONE_JWT_TOKEN", "").strip(),
            tick_context=tick_context,
            batch=batch,
        )
    return MockMarketDataAdapter(broker_name=broker_name, tick_interval_seconds=tick_interval)


def _resolve_instruments(source: str) -> tuple[list[str], str | None]:
    tick_batch = os.getenv("TB2_TICK_BATCH", "").strip()
    if tick_batch:
        universe = universe_dir_from_env()
        instruments = resolve_tick_instruments(source, tick_batch, directory=universe)
        if not instruments:
            raise RuntimeError(f"Batch {tick_batch!r} resolved to zero instruments.")
        return instruments, tick_batch

    if source == "zerodha":
        default_instruments = "256265,738561,2953217"
    elif source == "finvasia":
        default_instruments = "NSE|22,NSE|11536"
    elif source in {"angelone", "angel_one"}:
        default_instruments = "1|1594,1|3045"
    else:
        default_instruments = "NSE:RELIANCE,NSE:INFY,NSE:TCS"
    instruments_env = os.getenv("TB2_INSTRUMENTS", default_instruments)
    instruments = [item.strip() for item in instruments_env.split(",") if item.strip()]
    return instruments, None


def main() -> None:
    log_level = getattr(logging, os.getenv("TB2_LOG_LEVEL", "INFO").strip().upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")

    redis_url = os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0")
    source = os.getenv("TB2_MARKET_DATA_SOURCE", "mock")
    broker_name = os.getenv("TB2_BROKER_NAME", "zerodha")
    tick_interval = float(os.getenv("TB2_TICK_INTERVAL_SECONDS", "0.2"))

    instruments, batch_name = _resolve_instruments(source)
    session_id = os.getenv("TB2_TICK_SESSION_ID", "").strip() or (batch_name or "default")
    service_name = os.getenv("TB2_SERVICE_NAME", "").strip() or (
        f"ticks-service-{source}-{session_id}" if batch_name else "ticks-service"
    )

    tick_metadata: dict = {"tick_session_id": session_id}
    if batch_name:
        tick_metadata["batch"] = batch_name

    publisher = RedisStreamPublisher(redis_url=redis_url)
    tick_context = TickMappingContext.load()
    log = logging.getLogger(__name__)
    log.info(
        "Tick mapping context: symbol_map=%s instrument_map=%s csv_symbols=%s",
        len(tick_context.token_symbol_map),
        len(tick_context.instrument_to_exchange_token),
        len(tick_context.exchange_token_to_symbol),
    )
    if source.strip().lower() == "zerodha" and batch_name:
        reverse = zerodha_subscribe_reverse_map(batch_token_ints(batch_name))
        tick_context.merge_instrument_exchange_map(reverse)
        log.info("Merged Zerodha subscribe reverse map: %s instrument(s)", len(reverse))

    adapter = _build_adapter(
        source=source,
        broker_name=broker_name,
        tick_interval=tick_interval,
        session_label=session_id,
        tick_context=tick_context,
        batch=batch_name,
    )
    service = TickIngestionService(adapter=adapter, publisher=publisher, tick_metadata=tick_metadata)

    logging.getLogger(__name__).info(
        "Starting %s source=%s instruments=%s batch=%s",
        service_name,
        source,
        len(instruments),
        batch_name or "(flat TB2_INSTRUMENTS)",
    )

    def _heartbeat_metadata() -> dict:
        return {
            "tb2_market_data_source": source,
            "tb2_tick_batch": batch_name,
            "tb2_tick_session_id": session_id,
            "instrument_count": len(instruments),
        }

    emitter = HeartbeatEmitter(
        publisher=publisher,
        service_name=service_name,
        resource_provider=ProcessResourceHealthProvider(service_name).get_health,
        metadata_factory=_heartbeat_metadata,
    )
    hb_thread = threading.Thread(target=emitter.run_forever, kwargs={"interval_seconds": 2.0}, daemon=True)
    hb_thread.start()

    service.run(instruments)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        adapter.disconnect()


if __name__ == "__main__":
    main()
