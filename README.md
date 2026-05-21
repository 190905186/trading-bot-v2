# Trading Bot V2

Process-first, modular trading architecture with explicit event contracts, interface-driven services, and an extensible monitoring dashboard.

## Design Principles

- Independent runtime services communicate through event contracts.
- OOP for boundaries and extensibility; pure helpers for calculations.
- Sync-first control flow; async only where it clearly helps I/O throughput.
- Broker implementations are adapters behind abstract interfaces.
- Dashboard metrics are config/registry driven so new parameters are easy to add.

## Planned Service Modules

- `websocket_tick_service`
- `candle_service`
- `signal_service`
- `order_service`
- `risk_service`
- `dashboard_service`

## Initial Package Layout

- `src/trading_bot_v2/domain/contracts/events.py`
- `src/trading_bot_v2/interfaces/broker.py`
- `src/trading_bot_v2/interfaces/strategy.py`
- `src/trading_bot_v2/interfaces/messaging.py`
- `src/trading_bot_v2/interfaces/risk.py`
- `src/trading_bot_v2/services/dashboard/service.py`
- `src/trading_bot_v2/monitoring/metric_catalog.py`

## Phase 2 Added

- Redis Streams publisher/consumer adapters:
  - `src/trading_bot_v2/infrastructure/messaging/redis_streams.py`
- Redis-backed dashboard metric provider:
  - `src/trading_bot_v2/monitoring/redis_providers.py`
- Process CPU/memory health provider:
  - `src/trading_bot_v2/monitoring/system_providers.py`
- Dashboard FastAPI app:
  - `src/trading_bot_v2/services/dashboard/api.py`

## Run Dashboard API

Set environment variables (optional):

- `TB2_REDIS_URL` (default: `redis://localhost:6379/0`)
- `TB2_DASHBOARD_HOST` (default: `0.0.0.0`)
- `TB2_DASHBOARD_PORT` (default: `8080`)

Run:

`python scripts/run_dashboard_api.py`

API endpoints:

- `GET /health`
- `GET /dashboard/definitions`
- `GET /dashboard/metrics`
- `GET /dashboard/services-health`
- `GET /dashboard/snapshot`

## Publish Service Heartbeats

Use this from each independent service process to publish CPU/memory + status:

- `TB2_SERVICE_NAME=ticks-service python scripts/run_heartbeat_publisher.py`
- `TB2_SERVICE_NAME=order-service python scripts/run_heartbeat_publisher.py`

## Run Full Local Pipeline

Start Redis first, then run these scripts in separate terminals:

1. Tick producer (mock broker ticks):
   - `python scripts/run_ticks_service.py`
2. Candle builder (from ticks):
   - `python scripts/run_candle_service.py`
3. Signal generator (from candles):
   - `python scripts/run_signal_service.py`
4. Order service (paper execution from signals):
   - `python scripts/run_order_service.py`
5. Dashboard API:
   - `python scripts/run_dashboard_api.py`

Or start everything together:

- `python scripts/run_all_services.py`

Then open:

- `http://127.0.0.1:8088/dashboard/snapshot`
- `http://127.0.0.1:8088/dashboard/metrics`
- `http://127.0.0.1:8088/dashboard/services-health`
- `http://127.0.0.1:8088/dashboard`

Useful env vars:

- `TB2_REDIS_URL` (all scripts)
- `TB2_MARKET_DATA_SOURCE` (`mock`, `zerodha`, `finvasia`, or `angelone`)
- `TB2_INSTRUMENTS` for tick script:
  - Zerodha: instrument_token ints (`256265,738561`)
  - Finvasia: exchange-token pairs (`NSE|22,NFO|12345`)
  - AngelOne: exchangeType-token pairs (`1|1594,2|12345`)
- `TB2_BROKER_NAME` for tick/order script broker labeling
- `TB2_CONSUMER_START_ID` (`$` for new messages only, `0-0` for replay)

### Token batches and multi-process ticks

Generate the instrument universe (runs trading-bot v1 `token_list.py`, copies pickles into v2):

```text
python scripts/generate_token_universe.py
python scripts/build_token_batches.py
```

Pickles live under `data/token_universe/` (`TB2_TOKEN_UNIVERSE_DIR`).

**Batch layout (default `production` profile):**

| Batches | Broker | Typical size |
|---------|--------|----------------|
| batch1–3 | Zerodha | last 1141 tokens split 3 ways (~3000/subscribe limit per WS) |
| batch4–6 | AngelOne | tokens [0:3000] in chunks of 1000 |
| batch7–9 | Finvasia | tokens [3000:9000] in chunks of 2000 |

**One OS process = one websocket = one batch.** Example Zerodha session 1:

```text
set TB2_MARKET_DATA_SOURCE=zerodha
set TB2_TICK_BATCH=batch1
set TB2_SERVICE_NAME=ticks-zerodha-batch1
python scripts/run_ticks_service.py
```

Start all 9 tick children (3 per broker):

