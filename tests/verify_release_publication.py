#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / "Scripts" / "SwiftPackage" / "release_publication.py"

spec = importlib.util.spec_from_file_location("release_publication", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ReleasePublicationTests(unittest.TestCase):
    def stub_release(
        self,
        *,
        tag: str,
        assets: set[str],
        is_prerelease: bool,
        is_draft: bool = False,
    ) -> object:
        return module.GitHubRelease(
            tag_name=tag,
            assets=assets,
            is_prerelease=is_prerelease,
            is_draft=is_draft,
        )

    def test_alpha_create_when_no_existing_tag_or_release(self) -> None:
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: []
            module.list_github_release_tags = lambda repo: []
            module.fetch_github_release = lambda repo, tag: None
            module.fetch_latest_release_tag = lambda repo: None

            plan = module.resolve_release_plan(
                selection_mode="latest",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag

        self.assertEqual(plan.target_version, "1.2.3-alpha.1")
        self.assertEqual(plan.publication_mode, "create")
        self.assertEqual(plan.release_action, "create")
        self.assertFalse(plan.remote_tag_exists)
        self.assertFalse(plan.release_exists)
        self.assertEqual(plan.missing_assets, sorted(module.required_release_assets("1.2.3-alpha.1")))

    def test_alpha_repair_when_release_is_missing_assets(self) -> None:
        version = "1.2.3-alpha.4"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [version]
            module.list_github_release_tags = lambda repo: [version]
            module.fetch_github_release = lambda repo, tag: self.stub_release(
                tag=tag,
                assets={
                    f"MoltenVK-{version}.xcframework.zip",
                    f"MoltenVK-{version}.xcframework.checksum",
                },
                is_prerelease=True,
            )
            module.fetch_latest_release_tag = lambda repo: None

            plan = module.resolve_release_plan(
                selection_mode="requested",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag

        self.assertEqual(plan.target_version, version)
        self.assertEqual(plan.publication_mode, "repair")
        self.assertEqual(plan.release_action, "edit")
        self.assertTrue(plan.remote_tag_exists)
        self.assertTrue(plan.release_exists)
        self.assertEqual(
            plan.missing_assets,
            [
                f"MoltenVK-static-{version}.xcframework.checksum",
                f"MoltenVK-static-{version}.xcframework.zip",
                f"MoltenVKHeaders-{version}.checksum",
                f"MoltenVKHeaders-{version}.zip",
            ],
        )

    def test_alpha_skip_when_latest_release_is_complete(self) -> None:
        version = "1.2.3-alpha.4"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [version]
            module.list_github_release_tags = lambda repo: [version]
            module.fetch_github_release = lambda repo, tag: self.stub_release(
                tag=tag,
                assets=module.required_release_assets(tag),
                is_prerelease=True,
            )
            module.fetch_latest_release_tag = lambda repo: None

            plan = module.resolve_release_plan(
                selection_mode="latest",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag

        self.assertEqual(plan.target_version, version)
        self.assertEqual(plan.publication_mode, "skip")
        self.assertEqual(plan.release_action, "skip")
        self.assertEqual(plan.missing_assets, [])

    def test_alpha_fails_loudly_when_matching_stable_release_is_broken(self) -> None:
        version = "1.2.3"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [version]
            module.list_github_release_tags = lambda repo: [version]
            module.fetch_github_release = lambda repo, tag: self.stub_release(
                tag=tag,
                assets={
                    f"MoltenVK-{version}.xcframework.zip",
                    f"MoltenVK-{version}.xcframework.checksum",
                },
                is_prerelease=False,
            )
            module.fetch_latest_release_tag = lambda repo: None

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    module.resolve_release_plan(
                        selection_mode="latest",
                        release_channel="alpha",
                        upstream_ref="v1.2.3",
                        repo="SPMForge/MoltenVK",
                    )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag

        self.assertIn(
            "repair it through the stable release path before publishing alpha",
            stderr.getvalue(),
        )

    def test_alpha_resolution_fails_loudly_when_github_queries_fail(self) -> None:
        original_release_tags = module.list_github_release_tags
        try:
            def raising_release_tags(repo: str) -> list[str]:
                raise SystemExit(1)

            module.list_github_release_tags = raising_release_tags
            with self.assertRaises(SystemExit):
                module.resolve_release_plan(
                    selection_mode="latest",
                    release_channel="alpha",
                    upstream_ref="v1.2.3",
                    repo="SPMForge/MoltenVK",
                )
        finally:
            module.list_github_release_tags = original_release_tags

    def test_assert_tagged_state_fails_when_generated_metadata_drifts(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="moltenvk-release-state-"))
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        version = "1.2.3-alpha.4"
        for relative_path in module.metadata_paths_for_version(version):
            workspace_path = temp_root / relative_path
            workspace_path.parent.mkdir(parents=True, exist_ok=True)
            workspace_path.write_text("workspace\n", encoding="utf-8")

        original_read_tagged_text = module.read_tagged_text
        try:
            module.read_tagged_text = lambda tag, relative_path: "tagged\n"
            with self.assertRaises(SystemExit):
                module.assert_tagged_state_matches_workspace(version, temp_root)
        finally:
            module.read_tagged_text = original_read_tagged_text


if __name__ == "__main__":
    unittest.main(verbosity=2)
