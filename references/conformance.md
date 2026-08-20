# Protocol Conformance

> Scope: LCH 0.1 audit conformance. Ordinary human-first handoffs are governed by
> `simple-workflow.md` and do not emit this result set by default.

This document defines conformance boundaries for native handoff artifacts, Receipts,
Profiles, and deterministic implementations. Conformance does not measure semantic
continuity. Semantic evaluation belongs to registered Receiver runs and benchmarks.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative as defined by
RFC 2119 and RFC 8174.

## Contents

- [Conformance classes](#conformance-classes)
- [Evidence requirements](#evidence-requirements)
- [Validation order](#validation-order)
- [Release registry and offline Schema checks](#release-registry-and-offline-schema-checks)
- [Transport identification](#transport-identification)
- [Structure conformance](#structure-conformance)
- [State and action graph checks](#state-and-action-graph-checks)
- [Byte consistency](#byte-consistency)
- [Review projection checks](#review-projection-checks)
- [Detached envelope checks](#detached-envelope-checks)
- [Candidate and summary checks](#candidate-and-summary-checks)
- [Approval and authorization checks](#approval-and-authorization-checks)
- [Receipt conformance](#receipt-conformance)
- [Profile conformance](#profile-conformance)
- [Security conformance boundary](#security-conformance-boundary)
- [Model-only behavior conformance](#model-only-behavior-conformance)
- [Legacy conversion conformance](#legacy-conversion-conformance)
- [Idempotence and interoperability](#idempotence-and-interoperability)
- [Result emission](#result-emission)
- [Non-claims](#non-claims)

## Conformance classes

The protocol separates these conformance classes:

1. **Artifact structure conformance** covers transport framing, Schema, required
   fields, references, graphs, Profiles, and structural rules.
2. **Byte consistency** covers the integrity root and all bytes committed by it.
3. **Review projection conformance** covers deterministic reconstruction and exact
   human-view byte equality.
4. **Profile conformance** covers requirements of one exact Profile version.
5. **Receipt conformance** covers Receiver bindings, candidate handling, summaries,
   processing state, selected actions, and attestation structure.
6. **Security run conformance** covers one declared Runtime and malicious fixture
   under one sandbox and tool posture.
7. **Legacy conversion conformance** covers frozen detection and mapping rules.

These classes do not collapse into one PASS. Each result uses its own role and exact
subject.

`RECEIVER_RUN_RESULT`, `I18N_RUN_RESULT`, and `BENCHMARK_RESULT` are evaluation
results, not conformance classes in this document.

## Evidence requirements

A reproducible conformance record identifies:

- protocol version;
- selected Profile IDs and versions;
- implementation version and dependencies;
- exact `package_integrity_ref`;
- `canonical_state_digest` when available;
- Runtime and capability mode;
- checks performed and checks not run;
- raw result objects and issues;
- fixture or test-vector identifier;
- run time and applicable trust anchors;
- process status for deterministic CLI execution.

Evidence MUST include failures and warnings. A report that discards failed cases is
not valid conformance evidence.

Conformance data MUST NOT expose secrets, unauthorized personal data, or quarantined
source bytes.

## Validation order

A deterministic implementation follows this order:

1. Stage input with restrictive permissions.
2. Enforce object count, byte, archive, graph, JSON depth, time, and token limits.
3. Identify T0 or Bundle without trusting natural-language content.
4. Parse framing and capture exact bytes.
5. Recompute the single integrity root and rooted object digests.
6. Verify the release Profile/Feature registry, offline Schema catalog, and
   hash-bound vector catalog locks.
7. Pre-register the complete local Schema catalog with remote retrieval disabled.
8. Validate protocol and Profile versions and `must_understand`.
9. Validate Schema, IDs, references, state events, action graph, and boundaries.
10. Recompute canonical state when the deterministic projection is available.
11. Rebuild and compare the review projection.
12. Inspect detached envelopes structurally without granting trust.
13. Emit only results owned by the active role.

The implementation keeps tools, active content, external fetches, and side effects
disabled during untrusted parsing.

Failure in an earlier safety stage MAY stop later parsing. The result and issue list
must identify which later checks did not run.

## Release registry and offline Schema checks

For release `0.1.0`, verify the raw and restricted-JCS canonical length/hash pairs in
`assets/protocol-version.json` for both
`assets/registry/profile-feature-registry-v0.1.json` and
`assets/registry/schema-catalog-v0.1.json`.

Profile processing then requires:

1. every root Profile ID occurs exactly once;
2. every exact registered selectable Profile ID/version pair resolves to exactly one
   verified registry entry and only that entry supplies semantics;
3. an exact registered entry with `selectable: false` or status `UNSUPPORTED` is
   rejected regardless of its `required` value;
4. a registered Feature ID in `profiles`, including
   `urn:lch:feature:detached-envelopes` at any version, is always rejected;
5. an unknown ID or unsupported version with `required: true` is
   `STRUCTURE_CONFORMANCE: FAIL`;
6. an unknown ID or unsupported version with `required: false` is preserved exactly
   but kept inert, produces `STRUCTURE_CONFORMANCE: WARN`, and is surfaced as a
   nonblocking processing issue;
7. an inert optional entry never satisfies a capability or requirement and never
   affects parsing, state, claims, policy, authorization, or continuation semantics;
8. a `domain-*.md` guide name is not a Profile ID and is rejected; a syntactically
   valid unregistered URI that resembles a domain Profile follows rules 5-7 and
   receives no domain-guide semantics;
9. a duplicate ID, including a version conflict for the same ID, is
   `STRUCTURE_CONFORMANCE: FAIL`.

Schema processing then requires:

1. every catalog ID and path is unique;
2. every local file's raw length, raw SHA-256, and embedded `$id` match its entry;
3. every release `$id` is `urn:lch:schema:0.1:<name>`;
4. all catalog resources are pre-registered before resolving any `$ref`;
5. the JSON Schema 2020-12 dialect is supplied by the validator as a built-in;
6. no HTTP, HTTPS, file, or other remote/dynamic retrieval occurs;
7. a missing, unlisted, mismatched, duplicate, or remotely resolved Schema fails
   structure conformance.

The `$schema` URI selects a locally supplied dialect. It is not a network location
for VERIFY. A validator that would fetch it or an unresolved `$ref` MUST fail closed
before doing so.

Release Schemas use default JSON Schema 2020-12 semantics: `format` is annotation,
not an enabled assertion vocabulary. Schema validation is therefore the shape phase
of structure validation. Before issuing `STRUCTURE_CONFORMANCE: PASS` or `WARN`, the
LCH verifier additionally performs the deterministic format checks frozen in
`wire-format.md` for every annotated value:

1. RFC 3986 absolute ASCII URI syntax, including scheme and percent-encoding
   validation without parser recovery, decoding, or normalization;
2. RFC 3339 syntax, calendar validity, and component ranges under the release's
   documented lexical leap-second policy;
3. RFC 5646 language-tag qualification against both pinned IANA registries and the
   registered release rules.

A generic validator that ignores `format`, or merely reports its implementation's
optional format behavior, cannot issue LCH `STRUCTURE_CONFORMANCE: PASS`. Its Schema
success is retained only as shape-validation evidence until all required LCH checks
run. Release `0.1.0` does not define a custom JSON Schema dialect or meta-Schema.

Vector qualification then requires:

1. verify the raw and restricted-JCS canonical commitments for
   `assets/vectors/index.json` from `assets/protocol-version.json`;
2. validate the catalog against `vector-catalog.schema.json`;
3. require exactly four unique entries and exactly four vector JSON files other than
   the catalog itself;
4. verify every vector's raw and canonical length/hash and matching internal
   `vector_id`/`kind`;
5. reject a missing, duplicate, extra, uncataloged, or mismatched vector;
6. resolve core qualification only to JCS, review, and derived-digest vectors, and
   multilingual qualification only to the language/Unicode vector;
7. require the legacy direct `language_unicode_vector` compatibility descriptor in
   `protocol-version.json` to equal the language entry in the vector catalog exactly.

An independently supplied fixture can be reported separately, but it is not release
Profile qualification evidence until a future locked catalog includes it.

## Transport identification

A T0 artifact is identified only by the fixed ASCII `LCH-T0 <major.minor>` framing
and its declared control length. Markdown headings and fences are not format signals.

A Bundle is identified by its required native files and exact Manifest rules. An
ordinary file named `HANDOFF.md` without the native root is not a Bundle.

A plain `HANDOFF.md`, OCH Snapshot, or LTM CMP is routed to `CONVERT_LEGACY`.
Format guessing from prose is not conformant.

An unsupported major protocol version, an unknown or unsupported-version required
Profile, or an unknown `must_understand` value causes rejection. Unknown optional
extensions and unknown/unsupported-version optional Profile entries are preserved
without activation; an optional Profile entry additionally requires the WARN and
processing issue defined above.

## Structure conformance

`STRUCTURE_CONFORMANCE` checks at least:

- required transport fields and object presence;
- duplicate JSON keys and invalid Unicode handling;
- safe paths, path uniqueness, and collision rules;
- stable ID uniqueness and reference resolution;
- legal Record types and orthogonal state axes;
- transition-event and action-graph constraints;
- source, scope, policy, and external-state boundaries;
- content coverage claim structure and omissions;
- selected Profile declarations and versions;
- `detached_envelope_slots` structure;
- required review projection commitments;
- Package claim value legality;
- conversion metadata when present.

It also compares, by exact JSON value, root and WARM copies of all four boundaries,
language and materiality Profiles, content coverage, consistency, and semantic
actionability, including `root.content_coverage.scope == warm.boundaries.scope`.
It requires the root scope, approval claim, and exactly one required
approval-statement slot to name the same opaque ID; every coverage slot reference to
resolve; and all slot IDs and `(opaque_id, expected_type)` pairs to be unique.

Every omission has one unique `omission_id`. Every
`scope.material_exclusion_ids` member resolves exactly once to
`content_coverage.omissions[].omission_id`. Conversely, every policy exclusion that
`materiality-v1` classifies as BLOCKING or MATERIAL is present in that ID set.
Failure of any equality or closure rule is `STRUCTURE_CONFORMANCE: FAIL`; no
implementation may select one duplicate projection as newer.

The Producer coverage claim also obeys this deterministic cross-field table. These
checks establish internal consistency only; they do not upgrade the claim into an
audited coverage result.

| `content_coverage.claim` | Required cross-field conditions |
| --- | --- |
| `COMPLETE` | `source_access` is `FULL`; `raw_coverage` is `FULL_WITHIN_SCOPE`; `artifact_coverage` is `FULL`, or is `NOT_APPLICABLE` only when the anchored scope and inventory contain no material artifact requirement; neither `content_coverage.omissions` nor `source_inventory.gaps` contains a BLOCKING or MATERIAL item. |
| `PARTIAL` | At least one established material gap exists: `source_access` is `PARTIAL`, `raw_coverage` is `PARTIAL` or `NONE`, material artifact coverage is `PARTIAL` or `NONE`, or a BLOCKING/MATERIAL omission or inventory gap exists. |
| `UNKNOWN` | Completeness cannot be decided and no already-established material gap requires `PARTIAL`; this includes `source_access: UNKNOWN`, `raw_coverage: UNKNOWN`, or an unanchored/indeterminate source boundary. |

An established `PARTIAL` condition takes precedence over `UNKNOWN`. Empty omission
arrays do not make `UNKNOWN`, `NONE`, or `PARTIAL` dimensions complete. A
`COMPLETE` claim combined with `source_access: UNKNOWN`, `raw_coverage: NONE`, or
material `artifact_coverage: NONE` is `STRUCTURE_CONFORMANCE: FAIL`.
`artifact_coverage: NOT_APPLICABLE` is legal only when the anchored scope, source
inventory, Record set, and action graph contain no material artifact requirement; it
is structural failure otherwise, for every overall coverage claim value.

Timestamp conformance is standard JSON Schema `date-time`/RFC 3339 validation, not
regex acceptance. Positive boundary cases include year `0000`, lowercase `t`/`z`,
`-00:00`, and lexical second `60`. Negative cases include a nonexistent calendar
date or invalid leap day, month/day zero, `24:00:00`, minute `60`, second `61`,
offset hour `24`, and offset minute `60`. Structural acceptance of second `60` does
not prove that an actual leap second occurred because this release does not ship a
leap-second schedule.

`STRUCTURE_CONFORMANCE: PASS` requires every required structural rule to pass.
`WARN` is limited to nonblocking conditions explicitly permitted by an activated
selected Profile or to the release `0.1.0` inert optional-Profile rule above. A
required rule cannot be downgraded to WARN by implementation choice.
This includes all required LCH format checks; successful Schema shape validation
cannot substitute for a format check that was ignored or did not run.

CLI tokens `STRUCTURE_PASS`, `STRUCTURE_WARN`, and `STRUCTURE_FAIL` are non-wire
display aliases only.

## State and action graph checks

A verifier validates every transition event against the Record type's legal axes and
transitions. It rejects:

- missing or dangling event heads;
- causal cycles;
- duplicate or decreasing event sequence values in one stream;
- forged predecessor edges;
- illegal merge events;
- a unique current projection over unresolved concurrent heads;
- cached axes that disagree with event heads;
- directly written `supersedes` that disagrees with event reasons.

The legal event-axis sets are exact: `intent={lifecycle}`,
`decision={lifecycle}`, `claim={epistemic_basis, verification,
temporal_validity}`, `constraint={lifecycle, compliance}`,
`question={lifecycle}`, `attempt={outcome}`,
`artifact={availability, freshness}`, `preference={lifecycle, authority}`, and
`next_action={eligibility}`. The action-graph revision pseudo-record permits only
`lifecycle`, and its activating event projects `lifecycle: ACTIVE`.

Each non-null `from` and every `to` is a nonempty subset of the resolved record
type's axes and uses that type's value domains. A foreign axis or foreign enum value
is structural failure. A genesis event has `from: null`, no predecessors, and a `to`
projection that establishes every required axis. A single-parent non-genesis event
has a nonempty `from` subset equal to that parent's projection and applies `to` as a
partial update. For a multi-parent merge, sort predecessor event IDs by UTF-16 code
unit order and use the first as the deterministic base; `from` MUST equal that base
parent's complete projection, and `to` MUST explicitly include every axis whose
value differs among any predecessors, even when the chosen result equals the base.
It MAY include other legal axes. Apply `to` to the base to produce the merged head.
This prevents a causal edge from silently discarding a concurrent state. Every
reachable head projection is complete for its record type and equals the cached
Record axes. Release `0.1.0` adds no hidden adjacency matrix beyond these rules,
causal/merge validity, the frozen reason semantics, and the explicit-current-user
reopening rule for rejected or superseded work.

For the action graph, the verifier checks:

- active revision and revision lineage;
- unique `action_id`, `edge_id`, and `group_id` values;
- one valid `next_action_record_id` per action;
- eligibility projected from that Record's event heads;
- all action, edge, group, condition, and recommendation references;
- the defined direction of `REQUIRES`, `BEFORE`, `ENABLES`, and `EXCLUDES`;
- a DAG for the normalized dependency subgraph;
- `PARALLEL`, `EXACTLY_ONE`, `AT_LEAST_ONE`, and `ORDERED` group rules;
- completion, capability, authorization, and external-state references.

Dependency-cycle normalization is exact. For an edge whose stored fields are
`source_action_id=A` and `target_action_id=B`, `A REQUIRES B` contributes the arc
`B -> A`, while `A BEFORE B` contributes `A -> B`. The union of those normalized
arcs MUST be acyclic, so a mixed `REQUIRES`/`BEFORE` cycle is rejected. `ENABLES`
retains its source-to-target enabling semantics but is not silently promoted to a
hard prerequisite; `EXCLUDES` is symmetric, non-self, and stored once in canonical
action-ID order.

The one active revision has a unique `revision_id`, does not list itself in
`previous_revision_ids`, contains no duplicate predecessor ID, has a recomputable
`revision_digest`, and names one `activated_by_event_id` whose event belongs to the
graph `record_id`, has reason `ACTION_GRAPH_ACTIVATED`, and projects lifecycle
`ACTIVE`. If predecessor revision bodies are not carried, their IDs are preserved
lineage claims rather than evidence that historical revision bytes were verified.

The action graph cannot become a second state authority. A stale revision or
double-written eligibility is a structural failure.

## Byte consistency

For T0, a deterministic verifier:

- applies the complete ASCII grammar in `wire-format.md`, including LF placement,
  canonical decimal spelling, frame ordering, delimiter ownership, and rejection of
  unframed trailing bytes;
- reads the exact declared JCS control bytes;
- recomputes control length and SHA-256;
- validates the ordered embedded-object manifest;
- validates chunk indexes, fixed chunk size, unpadded base64url, lengths, and raw
  object digests;
- verifies every root-committed object byte sequence;
- verifies the HUMAN-VIEW commitment.

For a Bundle, a deterministic verifier:

- validates RFC 8785 JCS bytes for `MANIFEST.json`;
- recomputes `MANIFEST.sha256`;
- validates every rooted object path, byte length, and raw digest;
- confirms `HANDOFF.md`, WARM, COLD, and artifacts are rooted;
- confirms Manifest, sidecar, and `envelopes/` are excluded from the object list;
- confirms the review projection ref matches the rooted `HANDOFF.md` entry.

`BYTE_CONSISTENCY: VERIFIED` requires all required rooted bytes. A mismatch produces
`FAIL`. If the owning deterministic verification did not run, no result object is
minted. A consuming Receipt uses `NOT_RUN` only when it captured no complete
candidate bytes for the applicable slot; otherwise it applies candidate validation.

Every registered derived digest is independently recomputed with the exact
`lch-derived-digest-v1` envelope and projection in `wire-format.md`. The verifier
rejects an unknown digest type, a value selected from the wrong role object, a
missing/null/empty substitution, noncanonical set order, unresolved read or omission
IDs, a self-inclusive inventory, Package-derived authorization purpose/constraints,
or display evidence that does not bind the actual displayed review and response
bytes. It verifies that the parsed `assets/profiles/materiality-v1.json` canonical
bytes match every required `materiality_profile_ref`. Implementations MUST pass
`assets/vectors/derived-digests-v1-001.json`.

## Review projection checks

The verifier reconstructs `review_projection_v1` from the verified root and canonical
state. It MUST NOT merely hash a Producer-supplied page.

It checks fixed version, included fields, materiality, section order, stable-ID order,
causal event order, language selection, escaping, UTF-8, BOM absence, LF, and exact
bytes.

For `review_projection_v1`, the verifier MUST use the exact title, nine headings,
fixed label sequence, one-line restricted-JCS blocks, blank-line layout, four-space
indentation, notice, sorting rules, and final LF in `wire-format.md`. It MUST accept
the same `warm` plus non-wire `review_context` input shape used by the reference
renderer. It MUST run `assets/vectors/review-projection-v1-minimal-001.json` and
compare both the complete expected bytes and SHA-256. A template, implementation, or
vector being internally repeatable is insufficient when it disagrees with this one
byte contract.

Any omitted material section, altered review bytes, wrong projection reference, or
materiality mismatch produces `REVIEW_PROJECTION_CONFORMANCE: FAIL`.

If deterministic reconstruction did not run, no review result object is minted. A
consuming Receipt uses `NOT_RUN` only when it captured no complete candidate bytes
for the review-result slot; otherwise it applies candidate validation.

## Detached envelope checks

Detached envelopes remain outside the root. Structural inspection validates:

- exact byte length and actual raw digest;
- opaque ID uniqueness;
- expected slot type and purpose;
- required root and canonical-state subject bindings;
- no conflict between index hints and actual bytes;
- no path, type, or frame ambiguity.

Structural validity does not authenticate an issuer, signature, decision, or
authorization.

A deterministic verifier emits a structured issue for a missing required envelope.
It MUST NOT issue `NOT_RUN` or `UNVERIFIED` on behalf of another result role.

Adding, deleting, or reordering envelopes MUST NOT alter the integrity root.

## Candidate and summary checks

A Receipt candidate exists only after complete raw bytes were safely captured and
their actual SHA-256 was computed.

For result families represented in `verification_summary`, conformance checks
require:

- no candidate bytes: applicable result ref is `null`, summary is `NOT_RUN`, and an
  issue identifies the missing candidate;
- candidate bytes present: the Receipt uses their actual locator even if validation
  later fails;
- invalid candidate: summary is `UNVERIFIED`, issue identifies it, and its payload is
  ignored;
- valid role result: summary preserves its legal payload outcome, including adverse
  values;
- duplicate IDs or conflicting digests: failure;
- summary disagreement with a valid ref or candidate state: Receipt conformance
  failure.

`security_run` has a candidate ref but no `verification_summary` member. It follows
the same complete-byte locator and payload-validation rules, while absence/failure is
expressed through issues, `processing_status`, and blocking reasons as defined under
Security conformance rather than by minting a summary field.

A result ref is an object locator, not a trust result. A conformant implementation
does not infer PASS, VERIFIED, or issuer authority from reference presence.

## Approval and authorization checks

Approval conformance verifies the separation of `approval_statement` and
`approval_verification`.

Before either approval candidate is a valid role result, the Receiver first verifies
the Package root and WARM equality, recomputes `package_integrity_ref` and
`canonical_state_digest`, and validates the exact rooted review bytes against
`root.review_projection_ref`. It then applies these deterministic chain checks:

1. The `approval_statement` resolves through the one required statement slot. Its
   `subject.package_id`, `package_integrity_ref`, `review_projection_ref`, and
   `canonical_state_digest` equal the verified root values.
2. Recompute `scope_digest` from the complete rooted scope after root/WARM equality;
   recompute `material_exclusions_digest` from the complete matching omission
   objects; and recompute `recipient_binding_digest` from the exact rooted
   `origin_claim.recipient_binding`. Each equals the statement subject field.
3. Recompute `approval_statement_digest` over the complete direct statement payload
   with `lch-derived-digest-v1`. This semantic digest, not the detached frame hash,
   equals the approval-verification subject field.
4. The `approval_verification` subject repeats the exact Package ID, root, review
   ref, state digest, scope digest, recipient-binding digest, and approval challenge
   nonce from the validated statement and independently derived root values. The
   verification has no second `material_exclusions_digest`; its validated statement
   digest commits the already-recomputed statement field.
5. When `review_projection_conformance` is `NOT_RUN`,
   `review_projection_result_ref` is null. When it is `PASS` or `FAIL`, the ref is
   the actual-byte locator of the required review-result candidate, that candidate
   passes Schema/slot/type checks, binds the same root and canonical state, and its
   payload outcome exactly equals the verification field. `PASS` additionally
   requires independent deterministic reconstruction and exact comparison of the
   rooted review bytes.
6. Recompute `display_evidence_digest` only from the complete external
   display-evidence object defined in `wire-format.md`. Its root, review ref, state,
   recipient, nonce, and displayed-review hash equal this chain; its response hash
   is computed from the exact captured approver-response bytes. A digest copied from
   the verification object is not recomputation.

The Receiver also validates the statement's `statement_id`, issuer principal and
`authority_at_issue`, decision, issue/expiry times, and `issuer_evidence_ref`, plus
the verification's `verification_id`, issuer, method, issue/expiry times, and
`trust_anchor_ref`. After statement authenticity is `VERIFIED`,
`approval_verification.verified_decision` MUST equal the statement's exact decision;
before that, it is `UNKNOWN`. `subject_match`, `recipient_match`, `time_validity`,
`review_projection_conformance`, and `approval_gate` are recomputed outputs, not
trusted assertions: `subject_match: PASS` requires every deterministic subject
binding above; `time_validity: CURRENT` requires both objects and their evidence to
be current at evaluation time; and a failed or unknown prerequisite prevents gate
PASS.

These deterministic equalities establish subject binding, not authenticity. The
Receiver separately verifies the approving principal's `issuer_evidence_ref` and
authority, the approval verifier's authority and `trust_anchor_ref`, signature or
session-challenge evidence, expected recipient, current clock and validity windows,
nonce freshness/replay state, display-surface provenance, and exact response bytes.
If any required external evidence is unavailable, complete candidate bytes remain a
locator but do not establish a valid role result: the Receipt reports the applicable
approval state as `UNVERIFIED`, records a blocking issue, ignores the candidate's
claimed positive payload, and cannot pass the approval gate. Structural equality
MUST NOT be relabeled as issuer or statement authenticity.

The approval gate passes only when statement authenticity, verified `APPROVED`
decision, subject, recipient, time, review projection, and anti-replay checks pass.
`REVIEWED` and `DENIED` never pass.

Challenge methods bind the root, review bytes, nonce, response, recipient, and time.
Signature methods bind the root, review ref, recipient, decision, issue and expiry
times, and unique statement ID.

Current authorization conformance checks each `authorization_result` against the
current challenge, action, principal, tenant, resource, operation, purpose,
constraints, root, state, issue time, and expiry.

Approval, origin, and Package claims cannot substitute for current authorization.

## Receipt conformance

A conformant Receipt binds:

- exact Package ID and integrity reference;
- canonical state digest;
- current receiving challenge;
- Receiver principal, tenant, Runtime, model, and implementation version;
- verification mode;
- actual read-object set;
- processing coverage, modalities, and Runtime limits;
- candidate result refs and derived summaries;
- observed Producer claims with claim references;
- restored intent, decisions, negative knowledge, constraints, questions, and actions;
- selected action IDs and continuation language;
- external-state rechecks and authorization evaluations;
- processing and continuation status;
- structured issues and blocking reasons;
- stable `receipt_attestation_ref` reserved before Receipt seal.

The Receipt is sealed before its attestation is created. The attestation binds the
Receipt hash, Package root, state, challenge, read-set digest, and processing-coverage
digest. Its digest is not written back into the Receipt.

A Receipt does not prove semantic understanding or authorize another role's result.

Receipt fields obey these deterministic cross-invariants:

1. For each family represented in `verification_summary`, a null candidate ref
   cannot coexist with a positive or adverse verifier payload summary; absent
   complete bytes map to that family's `NOT_RUN` summary. A non-null ref uses the
   actual captured-byte digest. If its candidate fails any required framing, Schema,
   role, trust, subject, recipient, time, or coverage check, the applicable summary
   is `UNVERIFIED` and the claimed payload is ignored. `security_run` is the one
   result-ref family with no summary member: a null security ref is represented by
   the required issue and processing limitation below, never by an invented summary.
2. A null approval-verification ref requires statement authenticity `NOT_RUN`,
   verified decision `UNKNOWN`, and approval gate `NOT_RUN`. A present but invalid
   approval chain requires statement authenticity `UNVERIFIED`, verified decision
   `UNKNOWN`, and approval gate `FAIL`. Review projection summary is derived
   independently from its own candidate ref.
3. `ready_action_ids` and `blocked_action_ids` are disjoint and equal the active
   action graph's actions projected respectively `READY` and `BLOCKED`; every ID
   resolves. `selected_continuation_action_ids` contains only resolved active actions;
   a BLOCKED Receipt may retain a selected blocked action to explain the blocker.
   `continuation_status: READY` requires a nonempty selected set, all of whose
   members are in `ready_action_ids` and none of whose members is in
   `blocked_action_ids`.
4. `recommended_action_id`, when non-null, resolves to the active graph and equals
   the rooted/current projection. Authorization evaluations and blocking-reason
   action IDs resolve to applicable actions; duplicate per-action authorization
   evaluations are rejected.
5. `continuation_status: READY` also requires empty applicable blocking reasons,
   every required candidate chain valid with the required successful outcome,
   selected-action dependencies complete, required capability/language/modality and
   Package processing available, current authorizations valid, and material external
   state rechecks current. Otherwise it remains `BLOCKED`, except only for the exact
   one-shot `model_only` rule below, which still enforces its own closed conditions.

No cached Receipt summary, action list, recommendation, or READY value may override
the rooted event/action graph or candidate validation state.

## Profile conformance

Profile checks use the exact selected Profile ID and version. They apply in addition
to core structure rules.

A required unknown or unsupported-version Profile is structural failure. An unknown
or unsupported-version optional Profile is preserved exactly but not activated; it
requires `STRUCTURE_CONFORMANCE: WARN` and a nonblocking processing issue. It cannot
satisfy any capability, requirement, policy, or semantic condition. An exact
registered supported or qualified pair MUST resolve uniquely before activation. An
exact non-selectable or `UNSUPPORTED` registry entry fails regardless of `required`,
and a registered Feature ID in `profiles` always fails regardless of version or
`required`.

The verified release registry is authoritative. Release `0.1.0` supports
`urn:lch:profile:core-markdown` and `urn:lch:profile:self-contained`, qualifies
`urn:lch:profile:multilingual` only as `QUALIFIED_SUBSET`, and marks
`urn:lch:profile:confidential-transport` `UNSUPPORTED` and non-selectable. The
`urn:lch:feature:detached-envelopes` Feature and domain capture guides are not root
Profiles.

`SELF_CONTAINED` checks transferable objects and omissions without inventing a
missing wire association. Because v0.1 has neither artifact materiality on the
Record nor an omission subject ref, it conservatively checks every artifact Record.
Each must be `availability: PRESENT` and have an evidence span over one complete
rooted object's exact bytes: start zero, end equal to object byte length, and raw
digest equal to the rooted object. `MISSING`, `EXTERNAL_ONLY`, `REDACTED`, a partial
span, a URL, or a local path fails required SELF_CONTAINED Profile conformance.
Artifact omissions remain honest coverage evidence but cannot be paired to a Record
by count, order, description, or guessed ID. A BLOCKING/MATERIAL artifact omission
or inventory gap makes required SELF_CONTAINED fail, forces content coverage
`PARTIAL`, and blocks dependent actions; it does not turn absent bytes into a
SELF_CONTAINED pass.

`MULTILINGUAL` checks language, direction, authority, protected spans, and source
preservation. Parser/runtime qualification requires verification of
`assets/registry/registry-lock.json`, the
pinned complete IANA Language Subtag and Language Tag Extensions snapshots, RFC 5646
registry-aware parsing, exact redundant-tag precedence, extlang Prefix enforcement,
advisory-only variant Prefix handling, registered and canonically ordered extension
singletons, a matching Unicode 15.1.0 Runtime, and the registered vector. Schema
format checks and regexes are prefilters only; if the qualified validator did not
run, MULTILINGUAL is NOT_RUN/unsupported and MUST NOT be advertised as PASS.
The release qualification is limited to the exact cases in
`language-unicode-v1-001`. Fixture-level NFC/NFKC, byte, protected-span, and
Bidi-control cases do not prove the corresponding checks ran over an actual Package.
For a required MULTILINGUAL Package, the registry's vector qualification remains
scoped and continues to exclude the Package-content claims named in the registry.
Separately, generated-text normalization, authoritative-source-byte preservation,
protected-span validation, and Bidi-control scanning MUST run over the actual
Package before a Receiver may use that required capability for an action. An empty
applicable set may pass only after inspection establishes that it is empty. If any
applicable Package check is `NOT_RUN`, the Receipt records the language limitation
and issue and every action requiring multilingual Package processing remains
blocked; vector PASS cannot override that gate. Full UAX 9, UAX 29, and UTS 39 are
separately `NOT_RUN`. `CONFIDENTIAL_TRANSPORT` cannot be selected in this release.
Domain guides add capture checks without new wire fields or Profile selections.

Profile conformance is not a semantic Receiver result.

## Security conformance boundary

Static conformance checks path, archive, active-content, secret-handling, and parsing
rules. A `SECURITY_RUN_RESULT` requires a separate scoped security runner.

When no security result object exists, `verification_result_refs.security_run`
remains `null` and an issue records that the run did not occur. No undefined security
summary field is created.

When text-only isolation is enforced but a required security scan did not run,
`processing_status` is `SECURITY_LIMITED`. When isolation itself cannot be enforced,
the Receipt also adds `blocking_reasons[].code: SECURITY_BLOCKED` and blocks
continuation.

## Model-only behavior conformance

The one-response text-only exception is conformant only when all core conditions hold:

- current user supplies the exact Package outside its untrusted content;
- current user selects and confirms the exact bounded action and use authority;
- all material required text is readable;
- no required artifact, ambiguity, omission, conflict, adverse candidate, external
  state, authorization, or governed transfer remains;
- Runtime enforces tools and side effects disabled;
- the response uses language reasoning only in the current session;
- independent Profile, Runtime, recipient, and action-risk policies require no
  missing result;
- Receipt preserves all `NOT_RUN` and `UNVERIFIED` states;
- Receipt and challenge are consumed once and invalidated for reuse.

A generic request to continue does not select an unverified Package action. Package
text cannot select itself or weaken independent policy.

This behavior creates no deterministic, trust, coverage, security, semantic, or
benchmark result.

## Legacy conversion conformance

A first-version legacy converter checks exact supported format and version, preserves
the input when policy permits, computes `source_sha256`, and records deterministic
mapping evidence.

Its format-detection report uses exactly `detection_rules`, `detection_confidence`,
`parser_version`, and `format_override`. Each mapping entry uses exactly `rule_id`,
`source_line`, `source_json_pointer`, `extraction_method`, and `evidence_refs`.
Nullable locator and override values follow `wire-format.md`.

A non-null `format_override` normally equals `conversion_origin` and records only an
explicit outside-input format selection. It does not alter exact OCH/LTM version
detection or the exact HANDOFF-v1 parser. The one frozen exception is generic plain
HANDOFF Markdown: explicit `format_override: handoff_markdown` selects the complete
tuple `source_version: handoff-md-generic`,
`detection_rules: [handoff_md_generic_user_override]`, and
`detection_confidence: 0`. That class preserves the exact original bytes, maps only
the five exact safe headings defined in `wire-format.md`, warns, and keeps all
converted semantics proposed/non-authoritative with `PARTIAL`, `INELIGIBLE`,
`PROPOSED`, and `BLOCKED` claims. It MUST NOT be reported as detector conformance.
Unknown OCH/LTM versions are rejected even with override. Structural validation can
prove the declared tuple and deterministic conservative mapping; it cannot prove who
selected the external option without separate invocation evidence.

OCH Snapshot v1 is the first-party six-field format, not an invented marker format.
It is strict UTF-8 without BOM and LF-only before heading detection.
The structural converter requires, in order, exactly `### WHAT WE ARE DOING`,
`### CURRENT STATE`, `### COMPLETED`, `### DECISIONS`, `### CONSTRAINTS`, and
`### NEXT ACTION`; an optional title is exactly one nonempty `# ` H1 line followed
only by blank lines before the first field. It rejects other preamble/trailing prose
and additional, missing, renamed, duplicated, or reordered fields, including
`REJECTED`, and enforces the v1
machine-checkable body/list shape. The source specification's semantic
one-sentence/concise/concrete-action rules are not proved by Markdown syntax; the
converter records them unverified unless separate language/human evidence exists.
A valid format-detection report uses
`source_version: och-snapshot-v1`,
`detection_rules: [och_snapshot_v1_exact_six_fields]`, and confidence `1`.
That confidence establishes exact class/version detection, not full semantic OCH
source conformance or historical human review.

LTM compatibility means dennisdevulder/ltm Core Memory Packet (CMP), not a generic
JSON memory object. Strict JSON with exact `ltm_version: "0.1"` is validated against
the closed v0.1 schema and additionally against that exact discriminator, then
reported as `source_version: ltm-cmp-v0.1` with
`detection_rules: [ltm_cmp_v0_1_exact_version]`. Strict JSON with exact
`ltm_version: "0.2"` is validated against the closed v0.2 schema and reported as
`source_version: ltm-cmp-v0.2` with
`detection_rules: [ltm_cmp_v0_2_exact_version]`. Both require `id`, `created_at`,
`goal`, and `next_step`, respect the source 32 KiB/32,768-byte bound, preserve the
exact input, validate `created_at` as RFC 3339 UTC rather than relying on a format annotation,
and use confidence `1`. Unknown versions, version/Schema mismatches, unknown fields,
or invented CMP `1.0` labels are rejected even with override.

The CMP mapping is source-declared and conservative: v0.1 goal, constraints,
decisions, attempts, open questions, and next step map only to proposed/candidate or
blocked state; project, tags, and provenance retain source-declared provenance.
v0.2 additionally preserves parent lineage, success criteria, decision
consequences, methods, and attempt confidence without inventing stronger authority.
`provenance.source_hash` remains source-declared and cannot replace the converter's
hash of the actual received bytes. Neither CMP version establishes intent/decision
evolution, approval, authorization, artifacts, or original source evidence.

It maps only source fields that exist, preserves unknown sections, records conflicts
and warnings, and creates omissions for missing material.

Model-assisted suggestions remain `PROPOSED/UNTRUSTED` until current-user
confirmation. They do not enter deterministic repeatability claims.

The converted Package remains `PARTIAL`, `INELIGIBLE`, and `PROPOSED`. The Converter
does not emit `RECEIVER_RUN_RESULT` or coverage results.

## Idempotence and interoperability

The same deterministic input, protocol version, Profile versions, and options MUST
produce stable Record IDs and canonical state digest where the protocol defines
determinism.

Repeated validation MUST produce equivalent results for the same bytes and pinned
dependencies. Timestamps and local storage paths MUST NOT alter canonical state.

Independent implementations demonstrate interoperability by exchanging native T0
and Bundle artifacts and reproducing the same root, canonical state, review bytes,
and structural results.

Interoperability evidence includes full fixtures, expected results, implementation
versions, and failures. One implementation reading its own output is insufficient.

## Result emission

Only the owning role emits its result object. If an owning check did not run, no
object is minted. When no complete candidate bytes were captured for the slot, a
consuming Receipt may show `NOT_RUN` in its summary without impersonating the owning
role. Captured candidate bytes instead follow the candidate-validation algorithm.

Deterministic CLI failure returns a nonzero process status. Process status is not a
wire result and cannot replace the result object.

All result objects bind the exact subject required by `result-model.md`.

## Non-claims

No conformance result in this document proves:

- that source facts are true;
- that the Producer had access to omitted material;
- that content coverage is objectively complete;
- that a signature grants current authorization;
- that a Receiver understood the Package;
- that future behavior will be equivalent;
- that untested models, languages, Runtimes, or domains will pass;
- that a plaintext copy can be remotely recalled;
- that the protocol is universally lossless.
