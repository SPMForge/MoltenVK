#!/bin/bash

set -euo pipefail

ROOT_DIR="${MVK_PACKAGE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ARTIFACTS_DIR="$ROOT_DIR/Artifacts"
CONFIGURATION="${CONFIGURATION:-Release}"
SWIFT_PACKAGE_DIR="$ROOT_DIR/SwiftPackage"
MOLTENVK_PLATFORM_CONFIG_FILE="$SWIFT_PACKAGE_DIR/platforms.json"
MOLTENVK_PLATFORM_CONFIG_SCRIPT="$ROOT_DIR/Scripts/SwiftPackage/platform_config.py"
MOLTENVK_PROJECT="$ROOT_DIR/MoltenVK/MoltenVK.xcodeproj"
MOLTENVK_PACKAGING_PROJECT="$ROOT_DIR/MoltenVKPackaging.xcodeproj"
MOLTENVK_INCLUDE_DIR="$ROOT_DIR/MoltenVK/include"
MOLTENVK_API_HEADERS_DIR="$ROOT_DIR/MoltenVK/MoltenVK/API"
MOLTENVK_VULKAN_HEADERS_ROOT="$ROOT_DIR/External/Vulkan-Headers/include"
MOLTENVK_DYNAMIC_ARTIFACT_NAME="MoltenVK.xcframework"
MOLTENVK_STATIC_ARTIFACT_NAME="MoltenVK-static.xcframework"
MOLTENVK_RELEASE_REPOSITORY_FILE="$SWIFT_PACKAGE_DIR/ReleaseRepository.txt"
MOLTENVK_PACKAGE_VERSION_FILE="$SWIFT_PACKAGE_DIR/PackageVersion.txt"
MOLTENVK_PREPARED_WORKSPACE_RECORD_FILE="$SWIFT_PACKAGE_DIR/.prepared-workspace-path"
MOLTENVK_MERGEABLE_VALIDATOR_PATH="${MVK_MERGEABLE_VALIDATOR_PATH:-$ROOT_DIR/Scripts/SwiftPackage/validate_mergeable_xcframework.py}"
MOLTENVK_PUBLIC_HEADERS_SCRIPT="$ROOT_DIR/Scripts/SwiftPackage/materialize_public_headers.py"
MOLTENVK_REQUIRED_EXTERNAL_SOURCE_PATHS=(
    "$ROOT_DIR/External/cereal/include/cereal/cereal.hpp"
    "$ROOT_DIR/External/Vulkan-Headers/registry/vk.xml"
    "$ROOT_DIR/External/SPIRV-Cross/spirv.hpp"
    "$ROOT_DIR/External/Vulkan-Tools"
    "$ROOT_DIR/External/Volk/volk.h"
)

REQUESTED_PLATFORM_IDS=()
REQUESTED_PLATFORM_FLAGS=()
CCACHE_BUILD_ARGS=()
CCACHE_WRAPPER_DIR=""
CCACHE_ENABLED=0

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

load_platform_model() {
    local shell_assignments
    shell_assignments="$(
        python3 "$MOLTENVK_PLATFORM_CONFIG_SCRIPT" render-shell --config "$MOLTENVK_PLATFORM_CONFIG_FILE"
    )" || fail "Unable to load platform config from $MOLTENVK_PLATFORM_CONFIG_FILE"
    eval "$shell_assignments"
}

platform_index_by_id() {
    local requested_id="$1"
    local index
    for index in "${!MOLTENVK_PLATFORM_IDS[@]}"; do
        if [[ "${MOLTENVK_PLATFORM_IDS[$index]}" == "$requested_id" ]]; then
            printf '%s\n' "$index"
            return 0
        fi
    done
    return 1
}

platform_destination_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    printf '%s\n' "${MOLTENVK_PLATFORM_DESTINATIONS[$index]}"
}

platform_sdk_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    printf '%s\n' "${MOLTENVK_PLATFORM_SDKS[$index]}"
}

platform_validator_key_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    printf '%s\n' "${MOLTENVK_PLATFORM_VALIDATOR_KEYS[$index]}"
}

