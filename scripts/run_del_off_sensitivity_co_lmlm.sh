#!/usr/bin/env bash
# Standard audit under both retrieval-disabled controls.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/outputs/trex_del_off_sensitivity}"
STANDARD_CLOSURE="${STANDARD_CLOSURE:-geometric,value}"

for mode in null-retrieval forbid-token; do
    echo "=== DEL-OFF sensitivity: $mode ==="
    OUTPUT_DIR="$BASE_OUTPUT_DIR/$mode" \
    "$REPO_ROOT/scripts/run_audit_co_lmlm.sh" \
        --closure "$STANDARD_CLOSURE" \
        --co-lmlm-del-off-mode "$mode" \
        "$@"
done
