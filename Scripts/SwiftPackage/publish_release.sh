#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"
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
[[ -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE" ]] || fail "Missing prepared workspace record: $MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
PREPARED_WORKSPACE_ROOT="$(tr -d '[:space:]' <"$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE")"
[[ -n "$PREPARED_WORKSPACE_ROOT" ]] || fail "Prepared workspace record is empty: $MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
[[ -d "$PREPARED_WORKSPACE_ROOT" ]] || fail "Prepared workspace does not exist: $PREPARED_WORKSPACE_ROOT"

release_notes() {
    if [[ "$RELEASE_KIND" == "alpha" ]]; then
        printf 'Automated alpha Swift Package release for MoltenVK %s from upstream %s.\n' "$TARGET_VERSION" "$UPSTREAM_SOURCE_REF"
    else
        printf 'Manual stable Swift Package release for MoltenVK %s from upstream %s.\n' "$TARGET_VERSION" "$UPSTREAM_SOURCE_REF"
    fi
}

release_exists() {
    gh release view "$TARGET_VERSION" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1
}

ensure_release_tag() {
    git fetch --force origin \
        "refs/heads/main:refs/remotes/origin/main" \
        "refs/tags/*:refs/tags/*"
    if git ls-remote --exit-code --tags origin "refs/tags/${TARGET_VERSION}" >/dev/null 2>&1; then
        return 0
    fi

    if ! git rev-parse -q --verify "refs/tags/${TARGET_VERSION}" >/dev/null 2>&1; then
        git tag -a "${TARGET_VERSION}" "refs/remotes/origin/main" -m "${TARGET_VERSION}"
    fi

    git push origin "refs/tags/${TARGET_VERSION}:refs/tags/${TARGET_VERSION}"
}

normalize_release_metadata() {
    local release_edit_args=(
        "$TARGET_VERSION"
        --repo "$GITHUB_REPOSITORY"
        --title "$TARGET_VERSION"
        --notes "$(release_notes)"
        --draft=false
    )
    local release_create_args=(
        "$TARGET_VERSION"
        --repo "$GITHUB_REPOSITORY"
        --title "$TARGET_VERSION"
        --notes "$(release_notes)"
    )

    if [[ "$RELEASE_KIND" == "alpha" ]]; then
        release_edit_args+=(--prerelease --latest=false)
        release_create_args+=(--prerelease --latest=false)
    fi

    if release_exists; then
        gh release edit "${release_edit_args[@]}"
    else
        gh release create "${release_create_args[@]}" --verify-tag
    fi
}

cd "$ROOT_DIR"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

dynamic_checksum_path="Artifacts/$(dynamic_release_checksum_name "$TARGET_VERSION")"
static_checksum_path="Artifacts/$(static_release_checksum_name "$TARGET_VERSION")"
headers_checksum_path="Artifacts/$(headers_release_checksum_name "$TARGET_VERSION")"
dynamic_zip_path="$PREPARED_WORKSPACE_ROOT/Artifacts/$(dynamic_release_archive_name "$TARGET_VERSION")"
static_zip_path="$PREPARED_WORKSPACE_ROOT/Artifacts/$(static_release_archive_name "$TARGET_VERSION")"
headers_zip_path="$PREPARED_WORKSPACE_ROOT/Artifacts/$(headers_release_archive_name "$TARGET_VERSION")"

git add \
    Package.swift \
    SwiftPackage/PackageVersion.txt \
    SwiftPackage/ReleaseRepository.txt \
    SwiftPackage/UpstreamRepository.txt \
    SwiftPackage/UpstreamSourceRef.txt
git add -A Artifacts

if git diff --cached --quiet; then
    :
else
    git commit -m "chore(release): MoltenVK ${TARGET_VERSION} [skip ci]"
    git push origin HEAD:main
fi

ensure_release_tag
normalize_release_metadata
gh release upload "$TARGET_VERSION" \
    "$dynamic_zip_path" \
    "$dynamic_checksum_path" \
    "$static_zip_path" \
    "$static_checksum_path" \
    "$headers_zip_path" \
    "$headers_checksum_path" \
    --repo "$GITHUB_REPOSITORY" \
    --clobber
rm -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
rm -rf "$PREPARED_WORKSPACE_ROOT"
