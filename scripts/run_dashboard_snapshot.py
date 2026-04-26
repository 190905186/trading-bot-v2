"""Print one dashboard snapshot for smoke testing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.app_container import AppContainer
from trading_bot_v2.monitoring.metric_catalog import MetricCatalog
from trading_bot_v2.monitoring.providers import StaticHealthProvider, StaticMetricProvider


def main() -> None:
    catalog = MetricCatalog()
    metric_provider = StaticMetricProvider(
        {
            "ticks_received_total": {"value": 12500, "labels": {"broker": "zerodha"}},
            "signals_to_orders_ratio": {"value": 0.97, "labels": {"strategy": "quote_band"}},
            "realized_pnl": {"value": 2450.0, "labels": {"broker": "zerodha"}},
        }
    )
    health_provider = StaticHealthProvider("dashboard-service")

    container = AppContainer(
        metric_catalog=catalog,
        metric_providers=[metric_provider],
        health_providers=[health_provider],
    )
    dashboard = container.build_dashboard_service()
    output = {
        "definitions": dashboard.get_metric_definitions(),
        "metrics": dashboard.get_metrics_snapshot(),
        "health": dashboard.get_health_snapshot(),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
