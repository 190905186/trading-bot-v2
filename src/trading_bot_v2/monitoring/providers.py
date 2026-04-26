"""Reference provider implementations for early development."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from trading_bot_v2.interfaces.dashboard import HealthProvider, MetricProvider


class StaticMetricProvider(MetricProvider):
    """Simple metric provider backed by an in-memory dictionary."""

    def __init__(self, values: Mapping[str, Mapping[str, Any]]) -> None:
        self._values = {key: dict(value) for key, value in values.items()}

    def metric_ids(self) -> Iterable[str]:
        return self._values.keys()

    def get_metric_value(self, metric_id: str) -> Mapping[str, Any]:
        base = self._values.get(metric_id, {"status": "missing"})
        return {
            **base,
            "metric_id": metric_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class StaticHealthProvider(HealthProvider):
    """Simple health provider for bootstrap/testing."""

    def __init__(self, service_name: str, status: str = "up") -> None:
        self._service_name = service_name
        self._status = status

    def get_health(self) -> Dict[str, Any]:
        return {
            "service_name": self._service_name,
            "status": self._status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
