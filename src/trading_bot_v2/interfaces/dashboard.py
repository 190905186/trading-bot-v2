"""Dashboard metric interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Mapping


class MetricProvider(ABC):
    """Provides computed metric snapshots for dashboard consumption."""

    @abstractmethod
    def metric_ids(self) -> Iterable[str]:
        """Return metric ids this provider can compute."""

    @abstractmethod
    def get_metric_value(self, metric_id: str) -> Mapping[str, Any]:
        """Return metric payload by id."""


class HealthProvider(ABC):
    """Service health information contract."""

    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        """Return service/system health snapshot."""
