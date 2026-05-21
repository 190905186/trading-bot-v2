"""SQLite-backed cumulative metrics for dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from trading_bot_v2.infrastructure.storage.sqlite_store import SqliteEventStore, sqlite_path_from_env
from trading_bot_v2.interfaces.dashboard import MetricProvider


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteMetricProvider(MetricProvider):
    """Lifetime tick/candle totals from SQLite (no 5000 stream read cap)."""

    def __init__(self, store: SqliteEventStore | None = None) -> None:
        self._store = store or SqliteEventStore()

    def metric_ids(self) -> Iterable[str]:
        return ("ticks_stored_total", "candles_stored_total")

    def get_metric_value(self, metric_id: str) -> Mapping[str, Any]:
        by_broker = self._store.counts_by_broker()
        if metric_id == "ticks_stored_total":
            total = self._store.count_ticks()
            return {
                "metric_id": metric_id,
                "value": total,
                "breakdown": by_broker.get("ticks", {}),
                "db_path": str(self._store.db_path),
                "timestamp": _utc_iso_now(),
            }
        if metric_id == "candles_stored_total":
            total = self._store.count_candles()
            return {
                "metric_id": metric_id,
                "value": total,
                "breakdown": by_broker.get("candles", {}),
                "db_path": str(self._store.db_path),
                "timestamp": _utc_iso_now(),
            }
        return {"metric_id": metric_id, "status": "unsupported_metric", "timestamp": _utc_iso_now()}
