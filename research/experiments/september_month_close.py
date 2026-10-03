"""Close September 2026 as a diagnostic without reopening the formal holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

import pandas as pd

from research.binance_data import fetch_klines, load_csv, save_csv
from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_funding_carry import _universe, fetch_funding
from research.experiments.cross_sectional_funding_carry_v2 import simulate
from research.experiments.cross_sectional_funding_carry_v3 import (
    combined_inputs,
    summarize_window,
    v2_protocol,
)


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "september_2026_month_close.toml"
V3_PROTOCOL = BASE_DIR / "experiments" / "cross_sectional_funding_carry_v3.toml"
DATA_DIR = BASE_DIR / "data" / "september_2026_month_close"
MANIFEST_PATH = BASE_DIR / "manifests" / "september_2026_month_close.json"


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    if protocol["experiment"].get("status") != "PREREGISTERED_DIAGNOSTIC":
        raise ValueError("month close must be preregistered")
    if protocol["decision"].get("formal_holdout_decision") != "FAIL":
        raise ValueError("diagnostic cannot replace the frozen holdout decision")
    if protocol["decision"].get("effect") != "DIAGNOSTIC_ONLY":
        raise ValueError("month close must have diagnostic-only effect")
    return protocol


def load_v3_protocol() -> dict:
    with V3_PROTOCOL.open("rb") as handle:
        return tomllib.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def price_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return DATA_DIR / f"{symbol}_{data['interval']}_{data['closure_start']}_{data['closure_end']}.csv"


def funding_path(symbol: str, protocol: dict) -> Path:
    data = protocol["data"]
    return DATA_DIR / f"{symbol}_funding_{data['closure_start']}_{data['closure_end']}.csv"


def acquire(protocol: dict, *, refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    v3 = load_v3_protocol()
    funding_protocol = {"data": {
        "start": protocol["data"]["closure_start"],
        "discovery_end": protocol["data"]["closure_end"],
        "funding_endpoint": "https://fapi.binance.com/fapi/v1/fundingRate",
    }}
    entries = []
    for symbol in _universe(v3):
        p_path, f_path = price_path(symbol, protocol), funding_path(symbol, protocol)
        if refresh or not p_path.exists():
            frame = fetch_klines(
                symbol,
                protocol["data"]["interval"],
                protocol["data"]["closure_start"],
                protocol["data"]["closure_end"],
            )
            if frame.empty:
                raise RuntimeError(f"no month-close prices returned for {symbol}")
            save_csv(frame, p_path)
        if refresh or not f_path.exists():
            fetch_funding(symbol, funding_protocol).to_csv(f_path, index=False)
        for kind, path, time_column in (("price", p_path, "open_time"), ("funding", f_path, "fundingTime")):
            frame = pd.read_csv(path)
            times = pd.to_datetime(frame[time_column], utc=True, format="mixed")
            entries.append({
                "symbol": symbol,
                "kind": kind,
                "path": path.relative_to(BASE_DIR).as_posix(),
                "rows": len(frame),
                "first_time": times.min().isoformat(),
                "last_time": times.max().isoformat(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
    manifest = {
        "dataset_id": "september-2026-calendar-close",
        "requested_start": protocol["data"]["closure_start"],
        "requested_end_exclusive": protocol["data"]["closure_end"],
        "role": "DIAGNOSTIC_ONLY",
        "files": entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def combined_month_inputs(protocol: dict) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict]:
    v3 = load_v3_protocol()
    opens, funding = combined_inputs(v3)
    extension_prices = []
    for symbol in _universe(v3):
        extension = load_csv(price_path(symbol, protocol)).set_index("open_time")["open"].rename(symbol)
        extension_prices.append(extension)
        extra_funding = pd.read_csv(funding_path(symbol, protocol))
        extra_funding["fundingTime"] = pd.to_datetime(extra_funding["fundingTime"], utc=True, format="mixed")
        extra_funding["fundingRate"] = pd.to_numeric(extra_funding["fundingRate"], errors="raise")
        funding[symbol] = pd.concat([funding[symbol], extra_funding], ignore_index=True).drop_duplicates("fundingTime").sort_values("fundingTime")
    extension_frame = pd.concat(extension_prices, axis=1).sort_index()
    opens = pd.concat([opens, extension_frame]).sort_index()
    opens = opens.loc[~opens.index.duplicated(keep="last")]
    return opens, funding, v3


def run(protocol: dict) -> dict:
    opens, funding, v3 = combined_month_inputs(protocol)
    periods, _ = simulate(
        opens,
        funding,
        v2_protocol(v3),
        start="2024-04-01",
        end=protocol["data"]["closure_end"],
    )
    costs = protocol["evaluation"]["costs"]
    full_month = summarize_window(
        periods,
        protocol["evaluation"]["month_start"],
        protocol["evaluation"]["month_end"],
        costs,
    )
    increment = summarize_window(
        periods,
        protocol["evaluation"]["increment_start"],
        protocol["evaluation"]["month_end"],
        costs,
    )
    report = {
        "experiment_id": protocol["experiment"]["experiment_id"],
        "strategy_version": protocol["experiment"]["strategy_version"],
        "strategy_changed": False,
        "period": [protocol["evaluation"]["month_start"], protocol["evaluation"]["month_end"]],
        "full_month": full_month,
        "increment_after_original_holdout": increment,
        "formal_holdout_decision": "FAIL",
        "effect": "DIAGNOSTIC_ONLY",
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "september_2026_month_close.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.download or args.refresh:
        manifest = acquire(protocol, refresh=args.refresh)
        print(f"closure_files={len(manifest['files'])}")
    print(json.dumps(run(protocol), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