platform_build_flag_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    printf '%s\n' "${MOLTENVK_PLATFORM_BUILD_FLAGS[$index]}"
}

platform_family_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    printf '%s\n' "${MOLTENVK_PLATFORM_FAMILIES[$index]}"
}

deployment_target_index_by_family() {
    local requested_family="$1"
    local index
    for index in "${!MOLTENVK_DEPLOYMENT_TARGET_FAMILIES[@]}"; do
        if [[ "${MOLTENVK_DEPLOYMENT_TARGET_FAMILIES[$index]}" == "$requested_family" ]]; then
            printf '%s\n' "$index"
            return 0
        fi
    done
    return 1
}

swiftpm_platform_name_for_family() {
    local index
    index="$(deployment_target_index_by_family "$1")" || fail "Unknown deployment target family in platform config: $1"
    printf '%s\n' "${MOLTENVK_DEPLOYMENT_TARGET_SWIFTPM_PLATFORMS[$index]}"
}

deployment_target_version_for_family() {
    local index
    index="$(deployment_target_index_by_family "$1")" || fail "Unknown deployment target family in platform config: $1"
    printf '%s\n' "${MOLTENVK_DEPLOYMENT_TARGET_VERSIONS[$index]}"
}

deployment_target_build_setting_for_family() {
    local index
    index="$(deployment_target_index_by_family "$1")" || fail "Unknown deployment target family in platform config: $1"
    printf '%s\n' "${MOLTENVK_DEPLOYMENT_TARGET_BUILD_SETTINGS[$index]}"
}

platform_deployment_target_build_setting_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    deployment_target_build_setting_for_family "${MOLTENVK_PLATFORM_FAMILIES[$index]}"
}

platform_consumer_test_enabled_for_id() {
    local index
    index="$(platform_index_by_id "$1")" || fail "Unknown platform id in platform config: $1"
    [[ "${MOLTENVK_PLATFORM_CONSUMER_TESTS[$index]}" == "1" ]]
}

consumer_test_platform_ids() {
    local index
    for index in "${!MOLTENVK_PLATFORM_IDS[@]}"; do
        if [[ "${MOLTENVK_PLATFORM_CONSUMER_TESTS[$index]}" == "1" ]]; then
            printf '%s\n' "${MOLTENVK_PLATFORM_IDS[$index]}"
        fi
    done
}

configured_validator_args() {
    local args=()
    local platform_id
    for platform_id in "${MOLTENVK_PLATFORM_IDS[@]}"; do
        args+=(--require-platform "$(platform_validator_key_for_id "$platform_id")")
    done
    printf '%s\n' "${args[@]}"
}

load_platform_model

setup_ccache() {
    CCACHE_BUILD_ARGS=()
    CCACHE_ENABLED=0

    if [[ "${MVK_ENABLE_CCACHE:-0}" != "1" ]]; then
        return 0
    fi

    if ! command -v ccache >/dev/null 2>&1; then
        warn "MVK_ENABLE_CCACHE=1 but ccache is unavailable; continuing without compiler cache."
        return
    fi

    local ccache_dir="${CCACHE_DIR:-${MVK_CCACHE_DIR:-$ROOT_DIR/.ccache}}"
    local ccache_max_size="${CCACHE_MAXSIZE:-2G}"
    local ccache_base_dir="${MVK_WRAPPER_ROOT:-$ROOT_DIR}"
    local real_clang
    local real_clangxx

    mkdir -p "$ccache_dir"
    export CCACHE_DIR="$ccache_dir"
    export CCACHE_BASEDIR="$ccache_base_dir"
    export CCACHE_NOHASHDIR=1

    real_clang="$(xcrun -f clang)"
    real_clangxx="$(xcrun -f clang++)"
    CCACHE_WRAPPER_DIR="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-ccache.XXXXXX")"

    cat >"$CCACHE_WRAPPER_DIR/clang" <<EOF
#!/bin/sh
exec "$(command -v ccache)" "$real_clang" "\$@"
EOF
    cat >"$CCACHE_WRAPPER_DIR/clang++" <<EOF
