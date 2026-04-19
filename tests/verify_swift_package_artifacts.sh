#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DYNAMIC_XCFRAMEWORK="$ROOT_DIR/Artifacts/MoltenVK.xcframework"
DYNAMIC_ZIP="$ROOT_DIR/Artifacts/MoltenVK.xcframework.zip"
DYNAMIC_CHECKSUM="$ROOT_DIR/Artifacts/MoltenVK.xcframework.checksum"
STATIC_XCFRAMEWORK="$ROOT_DIR/Artifacts/MoltenVK-static.xcframework"
STATIC_ZIP="$ROOT_DIR/Artifacts/MoltenVK-static.xcframework.zip"
STATIC_CHECKSUM="$ROOT_DIR/Artifacts/MoltenVK-static.xcframework.checksum"
HEADERS_ZIP="$ROOT_DIR/Artifacts/MoltenVKHeaders.zip"
HEADERS_CHECKSUM="$ROOT_DIR/Artifacts/MoltenVKHeaders.checksum"
VALIDATOR="/Users/snow/.codex/skills/apple-spm-binary-distribution/scripts/validate_mergeable_xcframework.py"

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

swift package compute-checksum "$DYNAMIC_ZIP" >/tmp/moltenvk.dynamic.checksum
diff -u "$DYNAMIC_CHECKSUM" /tmp/moltenvk.dynamic.checksum
swift package compute-checksum "$STATIC_ZIP" >/tmp/moltenvk.static.checksum
diff -u "$STATIC_CHECKSUM" /tmp/moltenvk.static.checksum
swift package compute-checksum "$HEADERS_ZIP" >/tmp/moltenvk.headers.checksum
diff -u "$HEADERS_CHECKSUM" /tmp/moltenvk.headers.checksum

plutil -p "$DYNAMIC_XCFRAMEWORK/Info.plist" >/dev/null
python3 "$VALIDATOR" \
    "$DYNAMIC_XCFRAMEWORK" \
    --require-platform macos \
    --require-platform ios \
    --require-platform ios-simulator

swift package dump-package >/dev/null

echo "MoltenVK Swift package artifacts verified"

