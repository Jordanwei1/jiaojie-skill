"""Deterministic native validation and owned-result issuance."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .canonicalize import canonicalize, loads_strict, sha256_digest, sha256_hex
from .language import is_receipt_payload, qualify_languages
from .package import (
    MAX_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_OBJECT_BYTES,
    MAX_TOTAL_BYTES,
    BundleSource,
    SCHEMA_DIRECTORY,
    bundled_materiality_ref,
    identify_transport,
    manifest_reference_issues,
    parse_t0,
    root_capability_issues,
    root_capability_warnings,
    root_result_key_hits,
    root_warm_mismatches,
    state_resource_issues,
)
from .projection import (
    WARM_KEYS,
    canonical_state_digest,
    derived_digest_v1,
    review_projection_v1,
    state_projection_v1,
)
from .schema import SchemaProblem, SchemaStore, Validator
from .security import scan_bytes
from .util import (
    LCHError,
    atomic_commit_no_replace,
    check_json_depth,
    lexical_absolute,
    read_bytes,
    safe_relative_path,
    secure_output_path,
)


IMPLEMENTATION_VERSION = "lch-reference-python-0.1.0"


RECORD_AXIS_VALUES: dict[str, dict[str, frozenset[str]]] = {
    "intent": {
        "lifecycle": frozenset({"PROPOSED", "ACTIVE", "SUPERSEDED", "ABANDONED"}),
    },
    "decision": {
        "lifecycle": frozenset({"CANDIDATE", "ACTIVE", "SUPERSEDED", "REJECTED"}),
    },
    "claim": {
        "epistemic_basis": frozenset(
            {"USER_STATED", "TOOL_OBSERVED", "EXTERNAL_ASSERTED", "INFERRED", "ASSUMED", "UNKNOWN"}
        ),
        "verification": frozenset({"UNVERIFIED", "CORROBORATED", "DISPUTED", "REFUTED"}),
        "temporal_validity": frozenset({"CURRENT", "STALE", "EXPIRED", "UNKNOWN"}),
    },
    "constraint": {
        "lifecycle": frozenset({"PROPOSED", "ACTIVE", "SUPERSEDED", "RELEASED"}),
        "compliance": frozenset({"SATISFIED", "VIOLATED", "UNKNOWN"}),
    },
    "question": {
        "lifecycle": frozenset({"OPEN", "ANSWERED", "DEFERRED", "CANCELLED"}),
    },
    "attempt": {
        "outcome": frozenset({"SUCCEEDED", "FAILED", "INCONCLUSIVE", "ABORTED"}),
    },
    "artifact": {
        "availability": frozenset({"PRESENT", "MISSING", "EXTERNAL_ONLY", "REDACTED"}),
        "freshness": frozenset({"CURRENT", "STALE", "UNKNOWN"}),
    },
    "preference": {
        "lifecycle": frozenset({"PROPOSED", "ACTIVE", "SUPERSEDED", "RELEASED"}),
        "authority": frozenset({"USER_CONFIRMED", "OBSERVED_PATTERN", "INFERRED"}),
    },
    "next_action": {
        "eligibility": frozenset({"READY", "BLOCKED", "COMPLETED", "SUPERSEDED"}),
    },
    "__action_graph__": {
        "lifecycle": frozenset({"ACTIVE"}),
    },
}


def _problem(code: str, message: str, *, object_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if object_id is not None:
        result["object_id"] = object_id
    return result


def _schema_problems(
    validator: Validator,
    value: Any,
    schema_name: str,
    *,
    object_id: str,
) -> list[dict[str, Any]]:
    return [
        _problem("SCHEMA_FAIL", item.message + " at " + item.path, object_id=object_id)
        for item in validator.validate(value, schema_name)
    ]


def _unique(values: Iterable[Any], *, label: str, issues: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            issues.append(_problem("INVALID_ID", f"{label} must be a stable string ID"))
            continue
        if value in result:
            issues.append(_problem("DUPLICATE_ID", f"duplicate {label}", object_id=str(value)))
        result.add(value)
    return result


def _acyclic(nodes: set[str], edges: list[tuple[str, str]]) -> bool:
    incoming = {node: 0 for node in nodes}
    children = {node: set() for node in nodes}
    for source, target in edges:
        if source in nodes and target in nodes and target not in children[source]:
            children[source].add(target)
            incoming[target] += 1
    ready = sorted(node for node, count in incoming.items() if count == 0)
    visited = 0
    while ready:
        node = ready.pop(0)
        visited += 1
        for child in sorted(children[node]):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
                ready.sort()
    return visited == len(nodes)


def _state_invariants(
    warm: dict[str, Any],
    object_bytes: dict[str, bytes],
    root: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    records = warm.get("records", [])
    events = warm.get("transition_events", [])
    graph = warm.get("action_graph", {})
    if not isinstance(records, list) or not isinstance(events, list) or not isinstance(graph, dict):
        return [_problem("STATE_SHAPE_FAIL", "WARM state collections have invalid types", object_id="warm_state")]
    record_by_id = {
        item.get("id"): item for item in records if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    source_inventory_value = warm.get("source_inventory")
    source_inventory_entries = (
        source_inventory_value.get("entries", [])
        if isinstance(source_inventory_value, dict)
        and isinstance(source_inventory_value.get("entries"), list)
        else []
    )
    source_entry_by_id = {
        item.get("source_id"): item
        for item in source_inventory_entries
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    _unique(
        [item.get("id") for item in records if isinstance(item, dict)],
        label="record ID",
        issues=issues,
    )
    event_by_id = {
        item.get("event_id"): item for item in events if isinstance(item, dict) and isinstance(item.get("event_id"), str)
    }
    _unique(
        [item.get("event_id") for item in events if isinstance(item, dict)],
        label="event ID",
        issues=issues,
    )
    revision = graph.get("action_graph_revision", {}) if isinstance(graph.get("action_graph_revision"), dict) else {}
    graph_record_id = revision.get("record_id")
    try:
        projected_graph = state_projection_v1(warm)["action_graph"]
        revision_projection = dict(projected_graph["action_graph_revision"])
        revision_projection.pop("revision_digest", None)
        graph_digest_projection = dict(projected_graph)
        graph_digest_projection["action_graph_revision"] = revision_projection
        expected_revision_digest = derived_digest_v1(
            "revision_digest",
            graph_digest_projection,
            str(warm.get("protocol_version", "")),
        )
    except Exception:
        expected_revision_digest = None
    if revision.get("revision_digest") != expected_revision_digest:
        issues.append(
            _problem(
                "ACTION_GRAPH_REVISION_DIGEST_FAIL",
                "action graph revision digest does not match lch-derived-digest-v1",
                object_id=str(graph_record_id) if isinstance(graph_record_id, str) else None,
            )
        )
    valid_event_records = set(record_by_id)
    if isinstance(graph_record_id, str):
        valid_event_records.add(graph_record_id)

    event_edges: list[tuple[str, str]] = []
    streams: dict[str, set[int]] = {}
    for event_id, event in event_by_id.items():
        event_record_id = event.get("record_id")
        if event_record_id not in valid_event_records:
            issues.append(_problem("EVENT_RECORD_DANGLING", "event record_id is dangling", object_id=event_id))
        record_type = (
            "__action_graph__"
            if event_record_id == graph_record_id
            else record_by_id.get(event_record_id, {}).get("type")
        )
        legal_axes = RECORD_AXIS_VALUES.get(record_type, {})
        for projection_name in ("from", "to"):
            projection = event.get(projection_name)
            if projection is None:
                continue
            if not isinstance(projection, dict):
                continue
            for axis, value in projection.items():
                if axis not in legal_axes:
                    issues.append(
                        _problem(
                            "EVENT_AXIS_ILLEGAL",
                            f"event {projection_name} contains an axis illegal for record type {record_type}",
                            object_id=event_id,
                        )
                    )
                elif value not in legal_axes[axis]:
                    issues.append(
                        _problem(
                            "EVENT_AXIS_VALUE_ILLEGAL",
                            f"event {projection_name} contains a value illegal for record type {record_type}",
                            object_id=event_id,
                        )
                    )
        previous = event.get("previous_event_ids", [])
        if not isinstance(previous, list):
            continue
        if len(previous) != len({item for item in previous if isinstance(item, str)}):
            issues.append(
                _problem(
                    "EVENT_PARENT_DUPLICATE",
                    "event predecessor IDs must be unique",
                    object_id=event_id,
                )
            )
        if event.get("from") is None and previous:
            issues.append(_problem("GENESIS_PREDECESSOR", "genesis event cannot have predecessors", object_id=event_id))
        if event.get("from") is None and isinstance(event.get("to"), dict):
            if set(event["to"]) != set(legal_axes):
                issues.append(
                    _problem(
                        "GENESIS_AXIS_INCOMPLETE",
                        "genesis event must establish every axis for its resolved record type",
                        object_id=event_id,
                    )
                )
        if event.get("from") is not None and not previous:
            issues.append(_problem("NON_GENESIS_NO_PREDECESSOR", "non-genesis event requires a predecessor", object_id=event_id))
        if previous and (
            not isinstance(event.get("from"), dict)
            or not event["from"]
        ):
            issues.append(
                _problem(
                    "EVENT_FROM_EMPTY",
                    "non-genesis event from projection must be a nonempty object",
                    object_id=event_id,
                )
            )
        if not isinstance(event.get("to"), dict) or not event["to"]:
            issues.append(
                _problem(
                    "EVENT_TO_EMPTY",
                    "event to projection must be a nonempty object",
                    object_id=event_id,
                )
            )
        for parent in previous:
            if parent not in event_by_id:
                issues.append(_problem("EVENT_PARENT_DANGLING", "event predecessor is missing", object_id=event_id))
            else:
                event_edges.append((parent, event_id))
                if event_by_id[parent].get("record_id") != event.get("record_id"):
                    issues.append(_problem("EVENT_PARENT_RECORD_MISMATCH", "event predecessor belongs to another record", object_id=event_id))
                if (
                    event_by_id[parent].get("event_stream_id") == event.get("event_stream_id")
                    and event_by_id[parent].get("event_sequence", -1) >= event.get("event_sequence", -1)
                ):
                    issues.append(_problem("EVENT_SEQUENCE_REVERSED", "event sequence does not increase", object_id=event_id))
        stream_id = event.get("event_stream_id")
        sequence = event.get("event_sequence")
        if isinstance(stream_id, str) and isinstance(sequence, int):
            seen = streams.setdefault(stream_id, set())
            if sequence in seen:
                issues.append(_problem("EVENT_SEQUENCE_DUPLICATE", "duplicate sequence in event stream", object_id=event_id))
            seen.add(sequence)
    if not _acyclic(set(event_by_id), event_edges):
        issues.append(_problem("EVENT_GRAPH_CYCLE", "transition event graph contains a cycle", object_id="warm_state"))

    state_cache: dict[str, dict[str, Any] | None] = {}

    def projected_event_state(event_id: str, visiting: set[str]) -> dict[str, Any] | None:
        if event_id in state_cache:
            return state_cache[event_id]
        if event_id in visiting:
            return None
        event = event_by_id.get(event_id)
        if event is None:
            return None
        visiting.add(event_id)
        parents = event.get("previous_event_ids", [])
        parent_states: list[tuple[str, dict[str, Any]]] = []
        if isinstance(parents, list):
            for parent_id in sorted(
                (item for item in parents if isinstance(item, str)),
                key=lambda item: item.encode("utf-16-be", errors="strict"),
            ):
                if not isinstance(parent_id, str):
                    continue
                parent_state = projected_event_state(parent_id, visiting)
                if parent_state is not None:
                    parent_states.append((parent_id, parent_state))
        if not parent_states:
            state: dict[str, Any] = {}
        else:
            state = dict(parent_states[0][1])
        event_record_id = event.get("record_id")
        record_type = (
            "__action_graph__"
            if event_record_id == graph_record_id
            else record_by_id.get(event_record_id, {}).get("type")
        )
        legal_axes = RECORD_AXIS_VALUES.get(record_type, {})
        prior = event.get("from")
        target = event.get("to")
        if len(parent_states) == 1:
            if not isinstance(prior, dict) or not prior:
                issues.append(
                    _problem(
                        "EVENT_FROM_EMPTY",
                        "single-parent event requires a nonempty partial from projection",
                        object_id=event_id,
                    )
                )
            elif any(state.get(key) != value for key, value in prior.items()):
                issues.append(
                    _problem(
                        "EVENT_FROM_MISMATCH",
                        "event from projection disagrees with its predecessor state",
                        object_id=event_id,
                    )
                )
        elif len(parent_states) > 1:
            if set(state) != set(legal_axes):
                issues.append(
                    _problem(
                        "EVENT_MERGE_BASE_INCOMPLETE",
                        "deterministic merge base does not contain every legal record axis",
                        object_id=event_id,
                    )
                )
            if not isinstance(prior, dict) or prior != state:
                issues.append(
                    _problem(
                        "EVENT_MERGE_FROM_MISMATCH",
                        "multi-parent event from projection must equal the complete UTF-16-sorted base projection",
                        object_id=event_id,
                    )
                )
            differing_axes = {
                axis
                for axis in legal_axes
                if len({candidate.get(axis) for _, candidate in parent_states}) > 1
            }
            if not isinstance(target, dict) or not differing_axes.issubset(target):
                issues.append(
                    _problem(
                        "EVENT_MERGE_AXIS_OMITTED",
                        "multi-parent event to projection must explicitly resolve every axis that differs among parents",
                        object_id=event_id,
                    )
                )
        elif isinstance(prior, dict):
            issues.append(
                _problem(
                    "EVENT_FROM_MISMATCH",
                    "genesis event cannot carry a from projection",
                    object_id=event_id,
                )
            )
        if isinstance(target, dict):
            state.update(target)
        reopens_terminal_parent = any(
            (
                candidate.get("lifecycle") in {"REJECTED", "SUPERSEDED"}
                and state.get("lifecycle") != candidate.get("lifecycle")
            )
            or (
                candidate.get("eligibility") == "SUPERSEDED"
                and state.get("eligibility") != "SUPERSEDED"
            )
            for _, candidate in parent_states
        )
        principal_id = event.get("principal_id")
        source_refs = event.get("source_refs")
        user_evidence_bound = bool(
            isinstance(principal_id, str)
            and isinstance(source_refs, list)
            and any(
                isinstance(source_ref, str)
                and isinstance(source_entry_by_id.get(source_ref), dict)
                and source_entry_by_id[source_ref].get("source_role") == "user"
                and source_entry_by_id[source_ref].get("source_principal_id") == principal_id
                for source_ref in source_refs
            )
        )
        if reopens_terminal_parent and (
            event.get("reason_kind") != "USER_CONFIRMED"
            or not user_evidence_bound
        ):
            issues.append(
                _problem(
                    "TERMINAL_STATE_REOPEN_UNCONFIRMED",
                    "reopening rejected or superseded work requires a new USER_CONFIRMED event with principal-bound source evidence",
                    object_id=event_id,
                )
            )
        visiting.remove(event_id)
        state_cache[event_id] = state
        return state

    record_heads: dict[str, set[str]] = {}

    for record_id, record in record_by_id.items():
        transition_ids = record.get("transition_event_ids", [])
        if isinstance(transition_ids, list):
            for event_id in transition_ids:
                event = event_by_id.get(event_id)
                if event is None or event.get("record_id") != record_id:
                    issues.append(_problem("RECORD_EVENT_MISMATCH", "record transition event is missing or belongs elsewhere", object_id=record_id))
            referenced = {item for item in transition_ids if isinstance(item, str)}
            actual = {
                event_id
                for event_id, event in event_by_id.items()
                if event.get("record_id") == record_id
            }
            if referenced != actual:
                issues.append(
                    _problem(
                        "RECORD_EVENT_CLOSURE_FAIL",
                        "record transition_event_ids do not name exactly its events",
                        object_id=record_id,
                    )
                )
            non_heads = {
                parent
                for event_id in referenced
                for parent in event_by_id.get(event_id, {}).get("previous_event_ids", [])
                if isinstance(parent, str) and parent in referenced
            }
            heads = referenced - non_heads
            record_heads[record_id] = heads
            if len(heads) != 1:
                issues.append(
                    _problem(
                        "EVENT_HEAD_COUNT_FAIL",
                        "record must have one unambiguous current event head",
                        object_id=record_id,
                    )
                )
            else:
                head_state = projected_event_state(next(iter(heads)), set())
                legal_axes = RECORD_AXIS_VALUES.get(record.get("type"), {})
                cached_axes = {
                    axis: record.get(axis)
                    for axis in legal_axes
                    if axis in record
                }
                if (
                    head_state is None
                    or set(head_state) != set(legal_axes)
                    or cached_axes != head_state
                ):
                    issues.append(
                        _problem(
                            "RECORD_AXIS_PROJECTION_FAIL",
                            "record cached state axes disagree with its event head projection",
                            object_id=record_id,
                        )
                    )
        for span in record.get("evidence_spans", []) if isinstance(record.get("evidence_spans"), list) else []:
            if not isinstance(span, dict):
                continue
            object_id = span.get("object_id")
            data = object_bytes.get(object_id)
            start, end = span.get("byte_start"), span.get("byte_end")
            if data is None:
                issues.append(_problem("EVIDENCE_OBJECT_DANGLING", "evidence object bytes are unavailable", object_id=record_id))
            elif not isinstance(start, int) or not isinstance(end, int) or start > end or end > len(data):
                issues.append(_problem("EVIDENCE_RANGE_FAIL", "evidence byte range is invalid", object_id=record_id))
            elif sha256_digest(data[start:end]) != span.get("sha256_raw"):
                issues.append(_problem("EVIDENCE_DIGEST_FAIL", "evidence span digest does not match raw bytes", object_id=record_id))

        for related_id in record.get("related_records", []) if isinstance(record.get("related_records"), list) else []:
            if related_id not in record_by_id:
                issues.append(
                    _problem(
                        "RELATED_RECORD_DANGLING",
                        "record related_records contains a dangling record ID",
                        object_id=record_id,
                    )
                )
        ordering = record.get("ordering") if isinstance(record.get("ordering"), dict) else {}
        for parent_id in ordering.get("causal_parent_ids", []) if isinstance(ordering.get("causal_parent_ids"), list) else []:
            if parent_id not in record_by_id:
                issues.append(
                    _problem(
                        "CAUSAL_RECORD_DANGLING",
                        "record ordering causal parent is missing",
                        object_id=record_id,
                    )
                )

    graph_event_ids = {
        event_id
        for event_id, event in event_by_id.items()
        if event.get("record_id") == graph_record_id
    }
    graph_non_heads = {
        parent_id
        for event_id in graph_event_ids
        for parent_id in event_by_id[event_id].get("previous_event_ids", [])
        if isinstance(parent_id, str) and parent_id in graph_event_ids
    }
    graph_heads = graph_event_ids - graph_non_heads
    if len(graph_heads) != 1 or revision.get("activated_by_event_id") not in graph_heads:
        issues.append(
            _problem(
                "ACTION_GRAPH_REVISION_HEAD_FAIL",
                "active revision must name the unique current action-graph event head",
                object_id=str(graph_record_id) if isinstance(graph_record_id, str) else None,
            )
        )
    elif projected_event_state(next(iter(graph_heads)), set()) != {"lifecycle": "ACTIVE"}:
        issues.append(
            _problem(
                "ACTION_GRAPH_REVISION_STATE_FAIL",
                "active action-graph event head must project only lifecycle ACTIVE",
                object_id=str(graph_record_id) if isinstance(graph_record_id, str) else None,
            )
        )

    actions = graph.get("actions", []) if isinstance(graph.get("actions"), list) else []
    edges = graph.get("action_edges", []) if isinstance(graph.get("action_edges"), list) else []
    groups = graph.get("action_groups", []) if isinstance(graph.get("action_groups"), list) else []
    action_by_id = {
        item.get("action_id"): item for item in actions if isinstance(item, dict) and isinstance(item.get("action_id"), str)
    }
    external_dependencies = (
        warm.get("boundaries", {}).get("external_state_dependencies", [])
        if isinstance(warm.get("boundaries"), dict)
        else []
    )
    declared_external_ids: set[str] = set()
    for dependency in external_dependencies if isinstance(external_dependencies, list) else []:
        if not isinstance(dependency, dict):
            continue
        for key, value in dependency.items():
            if (
                isinstance(key, str)
                and (key == "id" or key.endswith("_id"))
                and isinstance(value, str)
            ):
                declared_external_ids.add(value)
    resolvable_requirement_ids = set(record_by_id) | declared_external_ids
    declared_capability_ids: set[str] = set()
    if isinstance(root, dict):
        declared_capability_ids.update(
            item.get("id")
            for item in root.get("profiles", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        declared_capability_ids.update(
            item
            for item in root.get("must_understand", [])
            if isinstance(item, str)
        )
    _unique([item.get("action_id") for item in actions if isinstance(item, dict)], label="action ID", issues=issues)
    _unique([item.get("edge_id") for item in edges if isinstance(item, dict)], label="action edge ID", issues=issues)
    _unique([item.get("group_id") for item in groups if isinstance(item, dict)], label="action group ID", issues=issues)
    revision_id = revision.get("revision_id")
    previous_revision_ids = revision.get("previous_revision_ids", [])
    if isinstance(previous_revision_ids, list):
        _unique(previous_revision_ids, label="previous action-graph revision ID", issues=issues)
        if revision_id in previous_revision_ids:
            issues.append(
                _problem(
                    "ACTION_GRAPH_REVISION_SELF_PARENT",
                    "active action-graph revision cannot name itself as a predecessor",
                    object_id=str(revision_id) if isinstance(revision_id, str) else None,
                )
            )
    dependency_edges: list[tuple[str, str]] = []
    excludes: set[tuple[str, str]] = set()
    for action_id, action in action_by_id.items():
        record = record_by_id.get(action.get("next_action_record_id"))
        if record is None or record.get("type") != "next_action":
            issues.append(_problem("ACTION_RECORD_DANGLING", "action next_action_record_id is invalid", object_id=action_id))
        elif action.get("eligibility_projection") != record.get("eligibility"):
            issues.append(_problem("ACTION_ELIGIBILITY_MISMATCH", "action eligibility disagrees with next_action record", object_id=action_id))
        for head in action.get("event_head_ids", []) if isinstance(action.get("event_head_ids"), list) else []:
            event = event_by_id.get(head)
            if event is None or event.get("record_id") != action.get("next_action_record_id"):
                issues.append(_problem("ACTION_EVENT_HEAD_FAIL", "action event head is dangling or belongs elsewhere", object_id=action_id))
        declared_heads = {
            item for item in action.get("event_head_ids", [])
            if isinstance(item, str)
        }
        if declared_heads != record_heads.get(action.get("next_action_record_id"), set()):
            issues.append(
                _problem(
                    "ACTION_EVENT_HEAD_FAIL",
                    "action event_head_ids do not equal the next-action record heads",
                    object_id=action_id,
                )
            )
        for authorization_id in action.get("required_authorization_specs", []) if isinstance(action.get("required_authorization_specs"), list) else []:
            if authorization_id not in resolvable_requirement_ids:
                issues.append(
                    _problem(
                        "ACTION_AUTHORIZATION_REF_DANGLING",
                        "required authorization specification does not resolve to a record or external dependency",
                        object_id=action_id,
                    )
                )
        for capability_id in action.get("required_capabilities", []) if isinstance(action.get("required_capabilities"), list) else []:
            if capability_id not in declared_capability_ids:
                issues.append(
                    _problem(
                        "ACTION_CAPABILITY_REF_DANGLING",
                        "required capability does not resolve to a selected Profile or must-understand Feature",
                        object_id=action_id,
                    )
                )
        for check_id in action.get("external_state_checks", []) if isinstance(action.get("external_state_checks"), list) else []:
            if check_id not in declared_external_ids:
                issues.append(
                    _problem(
                        "ACTION_EXTERNAL_CHECK_DANGLING",
                        "external-state check does not resolve to an external dependency",
                        object_id=action_id,
                    )
                )
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source, target, relation = edge.get("source_action_id"), edge.get("target_action_id"), edge.get("relation")
        if source not in action_by_id or target not in action_by_id:
            issues.append(_problem("ACTION_EDGE_DANGLING", "action edge endpoint is missing", object_id=edge.get("edge_id")))
            continue
        condition_id = edge.get("condition_id")
        if condition_id is not None and condition_id not in resolvable_requirement_ids:
            issues.append(
                _problem(
                    "ACTION_CONDITION_DANGLING",
                    "action edge condition does not resolve to a record or external dependency",
                    object_id=edge.get("edge_id"),
                )
            )
        if source == target:
            issues.append(
                _problem(
                    "ACTION_EDGE_SELF",
                    "action edge cannot target its source action",
                    object_id=edge.get("edge_id"),
                )
            )
        if relation == "REQUIRES":
            dependency_edges.append((target, source))
        elif relation == "BEFORE":
            dependency_edges.append((source, target))
        if relation == "EXCLUDES":
            ordered = tuple(sorted((source, target)))
            if source == target or ordered in excludes or (source, target) != ordered:
                issues.append(_problem("EXCLUDES_NOT_NORMALIZED", "EXCLUDES edge is self, duplicate, or reverse ordered", object_id=edge.get("edge_id")))
            excludes.add(ordered)
    for group in groups:
        if not isinstance(group, dict):
            continue
        for action_id in group.get("member_action_ids", []) if isinstance(group.get("member_action_ids"), list) else []:
            if action_id not in action_by_id:
                issues.append(_problem("ACTION_GROUP_DANGLING", "action group member is missing", object_id=group.get("group_id")))
        members = group.get("member_action_ids", [])
        if isinstance(members, list) and len(members) != len({item for item in members if isinstance(item, str)}):
            issues.append(
                _problem(
                    "ACTION_GROUP_MEMBER_DUPLICATE",
                    "action group member IDs must be unique",
                    object_id=group.get("group_id"),
                )
            )
        if isinstance(members, list) and group.get("kind") == "PARALLEL":
            member_set = {item for item in members if isinstance(item, str)}
            if any(source in member_set and target in member_set for source, target in dependency_edges):
                issues.append(
                    _problem(
                        "PARALLEL_GROUP_DEPENDENCY_CONFLICT",
                        "PARALLEL group members cannot have a hard dependency between them",
                        object_id=group.get("group_id"),
                    )
                )
        if isinstance(members, list) and group.get("kind") == "ORDERED":
            if len(members) < 2:
                issues.append(
                    _problem(
                        "ORDERED_GROUP_TOO_SMALL",
                        "ORDERED group requires at least two members to define an order",
                        object_id=group.get("group_id"),
                    )
                )
            dependency_edges.extend(
                (source, target)
                for source, target in zip(members, members[1:])
                if isinstance(source, str) and isinstance(target, str)
            )
    if not _acyclic(set(action_by_id), dependency_edges):
        issues.append(
            _problem(
                "ACTION_GRAPH_CYCLE",
                "REQUIRES/BEFORE/ORDERED dependency graph contains a cycle",
                object_id=graph_record_id,
            )
        )
    recommended = graph.get("recommended_action_id")
    if recommended is not None and recommended not in action_by_id:
        issues.append(_problem("RECOMMENDATION_DANGLING", "recommended action is missing", object_id=graph_record_id))
    for basis_id in graph.get("recommendation_basis_ids", []) if isinstance(graph.get("recommendation_basis_ids"), list) else []:
        if basis_id not in record_by_id:
            issues.append(
                _problem(
                    "RECOMMENDATION_BASIS_DANGLING",
                    "recommendation basis does not resolve to a WARM record",
                    object_id=str(basis_id),
                )
            )
    if recommended is not None and not graph.get("recommendation_basis_ids"):
        issues.append(
            _problem(
                "RECOMMENDATION_BASIS_MISSING",
                "recommended action requires at least one resolvable basis record",
                object_id=str(graph_record_id) if isinstance(graph_record_id, str) else None,
            )
        )
    activated = revision.get("activated_by_event_id")
    activation_event = event_by_id.get(activated)
    if (
        activation_event is None
        or activation_event.get("record_id") != graph_record_id
        or activation_event.get("reason_kind") != "ACTION_GRAPH_ACTIVATED"
        or not isinstance(activation_event.get("to"), dict)
        or activation_event["to"].get("lifecycle") != "ACTIVE"
    ):
        issues.append(_problem("GRAPH_ACTIVATION_FAIL", "action graph revision activation event is invalid", object_id=graph_record_id))

    current = warm.get("current_projection", {})
    if isinstance(current, dict):
        active_intents = sorted(
            record_id for record_id, item in record_by_id.items()
            if item.get("type") == "intent" and item.get("lifecycle") == "ACTIVE"
        )
        current_intent_id = current.get("current_intent_id")
        if len(active_intents) == 1:
            if current_intent_id != active_intents[0]:
                issues.append(_problem("CURRENT_INTENT_MISMATCH", "current_projection intent is not the unique ACTIVE intent", object_id="warm_state"))
        elif not active_intents:
            proposed_intents = sorted(
                record_id for record_id, item in record_by_id.items()
                if item.get("type") == "intent" and item.get("lifecycle") == "PROPOSED"
            )
            partial_blocked = (
                warm.get("semantic_actionability_claim") == "BLOCKED"
                and isinstance(warm.get("content_coverage"), dict)
                and warm["content_coverage"].get("claim") == "PARTIAL"
            )
            if not partial_blocked or len(proposed_intents) != 1 or current_intent_id != proposed_intents[0]:
                issues.append(_problem("CURRENT_INTENT_MISMATCH", "current_projection lacks a permitted unique current intent", object_id="warm_state"))
        else:
            issues.append(_problem("CURRENT_INTENT_MISMATCH", "current_projection has multiple ACTIVE intents", object_id="warm_state"))
        projections = {
            "active_decision_ids": sorted(record_id for record_id, item in record_by_id.items() if item.get("type") == "decision" and item.get("lifecycle") == "ACTIVE"),
            "rejected_decision_ids": sorted(record_id for record_id, item in record_by_id.items() if item.get("type") == "decision" and item.get("lifecycle") == "REJECTED"),
            "failed_attempt_ids": sorted(record_id for record_id, item in record_by_id.items() if item.get("type") == "attempt" and item.get("outcome") == "FAILED"),
            "active_constraint_ids": sorted(record_id for record_id, item in record_by_id.items() if item.get("type") == "constraint" and item.get("lifecycle") == "ACTIVE"),
            "answered_question_ids": sorted(record_id for record_id, item in record_by_id.items() if item.get("type") == "question" and item.get("lifecycle") == "ANSWERED"),
            "ready_action_ids": sorted(action_id for action_id, item in action_by_id.items() if item.get("eligibility_projection") == "READY"),
            "blocked_action_ids": sorted(action_id for action_id, item in action_by_id.items() if item.get("eligibility_projection") == "BLOCKED"),
        }
        for key, expected in projections.items():
            actual = current.get(key)
            if not isinstance(actual, list) or sorted(actual) != expected:
                issues.append(_problem("CURRENT_PROJECTION_MISMATCH", f"current_projection.{key} is stale", object_id="warm_state"))
        if current.get("recommended_action_id") != recommended:
            issues.append(_problem("CURRENT_RECOMMENDATION_MISMATCH", "current projection recommendation is stale", object_id="warm_state"))

    inventory = warm.get("source_inventory", {})
    entries = inventory.get("entries", []) if isinstance(inventory, dict) and isinstance(inventory.get("entries"), list) else []
    source_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source_id = entry.get("source_id")
        if isinstance(source_id, str):
            if source_id in source_ids:
                issues.append(_problem("SOURCE_ID_DUPLICATE", "source inventory source_id is duplicated", object_id=source_id))
            source_ids.add(source_id)
        object_id = entry.get("object_id")
        data = object_bytes.get(object_id)
        if data is None:
            issues.append(_problem("INVENTORY_OBJECT_DANGLING", "inventory object is unavailable", object_id=object_id))
        elif sha256_digest(data) != entry.get("object_sha256"):
            issues.append(_problem("INVENTORY_OBJECT_DIGEST_FAIL", "inventory object digest mismatch", object_id=object_id))
        for related in list(entry.get("attachment_object_ids", [])) + list(entry.get("tool_result_object_ids", [])):
            if related not in object_bytes:
                issues.append(_problem("INVENTORY_RELATED_DANGLING", "inventory attachment/tool object is unavailable", object_id=related))
    for event_id, event in event_by_id.items():
        for source_ref in event.get("source_refs", []):
            if source_ref not in source_ids:
                issues.append(
                    _problem(
                        "EVENT_SOURCE_REF_DANGLING",
                        "transition event source_ref is absent from source inventory",
                        object_id=event_id,
                    )
                )
    for record_id, record in record_by_id.items():
        for span in record.get("evidence_spans", []):
            if isinstance(span, dict) and span.get("source_id") not in source_ids:
                issues.append(
                    _problem(
                        "EVIDENCE_SOURCE_REF_DANGLING",
                        "evidence span source_id is absent from source inventory",
                        object_id=record_id,
                    )
                )
    boundaries = warm.get("boundaries") if isinstance(warm.get("boundaries"), dict) else {}
    scope = boundaries.get("scope") if isinstance(boundaries.get("scope"), dict) else {}
    scope_id = scope.get("scope_id")
    for record_id, record in record_by_id.items():
        if record.get("scope_id") != scope_id:
            issues.append(
                _problem(
                    "RECORD_SCOPE_MISMATCH",
                    "record scope_id does not resolve to the active WARM scope",
                    object_id=record_id,
                )
            )
    for event_id, event in event_by_id.items():
        if event.get("scope_id") != scope_id:
            issues.append(
                _problem(
                    "EVENT_SCOPE_MISMATCH",
                    "event scope_id does not resolve to the active WARM scope",
                    object_id=event_id,
                )
            )
    for request_id in scope.get("user_request_refs", []) if isinstance(scope.get("user_request_refs"), list) else []:
        if request_id not in source_ids:
            issues.append(
                _problem(
                    "USER_REQUEST_REF_DANGLING",
                    "scope user_request_ref is absent from source inventory",
                    object_id=str(request_id),
                )
            )
    source_boundary = boundaries.get("source_boundary") if isinstance(boundaries.get("source_boundary"), dict) else {}
    for key in ("first_source_id", "last_source_id", "first_native_id", "last_native_id"):
        value = source_boundary.get(key)
        if value is not None and value not in source_ids:
            issues.append(
                _problem(
                    "SOURCE_BOUNDARY_REF_DANGLING",
                    f"source_boundary.{key} is absent from source inventory",
                    object_id=str(value),
                )
            )
    inventory_sessions = {
        item for item in inventory.get("source_session_ids", [])
        if isinstance(item, str)
    } if isinstance(inventory, dict) else set()
    inventory_sessions.update(
        item.get("stream_id")
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("stream_id"), str)
    )
    for session_id in source_boundary.get("source_session_ids", []) if isinstance(source_boundary.get("source_session_ids"), list) else []:
        if session_id not in inventory_sessions:
            issues.append(
                _problem(
                    "SOURCE_BOUNDARY_SESSION_DANGLING",
                    "source boundary session is absent from source inventory",
                    object_id=str(session_id),
                )
            )
    capture_boundary = inventory.get("capture_boundary") if isinstance(inventory, dict) and isinstance(inventory.get("capture_boundary"), dict) else {}
    for key in ("first_native_id", "last_native_id"):
        value = capture_boundary.get(key)
        if value is not None and value not in source_ids:
            issues.append(
                _problem(
                    "INVENTORY_BOUNDARY_REF_DANGLING",
                    f"source inventory capture_boundary.{key} is absent from entries",
                    object_id=str(value),
                )
            )
    coverage = warm.get("content_coverage", {})
    if isinstance(coverage, dict) and isinstance(inventory, dict):
        if coverage.get("inventory_object_id") != inventory.get("inventory_id"):
            issues.append(_problem("INVENTORY_ID_MISMATCH", "coverage inventory_object_id disagrees with source inventory", object_id="warm_state"))
        inventory_projection = dict(inventory)
        inventory_projection.pop("inventory_digest", None)
        try:
            expected_inventory_digest = derived_digest_v1(
                "inventory_digest",
                inventory_projection,
                str(warm.get("protocol_version", "")),
            )
        except Exception:
            expected_inventory_digest = None
        if inventory.get("inventory_digest") != expected_inventory_digest:
            issues.append(
                _problem(
                    "INVENTORY_DIGEST_FAIL",
                    "source_inventory.inventory_digest does not match lch-derived-digest-v1",
                    object_id=inventory.get("inventory_id"),
                )
            )
        if coverage.get("scope") != scope:
            issues.append(
                _problem(
                    "COVERAGE_SCOPE_MISMATCH",
                    "WARM content_coverage.scope is not identical to boundaries.scope",
                    object_id="warm_state",
                )
            )
        omissions = coverage.get("omissions") if isinstance(coverage.get("omissions"), list) else []
        omission_counts: dict[str, int] = {}
        omission_by_id: dict[str, dict[str, Any]] = {}
        for omission in omissions:
            if not isinstance(omission, dict) or not isinstance(omission.get("omission_id"), str):
                continue
            omission_id = omission["omission_id"]
            omission_counts[omission_id] = omission_counts.get(omission_id, 0) + 1
            omission_by_id[omission_id] = omission
        for omission_id, count in sorted(omission_counts.items()):
            if count != 1:
                issues.append(
                    _problem(
                        "OMISSION_ID_DUPLICATE",
                        "coverage omission_id must occur exactly once",
                        object_id=omission_id,
                    )
                )
        exclusion_ids = scope.get("material_exclusion_ids")
        exclusion_ids = exclusion_ids if isinstance(exclusion_ids, list) else []
        for omission_id in exclusion_ids:
            omission = omission_by_id.get(omission_id) if isinstance(omission_id, str) else None
            if (
                omission is None
                or omission_counts.get(omission_id) != 1
                or omission.get("materiality") not in {"BLOCKING", "MATERIAL"}
            ):
                issues.append(
                    _problem(
                        "MATERIAL_EXCLUSION_DANGLING",
                        "material exclusion ID must resolve exactly once to a material omission",
                        object_id=str(omission_id),
                    )
                )
        for omission_id, omission in sorted(omission_by_id.items()):
            if (
                omission.get("category") == "policy_exclusion"
                and omission.get("materiality") in {"BLOCKING", "MATERIAL"}
                and omission_id not in exclusion_ids
            ):
                issues.append(
                    _problem(
                        "MATERIAL_EXCLUSION_UNDECLARED",
                        "material policy exclusion is absent from scope.material_exclusion_ids",
                        object_id=omission_id,
                    )
                )
        inventory_gaps = inventory.get("gaps") if isinstance(inventory.get("gaps"), list) else []
        material_omission = any(
            isinstance(item, dict) and item.get("materiality") in {"BLOCKING", "MATERIAL"}
            for item in omissions
        )
        material_gap = any(
            isinstance(item, dict) and item.get("materiality") in {"BLOCKING", "MATERIAL"}
            for item in inventory_gaps
        )
        artifact_required = any(
            item.get("type") == "artifact"
            for item in record_by_id.values()
        ) or any(
            bool(item.get("attachment_object_ids"))
            for item in entries
            if isinstance(item, dict)
        )
        source_access = coverage.get("source_access")
        raw_coverage = coverage.get("raw_coverage")
        artifact_coverage = coverage.get("artifact_coverage")
        established_partial = (
            source_access == "PARTIAL"
            or raw_coverage in {"PARTIAL", "NONE"}
            or (artifact_required and artifact_coverage in {"PARTIAL", "NONE"})
            or material_omission
            or material_gap
        )
        anchored_boundary = bool(source_boundary) and bool(source_ids) and bool(
            scope.get("user_request_refs")
        )
        undecidable = (
            source_access == "UNKNOWN"
            or raw_coverage == "UNKNOWN"
            or not anchored_boundary
        )
        claim = coverage.get("claim")
        complete_valid = (
            source_access == "FULL"
            and raw_coverage == "FULL_WITHIN_SCOPE"
            and artifact_coverage in {"FULL", "NOT_APPLICABLE"}
            and not (artifact_coverage == "NOT_APPLICABLE" and artifact_required)
            and not material_omission
            and not material_gap
            and anchored_boundary
        )
        if claim == "COMPLETE" and not complete_valid:
            issues.append(
                _problem(
                    "COVERAGE_COMPLETE_CONTRADICTION",
                    "COMPLETE coverage conflicts with access, raw, artifact, gap, omission, or boundary state",
                    object_id="warm_state",
                )
            )
        elif claim == "PARTIAL" and not established_partial:
            issues.append(
                _problem(
                    "COVERAGE_PARTIAL_UNSUPPORTED",
                    "PARTIAL coverage has no established material gap",
                    object_id="warm_state",
                )
            )
        elif claim == "UNKNOWN" and (established_partial or not undecidable):
            issues.append(
                _problem(
                    "COVERAGE_UNKNOWN_CONTRADICTION",
                    "UNKNOWN coverage is invalid when a material gap is established or completeness is decidable",
                    object_id="warm_state",
                )
            )
    required_self_contained = bool(root) and any(
        isinstance(profile, dict)
        and profile.get("id") == "urn:lch:profile:self-contained"
        and profile.get("version") == "0.1.0"
        and profile.get("required") is True
        for profile in root.get("profiles", [])
    )
    if required_self_contained:
        material_artifact_coverage_gap = any(
            isinstance(item, dict)
            and item.get("category") == "artifact"
            and item.get("materiality") in {"BLOCKING", "MATERIAL"}
            for item in omissions
        ) or any(
            isinstance(item, dict)
            and item.get("materiality") in {"BLOCKING", "MATERIAL"}
            for item in inventory_gaps
        )
        if material_artifact_coverage_gap:
            issues.append(
                _problem(
                    "SELF_CONTAINED_MATERIAL_GAP",
                    "required SELF_CONTAINED cannot pass with a blocking/material artifact omission or inventory gap",
                    object_id="warm_state",
                )
            )
        for record_id, record in record_by_id.items():
            if record.get("type") != "artifact":
                continue
            availability = record.get("availability")
            has_rooted_full_bytes = False
            if availability == "PRESENT":
                for span in record.get("evidence_spans", []):
                    if not isinstance(span, dict):
                        continue
                    data = object_bytes.get(span.get("object_id"))
                    if (
                        data is not None
                        and span.get("byte_start") == 0
                        and span.get("byte_end") == len(data)
                        and span.get("sha256_raw") == sha256_digest(data)
                    ):
                        has_rooted_full_bytes = True
                        break
            if not has_rooted_full_bytes:
                issues.append(
                    _problem(
                        "SELF_CONTAINED_ARTIFACT_UNRESOLVED",
                        "required SELF_CONTAINED artifact is not PRESENT with one evidence span covering verified rooted bytes in full",
                        object_id=record_id,
                    )
                )
    return issues


def _legacy_conversion_issues(
    object_bytes: dict[str, bytes],
    warm: dict[str, Any],
    validator: Validator,
) -> list[dict[str, Any]]:
    raw = object_bytes.get("legacy_conversion_report")
    if raw is None:
        return []
    issues: list[dict[str, Any]] = []
    try:
        report = loads_strict(raw)
        check_json_depth(report, maximum=MAX_JSON_DEPTH)
    except Exception:
        return [
            _problem(
                "CONVERSION_REPORT_JSON_FAIL",
                "rooted legacy conversion report is not bounded strict JSON",
                object_id="legacy_conversion_report",
            )
        ]
    if not isinstance(report, dict):
        return [
            _problem(
                "CONVERSION_REPORT_SCHEMA_FAIL",
                "rooted legacy conversion report is not an object",
                object_id="legacy_conversion_report",
            )
        ]
    schema_issues = _schema_problems(
        validator,
        report,
        "legacy-conversion-report.schema.json",
        object_id="legacy_conversion_report",
    )
    issues.extend(schema_issues)
    if schema_issues:
        return issues
    from .converters import (
        FORMAT_RULES,
        PARSER_VERSION,
        _ltm_mapping,
        _markdown_mapping,
    )

    origin = report.get("conversion_origin")
    rule = FORMAT_RULES.get(origin) if isinstance(origin, str) else None
    source_version = report.get("source_version")
    frozen_contract = False
    if origin == "handoff_markdown":
        if source_version == "handoff-md-generic":
            frozen_contract = (
                report.get("format_override") == "handoff_markdown"
                and report.get("detection_rules") == ["handoff_md_generic_user_override"]
                and report.get("detection_confidence") == 0
                and "GENERIC_HANDOFF_OVERRIDE_NONAUTHORITATIVE" in report.get("warnings", [])
            )
        else:
            frozen_contract = (
                source_version == rule.get("source_version")
                and report.get("detection_rules") == [rule.get("detection_rule")]
                and report.get("detection_confidence") == 1
                and report.get("format_override") in {None, "handoff_markdown"}
            )
    elif origin == "och_snapshot":
        frozen_contract = (
            source_version == rule.get("source_version")
            and report.get("detection_rules") == [rule.get("detection_rule")]
            and report.get("detection_confidence") == 1
            and report.get("format_override") in {None, "och_snapshot"}
        )
    elif origin == "ltm_packet" and isinstance(rule, dict):
        version_contracts = rule.get("versions", {})
        frozen_contract = any(
            source_version == item.get("source_version")
            and report.get("detection_rules") == [item.get("detection_rule")]
            and report.get("detection_confidence") == 1
            and report.get("format_override") in {None, "ltm_packet"}
            for item in version_contracts.values()
            if isinstance(item, dict)
        )
    if rule is None or report.get("parser_version") != PARSER_VERSION or not frozen_contract:
        issues.append(
            _problem(
                "CONVERSION_DETECTOR_FREEZE_FAIL",
                "conversion report detector, source version, or parser version is not frozen v0.1",
                object_id="legacy_conversion_report",
            )
        )
    if report.get("conflicts") != []:
        issues.append(
            _problem(
                "CONVERSION_CONFLICT_REPLAY_FAIL",
                "frozen deterministic legacy parsers emit an exact empty conflicts list",
                object_id="legacy_conversion_report",
            )
        )
    inventory = warm.get("source_inventory")
    inventory_entries = inventory.get("entries", []) if isinstance(inventory, dict) else []
    source_ids = {
        item.get("source_id")
        for item in inventory_entries
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    coverage = warm.get("content_coverage")
    omissions = coverage.get("omissions", []) if isinstance(coverage, dict) else []
    omission_ids = {
        item.get("omission_id")
        for item in omissions
        if isinstance(item, dict) and isinstance(item.get("omission_id"), str)
    }
    declared_source_digest = report.get("source_sha256")
    rooted_source = next(
        (
            data
            for object_id, data in object_bytes.items()
            if object_id != "legacy_conversion_report"
            and sha256_digest(data) == declared_source_digest
        ),
        None,
    )
    if rooted_source is None and "omission.original_transfer" not in omission_ids:
        issues.append(
            _problem(
                "CONVERSION_SOURCE_EVIDENCE_FAIL",
                "conversion source hash neither resolves to rooted bytes nor to the transfer omission",
                object_id="legacy_conversion_report",
            )
        )
    if source_version == "handoff-md-generic" and rooted_source is None:
        issues.append(
            _problem(
                "GENERIC_HANDOFF_SOURCE_MISSING",
                "generic HANDOFF override requires the exact source bytes to remain rooted",
                object_id="legacy_conversion_report",
            )
        )
    if rooted_source is not None and frozen_contract:
        try:
            if origin == "ltm_packet":
                replay = _ltm_mapping(
                    rooted_source,
                    override=False,
                    evidence_ref="legacy_source_entry",
                )
                expected_mapping, expected_unmapped, expected_missing = replay[0], replay[1], replay[2]
                expected_warnings, expected_confidence = replay[3], replay[4]
                expected_version, expected_rule = replay[5], replay[6]
            else:
                replay = _markdown_mapping(
                    rooted_source,
                    str(origin),
                    override=source_version == "handoff-md-generic",
                    evidence_ref="legacy_source_entry",
                )
                expected_mapping, expected_unmapped, expected_missing = replay[0], replay[1], replay[2]
                expected_warnings, expected_confidence = replay[3], replay[4]
                expected_version, expected_rule = replay[5], replay[6]
            if (
                report.get("mapping_report") != expected_mapping
                or report.get("unmapped_sections") != expected_unmapped
                or report.get("source_version") != expected_version
                or report.get("detection_rules") != [expected_rule]
                or report.get("detection_confidence") != expected_confidence
                or report.get("warnings") != expected_warnings
                or report.get("conflicts") != []
                or sorted(report.get("MISSING", [])) != sorted(set(expected_missing))
            ):
                issues.append(
                    _problem(
                        "CONVERSION_REPLAY_MISMATCH",
                        "rooted legacy source does not reproduce the frozen detector and mapping report",
                        object_id="legacy_conversion_report",
                    )
                )
        except LCHError:
            issues.append(
                _problem(
                    "CONVERSION_SOURCE_FORMAT_FAIL",
                    "rooted legacy source fails its declared frozen format contract",
                    object_id="legacy_conversion_report",
                )
            )
    allowed_evidence_refs = source_ids | omission_ids
    for mapping in report.get("mapping_report", []):
        if not isinstance(mapping, dict):
            continue
        refs = mapping.get("evidence_refs")
        if not isinstance(refs, list) or any(ref not in allowed_evidence_refs for ref in refs):
            issues.append(
                _problem(
                    "CONVERSION_EVIDENCE_REF_DANGLING",
                    "conversion mapping evidence_ref is absent from source inventory and omissions",
                    object_id="legacy_conversion_report",
                )
            )
            break
    return issues


def _review_context(root: dict[str, Any], integrity_kind: str) -> dict[str, Any]:
    origin = root.get("origin_claim") if isinstance(root.get("origin_claim"), dict) else {}
    return {
        "protocol_id": root.get("protocol_id", "lossless-context-handoff"),
        "package_id": root.get("package_id"),
        "profiles": root.get("profiles"),
        "integrity_kind": integrity_kind,
        "integrity_algorithm": "sha-256",
        "canonical_state_digest": root.get("canonical_state_digest"),
        "recipient_and_sharing_scope": origin.get("recipient_binding"),
        "detached_envelope_policy": root.get("detached_envelope_slots"),
    }


def _root_warm_issues(root: dict[str, Any], warm: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _problem(
            "ROOT_WARM_PROJECTION_MISMATCH",
            f"root.{field} is not identical to its canonical WARM projection",
            object_id="warm_state",
        )
        for field in root_warm_mismatches(root, warm)
    ]


def _root_protocol_issues(
    root: dict[str, Any],
    warm: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    issues = _root_warm_issues(root, warm) if warm is not None else []
    if root.get("materiality_profile_ref") != bundled_materiality_ref():
        issues.append(
            _problem(
                "MATERIALITY_PROFILE_REF_FAIL",
                "materiality_profile_ref does not match the bundled frozen Profile",
                object_id="materiality-v1",
            )
        )
    slots = root.get("detached_envelope_slots")
    slots = slots if isinstance(slots, list) else []
    slot_id_list = [
        item.get("opaque_id")
        for item in slots
        if isinstance(item, dict) and isinstance(item.get("opaque_id"), str)
    ]
    slot_ids = set(slot_id_list)
    if len(slot_id_list) != len(slot_ids):
        issues.append(
            _problem(
                "DUPLICATE_SLOT_ID",
                "detached slot opaque IDs must be unique",
                object_id="manifest",
            )
        )
    for expected_type in (
        "review_projection_conformance",
        "approval_statement",
        "approval_verification",
    ):
        count = sum(
            isinstance(item, dict)
            and item.get("required") is True
            and item.get("expected_type") == expected_type
            for item in slots
        )
        if count != 1:
            issues.append(
                _problem(
                    "REQUIRED_SLOT_CARDINALITY",
                    f"required {expected_type} slot must occur exactly once",
                    object_id="manifest",
                )
            )
    required_statements = [
        item
        for item in slots
        if isinstance(item, dict)
        and item.get("required") is True
        and item.get("expected_type") == "approval_statement"
    ]
    statement_id = required_statements[0].get("opaque_id") if len(required_statements) == 1 else None
    scope = root.get("scope") if isinstance(root.get("scope"), dict) else {}
    approval = root.get("approval_claim") if isinstance(root.get("approval_claim"), dict) else {}
    if (
        statement_id is None
        or scope.get("approval_statement_slot") != statement_id
        or approval.get("approval_statement_slot") != statement_id
    ):
        issues.append(
            _problem(
                "APPROVAL_SLOT_MISMATCH",
                "scope, approval claim, and exactly one required approval-statement slot must agree",
                object_id="manifest",
            )
        )
    coverage = root.get("content_coverage") if isinstance(root.get("content_coverage"), dict) else {}
    if coverage.get("scope") != scope:
        issues.append(
            _problem(
                "COVERAGE_SCOPE_MISMATCH",
                "root content_coverage.scope is not identical to root scope",
                object_id="manifest",
            )
        )
    coverage_slots = coverage.get("coverage_envelope_slot_ids")
    if not isinstance(coverage_slots, list) or any(
        not isinstance(item, str) or item not in slot_ids for item in coverage_slots
    ):
        issues.append(
            _problem(
                "COVERAGE_SLOT_DANGLING",
                "coverage envelope slot IDs do not resolve to declared detached slots",
                object_id="manifest",
            )
        )
    for key in root_result_key_hits(root):
        issues.append(
            _problem(
                "ROLE_BOUNDARY_VIOLATION",
                "Producer root contains a post-seal or foreign-role result key",
                object_id=key,
            )
        )
    for code, subject in root_capability_issues(root):
        issues.append(
            _problem(
                code,
                "root declares an unsupported or ambiguous selected protocol capability",
                object_id=subject,
            )
        )
    return issues


def _detached_payload_type(payload: dict[str, Any]) -> str | None:
    if payload.get("type") in {"structure_conformance", "byte_consistency", "review_projection_conformance"}:
        return payload["type"]
    if "statement_id" in payload and "decision" in payload:
        return "approval_statement"
    if "verification_id" in payload and "approval_gate" in payload:
        return "approval_verification"
    if is_receipt_payload(payload):
        return "receiver_receipt"
    if payload.get("type") == "receiver_receipt":
        return "receiver_receipt_attestation"
    if payload.get("issuer", {}).get("authority") == "authorize_operation":
        return "authorization_result"
    return payload.get("type") if isinstance(payload.get("type"), str) else None


def _canonical_language_from_report(
    qualification: dict[str, Any],
    source: Any,
) -> str | None:
    if not isinstance(source, str):
        return None
    mappings = qualification.get("canonical_mappings")
    if not isinstance(mappings, list):
        return None
    for item in mappings:
        if (
            isinstance(item, dict)
            and item.get("source") == source
            and isinstance(item.get("canonical"), str)
        ):
            return item["canonical"].casefold()
    return None


def _approval_chain_issues(
    root: dict[str, Any],
    parsed: list[dict[str, Any]],
    integrity_ref: dict[str, Any],
    warm: dict[str, Any] | None,
    review_bytes: bytes | None,
    integrity_kind: str = "bundle_manifest",
) -> tuple[list[dict[str, Any]], set[str], bool]:
    issues: list[dict[str, Any]] = []
    invalid_ids: set[str] = set()
    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in parsed:
        payload_type = item.get("payload_type")
        if isinstance(payload_type, str):
            by_type.setdefault(payload_type, []).append(item)

    def fail(code: str, message: str, item: dict[str, Any] | None) -> None:
        opaque_id = item.get("opaque_id") if isinstance(item, dict) else None
        issues.append(_problem(code, message, object_id=opaque_id))
        if isinstance(opaque_id, str):
            invalid_ids.add(opaque_id)

    statements = by_type.get("approval_statement", [])
    verifications = by_type.get("approval_verification", [])
    review_results = by_type.get("review_projection_conformance", [])
    statement = statements[0] if len(statements) == 1 else None
    verification = verifications[0] if len(verifications) == 1 else None
    if len(statements) > 1:
        for item in statements:
            fail("APPROVAL_STATEMENT_AMBIGUOUS", "approval chain has more than one statement candidate", item)
    if len(verifications) > 1:
        for item in verifications:
            fail("APPROVAL_VERIFICATION_AMBIGUOUS", "approval chain has more than one verification candidate", item)

    scope = root.get("scope") if isinstance(root.get("scope"), dict) else {}
    coverage = root.get("content_coverage") if isinstance(root.get("content_coverage"), dict) else {}
    omissions = coverage.get("omissions") if isinstance(coverage.get("omissions"), list) else []
    omission_by_id = {
        item.get("omission_id"): item
        for item in omissions
        if isinstance(item, dict) and isinstance(item.get("omission_id"), str)
    }
    exclusion_ids = scope.get("material_exclusion_ids") if isinstance(scope.get("material_exclusion_ids"), list) else []
    exclusion_objects = [omission_by_id[item] for item in sorted(exclusion_ids) if item in omission_by_id]
    recipient_binding = (
        root.get("origin_claim", {}).get("recipient_binding")
        if isinstance(root.get("origin_claim"), dict)
        else None
    )
    expected = {
        "package_id": root.get("package_id"),
        "package_integrity_ref": integrity_ref,
        "review_projection_ref": root.get("review_projection_ref"),
        "canonical_state_digest": root.get("canonical_state_digest"),
        "scope_digest": derived_digest_v1("scope_digest", scope),
        "material_exclusions_digest": derived_digest_v1(
            "material_exclusions_digest", exclusion_objects
        ),
        "recipient_binding_digest": derived_digest_v1(
            "recipient_binding_digest", recipient_binding
        ),
    }
    statement_payload = statement.get("payload") if isinstance(statement, dict) else None
    statement_subject = (
        statement_payload.get("subject")
        if isinstance(statement_payload, dict) and isinstance(statement_payload.get("subject"), dict)
        else {}
    )
    statement_structural = isinstance(statement_payload, dict)
    if isinstance(statement, dict):
        for key, value in expected.items():
            if statement_subject.get(key) != value:
                statement_structural = False
                fail("APPROVAL_STATEMENT_BINDING_FAIL", f"approval statement {key} binding is incorrect", statement)
        fail(
            "APPROVAL_STATEMENT_AUTHENTICITY_UNVERIFIED",
            "deterministic structure validation cannot establish issuer evidence, current authority, time, or nonce replay state",
            statement,
        )

    verification_payload = verification.get("payload") if isinstance(verification, dict) else None
    verification_subject = (
        verification_payload.get("subject")
        if isinstance(verification_payload, dict) and isinstance(verification_payload.get("subject"), dict)
        else {}
    )
    verification_structural = isinstance(verification_payload, dict) and statement_structural
    if isinstance(verification, dict):
        if not isinstance(statement_payload, dict):
            verification_structural = False
            fail("APPROVAL_STATEMENT_MISSING", "approval verification has no unique statement candidate", verification)
        else:
            repeated = {
                key: expected[key]
                for key in (
                    "package_id",
                    "package_integrity_ref",
                    "review_projection_ref",
                    "canonical_state_digest",
                    "scope_digest",
                    "recipient_binding_digest",
                )
            }
            repeated["approval_challenge_nonce"] = statement_subject.get("approval_challenge_nonce")
            repeated["approval_statement_digest"] = derived_digest_v1(
                "approval_statement_digest", statement_payload
            )
            for key, value in repeated.items():
                if verification_subject.get(key) != value:
                    verification_structural = False
                    fail("APPROVAL_VERIFICATION_BINDING_FAIL", f"approval verification {key} binding is incorrect", verification)
            verified_decision = verification_payload.get("verified_decision")
            if verified_decision != statement_payload.get("decision"):
                verification_structural = False
                fail("APPROVAL_DECISION_BINDING_FAIL", "verified decision does not equal the statement decision", verification)
        review_outcome = verification_payload.get("review_projection_conformance")
        result_ref = verification_subject.get("review_projection_result_ref")
        if review_outcome == "NOT_RUN":
            if result_ref is not None:
                verification_structural = False
                fail("APPROVAL_REVIEW_REF_FAIL", "NOT_RUN approval review outcome requires a null result ref", verification)
        else:
            matching_review = None
            for candidate in review_results:
                actual_ref = {
                    "opaque_id": candidate.get("opaque_id"),
                    "sha256_raw": sha256_digest(candidate.get("raw", b"")),
                }
                if result_ref == actual_ref:
                    matching_review = candidate
                    break
            if matching_review is None or matching_review.get("payload", {}).get("result") != review_outcome:
                verification_structural = False
                fail("APPROVAL_REVIEW_RESULT_BINDING_FAIL", "approval review result ref/outcome is not backed by the actual candidate", verification)
            if review_outcome == "PASS":
                try:
                    rebuilt = (
                        review_projection_v1(warm, _review_context(root, integrity_kind))
                        if isinstance(warm, dict)
                        else None
                    )
                except Exception:
                    rebuilt = None
                if rebuilt is None or review_bytes != rebuilt:
                    verification_structural = False
                    fail("APPROVAL_REVIEW_REBUILD_FAIL", "approval PASS is not backed by exact review reconstruction", verification)
        # The wire contains only the digest. This role has no complete display-evidence
        # object, response bytes, trust anchor, current clock, or replay store.
        fail(
            "APPROVAL_EXTERNAL_EVIDENCE_UNAVAILABLE",
            "display evidence, approver response, trust, time, and replay state are unavailable to deterministic structure validation",
            verification,
        )
        if verification_payload.get("approval_gate") == "PASS" or verification_payload.get("statement_authenticity") == "VERIFIED":
            verification_structural = False
            fail("APPROVAL_POSITIVE_RESULT_UNESTABLISHED", "positive approval claims cannot be established by structural equality alone", verification)
    return issues, invalid_ids, False


def _receipt_invariant_issues(
    receipt_item: dict[str, Any],
    root: dict[str, Any],
    warm: dict[str, Any] | None,
    parsed: list[dict[str, Any]],
    invalid_ids: set[str],
    approval_chain_valid: bool,
    deterministic_outcomes: dict[str, str | None],
) -> list[dict[str, Any]]:
    receipt = receipt_item.get("payload")
    opaque_id = receipt_item.get("opaque_id")
    if not isinstance(receipt, dict):
        return []
    issues: list[dict[str, Any]] = []

    def fail(code: str, message: str) -> None:
        issues.append(_problem(code, message, object_id=opaque_id))

    candidates_by_locator: dict[tuple[str, str], dict[str, Any]] = {}
    for item in parsed:
        candidate_id = item.get("opaque_id")
        raw = item.get("raw")
        if isinstance(candidate_id, str) and isinstance(raw, bytes):
            candidates_by_locator[(candidate_id, sha256_digest(raw))] = item

    refs = receipt.get("verification_result_refs")
    summary = receipt.get("verification_summary")
    refs = refs if isinstance(refs, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    observed = receipt.get("observed_producer_claims")
    observed = observed if isinstance(observed, dict) else {}
    expected_claims = {
        "content_coverage": (root.get("content_coverage", {}).get("claim") if isinstance(root.get("content_coverage"), dict) else None, "root.content_coverage"),
        "approval": (root.get("approval_claim", {}).get("state") if isinstance(root.get("approval_claim"), dict) else None, "root.approval_claim"),
        "semantic_actionability": (root.get("semantic_actionability_claim"), "root.semantic_actionability_claim"),
    }
    for key, (value, claim_ref) in expected_claims.items():
        item = observed.get(key)
        if not isinstance(item, dict) or item.get("value") != value or item.get("package_claim_ref") != claim_ref:
            fail("RECEIPT_PRODUCER_CLAIM_FAIL", f"Receipt observed {key} claim is not an exact rooted observation")

    rooted_object_ids = {
        item.get("object_id")
        for collection_key in ("objects", "embedded_objects")
        for item in (root.get(collection_key, []) if isinstance(root.get(collection_key), list) else [])
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }
    read_object_ids = receipt.get("read_object_ids", [])
    read_object_set = {
        item for item in read_object_ids if isinstance(item, str)
    } if isinstance(read_object_ids, list) else set()
    if any(item not in rooted_object_ids for item in read_object_set):
        fail("RECEIPT_READ_OBJECT_DANGLING", "Receipt read_object_ids contains an object absent from the verified root")
    if receipt.get("processing_coverage") == "FULL" or receipt.get("processing_status") == "FULL":
        if receipt.get("processing_coverage") != "FULL" or receipt.get("processing_status") != "FULL":
            fail(
                "RECEIPT_FULL_PROCESSING_MISMATCH",
                "FULL processing coverage and processing status must be declared together",
            )
        if read_object_set != rooted_object_ids:
            fail(
                "RECEIPT_FULL_READ_SET_FAIL",
                "FULL processing requires the exact complete rooted object ID set",
            )

    family_rules = {
        "structure_conformance": ("structure_conformance", "structure_conformance"),
        "byte_consistency": ("byte_consistency", "byte_consistency"),
        "origin": ("origin", "origin"),
        "inventory_authenticity": ("inventory_authenticity", "inventory_authenticity"),
        "inventory_scope_coverage": ("inventory_scope_coverage", "inventory_scope_coverage"),
        "package_vs_inventory_coverage": ("package_vs_inventory_coverage", "package_vs_inventory_coverage"),
        "review_projection": ("review_projection_conformance", "review_projection_conformance"),
    }
    for ref_key, (payload_type, summary_key) in family_rules.items():
        ref = refs.get(ref_key)
        observed_summary = summary.get(summary_key)
        if ref is None:
            if observed_summary != "NOT_RUN":
                fail("RECEIPT_NULL_REF_SUMMARY_FAIL", f"null {ref_key} ref requires {summary_key}=NOT_RUN")
            continue
        candidate = (
            candidates_by_locator.get((ref.get("opaque_id"), ref.get("sha256_raw")))
            if isinstance(ref, dict)
            else None
        )
        valid = (
            candidate is not None
            and candidate.get("payload_type") == payload_type
            and candidate.get("base_valid") is True
            and candidate.get("opaque_id") not in invalid_ids
        )
        if payload_type in {
            "structure_conformance",
            "byte_consistency",
            "review_projection_conformance",
        }:
            valid = bool(
                valid
                and deterministic_outcomes.get(payload_type) is not None
                and candidate.get("payload", {}).get("result")
                == deterministic_outcomes.get(payload_type)
            )
        else:
            # This deterministic structure role has no trust-anchor store, current
            # issuer authority, or owning-role coverage run. A syntactically valid
            # foreign attestation therefore remains an invalid captured candidate.
            valid = False
        if not valid:
            fail(
                "RECEIPT_CANDIDATE_UNVERIFIED",
                f"{ref_key} candidate lacks a current valid owning-role result and must be ignored",
            )
            if observed_summary != "UNVERIFIED":
                fail("RECEIPT_INVALID_REF_SUMMARY_FAIL", f"invalid {ref_key} candidate requires {summary_key}=UNVERIFIED")
        elif candidate.get("payload", {}).get("result") != observed_summary:
            fail("RECEIPT_RESULT_SUMMARY_MISMATCH", f"{summary_key} does not equal its owning candidate result")

    approval_ref = refs.get("approval")
    if approval_ref is None:
        expected_approval = {
            "approval_statement_authenticity": "NOT_RUN",
            "approval_verified_decision": "UNKNOWN",
            "approval_gate": "NOT_RUN",
        }
    else:
        approval_candidate = (
            candidates_by_locator.get((approval_ref.get("opaque_id"), approval_ref.get("sha256_raw")))
            if isinstance(approval_ref, dict)
            else None
        )
        valid_approval = (
            approval_chain_valid
            and approval_candidate is not None
            and approval_candidate.get("payload_type") == "approval_verification"
            and approval_candidate.get("base_valid") is True
            and approval_candidate.get("opaque_id") not in invalid_ids
        )
        if valid_approval:
            approval_payload = approval_candidate.get("payload", {})
            expected_approval = {
                "approval_statement_authenticity": approval_payload.get("statement_authenticity"),
                "approval_verified_decision": approval_payload.get("verified_decision"),
                "approval_gate": approval_payload.get("approval_gate"),
            }
        else:
            expected_approval = {
                "approval_statement_authenticity": "UNVERIFIED",
                "approval_verified_decision": "UNKNOWN",
                "approval_gate": "FAIL",
            }
    for key, value in expected_approval.items():
        if summary.get(key) != value:
            fail("RECEIPT_APPROVAL_SUMMARY_FAIL", f"Receipt {key} is not derived from the validated approval candidate chain")

    security_ref = refs.get("security_run")
    if security_ref is None:
        security_not_run = any(
            isinstance(item, dict)
            and item.get("code") == "LCH-SECURITY-RUN-NOT-RUN"
            for item in receipt.get("issues", [])
        )
        if not security_not_run:
            fail("RECEIPT_SECURITY_NOT_RUN_UNREPORTED", "null security_run ref requires an explicit processing issue")
    else:
        security_candidate = (
            candidates_by_locator.get(
                (security_ref.get("opaque_id"), security_ref.get("sha256_raw"))
            )
            if isinstance(security_ref, dict)
            else None
        )
        security_shape_valid = (
            security_candidate is not None
            and security_candidate.get("payload_type") == "security_run"
            and security_candidate.get("base_valid") is True
            and security_candidate.get("opaque_id") not in invalid_ids
        )
        # SECURITY_RUN_RESULT belongs to a separate scoped runner. This verifier
        # has no trust/permission/sandbox evidence store and cannot validate it.
        fail(
            "RECEIPT_SECURITY_RESULT_UNVERIFIED",
            (
                "security_run candidate lacks current scoped runner trust and coverage evidence"
                if security_shape_valid
                else "security_run ref does not locate a valid bound security result candidate"
            ),
        )
        if receipt.get("processing_status") != "SECURITY_LIMITED":
            fail(
                "RECEIPT_SECURITY_LIMITATION_UNREPORTED",
                "unverified security_run requires SECURITY_LIMITED processing status",
            )

    if not isinstance(warm, dict):
        fail("RECEIPT_STATE_UNAVAILABLE", "Receipt action projections cannot be checked without valid WARM state")
        return issues
    graph = warm.get("action_graph") if isinstance(warm.get("action_graph"), dict) else {}
    actions = graph.get("actions") if isinstance(graph.get("actions"), list) else []
    action_by_id = {
        item.get("action_id"): item
        for item in actions
        if isinstance(item, dict) and isinstance(item.get("action_id"), str)
    }
    ready = sorted(
        action_id for action_id, action in action_by_id.items()
        if action.get("eligibility_projection") == "READY"
    )
    blocked = sorted(
        action_id for action_id, action in action_by_id.items()
        if action.get("eligibility_projection") == "BLOCKED"
    )
    if sorted(receipt.get("ready_action_ids", [])) != ready:
        fail("RECEIPT_READY_PROJECTION_FAIL", "Receipt ready_action_ids is not the active graph READY projection")
    if sorted(receipt.get("blocked_action_ids", [])) != blocked:
        fail("RECEIPT_BLOCKED_PROJECTION_FAIL", "Receipt blocked_action_ids is not the active graph BLOCKED projection")
    if set(receipt.get("ready_action_ids", [])) & set(receipt.get("blocked_action_ids", [])):
        fail("RECEIPT_ACTION_SET_OVERLAP", "Receipt ready and blocked action sets must be disjoint")
    selected = receipt.get("selected_continuation_action_ids", [])
    selected_set = {item for item in selected if isinstance(item, str)} if isinstance(selected, list) else set()
    if any(item not in action_by_id for item in selected_set):
        fail("RECEIPT_SELECTED_ACTION_DANGLING", "Receipt selected action does not resolve to the active graph")
    if receipt.get("recommended_action_id") != graph.get("recommended_action_id"):
        fail("RECEIPT_RECOMMENDATION_FAIL", "Receipt recommendation differs from the active graph")
    current = warm.get("current_projection") if isinstance(warm.get("current_projection"), dict) else {}
    receipt_projection_fields = (
        "current_intent_id",
        "active_decision_ids",
        "rejected_decision_ids",
        "failed_attempt_ids",
        "active_constraint_ids",
        "answered_question_ids",
    )
    for key in receipt_projection_fields:
        if receipt.get(key) != current.get(key):
            fail("RECEIPT_STATE_PROJECTION_FAIL", f"Receipt {key} differs from the rooted current projection")

    auth_evaluations = receipt.get("authorization_evaluations", [])
    seen_auth_actions: set[str] = set()
    for evaluation in auth_evaluations if isinstance(auth_evaluations, list) else []:
        if not isinstance(evaluation, dict):
            continue
        action_id = evaluation.get("action_id")
        if action_id not in action_by_id:
            fail("RECEIPT_AUTH_ACTION_DANGLING", "authorization evaluation action does not resolve")
        if action_id in seen_auth_actions:
            fail("RECEIPT_AUTH_DUPLICATE", "Receipt has duplicate authorization evaluations for an action")
        if isinstance(action_id, str):
            seen_auth_actions.add(action_id)
        if evaluation.get("status") == "AUTHORIZED" and evaluation.get("authorization_result_ref") is None:
            fail("RECEIPT_AUTH_SELF_ATTESTED", "AUTHORIZED evaluation requires a valid independent authorization result candidate")
    selected_auth_required = {
        action_id
        for action_id in selected_set
        if action_by_id.get(action_id, {}).get("required_authorization_specs")
    }
    if not selected_auth_required and receipt.get("authorization_summary") != "NOT_APPLICABLE":
        fail("RECEIPT_AUTH_SUMMARY_FAIL", "authorization summary must be NOT_APPLICABLE when selected actions require no authorization")
    if selected_auth_required:
        authorized_actions = {
            item.get("action_id")
            for item in auth_evaluations
            if isinstance(item, dict)
            and item.get("status") == "AUTHORIZED"
            and item.get("authorization_result_ref") is not None
        }
        if receipt.get("authorization_summary") == "ALL_REQUIRED_AUTHORIZED" and not selected_auth_required.issubset(authorized_actions):
            fail("RECEIPT_AUTH_SUMMARY_FAIL", "ALL_REQUIRED_AUTHORIZED lacks valid per-action authorization candidates")
    for reason in receipt.get("blocking_reasons", []) if isinstance(receipt.get("blocking_reasons"), list) else []:
        if isinstance(reason, dict) and reason.get("action_id") not in action_by_id:
            fail("RECEIPT_BLOCKING_ACTION_DANGLING", "blocking reason action does not resolve")

    if receipt.get("continuation_status") == "READY":
        if not selected_set or not selected_set.issubset(set(ready)) or selected_set & set(blocked):
            fail("RECEIPT_READY_ACTION_FAIL", "READY requires a nonempty selected set containing only READY actions")
        if receipt.get("blocking_reasons"):
            fail("RECEIPT_READY_BLOCKER_FAIL", "READY cannot coexist with blocking reasons")
        if receipt.get("processing_coverage") != "FULL" or receipt.get("processing_status") != "FULL":
            fail("RECEIPT_READY_PROCESSING_FAIL", "READY requires FULL processing status and coverage")
        if any(receipt.get(key) for key in ("unprocessed_modalities", "protected_spans_failed", "conflicts", "material_ambiguities", "external_state_rechecks")):
            fail("RECEIPT_READY_UNRESOLVED_FAIL", "READY cannot coexist with unresolved modality, span, conflict, ambiguity, or external-state items")
        if receipt.get("verification_mode") == "model_only":
            fail("RECEIPT_MODEL_ONLY_READY_UNESTABLISHED", "stored Receipt cannot establish the outside-Package one-shot model_only exception")
        if any(
            action_by_id[action_id].get(key)
            for action_id in selected_set
            for key in ("required_capabilities", "required_authorization_specs", "external_state_checks")
        ):
            fail("RECEIPT_READY_REQUIREMENT_FAIL", "READY selected action retains unresolved capability, authorization, or external-state requirements")
        completed_actions = {
            action_id
            for action_id, action in action_by_id.items()
            if action.get("eligibility_projection") == "COMPLETED"
        }
        for edge in graph.get("action_edges", []) if isinstance(graph.get("action_edges"), list) else []:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source_action_id")
            target = edge.get("target_action_id")
            relation = edge.get("relation")
            if relation == "REQUIRES" and source in selected_set and target not in completed_actions:
                fail("RECEIPT_READY_DEPENDENCY_FAIL", "selected READY action has an incomplete required target")
            if relation == "BEFORE" and target in selected_set and source not in completed_actions:
                fail("RECEIPT_READY_DEPENDENCY_FAIL", "selected READY action has an incomplete BEFORE predecessor")
            if relation == "EXCLUDES" and source in selected_set and target in selected_set:
                fail("RECEIPT_READY_EXCLUSION_FAIL", "READY selected set contains mutually exclusive actions")
        for group in graph.get("action_groups", []) if isinstance(graph.get("action_groups"), list) else []:
            if not isinstance(group, dict):
                continue
            members = set(group.get("member_action_ids", []))
            selected_members = members & selected_set
            if group.get("kind") == "EXACTLY_ONE" and len(selected_members) != 1:
                fail("RECEIPT_READY_GROUP_FAIL", "READY must select exactly one member of an EXACTLY_ONE group")
            if group.get("kind") == "AT_LEAST_ONE" and not selected_members:
                fail("RECEIPT_READY_GROUP_FAIL", "READY must select at least one member of an AT_LEAST_ONE group")
        if summary.get("approval_gate") == "PASS" and not approval_chain_valid:
            fail("RECEIPT_READY_APPROVAL_FAIL", "READY cannot use an unvalidated approval chain")
    return issues


def _inspect_detached(
    root: dict[str, Any],
    candidates: list[dict[str, Any]],
    validator: Validator,
    integrity_ref: dict[str, Any],
    *,
    warm: dict[str, Any] | None = None,
    review_bytes: bytes | None = None,
    integrity_kind: str = "bundle_manifest",
    deterministic_outcomes: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    parsed_candidates: list[dict[str, Any]] = []
    slots = {
        item.get("opaque_id"): item
        for item in root.get("detached_envelope_slots", [])
        if isinstance(item, dict) and isinstance(item.get("opaque_id"), str)
    }
    seen: set[str] = set()
    for candidate in candidates:
        opaque_id = candidate.get("opaque_id")
        if opaque_id in seen:
            issues.append(_problem("DETACHED_ID_DUPLICATE", "detached opaque ID is duplicated", object_id=opaque_id))
            continue
        seen.add(opaque_id)
        candidate_issue_start = len(issues)
        raw = candidate.get("bytes")
        if not isinstance(raw, bytes):
            issues.append(_problem("DETACHED_BYTES_MISSING", "detached candidate bytes are incomplete", object_id=opaque_id))
            continue
        try:
            payload = loads_strict(raw)
        except Exception:
            issues.append(_problem("DETACHED_JSON_FAIL", "detached candidate is not strict JSON", object_id=opaque_id))
            continue
        if not isinstance(payload, dict):
            issues.append(_problem("DETACHED_SCHEMA_FAIL", "detached candidate is not an object", object_id=opaque_id))
            continue
        try:
            check_json_depth(payload, maximum=MAX_JSON_DEPTH)
        except LCHError:
            issues.append(
                _problem(
                    "DETACHED_JSON_DEPTH_FAIL",
                    "detached candidate exceeds JSON depth limit",
                    object_id=opaque_id,
                )
            )
            continue
        problems = validator.validate(payload, "detached-envelope.schema.json")
        if problems:
            issues.extend(_problem("DETACHED_SCHEMA_FAIL", item.message + " at " + item.path, object_id=opaque_id) for item in problems)
            continue
        candidate_language = qualify_languages(payload)
        if (
            candidate_language.get("performed") is not True
            and candidate_language.get("language_tags_present") is True
        ):
            issues.append(
                _problem(
                    "DETACHED_LANGUAGE_QUALIFICATION_NOT_RUN",
                    "detached language qualification did not run",
                    object_id=opaque_id,
                )
            )
        elif candidate_language.get("result") != "PASS":
            issues.append(
                _problem(
                    "DETACHED_LANGUAGE_QUALIFICATION_FAIL",
                    "detached language tag is not qualified by the pinned registry",
                    object_id=opaque_id,
                )
            )
        payload_type = _detached_payload_type(payload)
        frame_type = candidate.get("type")
        if isinstance(frame_type, str) and frame_type != payload_type:
            issues.append(
                _problem(
                    "DETACHED_FRAME_TYPE_FAIL",
                    "detached frame type does not match the direct payload type",
                    object_id=opaque_id,
                )
            )
        slot = slots.get(opaque_id)
        if slot is None:
            issues.append(
                _problem(
                    "DETACHED_SLOT_UNKNOWN",
                    "detached candidate opaque ID has no preallocated root slot",
                    object_id=opaque_id,
                )
            )
        elif slot.get("expected_type") != payload_type:
            issues.append(_problem("DETACHED_SLOT_TYPE_FAIL", "detached payload type does not match slot", object_id=opaque_id))
        subject = payload.get("subject")
        if isinstance(subject, dict):
            if subject.get("package_id") is not None and subject.get("package_id") != root.get("package_id"):
                issues.append(
                    _problem(
                        "DETACHED_PACKAGE_ID_BINDING_FAIL",
                        "detached subject binds a different package ID",
                        object_id=opaque_id,
                    )
                )
            if subject.get("package_integrity_ref") is not None and subject.get("package_integrity_ref") != integrity_ref:
                issues.append(_problem("DETACHED_ROOT_BINDING_FAIL", "detached subject binds a different package root", object_id=opaque_id))
            if subject.get("canonical_state_digest") is not None and subject.get("canonical_state_digest") != root.get("canonical_state_digest"):
                issues.append(_problem("DETACHED_STATE_BINDING_FAIL", "detached subject binds a different state", object_id=opaque_id))
            if subject.get("profiles") is not None and subject.get("profiles") != root.get("profiles"):
                issues.append(
                    _problem(
                        "DETACHED_PROFILE_BINDING_FAIL",
                        "detached subject binds a different Profile set",
                        object_id=opaque_id,
                    )
                )
        if is_receipt_payload(payload):
            if payload.get("package_id") != root.get("package_id"):
                issues.append(
                    _problem(
                        "DETACHED_PACKAGE_ID_BINDING_FAIL",
                        "Receipt binds a different package ID",
                        object_id=opaque_id,
                    )
                )
            if payload.get("package_integrity_ref") != integrity_ref:
                issues.append(
                    _problem(
                        "DETACHED_ROOT_BINDING_FAIL",
                        "Receipt binds a different package root",
                        object_id=opaque_id,
                    )
                )
            if payload.get("canonical_state_digest") != root.get("canonical_state_digest"):
                issues.append(
                    _problem(
                        "DETACHED_STATE_BINDING_FAIL",
                        "Receipt binds a different canonical state",
                        object_id=opaque_id,
                    )
                )
            root_language = qualify_languages(root)
            language_profile = root.get("language_profile")
            declared_ranges = (
                language_profile.get("continuation_language_ranges", [])
                if isinstance(language_profile, dict)
                else []
            )
            selected_key = _canonical_language_from_report(
                candidate_language,
                payload.get("selected_continuation_language"),
            )
            range_keys = {
                key
                for key in (
                    _canonical_language_from_report(root_language, item)
                    for item in declared_ranges
                )
                if key is not None
            }
            if selected_key is not None and range_keys and selected_key not in range_keys:
                issues.append(
                    _problem(
                        "DETACHED_RECEIPT_LANGUAGE_SCOPE_FAIL",
                        "Receipt continuation language is outside the package language profile",
                        object_id=opaque_id,
                    )
                )
        parsed_candidates.append(
            {
                "opaque_id": opaque_id,
                "payload_type": payload_type,
                "payload": payload,
                "raw": raw,
                "base_valid": len(issues) == candidate_issue_start,
            }
        )
    approval_issues, approval_invalid_ids, approval_chain_valid = _approval_chain_issues(
        root,
        parsed_candidates,
        integrity_ref,
        warm,
        review_bytes,
        integrity_kind,
    )
    issues.extend(approval_issues)
    invalid_candidate_ids = approval_invalid_ids | {
        item.get("opaque_id")
        for item in parsed_candidates
        if item.get("base_valid") is not True and isinstance(item.get("opaque_id"), str)
    }
    for receipt_item in parsed_candidates:
        if receipt_item.get("payload_type") == "receiver_receipt":
            issues.extend(
                _receipt_invariant_issues(
                    receipt_item,
                    root,
                    warm,
                    parsed_candidates,
                    invalid_candidate_ids,
                    approval_chain_valid,
                    deterministic_outcomes or {},
                )
            )
    for opaque_id, slot in sorted(slots.items()):
        if slot.get("required") is True and opaque_id not in seen:
            issues.append(
                _problem(
                    "DETACHED_REQUIRED_MISSING",
                    "required detached slot has no captured candidate",
                    object_id=opaque_id,
                )
            )
    return issues


def _validate_bundle(path: Path, validator: Validator) -> dict[str, Any]:
    structure: list[dict[str, Any]] = []
    byte: list[dict[str, Any]] = []
    security: list[dict[str, Any]] = []
    source = BundleSource(path)
    root: dict[str, Any] | None = None
    warm: dict[str, Any] | None = None
    integrity_ref: dict[str, Any] | None = None
    review_bytes: bytes | None = None
    warm_valid = False
    object_bytes: dict[str, bytes] = {}
    detached: list[dict[str, Any]] = []
    detached_issues: list[dict[str, Any]] = []
    try:
        names = source.names()
        required = {"HANDOFF.md", "MANIFEST.json", "MANIFEST.sha256", "state/warm.json"}
        for name in sorted(required - set(names)):
            structure.append(_problem("REQUIRED_FILE_MISSING", f"required Bundle file is missing: {name}"))
        manifest_bytes = source.read("MANIFEST.json", max_bytes=MAX_JSON_BYTES)
        integrity_ref = {
            "kind": "bundle_manifest",
            "sha256": sha256_digest(manifest_bytes),
            "byte_length": len(manifest_bytes),
        }
        security.extend(
            scan_bytes(
                manifest_bytes,
                object_id="manifest",
                suffix=".json",
                logical_name="MANIFEST.json",
            )
        )
        try:
            root_value = loads_strict(manifest_bytes)
            if not isinstance(root_value, dict):
                raise ValueError
            check_json_depth(root_value, maximum=MAX_JSON_DEPTH)
            root = root_value
        except Exception:
            structure.append(_problem("MANIFEST_JSON_FAIL", "Manifest is not a strict JSON object", object_id="manifest"))
            byte.append(_problem("MANIFEST_JCS_FAIL", "Manifest cannot be canonicalized", object_id="manifest"))
            return _report("bundle", root, warm, integrity_ref, structure, byte, None, security)
        if canonicalize(root) != manifest_bytes:
            byte.append(_problem("MANIFEST_JCS_FAIL", "Manifest bytes are not exact JCS", object_id="manifest"))
        sidecar = (
            source.read("MANIFEST.sha256", max_bytes=65)
            if "MANIFEST.sha256" in names
            else None
        )
        if sidecar != (sha256_hex(manifest_bytes) + "\n").encode("ascii"):
            byte.append(_problem("MANIFEST_SIDECAR_FAIL", "MANIFEST.sha256 does not match exact root bytes", object_id="manifest"))
        structure.extend(_schema_problems(validator, root, "manifest.schema.json", object_id="manifest"))
        entries = root.get("objects", []) if isinstance(root.get("objects"), list) else []
        ids: set[str] = set()
        paths: set[str] = set()
        folded_paths: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            object_id = entry.get("object_id")
            location = entry.get("location") if isinstance(entry.get("location"), dict) else {}
            relative = location.get("path")
            if not isinstance(object_id, str):
                structure.append(_problem("OBJECT_ID_INVALID", "Manifest object ID must be a stable string"))
                continue
            if object_id in ids:
                structure.append(_problem("OBJECT_ID_DUPLICATE", "Manifest object ID is duplicated", object_id=object_id))
            ids.add(object_id)
            try:
                safe_relative_path(relative)
            except LCHError as exc:
                structure.append(_problem(exc.code, exc.message, object_id=object_id))
                continue
            if relative in paths or relative.casefold() in folded_paths:
                structure.append(_problem("OBJECT_PATH_COLLISION", "Manifest object path collides", object_id=object_id))
                continue
            paths.add(relative)
            folded_paths.add(relative.casefold())
            try:
                data = source.read(relative)
            except LCHError as exc:
                structure.append(_problem(exc.code, exc.message, object_id=object_id))
                byte.append(_problem("ROOTED_OBJECT_MISSING", "rooted object bytes are missing", object_id=object_id))
                continue
            object_bytes[object_id] = data
            if len(data) != entry.get("byte_length"):
                byte.append(_problem("OBJECT_LENGTH_FAIL", "rooted object byte length mismatch", object_id=object_id))
            if sha256_digest(data) != entry.get("sha256_raw"):
                byte.append(_problem("OBJECT_DIGEST_FAIL", "rooted object SHA-256 mismatch", object_id=object_id))
            security.extend(
                scan_bytes(
                    data,
                    object_id=object_id,
                    suffix=Path(relative).suffix,
                    media_type=str(entry.get("media_type", "")),
                    logical_name=relative,
                )
            )
            if relative == "HANDOFF.md":
                review_bytes = data
        allowed_names = {"MANIFEST.json", "MANIFEST.sha256", *paths}
        for name in names:
            if name not in allowed_names and not name.startswith("envelopes/"):
                structure.append(
                    _problem(
                        "UNROOTED_BUNDLE_FILE",
                        "Bundle contains a non-envelope file that is absent from the Manifest",
                        object_id=name,
                    )
                )
                try:
                    unrooted = source.read(name)
                except LCHError:
                    continue
                security.extend(
                    scan_bytes(
                        unrooted,
                        object_id=name,
                        suffix=Path(name).suffix,
                        logical_name=name,
                    )
                )
        try:
            warm_value = loads_strict(source.read("state/warm.json", max_bytes=MAX_JSON_BYTES))
            if not isinstance(warm_value, dict):
                raise ValueError
            check_json_depth(warm_value, maximum=MAX_JSON_DEPTH)
            warm = warm_value
        except Exception:
            structure.append(_problem("WARM_JSON_FAIL", "WARM state is not a strict JSON object", object_id="warm_state"))
        for name in names:
            if name.startswith("envelopes/"):
                raw = source.read(name)
                security.extend(
                    scan_bytes(
                        raw,
                        object_id=name,
                        suffix=Path(name).suffix,
                        logical_name=name,
                    )
                )
                if name == "envelopes/INDEX.json":
                    # v0.1 deliberately does not freeze an INDEX wire shape. Do
                    # not infer consistency from an unparsed hint or let it
                    # override actual captured bytes. Presence is an explicit
                    # processing limitation until a registered index grammar is
                    # available.
                    detached_issues.append(
                        _problem(
                            "DETACHED_INDEX_NOT_EVALUATED",
                            "non-authoritative envelope index was ignored and no index-consistency claim is made",
                            object_id=name,
                        )
                    )
                else:
                    detached.append({"opaque_id": Path(name).stem, "bytes": raw})
        if warm is not None:
            resource_issues = state_resource_issues(warm)
            structure.extend(
                _problem(code, "WARM state collection exceeds the frozen item limit", object_id=path)
                for code, path in resource_issues
            )
            warm_schema_issues = [] if resource_issues else _schema_problems(
                validator, warm, "state.schema.json", object_id="warm_state"
            )
            structure.extend(warm_schema_issues)
            if not resource_issues and not warm_schema_issues:
                warm_valid = True
                structure.extend(_state_invariants(warm, object_bytes, root))
                structure.extend(_legacy_conversion_issues(object_bytes, warm, validator))
            for code, object_id in manifest_reference_issues(entries, warm):
                structure.append(
                    _problem(
                        code,
                        "Manifest contains a dangling or cyclic object/source reference",
                        object_id=object_id,
                    )
                )
        structure.extend(_root_protocol_issues(root, warm))
        language, language_issues = _language_check(root, warm)
        structure.extend(language_issues)
        review_byte_issues, review = _review_check(
            root,
            warm if warm_valid else None,
            review_bytes,
            "bundle_manifest",
        )
        byte.extend(review_byte_issues)
        if integrity_ref is not None:
            detached_issues.extend(
                _inspect_detached(
                    root,
                    detached,
                    validator,
                    integrity_ref,
                    warm=warm if warm_valid else None,
                    review_bytes=review_bytes,
                    integrity_kind="bundle_manifest",
                    deterministic_outcomes={
                        "structure_conformance": (
                            "FAIL"
                            if structure
                            else (
                                "WARN"
                                if root_capability_warnings(root)
                                else "PASS"
                            )
                        ),
                        "byte_consistency": "FAIL" if byte else "VERIFIED",
                        "review_projection_conformance": (
                            None
                            if review is None
                            else ("FAIL" if review else "PASS")
                        ),
                    },
                )
            )
        return _report(
            "bundle",
            root,
            warm,
            integrity_ref,
            structure,
            byte,
            review,
            security,
            language,
            detached_issues,
        )
    finally:
        source.close()


def _validate_t0(path: Path, validator: Validator) -> dict[str, Any]:
    structure: list[dict[str, Any]] = []
    byte: list[dict[str, Any]] = []
    security: list[dict[str, Any]] = []
    detached_issues: list[dict[str, Any]] = []
    data = read_bytes(path, max_bytes=MAX_TOTAL_BYTES)
    parsed = parse_t0(data)
    root = parsed["control"]
    integrity_ref = parsed["package_integrity_ref"]
    for item in parsed.get("byte_issues", []):
        byte.append(
            _problem(
                str(item.get("code", "T0_BYTE_FAIL")),
                str(item.get("message", "T0 byte commitment failed")),
                object_id=item.get("object_id"),
            )
        )
    for item in parsed.get("compatibility_issues", []):
        structure.append(
            _problem(
                str(item.get("code", "T0_NONCANONICAL")),
                "T0 compatibility form is accepted for parsing but is not canonical",
                object_id=item.get("object_id"),
            )
        )
    security.extend(
        scan_bytes(
            parsed["control_bytes"],
            object_id="t0_control",
            suffix=".json",
            logical_name="t0-control.json",
        )
    )
    security.extend(
        scan_bytes(
            parsed["review_bytes"],
            object_id="review_projection",
            suffix=".md",
            logical_name="HANDOFF.md",
        )
    )
    structure.extend(_schema_problems(validator, root, "t0-control.schema.json", object_id="t0_control"))
    object_bytes: dict[str, bytes] = {}
    warm_candidates: list[dict[str, Any]] = []
    for item in parsed["objects"]:
        metadata, raw = item["metadata"], item["bytes"]
        object_id = metadata["object_id"]
        object_bytes[object_id] = raw
        security.extend(
            scan_bytes(
                raw,
                object_id=object_id,
                media_type=str(metadata.get("media_type", "")),
                logical_name=object_id,
            )
        )
        if metadata.get("media_type") == "application/json":
            try:
                candidate = loads_strict(raw)
                check_json_depth(candidate, maximum=MAX_JSON_DEPTH)
                if isinstance(candidate, dict) and set(WARM_KEYS).issubset(candidate):
                    warm_candidates.append(candidate)
            except Exception:
                pass
    warm = warm_candidates[0] if len(warm_candidates) == 1 else None
    warm_valid = False
    if warm is None:
        structure.append(_problem("WARM_OBJECT_COUNT_FAIL", "T0 must contain exactly one WARM state object", object_id="t0_control"))
    else:
        resource_issues = state_resource_issues(warm)
        structure.extend(
            _problem(code, "WARM state collection exceeds the frozen item limit", object_id=path)
            for code, path in resource_issues
        )
        warm_schema_issues = [] if resource_issues else _schema_problems(
            validator, warm, "state.schema.json", object_id="warm_state"
        )
        structure.extend(warm_schema_issues)
        if not resource_issues and not warm_schema_issues:
            warm_valid = True
            structure.extend(_state_invariants(warm, object_bytes, root))
            structure.extend(_legacy_conversion_issues(object_bytes, warm, validator))
    structure.extend(_root_protocol_issues(root, warm))
    language, language_issues = _language_check(root, warm)
    structure.extend(language_issues)
    for candidate in parsed["detached"]:
        raw = candidate.get("bytes")
        if isinstance(raw, bytes):
            security.extend(
                scan_bytes(
                    raw,
                    object_id=str(candidate.get("opaque_id", "detached")),
                    suffix=".json",
                    logical_name=str(candidate.get("opaque_id", "detached")) + ".json",
                )
            )
    review_byte_issues, review = _review_check(
        root,
        warm if warm_valid else None,
        parsed["review_bytes"],
        "t0_control",
    )
    byte.extend(review_byte_issues)
    detached_issues.extend(
        _inspect_detached(
            root,
            parsed["detached"],
            validator,
            integrity_ref,
            warm=warm if warm_valid else None,
            review_bytes=parsed["review_bytes"],
            integrity_kind="t0_control",
            deterministic_outcomes={
                "structure_conformance": (
                    "FAIL"
                    if structure
                    else (
                        "WARN"
                        if root_capability_warnings(root)
                        else "PASS"
                    )
                ),
                "byte_consistency": "FAIL" if byte else "VERIFIED",
                "review_projection_conformance": (
                    None if review is None else ("FAIL" if review else "PASS")
                ),
            },
        )
    )
    return _report(
        "t0",
        root,
        warm,
        integrity_ref,
        structure,
        byte,
        review,
        security,
        language,
        detached_issues,
    )


def _language_check(
    root: dict[str, Any] | None,
    warm: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(root, dict) or not isinstance(warm, dict):
        return (
            {
                "performed": False,
                "result": "NOT_RUN",
                "issues": [],
                "qualification_scope": None,
                "not_claimed": [],
            },
            [],
        )
    qualification = qualify_languages(root, warm)
    qualification = dict(qualification)
    required_multilingual = any(
        isinstance(profile, dict)
        and profile.get("id") == "urn:lch:profile:multilingual"
        and profile.get("version") == "0.1.0"
        and profile.get("required") is True
        for profile in root.get("profiles", [])
    )
    qualification["package_content_checks"] = {
        "generated_text_normalization": "NOT_RUN",
        "source_byte_preservation": "NOT_RUN",
        "protected_span_preservation": "NOT_RUN",
        "bidi_control_processing": "NOT_RUN",
        "full_uax9": "NOT_RUN",
        "full_uax29": "NOT_RUN",
        "full_uts39": "NOT_RUN",
    }
    qualification["required_profile_blocked"] = required_multilingual
    issues: list[dict[str, Any]] = []
    if qualification.get("performed") is True and qualification.get("result") != "PASS":
        for item in qualification.get("issues", []):
            issues.append(
                _problem(
                    str(item.get("code", "LANGUAGE_QUALIFICATION_FAIL")),
                    str(item.get("message", "language qualification failed")),
                    object_id="warm_state",
                )
            )
    elif (
        qualification.get("performed") is not True
        and qualification.get("language_tags_present") is True
    ):
        issues.append(
            _problem(
                "LANGUAGE_QUALIFICATION_NOT_RUN",
                "language tags are present but the pinned RFC 5646 qualification could not run",
                object_id="warm_state",
            )
        )
    return qualification, issues


def _review_check(
    root: dict[str, Any],
    warm: dict[str, Any] | None,
    actual: bytes | None,
    integrity_kind: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if warm is None or actual is None:
        return [], None
    byte_issues: list[dict[str, Any]] = []
    review_issues: list[dict[str, Any]] = []
    reference_value = root.get("review_projection_ref")
    reference = reference_value if isinstance(reference_value, dict) else {}
    if reference.get("projection_version") != "review-v1":
        review_issues.append(
            _problem(
                "REVIEW_VERSION_UNSUPPORTED",
                "review projection version is unavailable or unsupported",
                object_id="review_projection",
            )
        )
    materiality_ref = bundled_materiality_ref()
    if (
        root.get("materiality_profile_ref") != materiality_ref
        or warm.get("materiality_profile_ref") != materiality_ref
    ):
        review_issues.append(
            _problem(
                "REVIEW_MATERIALITY_PROFILE_FAIL",
                "review materiality Profile does not match the frozen bundled Profile",
                object_id="materiality-v1",
            )
        )
    if root_warm_mismatches(root, warm):
        review_issues.append(
            _problem(
                "REVIEW_ROOT_WARM_PREREQUISITE_FAIL",
                "review prerequisites disagree between root and WARM",
                object_id="review_projection",
            )
        )
    try:
        digest = canonical_state_digest(warm)
        if digest != root.get("canonical_state_digest"):
            byte_issues.append(_problem("CANONICAL_STATE_DIGEST_FAIL", "canonical state digest mismatch", object_id="warm_state"))
        expected = review_projection_v1(warm, _review_context(root, integrity_kind))
        if expected != actual:
            review_issues.append(_problem("REVIEW_BYTES_FAIL", "review projection does not match deterministic reconstruction", object_id="review_projection"))
        if len(actual) != reference.get("byte_length") or sha256_digest(actual) != reference.get("sha256_raw"):
            problem = _problem("REVIEW_REF_FAIL", "review projection reference does not match actual bytes", object_id="review_projection")
            byte_issues.append(problem)
            review_issues.append(dict(problem))
    except Exception as exc:
        review_issues.append(_problem("REVIEW_REBUILD_FAIL", "review projection reconstruction failed: " + type(exc).__name__, object_id="review_projection"))
    return byte_issues, review_issues


def _report(
    transport: str,
    root: dict[str, Any] | None,
    warm: dict[str, Any] | None,
    integrity_ref: dict[str, Any] | None,
    structure: list[dict[str, Any]],
    byte: list[dict[str, Any]],
    review: list[dict[str, Any]] | None,
    security: list[dict[str, Any]],
    language: dict[str, Any] | None = None,
    detached_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    language_report = language or {
        "performed": False,
        "result": "NOT_RUN",
        "issues": [],
        "qualification_scope": None,
        "not_claimed": [],
        "required_profile_blocked": False,
    }
    language_public = dict(language_report)
    language_public.update(
        {
            "check_kind": "registry_tag_qualification",
            "registry_tag_result": language_report.get("result"),
            "runtime_vector": {
                "performed": language_report.get("performed") is True,
                "vector_id": language_report.get("vector_id"),
                "qualification_scope": language_report.get("qualification_scope"),
                "unicode_version": language_report.get("unicode_version"),
                "registry_file_date": language_report.get("registry_file_date"),
                "registry_path": language_report.get("registry_path"),
                "registry_sha256_raw": language_report.get("registry_sha256_raw"),
                "registry_byte_length": language_report.get("registry_byte_length"),
                "extension_registry_file_date": language_report.get("extension_registry_file_date"),
                "extension_registry_path": language_report.get("extension_registry_path"),
                "extension_registry_sha256_raw": language_report.get("extension_registry_sha256_raw"),
                "extension_registry_byte_length": language_report.get("extension_registry_byte_length"),
            },
            "multilingual_profile_conformance": "NOT_RUN",
        }
    )
    non_claims = [
        "No origin, coverage, approval, authorization, semantic continuity, or lossless result was issued.",
        "Static security preflight is not a SECURITY_RUN_RESULT.",
        "MULTILINGUAL Profile conformance and I18N_RUN_RESULT were not issued.",
    ]
    if language_report.get("performed") is not True:
        non_claims.append(
            "Qualified BCP 47, Unicode, and MULTILINGUAL conformance were not claimed."
        )
    capability_warnings = root_capability_warnings(root) if isinstance(root, dict) else []
    capability_warning_issues = [
        {
            "code": code,
            "message": "optional Profile is preserved inert and cannot satisfy capabilities",
            "object_id": subject,
            "severity": "warning",
        }
        for code, subject in capability_warnings
    ]
    structure_result = (
        "FAIL" if structure else ("WARN" if capability_warning_issues else "PASS")
    )
    return {
        "ok": (
            not structure
            and not byte
            and review == []
            and not security
            and language_report.get("required_profile_blocked") is not True
            and not detached_issues
        ),
        "operation": "validate_handoff",
        "transport": transport,
        "package_id": root.get("package_id") if isinstance(root, dict) else None,
        "package_integrity_ref": integrity_ref,
        "canonical_state_digest": root.get("canonical_state_digest") if isinstance(root, dict) else None,
        "checks": {
            "structure_conformance": {
                "performed": True,
                "result": structure_result,
                "issues": structure + capability_warning_issues,
            },
            "byte_consistency": {"performed": True, "result": "FAIL" if byte else "VERIFIED", "issues": byte},
            "review_projection_conformance": {
                "performed": review is not None,
                "result": None if review is None else ("FAIL" if review else "PASS"),
                "issues": [] if review is None else review,
            },
        },
        "security_preflight": {
            "performed": True,
            "result": "BLOCKED" if security else "NO_HIT_DETECTED",
            "findings": security,
            "security_run_result_issued": False,
        },
        "language_qualification": language_public,
        "capability_processing": {
            "result": "WARN" if capability_warnings else "NO_ISSUES",
            "issues": [
                {
                    "code": "LCH-" + code.replace("_", "-"),
                    "message": "optional Profile is preserved inert and cannot satisfy capabilities",
                    "object_id": subject,
                }
                for code, subject in capability_warnings
            ],
        },
        "detached_candidates": {
            "performed": True,
            "result": "ISSUES" if detached_issues else "NO_ISSUES",
            "issues": detached_issues or [],
            "blocks_continuation": bool(detached_issues),
            "deterministic_result_issued": False,
        },
        "non_claims": non_claims,
        "_root": root,
        "_warm": warm,
    }


def validate_native(path: Path) -> dict[str, Any]:
    validator = Validator(SchemaStore(SCHEMA_DIRECTORY))
    transport = identify_transport(path)
    if transport == "bundle":
        return _validate_bundle(path, validator)
    return _validate_t0(lexical_absolute(path), validator)


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _wire_issue(item: dict[str, Any]) -> dict[str, Any]:
    code = re.sub(r"[^A-Z0-9]+", "-", str(item.get("code", "VALIDATION-FAIL")).upper()).strip("-")
    object_id = item.get("object_id")
    if not isinstance(object_id, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", object_id) is None:
        object_id = None
    severity = item.get("severity")
    if severity not in {"info", "warning", "error", "blocking"}:
        severity = "error"
    return {"code": "LCH-" + code, "severity": severity, "object_id": object_id}


def deterministic_results(
    report: dict[str, Any],
    *,
    principal_id: str,
    tenant_id: str | None,
    runtime: str,
    issued_at: str,
) -> list[dict[str, Any]]:
    root = report.get("_root")
    if not isinstance(root, dict) or not isinstance(report.get("package_integrity_ref"), dict):
        raise LCHError("RESULT_SUBJECT_UNAVAILABLE", "cannot issue results without a parsed root subject")
    state_digest = report.get("canonical_state_digest")
    if not isinstance(state_digest, str):
        raise LCHError("RESULT_SUBJECT_UNAVAILABLE", "cannot issue results without canonical_state_digest")
    issuer: dict[str, Any] = {
        "principal_id": principal_id,
        "runtime": runtime,
        "authority": "deterministic_verify",
    }
    if tenant_id is not None:
        issuer["tenant_id"] = tenant_id
    subject = {
        "package_id": root["package_id"],
        "package_integrity_ref": report["package_integrity_ref"],
        "canonical_state_digest": state_digest,
        "profiles": root.get("profiles", []),
    }
    mapping = (
        ("structure_conformance", "structure_conformance"),
        ("byte_consistency", "byte_consistency"),
        ("review_projection_conformance", "review_projection_conformance"),
    )
    results: list[dict[str, Any]] = []
    validator = Validator(SchemaStore(SCHEMA_DIRECTORY))
    for check_name, result_type in mapping:
        check = report["checks"][check_name]
        if not check["performed"]:
            continue
        integrity_sha = report["package_integrity_ref"].get("sha256", "")
        integrity_token = (
            integrity_sha.split(":", 1)[1]
            if isinstance(integrity_sha, str) and ":" in integrity_sha
            else "unknown"
        )
        payload = {
            "result_id": f"{result_type}.{integrity_token[:40]}",
            "type": result_type,
            "issuer": issuer,
            "subject": subject,
            "result": check["result"],
            "issues": [_wire_issue(item) for item in check["issues"]],
            "implementation_version": IMPLEMENTATION_VERSION,
            "issued_at": issued_at,
        }
        problems = validator.validate(payload, "verification-result.schema.json")
        if problems:
            raise LCHError("RESULT_SCHEMA_FAIL", "generated deterministic result fails Schema", details=[item.as_dict() for item in problems])
        results.append(payload)
    return results


def write_result_set(output: Path, results: list[dict[str, Any]]) -> list[str]:
    output = secure_output_path(output)
    stage = Path(tempfile.mkdtemp(prefix=".lch-results-", dir=str(output.parent)))
    names: list[str] = []
    try:
        os.chmod(stage, 0o700)
        for result in results:
            name = result["type"] + ".json"
            target = stage / name
            target.write_bytes(canonicalize(result))
            os.chmod(target, 0o600)
            names.append(name)
        atomic_commit_no_replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return sorted(names)