#!/bin/sh
exec "$(command -v ccache)" "$real_clangxx" "\$@"
EOF
    chmod +x "$CCACHE_WRAPPER_DIR/clang" "$CCACHE_WRAPPER_DIR/clang++"

    export CC="$CCACHE_WRAPPER_DIR/clang"
    export CXX="$CCACHE_WRAPPER_DIR/clang++"
    export OBJC="$CC"
    export OBJCXX="$CXX"
    export LDPLUSPLUS="$CXX"

    CCACHE_BUILD_ARGS=(
        "CC=$CC"
        "CXX=$CXX"
        "OBJC=$OBJC"
        "OBJCXX=$OBJCXX"
        "LDPLUSPLUS=$LDPLUSPLUS"
    )

    ccache --max-size "$ccache_max_size" >/dev/null 2>&1 || true
    ccache --zero-stats >/dev/null 2>&1 || true
    CCACHE_ENABLED=1
    log "Enabled ccache at $CCACHE_DIR"
}

print_ccache_stats() {
    (( CCACHE_ENABLED )) || return 0

    log "ccache statistics"
    ccache --show-stats || true
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
    REQUESTED_PLATFORM_IDS=()
    REQUESTED_PLATFORM_FLAGS=()

    if [[ $# -eq 0 ]]; then
        local platform_id
        local sdk
        local build_flag
        for platform_id in "${MOLTENVK_PLATFORM_IDS[@]}"; do
            sdk="$(platform_sdk_for_id "$platform_id")"
            build_flag="$(platform_build_flag_for_id "$platform_id")"
            if sdk_supports_platform "$sdk"; then
                REQUESTED_PLATFORM_IDS+=("$platform_id")
                REQUESTED_PLATFORM_FLAGS+=("$build_flag")
            else
                warn "Skipping ${platform_id} because the ${sdk} SDK is not installed in this Xcode installation."
            fi
        done
        return
    fi

    local platform
    local platform_id
    local build_flag
    local matched_platform_id
    for platform in "$@"; do
        case "$platform" in
            --all)
                parse_requested_platforms
                return
                ;;
            *)
                matched_platform_id=""
                for platform_id in "${MOLTENVK_PLATFORM_IDS[@]}"; do
                    build_flag="$(platform_build_flag_for_id "$platform_id")"
                    if [[ "$build_flag" == "$platform" ]]; then
                        matched_platform_id="$platform_id"
                        break
                    fi
                done

                [[ -n "$matched_platform_id" ]] || fail "Unsupported platform flag: $platform"
                if ! sdk_supports_platform "$(platform_sdk_for_id "$matched_platform_id")"; then
                    fail "Requested ${platform}, but the $(platform_sdk_for_id "$matched_platform_id") SDK is not installed."
                fi

                REQUESTED_PLATFORM_IDS+=("$matched_platform_id")
                REQUESTED_PLATFORM_FLAGS+=("$platform")
                ;;
        esac
    done

    (( ${#REQUESTED_PLATFORM_IDS[@]} )) || fail "No supported Apple platform was requested."
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

dynamic_release_archive_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVK-%s.xcframework.zip\n' "$version"
}

dynamic_release_checksum_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVK-%s.xcframework.checksum\n' "$version"
}

static_release_archive_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVK-static-%s.xcframework.zip\n' "$version"
}

static_release_checksum_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVK-static-%s.xcframework.checksum\n' "$version"
}

headers_release_archive_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVKHeaders-%s.zip\n' "$version"
}

headers_release_checksum_name() {
    local version="${1:-$(read_package_version)}"
    printf 'MoltenVKHeaders-%s.checksum\n' "$version"
}

