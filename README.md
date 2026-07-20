# HALO

![Tests](badges/tests.svg)
![Coverage](badges/coverage.svg)

HALO is a causal audit of forgetting in language models with external memory.
It separates knowledge retained in model parameters from knowledge recovered
through related memory entries or nearby retrieval keys.

## Audit design

Each fact is evaluated in three database states:

- `FULL`: memory unchanged and retrieval enabled.
- `DEL-ON`: target entries hidden and retrieval enabled.
- `DEL-OFF`: target entries hidden and retrieval disabled.

Deletion is implemented by search-time filtering; the underlying store is not
modified. Evaluation records include retrieval traces and query embeddings.

The primary entanglement and adversarial cohorts contain facts for which the
`FULL` state is correct, the selected entry passes the value-support judge,
and a query embedding is available. Coverage and exclusion counts are reported
separately.

The audit includes:

- cross-state parametric leakage L(f), retrieval recovery R(f), and retrieval
  interference I(f);
- deletion closures over geometric, value, and provenance predicates;
- deletion-efficacy and collateral-damage curves over closure radius;
- a linear representational-leakage probe over frozen query embeddings; and
- adversarial survivor entries placed outside the deletion radius.

## Repository structure

- `src/halo/core/`: backend interface, database states, metrics, and analysis.
- `src/halo/interventions/`: closure construction, filtering, support
  judgments, and adversarial interventions.
- `src/halo/cli/`: command-line orchestration and reporting.
- `src/models/co_lmlm/`: backend for the public Co-LMLM release.
- `scripts/`: data setup and evaluation entry points.

## Installation

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
uv run pytest
```

## Co-LMLM evaluation

The default setup uses the T-REx prompts and the public Co-LMLM retrieval
index. The index requires approximately 113 GB. `INDEX_DIR`, `PROMPTS`, and
`OUTPUT_DIR` override the default paths.

```bash
./scripts/setup_data.sh
./scripts/run_audit_co_lmlm.sh
```

Additional `halo-audit` arguments are passed through by the shell entry point.
For example:

```bash
./scripts/run_audit_co_lmlm.sh \
  --closure geometric \
  --radius-grid 0.95:0.70:0.05 \
  --neighbor-mode cosine
```

The complete evaluation consists of the standard three-state audit, the
entanglement sweep, and the adversarial evaluation:

```bash
./scripts/run_audit_suite_co_lmlm.sh
```

The phases execute sequentially and share a `FULL` pass where applicable.
Partial evaluations resume from disk. Each phase creates a separate W&B run
named `<output-dir>__<mode>`.

The standard audit uses `geometric,value` closure by default. Radius and
adversarial evaluations use `geometric` alone. Relevant configuration variables
are `STANDARD_CLOSURE`, `SWEEP_CLOSURE`, `ADVERSARIAL_CLOSURE`, `RADIUS_GRID`,
`NEIGHBOR_MODE`, `NEIGHBOR_MIN_COUNT`, and `DEL_OFF_MODE`. The legacy predicate
name `semantic` is accepted as an alias for `value`.

### DEL-OFF controls

Two retrieval-disabled controls are available: `null-retrieval`, which permits
decoding after a failed fact lookup, and `forbid-token`, which prevents fact
retrieval tokens. The sensitivity script stores the two evaluations separately.

```bash
./scripts/run_del_off_sensitivity_co_lmlm.sh
```

### Deletion policies

Oracle, geometric, value, provenance, and hybrid closure policies can be
evaluated in separate output directories.

```bash
./scripts/run_policy_matrix_co_lmlm.sh
```

## Outputs

The default output directory is `outputs/trex`. Outputs include JSONL results,
retrieval traces, query-embedding sidecars, closure manifests, metrics CSVs,
and probe summaries.

## License

This project is licensed under the [MIT License](LICENSE).
