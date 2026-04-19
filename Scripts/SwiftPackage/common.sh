#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACTS_DIR="$ROOT_DIR/Artifacts"
CONFIGURATION="${CONFIGURATION:-Release}"
SWIFT_PACKAGE_DIR="$ROOT_DIR/SwiftPackage"
MOLTENVK_PROJECT="$ROOT_DIR/MoltenVK/MoltenVK.xcodeproj"
MOLTENVK_PACKAGING_PROJECT="$ROOT_DIR/MoltenVKPackaging.xcodeproj"
MOLTENVK_INCLUDE_DIR="$ROOT_DIR/MoltenVK/include"
MOLTENVK_DYNAMIC_ARTIFACT_NAME="MoltenVK.xcframework"
MOLTENVK_STATIC_ARTIFACT_NAME="MoltenVK-static.xcframework"
MOLTENVK_HEADERS_ARCHIVE_NAME="MoltenVKHeaders.zip"
MOLTENVK_HEADERS_CHECKSUM_NAME="${MOLTENVK_HEADERS_ARCHIVE_NAME%.zip}.checksum"
MOLTENVK_RELEASE_TAG_PREFIX="MoltenVK-v"
MOLTENVK_RELEASE_REPOSITORY_FILE="$SWIFT_PACKAGE_DIR/ReleaseRepository.txt"
MOLTENVK_PACKAGE_VERSION_FILE="$SWIFT_PACKAGE_DIR/PackageVersion.txt"
MOLTENVK_MERGEABLE_VALIDATOR_PATH="${MVK_MERGEABLE_VALIDATOR_PATH:-$ROOT_DIR/Scripts/SwiftPackage/validate_mergeable_xcframework.py}"

BUILD_MACOS=0
BUILD_IOS=0
BUILD_IOS_SIM=0
REQUESTED_PLATFORM_FLAGS=()

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

