#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
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
    def make_versioned_framework(self, root: Path, flattened: bool = False) -> tuple[Path, Path]:
        framework_path = root / "MoltenVK.framework"
        framework_path.mkdir()

        if flattened:
            binary_path = framework_path / "MoltenVK"
            binary_path.write_bytes(b"binary")
            resources_dir = framework_path / "Resources"
            resources_dir.mkdir()
            (resources_dir / "Info.plist").write_text("plist", encoding="utf-8")
            return framework_path, binary_path

        versioned_resources = framework_path / "Versions" / "A" / "Resources"
        versioned_resources.mkdir(parents=True)
        binary_path = framework_path / "Versions" / "A" / "MoltenVK"
        binary_path.write_bytes(b"binary")
        (versioned_resources / "Info.plist").write_text("plist", encoding="utf-8")
        (framework_path / "Versions" / "Current").symlink_to("A")
        (framework_path / "MoltenVK").symlink_to("Versions/Current/MoltenVK")
        (framework_path / "Resources").symlink_to("Versions/Current/Resources", target_is_directory=True)
        return framework_path, binary_path

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

    def test_macos_framework_layout_accepts_versioned_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path, binary_path = self.make_versioned_framework(Path(tmp_dir))
            issues = validator.macos_framework_layout_issues(framework_path, binary_path)
        self.assertEqual(issues, [])

    def test_macos_framework_layout_rejects_flat_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path, binary_path = self.make_versioned_framework(Path(tmp_dir), flattened=True)
            issues = validator.macos_framework_layout_issues(framework_path, binary_path)
        self.assertIn("macos: missing versioned framework directory", issues[0])
        self.assertTrue(any("top-level framework binary is not a symlink" in issue for issue in issues))
        self.assertTrue(any("top-level Resources is not a symlink" in issue for issue in issues))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidateMergeableXCFrameworkTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
