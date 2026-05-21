"""Run dashboard API backed by Redis streams."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_bot_v2.bootstrap.repo_dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from trading_bot_v2.bootstrap.app_container import AppContainer
from trading_bot_v2.monitoring.metric_catalog import MetricCatalog
from trading_bot_v2.monitoring.redis_providers import (
    RedisHeartbeatHealthProvider,
    RedisStreamMetricProvider,
)
from trading_bot_v2.monitoring.sqlite_providers import SqliteMetricProvider
from trading_bot_v2.monitoring.system_providers import ProcessResourceHealthProvider
from trading_bot_v2.infrastructure.storage.sqlite_store import SqliteEventStore
from trading_bot_v2.services.dashboard.api import create_dashboard_app


def main() -> None:
    redis_url = os.getenv("TB2_REDIS_URL", "redis://127.0.0.1:6381/0")
    host = os.getenv("TB2_DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("TB2_DASHBOARD_PORT", "8080"))
    stream_read_max = int(os.getenv("TB2_DASHBOARD_STREAM_READ_MAX", "50000"))

    catalog = MetricCatalog()
    sqlite_store = SqliteEventStore()
    stream_metric_provider = RedisStreamMetricProvider(
        catalog,
        redis_url=redis_url,
        per_stream_max_items=stream_read_max,
    )
    sqlite_metric_provider = SqliteMetricProvider(sqlite_store)
    heartbeat_provider = RedisHeartbeatHealthProvider(redis_url=redis_url)
    process_provider = ProcessResourceHealthProvider("dashboard-api")

    container = AppContainer(
        metric_catalog=catalog,
        metric_providers=[stream_metric_provider, sqlite_metric_provider],
        health_providers=[heartbeat_provider, process_provider],
    )
    dashboard_service = container.build_dashboard_service()
    app = create_dashboard_app(dashboard_service)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
