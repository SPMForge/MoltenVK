#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compute_next_alpha_version import DEFAULT_TAG_PREFIXES, Version, parse_release_identifiers, parse_version


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


@dataclass(frozen=True)
class GitHubRelease:
    tag_name: str
    assets: set[str]
    is_prerelease: bool
    is_draft: bool


@dataclass(frozen=True)
class ReleasePlan:
    upstream_ref: str
    target_version: str
    publication_mode: str
    release_action: str
    remote_tag_exists: bool
    release_exists: bool
    metadata_needs_repair: bool
    missing_assets: list[str]
    reason: str
    build_version: str = ""
    latest_alpha_version: str = ""
    next_alpha_version: str = ""

    def as_output_map(self) -> dict[str, str]:
        return {
            "upstream_ref": self.upstream_ref,
            "target_version": self.target_version,
            "build_version": self.build_version or self.target_version,
            "publication_mode": self.publication_mode,
            "release_action": self.release_action,
            "remote_tag_exists": str(self.remote_tag_exists).lower(),
            "release_exists": str(self.release_exists).lower(),
            "metadata_needs_repair": str(self.metadata_needs_repair).lower(),
            "missing_assets": ",".join(self.missing_assets),
            "reason": self.reason,
            "latest_alpha_version": self.latest_alpha_version,
            "next_alpha_version": self.next_alpha_version,
        }


