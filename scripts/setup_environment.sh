#!/usr/bin/env bash
# One-time environment setup for HALO: installs uv (per the README) and the
# system libraries the Python dependencies need (OpenBLAS for faiss).
# Run this once on a fresh machine before scripts/run_audit*_co_lmlm.sh.
set -euo pipefail

if ! command -v uv >/dev/null; then
    echo "Installing uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer drops uv in ~/.local/bin; make it visible to this shell.
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed: $(uv --version)"
fi

# faiss-cpu links against the system OpenBLAS, which fresh instances lack.
if command -v apt-get >/dev/null && ! ldconfig -p | grep -q libopenblas.so.0; then
    echo "libopenblas.so.0 not found; installing libopenblas0 (needed by faiss) ..."
    sudo apt-get update -qq && sudo apt-get install -y -qq libopenblas0
fi

echo "Environment setup complete."
