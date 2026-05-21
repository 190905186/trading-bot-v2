"""Futures + equity alignment and derived analytics columns for merged candle rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, MutableMapping


def minute_floor(dt: datetime) -> datetime:
    """Truncate to minute start in the same timezone as ``dt``."""
    return dt.replace(second=0, microsecond=0)


def equity_close_by_minute(eq_rows: List[Mapping[str, Any]]) -> Dict[datetime, float]:
    """Map minute-bucket start -> equity close for alignment onto futures bars."""
    out: Dict[datetime, float] = {}
    for r in eq_rows:
        raw = r.get("date")
        if not isinstance(raw, datetime):
            continue
        k = minute_floor(raw)
        try:
            out[k] = float(r.get("close", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def merge_equity_close_onto_futures(
    fut_rows: List[MutableMapping[str, Any]],
    eq_by_minute: Mapping[datetime, float],
) -> None:
    """Mutate each futures row with ``close_eq`` from ``eq_by_minute`` (or ``None``)."""
    for r in fut_rows:
        raw = r.get("date")
        if not isinstance(raw, datetime):
            r["close_eq"] = None
            continue
        k = minute_floor(raw)
        r["close_eq"] = eq_by_minute.get(k)


def enrich_futures_equity_features(rows: List[MutableMapping[str, Any]]) -> List[MutableMapping[str, Any]]:
    """
    Add rolling volume / OI metrics and premium classification.

    Expects rows sorted by ``date`` ascending. Mutates rows in place.
    """
    if not rows:
        return rows

    for i, r in enumerate(rows):
        if i < 4:
            r["avg_rolling_volume_5"] = 0.0
        else:
            window = rows[i - 4 : i + 1]
            acc = 0
            for w in window:
                try:
                    acc += int(w.get("volume", 0) or 0)
                except (TypeError, ValueError):
                    pass
            r["avg_rolling_volume_5"] = acc / 5.0

        if i == 0:
            r["oi_change"] = 0.0
        else:
            prev = rows[i - 1].get("oi")
            cur = r.get("oi")
            if prev is None or cur is None:
                r["oi_change"] = 0.0
            else:
                try:
                    r["oi_change"] = float(cur) - float(prev)
                except (TypeError, ValueError):
                    r["oi_change"] = 0.0

        if i < 4:
            r["avg_rolling_oi_change_5"] = 0.0
        else:
            s = 0.0
            for j in range(i - 4, i + 1):
                try:
                    s += float(rows[j].get("oi_change", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
            r["avg_rolling_oi_change_5"] = s / 5.0

        ceq = r.get("close_eq")
        try:
            fut_c = float(r.get("close", 0.0) or 0.0)
        except (TypeError, ValueError):
            fut_c = 0.0

        if ceq is None:
            r["fut_eq_close_diff"] = None
            r["premium_discount"] = None
        else:
            try:
                diff = fut_c - float(ceq)
            except (TypeError, ValueError):
                r["fut_eq_close_diff"] = None
                r["premium_discount"] = None
                continue

            r["fut_eq_close_diff"] = diff
            if diff > 0:
                r["premium_discount"] = "Premium"
            elif diff < 0:
                r["premium_discount"] = "Discount"
            else:
                r["premium_discount"] = "No Change"

    return rows
