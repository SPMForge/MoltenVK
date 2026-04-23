#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SWIFT_PACKAGE_DIR="$ROOT_DIR/SwiftPackage"
MOLTENVK_UPSTREAM_REPOSITORY_FILE="$SWIFT_PACKAGE_DIR/UpstreamRepository.txt"
MOLTENVK_UPSTREAM_SOURCE_REF_FILE="$SWIFT_PACKAGE_DIR/UpstreamSourceRef.txt"
MOLTENVK_UPSTREAM_TAG_NAMESPACE="${MVK_UPSTREAM_TAG_NAMESPACE:-refs/upstream-tags}"
MOLTENVK_EXTERNAL_CACHE_PATHS=(
    "External/cereal"
    "External/Vulkan-Headers"
    "External/SPIRV-Cross"
    "External/SPIRV-Tools"
    "External/Vulkan-Tools"
    "External/Volk"
    "External/build"
)

if ! command -v rsync >/dev/null 2>&1; then
    echo "error: Missing required command: rsync" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "error: Missing required command: git" >&2
    exit 1
fi

sa_fail() {
    printf 'error: %s\n' "$1" >&2
    exit 1
}

trim_trailing_newlines() {
    python3 -c 'import sys; print(sys.stdin.read().strip())'
}

read_upstream_repository() {
    [[ -f "$MOLTENVK_UPSTREAM_REPOSITORY_FILE" ]] || sa_fail "Missing upstream repository contract: $MOLTENVK_UPSTREAM_REPOSITORY_FILE"
    local repository
    repository="$(tr -d '\r\n' <"$MOLTENVK_UPSTREAM_REPOSITORY_FILE")"
    [[ -n "$repository" ]] || sa_fail "Upstream repository contract is empty: $MOLTENVK_UPSTREAM_REPOSITORY_FILE"
    printf '%s\n' "$repository"
}

read_pinned_upstream_ref() {
    if [[ -n "${MVK_UPSTREAM_REF:-}" ]]; then
        printf '%s\n' "$MVK_UPSTREAM_REF"
        return
    fi

    if [[ -f "$MOLTENVK_UPSTREAM_SOURCE_REF_FILE" ]]; then
        local pinned_ref
        pinned_ref="$(tr -d '\r\n' <"$MOLTENVK_UPSTREAM_SOURCE_REF_FILE")"
        if [[ -n "$pinned_ref" ]]; then
            printf '%s\n' "$pinned_ref"
            return
        fi
    fi

    printf '\n'
}

