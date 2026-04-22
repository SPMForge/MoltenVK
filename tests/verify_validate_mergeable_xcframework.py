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

    def add_mobile_framework_interface(self, framework_path: Path) -> None:
        headers_dir = framework_path / "Headers"
        modules_dir = framework_path / "Modules"
        headers_dir.mkdir()
        modules_dir.mkdir()
        (headers_dir / "mvk_vulkan.h").write_text("#pragma once\n", encoding="utf-8")
        (modules_dir / "module.modulemap").write_text(
            'framework module MoltenVK { header "mvk_vulkan.h" export * }\n',
            encoding="utf-8",
        )

    def add_macos_framework_interface(self, framework_path: Path) -> None:
        headers_dir = framework_path / "Versions" / "A" / "Headers"
        modules_dir = framework_path / "Versions" / "A" / "Modules"
        headers_dir.mkdir()
        modules_dir.mkdir()
        (headers_dir / "mvk_vulkan.h").write_text("#pragma once\n", encoding="utf-8")
        (modules_dir / "module.modulemap").write_text(
            'framework module MoltenVK { header "mvk_vulkan.h" export * }\n',
            encoding="utf-8",
        )
        (framework_path / "Headers").symlink_to("Versions/Current/Headers", target_is_directory=True)
        (framework_path / "Modules").symlink_to("Versions/Current/Modules", target_is_directory=True)

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
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["tvos"], "TVOS")
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["tvos-simulator"], "TVOSSIMULATOR")
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["xros"], "VISIONOS")
        self.assertEqual(validator.EXPECTED_VTOOL_PLATFORMS["xros-simulator"], "VISIONOSSIMULATOR")

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

    def test_mobile_framework_interface_accepts_headers_and_modulemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            self.add_mobile_framework_interface(framework_path)
            issues = validator.framework_interface_issues("ios", framework_path)
        self.assertEqual(issues, [])

    def test_mobile_framework_interface_rejects_missing_headers_and_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            issues = validator.framework_interface_issues("ios", framework_path)
        self.assertTrue(any("missing framework headers directory" in issue for issue in issues))
        self.assertTrue(any("missing framework module map" in issue for issue in issues))

    def test_macos_framework_interface_requires_versioned_headers_and_modulemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path, _ = self.make_versioned_framework(Path(tmp_dir))
            self.add_macos_framework_interface(framework_path)
            issues = validator.framework_interface_issues("macos", framework_path)
        self.assertEqual(issues, [])

    def test_macos_framework_interface_rejects_missing_versioned_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path, _ = self.make_versioned_framework(Path(tmp_dir))
            issues = validator.framework_interface_issues("macos", framework_path)
        self.assertTrue(any("missing versioned framework headers directory" in issue for issue in issues))
        self.assertTrue(any("missing versioned framework module map" in issue for issue in issues))

    def test_mobile_framework_interface_rejects_quoted_same_framework_include(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            self.add_mobile_framework_interface(framework_path)
            headers_dir = framework_path / "Headers"
            (headers_dir / "mvk_datatypes.h").write_text('#include "mvk_vulkan.h"\n', encoding="utf-8")

            issues = validator.framework_interface_issues("ios", framework_path)

        self.assertTrue(any("non-modular framework include" in issue for issue in issues))
        self.assertTrue(any('"mvk_vulkan.h" instead of <MoltenVK/mvk_vulkan.h>' in issue for issue in issues))

    def test_mobile_framework_interface_rejects_non_framework_angle_include(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            self.add_mobile_framework_interface(framework_path)
            vulkan_dir = framework_path / "Headers" / "vulkan"
            vulkan_dir.mkdir()
            (vulkan_dir / "vulkan.h").write_text('#include <vulkan/vk_platform.h>\n', encoding="utf-8")
            (vulkan_dir / "vk_platform.h").write_text("#pragma once\n", encoding="utf-8")

            issues = validator.framework_interface_issues("ios", framework_path)

        self.assertTrue(any("non-modular framework include" in issue for issue in issues))
        self.assertTrue(any("<vulkan/vk_platform.h> instead of <MoltenVK/vulkan/vk_platform.h>" in issue for issue in issues))

    def test_framework_header_include_issues_accept_framework_style_includes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            self.add_mobile_framework_interface(framework_path)
            headers_dir = framework_path / "Headers"
            (headers_dir / "mvk_datatypes.h").write_text('#include <MoltenVK/mvk_vulkan.h>\n', encoding="utf-8")
            vulkan_dir = headers_dir / "vulkan"
            vulkan_dir.mkdir()
            (vulkan_dir / "vulkan.h").write_text('#include <MoltenVK/vulkan/vk_platform.h>\n', encoding="utf-8")
            (vulkan_dir / "vk_platform.h").write_text("#pragma once\n", encoding="utf-8")

            issues = validator.framework_header_include_issues("ios", framework_path, headers_dir)

        self.assertEqual(issues, [])

    def test_mobile_framework_interface_rejects_quoted_local_header_even_if_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            framework_path = Path(tmp_dir) / "MoltenVK.framework"
            framework_path.mkdir()
            self.add_mobile_framework_interface(framework_path)
            vulkan_dir = framework_path / "Headers" / "vulkan"
            vulkan_dir.mkdir()
            (vulkan_dir / "vulkan.h").write_text('#include "vulkan_sci.h"\n', encoding="utf-8")

            issues = validator.framework_interface_issues("ios", framework_path)

        self.assertTrue(any("non-modular framework include" in issue for issue in issues))
        self.assertTrue(any('"vulkan_sci.h" instead of <MoltenVK/vulkan/vulkan_sci.h>' in issue for issue in issues))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidateMergeableXCFrameworkTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
