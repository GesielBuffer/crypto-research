import json
import tempfile
import unittest
from pathlib import Path

from research.data_manifest import build_manifest, verify_manifest, write_manifest


class DataManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.candles = self.data / "BTCUSDT_5m_sample.csv"
        self.candles.write_text(
            "open_time,open,close\n"
            "2026-01-01T00:00:00Z,100,101\n"
            "2026-01-01T00:05:00Z,101,102\n",
            encoding="utf-8",
        )
        self.manifest_path = self.root / "manifests" / "sample.json"

    def test_build_and_verify_manifest(self):
        manifest = build_manifest(
            [self.candles], dataset_id="sample", root=self.root
        )
        write_manifest(manifest, self.manifest_path)
        entries = verify_manifest(
            self.manifest_path, [self.candles], root=self.root
        )
        self.assertEqual(entries[0]["rows"], 2)
        self.assertEqual(entries[0]["path"], "data/BTCUSDT_5m_sample.csv")

    def test_tampered_file_is_rejected(self):
        manifest = build_manifest(
            [self.candles], dataset_id="sample", root=self.root
        )
        write_manifest(manifest, self.manifest_path)
        self.candles.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_manifest(self.manifest_path, [self.candles], root=self.root)

    def test_missing_manifest_entry_is_rejected(self):
        self.manifest_path.parent.mkdir()
        self.manifest_path.write_text(
            json.dumps({"schema_version": 1, "files": [{
                "path": "data/other.csv", "bytes": 0, "sha256": "x"
            }]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "absent from data manifest"):
            verify_manifest(self.manifest_path, [self.candles], root=self.root)

    def test_funding_time_is_supported(self):
        funding = self.data / "BTCUSDT_funding_sample.csv"
        funding.write_text(
            "symbol,fundingTime,fundingRate\n"
            "BTCUSDT,2026-01-01T00:00:00Z,0.0001\n",
            encoding="utf-8",
        )
        manifest = build_manifest([funding], dataset_id="funding", root=self.root)
        self.assertEqual(manifest["files"][0]["time_column"], "fundingTime")
        self.assertEqual(manifest["files"][0]["rows"], 1)
