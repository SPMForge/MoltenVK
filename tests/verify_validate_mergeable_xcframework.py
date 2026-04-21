#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def load_validator_module():
    script_path = Path(__file__).resolve().parents[1] / "Scripts/SwiftPackage/validate_mergeable_xcframework.py"
    spec = importlib.util.spec_from_file_location("validate_mergeable_xcframework", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load validator module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_validator_module()


class ValidateMergeableXCFrameworkTests(unittest.TestCase):
    def test_platform_key_includes_variant(self) -> None:
        self.assertEqual(
            validator.platform_key(
                {
                    "SupportedPlatform": "ios",
                    "SupportedPlatformVariant": "simulator",
                }
            ),
            "ios-simulator",
        )

    def test_expected_vtool_mapping_covers_current_platforms(self) -> None:
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["macos"], "MACOS")
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["ios"], "IOS")
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["ios-simulator"], "IOSSIMULATOR")

    def test_entry_issues_fails_when_vtool_platform_mismatches(self) -> None:
        issues = validator.entry_issues(
            {
                "platform": "ios-simulator",
                "mergeable_metadata": True,
                "binary_exists": True,
                "expected_vtool_platform": "IOSSIMULATOR",
                "vtool_platforms": ["IOS"],
            }
        )
        self.assertEqual(
            issues,
            ["ios-simulator: expected vtool platform IOSSIMULATOR, got IOS"],
        )

    def test_entry_issues_accepts_matching_vtool_platform(self) -> None:
        issues = validator.entry_issues(
            {
                "platform": "macos",
                "mergeable_metadata": True,
                "binary_exists": True,
                "expected_vtool_platform": "MACOS",
                "vtool_platforms": ["MACOS"],
            }
        )
        self.assertEqual(issues, [])

    def test_entry_issues_fails_without_vtool_output(self) -> None:
        issues = validator.entry_issues(
            {
                "platform": "ios",
                "mergeable_metadata": True,
                "binary_exists": True,
                "expected_vtool_platform": "IOS",
            }
        )
        self.assertEqual(issues, ["ios: missing vtool platform output"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidateMergeableXCFrameworkTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
