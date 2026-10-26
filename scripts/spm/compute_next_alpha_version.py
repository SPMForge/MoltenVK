#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass


VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-alpha\.(?P<alpha>\d+))?$")
DEFAULT_TAG_PREFIXES = ("", "MoltenVK-v")


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    alpha: int | None = None

    @property
    def core(self) -> "Version":
        return Version(self.major, self.minor, self.patch, None)

    @property
    def is_alpha(self) -> bool:
        return self.alpha is not None

    def with_alpha(self, alpha: int) -> "Version":
        return Version(self.major, self.minor, self.patch, alpha)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.alpha is None:
            return base
        return f"{base}-alpha.{self.alpha}"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_version(raw: str) -> Version:
    match = VERSION_RE.fullmatch(raw.strip())
    if not match:
        fail(f"Invalid version: {raw}")
    return version_from_match(match)


def version_from_match(match: re.Match[str]) -> Version:
    groups = match.groupdict()
    alpha = groups["alpha"]
    return Version(
        major=int(groups["major"]),
        minor=int(groups["minor"]),
        patch=int(groups["patch"]),
        alpha=int(alpha) if alpha is not None else None,
    )


def try_parse_version(raw: str) -> Version | None:
    match = VERSION_RE.fullmatch(raw.strip())
    if not match:
        return None
    return version_from_match(match)


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def normalize_prefixes(prefixes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for prefix in prefixes:
        if prefix in seen:
            continue
        seen.add(prefix)
        normalized.append(prefix)
    return normalized


def parse_tag_as_version(raw_tag: str, prefixes: list[str]) -> Version | None:
    for prefix in prefixes:
        if prefix:
            if not raw_tag.startswith(prefix):
                continue
            candidate = raw_tag.removeprefix(prefix)
        else:
            candidate = raw_tag

        parsed = try_parse_version(candidate)
        if parsed is not None:
            return parsed

    return None


def parse_release_identifiers(raw_identifiers: list[str], prefixes: list[str]) -> list[tuple[str, Version]]:
    tags: list[tuple[str, Version]] = []
    seen: set[str] = set()
    for raw_tag in raw_identifiers:
        if raw_tag in seen:
            continue
        seen.add(raw_tag)
        parsed = parse_tag_as_version(raw_tag, prefixes)
        if parsed is None:
            continue
        tags.append((raw_tag, parsed))
    tags.sort(
        key=lambda item: (
            item[1].major,
            item[1].minor,
            item[1].patch,
            1 if item[1].alpha is None else 0,
            item[1].alpha or 0,
        ),
        reverse=True,
    )
    return tags


def list_git_release_tags() -> list[str]:
    return run_git(["tag", "--list"]).splitlines()


def list_github_release_tags(repo: str | None) -> list[str]:
    if not repo:
        return []

    completed = subprocess.run(
        ["gh", "release", "list", "--repo", repo, "--limit", "100", "--json", "tagName"],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        fail(f"Unable to query GitHub releases for {repo}: {completed.stderr.strip() or completed.stdout.strip() or 'gh release list failed'}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        fail(f"Unable to parse GitHub release metadata for {repo}.")

    return [item["tagName"] for item in payload if isinstance(item, dict) and isinstance(item.get("tagName"), str)]


def list_release_tags(prefixes: list[str], repo: str | None) -> list[tuple[str, Version]]:
    raw_identifiers = list_git_release_tags() if not repo else []
    raw_identifiers.extend(list_github_release_tags(repo))
    return parse_release_identifiers(raw_identifiers, prefixes)



def main() -> None:
    parser = argparse.ArgumentParser(description="Compute the next MoltenVK alpha release version for a specific upstream stable release.")
    parser.add_argument("--base-version", required=True, help="Stable upstream version such as 1.2.3.")
    parser.add_argument(
        "--tag-prefix",
        action="append",
        default=[],
        help="Additional historical release-tag prefixes to scan alongside plain SemVer tags.",
    )
    parser.add_argument("--repo", default="", help="Optional GitHub repository in owner/name form to include existing releases in alpha version discovery.")
    args = parser.parse_args()

    base_version = parse_version(args.base_version)
    if base_version.is_alpha:
        fail(f"Base version must be stable, got pre-release: {base_version}")

    release_tags = list_release_tags(normalize_prefixes([*DEFAULT_TAG_PREFIXES, *args.tag_prefix]), args.repo or None)
    matching_versions = [version for _, version in release_tags if version.core == base_version]

    if any(not version.is_alpha for version in matching_versions):
        fail(f"Stable release already exists for upstream version {base_version}; refusing to mint another alpha release.")

    next_alpha = max((version.alpha or 0) for version in matching_versions) + 1 if matching_versions else 1
    next_version = base_version.with_alpha(next_alpha)

    print(str(next_version))


if __name__ == "__main__":
    main()
