#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIGURATION="${CONFIGURATION:-Release}"
PACKAGE_PROJECT="$ROOT_DIR/MoltenVKPackaging.xcodeproj"

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

sdk_supports_platform() {
    local sdk="$1"
    xcrun --sdk "$sdk" --show-sdk-path >/dev/null 2>&1
}

require_command xcodebuild
require_command xcrun
require_command python3
require_command git
require_command cmake

[[ -x "$ROOT_DIR/fetchDependencies" ]] || fail "Missing required script: $ROOT_DIR/fetchDependencies"
[[ -e "$PACKAGE_PROJECT" ]] || fail "Missing required path: $PACKAGE_PROJECT"

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

log "Fetching MoltenVK dependencies"
"$ROOT_DIR/fetchDependencies" "${DEPENDENCY_PLATFORMS[@]}" --keep-cache

log "Prewarmed MoltenVK dependencies for configuration $CONFIGURATION"
