#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET_VERSION="${1:-}"
RELEASE_KIND="${2:-}"

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

[[ -n "$TARGET_VERSION" ]] || fail "Missing release version argument."
[[ "$RELEASE_KIND" == "alpha" || "$RELEASE_KIND" == "stable" ]] || fail "Release kind must be alpha or stable."
[[ -n "${GITHUB_TOKEN:-}" ]] || fail "GITHUB_TOKEN is required to publish GitHub releases."

UPSTREAM_SOURCE_REF_FILE="$ROOT_DIR/SwiftPackage/UpstreamSourceRef.txt"
[[ -f "$UPSTREAM_SOURCE_REF_FILE" ]] || fail "Missing upstream source ref record: $UPSTREAM_SOURCE_REF_FILE"
UPSTREAM_SOURCE_REF="$(tr -d '[:space:]' <"$UPSTREAM_SOURCE_REF_FILE")"
[[ -n "$UPSTREAM_SOURCE_REF" ]] || fail "Upstream source ref record is empty: $UPSTREAM_SOURCE_REF_FILE"

cd "$ROOT_DIR"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add \
    Package.swift \
    SwiftPackage/PackageVersion.txt \
    SwiftPackage/ReleaseRepository.txt \
    SwiftPackage/UpstreamRepository.txt \
    SwiftPackage/UpstreamSourceRef.txt \
    Artifacts/MoltenVK.xcframework.checksum \
    Artifacts/MoltenVK-static.xcframework.checksum \
    Artifacts/MoltenVKHeaders.checksum

if git diff --cached --quiet; then
    if [[ "$RELEASE_KIND" == "alpha" ]]; then
        fail "Alpha release preparation did not produce any metadata changes."
    fi
else
    git commit -m "chore(release): MoltenVK ${TARGET_VERSION} [skip ci]"
    git push origin HEAD:main
fi

git fetch origin main
git checkout origin/main
git tag -a "${TARGET_VERSION}" -m "${TARGET_VERSION}"
git push origin "${TARGET_VERSION}"

release_args=(
    "${TARGET_VERSION}"
    Artifacts/MoltenVK.xcframework.zip
    Artifacts/MoltenVK.xcframework.checksum
    Artifacts/MoltenVK-static.xcframework.zip
    Artifacts/MoltenVK-static.xcframework.checksum
    Artifacts/MoltenVKHeaders.zip
    Artifacts/MoltenVKHeaders.checksum
    --repo "$GITHUB_REPOSITORY"
    --title "${TARGET_VERSION}"
)

if [[ "$RELEASE_KIND" == "alpha" ]]; then
    release_args+=(--prerelease --notes "Automated alpha Swift Package release for MoltenVK ${TARGET_VERSION} from upstream ${UPSTREAM_SOURCE_REF}.")
else
    release_args+=(--notes "Manual stable Swift Package release for MoltenVK ${TARGET_VERSION} from upstream ${UPSTREAM_SOURCE_REF}.")
fi

gh release create "${release_args[@]}"
