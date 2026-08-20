"""Deterministic state and human-review projections for protocol version 0.1.

The functions in this module do not validate every cross-reference or graph rule;
the structural validator owns those checks.  They do fail closed on ambiguous input,
unknown semantic WARM fields, missing required projection fields, unsupported JSON
values, duplicate stable IDs, and cyclic transition history.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable, Mapping, Sequence

from .canonicalize import canonicalize, canonicalize_text, sha256_digest, sha256_hex


STATE_PROJECTION_VERSION = "state-projection-v1"
REVIEW_PROJECTION_VERSION = "review-v1"

WARM_KEYS = (
    "protocol_version",
    "state_projection_version",
    "boundaries",
    "source_inventory",
    "records",
    "transition_events",
    "action_graph",
    "current_projection",
    "content_coverage",
    "consistency_claim",
    "semantic_actionability_claim",
    "language_profile",
    "materiality_profile_ref",
)

WARM_BOUNDARY_KEYS = (
    "source_boundary",
    "scope",
    "policy_boundary",
    "external_state_dependencies",
)

# These keys may occur in a caller's staging object but never enter canonical state.
# Unknown keys not on this explicit list fail closed instead of being silently lost.
EXCLUDED_STATE_METADATA_KEYS = frozenset(
    {
        "package_id",
        "created_at",
        "producer",
        "runtime",
        "receiver",
        "received_at",
        "storage_path",
        "storage_paths",
        "rendered_views",
        "translations",
        "signatures",
        "detached_results",
        "receipts",
        "receipt",
        "envelopes",
        "package_integrity_ref",
        "review_projection_ref",
    }
)

REVIEW_SECTION_HEADINGS = (
    "## 1. Protocol and rooted state",
    "## 2. Boundaries, requests, exclusions, and recipient",
    "## 3. Current intent and phase",
    "## 4. Active decisions and conflicts",
    "## 5. Negative knowledge and questions",
    "## 6. Constraints, sensitivity, freshness, and rechecks",
    "## 7. Action graph",
    "## 8. Coverage, inventory, omissions, modalities, and conflicts",
    "## 9. Approval slot and detached-envelope policy",
)

REVIEW_CONTEXT_KEYS = frozenset(
    {
        "protocol_id",
        "package_id",
        "profiles",
        "integrity_kind",
        "integrity_algorithm",
        "canonical_state_digest",
        "recipient_and_sharing_scope",
        "detached_envelope_policy",
    }
)

DERIVED_DIGEST_PROFILE = "lch-derived-digest-v1"
DERIVED_DIGEST_TYPES = frozenset(
    {
        "scope_digest",
        "material_exclusions_digest",
        "recipient_binding_digest",
        "display_evidence_digest",
        "materiality_profile_digest",
        "package_profile_digest",
        "read_set_digest",
        "processing_coverage_digest",
        "purpose_digest",
        "constraints_digest",
        "inventory_digest",
        "approval_statement_digest",
        "receipt_sha256",
        "revision_digest",
    }
)


class ProjectionError(ValueError):
    """Raised when a deterministic projection cannot be constructed safely."""


def _mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise ProjectionError(name + " must be a JSON object")
    return value


def _list(value: Any, *, name: str) -> list[Any]:
    if type(value) is not list:
        raise ProjectionError(name + " must be a JSON array")
    return value


def _json_clone(value: Any) -> Any:
    # canonicalize validates the restricted JSON value space before deepcopy.
    canonicalize(value)
    return deepcopy(value)


def _utf16_key(text: str) -> bytes:
    try:
        return text.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc:
        raise ProjectionError("stable ID contains a lone surrogate") from exc


def _stable_objects(
    values: Sequence[Any], *, id_key: str, name: str
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        item = _mapping(value, name=f"{name}[{index}]")
        identifier = item.get(id_key)
        if type(identifier) is not str or not identifier:
            raise ProjectionError(f"{name}[{index}].{id_key} must be a stable ID")
        if identifier in seen:
            raise ProjectionError(f"duplicate {name} stable ID: {identifier}")
        seen.add(identifier)
        result.append(dict(item))
    return sorted(result, key=lambda item: _utf16_key(item[id_key]))


def _sorted_unique_strings(value: Any, *, name: str) -> list[str]:
    items = _list(value, name=name)
    if any(type(item) is not str for item in items):
        raise ProjectionError(name + " must contain only strings")
    if len(set(items)) != len(items):
        raise ProjectionError(name + " contains duplicate IDs")
    return sorted(items, key=_utf16_key)


def state_projection_v1(warm: Mapping[str, Any]) -> dict[str, Any]:
    """Select the fixed canonical WARM state for ``state-projection-v1``.

    The thirteen fixed WARM members are required.  Explicit transport and run
    metadata is ignored because it is outside canonical state.  Any other unknown
    member fails closed; callers must not smuggle future semantic state through an
    unversioned projection.
    """

    source = _mapping(warm, name="WARM state")
    keys = set(source)
    required = set(WARM_KEYS)
    missing = required - keys
    if missing:
        raise ProjectionError(
            "WARM state is missing required keys: " + ", ".join(sorted(missing))
        )
    unknown = keys - required - EXCLUDED_STATE_METADATA_KEYS
    if unknown:
        raise ProjectionError(
            "WARM state has unknown semantic keys: " + ", ".join(sorted(unknown))
        )
    if source["state_projection_version"] != STATE_PROJECTION_VERSION:
        raise ProjectionError(
            "unsupported state projection version: "
            + repr(source["state_projection_version"])
        )

    boundaries = _mapping(source["boundaries"], name="boundaries")
    boundary_keys = set(boundaries)
    expected_boundaries = set(WARM_BOUNDARY_KEYS)
    if boundary_keys != expected_boundaries:
        missing_boundaries = expected_boundaries - boundary_keys
        unknown_boundaries = boundary_keys - expected_boundaries
        details: list[str] = []
        if missing_boundaries:
            details.append("missing " + ", ".join(sorted(missing_boundaries)))
        if unknown_boundaries:
            details.append("unknown " + ", ".join(sorted(unknown_boundaries)))
        raise ProjectionError("invalid boundaries object: " + "; ".join(details))

    projected = {key: _json_clone(source[key]) for key in WARM_KEYS}
    canonicalize(projected)
    return projected


def canonical_state_bytes(warm: Mapping[str, Any]) -> bytes:
    """Return exact JCS UTF-8 bytes for ``state_projection_v1``."""

    return canonicalize(state_projection_v1(warm))


def canonical_state_digest_hex(warm: Mapping[str, Any]) -> str:
    """Return lowercase SHA-256 hex for the canonical state bytes."""

    return sha256_hex(canonical_state_bytes(warm))


def canonical_state_digest(warm: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` for the canonical state bytes."""

    return sha256_digest(canonical_state_bytes(warm))


