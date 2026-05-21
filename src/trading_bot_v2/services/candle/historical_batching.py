"""Batching and per-minute budgets for historical candle polling under rps, rpm, and rpd."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True, slots=True)
class HistoricalRateLimits:
    """Broker-style historical API limits (all positive; rpd=0 disables daily cap for batch math)."""

    rps: float
    rpm: int
    rpd: int


@dataclass(frozen=True, slots=True)
class HistoricalBatchPlan:
    """Token lists per batch, sized to satisfy minute and (optional) daily limits."""

    num_batches: int
    per_minute_budget: int
    batches: List[List[int]]


def per_minute_budget_from_rps_rpm(rps: float, rpm: int) -> int:
    """
    Effective max requests in one wall minute given both burst (rps) and rpm.

    Uses ``min(rpm, floor(60 * rps))`` with ``floor(60 * rps)`` floored to at least 1 when rps > 0.
    """
    if rps <= 0 or rpm <= 0:
        raise ValueError("rps and rpm must be positive")
    rpm_from_rps = max(1, math.floor(60 * rps))
    return min(rpm, rpm_from_rps)


def partition_tokens(tokens: Sequence[int], num_batches: int) -> List[List[int]]:
    """Split ``tokens`` in original order into ``num_batches`` parts; sizes differ by at most one."""
    items = list(tokens)
    n = len(items)
    if num_batches <= 0:
        num_batches = 1
    if n == 0:
        return [[] for _ in range(num_batches)]
    base = n // num_batches
    rem = n % num_batches
    out: List[List[int]] = []
    idx = 0
    for i in range(num_batches):
        take = base + (1 if i < rem else 0)
        out.append(items[idx : idx + take])
        idx += take
    return out


def compute_batch_plan(
    tokens: Sequence[int],
    *,
    session_minutes: int,
    limits: HistoricalRateLimits,
) -> HistoricalBatchPlan:
    """
    Derive batch count and token partitions from rps, rpm, and optional rpd.

    - ``B_rpm_rps = ceil(N / per_minute_budget)``
    - ``B_rpd = ceil(T * N / rpd)`` when ``rpd > 0`` (requires ``session_minutes > 0``)
    - ``num_batches = max(B_rpm_rps, B_rpd, 1)``
    """
    n = len(tokens)
    budget = per_minute_budget_from_rps_rpm(limits.rps, limits.rpm)
    if n == 0:
        return HistoricalBatchPlan(num_batches=1, per_minute_budget=budget, batches=[[]])

    b_rpm_rps = math.ceil(n / budget)
    b_rpd = 0
    if limits.rpd > 0:
        if session_minutes <= 0:
            raise ValueError("session_minutes must be positive when rpd is set")
        b_rpd = math.ceil((session_minutes * n) / limits.rpd)

    num_batches = max(b_rpm_rps, b_rpd, 1)
    batches = partition_tokens(tokens, num_batches)
    max_size = max(len(b) for b in batches)

    if max_size > budget:
        repaired = num_batches
        while repaired < n:
            repaired += 1
            batches = partition_tokens(tokens, repaired)
            max_size = max(len(b) for b in batches)
            if max_size <= budget:
                break
        num_batches = repaired
        if max_size > budget:
            raise RuntimeError(
                f"Cannot satisfy per_minute_budget={budget} with N={n} tokens; "
                "increase rps/rpm or reduce token count."
            )

    return HistoricalBatchPlan(num_batches=num_batches, per_minute_budget=budget, batches=batches)


def apply_num_batches_override(
    plan: HistoricalBatchPlan,
    tokens: Sequence[int],
    override_batches: int,
) -> HistoricalBatchPlan:
    """Rebuild partitions with a larger ``num_batches`` (must still respect ``per_minute_budget``)."""
    if override_batches < plan.num_batches:
        raise ValueError(
            f"--num-batches ({override_batches}) must be >= computed minimum ({plan.num_batches})"
        )
    batches = partition_tokens(tokens, override_batches)
    max_size = max((len(b) for b in batches), default=0)
    if max_size > plan.per_minute_budget:
        raise ValueError(
            f"--num-batches ({override_batches}) yields a batch of size {max_size} "
            f"exceeding per_minute_budget={plan.per_minute_budget}"
        )
    return HistoricalBatchPlan(
        num_batches=override_batches,
        per_minute_budget=plan.per_minute_budget,
        batches=batches,
    )
