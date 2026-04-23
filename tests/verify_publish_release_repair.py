#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISH_SCRIPT = REPO_ROOT / "Scripts" / "SwiftPackage" / "publish_release.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def prepare_temp_checkout() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="moltenvk-publish-repair-"))
    shutil.copytree(REPO_ROOT / "Scripts", temp_root / "Scripts", symlinks=True)
    shutil.copytree(REPO_ROOT / "SwiftPackage", temp_root / "SwiftPackage", symlinks=True)
    (temp_root / "Artifacts").mkdir()
    return temp_root


def create_release_assets(root: Path, version: str) -> None:
    prepared_workspace = root / "prepared-workspace"
    artifacts_dir = prepared_workspace / "Artifacts"
    swift_package_dir = prepared_workspace / "SwiftPackage"
    artifacts_dir.mkdir(parents=True)
    swift_package_dir.mkdir(parents=True)

    dynamic_zip = artifacts_dir / f"MoltenVK-{version}.xcframework.zip"
    static_zip = artifacts_dir / f"MoltenVK-static-{version}.xcframework.zip"
    headers_zip = artifacts_dir / f"MoltenVKHeaders-{version}.zip"
    for asset in (dynamic_zip, static_zip, headers_zip):
        asset.write_text("asset", encoding="utf-8")

    (swift_package_dir / "UpstreamSourceRef.txt").write_text("v1.2.3", encoding="utf-8")
    (root / "SwiftPackage" / "UpstreamSourceRef.txt").write_text("v1.2.3", encoding="utf-8")
    (root / "Artifacts" / f"MoltenVK-{version}.xcframework.checksum").write_text("a" * 64, encoding="utf-8")
    (root / "Artifacts" / f"MoltenVK-static-{version}.xcframework.checksum").write_text("b" * 64, encoding="utf-8")
    (root / "Artifacts" / f"MoltenVKHeaders-{version}.checksum").write_text("c" * 64, encoding="utf-8")
    (root / "SwiftPackage" / ".prepared-workspace-path").write_text(str(prepared_workspace), encoding="utf-8")


def install_git_wrapper(bin_dir: Path, log_file: Path, *, remote_tag_exists: bool, local_tag_exists: bool) -> None:
    write_executable(
        bin_dir / "git",
        f"""#!/bin/bash
set -euo pipefail
printf 'git %s\\n' "$*" >> "{log_file}"
case "$1" in
  remote)
    if [[ "$2" == "get-url" && "$3" == "origin" ]]; then
      printf '%s\\n' "git@github.com:SPMForge/MoltenVK.git"
      exit 0
    fi
    ;;
  rev-parse)
    if [[ "{str(local_tag_exists).lower()}" == "true" && "$*" == *"refs/tags/"* ]]; then
      exit 0
    fi
    exit 1
    ;;
  ls-remote)
    if [[ "{str(remote_tag_exists).lower()}" == "true" && "$*" == *"refs/tags/"* ]]; then
      exit 0
    fi
    exit 1
    ;;
  diff)
    exit 0
    ;;
esac
exit 0
""",
    )


def install_gh_wrapper(bin_dir: Path, log_file: Path, *, release_exists: bool) -> None:
    write_executable(
        bin_dir / "gh",
        f"""#!/bin/bash
set -euo pipefail
printf 'gh %s\\n' "$*" >> "{log_file}"
case "$1 $2" in
  release\\ view)
    if [[ "{str(release_exists).lower()}" == "true" ]]; then
      exit 0
    fi
    exit 1
    ;;
  release\\ edit|release\\ create|release\\ upload)
    exit 0
    ;;
esac
exit 1
""",
    )


class PublishReleaseRepairTests(unittest.TestCase):
    maxDiff = None

    def run_publish(
        self,
        version: str,
        release_kind: str,
        *,
        remote_tag_exists: bool,
        local_tag_exists: bool,
        release_exists: bool,
        release_action: str,
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        temp_root = prepare_temp_checkout()
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)
        create_release_assets(temp_root, version)

        bin_dir = temp_root / "bin"
        bin_dir.mkdir()
        command_log = temp_root / "commands.log"
        install_git_wrapper(bin_dir, command_log, remote_tag_exists=remote_tag_exists, local_tag_exists=local_tag_exists)
        install_gh_wrapper(bin_dir, command_log, release_exists=release_exists)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["GITHUB_REPOSITORY"] = "SPMForge/MoltenVK"
        env["GITHUB_TOKEN"] = "dummy-token"
        env["MVK_RELEASE_ACTION"] = release_action

        completed = subprocess.run(
            ["bash", str(temp_root / "Scripts" / "SwiftPackage" / "publish_release.sh"), version, release_kind],
            cwd=temp_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, temp_root, command_log

    def test_alpha_repair_updates_existing_release_in_place(self) -> None:
        completed, temp_root, command_log = self.run_publish(
            "1.2.3-alpha.4",
            "alpha",
            remote_tag_exists=True,
            local_tag_exists=True,
            release_exists=True,
            release_action="edit",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        commands = command_log.read_text(encoding="utf-8")
        self.assertIn("git add -A Artifacts", commands)
        self.assertIn("gh release edit 1.2.3-alpha.4", commands)
        self.assertIn("--prerelease", commands)
        self.assertIn("--latest=false", commands)
        self.assertIn("gh release upload 1.2.3-alpha.4", commands)
        self.assertIn("--clobber", commands)
        self.assertNotIn("gh release create 1.2.3-alpha.4", commands)
        self.assertNotIn("git tag -a 1.2.3-alpha.4 refs/remotes/origin/main", commands)

    def test_stable_missing_release_creates_and_uploads_assets(self) -> None:
        completed, temp_root, command_log = self.run_publish(
            "1.2.3",
            "stable",
            remote_tag_exists=False,
            local_tag_exists=False,
            release_exists=False,
            release_action="create",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        commands = command_log.read_text(encoding="utf-8")
        self.assertIn("git add -A Artifacts", commands)
        self.assertIn("git fetch --force origin refs/heads/main:refs/remotes/origin/main refs/tags/*:refs/tags/*", commands)
        self.assertIn("git tag -a 1.2.3 refs/remotes/origin/main -m 1.2.3", commands)
        self.assertIn("git push origin refs/tags/1.2.3:refs/tags/1.2.3", commands)
        self.assertIn("gh release create 1.2.3", commands)
        self.assertIn("--verify-tag", commands)
        self.assertIn("gh release upload 1.2.3", commands)
        self.assertIn("--clobber", commands)
        self.assertNotIn("gh release edit 1.2.3", commands)


if __name__ == "__main__":
    unittest.main(verbosity=2)
