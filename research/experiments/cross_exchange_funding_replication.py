"""Replicate the frozen V3 funding carry strategy on Bybit and OKX."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import time
import tomllib
import zipfile
from pathlib import Path

import pandas as pd
import requests
import truststore

from research.config import BASE_DIR, RESULTS_DIR
from research.experiments.cross_sectional_funding_carry_v2 import simulate
from research.experiments.delta_neutral_carry import max_compounded_drawdown
from research.metrics import summarize_returns


DEFAULT_PROTOCOL = BASE_DIR / "experiments" / "cross_exchange_funding_replication_v1.toml"
DATA_DIR = BASE_DIR / "data" / "cross_exchange_funding_replication_v1"
MANIFEST_PATH = BASE_DIR / "manifests" / "cross_exchange_funding_replication_v1.json"
RESULT_PATH = RESULTS_DIR / "cross_exchange_funding_replication_v1_decision.json"
SUMMARY_PATH = RESULTS_DIR / "cross_exchange_funding_replication_v1_summary.csv"
PERIODS_PATH = RESULTS_DIR / "cross_exchange_funding_replication_v1_periods.csv"

truststore.inject_into_ssl()


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    required = {"experiment", "data", "bybit", "okx", "strategy", "evaluation", "decision"}
    missing = required.difference(protocol)
    if missing:
        raise ValueError(f"protocol missing sections: {sorted(missing)}")
    if protocol["experiment"].get("status") != "PREREGISTERED":
        raise ValueError("replication must be preregistered")
    if protocol["decision"].get("effect") != (
        "research evidence only; cannot promote to paper or real trading without a future temporal holdout"
    ):
        raise ValueError("replication cannot authorize trading")
    return protocol


def _request_json(session: requests.Session, url: str, params: dict) -> dict:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(0.5 * (2 ** attempt))
    else:  # pragma: no cover - defensive; loop either breaks or raises
        raise RuntimeError("request retry loop ended unexpectedly") from last_error
    if isinstance(payload, dict) and payload.get("retCode", 0) not in (0, "0"):
        raise RuntimeError(f"remote error {payload.get('retCode')}: {payload.get('retMsg')}")
    if isinstance(payload, dict) and payload.get("code", "0") != "0":
        raise RuntimeError(f"remote error {payload.get('code')}: {payload.get('msg')}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _milliseconds(value: str | pd.Timestamp) -> int:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return int(stamp.timestamp() * 1000)


def data_path(venue: str, base: str, kind: str, protocol: dict) -> Path:
    data = protocol["data"]
    return DATA_DIR / venue / f"{base}_{kind}_{data['start']}_{data['end']}.csv"


def fetch_bybit_prices(session: requests.Session, base: str, protocol: dict) -> pd.DataFrame:
    config, data = protocol["bybit"], protocol["data"]
    start_ms, end_ms = _milliseconds(data["start"]), _milliseconds(data["end"])
    cursor, rows = end_ms - 1, []
    while cursor >= start_ms:
        payload = _request_json(session, config["price_endpoint"], {
            "category": config["category"], "symbol": config["symbol_format"].format(base=base),
            "interval": config["interval"], "end": cursor, "limit": 1000,
        })
        batch = payload["result"]["list"]
        if not batch:
            break
        rows.extend(batch)
        oldest = min(int(row[0]) for row in batch)
        if oldest > cursor:
            raise RuntimeError(f"Bybit price pagination moved forward for {base}")
        next_cursor = oldest - 1
        if next_cursor >= cursor:
            raise RuntimeError(f"Bybit price pagination stalled for {base}")
        cursor = next_cursor
        if oldest <= start_ms:
            break
        time.sleep(0.03)
    frame = pd.DataFrame(rows, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "turnover"
    ])
    if frame.empty:
        return pd.DataFrame(columns=["symbol", "open_time", "open"])
    frame["open_time"] = pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="ms", utc=True)
    frame["open"] = pd.to_numeric(frame["open"], errors="raise")
    frame["symbol"] = base
    mask = (frame["open_time"] >= pd.Timestamp(data["start"], tz="UTC")) & (
        frame["open_time"] < pd.Timestamp(data["end"], tz="UTC")
    )
    return frame.loc[mask, ["symbol", "open_time", "open"]].drop_duplicates("open_time").sort_values("open_time")


def fetch_bybit_funding(session: requests.Session, base: str, protocol: dict) -> pd.DataFrame:
    config, data = protocol["bybit"], protocol["data"]
    start_ms, end_ms = _milliseconds(data["start"]), _milliseconds(data["end"])
    cursor, rows = end_ms - 1, []
    while cursor >= start_ms:
        payload = _request_json(session, config["funding_endpoint"], {
            "category": config["category"], "symbol": config["symbol_format"].format(base=base),
            "endTime": cursor, "limit": 200,
        })
        batch = payload["result"]["list"]
        if not batch:
            break
        rows.extend(batch)
        oldest = min(int(row["fundingRateTimestamp"]) for row in batch)
        next_cursor = oldest - 1
        if next_cursor >= cursor:
            raise RuntimeError(f"Bybit funding pagination stalled for {base}")
        cursor = next_cursor
        if oldest <= start_ms:
            break
        time.sleep(0.03)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["symbol", "fundingTime", "fundingRate"])
    frame["fundingTime"] = pd.to_datetime(pd.to_numeric(frame["fundingRateTimestamp"]), unit="ms", utc=True)
    frame["fundingRate"] = pd.to_numeric(frame["fundingRate"], errors="raise")
    frame["symbol"] = base
    mask = (frame["fundingTime"] >= pd.Timestamp(data["start"], tz="UTC")) & (
        frame["fundingTime"] < pd.Timestamp(data["end"], tz="UTC")
    )
    return frame.loc[mask, ["symbol", "fundingTime", "fundingRate"]].drop_duplicates("fundingTime").sort_values("fundingTime")


def fetch_okx_prices(session: requests.Session, base: str, protocol: dict) -> pd.DataFrame:
    config, data = protocol["okx"], protocol["data"]
    start_ms, end_ms = _milliseconds(data["start"]), _milliseconds(data["end"])
    cursor, rows = end_ms, []
    while cursor > start_ms:
        payload = _request_json(session, config["price_endpoint"], {
            "instId": config["symbol_format"].format(base=base), "bar": config["bar"],
            "after": cursor, "limit": 300,
        })
        batch = payload["data"]
        if not batch:
            break
        rows.extend(batch)
        oldest = min(int(row[0]) for row in batch)
        if oldest >= cursor:
            raise RuntimeError(f"OKX price pagination stalled for {base}")
        cursor = oldest
        if oldest <= start_ms:
            break
        time.sleep(0.05)
    columns = ["timestamp", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "confirm"]
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return pd.DataFrame(columns=["symbol", "open_time", "open"])
    frame["open_time"] = pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="ms", utc=True)
    frame["open"] = pd.to_numeric(frame["open"], errors="raise")
    frame["symbol"] = base
    mask = (frame["open_time"] >= pd.Timestamp(data["start"], tz="UTC")) & (
        frame["open_time"] < pd.Timestamp(data["end"], tz="UTC")
    ) & (frame["confirm"].astype(str) == "1")
    return frame.loc[mask, ["symbol", "open_time", "open"]].drop_duplicates("open_time").sort_values("open_time")


def _okx_month_chunks(start: str, end: str) -> list[tuple[int, int]]:
    cursor = pd.Timestamp(start, tz="UTC").normalize()
    final = pd.Timestamp(end, tz="UTC").normalize() - pd.Timedelta(days=1)
    chunks = []
    while cursor <= final:
        chunk_end = min(cursor + pd.DateOffset(months=9) - pd.Timedelta(days=1), final)
        chunks.append((_milliseconds(cursor), _milliseconds(chunk_end)))
        cursor = (chunk_end + pd.Timedelta(days=1)).normalize()
    return chunks


def okx_funding_catalog(session: requests.Session, bases: list[str], protocol: dict) -> dict[str, list[str]]:
    data = protocol["data"]
    catalog = {base: [] for base in bases}
    for offset in range(0, len(bases), 5):
        batch = bases[offset:offset + 5]
        families = ",".join(f"{base}-USDT" for base in batch)
        for begin, end in _okx_month_chunks(data["start"], data["end"]):
            payload = _request_json(session, protocol["okx"]["funding_archive_endpoint"], {
                "module": "3", "instType": "SWAP", "instFamilyList": families,
                "dateAggrType": "monthly", "begin": begin, "end": end,
            })
            for detail in payload.get("data", [{}])[0].get("details", []):
                family = detail.get("instFamily", "")
                base = family.removesuffix("-USDT")
                if base in catalog:
                    catalog[base].extend(item["url"] for item in detail.get("groupDetails", []))
            time.sleep(0.20)
    return {base: sorted(set(urls)) for base, urls in catalog.items()}


def fetch_okx_funding(session: requests.Session, base: str, urls: list[str], protocol: dict) -> pd.DataFrame:
    frames = []
    for url in urls:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".csv"):
                    frames.append(pd.read_csv(archive.open(name)))
        time.sleep(0.03)
    if not frames:
        return pd.DataFrame(columns=["symbol", "fundingTime", "fundingRate"])
    frame = pd.concat(frames, ignore_index=True)
    frame["fundingTime"] = pd.to_datetime(pd.to_numeric(frame["funding_time"]), unit="ms", utc=True)
    frame["fundingRate"] = pd.to_numeric(frame["funding_rate"], errors="raise")
    frame["symbol"] = base
    data = protocol["data"]
    mask = (frame["fundingTime"] >= pd.Timestamp(data["start"], tz="UTC")) & (
        frame["fundingTime"] < pd.Timestamp(data["end"], tz="UTC")
    )
    return frame.loc[mask, ["symbol", "fundingTime", "fundingRate"]].drop_duplicates("fundingTime").sort_values("fundingTime")


def acquire(protocol: dict, *, venues: list[str] | None = None, refresh: bool = False) -> dict:
    selected = venues or list(protocol["data"]["venues"])
    symbols = list(protocol["data"]["candidate_symbols"])
    entries, errors = [], []
    session = requests.Session()
    okx_catalog = okx_funding_catalog(session, symbols, protocol) if "okx" in selected else {}
    for venue in selected:
        for index, base in enumerate(symbols, start=1):
            print(f"acquire venue={venue} symbol={base} ({index}/{len(symbols)})", flush=True)
            for kind in ("price", "funding"):
                path = data_path(venue, base, kind, protocol)
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if refresh or not path.exists():
                        if venue == "bybit" and kind == "price":
                            frame = fetch_bybit_prices(session, base, protocol)
                        elif venue == "bybit":
                            frame = fetch_bybit_funding(session, base, protocol)
                        elif venue == "okx" and kind == "price":
                            frame = fetch_okx_prices(session, base, protocol)
                        elif venue == "okx":
                            frame = fetch_okx_funding(session, base, okx_catalog.get(base, []), protocol)
                        else:
                            raise ValueError(f"unsupported venue: {venue}")
                        frame.to_csv(path, index=False)
                    frame = pd.read_csv(path)
                    time_column = "open_time" if kind == "price" else "fundingTime"
                    times = pd.to_datetime(frame[time_column], utc=True, format="mixed") if not frame.empty else pd.Series(dtype="datetime64[ns, UTC]")
                    entries.append({
                        "venue": venue, "symbol": base, "kind": kind,
                        "path": path.relative_to(BASE_DIR).as_posix(), "rows": len(frame),
                        "first_time": times.min().isoformat() if len(times) else None,
                        "last_time": times.max().isoformat() if len(times) else None,
                        "bytes": path.stat().st_size, "sha256": _sha256(path),
                    })
                except Exception as exc:  # keep other symbols auditable
                    errors.append({"venue": venue, "symbol": base, "kind": kind, "error": f"{type(exc).__name__}: {exc}"})
    manifest = {
        "dataset_id": "cross-exchange-funding-replication-v1",
        "requested_start": protocol["data"]["start"],
        "requested_end_exclusive": protocol["data"]["end"],
        "sources": {"bybit": protocol["bybit"], "okx": protocol["okx"]},
        "files": entries, "errors": errors,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def coverage_ratio(frame: pd.DataFrame, time_column: str, start: str, end: str, *, expected_frequency: str | None = None) -> float:
    if frame.empty:
        return 0.0
    times = pd.to_datetime(frame[time_column], utc=True, format="mixed").drop_duplicates().sort_values()
    start_time, end_time = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    if expected_frequency:
        expected = len(pd.date_range(start_time, end_time, freq=expected_frequency, inclusive="left"))
        return min(1.0, len(times[(times >= start_time) & (times < end_time)]) / expected) if expected else 0.0
    duration = (end_time - start_time).total_seconds()
    covered = max(0.0, (min(times.max(), end_time) - max(times.min(), start_time)).total_seconds())
    return min(1.0, covered / duration) if duration else 0.0


def load_venue(protocol: dict, venue: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[dict]]:
    data = protocol["data"]
    rows, prices, funding = [], {}, {}
    for base in data["candidate_symbols"]:
        p_path, f_path = data_path(venue, base, "price", protocol), data_path(venue, base, "funding", protocol)
        if not p_path.exists() or not f_path.exists():
            rows.append({"symbol": base, "price_coverage": 0.0, "funding_coverage": 0.0, "eligible": False})
            continue
        p_frame, f_frame = pd.read_csv(p_path), pd.read_csv(f_path)
        price_coverage = coverage_ratio(p_frame, "open_time", data["start"], data["end"], expected_frequency="4h")
        funding_coverage = coverage_ratio(f_frame, "fundingTime", data["start"], data["end"])
        eligible = min(price_coverage, funding_coverage) >= data["minimum_symbol_coverage"]
        rows.append({"symbol": base, "price_coverage": price_coverage, "funding_coverage": funding_coverage, "eligible": eligible})
        if eligible:
            p_frame["open_time"] = pd.to_datetime(p_frame["open_time"], utc=True, format="mixed")
            p_frame["open"] = pd.to_numeric(p_frame["open"], errors="raise")
            f_frame["fundingTime"] = pd.to_datetime(f_frame["fundingTime"], utc=True, format="mixed")
            f_frame["fundingRate"] = pd.to_numeric(f_frame["fundingRate"], errors="raise")
            prices[base] = p_frame.set_index("open_time")["open"].sort_index()
            funding[base] = f_frame.sort_values("fundingTime")
    opens = pd.concat(prices, axis=1, join="inner").sort_index() if prices else pd.DataFrame()
    return opens, funding, rows


def _simulation_protocol(protocol: dict) -> dict:
    strategy = protocol["strategy"]
    return {"signal": {
        "trailing_funding_records": strategy["trailing_funding_records"],
        "rebalance_funding_periods": strategy["rebalance_funding_periods"],
        "entry_fraction": strategy["entry_fraction"],
        "exit_boundary": strategy["exit_boundary"],
    }}


def summarize_venue(periods: pd.DataFrame, protocol: dict, venue: str) -> pd.DataFrame:
    evaluation, data = protocol["evaluation"], protocol["data"]
    bounds = {
        "2024": (data["evaluation_start"], "2025-01-01"),
        "2025": ("2025-01-01", "2026-01-01"),
        "2026": ("2026-01-01", data["end"]),
        "full": (data["evaluation_start"], data["end"]),
    }
    rows = []
    for segment, (start, end) in bounds.items():
        selected = periods[(periods["entry_time"] >= pd.Timestamp(start, tz="UTC")) & (periods["exit_time"] < pd.Timestamp(end, tz="UTC"))]
        for cost in protocol["strategy"]["round_trip_costs"]:
            net = selected["gross_return"] - selected["turnover"] * cost / 2
            rows.append({
                "venue": venue, "segment": segment, "cost": cost,
                **summarize_returns(net),
                "max_compounded_drawdown": max_compounded_drawdown(net),
                "mean_turnover": float(selected["turnover"].mean()) if not selected.empty else math.nan,
                "mean_price_component": float(selected["price_component"].mean()) if not selected.empty else math.nan,
                "mean_funding_component": float(selected["funding_component"].mean()) if not selected.empty else math.nan,
            })
    return pd.DataFrame(rows)


def decide_venue(summary: pd.DataFrame, protocol: dict) -> dict:
    evaluation = protocol["evaluation"]
    costs = protocol["strategy"]["round_trip_costs"]
    reasons = []
    for segment in ("2024", "2025", "2026"):
        row = summary[(summary["segment"] == segment) & (summary["cost"] == costs[0])].iloc[0]
        minimum = evaluation["minimum_periods_2026_partial"] if segment == "2026" else evaluation["minimum_periods_per_full_year"]
        if row["samples"] < minimum:
            reasons.append(f"{segment}_samples")
        if not math.isfinite(float(row["profit_factor"])) or row["profit_factor"] < evaluation["base_cost_min_profit_factor_each_segment"]:
            reasons.append(f"{segment}_base_profit_factor")
    base = summary[(summary["segment"] == "full") & (summary["cost"] == costs[0])].iloc[0]
    stress = summary[(summary["segment"] == "full") & (summary["cost"] == costs[-1])].iloc[0]
    if not math.isfinite(float(base["profit_factor"])) or base["profit_factor"] < evaluation["base_cost_min_profit_factor_full_period"]:
        reasons.append("full_base_profit_factor")
    if not math.isfinite(float(stress["profit_factor"])) or stress["profit_factor"] < evaluation["stress_cost_min_profit_factor_full_period"]:
        reasons.append("full_stress_profit_factor")
    if not math.isfinite(float(base["max_compounded_drawdown"])) or base["max_compounded_drawdown"] > evaluation["max_full_period_drawdown"]:
        reasons.append("full_drawdown")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "full_base_profit_factor": float(base["profit_factor"]),
        "full_stress_profit_factor": float(stress["profit_factor"]),
        "full_drawdown": float(base["max_compounded_drawdown"]),
        "full_samples": int(base["samples"]),
    }


def run(protocol: dict) -> dict:
    all_summaries, all_periods, venues = [], [], {}
    for venue in protocol["data"]["venues"]:
        opens, funding, coverage = load_venue(protocol, venue)
        eligible = sorted(funding)
        if len(eligible) < protocol["data"]["minimum_eligible_symbols_per_venue"]:
            venues[venue] = {"status": "INSUFFICIENT_DATA", "eligible_symbols": eligible, "coverage": coverage}
            continue
        periods, _ = simulate(
            opens, funding, _simulation_protocol(protocol),
            start=protocol["data"]["evaluation_start"], end=protocol["data"]["end"],
        )
        if periods.empty:
            venues[venue] = {"status": "INSUFFICIENT_DATA", "eligible_symbols": eligible, "coverage": coverage}
            continue
        summary = summarize_venue(periods, protocol, venue)
        decision = decide_venue(summary, protocol)
        venues[venue] = {"status": "PASS" if decision["passed"] else "FAIL", "eligible_symbols": eligible, "coverage": coverage, **decision}
        periods.insert(0, "venue", venue)
        all_summaries.append(summary)
        all_periods.append(periods)
    evaluable = [value for value in venues.values() if value["status"] in {"PASS", "FAIL"}]
    passes = sum(value["status"] == "PASS" for value in evaluable)
    if len(evaluable) < len(protocol["data"]["venues"]):
        decision = "INCOMPLETE_DATA"
    elif passes == 2:
        decision = "REPLICATION_CONFIRMED"
    elif passes == 1:
        decision = "PARTIAL_REPLICATION"
    else:
        decision = "REPLICATION_REJECTED"
    report = {
        "experiment_id": protocol["experiment"]["experiment_id"],
        "source_strategy": protocol["experiment"]["source_strategy"],
        "decision": decision,
        "effect": protocol["decision"]["effect"],
        "strategy_changed": False,
        "venues": venues,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (pd.concat(all_summaries, ignore_index=True) if all_summaries else pd.DataFrame()).to_csv(SUMMARY_PATH, index=False)
    (pd.concat(all_periods, ignore_index=True) if all_periods else pd.DataFrame()).to_csv(PERIODS_PATH, index=False)
    RESULT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--venue", action="append", choices=["bybit", "okx"])
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.download or args.refresh:
        manifest = acquire(protocol, venues=args.venue, refresh=args.refresh)
        print(f"files={len(manifest['files'])} errors={len(manifest['errors'])}")
    report = run(protocol)
    print(json.dumps({"decision": report["decision"], "venues": {
        venue: {key: value[key] for key in value if key in {"status", "eligible_symbols", "reasons", "full_base_profit_factor", "full_stress_profit_factor", "full_drawdown", "full_samples"}}
        for venue, value in report["venues"].items()
    }}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
