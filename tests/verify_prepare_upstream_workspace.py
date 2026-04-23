#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def load_prepare_workspace_module():
    script_path = Path(__file__).resolve().parents[1] / "Scripts/SwiftPackage/prepare_upstream_workspace.py"
    spec = importlib.util.spec_from_file_location("prepare_upstream_workspace", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load prepare_upstream_workspace module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_workspace = load_prepare_workspace_module()


class PrepareUpstreamWorkspaceTests(unittest.TestCase):
    def test_patch_revision_script_installs_explicit_commit_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "Scripts" / "gen_moltenvk_rev_hdr.sh"
            script_path.parent.mkdir(parents=True)
            script_path.write_text("#!/bin/bash\n", encoding="utf-8")

            prepare_workspace.patch_revision_script(script_path)

            rewritten = script_path.read_text(encoding="utf-8")
            self.assertIn("UpstreamCommit.txt", rewritten)
            self.assertIn("MVK_UPSTREAM_COMMIT", rewritten)
            self.assertIn("unable to determine MoltenVK revision", rewritten)

    def test_write_upstream_commit_file_rejects_invalid_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "40-character"):
                prepare_workspace.write_upstream_commit_file(Path(tmp_dir), "not-a-commit")

    def test_patch_pbxproj_deployment_targets_rewrites_tvos_and_xros(self) -> None:
        sample = """\
                TVOS_DEPLOYMENT_TARGET = 14.5;
                TVOS_DEPLOYMENT_TARGET = 14.5;
                SDKROOT = xros;
                SDKROOT = xros;
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pbxproj_path = Path(tmp_dir) / "project.pbxproj"
            pbxproj_path.write_text(sample, encoding="utf-8")

            prepare_workspace.patch_pbxproj_deployment_targets(
                pbxproj_path,
                tvos_deployment_target="14.0",
                xros_deployment_target="1.0",
                expected_tvos_replacements=2,
                expected_xros_blocks=2,
            )

            patched = pbxproj_path.read_text(encoding="utf-8")
            self.assertEqual(patched.count("TVOS_DEPLOYMENT_TARGET = 14.0;"), 2)
            self.assertEqual(patched.count("XROS_DEPLOYMENT_TARGET = 1.0;"), 2)
            self.assertNotIn("TVOS_DEPLOYMENT_TARGET = 14.5;", patched)

    def test_patch_pbxproj_deployment_targets_fails_on_upstream_shape_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pbxproj_path = Path(tmp_dir) / "project.pbxproj"
            pbxproj_path.write_text("TVOS_DEPLOYMENT_TARGET = 14.5;\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Expected 2 TVOS_DEPLOYMENT_TARGET replacements"):
                prepare_workspace.patch_pbxproj_deployment_targets(
                    pbxproj_path,
                    tvos_deployment_target="14.0",
                    xros_deployment_target="1.0",
                    expected_tvos_replacements=2,
                    expected_xros_blocks=0,
                )


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PrepareUpstreamWorkspaceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
