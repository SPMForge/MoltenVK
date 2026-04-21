#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/Scripts/SwiftPackage/common.sh"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-consumer.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

run_consumer_builds_for_platform() {
    local platform_id="$1"
    local destination
    local debug_derived_data
    local release_derived_data
    local debug_log
    local release_log

    destination="$(platform_destination_for_id "$platform_id")"
    debug_derived_data="$TMP_DIR/DerivedData-${platform_id}-Debug"
    release_derived_data="$TMP_DIR/DerivedData-${platform_id}-Release"
    debug_log="$TMP_DIR/moltenvk-consumer-${platform_id}-debug.log"
    release_log="$TMP_DIR/moltenvk-consumer-${platform_id}-release.log"

    if ! sdk_supports_platform "$(platform_sdk_for_id "$platform_id")"; then
        warn "Skipping ${platform_id} consumer smoke tests because the $(platform_sdk_for_id "$platform_id") SDK is not installed."
        return
    fi

    (
        cd "$TMP_DIR"
        xcodebuild \
            -scheme "$SCHEME_NAME" \
            -configuration Debug \
            -destination "$destination" \
            -derivedDataPath "$debug_derived_data" \
            CODE_SIGNING_ALLOWED=NO \
            build >"$debug_log"
    )

    (
        cd "$TMP_DIR"
        xcodebuild \
            -scheme "$SCHEME_NAME" \
            -configuration Release \
            -destination "$destination" \
            -derivedDataPath "$release_derived_data" \
            CODE_SIGNING_ALLOWED=NO \
            MERGED_BINARY_TYPE=automatic \
            build >"$release_log"
    )
}

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

while IFS= read -r platform_id; do
    [[ -n "$platform_id" ]] || continue
    run_consumer_builds_for_platform "$platform_id"
done < <(consumer_test_platform_ids)

echo "MoltenVK Swift package consumer smoke tests verified"
