"""Operational readiness entry point. It never connects to an exchange."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from execution.readiness import live_blockers, load_readiness
from research.config import BASE_DIR


DEFAULT_READINESS = BASE_DIR / "deployment" / "readiness.toml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    args = parser.parse_args()
    document = load_readiness(args.readiness)
    blockers = live_blockers(document)
    print(json.dumps({
        "service": "crypto-research-execution",
        "configured_mode": document["deployment"]["mode"],
        "live_ready": not blockers,
        "blockers": blockers,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
