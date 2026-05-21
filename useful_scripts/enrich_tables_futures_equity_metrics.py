#!/usr/bin/env python3
"""
Enrich SQLite candle tables with futures–equity analytics (pandas).

Configuration is read from ``env.txt`` next to this script::
  rolling_window_size — rolling window length for all rolling stats
  max_percentile — high quantile for rolling columns (e.g. 85 → 85th percentile)
  min_percentile — low quantile for rolling columns (e.g. 10 → 10th percentile)

Adds (after sorting rows by timestamp):
  - avg_rolling_volume_<W> — rolling mean of volume (window W); if fewer than W rows → 0
  - oi_change — current oi − previous oi; first row → 0; missing oi → 0
  - avg_rolling_oi_change_<W> — rolling mean of oi_change (window W); fewer than W → 0
  - volume_rolling_p<Pmax>, volume_rolling_p<Pmin> — rolling quantiles of volume
  - oi_change_rolling_p<Pmax>, oi_change_rolling_p<Pmin> — rolling quantiles of oi_change
  - volume_ratio_rolling_p<Pmax/min> — rolling quantiles of volume / avg_rolling_volume_<W>
  - oi_change_ratio_rolling_p<Pmax/min> — rolling quantiles of oi_change / avg_rolling_oi_change_<W>
  - fut_eq_close_diff — futures close − equity close (minute-aligned with sibling table)
  - premium_discount — Premium / Discount / No Change when diff is finite; else NULL

Pairing convention (this DB): FUT tables like SYMBOL28APR26FUT pair with SYMBOL_EQ using
SYMBOL as the substring before the first digit in the FUT name.

Requirements::
  pip install pandas

Examples::
  python enrich_tables_futures_equity_metrics.py
  python enrich_tables_futures_equity_metrics.py --db some_tables.db --dry-run

By default backs up the DB file to ``*.bak.<utc_timestamp>``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

# Columns from older script versions; dropped from persisted base schema on re-run.
LEGACY_DERIVED_COLUMNS = frozenset(
    {
        "avg_rolling_volume_5",
        "avg_rolling_oi_change_5",
    }
)


def load_env_config(env_path: Path) -> Tuple[int, int, int]:
    """Parse key = value lines from env.txt. Returns (rolling_window_size, max_percentile, min_percentile)."""
    if not env_path.is_file():
        raise SystemExit(f"Config file not found: {env_path}")
    raw: Dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        raw[k.strip()] = v.strip()
    try:
        w = int(raw["rolling_window_size"])
        pmax = int(raw["max_percentile"])
        pmin = int(raw["min_percentile"])
    except KeyError as e:
        raise SystemExit(f"env.txt missing required key: {e.args[0]}") from e
    except ValueError as e:
        raise SystemExit(f"env.txt: invalid integer for rolling_window_size / percentiles: {e}") from e
    if w < 1:
        raise SystemExit("rolling_window_size must be >= 1")
    if not (0 <= pmin <= 100 and 0 <= pmax <= 100):
        raise SystemExit("max_percentile and min_percentile must be between 0 and 100")
    if pmax == pmin:
        raise SystemExit("max_percentile and min_percentile must differ (otherwise column names collide)")
    return w, pmax, pmin


def derived_column_names(rolling_window_size: int, max_percentile: int, min_percentile: int) -> Tuple[str, ...]:
    w = rolling_window_size
    pmax, pmin = max_percentile, min_percentile
    return (
        f"avg_rolling_volume_{w}",
        "oi_change",
        f"avg_rolling_oi_change_{w}",
        f"volume_rolling_p{pmax}",
        f"oi_change_rolling_p{pmax}",
        f"volume_ratio_rolling_p{pmax}",
        f"oi_change_ratio_rolling_p{pmax}",
        f"volume_rolling_p{pmin}",
        f"oi_change_rolling_p{pmin}",
        f"volume_ratio_rolling_p{pmin}",
        f"oi_change_ratio_rolling_p{pmin}",
        "fut_eq_close_diff",
        "premium_discount",
    )


# Stale enriched columns from a previous env (different window / percentile names).
_RE_AVG_ROLL_VOL = re.compile(r"^avg_rolling_volume_\d+$")
_RE_AVG_ROLL_OI = re.compile(r"^avg_rolling_oi_change_\d+$")
_RE_ROLL_PCTL = re.compile(r"^(volume|oi_change|volume_ratio|oi_change_ratio)_rolling_p\d+$")


def _exclude_from_original_base_cols(col: str, current_derived: Tuple[str, ...]) -> bool:
    if col in current_derived or col in LEGACY_DERIVED_COLUMNS:
        return True
    if _RE_AVG_ROLL_VOL.fullmatch(col) or _RE_AVG_ROLL_OI.fullmatch(col) or _RE_ROLL_PCTL.fullmatch(col):
        return True
    return False


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def list_user_tables(con: sqlite3.Connection) -> List[str]:
    q = """SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"""
    return [r[0] for r in con.execute(q).fetchall()]


def symbol_prefix_before_first_digit(table_name: str) -> str:
    parts = re.split(r"(?=\d)", table_name, maxsplit=1)
    return parts[0].strip()


def classify_pairings(tables: Iterable[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    from collections import defaultdict

    lst = sorted(tables)
    eq_tables = [t for t in lst if t.endswith("_EQ")]
    fut_tables = [t for t in lst if t not in eq_tables and "FUT" in t.upper()]

    eq_set = set(eq_tables)
    fut_to_eq: Dict[str, str] = {}
    by_eq: Dict[str, List[str]] = defaultdict(list)

    for ft in fut_tables:
        pref = symbol_prefix_before_first_digit(ft)
        eqn = f"{pref}_EQ"
        if eqn in eq_set:
            fut_to_eq[ft] = eqn
            by_eq[eqn].append(ft)

    eq_to_fut = {eq: sorted(cands)[0] for eq, cands in by_eq.items() if cands}
    return fut_to_eq, eq_to_fut


def load_table(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    df = pd.read_sql_query(f'SELECT * FROM "{name}"', con)
    if "date" not in df.columns:
        raise ValueError(f'Table "{name}" has no "date" column.')
    dt = pd.to_datetime(df["date"], errors="coerce")
    if getattr(dt.dt, "tz", None) is not None:
        dt = dt.dt.tz_localize(None)
    df["_date_sort"] = dt
    df["date_norm"] = dt.dt.floor("min")
    return df


def build_minute_lookup(df: pd.DataFrame, close_col: str = "close") -> pd.Series:
    g = df[["date_norm", close_col]].dropna(subset=["date_norm"]).drop_duplicates("date_norm", keep="last")
    return pd.Series(g[close_col].values, index=g["date_norm"].values)


def enrich_frame(
    df: pd.DataFrame,
    *,
    fut_close_lookup: pd.Series | None,
    eq_close_lookup: pd.Series | None,
    equity_side: bool,
    rolling_window_size: int,
    max_percentile: int,
    min_percentile: int,
) -> pd.DataFrame:
    """Mutates a sorted copy with derived columns merged on date_norm."""
    w = rolling_window_size
    derived_columns = derived_column_names(w, max_percentile, min_percentile)
    q_high = max_percentile / 100.0
    q_low = min_percentile / 100.0
    roll_kw = {"window": w, "min_periods": w}

    out = df.copy()
    original_cols = [
        c
        for c in out.columns
        if c not in ("_date_sort", "date_norm") and not _exclude_from_original_base_cols(c, derived_columns)
    ]
    out = out.sort_values("_date_sort").reset_index(drop=True)

    col_avg_v = f"avg_rolling_volume_{w}"
    col_avg_oi = f"avg_rolling_oi_change_{w}"

    vol = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    rolling_v_mean = vol.rolling(**roll_kw).mean()
    out[col_avg_v] = rolling_v_mean.fillna(0.0).astype(float)

    if "oi" in out.columns:
        oi = pd.to_numeric(out["oi"], errors="coerce")
    else:
        oi = pd.Series(np.nan, index=out.index)

    prev = oi.shift(1)
    oc = pd.Series(np.zeros(len(out)), dtype=float)
    for i in range(1, len(out)):
        curr = oi.iat[i]
        pr = prev.iat[i]
        if pd.isna(curr) or pd.isna(pr):
            oc.iat[i] = 0.0
        else:
            oc.iat[i] = float(curr - pr)
    out["oi_change"] = oc.astype(float)

    roc = out["oi_change"].rolling(**roll_kw).mean()
    out[col_avg_oi] = roc.fillna(0.0).astype(float)

    vol_ratio = vol / out[col_avg_v].replace(0, np.nan)
    vol_ratio = vol_ratio.replace([np.inf, -np.inf], np.nan)
    oi_chg_ratio = out["oi_change"] / out[col_avg_oi].replace(0, np.nan)
    oi_chg_ratio = oi_chg_ratio.replace([np.inf, -np.inf], np.nan)

    out[f"volume_rolling_p{max_percentile}"] = (
        vol.rolling(**roll_kw).quantile(q_high).fillna(0.0).astype(float)
    )
    out[f"oi_change_rolling_p{max_percentile}"] = (
        out["oi_change"].rolling(**roll_kw).quantile(q_high).fillna(0.0).astype(float)
    )
    out[f"volume_ratio_rolling_p{max_percentile}"] = (
        vol_ratio.rolling(**roll_kw).quantile(q_high).fillna(0.0).astype(float)
    )
    out[f"oi_change_ratio_rolling_p{max_percentile}"] = (
        oi_chg_ratio.rolling(**roll_kw).quantile(q_high).fillna(0.0).astype(float)
    )

    out[f"volume_rolling_p{min_percentile}"] = (
        vol.rolling(**roll_kw).quantile(q_low).fillna(0.0).astype(float)
    )
    out[f"oi_change_rolling_p{min_percentile}"] = (
        out["oi_change"].rolling(**roll_kw).quantile(q_low).fillna(0.0).astype(float)
    )
    out[f"volume_ratio_rolling_p{min_percentile}"] = (
        vol_ratio.rolling(**roll_kw).quantile(q_low).fillna(0.0).astype(float)
    )
    out[f"oi_change_ratio_rolling_p{min_percentile}"] = (
        oi_chg_ratio.rolling(**roll_kw).quantile(q_low).fillna(0.0).astype(float)
    )

    eq_c = pd.to_numeric(out["close"], errors="coerce")
    fc = pd.to_numeric(out["close"], errors="coerce")

    if equity_side:
        if fut_close_lookup is None or fut_close_lookup.empty:
            out["fut_eq_close_diff"] = np.nan
        else:
            sib = pd.to_numeric(fut_close_lookup.reindex(out["date_norm"].tolist()), errors="coerce")
            diff = sib.to_numpy(dtype=float) - eq_c.to_numpy(dtype=float)
            out["fut_eq_close_diff"] = diff
            bad = sib.isna() | eq_c.isna()
            out.loc[bad, "fut_eq_close_diff"] = np.nan
    else:
        if eq_close_lookup is None or eq_close_lookup.empty:
            out["fut_eq_close_diff"] = np.nan
        else:
            sib = pd.to_numeric(eq_close_lookup.reindex(out["date_norm"].tolist()), errors="coerce")
            diff = fc.to_numpy(dtype=float) - sib.to_numpy(dtype=float)
            out["fut_eq_close_diff"] = diff
            bad = sib.isna() | fc.isna()
            out.loc[bad, "fut_eq_close_diff"] = np.nan

    fe = pd.to_numeric(out["fut_eq_close_diff"], errors="coerce")
    lbl = pd.Series(index=out.index, dtype=object)
    ok = fe.notna()
    lbl.loc[ok & (fe > 0)] = "Premium"
    lbl.loc[ok & (fe < 0)] = "Discount"
    lbl.loc[ok & (fe == 0)] = "No Change"
    out["premium_discount"] = lbl.astype(object)

    keep = original_cols + list(derived_columns)
    for c in keep:
        if c not in out.columns:
            out[c] = np.nan if c != "premium_discount" else None
    return out[[c for c in keep if c in out.columns]]


def persist_table(con: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Replace table preserving structure via DROP + recreate from DataFrame dtypes."""
    con.execute(f'DROP TABLE IF EXISTS "{table}_tmp_reload"')
    df.to_sql(f"{table}_tmp_reload", con, index=False)
    con.execute(f'DROP TABLE "{table}"')
    con.execute(f'ALTER TABLE "{table}_tmp_reload" RENAME TO "{table}"')
    con.commit()


