#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-consumer.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/Sources/SmokeConsumer"

cat >"$TMP_DIR/Package.swift" <<EOF
// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "SmokeConsumer",
    platforms: [
        .macOS(.v11),
    ],
    dependencies: [
        .package(path: "$ROOT_DIR"),
    ],
    targets: [
        .executableTarget(
            name: "SmokeConsumer",
            dependencies: [
                .product(name: "MoltenVK", package: "MoltenVK"),
            ]
        ),
    ]
)
EOF

cat >"$TMP_DIR/Sources/SmokeConsumer/main.swift" <<'EOF'
import MoltenVK

print("MoltenVK consumer smoke test")
EOF

(
    cd "$TMP_DIR"
    xcodebuild \
        -scheme SmokeConsumer \
        -configuration Debug \
        -destination 'generic/platform=macOS' \
        -derivedDataPath "$TMP_DIR/DerivedData-Debug" \
        CODE_SIGNING_ALLOWED=NO \
        build >/tmp/moltenvk-consumer-debug.log
)

(
    cd "$TMP_DIR"
    xcodebuild \
        -scheme SmokeConsumer \
        -configuration Release \
        -destination 'generic/platform=macOS' \
        -derivedDataPath "$TMP_DIR/DerivedData-Release" \
        CODE_SIGNING_ALLOWED=NO \
        MERGED_BINARY_TYPE=automatic \
        build >/tmp/moltenvk-consumer-release.log
)

echo "MoltenVK Swift package consumer smoke tests verified"

