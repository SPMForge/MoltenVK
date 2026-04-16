#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARTIFACTS_DIR="$ROOT_DIR/Artifacts"
CONFIGURATION="${CONFIGURATION:-Release}"
PACKAGE_PROJECT="$ROOT_DIR/MoltenVKPackaging.xcodeproj"
PACKAGE_DIR="$ROOT_DIR/Package/$CONFIGURATION/MoltenVK"
STATIC_SOURCE="$PACKAGE_DIR/static/MoltenVK.xcframework"
DYNAMIC_SOURCE="$PACKAGE_DIR/dynamic/MoltenVK.xcframework"
HEADERS_SOURCE="$ROOT_DIR/MoltenVK/include"
STATIC_DEST="$ARTIFACTS_DIR/MoltenVK-static.xcframework"
DYNAMIC_DEST="$ARTIFACTS_DIR/MoltenVK.xcframework"
STATIC_ZIP="$ARTIFACTS_DIR/MoltenVK-static.xcframework.zip"
DYNAMIC_ZIP="$ARTIFACTS_DIR/MoltenVK.xcframework.zip"
HEADERS_ZIP="$ARTIFACTS_DIR/MoltenVKHeaders.zip"
STATIC_CHECKSUM_FILE="$ARTIFACTS_DIR/MoltenVK-static.xcframework.checksum"
DYNAMIC_CHECKSUM_FILE="$ARTIFACTS_DIR/MoltenVK.xcframework.checksum"
HEADERS_CHECKSUM_FILE="$ARTIFACTS_DIR/MoltenVKHeaders.checksum"

DEPENDENCY_PLATFORMS=("$@")
BUILD_MACOS=0
BUILD_IOS=0
BUILD_IOS_SIM=0

log() {
    printf '==> %s\n' "$1"
}

warn() {
    printf 'warning: %s\n' "$1" >&2
}

fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_path() {
    [[ -e "$1" ]] || fail "Missing required path: $1"
}

sdk_supports_platform() {
    local sdk="$1"
    xcrun --sdk "$sdk" --show-sdk-path >/dev/null 2>&1
}

run_package_build() {
    local scheme="$1"
    local destination="$2"

    xcodebuild build \
        -project "$PACKAGE_PROJECT" \
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

require_path "$ROOT_DIR/fetchDependencies"
require_path "$PACKAGE_PROJECT"

if [[ ${#DEPENDENCY_PLATFORMS[@]} -eq 0 ]]; then
    BUILD_MACOS=1
    DEPENDENCY_PLATFORMS=(--macos)

    if sdk_supports_platform iphoneos; then
        BUILD_IOS=1
        DEPENDENCY_PLATFORMS+=(--ios)
    else
        warn "Skipping iOS device slice because the iPhoneOS SDK is not installed in this Xcode installation."
    fi

    if sdk_supports_platform iphonesimulator; then
        BUILD_IOS_SIM=1
        DEPENDENCY_PLATFORMS+=(--iossim)
    else
        warn "Skipping iOS simulator slice because the iPhoneSimulator SDK is not installed in this Xcode installation."
    fi
else
    for platform in "${DEPENDENCY_PLATFORMS[@]}"; do
        case "$platform" in
            --all)
                BUILD_MACOS=1
                BUILD_IOS=1
                BUILD_IOS_SIM=1
                ;;
            --macos)
                BUILD_MACOS=1
                ;;
            --ios)
                BUILD_IOS=1
                ;;
            --iossim)
                BUILD_IOS_SIM=1
                ;;
        esac
    done

    (( BUILD_MACOS )) || fail "No supported Apple platform was requested. Use --macos, --ios, --iossim, or --all."

    if (( BUILD_IOS )) && ! sdk_supports_platform iphoneos; then
        fail "Requested --ios, but the iPhoneOS SDK is not installed."
    fi

    if (( BUILD_IOS_SIM )) && ! sdk_supports_platform iphonesimulator; then
        fail "Requested --iossim, but the iPhoneSimulator SDK is not installed."
    fi
fi

if [[ "${SKIP_DEPENDENCY_FETCH:-0}" == "1" ]]; then
    require_path "$ROOT_DIR/External/build"
    log "Skipping MoltenVK dependency fetch because SKIP_DEPENDENCY_FETCH=1"
else
    log "Fetching MoltenVK dependencies"
    "$ROOT_DIR/fetchDependencies" "${DEPENDENCY_PLATFORMS[@]}" --keep-cache
fi

log "Building MoltenVK package slices"
if (( BUILD_MACOS )); then
    run_package_build "MoltenVK Package (macOS only)" "generic/platform=macOS"
fi

if (( BUILD_IOS )); then
    run_package_build "MoltenVK Package (iOS only)" "generic/platform=iOS"
fi

if (( BUILD_IOS_SIM )); then
    run_package_build "MoltenVK Package (iOS only)" "generic/platform=iOS Simulator"
fi

require_path "$STATIC_SOURCE"
require_path "$DYNAMIC_SOURCE"
require_path "$HEADERS_SOURCE"

mkdir -p "$ARTIFACTS_DIR"
rm -rf "$STATIC_DEST" "$DYNAMIC_DEST"
cp -R "$STATIC_SOURCE" "$STATIC_DEST"
cp -R "$DYNAMIC_SOURCE" "$DYNAMIC_DEST"

log "Packaging SPM download artifact"
rm -f "$STATIC_ZIP" "$DYNAMIC_ZIP" "$HEADERS_ZIP" "$STATIC_CHECKSUM_FILE" "$DYNAMIC_CHECKSUM_FILE" "$HEADERS_CHECKSUM_FILE"
ditto -c -k --keepParent "$STATIC_DEST" "$STATIC_ZIP"
ditto -c -k --keepParent "$DYNAMIC_DEST" "$DYNAMIC_ZIP"
ditto -c -k --keepParent "$HEADERS_SOURCE" "$HEADERS_ZIP"
swift package compute-checksum "$STATIC_ZIP" > "$STATIC_CHECKSUM_FILE"
swift package compute-checksum "$DYNAMIC_ZIP" > "$DYNAMIC_CHECKSUM_FILE"
swift package compute-checksum "$HEADERS_ZIP" > "$HEADERS_CHECKSUM_FILE"

log "Wrote $STATIC_DEST"
log "Wrote $DYNAMIC_DEST"
log "Wrote $STATIC_ZIP"
log "Wrote $DYNAMIC_ZIP"
log "Wrote $HEADERS_ZIP"
log "Wrote $STATIC_CHECKSUM_FILE"
log "Wrote $DYNAMIC_CHECKSUM_FILE"
log "Wrote $HEADERS_CHECKSUM_FILE"