def derived_digest_v1(
    digest_type: str, value: Any, protocol_version: str = "0.1.0"
) -> str:
    """Return a protocol ``lch-derived-digest-v1`` digest.

    The caller supplies the already selected and protocol-ordered ``value``.  This
    helper deliberately refuses unknown digest families and protocol versions so an
    implementation cannot silently create an incompatible projection.  Restricted
    JCS validation, UTF-8 encoding, and fail-closed handling of unsupported JSON
    values are delegated to :func:`canonicalize`.
    """

    if type(digest_type) is not str or digest_type not in DERIVED_DIGEST_TYPES:
        raise ProjectionError("unsupported derived digest type: " + repr(digest_type))
    if protocol_version != "0.1.0":
        raise ProjectionError(
            "unsupported derived digest protocol version: "
            + repr(protocol_version)
        )
    envelope = {
        "digest_profile": DERIVED_DIGEST_PROFILE,
        "digest_type": digest_type,
        "protocol_version": protocol_version,
        "value": _json_clone(value),
    }
    return sha256_digest(canonicalize(envelope))


def _causal_events(events: Sequence[Any]) -> list[dict[str, Any]]:
    ordered = _stable_objects(events, id_key="event_id", name="transition_events")
    by_id = {event["event_id"]: event for event in ordered}
    parents: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {event_id: set() for event_id in by_id}

    for event_id, event in by_id.items():
        previous = event.get("previous_event_ids", [])
        previous_ids = _sorted_unique_strings(
            previous, name=f"transition event {event_id}.previous_event_ids"
        )
        unknown = set(previous_ids) - set(by_id)
        if unknown:
            raise ProjectionError(
                "transition event references missing parent(s): "
                + ", ".join(sorted(unknown))
            )
        parents[event_id] = set(previous_ids)
        for parent in previous_ids:
            children[parent].add(event_id)

    ready = sorted(
        (event_id for event_id, values in parents.items() if not values),
        key=_utf16_key,
    )
    result: list[dict[str, Any]] = []
    while ready:
        event_id = ready.pop(0)
        result.append(by_id[event_id])
        for child in sorted(children[event_id], key=_utf16_key):
            parents[child].discard(event_id)
            if not parents[child] and child not in ready:
                ready.append(child)
        ready.sort(key=_utf16_key)

    if len(result) != len(ordered):
        raise ProjectionError("transition event graph contains a cycle")
    return result


