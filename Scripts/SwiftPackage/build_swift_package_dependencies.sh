#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
source "$(cd "$(dirname "$0")" && pwd)/source_acquisition.sh"

require_command xcodebuild
require_command xcrun
require_command python3
require_command git
require_command cmake

if [[ "${MVK_SOURCE_WORKSPACE_ACTIVE:-0}" != "1" ]]; then
    workspace_info="$(prepare_upstream_wrapper_workspace "${MVK_UPSTREAM_REF:-}")"
    workspace_root="$(printf '%s\n' "$workspace_info" | sed -n '1p')"
    resolved_upstream_ref="$(printf '%s\n' "$workspace_info" | sed -n '2p')"

    cleanup_upstream_workspace() {
        [[ -n "${workspace_root:-}" ]] && rm -rf "$workspace_root"
    }
    trap cleanup_upstream_workspace EXIT

    (
        cd "$workspace_root"
        MVK_SOURCE_WORKSPACE_ACTIVE=1 \
        MVK_UPSTREAM_REF="$resolved_upstream_ref" \
        ./Scripts/SwiftPackage/build_swift_package_dependencies.sh "$@"
    )

    sync_workspace_outputs_back "$workspace_root" "$ROOT_DIR"
    log "Prewarmed MoltenVK dependencies from upstream snapshot $resolved_upstream_ref"
    exit 0
fi

require_path "$ROOT_DIR/fetchDependencies"
require_path "$MOLTENVK_PACKAGING_PROJECT"

parse_requested_platforms "$@"

log "Fetching MoltenVK dependencies for ${REQUESTED_PLATFORM_FLAGS[*]}"
"$ROOT_DIR/fetchDependencies" "${REQUESTED_PLATFORM_FLAGS[@]}" --keep-cache

log "Prewarmed MoltenVK dependencies for configuration $CONFIGURATION"
