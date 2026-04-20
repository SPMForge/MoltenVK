#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
source "$(cd "$(dirname "$0")" && pwd)/source_acquisition.sh"

PACKAGE_OUTPUT_DIR="$ROOT_DIR/Package/$CONFIGURATION/MoltenVK"
STATIC_SOURCE="$PACKAGE_OUTPUT_DIR/static/MoltenVK.xcframework"
STATIC_DEST="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME"
DYNAMIC_DEST="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME"
STATIC_ZIP="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME.zip"
DYNAMIC_ZIP="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.zip"
HEADERS_ZIP="$ARTIFACTS_DIR/$MOLTENVK_HEADERS_ARCHIVE_NAME"
STATIC_CHECKSUM_FILE="$ARTIFACTS_DIR/$MOLTENVK_STATIC_ARTIFACT_NAME.checksum"
DYNAMIC_CHECKSUM_FILE="$ARTIFACTS_DIR/$MOLTENVK_DYNAMIC_ARTIFACT_NAME.checksum"
HEADERS_CHECKSUM_FILE="$ARTIFACTS_DIR/$MOLTENVK_HEADERS_CHECKSUM_NAME"

if [[ "${MVK_SOURCE_MODE:-upstream-snapshot}" == "upstream-snapshot" && "${MVK_SOURCE_WORKSPACE_ACTIVE:-0}" != "1" ]]; then
    workspace_info="$(prepare_upstream_wrapper_workspace "${MVK_UPSTREAM_REF:-}")"
    workspace_root="$(printf '%s\n' "$workspace_info" | sed -n '1p')"
    resolved_upstream_ref="$(printf '%s\n' "$workspace_info" | sed -n '2p')"

    cleanup_upstream_workspace() {
        [[ -n "${workspace_root:-}" ]] && rm -rf "$workspace_root"
    }
    trap cleanup_upstream_workspace EXIT

    (
        cd "$workspace_root"
        MVK_SOURCE_MODE=upstream-snapshot \
        MVK_SOURCE_WORKSPACE_ACTIVE=1 \
        MVK_UPSTREAM_REF="$resolved_upstream_ref" \
        MVK_WRAPPER_ROOT="$ROOT_DIR" \
        ./Scripts/SwiftPackage/build_swift_package.sh "$@"
    )

    sync_workspace_outputs_back "$workspace_root" "$ROOT_DIR"
    log "Built MoltenVK Swift package artifacts from upstream snapshot $resolved_upstream_ref"
    exit 0
fi

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

scheme_exists() {
    local project_path="$1"
    local scheme="$2"

    xcodebuild -list -project "$project_path" 2>/dev/null | grep -Fq "        $scheme"
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
require_path "$MOLTENVK_MERGEABLE_VALIDATOR_PATH"

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
    macos_dynamic_scheme="MoltenVK-macOS-dynamic"
    if ! scheme_exists "$local_workspace/MoltenVK/MoltenVK.xcodeproj" "$macos_dynamic_scheme"; then
        macos_dynamic_scheme="MoltenVK-macOS"
    fi
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "$macos_dynamic_scheme" \
        "generic/platform=macOS" \
        "$archives_dir/macos.xcarchive"
fi

if (( BUILD_IOS )); then
    ios_dynamic_scheme="MoltenVK-iOS-dynamic"
    if ! scheme_exists "$local_workspace/MoltenVK/MoltenVK.xcodeproj" "$ios_dynamic_scheme"; then
        ios_dynamic_scheme="MoltenVK-iOS"
    fi
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "$ios_dynamic_scheme" \
        "generic/platform=iOS" \
        "$archives_dir/ios.xcarchive"
fi

if (( BUILD_IOS_SIM )); then
    ios_sim_dynamic_scheme="MoltenVK-iOS-dynamic"
    if ! scheme_exists "$local_workspace/MoltenVK/MoltenVK.xcodeproj" "$ios_sim_dynamic_scheme"; then
        ios_sim_dynamic_scheme="MoltenVK-iOS"
    fi
    archive_dynamic_framework \
        "$local_workspace/MoltenVK/MoltenVK.xcodeproj" \
        "$ios_sim_dynamic_scheme" \
        "generic/platform=iOS Simulator" \
        "$archives_dir/ios-simulator.xcarchive"
fi

mkdir -p "$ARTIFACTS_DIR"
rm -rf "$DYNAMIC_DEST" "$STATIC_DEST"
rm -f "$DYNAMIC_ZIP" "$STATIC_ZIP" "$HEADERS_ZIP" "$DYNAMIC_CHECKSUM_FILE" "$STATIC_CHECKSUM_FILE" "$HEADERS_CHECKSUM_FILE"

xcframework_args=()
validator_args=()
while IFS= read -r validator_arg; do
    [[ -n "$validator_arg" ]] && validator_args+=("$validator_arg")
done < <(dynamic_validator_args)

if (( BUILD_MACOS )); then
    require_path "$archives_dir/macos.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/macos.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
fi

if (( BUILD_IOS )); then
    require_path "$archives_dir/ios.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/ios.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
fi

if (( BUILD_IOS_SIM )); then
    require_path "$archives_dir/ios-simulator.xcarchive/Products/Library/Frameworks/MoltenVK.framework"
    xcframework_args+=(-framework "$archives_dir/ios-simulator.xcarchive/Products/Library/Frameworks/MoltenVK.framework")
fi

xcodebuild -create-xcframework "${xcframework_args[@]}" -output "$DYNAMIC_DEST"
python3 "$MOLTENVK_MERGEABLE_VALIDATOR_PATH" \
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
    --ios-deployment-target "$MOLTENVK_PACKAGE_IOS_DEPLOYMENT_TARGET" \
    --macos-deployment-target "$MOLTENVK_PACKAGE_MACOS_DEPLOYMENT_TARGET" \
    --output "$ROOT_DIR/Package.swift"

swift package dump-package >/dev/null

log "Wrote $DYNAMIC_DEST"
log "Wrote $STATIC_DEST"
log "Wrote $DYNAMIC_ZIP"
log "Wrote $STATIC_ZIP"
log "Wrote $HEADERS_ZIP"
log "Rendered $ROOT_DIR/Package.swift"
