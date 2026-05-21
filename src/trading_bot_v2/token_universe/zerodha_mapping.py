"""Map Angel/master exchange_token ints to Zerodha Kite instrument_token (v1 parity)."""

from __future__ import annotations

import csv
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger("trading_bot_v2.token_universe.zerodha_mapping")

_CACHE_MAX_AGE_SEC = 86400


def _default_instruments_csv() -> Path:
    raw = os.getenv("TB2_ZERODHA_INSTRUMENTS_CSV", "").strip()
    if raw:
        return Path(raw).resolve()
    root = Path(__file__).resolve().parents[3]
    return (root / "data" / "instruments.csv").resolve()


def _load_amxidx_dict(universe_dir: Path) -> Dict[Any, str]:
    candidates = [
        universe_dir / "amxidx_dict.pkl",
    ]
    code_root = Path(__file__).resolve().parents[4]
    candidates.append(code_root / "trading-bot" / "src" / "token_objects" / "amxidx_dict.pkl")
    for path in candidates:
        if path.is_file():
            with path.open("rb") as f:
                raw = pickle.load(f)
            return dict(raw)
    logger.warning("amxidx_dict.pkl not found; AMXIDX mapping skipped")
    return {}


def _read_instruments_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _download_instruments_csv(path: Path, *, api_key: str, access_token: str) -> None:
    try:
        from kiteconnect import KiteConnect  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("kiteconnect is required to download Zerodha instruments.") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    instruments = kite.instruments()
    if not instruments:
        raise RuntimeError("Zerodha instruments() returned empty list")

    fieldnames = list(instruments[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(instruments)
    logger.info("Downloaded %s Zerodha instruments to %s", len(instruments), path)


def load_instruments_table(
    *,
    api_key: str,
    access_token: str,
    cache_path: Optional[Path] = None,
) -> List[Dict[str, str]]:
    """Load Kite instruments from CSV cache or refresh from API (max age 24h)."""
    path = cache_path or _default_instruments_csv()
    refresh = True
    if path.is_file():
        age = time.time() - path.stat().st_mtime
        if age < _CACHE_MAX_AGE_SEC:
            refresh = False
    if refresh:
        logger.info("Refreshing Zerodha instruments cache at %s", path)
        _download_instruments_csv(path, api_key=api_key, access_token=access_token)
    return _read_instruments_csv(path)


def map_exchange_tokens_to_instrument_tokens(
    exchange_tokens: List[int],
    *,
    api_key: str,
    access_token: str,
    universe_dir: Path,
    instruments_csv: Optional[Path] = None,
) -> List[int]:
    """Convert exchange_token ints to Kite instrument_token (subscribe list only)."""
    instruments, _ = map_exchange_tokens_with_reverse(
        exchange_tokens,
        api_key=api_key,
        access_token=access_token,
        universe_dir=universe_dir,
        instruments_csv=instruments_csv,
    )
    return instruments


def map_exchange_tokens_with_reverse(
    exchange_tokens: List[int],
    *,
    api_key: str,
    access_token: str,
    universe_dir: Path,
    instruments_csv: Optional[Path] = None,
) -> tuple[List[int], Dict[int, str]]:
    """
    Convert batch token ints (Angel exchange_token) to Kite instrument_token for subscribe/historical.

    Returns (instrument_tokens, instrument_token -> exchange_token string) for tick enrichment.
    """
    if not exchange_tokens:
        return [], {}

    amxidx_dict = _load_amxidx_dict(universe_dir)
    rows = load_instruments_table(
        api_key=api_key,
        access_token=access_token,
        cache_path=instruments_csv,
    )

    token_map: Dict[int, int] = {}
    symbol_map: Dict[str, int] = {}
    for row in rows:
        try:
            inst = int(float(row["instrument_token"]))
            exch = int(float(row["exchange_token"]))
        except (KeyError, TypeError, ValueError):
            continue
        token_map[exch] = inst
        sym = str(row.get("tradingsymbol", "")).strip().lower()
        if sym:
            symbol_map[sym] = inst

    amxidx_key_strs = {str(k) for k in amxidx_dict.keys()}
    filtered_exchange = [et for et in exchange_tokens if str(et) not in amxidx_key_strs]

    for key, symbol in amxidx_dict.items():
        try:
            k_int = int(key)
        except (TypeError, ValueError):
            continue
        sym_lower = str(symbol).strip().lower()
        inst = symbol_map.get(sym_lower)
        if inst is not None:
            token_map[k_int] = inst

    out: List[int] = []
    reverse: Dict[int, str] = {}
    missing = 0
    for et in filtered_exchange:
        inst = token_map.get(et)
        if inst is None:
            missing += 1
            continue
        inst_int = int(inst)
        out.append(inst_int)
        reverse[inst_int] = str(et)

    if missing:
        logger.warning(
            "Zerodha mapping: %s exchange_token(s) had no instrument_token in Kite instruments",
            missing,
        )
    logger.info(
        "Zerodha mapping: %s exchange_token(s) -> %s instrument_token(s)",
        len(exchange_tokens),
        len(out),
    )
    return out, reverse
