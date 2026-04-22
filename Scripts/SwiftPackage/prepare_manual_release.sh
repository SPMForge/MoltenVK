#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"
TARGET_VERSION="${1:-}"
SEMVER_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+$'

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

parse_release_repository() {
    local remote_url="$1"
    local repository="$remote_url"

    repository="${repository#git@github.com:}"
    repository="${repository#https://github.com/}"
    repository="${repository#ssh://git@github.com/}"
    repository="${repository%.git}"

    [[ "$repository" =~ ^[^/]+/[^/]+$ ]] || fail "Unable to derive GitHub repository from origin remote: $remote_url"
    printf '%s\n' "$repository"
}

[[ -n "$TARGET_VERSION" ]] || fail "Missing target stable version argument."
[[ "$TARGET_VERSION" =~ $SEMVER_PATTERN ]] || fail "Invalid stable version: $TARGET_VERSION"

if [[ -z "${MVK_UPSTREAM_REF:-}" ]]; then
    MVK_UPSTREAM_REF="v${TARGET_VERSION}"
    export MVK_UPSTREAM_REF
fi

release_repository="$(parse_release_repository "$(git remote get-url origin)")"
printf '%s\n' "$release_repository" > "$ROOT_DIR/SwiftPackage/ReleaseRepository.txt"
printf '%s\n' "$TARGET_VERSION" > "$ROOT_DIR/SwiftPackage/PackageVersion.txt"

cd "$ROOT_DIR"
rm -f "$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
MVK_PREPARED_WORKSPACE_RECORD="$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE" \
SKIP_DEPENDENCY_FETCH="${SKIP_DEPENDENCY_FETCH:-1}" \
./Scripts/SwiftPackage/build_swift_package.sh

prepared_workspace="$(tr -d '[:space:]' <"$MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE")"
[[ -n "$prepared_workspace" ]] || fail "Prepared workspace record is empty: $MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE"
[[ -d "$prepared_workspace" ]] || fail "Prepared workspace does not exist: $prepared_workspace"

(cd "$prepared_workspace" && swift package dump-package >/dev/null)
MVK_PACKAGE_ROOT="$prepared_workspace" ./tests/verify_swift_package_artifacts.sh
MVK_PACKAGE_ROOT="$prepared_workspace" ./tests/verify_swift_package_consumer.sh

mkdir -p "$ROOT_DIR/Artifacts"
cp "$prepared_workspace/Package.swift" "$ROOT_DIR/Package.swift"
for relative_path in PackageVersion.txt ReleaseRepository.txt UpstreamRepository.txt UpstreamSourceRef.txt; do
    cp "$prepared_workspace/SwiftPackage/$relative_path" "$ROOT_DIR/SwiftPackage/$relative_path"
done
find "$ROOT_DIR/Artifacts" -maxdepth 1 -name 'MoltenVK*.checksum' -delete
find "$prepared_workspace/Artifacts" -maxdepth 1 -name 'MoltenVK*.checksum' -exec cp {} "$ROOT_DIR/Artifacts/" \;
