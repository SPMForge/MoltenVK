#!/bin/bash

set -euo pipefail

ROOT_DIR="${MVK_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
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

LOCAL_PACKAGE_ROOT="$TMP_DIR/LocalMoltenVKPackage"
mkdir -p "$TMP_DIR/Sources/SmokeConsumer" "$LOCAL_PACKAGE_ROOT/Artifacts"
cp -R "$ROOT_DIR/Artifacts/MoltenVK.xcframework" "$LOCAL_PACKAGE_ROOT/Artifacts/MoltenVK.xcframework"
python3 "$ROOT_DIR/Scripts/SwiftPackage/render_local_dev_package_manifest.py" \
    --output "$LOCAL_PACKAGE_ROOT/Package.swift"

SCHEME_NAME="SmokeConsumer-Package"
PLATFORM_LINES="$(
    python3 - "$ROOT_DIR/Scripts/SwiftPackage/platform_config.py" <<'PY'
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("platform_config", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load platform_config module from {script_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

config = module.load_platform_config()
for swiftpm_platform, deployment_target in module.manifest_platform_entries(config):
    print(f"        .{swiftpm_platform}(.v{deployment_target}),")
PY
)"

cat >"$TMP_DIR/Package.swift" <<EOF
// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "SmokeConsumer",
    platforms: [
${PLATFORM_LINES}
    ],
    dependencies: [
        .package(path: "$LOCAL_PACKAGE_ROOT"),
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
