#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


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
    build_script = read_text(REPO_ROOT / "Scripts" / "SwiftPackage" / "build_swift_package.sh")
    release_publication = read_text(REPO_ROOT / "Scripts" / "SwiftPackage" / "release_publication.py")
    publish_workflow = read_text(WORKFLOWS_DIR / "publish-package-release-core.yml")
    alpha_publish_workflow = read_text(WORKFLOWS_DIR / "publish-latest-upstream-alpha.yml")
    manual_publish_workflow = read_text(WORKFLOWS_DIR / "publish-upstream-release-manually.yml")
    validate_workflow = read_text(WORKFLOWS_DIR / "validate-apple-release-pipeline.yml")

    require("wrapper repo" in readme, "README must describe MoltenVK as a wrapper repo")
    require("render_local_dev_package_manifest.py" in readme, "README must document the explicit local-only manifest helper")
    require("Alpha publishes create and tag a release/" in readme, "README must describe the alpha release-branch model")
    require("default branch can be fast-forwarded only from the manual stable path" in readme, "README must describe the stable-only default-branch update rule")
    require("Runtime dependency model" in readme, "README must record the runtime dependency model")
    require("Runtime dependency model: `none`" in readme, "README must record MoltenVK as runtime dependency model none")
    require("does not ship a `libvulkan.dylib`" in readme, "README must state MoltenVK does not ship a libvulkan loader")
    require("does not promise a `libvulkan.1.dylib`" in readme, "README must state MoltenVK does not promise a libvulkan.1.dylib alias")
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
    require("push:" in validate_workflow and "pull_request:" in validate_workflow, "validation workflow must run on push and pull_request")
    require("MVK_PREPARED_WORKSPACE_RECORD" in validate_workflow, "validation workflow must use prepared workspace mode")
    require((REPO_ROOT / "Scripts" / "SwiftPackage" / "render_local_dev_package_manifest.py").exists(), "local-only manifest helper missing")
    require((REPO_ROOT / "Scripts" / "SwiftPackage" / "release_publication.py").exists(), "release publication planner missing")
    require((REPO_ROOT / "SwiftPackage" / "platforms.json").exists(), "platform config missing")

    print("MoltenVK SOP conformance verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
