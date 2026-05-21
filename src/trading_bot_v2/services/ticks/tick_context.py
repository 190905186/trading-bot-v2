"""Load token metadata pickles and Zerodha instrument_token maps for unified ticks."""



from __future__ import annotations



import csv

import pickle

from dataclasses import dataclass, field

from pathlib import Path

from typing import Any, Dict, Mapping, Optional



from trading_bot_v2.token_universe.loader import universe_dir_from_env

from trading_bot_v2.token_universe.zerodha_mapping import _default_instruments_csv





def normalize_exchange_token(token: Any) -> Optional[str]:

    """Canonical string exchange token for pickle/CSV lookups (never instrument_token)."""

    if token is None:

        return None

    raw = str(token).strip()

    if not raw:

        return None

    try:

        return str(int(float(raw)))

    except (TypeError, ValueError):

        return raw





@dataclass

class TickMappingContext:

    """Maps and pickles shared by broker adapters when building unified ticks."""



    token_symbol_map: Dict[str, str] = field(default_factory=dict)

    token_tick_size_map: Dict[str, float] = field(default_factory=dict)

    token_exch_map: Dict[str, str] = field(default_factory=dict)

    instrument_to_exchange_token: Dict[int, str] = field(default_factory=dict)

    exchange_token_to_symbol: Dict[str, str] = field(default_factory=dict)



    @classmethod

    def load(cls, universe_dir: Optional[Path] = None, *, instruments_csv: Optional[Path] = None) -> TickMappingContext:

        d = universe_dir or universe_dir_from_env()

        ctx = cls()

        for name, attr in (

            ("token_symbol_map.pkl", "token_symbol_map"),

            ("token_tick_size_map.pkl", "token_tick_size_map"),

            ("token_exch_map.pkl", "token_exch_map"),

        ):

            path = d / name

            if path.is_file():

                with path.open("rb") as f:

                    raw = pickle.load(f)

                normalized = {

                    normalize_exchange_token(k) or str(k): v for k, v in raw.items()

                }

                setattr(ctx, attr, normalized)



        csv_path = instruments_csv or _default_instruments_csv()

        if csv_path.is_file():

            inst_to_ex, ex_to_sym = _load_from_instruments_csv(csv_path)

            ctx.instrument_to_exchange_token = inst_to_ex

            ctx.exchange_token_to_symbol = ex_to_sym

        return ctx



    def merge_instrument_exchange_map(self, mapping: Mapping[int, str]) -> None:
        """Overlay subscribe-batch instrument_token -> exchange_token pairs."""
        for inst, exch in mapping.items():
            try:
                inst_key = int(inst)
            except (TypeError, ValueError):
                continue
            ex_key = normalize_exchange_token(exch)
            if ex_key:
                self.instrument_to_exchange_token[inst_key] = ex_key

    def exchange_token_for_instrument(self, instrument_token: int | float | str) -> Optional[str]:
        try:
            inst_key = int(float(str(instrument_token).strip()))
        except (TypeError, ValueError):
            return None
        return self.instrument_to_exchange_token.get(inst_key)



    def symbol_for_exchange_token(self, exchange_token: Any) -> Optional[str]:

        """Resolve symbol_name from exchange token (v1 token_symbol_map keys)."""

        key = normalize_exchange_token(exchange_token)

        if not key:

            return None

        sym = self.token_symbol_map.get(key)

        if sym:

            return sym

        return self.exchange_token_to_symbol.get(key)



    def exchange_for_exchange_token(self, exchange_token: Any) -> Optional[str]:

        key = normalize_exchange_token(exchange_token)

        if not key:

            return None

        return self.token_exch_map.get(key)



    def tick_size_for_exchange_token(self, exchange_token: Any) -> float:

        key = normalize_exchange_token(exchange_token)

        if not key:

            return 0.01

        raw = self.token_tick_size_map.get(key)

        return (raw / 100) if raw is not None else 0.01





def _load_from_instruments_csv(csv_path: Path) -> tuple[Dict[int, str], Dict[str, str]]:

    inst_to_ex: Dict[int, str] = {}

    ex_to_sym: Dict[str, str] = {}

    with csv_path.open(newline="", encoding="utf-8") as f:

        for row in csv.DictReader(f):

            try:

                inst = int(float(row["instrument_token"]))

                ex_key = normalize_exchange_token(row["exchange_token"])

            except (KeyError, TypeError, ValueError):

                continue

            if not ex_key:

                continue

            inst_to_ex[inst] = ex_key

            symbol = (row.get("tradingsymbol") or row.get("name") or "").strip()

            if symbol and ex_key not in ex_to_sym:

                ex_to_sym[ex_key] = symbol

    return inst_to_ex, ex_to_sym





def _load_instrument_to_exchange(csv_path: Path) -> Dict[int, str]:

    inst_to_ex, _ = _load_from_instruments_csv(csv_path)

    return inst_to_ex


