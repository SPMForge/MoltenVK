#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"
TARGET_VERSION="${1:-}"
RELEASE_KIND="${2:-}"
RELEASE_ACTION="${MVK_RELEASE_ACTION:-}"
PUBLISH_TO_DEFAULT_BRANCH="${MVK_PUBLISH_TO_DEFAULT_BRANCH:-false}"
DEFAULT_BRANCH="${MVK_DEFAULT_BRANCH:-main}"
PREPARED_WORKSPACE_ROOT=""

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

[[ -n "$TARGET_VERSION" ]] || fail "Missing release version argument."
[[ "$RELEASE_KIND" == "alpha" || "$RELEASE_KIND" == "stable" ]] || fail "Release kind must be alpha or stable."
[[ "$RELEASE_ACTION" == "create" || "$RELEASE_ACTION" == "edit" ]] || fail "MVK_RELEASE_ACTION must be create or edit."
[[ "$PUBLISH_TO_DEFAULT_BRANCH" == "true" || "$PUBLISH_TO_DEFAULT_BRANCH" == "false" ]] || fail "MVK_PUBLISH_TO_DEFAULT_BRANCH must be true or false."
[[ "$RELEASE_KIND" == "stable" || "$PUBLISH_TO_DEFAULT_BRANCH" == "false" ]] || fail "Only stable releases may update the default branch."
[[ -n "$DEFAULT_BRANCH" ]] || fail "MVK_DEFAULT_BRANCH must not be empty."
[[ -n "${GITHUB_TOKEN:-}" ]] || fail "GITHUB_TOKEN is required to publish GitHub releases."
[[ -n "${GITHUB_REPOSITORY:-}" ]] || fail "GITHUB_REPOSITORY is required to publish GitHub releases."

UPSTREAM_SOURCE_REF_FILE="$ROOT_DIR/SwiftPackage/UpstreamSourceRef.txt"
[[ -f "$UPSTREAM_SOURCE_REF_FILE" ]] || fail "Missing upstream source ref record: $UPSTREAM_SOURCE_REF_FILE"
UPSTREAM_SOURCE_REF="$(tr -d '[:space:]' <"$UPSTREAM_SOURCE_REF_FILE")"
[[ -n "$UPSTREAM_SOURCE_REF" ]] || fail "Upstream source ref record is empty: $UPSTREAM_SOURCE_REF_FILE"

release_notes() {
    local release_description
    if [[ "$RELEASE_KIND" == "alpha" ]]; then
        release_description="Automated alpha Swift Package release for MoltenVK ${TARGET_VERSION} from upstream ${UPSTREAM_SOURCE_REF}."
    else
        release_description="Manual stable Swift Package release for MoltenVK ${TARGET_VERSION} from upstream ${UPSTREAM_SOURCE_REF}."
    fi

    cat <<EOF
${release_description}

This package remains a provider framework package for MoltenVK.framework.
It does not ship a Vulkan loader dylib and does not promise libvulkan.dylib or libvulkan.1.dylib.
C/C++ Vulkan API consumers should use MoltenVKHeaders-${TARGET_VERSION}.zip extracted include/ as Vulkan_INCLUDE_DIR and link against MoltenVK.framework/MoltenVK.
EOF
}

fetch_release_refs() {
    git fetch --force origin \
        "refs/heads/${DEFAULT_BRANCH}:refs/remotes/origin/${DEFAULT_BRANCH}" \
        "refs/tags/*:refs/tags/*"
}

remote_tag_exists() {
    git ls-remote --exit-code --tags origin "refs/tags/${TARGET_VERSION}" >/dev/null 2>&1
}

create_release_tag() {
    if remote_tag_exists; then
        fail "Package tag ${TARGET_VERSION} already exists on origin."
    fi

    if ! git rev-parse -q --verify "refs/tags/${TARGET_VERSION}" >/dev/null 2>&1; then
        git tag -a "${TARGET_VERSION}" HEAD -m "${TARGET_VERSION}"
    fi

    git push origin "refs/tags/${TARGET_VERSION}:refs/tags/${TARGET_VERSION}"
}

push_default_branch() {
    local release_commit="${1:-}"
    [[ -n "$release_commit" ]] || fail "Missing release commit for default-branch update."
    git push origin "${release_commit}:refs/heads/${DEFAULT_BRANCH}"
}

