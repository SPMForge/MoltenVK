#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def main() -> int:
    package_swift = read_text(REPO_ROOT / "Package.swift")
    readme = read_text(REPO_ROOT / "README.md")
    build_script = read_text(REPO_ROOT / "scripts" / "spm" / "build_swift_package.sh")
    release_publication = read_text(REPO_ROOT / "scripts" / "spm" / "release_publication.py")
    publish_workflow = read_text(WORKFLOWS_DIR / "publish-package-release-core.yml")
    alpha_publish_workflow = read_text(WORKFLOWS_DIR / "publish-latest-upstream-alpha.yml")
    manual_publish_workflow = read_text(WORKFLOWS_DIR / "publish-upstream-release-manually.yml")
    validate_workflow = read_text(WORKFLOWS_DIR / "validate-apple-release-pipeline.yml")

    gitignore = read_text(REPO_ROOT / ".gitignore")
    checksums_dir = REPO_ROOT / "config" / "checksums"

    top_level_names = {p.name for p in REPO_ROOT.iterdir()}
    require("config" in top_level_names and (REPO_ROOT / "config").is_dir(), "config/ directory must exist")
    require("scripts" in top_level_names and (REPO_ROOT / "scripts" / "verify_sop_conformance.py").is_file(), "scripts/verify_sop_conformance.py must exist")
    require("tests" in top_level_names and (REPO_ROOT / "tests").is_dir(), "top-level tests/ directory must exist")
    require((REPO_ROOT / "docs" / "how-to-build" / "swiftpm-binary-package.md").is_file(), "docs/how-to-build/swiftpm-binary-package.md must exist")
    require("SwiftPackage" not in top_level_names, "legacy SwiftPackage/ directory must be migrated to config/")
    require("Scripts" not in top_level_names and not (REPO_ROOT / "scripts" / "SwiftPackage").exists(), "legacy Scripts/SwiftPackage/ directory must be migrated to scripts/spm/")

    if (REPO_ROOT / ".git").exists():
        tracked_artifacts = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "Artifacts"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        require(not tracked_artifacts, "committed repository must not track Artifacts directory in Git")
    require(not (REPO_ROOT / "Artifacts").exists(), "committed repository must not track Artifacts directory")
    require("/Artifacts/" in gitignore or "Artifacts/" in gitignore, ".gitignore must ignore Artifacts/")
    require("!/Artifacts" not in gitignore, ".gitignore must not contain Artifacts whitelist exceptions")
    require(checksums_dir.is_dir(), "config/checksums must exist as the tracked checksum directory")
    require("strictly an ignored local/ephemeral build output directory" in readme, "README must document Artifacts as an ignored ephemeral build directory")
    require("repo/config/checksums" in publish_workflow, "publish workflow must stage checksums into repo/config/checksums")
    require("find Artifacts" not in publish_workflow, "publish workflow must not find checksums in Artifacts")
    require('mkdir -p "$GITHUB_WORKSPACE/Artifacts"' not in publish_workflow, "publish workflow must not restore checksums into Artifacts")
    require("config/checksums" in release_publication, "release publication planner must track checksums in config/checksums")
    require("expected_tagged_file_paths" in release_publication, "release publication planner must export expected_tagged_file_paths")

    require("wrapper repo" in readme, "README must describe MoltenVK as a wrapper repo")
    require("render_local_dev_package_manifest.py" in readme, "README must document the explicit local-only manifest helper")
    require("Alpha publishes create and tag a release/" in readme, "README must describe the alpha release-branch model")
    require("default branch can be fast-forwarded only from the manual stable path" in readme, "README must describe the stable-only default-branch update rule")
    require("Runtime dependency model" in readme, "README must record the runtime dependency model")
    require("Runtime dependency model: `none`" in readme, "README must record MoltenVK as runtime dependency model none")
    require("does not ship a `libvulkan.dylib`" in readme, "README must state MoltenVK does not ship a libvulkan loader")
    require("does not promise a `libvulkan.1.dylib`" in readme, "README must state MoltenVK does not promise a libvulkan.1.dylib alias")
    require("C/C++ build-time include contract" in readme, "README must document the native build-time include contract")
    require("Vulkan_INCLUDE_DIR=<extracted>/include" in readme, "README must document the CMake include root")
    require("Vulkan_LIBRARY=<path-to-MoltenVK.framework/MoltenVK>" in readme, "README must document the framework binary link input")
    require("should not assume `MoltenVK.framework/Headers` alone" in readme, "README must reject direct framework Headers as the native include contract")
    require("FileManager.default.fileExists" not in package_swift, "committed Package.swift must not use local checkout fallback")
    require('path: "Artifacts/MoltenVK.xcframework"' not in package_swift, "committed Package.swift must not point at local Artifacts")
    require("url:" in package_swift and "checksum:" in package_swift, "committed Package.swift must be a remote binary target contract")
    require("MVK_PREPARED_WORKSPACE_RECORD" in build_script, "build script must support prepared workspace mode")
    require("MVK_SYNC_WORKSPACE_OUTPUTS_TO_WRAPPER" in build_script, "build script must gate checkout sync behind an explicit flag")
    require("verify:" in publish_workflow and "resolve:" in publish_workflow and "build:" in publish_workflow and "publish:" in publish_workflow, "publish workflow must split verify/resolve/build/publish jobs")
    require("release_publication.py plan" in publish_workflow, "publish workflow must resolve release state through repo-local Python")
    require("select_existing_or_next_alpha_plan" in release_publication, "release planner must centralize alpha reuse vs next-alpha selection")
    require('publication_mode="evaluate"' in release_publication, "complete alpha must enter pre-build evaluation instead of skipping before rendered contract comparison")
    require('if highest_plan.publication_mode != "skip":' in release_publication, "release planner must repair incomplete highest alpha before considering a new alpha")
    require("build and compare rendered Package.swift and release metadata" in release_publication, "complete alpha must keep the workflow alive until rendered package contract is available")
    require("generated_contract_matches_tag" in release_publication, "release planner must compare the rendered package contract with the latest alpha tag")
    require("--rendered-package-swift" in release_publication, "release planner CLI must expose rendered-manifest comparison input")
    require("--rendered-workspace-root" in release_publication, "release planner CLI must expose rendered release metadata comparison input")
    require("build_version:" in publish_workflow and "needs.resolve.outputs.build_version" in publish_workflow, "publish workflow must distinguish pre-build build version from final publication version")
    require("Resolve final publication mode from rendered package contract" in publish_workflow, "publish workflow must run final planning after package contract has been rendered")
    require('--rendered-package-swift "$GITHUB_WORKSPACE/Package.swift"' in publish_workflow, "publish workflow must pass the rendered Package.swift into final release planning")
    require('--rendered-workspace-root "$GITHUB_WORKSPACE"' in publish_workflow, "publish workflow must pass generated release metadata into final release planning")
    require("retag-workspace" in publish_workflow, "publish workflow must retag rendered payload when final alpha advances after manifest comparison")
    require("steps.final_plan.outputs.target_version" in publish_workflow, "publish workflow must publish the final post-render target version")
    require("publish_to_default_branch:" in publish_workflow, "publish workflow must declare default-branch publication control")
    require("MVK_PUBLISH_TO_DEFAULT_BRANCH: ${{ inputs.publish_to_default_branch }}" in publish_workflow, "publish workflow must pass the default-branch publication flag into publish_release.sh")
    require("moltenvk-release-payload-${{ github.run_id }}" in publish_workflow, "publish workflow payload artifact name must stay stable within a workflow run")
    require("moltenvk-release-payload-${{ github.run_id }}-${{ github.run_attempt }}" not in publish_workflow, "publish workflow payload artifact name must not key on run_attempt")
    require("overwrite: true" in publish_workflow, "publish workflow payload upload must overwrite the stable artifact on full reruns")
    require("publish_to_default_branch: false" in alpha_publish_workflow, "auto alpha workflow must keep default-branch publication disabled")
    require("publish_to_default_branch:" in manual_publish_workflow and "type: boolean" in manual_publish_workflow, "manual publish workflow must expose default-branch publication as an explicit boolean input")
    require("publish_to_default_branch: ${{ inputs.publish_to_default_branch }}" in manual_publish_workflow, "manual publish workflow must forward the explicit default-branch publication choice")
    require("MoltenVKHeaders-${TARGET_VERSION}.zip extracted include/ as Vulkan_INCLUDE_DIR" in read_text(REPO_ROOT / "scripts" / "spm" / "publish_release.sh"), "release notes must document the native include contract")
    require("does not ship a Vulkan loader dylib" in read_text(REPO_ROOT / "scripts" / "spm" / "publish_release.sh"), "release notes must preserve the no-loader contract")
    require("push:" in validate_workflow and "pull_request:" in validate_workflow, "validation workflow must run on push and pull_request")
    require("MVK_PREPARED_WORKSPACE_RECORD" in validate_workflow, "validation workflow must use prepared workspace mode")
    require((REPO_ROOT / "scripts" / "spm" / "render_local_dev_package_manifest.py").exists(), "local-only manifest helper missing")
    require((REPO_ROOT / "scripts" / "spm" / "release_publication.py").exists(), "release publication planner missing")
    require((REPO_ROOT / "config" / "platforms.json").exists(), "platform config missing")

    license_file = REPO_ROOT / "LICENSE"
    require(license_file.exists(), "MoltenVK must include root LICENSE file")
    require("Apache License" in read_text(license_file), "LICENSE must contain Apache License text")
    require("## License" in readme and "Apache License, Version 2.0" in readme, "README must contain ## License section with Apache License 2.0")
    require("Vulkan and the Vulkan logo are registered trademarks" in readme, "README must disclose Vulkan trademark notice")
    require('cp "$ROOT_DIR/LICENSE" "$DYNAMIC_DEST/LICENSE"' in build_script, "build script must inject LICENSE into DYNAMIC_DEST")
    require('cp "$ROOT_DIR/LICENSE" "$STATIC_DEST/LICENSE"' in build_script, "build script must inject LICENSE into STATIC_DEST")
    require('cp "$ROOT_DIR/LICENSE" "$fw/Versions/A/Resources/LICENSE"' in build_script, "build script must inject LICENSE into framework slice resources")

    consumer_script = read_text(REPO_ROOT / "tests" / "verify_swift_package_consumer.sh")
    require("swift run" in consumer_script, "consumer script must execute pure Swift smoke consumer via swift run")
    require("main.swift" in consumer_script, "consumer script must construct pure Swift main.swift")
    require("vkEnumerateInstanceVersion" in consumer_script, "consumer script must exercise Vulkan API in Swift")
    require('SCHEME_NAME="SmokeConsumer"' in consumer_script, "single-product consumer script must use the SmokeConsumer scheme")
    require("@loader_path/PackageFrameworks" in consumer_script, "consumer script must configure @loader_path rpaths for SwiftPM runtime execution")
    require("scripts/ci_artifacts.py consumers" in publish_workflow and "needs.consumers.result == 'success'" in publish_workflow, "publish workflow must require independent consumer acceptance")
    require("restore-homebrew-download-cache" not in publish_workflow and "HOMEBREW_CACHE" not in publish_workflow, "publish workflow must not cache HOMEBREW_CACHE to prevent runner symlink poisoning")
    require("restore-homebrew-download-cache" not in validate_workflow and "HOMEBREW_CACHE" not in validate_workflow, "validate workflow must not cache HOMEBREW_CACHE to prevent runner symlink poisoning")

    publication_text = (REPO_ROOT / ".github/workflows/publish-package-release-core.yml").read_text()
    require((REPO_ROOT / "scripts/release_inputs.py").is_file(), "immutable release input helper is required")
    require("scripts/release_inputs.py capture" in publication_text, "publish core must record immutable release inputs")
    require("SPMFORGE_EXPECTED_UPSTREAM_COMMIT" in publication_text, "build must pin the resolved upstream commit")
    require("config/release-inputs.json" in publication_text, "package tags must own release input metadata")
    require("group: spm-package-publication-${{ github.repository }}" in publication_text, "scheduled and manual publication must share a repository lock")
    require("--clobber" not in publication_text, "publish repair must not overwrite existing assets")

    print("MoltenVK SOP conformance verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
