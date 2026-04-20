#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-consumer.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/Sources/SmokeConsumer"
SCHEME_NAME="SmokeConsumer-Package"

cat >"$TMP_DIR/Package.swift" <<EOF
// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "SmokeConsumer",
    platforms: [
        .iOS(.v${MOLTENVK_PACKAGE_IOS_DEPLOYMENT_TARGET}),
        .macOS(.v${MOLTENVK_PACKAGE_MACOS_DEPLOYMENT_TARGET}),
    ],
    dependencies: [
        .package(path: "$ROOT_DIR"),
    ],
    targets: [
        .target(
            name: "SmokeConsumer",
            dependencies: [
                .product(name: "MoltenVK", package: "MoltenVK"),
            ]
        ),
    ]
)
EOF

cat >"$TMP_DIR/Sources/SmokeConsumer/SmokeConsumer.swift" <<'EOF'
import MoltenVK
EOF

(
    cd "$TMP_DIR"
    xcodebuild \
        -scheme "$SCHEME_NAME" \
        -configuration Debug \
        -destination 'generic/platform=macOS' \
        -derivedDataPath "$TMP_DIR/DerivedData-Debug" \
        CODE_SIGNING_ALLOWED=NO \
        build >"$TMP_DIR/moltenvk-consumer-debug.log"
)

(
    cd "$TMP_DIR"
    xcodebuild \
        -scheme "$SCHEME_NAME" \
        -configuration Release \
        -destination 'generic/platform=macOS' \
        -derivedDataPath "$TMP_DIR/DerivedData-Release" \
        CODE_SIGNING_ALLOWED=NO \
        MERGED_BINARY_TYPE=automatic \
        build >"$TMP_DIR/moltenvk-consumer-release.log"
)

if sdk_supports_platform iphonesimulator; then
    (
        cd "$TMP_DIR"
        xcodebuild \
            -scheme "$SCHEME_NAME" \
            -configuration Debug \
            -destination 'generic/platform=iOS Simulator' \
            -derivedDataPath "$TMP_DIR/DerivedData-iOSSim-Debug" \
            CODE_SIGNING_ALLOWED=NO \
            build >"$TMP_DIR/moltenvk-consumer-iossim-debug.log"
    )

    (
        cd "$TMP_DIR"
        xcodebuild \
            -scheme "$SCHEME_NAME" \
            -configuration Release \
            -destination 'generic/platform=iOS Simulator' \
            -derivedDataPath "$TMP_DIR/DerivedData-iOSSim-Release" \
            CODE_SIGNING_ALLOWED=NO \
            MERGED_BINARY_TYPE=automatic \
            build >"$TMP_DIR/moltenvk-consumer-iossim-release.log"
    )
else
    warn "Skipping iOS Simulator consumer smoke tests because the iPhoneSimulator SDK is not installed."
fi

echo "MoltenVK Swift package consumer smoke tests verified"
