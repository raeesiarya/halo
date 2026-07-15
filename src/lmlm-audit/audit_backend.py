import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from database_states import DatabaseState, retrieval_enabled
from equivalence import prompt_row_aliases


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = tuple(str(item) for item in value if item is not None)
    else:
        values = (str(value),)
    return tuple(sorted({value.strip() for value in values if value.strip()}))


_MISSING = object()


def _first_present(*candidates: tuple[Mapping[str, Any], str]) -> Any:
    for mapping, key in candidates:
        value = mapping.get(key, _MISSING)
        if value is not _MISSING:
            return value
    return None


@dataclass(frozen=True)
class DeletionManifest:
    entry_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    strategy: str = "oracle-entry"
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_ids", _string_tuple(self.entry_ids))
        object.__setattr__(self, "source_ids", _string_tuple(self.source_ids))
        object.__setattr__(self, "strategy", str(self.strategy))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_prompt_row(cls, prompt_row: Mapping[str, Any]) -> "DeletionManifest":
        embedded = prompt_row.get("deletion_manifest")
        manifest_row = dict(embedded) if isinstance(embedded, Mapping) else {}

        entry_ids = _first_present(
            (manifest_row, "entry_ids"),
            (manifest_row, "deletion_entry_ids"),
            (prompt_row, "deletion_entry_ids"),
            (prompt_row, "oracle_entry_ids"),
            (prompt_row, "entry_ids"),
        )
        source_ids = _first_present(
            (manifest_row, "source_ids"),
            (prompt_row, "source_ids"),
        )
        strategy = str(
            manifest_row.get("strategy")
            or prompt_row.get("deletion_strategy")
            or "oracle-entry"
        )
        metadata = manifest_row.get("metadata")
        return cls(
            entry_ids=_string_tuple(entry_ids),
            source_ids=_string_tuple(source_ids),
            strategy=strategy,
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        )

    @property
    def manifest_id(self) -> str:
        payload = json.dumps(self.as_dict(include_id=False), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @property
    def is_empty(self) -> bool:
        return not self.entry_ids and not self.source_ids

    def as_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        result = {
            "entry_ids": list(self.entry_ids),
            "source_ids": list(self.source_ids),
            "strategy": self.strategy,
            "metadata": dict(self.metadata),
        }
        if include_id:
            result["manifest_id"] = self.manifest_id
        return result


@dataclass(frozen=True)
class AuditExample:
    prompt: str
    ground_truth: str
    fact_id: str | int | None = None
    prompt_id: str | int | None = None
    object_aliases: tuple[str, ...] = ()
    subject: str | None = None
    subject_aliases: tuple[str, ...] = ()
    relation: str | None = None
    relation_aliases: tuple[str, ...] = ()
    deletion_manifest: DeletionManifest = field(default_factory=DeletionManifest)
    source_row: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    @classmethod
    def from_prompt_row(cls, prompt_row: Mapping[str, Any]) -> "AuditExample":
        if "prompt_text" not in prompt_row:
            raise ValueError("Audit prompt row is missing required field 'prompt_text'.")
        if "gold_object" not in prompt_row:
            raise ValueError("Audit prompt row is missing required field 'gold_object'.")

        row = dict(prompt_row)
        return cls(
            fact_id=row.get("fact_id"),
            prompt_id=row.get("prompt_id"),
            prompt=str(row["prompt_text"]),
            ground_truth=str(row["gold_object"]),
            object_aliases=prompt_row_aliases(row, "object"),
            subject=(str(row["subject"]) if row.get("subject") is not None else None),
            subject_aliases=prompt_row_aliases(row, "subject"),
            relation=(
                str(row["relation"]) if row.get("relation") is not None else None
            ),
            relation_aliases=prompt_row_aliases(row, "relation"),
            deletion_manifest=DeletionManifest.from_prompt_row(row),
            source_row=row,
        )


@dataclass(frozen=True)
class AuditObservation:
    model_output: str
    retrieval_trace: Mapping[str, Any] | None = None
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class AuditBackend(Protocol):
    def generate(
        self,
        example: AuditExample,
        state: DatabaseState,
        *,
        max_new_tokens: int = 12,
    ) -> AuditObservation:
        ...


def default_retrieval_trace(state: DatabaseState) -> dict[str, Any]:
    return {
        "state": state.value,
        "trace_available": False,
        "trace_complete": False,
        "retrieval_enabled": retrieval_enabled(state),
        "retrieval_triggered": False,
        "threshold_fallback": False,
        "lookup_query": None,
        "threshold": None,
        "all_candidates": [],
        "deleted_candidates": [],
        "retained_candidates": [],
        "selected_candidate": None,
        "selected_value": None,
        "retrieval_events": [],
        "error": None,
    }


def audit_example(
    backend: AuditBackend,
    example: AuditExample,
    state: DatabaseState,
    *,
    max_new_tokens: int = 12,
) -> dict[str, Any]:
    observation = backend.generate(
        example,
        state,
        max_new_tokens=max_new_tokens,
    )
    retrieval_trace = default_retrieval_trace(state)
    if observation.retrieval_trace is not None:
        supplied_trace = dict(observation.retrieval_trace)
        supplied_state = supplied_trace.get("state")
        if supplied_state is not None and supplied_state != state.value:
            raise ValueError(
                f"Backend returned trace state {supplied_state!r} for {state.value!r}."
            )
        retrieval_trace.update(supplied_trace)
        retrieval_trace["state"] = state.value
        if "trace_available" not in supplied_trace:
            retrieval_trace["trace_available"] = True
        if "trace_complete" not in supplied_trace:
            retrieval_trace["trace_complete"] = supplied_trace.get("error") is None

    return {
        "fact_id": example.fact_id,
        "prompt_id": example.prompt_id,
        "subject": example.subject,
        "subject_aliases": list(example.subject_aliases),
        "relation": example.relation,
        "relation_aliases": list(example.relation_aliases),
        "state": state.value,
        "prompt": example.prompt,
        "ground_truth": example.ground_truth,
        "object_aliases": list(example.object_aliases),
        "deletion_manifest": example.deletion_manifest.as_dict(),
        "model_output": observation.model_output,
        "retrieval_trace": retrieval_trace,
        "generation_metadata": dict(observation.generation_metadata),
    }


def validate_intervention_results(
    results: list[dict[str, Any]],
    *,
    expected_states: list[DatabaseState],
) -> None:
    if not results:
        return
    states = [result.get("state") for result in results]
    expected = [state.value for state in expected_states]
    if states != expected:
        raise ValueError(f"Intervention states {states!r} do not match {expected!r}.")

    identity_fields = ("fact_id", "prompt_id", "prompt", "ground_truth")
    for field_name in identity_fields:
        values = {json.dumps(result.get(field_name), sort_keys=True) for result in results}
        if len(values) != 1:
            raise ValueError(f"Cross-state rows disagree on {field_name!r}.")

    manifests = {
        json.dumps(result.get("deletion_manifest"), sort_keys=True)
        for result in results
    }
    if len(manifests) != 1:
        raise ValueError("Cross-state rows do not share one deletion manifest.")

    for result in results:
        trace = result.get("retrieval_trace") or {}
        if trace.get("state") != result.get("state"):
            raise ValueError("Result state and retrieval-trace state disagree.")

        if result.get("state") == DatabaseState.DEL_OFF.value:
            if trace.get("retrieval_enabled") is not False:
                raise ValueError("DEL-OFF must disable retrieval.")
            if trace.get("retrieval_triggered") is True:
                raise ValueError("DEL-OFF unexpectedly triggered retrieval.")
            if trace.get("retrieval_events"):
                raise ValueError("DEL-OFF unexpectedly recorded retrieval events.")

        if result.get("state") == DatabaseState.DEL_ON.value:
            manifest = result.get("deletion_manifest") or {}
            excluded_entry_ids = set(manifest.get("entry_ids") or [])
            excluded_source_ids = set(manifest.get("source_ids") or [])
            selected_candidates = [trace.get("selected_candidate")]
            selected_candidates.extend(
                event.get("selected_candidate")
                for event in trace.get("retrieval_events") or []
            )
            for selected in selected_candidates:
                if not isinstance(selected, Mapping):
                    continue
                if selected.get("entry_id") in excluded_entry_ids:
                    raise ValueError(
                        "DEL-ON selected an entry from its deletion manifest."
                    )
                if selected.get("source_id") in excluded_source_ids:
                    raise ValueError(
                        "DEL-ON selected a source from its deletion manifest."
                    )