```text
python scripts/run_ticks_sessions.py
```

Override sessions with `TB2_TICK_SESSIONS=zerodha:batch1,zerodha:batch2,...`.

If `TB2_TICK_BATCH` is unset, `TB2_INSTRUMENTS` still works for small dev lists.

**Zerodha batch mapping:** batch pickles use Angel `exchange_token` ints (same as v1). At subscribe time, v2 maps them to Kite `instrument_token` via `data/instruments.csv` (downloaded from Kite once per day) and `amxidx_dict.pkl` from token generation — same logic as v1 `get_instruments_from_tokens`.

### Zerodha Tick Source

To switch from mock ticks to Zerodha websocket in the same pipeline:

- `TB2_MARKET_DATA_SOURCE=zerodha`
- `TB2_ZERODHA_API_KEY=<your_api_key>`
- `TB2_ZERODHA_ACCESS_TOKEN=<your_access_token>`
- `TB2_INSTRUMENTS=256265,738561,2953217` (example instrument tokens)

Then run:

- `python scripts/run_ticks_service.py`

### Finvasia Tick Source

Set:

- `TB2_MARKET_DATA_SOURCE=finvasia`
- `TB2_FINVASIA_USER_ID=<user_id>`
- `TB2_FINVASIA_PASSWORD=<password>`
- `TB2_FINVASIA_TOTP_KEY=<totp_secret>`
- `TB2_FINVASIA_API_KEY=<api_key>`
- Optional token reuse:
  - `TB2_FINVASIA_ACCESS_TOKEN=<access_token>`
  - `TB2_FINVASIA_SUSER_TOKEN=<susertoken>`
- Optional feed mode:
  - `TB2_FINVASIA_FEED_TYPE=t` (`t` trade feed, `d` depth feed)
- `TB2_INSTRUMENTS=NSE|22,NSE|11536`

Then run:

- `python scripts/run_ticks_service.py`

### Historical 1m candles (Redis)

Publish broker historical minute bars to `candles.1m.closed` with **rps**, **rpm**, and optional **rpd** limits.
Batch count is derived as `max(ceil(N / per_minute_budget), ceil(T * N / rpd))` where
`per_minute_budget = min(rpm, floor(60 * rps))` and **T** is the session length in minutes (for daily caps).

**Poll mode** only fetches during the configured session window (`TB2_HIST_SESSION_START` / `END`, default 09:15–15:30 IST).
Outside market hours the process stays alive but skips API calls.

**SQLite persistence:** run `python scripts/run_storage_service.py` to write all `ticks.raw` and
`candles.1m.closed` events to `TB2_SQLITE_PATH` (default `data/trading_bot_v2.db`). The dashboard shows
SQLite totals (`ticks_stored_total`, `candles_stored_total`) without the 5000 Redis read cap.

**Service heartbeats:** historical candles publishes to `service.heartbeat` as `historical-minute-candles`
(with CPU/memory). Storage service heartbeats as `storage-service`.

```bash
# Poll: one token batch per wall minute, rotate with epoch-minute % num_batches; sub-minute pacing >= 1/rps
TB2_MARKET_DATA_SOURCE=zerodha TB2_HIST_TOKENS=256265,738561 python scripts/run_historical_minute_candles.py --mode poll

# One-shot session for a calendar day (market timezone)
python scripts/run_historical_minute_candles.py --mode one-shot --date 2026-05-16 --tokens 256265,738561
```

Environment (defaults in parentheses):

- `TB2_HIST_RPS` (2), `TB2_HIST_RPM` (60), `TB2_HIST_RPD` (0 = no daily cap in batch math)
- `TB2_HIST_SESSION_MINUTES` (0 = derive from `TB2_HIST_SESSION_START` / `TB2_HIST_SESSION_END`, default 09:15–15:30)
- `TB2_HIST_POLL_OFFSET_SEC` (3): wait after each minute boundary before fetching (poll mode)
- `TB2_HIST_STATE_PATH`: optional JSON file for watermarks + dedupe
- `TB2_HIST_MODE`, `TB2_HIST_DATE`, `TB2_HIST_LOG_LEVEL`

Override batch count only to **increase** parallelism: `--num-batches` must be ≥ the computed minimum and each batch must stay ≤ `per_minute_budget`.

### AngelOne Tick Source

Set:

- `TB2_MARKET_DATA_SOURCE=angelone`
- `TB2_ANGELONE_API_KEY=<api_key>`
- `TB2_ANGELONE_CLIENT_CODE=<client_code>`
- `TB2_ANGELONE_PASSWORD=<password>`
- `TB2_ANGELONE_TOTP_SECRET=<totp_secret>`
- Optional session reuse:
  - `TB2_ANGELONE_FEED_TOKEN=<feed_token>`
  - `TB2_ANGELONE_JWT_TOKEN=<jwt_token>`
- `TB2_INSTRUMENTS=1|1594,1|3045`

Then run:

- `python scripts/run_ticks_service.py`
