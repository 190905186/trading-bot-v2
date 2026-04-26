"""Simple container for composing service dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from trading_bot_v2.interfaces.dashboard import HealthProvider, MetricProvider
from trading_bot_v2.monitoring.metric_catalog import MetricCatalog
from trading_bot_v2.services.dashboard.service import DashboardService


@dataclass(slots=True)
class AppContainer:
    """Shared dependency holder for V2 modules."""

    metric_catalog: MetricCatalog
    metric_providers: List[MetricProvider]
    health_providers: List[HealthProvider]

    def build_dashboard_service(self) -> DashboardService:
        return DashboardService(
            metric_catalog=self.metric_catalog,
            metric_providers=self.metric_providers,
            health_providers=self.health_providers,
        )
