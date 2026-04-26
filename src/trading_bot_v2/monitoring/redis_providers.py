"""Redis-backed monitoring providers for dashboard snapshots."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping

from redis import Redis

from trading_bot_v2.interfaces.dashboard import HealthProvider, MetricProvider
from trading_bot_v2.monitoring.metric_catalog import MetricCatalog


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class RedisStreamMetricProvider(MetricProvider):
    """Computes dashboard metrics from Redis event streams."""

    def __init__(
        self,
        metric_catalog: MetricCatalog,
        redis_url: str = "redis://localhost:6379/0",
        *,
        default_window_seconds: int = 60,
        per_stream_max_items: int = 5000,
    ) -> None:
        self._catalog = metric_catalog
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._default_window_seconds = default_window_seconds
        self._max_items = per_stream_max_items

    def metric_ids(self) -> Iterable[str]:
        return [metric.metric_id for metric in self._catalog.list_enabled()]

    def _read_stream_payloads(self, stream_name: str, window_seconds: int) -> list[Dict[str, Any]]:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        results = self._redis.xrevrange(stream_name, max="+", min="-", count=self._max_items)
        payloads: list[Dict[str, Any]] = []
        for stream_id, fields in results:
            try:
                ts_ms = int(str(stream_id).split("-", maxsplit=1)[0])
            except (TypeError, ValueError):
                continue
            if (now_ms - ts_ms) > (window_seconds * 1000):
                continue
            raw = fields.get("data")
            if raw is None:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            payload["_stream_id"] = stream_id
            payloads.append(payload)
        return payloads

    def _key(self, payload: Mapping[str, Any], *fields: str) -> str:
        values = []
        event_payload = payload.get("payload", {})
        for field in fields:
            if field in payload:
                values.append(str(payload.get(field)))
            else:
                values.append(str(event_payload.get(field)))
        return "|".join(values)

    def _compute(self, metric_id: str, window_seconds: int) -> Dict[str, Any]:
        if metric_id == "ticks_received_total":
            rows = self._read_stream_payloads("ticks.raw", window_seconds)
            grouped = Counter(self._key(row, "broker", "token") for row in rows)
            return {"value": len(rows), "breakdown": dict(grouped), "timestamp": _utc_iso_now()}

        if metric_id == "tick_share_by_broker":
            rows = self._read_stream_payloads("ticks.raw", window_seconds)
            broker_counts = Counter(self._key(row, "broker") for row in rows)
            total = sum(broker_counts.values()) or 1
            share = {broker: round((count / total) * 100.0, 2) for broker, count in broker_counts.items()}
            return {"value": share, "timestamp": _utc_iso_now()}

        if metric_id == "candles_closed_total":
            rows = self._read_stream_payloads("candles.1m.closed", window_seconds)
            grouped = Counter(self._key(row, "broker", "token") for row in rows)
            return {"value": len(rows), "breakdown": dict(grouped), "timestamp": _utc_iso_now()}

        if metric_id == "signals_generated_total":
            rows = self._read_stream_payloads("signals.generated", window_seconds)
            grouped = Counter(self._key(row, "broker", "strategy", "token", "signal_type") for row in rows)
            buy_sell = Counter(self._key(row, "signal_type") for row in rows)
            return {
                "value": len(rows),
                "breakdown": dict(grouped),
                "buy_sell_distribution": dict(buy_sell),
                "timestamp": _utc_iso_now(),
            }

        if metric_id == "signals_to_orders_ratio":
            signals = self._read_stream_payloads("signals.generated", window_seconds)
            order_updates = self._read_stream_payloads("orders.updates", window_seconds)
            submitted = [
                row
                for row in order_updates
                if str(row.get("payload", {}).get("status", "")).upper() in {"SUBMITTED", "PLACED", "FILLED"}
            ]
            ratio = (len(submitted) / len(signals)) if signals else 0.0
            return {
                "value": round(ratio, 4),
                "signals": len(signals),
                "orders_submitted": len(submitted),
                "timestamp": _utc_iso_now(),
            }

        if metric_id == "sl_modifications_total":
            rows = self._read_stream_payloads("orders.updates", window_seconds)
            modified = [
                row
                for row in rows
                if str(row.get("payload", {}).get("status", "")).upper() == "SL_MODIFIED"
            ]
            grouped = Counter(self._key(row, "broker", "token") for row in modified)
            return {"value": len(modified), "breakdown": dict(grouped), "timestamp": _utc_iso_now()}

        if metric_id == "orders_exited_total":
            rows = self._read_stream_payloads("orders.updates", window_seconds)
            exited = [row for row in rows if str(row.get("payload", {}).get("status", "")).upper() == "EXITED"]
            grouped = Counter(self._key(row, "broker", "exit_reason") for row in exited)
            return {"value": len(exited), "breakdown": dict(grouped), "timestamp": _utc_iso_now()}

        if metric_id == "realized_pnl":
            rows = self._read_stream_payloads("orders.updates", window_seconds)
            total = 0.0
            by_broker: dict[str, float] = defaultdict(float)
            by_strategy: dict[str, float] = defaultdict(float)
            for row in rows:
                payload = row.get("payload", {})
                pnl = _safe_float(payload.get("realized_pnl", payload.get("pnl", 0.0)))
                total += pnl
                by_broker[str(payload.get("broker", "unknown"))] += pnl
                by_strategy[str(payload.get("strategy", "unknown"))] += pnl
            return {
                "value": round(total, 4),
                "by_broker": {k: round(v, 4) for k, v in by_broker.items()},
                "by_strategy": {k: round(v, 4) for k, v in by_strategy.items()},
                "timestamp": _utc_iso_now(),
            }

        if metric_id in {"service_cpu_percent", "service_memory_mb"}:
            rows = self._read_stream_payloads("service.heartbeat", window_seconds)
            grouped: dict[str, list[float]] = defaultdict(list)
            field = "cpu_percent" if metric_id == "service_cpu_percent" else "memory_mb"
            for row in rows:
                payload = row.get("payload", {})
                service = str(payload.get("service_name", row.get("producer", "unknown")))
                grouped[service].append(_safe_float(payload.get(field, 0.0)))
            averages = {
                service: round(sum(values) / len(values), 4) if values else 0.0
                for service, values in grouped.items()
            }
            return {"value": averages, "timestamp": _utc_iso_now()}

        return {"status": "unsupported_metric", "metric_id": metric_id, "timestamp": _utc_iso_now()}

    def get_metric_value(self, metric_id: str) -> Mapping[str, Any]:
        definition = self._catalog.get(metric_id)
        window_seconds = max(1, int(definition.window_seconds or self._default_window_seconds))
        metric_value = self._compute(metric_id, window_seconds)
        metric_value["metric_id"] = metric_id
        metric_value["window_seconds"] = window_seconds
        return metric_value


class RedisHeartbeatHealthProvider(HealthProvider):
    """Builds service health map from `service.heartbeat` events."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        stale_after_seconds: int = 15,
        max_items: int = 500,
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._stale_after_seconds = stale_after_seconds
        self._max_items = max_items

    def get_health(self) -> Dict[str, Any]:
        rows = self._redis.xrevrange("service.heartbeat", max="+", min="-", count=self._max_items)
        latest_by_service: dict[str, Dict[str, Any]] = {}
        now = datetime.now(timezone.utc)

        for stream_id, fields in rows:
            raw = fields.get("data")
            if raw is None:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload", {})
            service_name = str(payload.get("service_name", event.get("producer", "unknown")))
            if service_name in latest_by_service:
                continue
            try:
                ts = datetime.fromisoformat(str(event.get("published_at")).replace("Z", "+00:00"))
            except ValueError:
                ts = now
            age_seconds = max(0.0, (now - ts).total_seconds())
            status = "up" if age_seconds <= self._stale_after_seconds else "stale"
            latest_by_service[service_name] = {
                "service_name": service_name,
                "status": status,
                "age_seconds": round(age_seconds, 3),
                "cpu_percent": _safe_float(payload.get("cpu_percent")),
                "memory_mb": _safe_float(payload.get("memory_mb")),
                "last_heartbeat": ts.isoformat(),
            }

        return {
            "service_name": "heartbeat-monitor",
            "status": "up" if latest_by_service else "degraded",
            "timestamp": now.isoformat(),
            "services": latest_by_service,
        }