def run_command(args: list[str], *, check: bool, allow_not_found: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        if allow_not_found:
            return subprocess.CompletedProcess(args=args, returncode=127, stdout="", stderr="command not found")
        raise

    if check and completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "command failed"
        fail(f"{' '.join(args)}: {details}")
    return completed


def list_remote_tag_names() -> list[str]:
    completed = run_command(["git", "ls-remote", "--tags", "--refs", "origin"], check=True)
    tags: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            _, ref_name = line.split("\t", 1)
        except ValueError:
            fail(f"Unable to parse git ls-remote output line: {line}")
        tags.append(ref_name.removeprefix("refs/tags/"))
    return tags


def list_github_release_tags(repo: str) -> list[str]:
    completed = run_command(
        ["gh", "release", "list", "--repo", repo, "--limit", "100", "--json", "tagName"],
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip() or "gh release list failed"
        fail(f"Unable to query GitHub releases for {repo}: {details}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        fail(f"Unable to parse GitHub release list for {repo}.")

    tags: list[str] = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("tagName"), str):
            tags.append(item["tagName"])
    return tags


def fetch_github_release(repo: str, tag: str) -> GitHubRelease | None:
    completed = run_command(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "assets,isDraft,isPrerelease,tagName"],
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        if "release not found" in details.lower() or "not found" in details.lower():
            return None
        fail(f"Unable to inspect GitHub release {tag} in {repo}: {details or 'gh release view failed'}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        fail(f"Unable to parse GitHub release metadata for {tag} in {repo}.")

    tag_name = payload.get("tagName")
    if not isinstance(tag_name, str) or not tag_name:
        fail(f"GitHub release {tag} in {repo} returned an invalid tag name.")

    assets_payload = payload.get("assets")
    if not isinstance(assets_payload, list):
        fail(f"GitHub release {tag} in {repo} returned invalid assets metadata.")

    assets: set[str] = set()
    for asset in assets_payload:
        if isinstance(asset, dict) and isinstance(asset.get("name"), str):
            assets.add(asset["name"])

    is_prerelease = payload.get("isPrerelease")
    is_draft = payload.get("isDraft")
    if not isinstance(is_prerelease, bool) or not isinstance(is_draft, bool):
        fail(f"GitHub release {tag} in {repo} returned invalid prerelease metadata.")

    return GitHubRelease(
        tag_name=tag_name,
        assets=assets,
        is_prerelease=is_prerelease,
        is_draft=is_draft,
    )


def fetch_latest_release_tag(repo: str) -> str | None:
    completed = run_command(
        ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"],
        check=False,
        allow_not_found=True,
    )
    if completed.returncode == 0:
        latest_tag = completed.stdout.strip()
        return latest_tag or None

    details = completed.stderr.strip() or completed.stdout.strip()
    normalized = details.lower()
    if completed.returncode in {1, 127} and ("not found" in normalized or "command not found" in normalized):
        return None
    fail(f"Unable to inspect latest release metadata for {repo}: {details or 'gh api releases/latest failed'}")


def required_release_assets(version: str) -> set[str]:
    return {
        f"MoltenVK-{version}.xcframework.zip",
        f"MoltenVK-{version}.xcframework.checksum",
        f"MoltenVK-static-{version}.xcframework.zip",
        f"MoltenVK-static-{version}.xcframework.checksum",
        f"MoltenVKHeaders-{version}.zip",
        f"MoltenVKHeaders-{version}.checksum",
    }


def release_asset_name_pairs(version: str) -> list[tuple[str, str]]:
    return [
        (
            f"MoltenVK-{version}.xcframework.zip",
            f"MoltenVK-{version}.xcframework.checksum",
        ),
        (
            f"MoltenVK-static-{version}.xcframework.zip",
            f"MoltenVK-static-{version}.xcframework.checksum",
        ),
        (
            f"MoltenVKHeaders-{version}.zip",
            f"MoltenVKHeaders-{version}.checksum",
        ),
    ]


def normalize_version_identifiers(identifiers: list[str]) -> list[Version]:
    parsed = parse_release_identifiers(identifiers, list(DEFAULT_TAG_PREFIXES))
    return [version for _, version in parsed]


def inspect_target_state(repo: str, upstream_ref: str, target_version: str, release_channel: str, remote_tags: set[str]) -> ReleasePlan:
    remote_tag_exists = target_version in remote_tags
    release = fetch_github_release(repo, target_version)
    release_exists = release is not None

    if release_exists and not remote_tag_exists:
        fail(f"GitHub release {target_version} exists but the package tag is missing.")

    required_assets = required_release_assets(target_version)
    missing_assets = sorted(required_assets - (release.assets if release else set()))

    metadata_needs_repair = False
    if release is not None:
        latest_release_tag = fetch_latest_release_tag(repo)
        if release.is_draft:
            metadata_needs_repair = True
        elif release_channel == "alpha":
            metadata_needs_repair = (not release.is_prerelease) or latest_release_tag == target_version
        else:
            metadata_needs_repair = release.is_prerelease

    if not remote_tag_exists:
        return ReleasePlan(
            upstream_ref=upstream_ref,
            target_version=target_version,
            publication_mode="create",
            release_action="create",
            remote_tag_exists=False,
            release_exists=release_exists,
            metadata_needs_repair=metadata_needs_repair,
            missing_assets=missing_assets,
            reason="package tag is missing",
        )

    if not release_exists:
        return ReleasePlan(
            upstream_ref=upstream_ref,
            target_version=target_version,
            publication_mode="repair",
            release_action="create",
            remote_tag_exists=True,
            release_exists=False,
            metadata_needs_repair=False,
            missing_assets=sorted(required_assets),
            reason="package tag exists but GitHub release is missing",
        )

    if missing_assets or metadata_needs_repair:
        return ReleasePlan(
            upstream_ref=upstream_ref,
            target_version=target_version,
            publication_mode="repair",
            release_action="edit",
            remote_tag_exists=True,
            release_exists=True,
            metadata_needs_repair=metadata_needs_repair,
            missing_assets=missing_assets,
            reason="GitHub release is incomplete or metadata drifted",
        )

    return ReleasePlan(
        upstream_ref=upstream_ref,
        target_version=target_version,
        publication_mode="skip",
        release_action="skip",
        remote_tag_exists=True,
        release_exists=True,
        metadata_needs_repair=False,
        missing_assets=[],
        reason="package tag and GitHub release already match the required contract",
    )


def read_optional_tagged_text(tag: str, relative_path: str) -> str | None:
    completed = run_command(["git", "show", f"refs/tags/{tag}:{relative_path}"], check=False)
    if completed.returncode == 0:
        return completed.stdout

    fetch_completed = run_command(
        ["git", "fetch", "--force", "origin", f"refs/tags/{tag}:refs/tags/{tag}"],
        check=False,
    )
    if fetch_completed.returncode != 0:
        return None

    completed = run_command(["git", "show", f"refs/tags/{tag}:{relative_path}"], check=False)
    if completed.returncode == 0:
        return completed.stdout
    return None


def with_alpha_context(plan: ReleasePlan, latest_alpha: Version, base_version: Version) -> ReleasePlan:
    next_alpha_version = str(base_version.with_alpha((latest_alpha.alpha or 0) + 1))
    return ReleasePlan(
        upstream_ref=plan.upstream_ref,
        target_version=plan.target_version,
        publication_mode=plan.publication_mode,
        release_action=plan.release_action,
        remote_tag_exists=plan.remote_tag_exists,
        release_exists=plan.release_exists,
        metadata_needs_repair=plan.metadata_needs_repair,
        missing_assets=plan.missing_assets,
        reason=plan.reason,
        build_version=plan.build_version or plan.target_version,
        latest_alpha_version=str(latest_alpha),
        next_alpha_version=next_alpha_version,
    )


def select_existing_or_next_alpha_plan(
    *,
    repo: str,
    upstream_ref: str,
    base_version: Version,
    highest_alpha: Version,
    release_channel: str,
    remote_tags: set[str],
    rendered_package_swift: str | None,
    rendered_workspace_root: Path | None,
) -> ReleasePlan:
    highest_tag = str(highest_alpha)
    highest_plan = inspect_target_state(repo, upstream_ref, highest_tag, release_channel, remote_tags)
    if highest_plan.publication_mode != "skip":
        return with_alpha_context(highest_plan, highest_alpha, base_version)

    if rendered_package_swift is None and rendered_workspace_root is None:
        return with_alpha_context(
            ReleasePlan(
                upstream_ref=highest_plan.upstream_ref,
                target_version=highest_plan.target_version,
                publication_mode="evaluate",
                release_action="skip",
                remote_tag_exists=highest_plan.remote_tag_exists,
                release_exists=highest_plan.release_exists,
                metadata_needs_repair=highest_plan.metadata_needs_repair,
                missing_assets=highest_plan.missing_assets,
                reason="highest alpha is complete; build and compare rendered Package.swift and release metadata before deciding whether to skip or mint next alpha",
                build_version=highest_tag,
            ),
            highest_alpha,
            base_version,
        )

    if generated_contract_matches_tag(highest_tag, rendered_package_swift, rendered_workspace_root):
        return with_alpha_context(highest_plan, highest_alpha, base_version)

    next_alpha = (highest_alpha.alpha or 0) + 1
    target_version = str(base_version.with_alpha(next_alpha))
    next_plan = inspect_target_state(repo, upstream_ref, target_version, release_channel, remote_tags)
    return with_alpha_context(
        ReleasePlan(
            upstream_ref=next_plan.upstream_ref,
            target_version=next_plan.target_version,
            publication_mode=next_plan.publication_mode,
            release_action=next_plan.release_action,
            remote_tag_exists=next_plan.remote_tag_exists,
            release_exists=next_plan.release_exists,
            metadata_needs_repair=next_plan.metadata_needs_repair,
            missing_assets=next_plan.missing_assets,
            reason="rendered package contract differs from latest alpha tag; publishing next alpha",
            build_version=highest_tag,
        ),
        highest_alpha,
        base_version,
    )


def resolve_release_plan(
    selection_mode: str,
    release_channel: str,
    upstream_ref: str,
    repo: str,
    rendered_package_swift: str | None = None,
    rendered_workspace_root: Path | None = None,
) -> ReleasePlan:
    if release_channel not in {"alpha", "stable"}:
        fail(f"Unsupported release channel: {release_channel}")
    if selection_mode not in {"latest", "requested"}:
        fail(f"Unsupported selection mode: {selection_mode}")
    if selection_mode == "latest" and release_channel != "alpha":
        fail("selection_mode=latest only supports alpha releases")

    base_version = parse_version(upstream_ref.removeprefix("v"))
    if base_version.is_alpha:
        fail(f"Upstream ref must be stable, got {upstream_ref}")

    remote_tag_names = list_remote_tag_names()
    release_tags = list_github_release_tags(repo)
    all_versions = normalize_version_identifiers([*remote_tag_names, *release_tags])
    matching_versions = [version for version in all_versions if version.core == base_version]
    stable_versions = [version for version in matching_versions if not version.is_alpha]

    if release_channel == "stable":
        target_version = str(base_version)
        return inspect_target_state(repo, upstream_ref, target_version, release_channel, set(remote_tag_names))

    if stable_versions:
        stable_plan = inspect_target_state(
            repo,
            upstream_ref,
            str(base_version),
            "stable",
            set(remote_tag_names),
        )
        if stable_plan.publication_mode == "skip":
            return ReleasePlan(
                upstream_ref=stable_plan.upstream_ref,
                target_version=stable_plan.target_version,
                publication_mode="skip",
                release_action="skip",
                remote_tag_exists=stable_plan.remote_tag_exists,
                release_exists=stable_plan.release_exists,
                metadata_needs_repair=stable_plan.metadata_needs_repair,
                missing_assets=stable_plan.missing_assets,
                reason=f"stable package release already exists for {base_version}",
            )
        fail(
            f"Stable package release {base_version} is incomplete "
            f"({stable_plan.reason}); repair it through the stable release path before publishing alpha."
        )

    alpha_versions = [version for version in matching_versions if version.is_alpha]
    if alpha_versions:
        highest_alpha = max(alpha_versions, key=lambda version: version.alpha or 0)
        return select_existing_or_next_alpha_plan(
            repo=repo,
            upstream_ref=upstream_ref,
            base_version=base_version,
            highest_alpha=highest_alpha,
            release_channel=release_channel,
            remote_tags=set(remote_tag_names),
            rendered_package_swift=rendered_package_swift,
            rendered_workspace_root=rendered_workspace_root,
        )

    target_version = str(base_version.with_alpha(1))
    return inspect_target_state(repo, upstream_ref, target_version, release_channel, set(remote_tag_names))


def copy_and_remove_source(source: Path, destination: Path) -> None:
    if not source.is_file():
        fail(f"Missing source release payload file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    if source != destination:
        source.unlink()


def retag_generated_workspace(source_version: str, target_version: str, workspace_root: Path, release_assets_dir: Path) -> None:
    parse_version(source_version)
    parse_version(target_version)
    if source_version == target_version:
        return

    artifacts_dir = workspace_root / "Artifacts"
    swift_package_dir = workspace_root / "SwiftPackage"
    release_repository_path = swift_package_dir / "ReleaseRepository.txt"
    platform_config_path = swift_package_dir / "platforms.json"

    if not artifacts_dir.is_dir():
        fail(f"Missing Artifacts directory: {artifacts_dir}")
    if not release_assets_dir.is_dir():
        fail(f"Missing release assets directory: {release_assets_dir}")
    if not release_repository_path.is_file():
        fail(f"Missing release repository metadata: {release_repository_path}")
    if not platform_config_path.is_file():
        fail(f"Missing platform config: {platform_config_path}")

    for source_zip_name, source_checksum_name in release_asset_name_pairs(source_version):
        target_zip_name = source_zip_name.replace(source_version, target_version)
        target_checksum_name = source_checksum_name.replace(source_version, target_version)
        copy_and_remove_source(release_assets_dir / source_zip_name, release_assets_dir / target_zip_name)
        copy_and_remove_source(artifacts_dir / source_checksum_name, artifacts_dir / target_checksum_name)

    package_version_path = swift_package_dir / "PackageVersion.txt"
    package_version_path.write_text(f"{target_version}\n", encoding="utf-8")

    release_repository = release_repository_path.read_text(encoding="utf-8").strip()
    dynamic_checksum_path = artifacts_dir / f"MoltenVK-{target_version}.xcframework.checksum"
    dynamic_checksum = dynamic_checksum_path.read_text(encoding="utf-8").strip()
    render_script = SCRIPT_DIR / "render_package_manifest.py"
    run_command(
        [
            "python3",
            str(render_script),
            "--version",
            target_version,
            "--release-repository",
            release_repository,
            "--checksum",
            dynamic_checksum,
            "--platform-config",
            str(platform_config_path),
            "--output",
            str(workspace_root / "Package.swift"),
        ],
        check=True,
    )


def generated_contract_matches_tag(tag: str, rendered_package_swift: str | None, rendered_workspace_root: Path | None) -> bool:
    if rendered_workspace_root is not None:
        for relative_path in metadata_paths_for_version(tag):
            workspace_path = rendered_workspace_root / relative_path
            if not workspace_path.is_file():
                fail(f"Missing generated release metadata file: {workspace_path}")

            tagged_text = read_optional_tagged_text(tag, relative_path)
            if tagged_text is None:
                fail(f"Package tag {tag} exists but {relative_path} could not be read from the tag.")
            if tagged_text != workspace_path.read_text(encoding="utf-8"):
                return False
        return True

    if rendered_package_swift is None:
        fail("Rendered Package.swift or rendered workspace root is required for alpha package contract comparison.")

    tagged_package_swift = read_optional_tagged_text(tag, "Package.swift")
    if tagged_package_swift is None:
        fail(f"Package tag {tag} exists but Package.swift could not be read from the tag.")
    return tagged_package_swift == rendered_package_swift


def metadata_paths_for_version(version: str) -> list[str]:
    return [
        "Package.swift",
        "SwiftPackage/PackageVersion.txt",
        "SwiftPackage/ReleaseRepository.txt",
        "SwiftPackage/UpstreamRepository.txt",
        "SwiftPackage/UpstreamSourceRef.txt",
        f"Artifacts/MoltenVK-{version}.xcframework.checksum",
        f"Artifacts/MoltenVK-static-{version}.xcframework.checksum",
        f"Artifacts/MoltenVKHeaders-{version}.checksum",
    ]


def read_tagged_text(tag: str, relative_path: str) -> str:
    tagged_text = read_optional_tagged_text(tag, relative_path)
    if tagged_text is None:
        details = f"unable to read {relative_path} from refs/tags/{tag}"
        fail(f"Unable to read {relative_path} from tag {tag}: {details}")
    return tagged_text


def assert_tagged_state_matches_workspace(tag: str, workspace_root: Path) -> None:
    for relative_path in metadata_paths_for_version(tag):
        workspace_path = workspace_root / relative_path
        if not workspace_path.is_file():
            fail(f"Missing generated release metadata file: {workspace_path}")

        tagged_text = read_tagged_text(tag, relative_path)
        workspace_text = workspace_path.read_text(encoding="utf-8")
        if tagged_text != workspace_text:
            fail(
                f"Generated release metadata drifted from existing package tag {tag}: "
                f"{relative_path} differs from refs/tags/{tag}."
            )


def write_github_output(path: Path, outputs: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def command_plan(args: argparse.Namespace) -> int:
    rendered_package_swift = None
    if args.rendered_package_swift:
        rendered_package_swift = Path(args.rendered_package_swift).read_text(encoding="utf-8")
    rendered_workspace_root = Path(args.rendered_workspace_root).resolve() if args.rendered_workspace_root else None

    plan = resolve_release_plan(
        selection_mode=args.selection_mode,
        release_channel=args.release_channel,
        upstream_ref=args.upstream_ref,
        repo=args.repo,
        rendered_package_swift=rendered_package_swift,
        rendered_workspace_root=rendered_workspace_root,
    )
    outputs = plan.as_output_map()
    if args.github_output:
        write_github_output(Path(args.github_output), outputs)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


def command_assert_tagged_state(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    assert_tagged_state_matches_workspace(args.tag, workspace_root)
    print(f"release metadata matches refs/tags/{args.tag}")
    return 0


def command_retag_workspace(args: argparse.Namespace) -> int:
    retag_generated_workspace(
        args.source_version,
        args.target_version,
        Path(args.workspace_root).resolve(),
        Path(args.release_assets_dir).resolve(),
    )
    print(f"retagged generated release payload from {args.source_version} to {args.target_version}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve MoltenVK GitHub release publication state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Resolve create/repair/skip publication state.")
    plan_parser.add_argument("--selection-mode", required=True)
    plan_parser.add_argument("--release-channel", required=True)
    plan_parser.add_argument("--upstream-ref", required=True)
    plan_parser.add_argument("--repo", required=True)
    plan_parser.add_argument("--rendered-package-swift", default="")
    plan_parser.add_argument("--rendered-workspace-root", default="")
    plan_parser.add_argument("--github-output", default="")
    plan_parser.set_defaults(func=command_plan)

    assert_parser = subparsers.add_parser("assert-tagged-state", help="Ensure generated metadata matches an existing package tag.")
    assert_parser.add_argument("--tag", required=True)
    assert_parser.add_argument("--workspace-root", required=True)
    assert_parser.set_defaults(func=command_assert_tagged_state)

    retag_parser = subparsers.add_parser("retag-workspace", help="Retag generated release payload files without rebuilding binaries.")
    retag_parser.add_argument("--source-version", required=True)
    retag_parser.add_argument("--target-version", required=True)
    retag_parser.add_argument("--workspace-root", required=True)
    retag_parser.add_argument("--release-assets-dir", required=True)
    retag_parser.set_defaults(func=command_retag_workspace)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