def _records(warm: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _stable_objects(
        _list(warm["records"], name="records"), id_key="id", name="records"
    )


def _select_records(
    records: Iterable[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> list[dict[str, Any]]:
    return [record for record in records if predicate(record)]


def _normalized_action_graph(value: Any) -> dict[str, Any]:
    graph = dict(_mapping(value, name="action_graph"))
    required = {
        "action_graph_revision",
        "actions",
        "action_edges",
        "action_groups",
        "recommendation_basis_ids",
    }
    missing = required - set(graph)
    if missing:
        raise ProjectionError(
            "action_graph is missing required keys: " + ", ".join(sorted(missing))
        )
    graph["actions"] = _stable_objects(
        _list(graph["actions"], name="action_graph.actions"),
        id_key="action_id",
        name="action_graph.actions",
    )
    graph["action_edges"] = _stable_objects(
        _list(graph["action_edges"], name="action_graph.action_edges"),
        id_key="edge_id",
        name="action_graph.action_edges",
    )
    graph["action_groups"] = _stable_objects(
        _list(graph["action_groups"], name="action_graph.action_groups"),
        id_key="group_id",
        name="action_graph.action_groups",
    )
    graph["recommendation_basis_ids"] = _sorted_unique_strings(
        graph["recommendation_basis_ids"],
        name="action_graph.recommendation_basis_ids",
    )
    return graph


def _jcs_block(label: str, value: Any) -> str:
    # Canonical JSON is one line, so four-space Markdown indentation cannot be
    # terminated by attacker-controlled text or backticks.
    return f"- {label} (JCS):\n\n    {canonicalize_text(value)}\n"


def _section(heading: str, blocks: Sequence[str]) -> str:
    return heading + "\n\n" + "\n".join(blocks).rstrip() + "\n"


def _review_context(value: Mapping[str, Any]) -> dict[str, Any]:
    context = dict(_mapping(value, name="review context"))
    unknown = set(context) - REVIEW_CONTEXT_KEYS
    if unknown:
        raise ProjectionError(
            "review context has unknown keys: " + ", ".join(sorted(unknown))
        )
    required = {
        "package_id",
        "profiles",
        "integrity_kind",
        "recipient_and_sharing_scope",
        "detached_envelope_policy",
    }
    missing = required - set(context)
    if missing:
        raise ProjectionError(
            "review context is missing required keys: " + ", ".join(sorted(missing))
        )
    context.setdefault("protocol_id", "lossless-context-handoff")
    context.setdefault("integrity_algorithm", "sha-256")
    if context["integrity_kind"] not in {"t0_control", "bundle_manifest"}:
        raise ProjectionError("invalid review integrity_kind")
    if context["integrity_algorithm"] != "sha-256":
        raise ProjectionError("unsupported review integrity_algorithm")
    canonicalize(context)
    context["profiles"] = _stable_objects(
        _list(context["profiles"], name="review context profiles"),
        id_key="id",
        name="review context profiles",
    )
    context["detached_envelope_policy"] = _stable_objects(
        _list(
            context["detached_envelope_policy"],
            name="review context detached_envelope_policy",
        ),
        id_key="opaque_id",
        name="review context detached_envelope_policy",
    )
    return context


def _approval_statement_slot(
    boundaries: Mapping[str, Any], detached_policy: Any
) -> Any:
    scope = _mapping(boundaries["scope"], name="boundaries.scope")
    scoped_slot = scope.get("approval_statement_slot")
    slots = detached_policy if type(detached_policy) is list else []
    matching = [
        slot.get("opaque_id")
        for slot in slots
        if type(slot) is dict and slot.get("expected_type") == "approval_statement"
    ]
    matching = [item for item in matching if type(item) is str]
    if scoped_slot is not None and type(scoped_slot) is not str:
        raise ProjectionError("scope approval_statement_slot must be a stable ID")
    if scoped_slot is not None and matching and scoped_slot not in matching:
        raise ProjectionError("scope and detached policy approval slots disagree")
    if scoped_slot is not None:
        return scoped_slot
    if len(matching) == 1:
        return matching[0]
    raise ProjectionError("exactly one approval statement slot is required")


def review_projection_v1(
    warm: Mapping[str, Any], review_context: Mapping[str, Any]
) -> bytes:
    """Build the exact nine-section ``review_projection_v1`` Markdown bytes.

    ``review_context`` contains rooted review inputs that are intentionally outside
    canonical WARM state: package identity, Profile list, integrity kind (never the
    not-yet-computed root digest), recipient/sharing scope, and the detached-envelope
    policy.  Slot ``purpose`` values are rendered as their full JSON value and may be
    ``LocalizedText`` objects.  Direct detached payload framing does not affect this
    projection.
    """

    projected = state_projection_v1(warm)
    context = _review_context(review_context)
    state_digest = canonical_state_digest(projected)
    declared_digest = context.get("canonical_state_digest")
    if declared_digest is not None and declared_digest != state_digest:
        raise ProjectionError("review context canonical_state_digest mismatch")

    records = _records(projected)
    events = _causal_events(
        _list(projected["transition_events"], name="transition_events")
    )
    current = _mapping(projected["current_projection"], name="current_projection")
    current_intent_id = current.get("current_intent_id")
    if type(current_intent_id) is not str:
        raise ProjectionError("current_projection.current_intent_id is required")
    current_intents = [record for record in records if record["id"] == current_intent_id]
    if len(current_intents) != 1 or current_intents[0].get("type") != "intent":
        raise ProjectionError("current intent ID does not resolve to one intent record")

    active_decisions = _select_records(
        records,
        lambda record: record.get("type") == "decision"
        and record.get("lifecycle") == "ACTIVE",
    )
    decision_ids = {record["id"] for record in active_decisions}
    decision_events = [event for event in events if event.get("record_id") in decision_ids]

    negative_records = _select_records(
        records,
        lambda record: (
            record.get("lifecycle") in {"REJECTED", "SUPERSEDED", "ABANDONED"}
            or record.get("outcome") in {"FAILED", "INCONCLUSIVE", "ABORTED"}
            or record.get("verification") in {"DISPUTED", "REFUTED"}
        ),
    )
    questions = _select_records(records, lambda record: record.get("type") == "question")
    constraints = _select_records(
        records,
        lambda record: record.get("type") == "constraint"
        and record.get("lifecycle") == "ACTIVE",
    )
    freshness_records = _select_records(
        records,
        lambda record: (
            record.get("freshness") in {"STALE", "UNKNOWN"}
            or record.get("temporal_validity") in {"STALE", "EXPIRED", "UNKNOWN"}
            or (
                type(record.get("temporal")) is dict
                and (
                    record["temporal"].get("expires_at") is not None
                    or record["temporal"].get("revalidate_before") is not None
                )
            )
        ),
    )
    conflict_records = _select_records(
        records,
        lambda record: record.get("verification") in {"DISPUTED", "REFUTED"},
    )
    artifacts = _select_records(records, lambda record: record.get("type") == "artifact")
    boundaries = _mapping(projected["boundaries"], name="boundaries")
    scope = _mapping(boundaries["scope"], name="boundaries.scope")
    content_coverage = _mapping(
        projected["content_coverage"], name="content_coverage"
    )
    approval_slot = _approval_statement_slot(
        boundaries, context["detached_envelope_policy"]
    )

    section_1 = _section(
        REVIEW_SECTION_HEADINGS[0],
        [
            _jcs_block("Protocol", {
                "protocol_id": context["protocol_id"],
                "protocol_version": projected["protocol_version"],
            }),
            _jcs_block("Profiles", context["profiles"]),
            _jcs_block("Package ID", context["package_id"]),
            _jcs_block("Integrity kind", context["integrity_kind"]),
            _jcs_block("Integrity algorithm", context["integrity_algorithm"]),
            _jcs_block("Canonical state digest", state_digest),
            _jcs_block("Materiality profile", projected["materiality_profile_ref"]),
        ],
    )
    section_2 = _section(
        REVIEW_SECTION_HEADINGS[1],
        [
            _jcs_block("Boundaries", boundaries),
            _jcs_block(
                "Original user request refs",
                _sorted_unique_strings(
                    scope.get("user_request_refs", []),
                    name="scope.user_request_refs",
                ),
            ),
            _jcs_block(
                "Material exclusion IDs",
                _sorted_unique_strings(
                    scope.get("material_exclusion_ids", []),
                    name="scope.material_exclusion_ids",
                ),
            ),
            _jcs_block(
                "Recipient and sharing scope",
                context["recipient_and_sharing_scope"],
            ),
        ],
    )
    current_intent_events = [
        event for event in events if event.get("record_id") == current_intent_id
    ]
    section_3 = _section(
        REVIEW_SECTION_HEADINGS[2],
        [
            _jcs_block("Current intent", current_intents[0]),
            _jcs_block("Intent evolution events", current_intent_events),
            _jcs_block("Current phase", current.get("current_phase")),
        ],
    )
    section_4 = _section(
        REVIEW_SECTION_HEADINGS[3],
        [
            _jcs_block("Active decisions", active_decisions),
            _jcs_block("Decision evolution events", decision_events),
            _jcs_block("Consistency claim", projected["consistency_claim"]),
            _jcs_block("Conflict records", conflict_records),
        ],
    )
    section_5 = _section(
        REVIEW_SECTION_HEADINGS[4],
        [
            _jcs_block("Rejected, superseded, failed, or prohibited records", negative_records),
            _jcs_block("Answered and open questions", questions),
        ],
    )
    section_6 = _section(
        REVIEW_SECTION_HEADINGS[5],
        [
            _jcs_block("Active constraints", constraints),
            _jcs_block("Policy and sensitivity boundary", boundaries["policy_boundary"]),
            _jcs_block("Freshness and recheck records", freshness_records),
            _jcs_block(
                "External state dependencies",
                boundaries["external_state_dependencies"],
            ),
        ],
    )
    section_7 = _section(
        REVIEW_SECTION_HEADINGS[6],
        [_jcs_block("Complete active action graph", _normalized_action_graph(projected["action_graph"]))],
    )
    section_8 = _section(
        REVIEW_SECTION_HEADINGS[7],
        [
            _jcs_block("Content coverage claim", content_coverage),
            _jcs_block("Source inventory", projected["source_inventory"]),
            _jcs_block("Omissions", content_coverage.get("omissions", [])),
            _jcs_block("Artifact and modality records", artifacts),
            _jcs_block("Consistency and conflicts", {
                "consistency_claim": projected["consistency_claim"],
                "conflict_records": conflict_records,
            }),
        ],
    )
    section_9 = _section(
        REVIEW_SECTION_HEADINGS[8],
        [
            _jcs_block("Approval statement slot", approval_slot),
            _jcs_block(
                "Detached-envelope policy",
                context["detached_envelope_policy"],
            ),
            (
                "This is the pending-approval review projection for the exact root. "
                "Display the final `package_integrity_ref` separately after sealing "
                "and bind it with these review bytes in approval display evidence.\n"
            ),
        ],
    )

    text = "# Context Handoff Review Projection\n\n" + "\n".join(
        (
            section_1,
            section_2,
            section_3,
            section_4,
            section_5,
            section_6,
            section_7,
            section_8,
            section_9,
        )
    )
    if text.startswith("\ufeff") or "\r" in text:
        raise ProjectionError("review projection encoding invariant failed")
    return text.encode("utf-8", errors="strict")


def review_projection_digest(
    warm: Mapping[str, Any], review_context: Mapping[str, Any]
) -> str:
    """Return ``sha256:<hex>`` for exact ``review_projection_v1`` bytes."""

    return sha256_digest(review_projection_v1(warm, review_context))
