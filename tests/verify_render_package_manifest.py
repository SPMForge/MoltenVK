#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def load_module(script_name: str, module_name: str):
    script_path = Path(__file__).resolve().parents[1] / "Scripts/SwiftPackage" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_name} module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest_renderer = load_module("render_package_manifest.py", "render_package_manifest")
local_manifest_renderer = load_module("render_local_dev_package_manifest.py", "render_local_dev_package_manifest")


class RenderPackageManifestTests(unittest.TestCase):
    def test_validate_deployment_target_accepts_dotted_version(self) -> None:
        self.assertEqual(manifest_renderer.validate_deployment_target("14.0", "iOS"), "14.0")

    def test_validate_deployment_target_rejects_major_only_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "major.minor"):
            manifest_renderer.validate_deployment_target("14", "iOS")

    def test_render_manifest_uses_string_platform_deployment_targets(self) -> None:
        manifest = manifest_renderer.render_manifest(
            "1.0.0",
            "SPMForge/MoltenVK",
            "0" * 64,
            [("iOS", "14.0"), ("macOS", "11.0"), ("tvOS", "14.0"), ("visionOS", "1.0")],
        )

        self.assertIn('.iOS("14.0")', manifest)
        self.assertIn('.macOS("11.0")', manifest)
        self.assertIn('.tvOS("14.0")', manifest)
        self.assertIn('.visionOS("1.0")', manifest)
        self.assertNotIn(".tvOS(.v14)", manifest)

    def test_render_local_dev_manifest_uses_string_platform_deployment_targets(self) -> None:
        manifest = local_manifest_renderer.render_manifest(
            "Artifacts/MoltenVK.xcframework",
            [("iOS", "14.0"), ("macOS", "11.0"), ("tvOS", "14.0"), ("visionOS", "1.0")],
        )

        self.assertIn('.iOS("14.0")', manifest)
        self.assertIn('.visionOS("1.0")', manifest)
        self.assertNotIn(".visionOS(.v1)", manifest)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RenderPackageManifestTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
