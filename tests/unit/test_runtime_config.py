import unittest

from execution.config import RuntimeConfig


class RuntimeConfigTests(unittest.TestCase):
    def test_defaults_fail_closed_to_paper(self):
        config = RuntimeConfig.from_mapping({})
        self.assertEqual(config.mode, "paper")
        self.assertFalse(config.real_trading_enabled)

    def test_live_mode_is_not_supported(self):
        with self.assertRaisesRegex(ValueError, "live is not supported"):
            RuntimeConfig.from_mapping({"BOT_MODE": "live"})

    def test_environment_cannot_enable_real_trading(self):
        with self.assertRaisesRegex(ValueError, "cannot be enabled"):
            RuntimeConfig.from_mapping({"REAL_TRADING_ENABLED": "true"})

    def test_testnet_requires_dedicated_credentials(self):
        with self.assertRaisesRegex(ValueError, "testnet credentials"):
            RuntimeConfig.from_mapping({"BOT_MODE": "testnet"})
