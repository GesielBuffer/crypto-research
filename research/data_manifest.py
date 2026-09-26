"""Build and verify deterministic manifests for local historical datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from research.config import BASE_DIR


SCHEMA_VERSION = 1
DEFAULT_SOURCE = {
    "provider": "Binance",
    "market": "USD-M Futures",
    "endpoint": "https://fapi.binance.com/fapi/v1/klines",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"dataset file is outside repository: {path}") from exc


def describe_candle_file(path: Path, root: Path = BASE_DIR) -> dict:
    """Return content identity and temporal coverage for one market-data CSV."""

    if not path.exists():
        raise FileNotFoundError(f"missing dataset file: {path}")
    columns = pd.read_csv(path, nrows=0).columns
    time_column = next(
        (name for name in ("open_time", "fundingTime") if name in columns),
        None,
    )
    if time_column is None:
        raise ValueError(f"dataset has no supported time column: {path}")
    times = pd.read_csv(path, usecols=[time_column])[time_column]
    parsed = pd.to_datetime(times, utc=True, errors="raise", format="mixed")
    return {
        "path": _relative_path(path, root),
        "bytes": path.stat().st_size,
        "rows": len(parsed),
        "time_column": time_column,
        "first_open_time": parsed.min().isoformat() if len(parsed) else None,
        "last_open_time": parsed.max().isoformat() if len(parsed) else None,
        "sha256": file_sha256(path),
    }


def build_manifest(
    paths: Iterable[Path],
    *,
    dataset_id: str,
    root: Path = BASE_DIR,
    source: dict | None = None,
) -> dict:
    """Build a deterministic manifest; timestamps of generation are omitted."""

    unique = sorted({path.resolve() for path in paths}, key=lambda path: path.as_posix())
    if not unique:
        raise ValueError("at least one dataset file is required")
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "source": source or DEFAULT_SOURCE,
        "files": [describe_candle_file(path, root) for path in unique],
    }


def write_manifest(manifest: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_manifest(
    manifest_path: Path,
    expected_paths: Iterable[Path],
    *,
    root: Path = BASE_DIR,
) -> list[dict]:
    """Verify that expected local files match their committed identities."""

    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported data manifest schema: {manifest_path}")
    entries = document.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"data manifest has no files: {manifest_path}")

    indexed: dict[str, dict] = {}
    for entry in entries:
        relative = Path(entry.get("path", ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe path in data manifest: {relative}")
        key = relative.as_posix()
        if not key or key in indexed:
            raise ValueError(f"duplicate or empty path in data manifest: {key}")
        indexed[key] = entry

    required = [_relative_path(path, root) for path in expected_paths]
    missing = sorted(set(required).difference(indexed))
    if missing:
        raise ValueError(f"files absent from data manifest: {missing}")

    verified = []
    for relative in required:
        entry = indexed[relative]
        path = root / relative
        if not path.exists():
            raise FileNotFoundError(f"missing dataset file: {path}")
        if path.stat().st_size != entry.get("bytes"):
            raise ValueError(f"dataset size mismatch: {relative}")
        if file_sha256(path) != entry.get("sha256"):
            raise ValueError(f"dataset checksum mismatch: {relative}")
        verified.append(entry)
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", action="append", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # Imported lazily to keep manifest verification independent from the runner.
    from research.run_research import load_registry, used_cache_files

    registry = load_registry()
    paths: set[Path] = set()
    for experiment_id in args.experiment:
        if experiment_id not in registry:
            raise ValueError(f"unknown experiment '{experiment_id}'")
        spec = registry[experiment_id]
        frozen = pd.read_csv(BASE_DIR / spec["trades_file"], usecols=["symbol"])
        paths.update(used_cache_files(frozen["symbol"].unique().tolist(), spec))

    output = args.output if args.output.is_absolute() else BASE_DIR / args.output
    manifest = build_manifest(paths, dataset_id=args.dataset_id)
    write_manifest(manifest, output)
    print(f"wrote {len(manifest['files'])} files to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
