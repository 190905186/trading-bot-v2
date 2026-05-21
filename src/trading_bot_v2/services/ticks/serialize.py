"""JSON-safe serialization for unified tick payloads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping


def prepare_tick_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert datetimes to ISO strings without timezone conversion (v1 parity)."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, date):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out
