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
