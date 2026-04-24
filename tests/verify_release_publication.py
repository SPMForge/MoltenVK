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

    def test_alpha_tag_exists_release_missing_creates_release_without_new_tag(self) -> None:
        version = "1.2.3-alpha.4"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [version]
            module.list_github_release_tags = lambda repo: []
            module.fetch_github_release = lambda repo, tag: None
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
        self.assertEqual(plan.release_action, "create")
        self.assertTrue(plan.remote_tag_exists)
        self.assertFalse(plan.release_exists)
        self.assertEqual(plan.missing_assets, sorted(module.required_release_assets(version)))

    def test_alpha_latest_release_requires_rendered_manifest_when_highest_alpha_is_complete(self) -> None:
        existing_version = "1.2.3-alpha.4"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [existing_version]
            module.list_github_release_tags = lambda repo: [existing_version]
            module.fetch_github_release = lambda repo, tag: (
                self.stub_release(
                    tag=tag,
                    assets=module.required_release_assets(tag),
                    is_prerelease=True,
                )
                if tag == existing_version
                else None
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

        self.assertEqual(plan.target_version, existing_version)
        self.assertEqual(plan.build_version, existing_version)
        self.assertEqual(plan.latest_alpha_version, existing_version)
        self.assertEqual(plan.next_alpha_version, "1.2.3-alpha.5")
        self.assertEqual(plan.publication_mode, "evaluate")
        self.assertEqual(plan.release_action, "skip")
        self.assertTrue(plan.remote_tag_exists)
        self.assertTrue(plan.release_exists)
        self.assertEqual(plan.missing_assets, [])

    def test_alpha_requested_release_requires_rendered_contract_when_highest_alpha_is_complete(self) -> None:
        existing_version = "1.2.3-alpha.4"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        try:
            module.list_remote_tag_names = lambda: [existing_version]
            module.list_github_release_tags = lambda repo: [existing_version]
            module.fetch_github_release = lambda repo, tag: (
                self.stub_release(
                    tag=tag,
                    assets=module.required_release_assets(tag),
                    is_prerelease=True,
                )
                if tag == existing_version
                else None
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

        self.assertEqual(plan.target_version, existing_version)
        self.assertEqual(plan.build_version, existing_version)
        self.assertEqual(plan.publication_mode, "evaluate")
        self.assertEqual(plan.next_alpha_version, "1.2.3-alpha.5")

    def test_alpha_latest_release_reuses_highest_alpha_when_rendered_manifest_matches(self) -> None:
        existing_version = "1.2.3-alpha.4"
        rendered_manifest = "// rendered Package.swift\n"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        original_read_tagged_text = module.read_optional_tagged_text
        try:
            module.list_remote_tag_names = lambda: [existing_version]
            module.list_github_release_tags = lambda repo: [existing_version]
            module.fetch_github_release = lambda repo, tag: self.stub_release(
                tag=tag,
                assets=module.required_release_assets(tag),
                is_prerelease=True,
            )
            module.fetch_latest_release_tag = lambda repo: None
            module.read_optional_tagged_text = lambda tag, relative_path: rendered_manifest

            plan = module.resolve_release_plan(
                selection_mode="latest",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
                rendered_package_swift=rendered_manifest,
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag
            module.read_optional_tagged_text = original_read_tagged_text

        self.assertEqual(plan.target_version, existing_version)
        self.assertEqual(plan.publication_mode, "skip")
        self.assertEqual(plan.release_action, "skip")
        self.assertEqual(plan.build_version, existing_version)

    def test_alpha_latest_release_mints_next_version_when_rendered_manifest_changes(self) -> None:
        existing_version = "1.2.3-alpha.4"
        next_version = "1.2.3-alpha.5"
        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        original_read_tagged_text = module.read_optional_tagged_text
        try:
            module.list_remote_tag_names = lambda: [existing_version]
            module.list_github_release_tags = lambda repo: [existing_version]
            module.fetch_github_release = lambda repo, tag: (
                self.stub_release(
                    tag=tag,
                    assets=module.required_release_assets(tag),
                    is_prerelease=True,
                )
                if tag == existing_version
                else None
            )
            module.fetch_latest_release_tag = lambda repo: None
            module.read_optional_tagged_text = lambda tag, relative_path: "// old Package.swift\n"

            plan = module.resolve_release_plan(
                selection_mode="latest",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
                rendered_package_swift="// new Package.swift\n",
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag
            module.read_optional_tagged_text = original_read_tagged_text

        self.assertEqual(plan.target_version, next_version)
        self.assertEqual(plan.build_version, existing_version)
        self.assertEqual(plan.publication_mode, "create")
        self.assertEqual(plan.release_action, "create")
        self.assertFalse(plan.remote_tag_exists)
        self.assertFalse(plan.release_exists)
        self.assertEqual(plan.missing_assets, sorted(module.required_release_assets(next_version)))

    def test_alpha_latest_release_mints_next_version_when_generated_metadata_changes(self) -> None:
        existing_version = "1.2.3-alpha.4"
        next_version = "1.2.3-alpha.5"
        temp_root = Path(tempfile.mkdtemp(prefix="moltenvk-rendered-contract-"))
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        tagged_metadata: dict[str, str] = {}
        for relative_path in module.metadata_paths_for_version(existing_version):
            workspace_path = temp_root / relative_path
            workspace_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"{relative_path}\n"
            workspace_path.write_text(content, encoding="utf-8")
            tagged_metadata[relative_path] = content

        static_checksum_path = f"Artifacts/MoltenVK-static-{existing_version}.xcframework.checksum"
        tagged_metadata[static_checksum_path] = "old-static-checksum\n"

        original_remote_tags = module.list_remote_tag_names
        original_release_tags = module.list_github_release_tags
        original_fetch_release = module.fetch_github_release
        original_latest_tag = module.fetch_latest_release_tag
        original_read_tagged_text = module.read_optional_tagged_text
        try:
            module.list_remote_tag_names = lambda: [existing_version]
            module.list_github_release_tags = lambda repo: [existing_version]
            module.fetch_github_release = lambda repo, tag: (
                self.stub_release(
                    tag=tag,
                    assets=module.required_release_assets(tag),
                    is_prerelease=True,
                )
                if tag == existing_version
                else None
            )
            module.fetch_latest_release_tag = lambda repo: None
            module.read_optional_tagged_text = lambda tag, relative_path: tagged_metadata.get(relative_path)

            plan = module.resolve_release_plan(
                selection_mode="latest",
                release_channel="alpha",
                upstream_ref="v1.2.3",
                repo="SPMForge/MoltenVK",
                rendered_workspace_root=temp_root,
            )
        finally:
            module.list_remote_tag_names = original_remote_tags
            module.list_github_release_tags = original_release_tags
            module.fetch_github_release = original_fetch_release
            module.fetch_latest_release_tag = original_latest_tag
            module.read_optional_tagged_text = original_read_tagged_text

        self.assertEqual(plan.target_version, next_version)
        self.assertEqual(plan.build_version, existing_version)
        self.assertEqual(plan.publication_mode, "create")

    def test_alpha_latest_repairs_incomplete_highest_alpha_before_minting_new_one(self) -> None:
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
        self.assertEqual(plan.publication_mode, "repair")
        self.assertEqual(plan.release_action, "edit")
        self.assertTrue(plan.remote_tag_exists)
        self.assertTrue(plan.release_exists)

    def test_alpha_latest_repairs_metadata_drift_before_minting_new_one(self) -> None:
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
            module.fetch_latest_release_tag = lambda repo: version

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
        self.assertEqual(plan.publication_mode, "repair")
        self.assertEqual(plan.release_action, "edit")
        self.assertTrue(plan.metadata_needs_repair)

    def test_stable_skip_when_existing_release_is_complete(self) -> None:
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
                assets=module.required_release_assets(tag),
                is_prerelease=False,
            )
            module.fetch_latest_release_tag = lambda repo: version

            plan = module.resolve_release_plan(
                selection_mode="requested",
                release_channel="stable",
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
        self.assertFalse(plan.metadata_needs_repair)
        self.assertEqual(plan.missing_assets, [])

    def test_stable_repairs_when_existing_release_is_incomplete(self) -> None:
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
                assets={f"MoltenVK-{version}.xcframework.zip"},
                is_prerelease=False,
            )
            module.fetch_latest_release_tag = lambda repo: version

            plan = module.resolve_release_plan(
                selection_mode="requested",
                release_channel="stable",
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
        self.assertIn(f"MoltenVKHeaders-{version}.zip", plan.missing_assets)

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

    def test_retag_workspace_rewrites_generated_payload_without_rebuilding_archives(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="moltenvk-retag-workspace-"))
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        source_version = "1.2.3-alpha.4"
        target_version = "1.2.3-alpha.5"
        artifacts_dir = temp_root / "Artifacts"
        swift_package_dir = temp_root / "SwiftPackage"
        release_assets_dir = temp_root / "release-assets"
        artifacts_dir.mkdir()
        swift_package_dir.mkdir()
        release_assets_dir.mkdir()

        shutil.copyfile(ROOT_DIR / "SwiftPackage" / "platforms.json", swift_package_dir / "platforms.json")
        (swift_package_dir / "ReleaseRepository.txt").write_text("SPMForge/MoltenVK\n", encoding="utf-8")
        (swift_package_dir / "PackageVersion.txt").write_text(f"{source_version}\n", encoding="utf-8")

        checksums = {
            f"MoltenVK-{source_version}.xcframework.checksum": "a" * 64,
            f"MoltenVK-static-{source_version}.xcframework.checksum": "b" * 64,
            f"MoltenVKHeaders-{source_version}.checksum": "c" * 64,
        }
        for name, checksum in checksums.items():
            (artifacts_dir / name).write_text(f"{checksum}\n", encoding="utf-8")

        for name in (
            f"MoltenVK-{source_version}.xcframework.zip",
            f"MoltenVK-static-{source_version}.xcframework.zip",
            f"MoltenVKHeaders-{source_version}.zip",
        ):
            (release_assets_dir / name).write_text("archive\n", encoding="utf-8")

        module.retag_generated_workspace(source_version, target_version, temp_root, release_assets_dir)

        self.assertEqual((swift_package_dir / "PackageVersion.txt").read_text(encoding="utf-8"), f"{target_version}\n")
        self.assertFalse((artifacts_dir / f"MoltenVK-{source_version}.xcframework.checksum").exists())
        self.assertFalse((release_assets_dir / f"MoltenVK-{source_version}.xcframework.zip").exists())
        self.assertTrue((artifacts_dir / f"MoltenVK-{target_version}.xcframework.checksum").is_file())
        self.assertTrue((release_assets_dir / f"MoltenVK-{target_version}.xcframework.zip").is_file())
        rendered_manifest = (temp_root / "Package.swift").read_text(encoding="utf-8")
        self.assertIn(f"releases/download/{target_version}/MoltenVK-{target_version}.xcframework.zip", rendered_manifest)
        self.assertIn(f'checksum: "{"a" * 64}"', rendered_manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
