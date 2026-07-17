from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from halo.core.entanglement import fact_key  # noqa: E402
from halo.core.examples import DeletionManifest  # noqa: E402
from halo.interventions.judge import default_support_judge  # noqa: E402
from models.co_lmlm.backend import (  # noqa: E402
    full_trace_unaffected,
    manifest_reuse_fingerprint,
)


def _load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _row_manifest(row: dict) -> DeletionManifest:
    manifest = row.get("deletion_manifest") or {}
    metadata = manifest.get("metadata")
    return DeletionManifest(
        entry_ids=tuple(manifest.get("entry_ids") or ()),
        source_ids=tuple(manifest.get("source_ids") or ()),
        strategy=str(manifest.get("strategy") or "closure"),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _row_seconds(row: dict) -> float | None:
    metadata = row.get("generation_metadata") or {}
    parts = [
        metadata.get("t_generate_s"),
        metadata.get("t_encode_s"),
        metadata.get("t_search_s"),
    ]
    if all(part is None for part in parts):
        return None
    return sum(float(part or 0.0) for part in parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sweep_dir", type=Path, help="Directory with sweep_rho_*.jsonl")
    parser.add_argument(
        "--full-dir",
        type=Path,
        default=None,
        help="Directory with full_results.jsonl (defaults to sweep_dir).",
    )
    args = parser.parse_args()

    full_dir = args.full_dir or args.sweep_dir
    full_path = full_dir / "full_results.jsonl"
    if not full_path.is_file():
        raise SystemExit(
            f"No {full_path}; pass --full-dir pointing at the shared FULL pass "
            "(the <prompts>_full/ directory)."
        )
    full_rows = {fact_key(row): row for row in _load_jsonl(full_path)}

    rho_paths = sorted(args.sweep_dir.glob("sweep_rho_*.jsonl"))
    if not rho_paths:
        raise SystemExit(f"No sweep_rho_*.jsonl files under {args.sweep_dir}.")

    manifests: dict[tuple[str, float], DeletionManifest] = {}
    jobs_by_target: dict[str, set[tuple[str, str]]] = defaultdict(set)
    observed_rows = 0
    observed_generated = 0
    unaffected_rows = 0
    violations: list[str] = []
    seconds: list[float] = []

    for rho_path in rho_paths:
        for row in _load_jsonl(rho_path):
            tag = row.get("sweep") or {}
            target = str(tag.get("target_key", ""))
            rho = tag.get("rho")
            role = str(tag.get("role", ""))
            subject = fact_key(row)
            if not target or rho is None:
                continue
            rho = float(rho)
            observed_rows += 1
            manifests.setdefault((target, rho), _row_manifest(row))
            jobs_by_target[target].add((role, subject))
            row_seconds = _row_seconds(row)
            if row_seconds is not None:
                seconds.append(row_seconds)

            was_reused = bool(tag.get("reused"))
            if not was_reused:
                observed_generated += 1
            full_row = full_rows.get(subject)
            if full_row is None:
                continue
            if full_trace_unaffected(
                full_row, manifests[(target, rho)], default_support_judge
            ):
                unaffected_rows += 1
                if not was_reused and row.get("model_output") != full_row.get(
                    "model_output"
                ):
                    violations.append(
                        f"target={target} role={role} subject={subject} "
                        f"rho={rho}: generated {row.get('model_output')!r} "
                        f"!= FULL {full_row.get('model_output')!r}"
                    )

    radii_by_target: dict[str, list[float]] = defaultdict(list)
    for target, rho in manifests:
        radii_by_target[target].append(rho)
    distinct_counts: list[int] = []
    projected = 0
    cache: set[tuple[str, object]] = set()
    for target, jobs in jobs_by_target.items():
        radii = sorted(radii_by_target[target], reverse=True)
        fingerprints = {
            rho: manifest_reuse_fingerprint(manifests[(target, rho)]) for rho in radii
        }
        distinct_counts.append(
            len({fp for fp in fingerprints.values() if fp is not None})
            + sum(1 for fp in fingerprints.values() if fp is None)
        )
        for role, subject in sorted(jobs):
            for rho in radii:
                fingerprint = fingerprints[rho]
                cache_key = (subject, fingerprint) if fingerprint is not None else None
                if cache_key is not None and cache_key in cache:
                    continue
                full_row = full_rows.get(subject)
                if full_row is not None and full_trace_unaffected(
                    full_row, manifests[(target, rho)], default_support_judge
                ):
                    if cache_key is not None:
                        cache.add(cache_key)
                    continue
                projected += 1
                if cache_key is not None:
                    cache.add(cache_key)

    targets = len(jobs_by_target)
    mean_d = sum(distinct_counts) / len(distinct_counts) if distinct_counts else 0.0
    mean_seconds = sum(seconds) / len(seconds) if seconds else None
    print(f"Sweep rows observed:        {observed_rows} across {len(rho_paths)} radii")
    print(f"Targets:                    {targets}")
    print(f"Mean distinct manifests D:  {mean_d:.2f} per target")
    if observed_rows:
        print(
            f"Reuse-rule unaffected a:    {unaffected_rows}/{observed_rows} rows "
            f"({unaffected_rows / observed_rows:.1%})"
        )
        print(
            f"Projected generations:      {projected} "
            f"({projected / observed_rows:.1%} of observed; "
            f"~{observed_rows / max(projected, 1):.1f}x fewer)"
        )
    if mean_seconds is not None:
        old_hours = observed_generated * mean_seconds / 3600
        new_hours = projected * mean_seconds / 3600
        print(
            f"Wall-clock projection:      ~{old_hours:.1f} h -> ~{new_hours:.1f} h "
            f"at {mean_seconds:.2f} s/generation (single process)"
        )
    if violations:
        print(f"\nVALIDATION FAILED: {len(violations)} rows contradict the reuse rule:")
        for violation in violations[:20]:
            print(f"  {violation}")
        if len(violations) > 20:
            print(f"  ... and {len(violations) - 20} more")
        raise SystemExit(1)
    print("Validation: OK — no observed row contradicts the reuse rule.")


if __name__ == "__main__":
    main()