resolve_release_assets_dir() {
    if [[ -n "${MVK_RELEASE_ASSETS_DIR:-}" ]]; then
        [[ -d "${MVK_RELEASE_ASSETS_DIR}" ]] || fail "Configured MVK_RELEASE_ASSETS_DIR does not exist: ${MVK_RELEASE_ASSETS_DIR}"
        printf '%s\n' "${MVK_RELEASE_ASSETS_DIR}"
        return 0
    fi

    [[ -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE" ]] || fail "Missing prepared workspace record: $MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
    PREPARED_WORKSPACE_ROOT="$(tr -d '[:space:]' <"$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE")"
    [[ -n "$PREPARED_WORKSPACE_ROOT" ]] || fail "Prepared workspace record is empty: $MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
    [[ -d "$PREPARED_WORKSPACE_ROOT" ]] || fail "Prepared workspace does not exist: $PREPARED_WORKSPACE_ROOT"
    printf '%s\n' "$PREPARED_WORKSPACE_ROOT/Artifacts"
}

publish_release_metadata() {
    local release_args=(
        "$TARGET_VERSION"
        --repo "$GITHUB_REPOSITORY"
        --title "$TARGET_VERSION"
        --notes "$(release_notes)"
    )

    if [[ "$RELEASE_ACTION" == "edit" ]]; then
        release_args+=(--draft=false)
    fi

    if [[ "$RELEASE_KIND" == "alpha" ]]; then
        release_args+=(--prerelease --latest=false)
    fi

    if [[ "$RELEASE_ACTION" == "create" ]]; then
        gh release create "${release_args[@]}" --verify-tag
    else
        gh release edit "${release_args[@]}"
    fi
}

cd "$ROOT_DIR"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
fetch_release_refs

dynamic_checksum_path="Artifacts/$(dynamic_release_checksum_name "$TARGET_VERSION")"
static_checksum_path="Artifacts/$(static_release_checksum_name "$TARGET_VERSION")"
headers_checksum_path="Artifacts/$(headers_release_checksum_name "$TARGET_VERSION")"
RELEASE_ASSETS_DIR="$(resolve_release_assets_dir)"
dynamic_zip_path="$RELEASE_ASSETS_DIR/$(dynamic_release_archive_name "$TARGET_VERSION")"
static_zip_path="$RELEASE_ASSETS_DIR/$(static_release_archive_name "$TARGET_VERSION")"
headers_zip_path="$RELEASE_ASSETS_DIR/$(headers_release_archive_name "$TARGET_VERSION")"

[[ -f "$dynamic_zip_path" ]] || fail "Missing dynamic release archive: $dynamic_zip_path"
[[ -f "$static_zip_path" ]] || fail "Missing static release archive: $static_zip_path"
[[ -f "$headers_zip_path" ]] || fail "Missing headers release archive: $headers_zip_path"
[[ -f "$dynamic_checksum_path" ]] || fail "Missing dynamic release checksum: $dynamic_checksum_path"
[[ -f "$static_checksum_path" ]] || fail "Missing static release checksum: $static_checksum_path"
[[ -f "$headers_checksum_path" ]] || fail "Missing headers release checksum: $headers_checksum_path"

release_commit=""
if [[ "$RELEASE_ACTION" == "create" ]]; then
    if remote_tag_exists; then
        git fetch --force origin "refs/tags/${TARGET_VERSION}:refs/tags/${TARGET_VERSION}"
        release_commit="$(git rev-parse "refs/tags/${TARGET_VERSION}^{commit}")"
    else
        git switch --create "release/${TARGET_VERSION}"

        git add \
            Package.swift \
            SwiftPackage/PackageVersion.txt \
            SwiftPackage/ReleaseRepository.txt \
            SwiftPackage/UpstreamRepository.txt \
            SwiftPackage/UpstreamSourceRef.txt
        git add -A Artifacts

        if git diff --cached --quiet; then
            release_commit="HEAD"
        else
            git commit -m "chore(release): MoltenVK ${TARGET_VERSION} [skip ci]"
            release_commit="HEAD"
        fi

        create_release_tag
    fi
else
    git fetch --force origin "refs/tags/${TARGET_VERSION}:refs/tags/${TARGET_VERSION}"
    release_commit="$(git rev-parse "refs/tags/${TARGET_VERSION}^{commit}")"
fi

publish_release_metadata
gh release upload "$TARGET_VERSION" \
    "$dynamic_zip_path" \
    "$dynamic_checksum_path" \
    "$static_zip_path" \
    "$static_checksum_path" \
    "$headers_zip_path" \
    "$headers_checksum_path" \
    --repo "$GITHUB_REPOSITORY" \
    --clobber

if [[ "$PUBLISH_TO_DEFAULT_BRANCH" == "true" ]]; then
    push_default_branch "$release_commit"
fi

if [[ -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE" ]]; then
    rm -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
fi

if [[ -n "$PREPARED_WORKSPACE_ROOT" && -d "$PREPARED_WORKSPACE_ROOT" ]]; then
    rm -rf "$PREPARED_WORKSPACE_ROOT"
fi
