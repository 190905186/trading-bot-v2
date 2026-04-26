"""Extensible metric catalog for dashboard cards and alerting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Mapping

Aggregation = Literal["sum", "avg", "min", "max", "count", "rate", "ratio", "p95"]
ChartType = Literal["single_stat", "line", "bar", "table", "heatmap", "gauge", "histogram"]


@dataclass(slots=True)
class MetricDefinition:
    """Config-driven metric definition used by dashboard service."""

    metric_id: str
    title: str
    source_stream: str
    aggregation: Aggregation
    chart_type: ChartType
    window_seconds: int = 60
    group_by: List[str] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    threshold_warning: float | None = None
    threshold_critical: float | None = None
    enabled: bool = True


DEFAULT_METRIC_CATALOG: Dict[str, MetricDefinition] = {
    "ticks_received_total": MetricDefinition(
        metric_id="ticks_received_total",
        title="Ticks Received (Broker/Token)",
        source_stream="ticks.raw",
        aggregation="count",
        chart_type="table",
        group_by=["broker", "token"],
    ),
    "tick_share_by_broker": MetricDefinition(
        metric_id="tick_share_by_broker",
        title="Tick Share by Broker",
        source_stream="ticks.raw",
        aggregation="ratio",
        chart_type="bar",
        group_by=["broker"],
    ),
    "candles_closed_total": MetricDefinition(
        metric_id="candles_closed_total",
        title="Closed Candles (Broker/Token)",
        source_stream="candles.1m.closed",
        aggregation="count",
        chart_type="table",
        group_by=["broker", "token"],
    ),
    "signals_generated_total": MetricDefinition(
        metric_id="signals_generated_total",
        title="Signals Generated (Buy/Sell)",
        source_stream="signals.generated",
        aggregation="count",
        chart_type="table",
        group_by=["broker", "strategy", "token", "signal_type"],
    ),
    "signals_to_orders_ratio": MetricDefinition(
        metric_id="signals_to_orders_ratio",
        title="Signals to Orders Match Ratio",
        source_stream="orders.updates",
        aggregation="ratio",
        chart_type="gauge",
        window_seconds=300,
        threshold_warning=0.90,
        threshold_critical=0.80,
    ),
    "sl_modifications_total": MetricDefinition(
        metric_id="sl_modifications_total",
        title="SL Modifications",
        source_stream="orders.updates",
        aggregation="count",
        chart_type="line",
        group_by=["broker", "token"],
    ),
    "orders_exited_total": MetricDefinition(
        metric_id="orders_exited_total",
        title="Exited Orders",
        source_stream="orders.updates",
        aggregation="count",
        chart_type="bar",
        group_by=["broker", "exit_reason"],
    ),
    "realized_pnl": MetricDefinition(
        metric_id="realized_pnl",
        title="Realized PnL",
        source_stream="orders.updates",
        aggregation="sum",
        chart_type="line",
        group_by=["broker", "strategy"],
    ),
    "service_cpu_percent": MetricDefinition(
        metric_id="service_cpu_percent",
        title="Service CPU %",
        source_stream="service.heartbeat",
        aggregation="avg",
        chart_type="line",
        group_by=["service_name"],
    ),
    "service_memory_mb": MetricDefinition(
        metric_id="service_memory_mb",
        title="Service Memory (MB)",
        source_stream="service.heartbeat",
        aggregation="avg",
        chart_type="line",
        group_by=["service_name"],
    ),
}


class MetricCatalog:
    """Runtime metric catalog with easy metric registration."""

    def __init__(self, initial: Mapping[str, MetricDefinition] | None = None) -> None:
        self._metrics: Dict[str, MetricDefinition] = dict(initial or DEFAULT_METRIC_CATALOG)

    def register(self, definition: MetricDefinition) -> None:
        self._metrics[definition.metric_id] = definition

    def get(self, metric_id: str) -> MetricDefinition:
        return self._metrics[metric_id]

    def list_enabled(self) -> list[MetricDefinition]:
        return [metric for metric in self._metrics.values() if metric.enabled]

    def as_dict(self) -> Dict[str, Dict[str, Any]]:
        return {mid: asdict(definition) for mid, definition in self._metrics.items()}
