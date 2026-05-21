"""Partition instrument tokens into broker batches (mirrors trading-bot token_batches layout)."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

# Which broker process may use each batch name.
BATCH_BROKER: Dict[str, str] = {
    "batch1": "zerodha",
    "batch2": "zerodha",
    "batch3": "zerodha",
    "batch4": "angelone",
    "batch5": "angelone",
    "batch6": "angelone",
    "batch7": "finvasia",
    "batch8": "finvasia",
    "batch9": "finvasia",
}

ZERODHA_BATCHES = ("batch1", "batch2", "batch3")
ANGELONE_BATCHES = ("batch4", "batch5", "batch6")
FINVASIA_BATCHES = ("batch7", "batch8", "batch9")


def _chunk(tokens: Sequence[int], size: int) -> List[int]:
    return list(tokens[:size])


def _split_evenly(tokens: Sequence[int], parts: int) -> List[List[int]]:
    items = list(tokens)
    n = len(items)
    if parts <= 0:
        return [items]
    base = n // parts
    rem = n % parts
    out: List[List[int]] = []
    idx = 0
    for i in range(parts):
        take = base + (1 if i < rem else 0)
        out.append(items[idx : idx + take])
        idx += take
    return out


def build_token_batches(
    all_tokens: Sequence[int],
    *,
    profile: str = "production",
) -> Dict[str, List[int]]:
    """
    Build batch1–batch9 from the full token list.

    Profiles:
    - ``production``: Zerodha = last 1141 split 3 ways; Angel = [:3000] in 1k chunks;
      Finvasia = [3000:9000] in 2k chunks (same as trading-bot token_batches.py intent).
    - ``test``: same Zerodha split on last 1141; smaller slices for Angel/Finvasia if list short.
    """
    tokens = [int(t) for t in all_tokens]
    if not tokens:
        return {name: [] for name in BATCH_BROKER}

    prof = profile.strip().lower()
    if prof == "test":
        return _build_test_profile(tokens)
    return _build_production_profile(tokens)


def _build_production_profile(tokens: List[int]) -> Dict[str, List[int]]:
    last_n = min(1141, len(tokens))
    z_slice = tokens[-last_n:] if last_n else []
    z_parts = _split_evenly(z_slice, 3)

    return {
        "batch1": z_parts[0] if len(z_parts) > 0 else [],
        "batch2": z_parts[1] if len(z_parts) > 1 else [],
        "batch3": z_parts[2] if len(z_parts) > 2 else [],
        "batch4": _chunk(tokens[0:3000], 1000),
        "batch5": _chunk(tokens[1000:3000], 1000),
        "batch6": _chunk(tokens[2000:3000], 1000),
        "batch7": list(tokens[3000:5000]),
        "batch8": list(tokens[5000:7000]),
        "batch9": list(tokens[7000:9000]),
    }


def _build_test_profile(tokens: List[int]) -> Dict[str, List[int]]:
    """Smaller batches when the universe is short (local dev)."""
    n = len(tokens)
    z_count = min(1141, n)
    z_slice = tokens[-z_count:] if z_count else []
    z_parts = _split_evenly(z_slice, 3)
    per_angel = max(1, min(1000, math.ceil(n / 3))) if n else 0
    return {
        "batch1": z_parts[0] if len(z_parts) > 0 else [],
        "batch2": z_parts[1] if len(z_parts) > 1 else [],
        "batch3": z_parts[2] if len(z_parts) > 2 else [],
        "batch4": list(tokens[0:per_angel]),
        "batch5": list(tokens[per_angel : 2 * per_angel]),
        "batch6": list(tokens[2 * per_angel : 3 * per_angel]),
        "batch7": list(tokens[3 * per_angel : 3 * per_angel + per_angel]),
        "batch8": list(tokens[3 * per_angel + per_angel : 3 * per_angel + 2 * per_angel]),
        "batch9": list(tokens[3 * per_angel + 2 * per_angel : 3 * per_angel + 3 * per_angel]),
    }


def validate_batches_no_overlap(batches: Dict[str, List[int]]) -> None:
    """Ensure no token appears twice in any single batch dict (all keys)."""
    seen: Dict[int, str] = {}
    for batch_name, toks in batches.items():
        for t in toks:
            if t in seen:
                raise ValueError(
                    f"Token {t} appears in both {seen[t]!r} and {batch_name!r}; batches must be disjoint."
                )
            seen[t] = batch_name


def validate_batches_no_overlap_within_broker(batches: Dict[str, List[int]]) -> None:
    """Same token may appear on multiple brokers (v1 layout); batches per broker must not overlap."""
    by_broker: Dict[str, Dict[str, List[int]]] = {}
    for batch_name, toks in batches.items():
        broker = BATCH_BROKER.get(batch_name)
        if broker is None:
            continue
        by_broker.setdefault(broker, {})[batch_name] = toks
    for broker, broker_batches in by_broker.items():
        seen: Dict[int, str] = {}
        for batch_name, toks in broker_batches.items():
            for t in toks:
                if t in seen:
                    raise ValueError(
                        f"Token {t} appears in both {seen[t]!r} and {batch_name!r} "
                        f"for broker {broker!r}."
                    )
                seen[t] = batch_name


def broker_for_batch(batch_name: str) -> str:
    key = batch_name.strip().lower()
    if key not in BATCH_BROKER:
        raise ValueError(f"Unknown batch {batch_name!r}; expected one of {sorted(BATCH_BROKER)}")
    return BATCH_BROKER[key]


def assert_batch_matches_source(batch_name: str, market_data_source: str) -> None:
    expected = broker_for_batch(batch_name)
    src = market_data_source.strip().lower()
    if src in {"angel_one"}:
        src = "angelone"
    if src != expected:
        raise ValueError(
            f"Batch {batch_name!r} belongs to broker {expected!r}, "
            f"but TB2_MARKET_DATA_SOURCE={market_data_source!r}"
        )
