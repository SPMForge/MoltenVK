#!/bin/bash

set -euo pipefail

SUMMARY_TITLE="${1:-ccache statistics}"

append_summary() {
    [[ -n "${GITHUB_STEP_SUMMARY:-}" ]] || return 0
    if [[ $# -eq 0 ]]; then
        printf '\n' >> "$GITHUB_STEP_SUMMARY"
        return 0
    fi
    printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"
}

if ! command -v ccache >/dev/null 2>&1; then
    echo "warning: ccache is unavailable; skipping statistics." >&2
    append_summary "## ${SUMMARY_TITLE}"
    append_summary
    append_summary "_ccache is unavailable on this runner._"
    exit 0
fi

stats_file="$(mktemp "${TMPDIR:-/tmp}/moltenvk-ccache-stats.XXXXXX")"
trap 'rm -f "$stats_file"' EXIT

echo "==> ccache statistics"
ccache --show-stats | tee "$stats_file"

append_summary "## ${SUMMARY_TITLE}"
append_summary
if [[ -n "${CCACHE_DIR:-}" ]]; then
    append_summary "- cache dir: \`${CCACHE_DIR}\`"
    append_summary
fi
append_summary '```text'
cat "$stats_file" >> "$GITHUB_STEP_SUMMARY"
append_summary '```'
