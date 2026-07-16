import argparse
import csv
from pathlib import Path

from lmlm_audit.core.probe import (
    ProbeConfig,
    compute_delta_rep,
    load_labels_and_behavioral,
    load_probe_samples,
    run_probe,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fit a linear probe on frozen query embeddings and report "
            "representational leakage (L_rep, Delta_rep)."
        )
    )
    parser.add_argument(
        "--results",
        nargs="+",
        type=Path,
        required=True,
        help=(
            "Audit result JSONL files. FULL rows provide labels; DEL-OFF "
            "rows provide the behavioral leakage baseline."
        ),
    )
    parser.add_argument(
        "--embeddings",
        nargs="+",
        type=Path,
        required=True,
        help="Query-embedding sidecar .npz files.",
    )
    parser.add_argument(
        "--mode",
        choices=["ranking", "classification"],
        default="ranking",
        help=(
            "ranking: ridge-regress to answer features and rank all "
            "candidate answers (valid fact-disjoint even with unique "
            "answers). classification: the draft's argmax over answer "
            "classes (needs answers shared across facts)."
        ),
    )
    parser.add_argument(
        "--state",
        default="FULL",
        help="Sidecar state whose embeddings are probed.",
    )
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ridge-lambda", type=float, default=1.0)
    parser.add_argument("--feature-dim", type=int, default=2048)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/probe"),
        help="Directory for probe_per_fact.csv and probe_summary.csv.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = ProbeConfig(
        mode=args.mode,
        folds=args.folds,
        seed=args.seed,
        ridge_lambda=args.ridge_lambda,
        feature_dim=args.feature_dim,
    )
    samples = load_probe_samples(args.embeddings, state=args.state)
    labels, behavioral = load_labels_and_behavioral(args.results)
    report = run_probe(samples, labels, config)
    delta = compute_delta_rep(report.per_fact, behavioral)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    per_fact_path = args.output_dir / "probe_per_fact.csv"
    summary_path = args.output_dir / "probe_summary.csv"

    per_fact_rows = [
        {
            **row,
            "behavioral_l": behavioral.get(row["fact"]),
        }
        for row in report.per_fact
    ]
    with per_fact_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(per_fact_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(per_fact_rows)

    summary_row = {**report.summary, **delta}
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_row.keys()))
        writer.writeheader()
        writer.writerow(summary_row)

    print(f"Probed {report.summary['facts']} facts "
          f"({report.summary['samples']} embeddings, mode={config.mode}).")
    if report.summary["label_unseen_count"]:
        print(
            f"WARNING: {report.summary['label_unseen_count']} facts have "
            "labels unseen in their training fold; their L_rep is "
            "structurally zero under classification. Consider --mode ranking."
        )
    l_rep_hat = report.summary["l_rep_hat"]
    print(f"L_rep: {l_rep_hat:.3f}" if l_rep_hat is not None else "L_rep: n/a")
    if delta["delta_rep"] is not None:
        print(
            f"Behavioral L: {delta['l_hat']:.3f}, "
            f"Delta_rep: {delta['delta_rep']:.3f} "
            f"over {delta['facts_common']} facts"
        )
    else:
        print("Delta_rep: n/a (no facts with both embeddings and DEL-OFF rows)")
    print(f"Wrote {per_fact_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
