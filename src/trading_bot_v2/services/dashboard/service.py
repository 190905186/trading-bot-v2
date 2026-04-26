"""Dashboard service that aggregates health and metrics."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from trading_bot_v2.interfaces.dashboard import HealthProvider, MetricProvider
from trading_bot_v2.monitoring.metric_catalog import MetricCatalog


class DashboardService:
    """Provides a single-pane snapshot used by dashboard UI/backend."""

    def __init__(
        self,
        metric_catalog: MetricCatalog,
        metric_providers: Iterable[MetricProvider],
        health_providers: Iterable[HealthProvider],
    ) -> None:
        self._catalog = metric_catalog
        self._metric_providers = list(metric_providers)
        self._health_providers = list(health_providers)

    def get_metric_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Expose metric registry for dynamic dashboard cards."""
        return self._catalog.as_dict()

    def get_metrics_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Gather metric values from all providers."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for provider in self._metric_providers:
            for metric_id in provider.metric_ids():
                try:
                    snapshot[metric_id] = dict(provider.get_metric_value(metric_id))
                except Exception as exc:  # pragma: no cover - defensive path
                    snapshot[metric_id] = {"status": "error", "error": str(exc)}
        return snapshot

    def get_health_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Gather all service health details."""
        health: Dict[str, Dict[str, Any]] = {}
        for provider in self._health_providers:
            data = provider.get_health()
            service_name = str(data.get("service_name", provider.__class__.__name__))
            health[service_name] = data
        return health
