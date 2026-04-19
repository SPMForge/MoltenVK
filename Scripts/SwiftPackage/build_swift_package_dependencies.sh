#!/bin/bash

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_command xcodebuild
require_command xcrun
require_command python3
require_command git
require_command cmake

require_path "$ROOT_DIR/fetchDependencies"
require_path "$MOLTENVK_PACKAGING_PROJECT"

parse_requested_platforms "$@"

log "Fetching MoltenVK dependencies for ${REQUESTED_PLATFORM_FLAGS[*]}"
"$ROOT_DIR/fetchDependencies" "${REQUESTED_PLATFORM_FLAGS[@]}" --keep-cache

log "Prewarmed MoltenVK dependencies for configuration $CONFIGURATION"
