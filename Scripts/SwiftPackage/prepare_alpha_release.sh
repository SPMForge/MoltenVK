#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
NEXT_VERSION="${1:-}"
SEMVER_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+-alpha\.[0-9]+$'

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

[[ -n "$NEXT_VERSION" ]] || fail "Missing next alpha release version argument."
[[ "$NEXT_VERSION" =~ $SEMVER_PATTERN ]] || fail "Invalid alpha release version: $NEXT_VERSION"
[[ -n "${MVK_UPSTREAM_REF:-}" ]] || fail "MVK_UPSTREAM_REF must point at the upstream source tag for alpha publishing."

release_repository="$(parse_release_repository "$(git remote get-url origin)")"
printf '%s\n' "$release_repository" > "$ROOT_DIR/SwiftPackage/ReleaseRepository.txt"
printf '%s\n' "$NEXT_VERSION" > "$ROOT_DIR/SwiftPackage/PackageVersion.txt"

cd "$ROOT_DIR"
SKIP_DEPENDENCY_FETCH="${SKIP_DEPENDENCY_FETCH:-1}" ./Scripts/SwiftPackage/build_swift_package.sh
swift package dump-package >/dev/null
./tests/verify_swift_package_artifacts.sh
./tests/verify_swift_package_consumer.sh
