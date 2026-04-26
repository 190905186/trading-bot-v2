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

Then open:

- `http://localhost:8080/dashboard/snapshot`
- `http://localhost:8080/dashboard/metrics`
- `http://localhost:8080/dashboard/services-health`

Useful env vars:

- `TB2_REDIS_URL` (all scripts)
- `TB2_INSTRUMENTS` for tick script (comma separated tokens)
- `TB2_BROKER_NAME` for tick/order script broker labeling
- `TB2_CONSUMER_START_ID` (`$` for new messages only, `0-0` for replay)
