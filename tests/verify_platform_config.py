#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def load_platform_config_module():
    script_path = Path(__file__).resolve().parents[1] / "Scripts/SwiftPackage/platform_config.py"
    spec = importlib.util.spec_from_file_location("platform_config", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load platform_config module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


platform_config = load_platform_config_module()


class PlatformConfigTests(unittest.TestCase):
    def test_platform_config_contains_expected_platforms(self) -> None:
        config = platform_config.load_platform_config()
        self.assertEqual(
            [entry["id"] for entry in config["build_matrix"]],
            ["macos", "ios", "ios-simulator", "tvos", "tvos-simulator", "xros", "xros-simulator"],
        )

    def test_manifest_platform_entries_follow_deployment_targets(self) -> None:
        config = platform_config.load_platform_config()
        self.assertEqual(
            platform_config.manifest_platform_entries(config),
            [("iOS", "14.0"), ("macOS", "11.0"), ("tvOS", "14.0"), ("visionOS", "1.0")],
        )

    def test_expected_vtool_platforms_follow_platform_config(self) -> None:
        config = platform_config.load_platform_config()
        self.assertEqual(
            platform_config.expected_vtool_platforms(config),
            {
                "macos": "MACOS",
                "ios": "IOS",
                "ios-simulator": "IOSSIMULATOR",
                "tvos": "TVOS",
                "tvos-simulator": "TVOSSIMULATOR",
                "xros": "VISIONOS",
                "xros-simulator": "VISIONOSSIMULATOR",
            },
        )

    def test_deployment_target_build_settings_follow_platform_config(self) -> None:
        config = platform_config.load_platform_config()
        self.assertEqual(
            platform_config.deployment_target_build_settings(config),
            [
                ("IPHONEOS_DEPLOYMENT_TARGET", "14.0"),
                ("MACOSX_DEPLOYMENT_TARGET", "11.0"),
                ("TVOS_DEPLOYMENT_TARGET", "14.0"),
                ("XROS_DEPLOYMENT_TARGET", "1.0"),
            ],
        )

    def test_platform_config_rejects_major_only_deployment_targets(self) -> None:
        invalid_config = """\
{
  "deployment_targets": {
    "ios": {
      "swiftpm_platform": "iOS",
      "version": "14",
      "xcodebuild_setting": "IPHONEOS_DEPLOYMENT_TARGET"
    }
  },
  "build_matrix": [
    {
      "id": "ios",
      "family": "ios",
      "build_flag": "--ios",
      "destination": "generic/platform=iOS",
      "sdk": "iphoneos",
      "validator_key": "ios",
      "vtool_platform": "IOS",
      "consumer_test": true
    }
  ]
}
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "platforms.json"
            config_path.write_text(invalid_config, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "major.minor"):
                platform_config.load_platform_config(config_path)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PlatformConfigTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
