#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"

DYNAMIC_XCFRAMEWORK="$ROOT_DIR/Artifacts/$MOLTENVK_DYNAMIC_ARTIFACT_NAME"
DYNAMIC_ZIP="$ROOT_DIR/Artifacts/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.zip"
DYNAMIC_CHECKSUM="$ROOT_DIR/Artifacts/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.checksum"
STATIC_XCFRAMEWORK="$ROOT_DIR/Artifacts/$MOLTENVK_STATIC_ARTIFACT_NAME"
STATIC_ZIP="$ROOT_DIR/Artifacts/$MOLTENVK_STATIC_ARTIFACT_NAME.zip"
STATIC_CHECKSUM="$ROOT_DIR/Artifacts/$MOLTENVK_STATIC_ARTIFACT_NAME.checksum"
HEADERS_ZIP="$ROOT_DIR/Artifacts/$MOLTENVK_HEADERS_ARCHIVE_NAME"
HEADERS_CHECKSUM="$ROOT_DIR/Artifacts/$MOLTENVK_HEADERS_CHECKSUM_NAME"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-artifacts.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

assert_dir() {
    [[ -d "$1" ]] || { echo "missing directory: $1" >&2; exit 1; }
}

assert_file() {
    [[ -f "$1" ]] || { echo "missing file: $1" >&2; exit 1; }
}

assert_dir "$DYNAMIC_XCFRAMEWORK"
assert_dir "$STATIC_XCFRAMEWORK"
assert_file "$DYNAMIC_ZIP"
assert_file "$DYNAMIC_CHECKSUM"
assert_file "$STATIC_ZIP"
assert_file "$STATIC_CHECKSUM"
assert_file "$HEADERS_ZIP"
assert_file "$HEADERS_CHECKSUM"
assert_file "$ROOT_DIR/Package.swift"
assert_file "$MOLTENVK_MERGEABLE_VALIDATOR_PATH"

swift package compute-checksum "$DYNAMIC_ZIP" >"$TMP_DIR/moltenvk.dynamic.checksum"
diff -u "$DYNAMIC_CHECKSUM" "$TMP_DIR/moltenvk.dynamic.checksum"
swift package compute-checksum "$STATIC_ZIP" >"$TMP_DIR/moltenvk.static.checksum"
diff -u "$STATIC_CHECKSUM" "$TMP_DIR/moltenvk.static.checksum"
swift package compute-checksum "$HEADERS_ZIP" >"$TMP_DIR/moltenvk.headers.checksum"
diff -u "$HEADERS_CHECKSUM" "$TMP_DIR/moltenvk.headers.checksum"

plutil -p "$DYNAMIC_XCFRAMEWORK/Info.plist" >/dev/null
python3 "$MOLTENVK_MERGEABLE_VALIDATOR_PATH" \
    "$DYNAMIC_XCFRAMEWORK" \
    --require-platform macos \
    --require-platform ios \
    --require-platform ios-simulator

swift package dump-package >/dev/null

echo "MoltenVK Swift package artifacts verified"