dynamic_validator_args() {
    local args=()
    local platform_id
    for platform_id in "${REQUESTED_PLATFORM_IDS[@]}"; do
        args+=(--require-platform "$(platform_validator_key_for_id "$platform_id")")
    done
    if (( ${#args[@]} )); then
        printf '%s\n' "${args[@]}"
    fi
}

scheme_exists() {
    local project_path="$1"
    local scheme="$2"

    xcodebuild -list -project "$project_path" 2>/dev/null | grep -Fq "        $scheme"
}

dynamic_scheme_for_platform() {
    local platform_id="$1"
    local project_path="$2"
    local scheme_base

    case "$platform_id" in
        macos)
            scheme_base="MoltenVK-macOS"
            ;;
        ios|ios-simulator)
            scheme_base="MoltenVK-iOS"
            ;;
        tvos|tvos-simulator)
            scheme_base="MoltenVK-tvOS"
            ;;
        xros|xros-simulator)
            scheme_base="MoltenVK-xrOS"
            ;;
        *)
            fail "Unsupported platform id in dynamic scheme mapping: $platform_id"
            ;;
    esac

    if scheme_exists "$project_path" "${scheme_base}-dynamic"; then
        printf '%s-dynamic\n' "$scheme_base"
        return
    fi

    printf '%s\n' "$scheme_base"
}

require_external_dependency_sources() {
    local required_path
    for required_path in "${MOLTENVK_REQUIRED_EXTERNAL_SOURCE_PATHS[@]}"; do
        require_path "$required_path"
    done

    if [[ -e "$ROOT_DIR/External/SPIRV-Tools/external/spirv-headers/include/spirv/unified1/spirv.hpp" ]]; then
        return
    fi

    if [[ -e "$ROOT_DIR/Templates/spirv-tools/build.zip" ]]; then
        return
    fi

    fail "Missing SPIRV-Tools header source. Expected either External/SPIRV-Tools/external/spirv-headers/include/spirv/unified1/spirv.hpp or Templates/spirv-tools/build.zip"
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

patch_tvos_mergeable_linker_mode() {
    local pbxproj_path="$1"

    python3 - "$pbxproj_path" <<'PY'
from pathlib import Path
import sys

pbxproj_path = Path(sys.argv[1])
text = pbxproj_path.read_text()

# Upstream tvOS dynamic targets still opt into the legacy classic linker.
# Mergeable archives require the modern linker because Xcode injects -make_mergeable.
legacy_flags = 'OTHER_LDFLAGS = (\n\t\t\t\t\t"-ld_classic",\n\t\t\t\t\t"-all_load",\n\t\t\t\t\t"-w",\n\t\t\t\t);'
mergeable_flags = 'OTHER_LDFLAGS = (\n\t\t\t\t\t"-all_load",\n\t\t\t\t\t"-w",\n\t\t\t\t);'

legacy_count = text.count(legacy_flags)
if legacy_count != 2:
    raise SystemExit(
        f"Expected 2 tvOS dynamic classic-linker flag blocks in {pbxproj_path}, found {legacy_count}"
    )

text = text.replace(legacy_flags, mergeable_flags, 2)
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
    patch_tvos_mergeable_linker_mode "$workspace_root/MoltenVK/MoltenVK.xcodeproj/project.pbxproj"
    printf '%s\n' "$workspace_root"
}

archive_dynamic_framework() {
    local project_path="$1"
    local scheme="$2"
    local destination="$3"
    local archive_path="$4"
    local platform_id="$5"
    local command=(
        xcodebuild archive
        -project "$project_path"
        -scheme "$scheme"
        -configuration "$CONFIGURATION"
        -destination "$destination"
        -archivePath "$archive_path"
    )

    if (( ${#CCACHE_BUILD_ARGS[@]} )); then
        command+=("${CCACHE_BUILD_ARGS[@]}")
    fi

    command+=(
        "$(platform_deployment_target_build_setting_for_id "$platform_id")"
        SKIP_INSTALL=NO
        MERGEABLE_LIBRARY=YES
        BUILD_LIBRARY_FOR_DISTRIBUTION=YES
        CODE_SIGNING_ALLOWED=NO
        CODE_SIGNING_REQUIRED=NO
        ONLY_ACTIVE_ARCH=NO
        'GCC_PREPROCESSOR_DEFINITIONS=$inherited MVK_USE_METAL_PRIVATE_API=0'
    )

    "${command[@]}"
}
