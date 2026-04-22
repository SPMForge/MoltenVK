#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
source "$(cd "$(dirname "$0")" && pwd)/source_acquisition.sh"

showdestinations_token_for_platform() {
    local destination
    destination="$(platform_destination_for_id "$1")"
    destination="${destination#generic/platform=}"
    printf '%s\n' "$destination"
}

require_command xcodebuild
require_command python3

parse_requested_platforms "$@"

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
        ./Scripts/SwiftPackage/preflight_apple_platforms.sh "$@"
    )

    log "Preflight Apple platform destinations from upstream snapshot $resolved_upstream_ref"
    exit 0
fi

require_path "$MOLTENVK_PROJECT"

for platform_id in "${REQUESTED_PLATFORM_IDS[@]}"; do
    scheme="$(dynamic_scheme_for_platform "$platform_id" "$MOLTENVK_PROJECT")"
    expected_token="$(showdestinations_token_for_platform "$platform_id")"
    destination_output="$(xcodebuild -showdestinations -project "$MOLTENVK_PROJECT" -scheme "$scheme")"
    grep -F "platform:${expected_token}" <<<"$destination_output" | grep -Fv "error:" >/dev/null \
        || fail "Scheme $scheme does not advertise an eligible destination platform:${expected_token}"
    log "Verified destination platform:${expected_token} for scheme $scheme"
done