normalize_upstream_ref() {
    local raw_ref="$1"
    local trimmed
    trimmed="$(printf '%s' "$raw_ref" | trim_trailing_newlines)"
    [[ -n "$trimmed" ]] || sa_fail "Upstream ref must not be empty."

    if [[ "$trimmed" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        printf 'v%s\n' "$trimmed"
        return
    fi

    printf '%s\n' "$trimmed"
}

fetch_upstream_tags() {
    local upstream_repository
    upstream_repository="$(read_upstream_repository)"

    git -C "$ROOT_DIR" fetch --force --no-tags "$upstream_repository" "+refs/tags/*:${MOLTENVK_UPSTREAM_TAG_NAMESPACE}/*"
}

list_stable_upstream_refs() {
    git -C "$ROOT_DIR" for-each-ref --format='%(refname:strip=2)' "$MOLTENVK_UPSTREAM_TAG_NAMESPACE" \
        | awk '/^v[0-9]+\.[0-9]+\.[0-9]+$/ { print }' \
        | sort -V
}

resolve_requested_or_latest_upstream_ref() {
    local requested_ref="${1:-}"

    fetch_upstream_tags

    if [[ -z "$requested_ref" ]]; then
        requested_ref="$(read_pinned_upstream_ref)"
    fi

    if [[ -n "$requested_ref" ]]; then
        local normalized_ref
        normalized_ref="$(normalize_upstream_ref "$requested_ref")"
        git -C "$ROOT_DIR" rev-parse -q --verify "${MOLTENVK_UPSTREAM_TAG_NAMESPACE}/${normalized_ref}" >/dev/null \
            || sa_fail "Requested upstream ref is not available after fetch: ${normalized_ref}"
        printf '%s\n' "$normalized_ref"
        return
    fi

    local latest_ref
    latest_ref="$(list_stable_upstream_refs | tail -n 1)"
    [[ -n "$latest_ref" ]] || sa_fail "Unable to determine the latest stable upstream tag from ${MOLTENVK_UPSTREAM_TAG_NAMESPACE}."
    printf '%s\n' "$latest_ref"
}

resolve_latest_upstream_ref() {
    fetch_upstream_tags

    local latest_ref
    latest_ref="$(list_stable_upstream_refs | tail -n 1)"
    [[ -n "$latest_ref" ]] || sa_fail "Unable to determine the latest stable upstream tag from ${MOLTENVK_UPSTREAM_TAG_NAMESPACE}."
    printf '%s\n' "$latest_ref"
}

export_upstream_snapshot() {
    local upstream_ref="$1"
    local destination="$2"

    mkdir -p "$destination"
    git -C "$ROOT_DIR" archive --format=tar "${MOLTENVK_UPSTREAM_TAG_NAMESPACE}/${upstream_ref}" | tar -xf - -C "$destination"
}

overlay_wrapper_files() {
    local workspace_root="$1"

    mkdir -p "$workspace_root/Scripts/SwiftPackage" "$workspace_root/SwiftPackage" "$workspace_root/tests" "$workspace_root/Artifacts"

    rsync -a "$ROOT_DIR/Scripts/SwiftPackage/" "$workspace_root/Scripts/SwiftPackage/"
    rsync -a "$ROOT_DIR/tests/" "$workspace_root/tests/"
    if [[ -d "$ROOT_DIR/Sources" ]]; then
        mkdir -p "$workspace_root/Sources"
        rsync -a "$ROOT_DIR/Sources/" "$workspace_root/Sources/"
    fi
    rsync -a --exclude 'node_modules' "$ROOT_DIR/SwiftPackage/" "$workspace_root/SwiftPackage/"

    if [[ -f "$ROOT_DIR/Package.swift" ]]; then
        cp "$ROOT_DIR/Package.swift" "$workspace_root/Package.swift"
    fi

}

seed_dependency_cache_into_workspace() {
    local workspace_root="$1"
    local relative_path

    for relative_path in "${MOLTENVK_EXTERNAL_CACHE_PATHS[@]}"; do
        if [[ -e "$ROOT_DIR/$relative_path" ]]; then
            mkdir -p "$workspace_root/$(dirname "$relative_path")"
            rsync -a "$ROOT_DIR/$relative_path" "$workspace_root/$(dirname "$relative_path")/"
        fi
    done
}

patch_upstream_wrapper_workspace() {
    local workspace_root="$1"
    local resolved_ref="$2"
    local upstream_commit

    command -v python3 >/dev/null 2>&1 || sa_fail "Missing required command: python3"

    upstream_commit="$(git -C "$ROOT_DIR" rev-parse "${MOLTENVK_UPSTREAM_TAG_NAMESPACE}/${resolved_ref}^{commit}")" \
        || sa_fail "Unable to resolve upstream commit for ${resolved_ref}"

    python3 "$ROOT_DIR/Scripts/SwiftPackage/prepare_upstream_workspace.py" \
        --workspace-root "$workspace_root" \
        --upstream-commit "$upstream_commit" \
        --platform-config "$ROOT_DIR/SwiftPackage/platforms.json" \
        || sa_fail "Unable to patch prepared upstream workspace at $workspace_root"
}

prepare_upstream_wrapper_workspace() {
    local requested_ref="${1:-}"
    local resolved_ref
    local workspace_root

    resolved_ref="$(resolve_requested_or_latest_upstream_ref "$requested_ref")"
    workspace_root="$(mktemp -d "${TMPDIR:-/tmp}/moltenvk-wrapper-upstream.XXXXXX")"

    export_upstream_snapshot "$resolved_ref" "$workspace_root"
    overlay_wrapper_files "$workspace_root"
    seed_dependency_cache_into_workspace "$workspace_root"
    printf '%s\n' "$resolved_ref" > "$workspace_root/SwiftPackage/UpstreamSourceRef.txt"
    patch_upstream_wrapper_workspace "$workspace_root" "$resolved_ref"

    printf '%s\n%s\n' "$workspace_root" "$resolved_ref"
}

sync_dependency_cache_back() {
    local workspace_root="$1"
    local wrapper_root="${2:-$ROOT_DIR}"
    local relative_path

    for relative_path in "${MOLTENVK_EXTERNAL_CACHE_PATHS[@]}"; do
        if [[ -e "$workspace_root/$relative_path" ]]; then
            mkdir -p "$wrapper_root/$(dirname "$relative_path")"
            rsync -a --delete "$workspace_root/$relative_path" "$wrapper_root/$(dirname "$relative_path")/"
        fi
    done
}

sync_workspace_outputs_back() {
    local workspace_root="$1"
    local wrapper_root="${2:-$ROOT_DIR}"
    local relative_path

    [[ -d "$workspace_root/Artifacts" ]] || sa_fail "Workspace does not contain Artifacts output: $workspace_root/Artifacts"
    mkdir -p "$wrapper_root/Artifacts"
    rsync -a --delete "$workspace_root/Artifacts/" "$wrapper_root/Artifacts/"

    [[ -f "$workspace_root/Package.swift" ]] || sa_fail "Workspace did not render Package.swift."
    cp "$workspace_root/Package.swift" "$wrapper_root/Package.swift"

    mkdir -p "$wrapper_root/SwiftPackage"
    for relative_path in PackageVersion.txt ReleaseRepository.txt UpstreamRepository.txt UpstreamSourceRef.txt; do
        if [[ -f "$workspace_root/SwiftPackage/$relative_path" ]]; then
            cp "$workspace_root/SwiftPackage/$relative_path" "$wrapper_root/SwiftPackage/$relative_path"
        fi
    done

    sync_dependency_cache_back "$workspace_root" "$wrapper_root"
}
