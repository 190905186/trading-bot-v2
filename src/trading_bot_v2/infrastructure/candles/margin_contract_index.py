"""Margin-list CSV index: map Angel tokens to underlying name and EQ / FUTSTK siblings."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from enum import Enum
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("trading_bot_v2.candles.margin_index")

_EQ_SUFFIX = "-EQ"


def parse_margin_expiry(raw: Optional[str]) -> Optional[date]:
    """Parse Angel margin CSV expiry like ``28APR2026`` to a :class:`~datetime.date`."""
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "")
    if not s:
        return None
    try:
        return datetime.strptime(s.title(), "%d%b%Y").date()
    except ValueError:
        try:
            return datetime.strptime(s, "%d%b%y").date()
        except ValueError:
            logger.debug("Unparseable margin expiry: %r", raw)
            return None


def iter_session_dates(fr: datetime, to: datetime, tz: ZoneInfo) -> Iterator[date]:
    """
    Yield each calendar ``date`` touched by broker window ``[fr, to)`` in ``tz``.
    Uses half-open semantics on ``to``: if ``to`` is midnight April 3, April 2 is still included.
    """
    if to <= fr:
        return
    ef = fr.astimezone(tz)
    et_excl_last = (to.astimezone(tz) - timedelta(microseconds=1)).date()
    d_start = ef.date()
    cur = d_start
    while cur <= et_excl_last:
        yield cur
        cur += timedelta(days=1)


def _normalize_header_map(fieldnames: Optional[Sequence[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not fieldnames:
        return out
    for fn in fieldnames:
        if fn is None:
            continue
        key = str(fn).strip().lower()
        if key:
            out[key] = str(fn).strip()
    return out


@dataclass(frozen=True)
class MarginInstrumentRow:
    token: int
    symbol: str
    name: str
    expiry: Optional[date]
    instrumenttype: str
    exch_seg: str


class InstrumentKind(Enum):
    EQ = "eq"
    FUT = "fut"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FutSegmentPlan:
    """One contiguous futures contract covering ``[effective_from, effective_to)``."""

    fut_token: int
    effective_from: datetime
    effective_to: datetime


class MarginContractIndex:
    """In-memory lookups from Angel margin calculator CSV."""

    def __init__(self, rows_by_token: Dict[int, MarginInstrumentRow]) -> None:
        self._by_token = dict(rows_by_token)
        eq_by_name: Dict[str, List[int]] = {}
        fut_rows_by_name: Dict[str, List[MarginInstrumentRow]] = {}
        for row in rows_by_token.values():
            it = row.instrumenttype.upper()
            if it == "FUTSTK":
                fut_rows_by_name.setdefault(row.name, []).append(row)
                continue
            symbol_u = row.symbol.upper()
            if row.exch_seg == "NSE" and symbol_u.endswith(_EQ_SUFFIX):
                eq_by_name.setdefault(row.name, []).append(row.token)

        self._eq_by_underlying_name = eq_by_name
        self._fut_by_underlying_name = fut_rows_by_name

    @classmethod
    def from_csv_path(cls, path: str | Path) -> MarginContractIndex:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Margin CSV not found: {p}")

        mapping: Dict[int, MarginInstrumentRow] = {}
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            row_lc: Dict[str, str]

            if not reader.fieldnames:
                raise ValueError(f"Margin CSV empty or malformed: {p}")

            hdr = _normalize_header_map(reader.fieldnames)
            tk = hdr.get("token", "token")

            for raw in reader:
                row_lc = {(k or "").strip().lower(): str(v).strip() for k, v in raw.items()}
                token_s = raw.get(hdr.get("token", tk), raw.get(tk))
                symbol = row_lc.get("symbol", "").strip()
                name = row_lc.get("name", "").strip()
                expiry_s = row_lc.get("expiry", "").strip()
                itype = row_lc.get("instrumenttype", "").strip().upper()
                exch = row_lc.get("exch_seg", "").strip().upper()

                try:
                    tok = int(float(str(token_s).strip()))
                except (TypeError, ValueError):
                    continue
                if not name:
                    continue

                mapping[tok] = MarginInstrumentRow(
                    token=tok,
                    symbol=symbol,
                    name=name,
                    expiry=parse_margin_expiry(expiry_s),
                    instrumenttype=itype,
                    exch_seg=exch,
                )

        logger.info("Loaded margin index: %s instruments from %s", len(mapping), p)
        return cls(mapping)

    def row(self, token: int) -> Optional[MarginInstrumentRow]:
        return self._by_token.get(int(token))

    def classify(self, token: int) -> Tuple[InstrumentKind, Optional[MarginInstrumentRow]]:
        row = self.row(token)
        if row is None:
            return InstrumentKind.UNKNOWN, None
        if row.instrumenttype.upper() == "FUTSTK":
            return InstrumentKind.FUT, row
        symbol_u = row.symbol.upper()
        if row.exch_seg.upper() == "NSE" and symbol_u.endswith(_EQ_SUFFIX):
            return InstrumentKind.EQ, row
        return InstrumentKind.UNKNOWN, row

    def resolve_eq_token_for_underlying(
        self,
        underlying_name: str,
        *,
        prefer_tokens: FrozenSet[int] = frozenset(),
    ) -> Optional[int]:
        cands = self._eq_by_underlying_name.get(underlying_name, [])
        if not cands:
            return None
        if len(cands) == 1:
            return int(cands[0])
        for t in sorted(cands):
            if int(t) in prefer_tokens:
                return int(t)
        return int(min(cands))

    def pick_fut_token_for_session_date(
        self,
        underlying_name: str,
        session_d: date,
        *,
        prefer_exchanges: Sequence[str] = ("NFO", "BFO"),
    ) -> Optional[int]:
        rows = [
            r
            for r in self._fut_by_underlying_name.get(underlying_name, [])
            if r.expiry is not None
        ]
        if not rows:
            return None

        exch_order = {ex.upper(): idx for idx, ex in enumerate(prefer_exchanges)}
        ranked = sorted(rows, key=lambda r: (exch_order.get(r.exch_seg, 999), r.expiry or date.min))

        viable = [r for r in ranked if r.expiry >= session_d]
        pick: MarginInstrumentRow
        if viable:
            pick = min(viable, key=lambda r: (r.expiry, r.token))
        else:
            pick = max(ranked, key=lambda r: (r.expiry or date.min, r.token))

        return pick.token

    def plan_fut_segments_for_range(
        self,
        underlying_name: str,
        effective_from: datetime,
        effective_to: datetime,
        tz: ZoneInfo,
        *,
        prefer_exchanges: Sequence[str] = ("NFO", "BFO"),
    ) -> List[FutSegmentPlan]:
        dates = list(iter_session_dates(effective_from, effective_to, tz))
        if not dates:
            return []

        ef = effective_from.astimezone(tz)
        et = effective_to.astimezone(tz)

        out: List[FutSegmentPlan] = []
        idx = 0
        while idx < len(dates):
            d0 = dates[idx]
            tok = self.pick_fut_token_for_session_date(
                underlying_name, d0, prefer_exchanges=prefer_exchanges
            )
            if tok is None:
                logger.warning("Margin index: no FUT candidate for underlying=%s on %s", underlying_name, d0)
                idx += 1
                continue
            j = idx
            while j < len(dates):
                dj = dates[j]
                tok_j = self.pick_fut_token_for_session_date(
                    underlying_name, dj, prefer_exchanges=prefer_exchanges
                )
                if tok_j != tok:
                    break
                j += 1
            run_start = dates[idx]
            run_end_inclusive = dates[j - 1]
            seg_open = datetime.combine(run_start, time.min, tzinfo=tz)
            seg_close_excl = datetime.combine(run_end_inclusive + timedelta(days=1), time.min, tzinfo=tz)
            eff_fr = max(ef, seg_open)
            eff_to = min(et, seg_close_excl)
            if eff_fr < eff_to:
                out.append(FutSegmentPlan(fut_token=tok, effective_from=eff_fr, effective_to=eff_to))
            idx = j

        return out
