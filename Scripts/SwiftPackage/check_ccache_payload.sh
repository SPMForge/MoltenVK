#!/usr/bin/env bash
set -euo pipefail

ccache_dir="${1:-${CCACHE_DIR:-.ccache}}"
minimum_bytes="${2:-262144}"

[[ -d "$ccache_dir" ]] || {
    echo "error: missing ccache directory: $ccache_dir" >&2
    exit 1
}

[[ "$minimum_bytes" =~ ^[0-9]+$ ]] || {
    echo "error: minimum_bytes must be an integer: $minimum_bytes" >&2
    exit 1
}

file_count=0
total_bytes=0
while IFS= read -r -d '' file_path; do
    file_size="$(stat -f '%z' "$file_path")"
    total_bytes=$((total_bytes + file_size))
    file_count=$((file_count + 1))
done < <(find "$ccache_dir" -type f -print0)

non_empty=false
if (( file_count > 0 )) && (( total_bytes >= minimum_bytes )); then
    non_empty=true
fi

emit_output() {
    local line="$1"
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "$line" >> "$GITHUB_OUTPUT"
    else
        echo "$line"
    fi
}

emit_output "file_count=$file_count"
emit_output "total_bytes=$total_bytes"
emit_output "minimum_bytes=$minimum_bytes"
emit_output "non_empty=$non_empty"

echo "ccache payload bytes: $total_bytes across $file_count files (threshold: $minimum_bytes)" >&2
