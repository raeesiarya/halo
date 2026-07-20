#!/usr/bin/env bash
# Standard audit for each deletion-set policy, with separate output paths.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/outputs/trex_policy_matrix}"
DEL_OFF_MODE="${DEL_OFF_MODE:-null-retrieval}"

run_policy() {
    local label="$1"
    shift
    echo "=== Deletion policy: $label ==="
    OUTPUT_DIR="$BASE_OUTPUT_DIR/$label" \
    "$REPO_ROOT/scripts/run_audit_co_lmlm.sh" \
        --co-lmlm-del-off-mode "$DEL_OFF_MODE" \
        "$@"
}

run_policy oracle "$@"
run_policy geometric --closure geometric "$@"
run_policy value --closure value "$@"
run_policy provenance --closure provenance "$@"
run_policy hybrid --closure geometric,value,provenance "$@"
