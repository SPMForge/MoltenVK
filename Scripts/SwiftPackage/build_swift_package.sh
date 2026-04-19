#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"

PACKAGE_OUTPUT_DIR="$ROOT_DIR/Package/$CONFIGURATION/MoltenVK"
STATIC_SOURCE="$PACKAGE_OUTPUT_DIR/static/MoltenVK.xcframework"
STATIC_DEST="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME"
DYNAMIC_DEST="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME"
STATIC_ZIP="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME.zip"
DYNAMIC_ZIP="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.zip"
HEADERS_ZIP="$ARTIFACTS_DIR/$MOLTENVK_HEADERS_ARCHIVE_NAME"
STATIC_CHECKSUM_FILE="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME.checksum"
DYNAMIC_CHECKSUM_FILE="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.checksum"
HEADERS_CHECKSUM_FILE="$ARTIFACTS_DIR/MoltenVKHeaders.checksum"

run_packaging_build() {
    local scheme="$1"
    local destination="$2"

    xcodebuild build \
        -project "$MOLTENVK_PACKAGING_PROJECT" \
        -scheme "$scheme" \
        -configuration "$CONFIGURATION" \
        -destination "$destination" \
        GCC_PREPROCESSOR_DEFINITIONS='$inherited MVK_USE_METAL_PRIVATE_API=0'
}

require_command xcodebuild
require_command xcrun
require_command python3
require_command git
require_command cmake
require_command swift
require_command ditto

require_path "$ROOT_DIR/fetchDependencies"
require_path "$MOLTENVK_PROJECT"
require_path "$MOLTENVK_PACKAGING_PROJECT"
require_path "$MOLTENVK_INCLUDE_DIR"

parse_requested_platforms "$@"

if [[ "${SKIP_DEPENDENCY_FETCH:-0}" == "1" ]]; then
    require_path "$ROOT_DIR/External/build"
    log "Skipping MoltenVK dependency fetch because SKIP_DEPENDENCY_FETCH=1"
else
    "$ROOT_DIR/Scripts/SwiftPackage/build_swift_package_dependencies.sh" "${REQUESTED_PLATFORM_FLAGS[@]}"
fi

local_workspace=""
archives_dir=""
cleanup() {
    [[ -n "$local_workspace" ]] && rm -rf "$local_workspace"
    [[ -n "$archives_dir" ]] && rm -rf "$archives_dir"
}
trap cleanup EXIT

local_workspace="$(prepare_patched_swift_package_workspace)"
archives_dir="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-swift-package-archives.XXXXXX")"

log "Archiving mergeable MoltenVK runtime slices"
if (( BUILD_MACOS )); then
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "MoltenVK-macOS-dynamic" \
        "generic/platform=macOS" \
        "$archives_dir/macos.xcarchive"
fi

if (( BUILD_IOS )); then
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "MoltenVK-iOS-dynamic" \
        "generic/platform=iOS" \
        "$archives_dir/ios.xcarchive"
fi

if (( BUILD_IOS_SIM )); then
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "MoltenVK-iOS-dynamic" \
        "generic/platform=iOS Simulator" \
        "$archives_dir/ios-simulator.xcarchive"
fi

mkdir -p "$ARTIFACTS_DIR"
rm -rf "$DYNAMIC_DEST" "$STATIC_DEST"
rm -f "$DYNAMIC_ZIP" "$STATIC_ZIP" "$HEADERS_ZIP" "$DYNAMIC_CHECKSUM_FILE" "$STATIC_CHECKSUM_FILE" "$HEADERS_CHECKSUM_FILE"

xcframework_args=()
validator_args=()

if (( BUILD_MACOS )); then
    require_path "$archives_dir/macos.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/macos.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
    validator_args+=(--require-platform macos)
fi

if (( BUILD_IOS )); then
    require_path "$archives_dir/ios.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/ios.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
    validator_args+=(--require-platform ios)
fi

if (( BUILD_IOS_SIM )); then
    require_path "$archives_dir/ios-simulator.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/ios-simulator.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
    validator_args+=(--require-platform ios-simulator)
fi

xcodebuild -create-xcframework "${xcframework_args[@]}" -output "$DYNAMIC_DEST"
python3 /Users/snow/.codex/skills/apple-spm-binary-distribution/scripts/validate_mergeable_xcframework.py \
    "$DYNAMIC_DEST" \
    "${validator_args[@]}"

log "Building legacy static MoltenVK XCFramework slices"
if (( BUILD_MACOS )); then
    run_packaging_build "MoltenVK Package (macOS only)" "generic/platform=macOS"
fi

if (( BUILD_IOS )); then
    run_packaging_build "MoltenVK Package (iOS only)" "generic/platform=iOS"
fi

if (( BUILD_IOS_SIM )); then
    run_packaging_build "MoltenVK Package (iOS only)" "generic/platform=iOS Simulator"
fi

require_path "$STATIC_SOURCE"
cp -R "$STATIC_SOURCE" "$STATIC_DEST"

log "Packaging release artifacts"
ditto -c -k --keepParent "$DYNAMIC_DEST" "$DYNAMIC_ZIP"
ditto -c -k --keepParent "$STATIC_DEST" "$STATIC_ZIP"
ditto -c -k --keepParent "$MOLTENVK_INCLUDE_DIR" "$HEADERS_ZIP"

swift package compute-checksum "$DYNAMIC_ZIP" >"$DYNAMIC_CHECKSUM_FILE"
swift package compute-checksum "$STATIC_ZIP" >"$STATIC_CHECKSUM_FILE"
swift package compute-checksum "$HEADERS_ZIP" >"$HEADERS_CHECKSUM_FILE"

python3 "$ROOT_DIR/Scripts/SwiftPackage/render_package_manifest.py" \
    --version "$(read_package_version)" \
    --release-repository "$(read_release_repository)" \
    --checksum "$(tr -d '[:space:]' <"$DYNAMIC_CHECKSUM_FILE")" \
    --output "$ROOT_DIR/Package.swift"

swift package dump-package >/dev/null

log "Wrote $DYNAMIC_DEST"
log "Wrote $STATIC_DEST"
log "Wrote $DYNAMIC_ZIP"
log "Wrote $STATIC_ZIP"
log "Wrote $HEADERS_ZIP"
log "Rendered $ROOT_DIR/Package.swift"