def main() -> None:
    default_db = Path(__file__).resolve().parent / "some_tables.db"
    default_env = Path(__file__).resolve().parent / "env.txt"
    p = argparse.ArgumentParser(description="Add futures-equity derived columns to DB tables.")
    p.add_argument("--db", type=Path, default=default_db, help="SQLite database path")
    p.add_argument("--env", type=Path, default=default_env, help="Config file (rolling_window_size, max_percentile, min_percentile)")
    p.add_argument("--dry-run", action="store_true", help="Print pairings only; do not modify DB.")
    p.add_argument("--no-backup", action="store_true", help="Skip creating a .bak copy before writes.")
    args = p.parse_args()

    db_path: Path = args.db.resolve()
    env_path: Path = args.env.resolve()
    roll_w, p_max, p_min = load_env_config(env_path)

    if not db_path.is_file():
        raise SystemExit(f"Database file not found: {db_path}")

    con = sqlite3.connect(db_path)

    tables = list_user_tables(con)
    fut_to_eq, eq_to_fut = classify_pairings(tables)

    print(
        f"Config from {env_path}: rolling_window_size={roll_w}, "
        f"max_percentile={p_max}, min_percentile={p_min}"
    )

    print("FUT -> EQ:")
    for k, v in sorted(fut_to_eq.items()):
        print(f"  {k} -> {v}")
    print("EQ -> FUT (used):")
    for k, v in sorted(eq_to_fut.items()):
        print(f"  {k} -> {v}")

    if args.dry_run:
        con.close()
        print("Dry run; no writes.")
        return

    if not args.no_backup:
        bak = db_path.with_name(f"{db_path.name}.bak.{utc_now_compact()}")
        shutil.copy2(db_path, bak)
        print(f"Backed up DB to {bak}")

    lookups_fut_close: Dict[str, pd.Series] = {}
    lookups_eq_close: Dict[str, pd.Series] = {}

    for ft in fut_to_eq:
        lookups_fut_close[ft] = build_minute_lookup(load_table(con, ft), "close")
    for eq in eq_to_fut:
        lookups_eq_close[eq] = build_minute_lookup(load_table(con, eq), "close")

    touched: List[str] = []

    try:
        for ft, eq_name in fut_to_eq.items():
            raw = load_table(con, ft)
            eq_lut = lookups_eq_close.get(eq_name)
            enriched = enrich_frame(
                raw,
                fut_close_lookup=None,
                eq_close_lookup=eq_lut if eq_lut is not None else pd.Series(dtype=float),
                equity_side=False,
                rolling_window_size=roll_w,
                max_percentile=p_max,
                min_percentile=p_min,
            )
            persist_table(con, ft, enriched)
            touched.append(ft)

        for eq_name, ft_name in eq_to_fut.items():
            raw = load_table(con, eq_name)
            fc_lut = lookups_fut_close.get(ft_name)
            enriched = enrich_frame(
                raw,
                fut_close_lookup=fc_lut if fc_lut is not None else pd.Series(dtype=float),
                eq_close_lookup=None,
                equity_side=True,
                rolling_window_size=roll_w,
                max_percentile=p_max,
                min_percentile=p_min,
            )
            persist_table(con, eq_name, enriched)
            touched.append(eq_name)

        orphan = sorted(set(tables) - set(touched))
        if orphan:
            print("Warning - tables without FUT/EQ sibling pair were skipped:", orphan)

    finally:
        con.close()

    print(f"Updated {len(touched)} tables: {sorted(touched)}")


if __name__ == "__main__":
    main()
