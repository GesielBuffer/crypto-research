"""Observe the frozen funding strategy with public data and no order capability."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import truststore

from execution.readiness import live_blockers, load_readiness
from research.config import BASE_DIR
from research.experiments.cross_sectional_funding_carry_v2 import hysteresis_membership


PROTOCOL_PATH = BASE_DIR / "experiments" / "cross_venue_funding_holdout_v4.toml"
READINESS_PATH = BASE_DIR / "deployment" / "readiness.toml"
DEFAULT_STATE_PATH = BASE_DIR / "runtime" / "funding_shadow_state.json"
FUNDING_ENDPOINT = "https://fapi.binance.com/fapi/v1/fundingRate"

truststore.inject_into_ssl()


def _protocol() -> dict:
    import tomllib

    with PROTOCOL_PATH.open("rb") as handle:
        return tomllib.load(handle)


def fetch_public_funding(session: requests.Session, base: str, *, limit: int = 30) -> pd.DataFrame:
    response = session.get(
        FUNDING_ENDPOINT,
        params={"symbol": f"{base}USDT", "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    frame = pd.DataFrame(response.json())
    if frame.empty:
        raise RuntimeError(f"no public funding returned for {base}")
    frame["fundingTime"] = pd.to_datetime(pd.to_numeric(frame["fundingTime"]), unit="ms", utc=True)
    frame["fundingRate"] = pd.to_numeric(frame["fundingRate"], errors="raise")
    return frame[["fundingTime", "fundingRate"]].drop_duplicates("fundingTime").sort_values("fundingTime")


def funding_matrix(frames: dict[str, pd.DataFrame], records: int) -> pd.DataFrame:
    series = []
    for symbol, frame in frames.items():
        values = frame.set_index("fundingTime")["fundingRate"].rolling(records, min_periods=records).mean()
        series.append(values.rename(symbol))
    return pd.concat(series, axis=1, join="inner").dropna().sort_index()


def advance_state(matrix: pd.DataFrame, previous: dict, protocol: dict) -> tuple[dict, bool]:
    strategy = protocol["strategy"]
    step = int(strategy["rebalance_funding_periods"])
    last_text = previous.get("last_rebalance_time")
    previous_longs = set(previous.get("longs", []))
    previous_shorts = set(previous.get("shorts", []))
    if matrix.empty:
        raise ValueError("no common settled funding observations")
    if last_text:
        last = pd.Timestamp(last_text)
        if last.tzinfo is None:
            last = last.tz_localize("UTC")
        pending = matrix[matrix.index > last]
        rebalance_rows = [pending.iloc[index] for index in range(step - 1, len(pending), step)]
    else:
        rebalance_rows = [matrix.iloc[-1]]
    changed = bool(rebalance_rows)
    last_time = pd.Timestamp(last_text) if last_text else None
    for ranking in rebalance_rows:
        previous_longs, previous_shorts = hysteresis_membership(
            ranking,
            previous_longs,
            previous_shorts,
            entry_fraction=float(strategy["entry_fraction"]),
            exit_boundary=float(strategy["exit_boundary"]),
        )
        last_time = ranking.name
    state = {
        "strategy_version": protocol["experiment"]["strategy_version"],
        "last_rebalance_time": last_time.isoformat() if last_time is not None else None,
        "latest_common_funding_time": matrix.index[-1].isoformat(),
        "longs": sorted(previous_longs),
        "shorts": sorted(previous_shorts),
    }
    return state, changed


def _weights(state: dict) -> dict[str, float]:
    longs, shorts = state["longs"], state["shorts"]
    result = {symbol: 0.5 / len(longs) for symbol in longs}
    result.update({symbol: -0.5 / len(shorts) for symbol in shorts})
    return dict(sorted(result.items()))


def observe(*, state_path: Path = DEFAULT_STATE_PATH, save: bool = True) -> dict:
    readiness = load_readiness(READINESS_PATH)
    if readiness["deployment"].get("real_trading_enabled") is not False:
        raise RuntimeError("shadow observer refuses a readiness file that enables real trading")
    protocol = _protocol()
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    session = requests.Session()
    frames = {
        base: fetch_public_funding(session, base)
        for base in protocol["data"]["candidate_symbols"]
    }
    matrix = funding_matrix(frames, int(protocol["strategy"]["trailing_funding_records"]))
    state, changed = advance_state(matrix, previous, protocol)
    state["observed_at"] = datetime.now(timezone.utc).isoformat()
    state["weights"] = _weights(state)
    canonical = json.dumps(state["weights"], sort_keys=True, separators=(",", ":"))
    state["signal_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    state["rebalance_changed"] = changed
    state["execution"] = "DISABLED_BY_DESIGN"
    state["live_blockers"] = live_blockers(readiness)
    if save:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    print(json.dumps(observe(state_path=args.state, save=not args.no_save), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