parse_requested_platforms() {
    BUILD_MACOS=0
    BUILD_IOS=0
    BUILD_IOS_SIM=0
    REQUESTED_PLATFORM_FLAGS=()

    if [[ $# -eq 0 ]]; then
        BUILD_MACOS=1
        REQUESTED_PLATFORM_FLAGS+=(--macos)

        if sdk_supports_platform iphoneos; then
            BUILD_IOS=1
            REQUESTED_PLATFORM_FLAGS+=(--ios)
        else
            warn "Skipping iOS device slice because the iPhoneOS SDK is not installed in this Xcode installation."
        fi

        if sdk_supports_platform iphonesimulator; then
            BUILD_IOS_SIM=1
            REQUESTED_PLATFORM_FLAGS+=(--iossim)
        else
            warn "Skipping iOS simulator slice because the iPhoneSimulator SDK is not installed in this Xcode installation."
        fi

        return
    fi

    local platform
    for platform in "$@"; do
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
            *)
                fail "Unsupported platform flag: $platform"
                ;;
        esac
    done

    (( BUILD_MACOS || BUILD_IOS || BUILD_IOS_SIM )) || fail "No supported Apple platform was requested. Use --macos, --ios, --iossim, or --all."

    REQUESTED_PLATFORM_FLAGS=()
    (( BUILD_MACOS )) && REQUESTED_PLATFORM_FLAGS+=(--macos)
    (( BUILD_IOS )) && REQUESTED_PLATFORM_FLAGS+=(--ios)
    (( BUILD_IOS_SIM )) && REQUESTED_PLATFORM_FLAGS+=(--iossim)

    if (( BUILD_IOS )) && ! sdk_supports_platform iphoneos; then
        fail "Requested --ios, but the iPhoneOS SDK is not installed."
    fi

    if (( BUILD_IOS_SIM )) && ! sdk_supports_platform iphonesimulator; then
        fail "Requested --iossim, but the iPhoneSimulator SDK is not installed."
    fi
}

read_package_version() {
    if [[ -n "${MVK_PACKAGE_VERSION_OVERRIDE:-}" ]]; then
        printf '%s\n' "$MVK_PACKAGE_VERSION_OVERRIDE"
        return
    fi

    require_path "$MOLTENVK_PACKAGE_VERSION_FILE"
    local version
    version="$(tr -d '[:space:]' <"$MOLTENVK_PACKAGE_VERSION_FILE")"
    [[ -n "$version" ]] || fail "MoltenVK package version file is empty: $MOLTENVK_PACKAGE_VERSION_FILE"
    printf '%s\n' "$version"
}

read_release_repository() {
    if [[ -n "${MVK_RELEASE_REPOSITORY_OVERRIDE:-}" ]]; then
        printf '%s\n' "$MVK_RELEASE_REPOSITORY_OVERRIDE"
        return
    fi

    require_path "$MOLTENVK_RELEASE_REPOSITORY_FILE"
    local repository
    repository="$(tr -d '[:space:]' <"$MOLTENVK_RELEASE_REPOSITORY_FILE")"
    [[ -n "$repository" ]] || fail "MoltenVK release repository file is empty: $MOLTENVK_RELEASE_REPOSITORY_FILE"
    printf '%s\n' "$repository"
}

dynamic_validator_args() {
    local args=()
    (( BUILD_MACOS )) && args+=(--require-platform macos)
    (( BUILD_IOS )) && args+=(--require-platform ios)
    (( BUILD_IOS_SIM )) && args+=(--require-platform ios-simulator)
    if (( ${#args[@]} )); then
        printf '%s\n' "${args[@]}"
    fi
}

patch_macos_shader_converter_dependency() {
    local pbxproj_path="$1"

    python3 - "$pbxproj_path" <<'PY'
from pathlib import Path
import sys

pbxproj_path = Path(sys.argv[1])
text = pbxproj_path.read_text()

proxy_old = 'remoteGlobalIDString = A9092A8C1A81717B00051823;\n\t\t\tremoteInfo = MoltenVKShaderConverter;'
proxy_new = 'remoteGlobalIDString = A93903C01C57E9ED00FE90DC;\n\t\t\tremoteInfo = "MoltenVKShaderConverter-macOS";'
dependency_old = 'name = MoltenVKShaderConverter;\n\t\t\ttargetProxy = A9B1C7F4251AA5AF001D12CC'
dependency_new = 'name = "MoltenVKShaderConverter-macOS";\n\t\t\ttargetProxy = A9B1C7F4251AA5AF001D12CC'

if proxy_old not in text:
    raise SystemExit(f"Unable to find macOS shader converter proxy in {pbxproj_path}")
if dependency_old not in text:
    raise SystemExit(f"Unable to find macOS shader converter dependency in {pbxproj_path}")

text = text.replace(proxy_old, proxy_new, 1)
text = text.replace(dependency_old, dependency_new, 1)
pbxproj_path.write_text(text)
PY
}

prepare_patched_swift_package_workspace() {
    local workspace_root
    workspace_root="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-swift-package.XXXXXX")"

    python3 - "$ROOT_DIR" "$workspace_root" <<'PY'
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1])
workspace = Path(sys.argv[2])

def mirror_with_symlinks(source: Path, destination: Path, skip: set[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name in skip:
            continue
        target = destination / child.name
        target.symlink_to(child, target_is_directory=child.is_dir())

mirror_with_symlinks(root, workspace, {"MoltenVK"})

moltenvk_destination = workspace / "MoltenVK"
mirror_with_symlinks(root / "MoltenVK", moltenvk_destination, {"MoltenVK.xcodeproj"})
shutil.copytree(
    root / "MoltenVK" / "MoltenVK.xcodeproj",
    moltenvk_destination / "MoltenVK.xcodeproj",
    symlinks=True,
)
PY

    patch_macos_shader_converter_dependency "$workspace_root/MoltenVK/MoltenVK.xcodeproj/project.pbxproj"
    printf '%s\n' "$workspace_root"
}

archive_dynamic_framework() {
    local project_path="$1"
    local scheme="$2"
    local destination="$3"
    local archive_path="$4"

    xcodebuild archive \
        -project "$project_path" \
        -scheme "$scheme" \
        -configuration "$CONFIGURATION" \
        -destination "$destination" \
        -archivePath "$archive_path" \
        SKIP_INSTALL=NO \
        MERGEABLE_LIBRARY=YES \
        BUILD_LIBRARY_FOR_DISTRIBUTION=YES \
        CODE_SIGNING_ALLOWED=NO \
        CODE_SIGNING_REQUIRED=NO \
        ONLY_ACTIVE_ARCH=NO \
        GCC_PREPROCESSOR_DEFINITIONS='$inherited MVK_USE_METAL_PRIVATE_API=0'
}
