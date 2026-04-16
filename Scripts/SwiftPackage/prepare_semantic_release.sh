#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
NEXT_VERSION="${1:-}"
SEMVER_PATTERN='^[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$'

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

[[ -n "$NEXT_VERSION" ]] || fail "Missing next semantic-release version argument."
[[ "$NEXT_VERSION" =~ $SEMVER_PATTERN ]] || fail "Invalid semantic-release version: $NEXT_VERSION"

printf '%s\n' "$NEXT_VERSION" > "$ROOT_DIR/SwiftPackage/PackageVersion.txt"

cd "$ROOT_DIR"
./Scripts/SwiftPackage/build_swift_package.sh
swift package describe >/dev/null
