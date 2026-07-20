# Result status

The files in this directory predate the current evaluation protocol and are
retained as preliminary outputs. Their limitations are:

- sweep and adversarial cohorts were not restricted to `FULL`-correct facts
  with verified supporting retrievals;
- geometric and value filtering were combined in the radius sweep;
- some cosine targets had empty neighbor sets;
- adversarial correctness did not require selection of the injected entry; and
- only the `null-retrieval` DEL-OFF control was evaluated.

These outputs are not used for final reporting. Current evaluations are defined
by `scripts/run_audit_suite_co_lmlm.sh`,
`scripts/run_del_off_sensitivity_co_lmlm.sh`, and
`scripts/run_policy_matrix_co_lmlm.sh`.
