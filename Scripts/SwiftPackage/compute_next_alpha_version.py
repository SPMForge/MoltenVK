#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass


VERSION_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-alpha\.(?P<alpha>\d+))?$")


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
    groups = match.groupdict()
    alpha = groups["alpha"]
    return Version(
        major=int(groups["major"]),
        minor=int(groups["minor"]),
        patch=int(groups["patch"]),
        alpha=int(alpha) if alpha is not None else None,
    )


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def list_release_tags(prefix: str) -> list[tuple[str, Version]]:
    tags: list[tuple[str, Version]] = []
    for raw_tag in run_git(["tag", "--list", f"{prefix}*"]).splitlines():
        version_text = raw_tag.removeprefix(prefix)
        try:
            parsed = parse_version(version_text)
        except SystemExit:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute the next MoltenVK alpha release version for a specific upstream stable release.")
    parser.add_argument("--base-version", required=True, help="Stable upstream version such as 1.2.3.")
    parser.add_argument("--tag-prefix", default="MoltenVK-v")
    args = parser.parse_args()

    base_version = parse_version(args.base_version)
    if base_version.is_alpha:
        fail(f"Base version must be stable, got pre-release: {base_version}")

    release_tags = list_release_tags(args.tag_prefix)
    matching_versions = [version for _, version in release_tags if version.core == base_version]

    if any(not version.is_alpha for version in matching_versions):
        fail(f"Stable release already exists for upstream version {base_version}; refusing to mint another alpha release.")

    next_alpha = max((version.alpha or 0) for version in matching_versions) + 1 if matching_versions else 1
    next_version = base_version.with_alpha(next_alpha)

    print(str(next_version))


if __name__ == "__main__":
    main()
