"""FastAPI app for dashboard snapshots."""

from __future__ import annotations

from fastapi import FastAPI

from trading_bot_v2.services.dashboard.service import DashboardService


def create_dashboard_app(dashboard_service: DashboardService) -> FastAPI:
    """Create dashboard API application."""
    app = FastAPI(title="Trading Bot V2 Dashboard API", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "up"}

    @app.get("/dashboard/definitions")
    def definitions() -> dict:
        return {"definitions": dashboard_service.get_metric_definitions()}

    @app.get("/dashboard/metrics")
    def metrics() -> dict:
        return {"metrics": dashboard_service.get_metrics_snapshot()}

    @app.get("/dashboard/services-health")
    def services_health() -> dict:
        return {"health": dashboard_service.get_health_snapshot()}

    @app.get("/dashboard/snapshot")
    def snapshot() -> dict:
        return {
            "definitions": dashboard_service.get_metric_definitions(),
            "metrics": dashboard_service.get_metrics_snapshot(),
            "health": dashboard_service.get_health_snapshot(),
        }

    return app
