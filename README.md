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
