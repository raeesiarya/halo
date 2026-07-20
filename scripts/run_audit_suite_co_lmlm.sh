#!/usr/bin/env bash
# Run the full HALO audit suite on Co-LMLM: the standard three-state audit,
# the entanglement sweep, and the adversarial-closure evaluation.
#
# Invoke from the HALO repo, but it executes inside the public Co-LMLM
# environment (Co-LMLM ships its own `lmlm` package, so it must run there):
# it clones/syncs the checkout if needed, cd's into it, and puts HALO's src
# on PYTHONPATH.
#
# The three phases are separate evaluation modes and run sequentially — they
# share one GPU, and the sweep/adversarial phases share one FULL pass (the
# <prompts>_full/ directory). Every phase is resumable, so if the suite dies
# partway, re-running it skips everything already on disk. All phases log to
# W&B as separate runs named <output-dir>__<mode>.
#
# Wall-clock tip: phase 2 shards cleanly by radius. Run one single-radius
# sweep first (e.g. RADIUS_GRID=0.95:0.95:0.05) so the shared FULL pass is
# materialized, then launch the remaining radii as parallel processes (one
# GPU each, same OUTPUT_DIR — each writes its own sweep_rho_*.jsonl), and
# finally re-run the full grid: it resumes every per-radius file and only
# computes the analysis. Do NOT shard by prompt file subsets — neighbor
# sets N(f) are defined within a prompt file.
#
# Optional:  CO_LMLM_DIR (defaults to ../Co-LMLM next to this repo; cloned
#            from GitHub if absent), INDEX_DIR, PROMPTS, OUTPUT_DIR,
#            STANDARD_CLOSURE, SWEEP_CLOSURE, ADVERSARIAL_CLOSURE,
#            RADIUS_GRID, NEIGHBOR_MODE, NEIGHBOR_MIN_COUNT, DEL_OFF_MODE
# Extra flags are passed through to every phase, so keep --limit consistent
# across re-runs: the shared FULL pass is resumed wholesale and only covers
# the facts it was built with.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CO_LMLM_REPO_URL="https://github.com/lil-lab/Co-LMLM.git"
CO_LMLM_DIR="${CO_LMLM_DIR:-$(dirname "$REPO_ROOT")/Co-LMLM}"

INDEX_DIR="${INDEX_DIR:-$REPO_ROOT/data/co-lmlm-wiki-index}"
# T-REx slot-filling is the default audit corpus (in-context prompts, native
# continuation format); use PROMPTS=data/prompts.jsonl for the PopQA set.
PROMPTS="${PROMPTS:-$REPO_ROOT/data/prompts_trex.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/outputs/trex}"

# The audit runs from inside the Co-LMLM checkout, so anchor relative
# overrides to the invocation directory before we cd away.
case "$INDEX_DIR" in /*) ;; *) INDEX_DIR="$PWD/$INDEX_DIR" ;; esac
case "$PROMPTS" in /*) ;; *) PROMPTS="$PWD/$PROMPTS" ;; esac
case "$OUTPUT_DIR" in /*) ;; *) OUTPUT_DIR="$PWD/$OUTPUT_DIR" ;; esac

# Radius-dependent evaluations use geometric closure only.
STANDARD_CLOSURE="${STANDARD_CLOSURE:-${CLOSURE:-geometric,value}}"
SWEEP_CLOSURE="${SWEEP_CLOSURE:-geometric}"
ADVERSARIAL_CLOSURE="${ADVERSARIAL_CLOSURE:-geometric}"
RADIUS_GRID="${RADIUS_GRID:-0.95:0.70:0.05}"
NEIGHBOR_MODE="${NEIGHBOR_MODE:-cosine}"
NEIGHBOR_MIN_COUNT="${NEIGHBOR_MIN_COUNT:-5}"
DEL_OFF_MODE="${DEL_OFF_MODE:-null-retrieval}"

if [ ! -d "$CO_LMLM_DIR" ]; then
    echo "Co-LMLM checkout not found; cloning $CO_LMLM_REPO_URL -> $CO_LMLM_DIR"
    git clone "$CO_LMLM_REPO_URL" "$CO_LMLM_DIR"
elif [ ! -f "$CO_LMLM_DIR/src/lmlm/eval/hf_generate.py" ]; then
    echo "error: $CO_LMLM_DIR exists but does not look like the public Co-LMLM checkout" >&2
    echo "       (missing src/lmlm/eval/hf_generate.py); set CO_LMLM_DIR to the right path" >&2
    exit 1
fi

cd "$CO_LMLM_DIR"
echo "Syncing the Co-LMLM environment (uv sync) ..."
uv sync

run_audit() {
    PYTHONPATH="$REPO_ROOT/src:src${PYTHONPATH:+:$PYTHONPATH}" \
    uv run python -m halo.run_audit \
        --backend co-lmlm \
        --index-path "$INDEX_DIR" \
        --prompt-files "$PROMPTS" \
        --bootstrap-oracle-from-full \
        --co-lmlm-del-off-mode "$DEL_OFF_MODE" \
        --wandb-activation on \
        --output-dir "$OUTPUT_DIR" \
        "$@"
}

echo "=== Phase 1/3: standard audit (L(f), R(f), probe, closure manifests) ==="
run_audit --closure "$STANDARD_CLOSURE" "$@"

echo "=== Phase 2/3: entanglement sweep (operating curves, G(f)) ==="
run_audit --closure "$SWEEP_CLOSURE" --radius-grid "$RADIUS_GRID" \
    --neighbor-mode "$NEIGHBOR_MODE" \
    --neighbor-min-count "$NEIGHBOR_MIN_COUNT" "$@"

echo "=== Phase 3/3: adversarial closure (Ev, margin predictor) ==="
run_audit --closure "$ADVERSARIAL_CLOSURE" --adversarial "$@"

echo "=== Audit suite complete ==="
