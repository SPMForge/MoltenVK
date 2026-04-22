#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
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
            [("iOS", "14"), ("macOS", "11"), ("tvOS", "14"), ("visionOS", "1")],
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


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PlatformConfigTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
