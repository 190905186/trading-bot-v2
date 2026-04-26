# Trading Bot V2 Architecture

## Runtime Services

- `ticks-service`: broker websocket ingest, emits `ticks.raw`.
- `candle-service`: tick aggregation + backfill reconciliation, emits `candles.1m.closed`.
- `signal-service`: strategy plugins consume candles/ticks, emits `signals.generated`.
- `order-service`: risk checks + execution adapter, emits order intent/updates.
- `risk-service`: shared TSL and kill-switch logic.
- `dashboard-service`: health and metric aggregation.

## Event Contract Spine

- `ticks.raw`
- `candles.1m.closed`
- `signals.generated`
- `orders.intent`
- `orders.updates`
- `service.heartbeat`
- `pipeline.latency`
- `dashboard.metric.definition`
- `dashboard.metric.value`

## OOP Boundaries

- Broker ports: `MarketDataAdapter`, `ExecutionAdapter`
- Strategy ports: `TradingStrategy`, `StrategyFactory`
- Bus ports: `EventPublisher`, `EventConsumer`
- Risk ports: `RiskManager`, `TrailingStopManager`
- Dashboard ports: `MetricProvider`, `HealthProvider`

## Concurrency Approach

- Independent services run as independent processes.
- Sync-first control flow for readability.
- Async can be adopted in focused hotspots (high I/O fan-out or websocket bottlenecks).
