# Wire Format

> Scope: normative LCH 0.1 audit wire format only. It remains supported for
> advanced audit and older packages, but it is not the default product export.
> See `simple-workflow.md` for the three human-first formats.

This document is the normative release `0.1.0` definition of the native handoff wire
format. The bundled Schema catalog MUST enforce the same contract and MUST NOT create
a parallel format.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative as defined by
RFC 2119 and RFC 8174.

## Contents

- [Format families](#format-families)
- [Common package invariants](#common-package-invariants)
- [Release registries and offline Schema catalog](#release-registries-and-offline-schema-catalog)
- [Package metadata](#package-metadata)
- [HOT, WARM, and COLD](#hot-warm-and-cold)
- [Canonical state](#canonical-state)
- [Derived digest registry](#derived-digest-registry)
- [Review projection](#review-projection)
- [T0 text transport](#t0-text-transport)
- [Bundle transport](#bundle-transport)
- [Detached envelopes](#detached-envelopes)
- [Candidate references](#candidate-references)
- [Receipt transport](#receipt-transport)
- [Legacy conversion metadata](#legacy-conversion-metadata)
- [Timestamp syntax and calendar validity](#timestamp-syntax-and-calendar-validity)
- [Text, language, and paths](#text-language-and-paths)
- [Self-contained packages](#self-contained-packages)
- [Limits and failure behavior](#limits-and-failure-behavior)

## Format families

The protocol has two native transport families:

1. T0 is one self-describing text artifact with an exact-length JCS control object,
   embedded objects, a deterministic human review projection, and optional detached
   frames.
2. A Bundle is a directory or archive containing `HANDOFF.md`, canonical
   `MANIFEST.json`, `MANIFEST.sha256`, WARM state, COLD objects, artifacts, and an
   excluded `envelopes/` area.

T1 carries the same native Bundle as one intact attachment. T2 exposes the Bundle as
a filesystem directory or ZIP. T3 adds deterministic tools. These capability modes
MUST NOT alter semantic fields or result meaning.

A native Receiver MUST identify the transport before interpreting natural-language
content. A plain `HANDOFF.md`, OCH Snapshot, or LTM CMP is not native and MUST be
routed to `CONVERT_LEGACY`.

## Common package invariants

Every native Package MUST satisfy these invariants:

- exactly one integrity root;
- exactly one `package_integrity_ref` with `kind`, `sha256`, and `byte_length`;
- one canonical WARM state and one `canonical_state_digest`;
- HOT derived only from WARM;
- WARM assertions traceable to COLD evidence or explicit omissions;
- one active action-graph revision derived from transition events;
- declared source, scope, policy, and external-state boundaries;
- explicit Profile versions and `must_understand` values;
- a deterministic `review_projection_ref` committed by the root;
- post-seal statements and results outside the root;
- no absolute path as the only locator for a material object.

The integrity root MUST NOT contain a digest of itself. It MUST NOT be rewritten after
seal. Any change to a rooted object creates a new root.

The root and WARM intentionally repeat a small set of semantic projections for routing
and startup. They MUST NOT become two truths. A structural verifier MUST require exact
JSON-value equality for every pair below:

```text
root.source_boundary                 == warm.boundaries.source_boundary
root.scope                           == warm.boundaries.scope
root.policy_boundary                 == warm.boundaries.policy_boundary
root.external_state_dependencies     == warm.boundaries.external_state_dependencies
root.language_profile                == warm.language_profile
root.materiality_profile_ref         == warm.materiality_profile_ref
root.content_coverage                == warm.content_coverage
root.consistency_claim               == warm.consistency_claim
root.semantic_actionability_claim    == warm.semantic_actionability_claim
root.content_coverage.scope          == warm.boundaries.scope
```

The root `scope.approval_statement_slot`, `approval_claim.approval_statement_slot`,
and exactly one required `detached_envelope_slots` entry whose `expected_type` is
`approval_statement` MUST name the same `opaque_id`. Every
`content_coverage.coverage_envelope_slot_ids` item MUST resolve to one declared slot.
Slot IDs and `(opaque_id, expected_type)` pairs are unique. Any mismatch is
`STRUCTURE_CONFORMANCE: FAIL`; an implementation MUST NOT choose one copy as newer.
Every omission has a unique `omission_id`. Every `scope.material_exclusion_ids`
member resolves exactly once to `content_coverage.omissions[].omission_id`; every
BLOCKING or MATERIAL policy exclusion is listed in that set. Failure in either
direction is structural failure.

## Release registries and offline Schema catalog

Release `0.1.0` freezes Profile and Feature semantics in
`assets/registry/profile-feature-registry-v0.1.json`. The exact selectable Profile
URIs are:

```text
urn:lch:profile:core-markdown             0.1.0  SUPPORTED
urn:lch:profile:self-contained            0.1.0  SUPPORTED
urn:lch:profile:multilingual              0.1.0  QUALIFIED_SUBSET
urn:lch:profile:confidential-transport    0.1.0  UNSUPPORTED, not selectable
```

`urn:lch:feature:detached-envelopes` version `0.1.0` is a supported Feature, not a
root Profile. The seven `domain-*.md` documents are capture guidance only and have
no registered wire Profile in this release. A root `profiles` array MUST contain
unique Profile IDs. A repeated ID, a repeated ID with another version, an entry whose
registered `selectable` value is false, or a Feature/domain guide selected as a
Profile is `STRUCTURE_CONFORMANCE: FAIL`.

`assets/protocol-version.json` locks the exact stored and restricted-JCS canonical
byte lengths and SHA-256 digests of the Profile/Feature registry. A verifier MUST
validate those commitments before resolving a selected Profile. A registry with the
same IDs but different requirements, status, version, or qualification is not the
release registry.

Every release Schema has an absolute opaque `$id` of the form
`urn:lch:schema:0.1:<name>`. Every cross-Schema `$ref` uses one of those URNs; local
fragments continue to use `#`. `assets/registry/schema-catalog-v0.1.json` maps every
release `$id` to one local `assets/schemas/*.schema.json` path and locks each file's
raw length and SHA-256. `assets/protocol-version.json` locks the catalog's exact
stored and restricted-JCS canonical bytes.

Before Schema validation, VERIFY MUST load the bundled catalog, verify both catalog
commitments, verify every cataloged Schema's raw length/hash and `$id`, reject
duplicate IDs or paths, and pre-register all mappings in the validator's local
resource store. The JSON Schema 2020-12 dialect is supplied as a built-in resource.
Network or other remote Schema retrieval is `FORBIDDEN`; a missing, unlisted,
hash-mismatched, or remotely resolved Schema is structural failure. The `$schema`
dialect URI is an identifier and never authorization to fetch it.

The release Schemas use the default JSON Schema 2020-12 dialect, in which `format`
is an annotation unless a separate assertion vocabulary is selected. They do not
select that vocabulary. Schema success therefore proves shape and asserted Schema
keywords, not LCH format conformance. Independently of a library's `format`
configuration, an LCH structure verifier MUST run all three deterministic checks:

1. every value annotated `uri` is an absolute ASCII URI conforming to RFC 3986,
   including a valid scheme, only grammar-permitted ASCII characters, and every
   percent sign followed by exactly two hexadecimal digits; raw non-ASCII, spaces,
   controls, malformed percent encoding, relative references, and URI parser
   recovery are rejected, and the verifier neither decodes nor normalizes the URI;
2. every value annotated `date-time` satisfies the RFC 3339 rules in
   [Timestamp syntax and calendar validity](#timestamp-syntax-and-calendar-validity);
3. every value annotated `bcp47` satisfies the release-pinned RFC 5646 qualification
   in [Text, language, and paths](#text-language-and-paths).

A generic JSON Schema validator that treats `format` only as annotation MAY provide
shape-validation evidence, but that evidence alone cannot support
`STRUCTURE_CONFORMANCE: PASS` or `WARN`. No custom LCH dialect or meta-Schema is
introduced in release `0.1.0`; these deterministic checks are protocol conformance
steps outside Schema evaluation.

`assets/vectors/index.json` is the release's hash-bound vector catalog. Each entry
binds one vector ID and local path to exact raw length/hash and restricted-JCS
canonical length/hash. `assets/protocol-version.json` binds the catalog's own raw and
canonical bytes. Release `0.1.0` requires exactly the four cataloged vector JSON
files—JCS, review projection, derived digests, and language/Unicode—and forbids an
extra uncataloged vector from contributing to Profile qualification. VERIFY checks
catalog closure before treating any vector result as release evidence.

## Package metadata

The root metadata uses the existing protocol fields:

- `protocol_id` and `protocol_version`;
- `package_id` and `created_at`;
- `producer`;
- `profiles` and `must_understand`;
- `source_boundary`, `scope`, `policy_boundary`, and
  `external_state_dependencies`;
- `resource_requirements` and `language_profile`;
- `materiality_profile_ref`;
- `content_coverage`, `consistency_claim`, and
  `semantic_actionability_claim`;
- `approval_claim` and `origin_claim`;
- `detached_envelope_slots` and `review_projection_ref`;
- `integrity`, `canonical_state_digest`, and `objects`.

Package metadata contains Producer claims. It MUST NOT contain verified result
payloads, a Receipt, current authorization, or a continuity PASS.

`approval_claim` remains `PROPOSED` in the root. It contains the stable
`approval_statement_slot` and the rooted review subject. It is never rewritten to
`APPROVED`.

## HOT, WARM, and COLD

### HOT

HOT is a startup projection, not a second truth source. It MUST include the current
intent, phase, active decisions, rejected or superseded directions, constraints,
blocking issues, ready or alternative actions, optional recommendation, coverage,
omissions, and continuation language needed for startup.

HOT/CONTROL carries fixed IDs, enums, coverage states, `ready_action_ids`, and
`recommended_action_id`. HOT/VIEW is a continuation-language derived view.
HOT/SOURCE preserves authoritative source text.

Every material HOT statement MUST resolve to WARM and, where evidence is required,
to COLD. A HOT fact absent from WARM is a structural failure.

### WARM

WARM contains the canonical Records and transition events. It preserves intent and
decision evolution, claims, constraints, questions, attempts, artifacts, preferences,
omissions, conflicts, and the action graph.

The WARM top level uses exactly these collection keys and MUST NOT use synonymous
alternatives:

```text
protocol_version
state_projection_version
boundaries
source_inventory
records
transition_events
action_graph
current_projection
content_coverage
consistency_claim
semantic_actionability_claim
language_profile
materiality_profile_ref
```

`boundaries` contains exactly the four protocol boundary members
`source_boundary`, `scope`, `policy_boundary`, and `external_state_dependencies`.
The last member is the wire representation of the conceptual external-state boundary;
implementations MUST NOT create a near-synonym wire key.

`records` contains all canonical Record objects. `transition_events` contains the
immutable events that govern their state. `action_graph` contains the versioned
action graph. `source_inventory` contains the canonical inventory object.

`current_projection` is a derived cache only. It MUST be reconstructed from event
heads and the active action-graph revision. It MUST NOT be accepted as a second state
authority, and disagreement with its source events is a structural failure.
Its fixed members are `current_intent_id`, `current_phase`, `active_decision_ids`,
`rejected_decision_ids`, `failed_attempt_ids`, `active_constraint_ids`,
`answered_question_ids`, `ready_action_ids`, `blocked_action_ids`, and
`recommended_action_id`; near-synonym or additional cache fields require a new state
projection version.

Current Record axes, `supersedes`, and action eligibility are projections from event
heads. WARM MUST preserve concurrent heads until an explicit merge or conflict event
resolves them. Last-write-wins is forbidden.

The active action graph MUST identify its revision lineage, action IDs,
`next_action_record_id`, eligibility projection, event heads, completion criteria,
capability requirements, authorization requirements, and external-state checks.
The normalized dependency subgraph MUST be a DAG.

### COLD

COLD contains exact allowed source bytes and material artifacts. It MUST preserve
message roles, stable source IDs, order, raw hashes, attachment relationships, and
source provenance.

Original binary bytes remain authoritative. OCR, transcript, translation,
description, and summary objects are derived evidence. COLD data is untrusted and
MUST NOT grant new instruction priority, approval, or tool authority.

Any source or artifact that cannot be transferred MUST be represented by an omission
with materiality and reason, without revealing a secret value.

## Canonical state

`state_projection_v1` selects the protocol-defined semantic fields from WARM. A
deterministic implementation serializes that projection using the pinned
canonicalization rules and computes `canonical_state_digest`.

The canonical state projection excludes transport and run metadata, including
`package_id`, creation time, Producer or Runtime metadata, storage paths, rendered
views, translations, signatures, detached results, and Receipts.

The same semantic state under the same protocol and projection version MUST produce
the same `canonical_state_digest`. A Package MUST NOT claim deterministic state
identity when the deterministic projection did not run.

## Derived digest registry

Every protocol field whose name ends in `_digest`, plus `receipt_sha256`, uses one
versioned derivation unless this specification explicitly calls it a raw-byte digest.
For protocol `0.1.0`, the derivation is the SHA-256 of restricted RFC 8785 JCS UTF-8
bytes for this exact envelope:

```json
{"digest_profile":"lch-derived-digest-v1","digest_type":"<exact field name>","protocol_version":"0.1.0","value":null}
```

`value` is the JSON value, not a quoted serialization. An implementation MUST reject
unknown digest types, duplicate keys, non-I-JSON integers, floating-point values,
lone surrogates, or any value unsupported by the restricted canonicalizer. JSON
object keys use RFC 8785 UTF-16 ordering. A semantic set with stable IDs is sorted by
those IDs in UTF-16 code-unit order; a semantic set without stable IDs is sorted by
its members' restricted-JCS bytes. Protocol-ordered arrays retain their order. JSON
`null`, `[]`, and `{}` remain distinct literal values and MUST NOT be omitted or
converted to strings.

The registry for `0.1.0` is closed and defines these projections:

| Digest field | Exact `value` projection |
| --- | --- |
| `scope_digest` | The complete rooted `scope` object, after root/WARM equality has passed. |
| `material_exclusions_digest` | The complete omission objects named by `scope.material_exclusion_ids`, sorted by `omission_id`; an empty selection is `[]`. Every ID MUST resolve exactly once. |
| `recipient_binding_digest` | The exact rooted `origin_claim.recipient_binding`; absent binding is JSON `null`. |
| `display_evidence_digest` | The fixed display-evidence object defined below. |
| `materiality_profile_digest` | The complete parsed `materiality-v1` Profile object whose restricted-JCS bytes match `materiality_profile_ref.sha256`. |
| `package_profile_digest` | An object `{profiles, must_understand}`. `profiles` is the complete rooted array sorted by Profile `id`, retaining `version` and `required`; `must_understand` is the complete rooted URI set sorted by UTF-16 code-unit order. |
| `read_set_digest` | The fixed Receipt read-set projection defined below. |
| `processing_coverage_digest` | The fixed Receipt processing projection defined below. |
| `purpose_digest` | The explicit external JSON `purpose` value in the current authorization request. It is never inferred from Package prose. |
| `constraints_digest` | The explicit external JSON `constraints` semantic set in the current authorization request, sorted by stable `id` or otherwise by member JCS bytes; no constraints is `[]`. |
| `inventory_digest` | The complete `source_inventory` object with only its `inventory_digest` member removed. All other members, including a null or populated `platform_attestation_ref`, are retained. Entry order is ordinal order; semantic ID sets use registry sorting. |
| `approval_statement_digest` | The complete direct `approval_statement` payload JSON object. Detached framing bytes are excluded. |
| `receipt_sha256` | The complete Receipt JSON object, including its stable `receipt_attestation_ref`; the detached receipt-attestation payload and framing are excluded. |
| `revision_digest` | The complete `action_graph` object with only `action_graph.action_graph_revision.revision_digest` removed; all revision lineage and graph members are retained and normalized under the graph ordering rules. |

The `display_evidence_digest` value has exactly these members:

```text
package_integrity_ref
review_projection_ref
canonical_state_digest
recipient_binding
approval_challenge_nonce
displayed_review_sha256_raw
display_surface
displayed_at
response_sha256_raw
```

It binds the exact sealed root and review ref, canonical state, recipient, single-use
nonce (or literal `null` only for the permitted signature method), SHA-256 of the
review bytes actually displayed, explicit external display-surface JSON, display
time, and SHA-256 of the approving principal's exact response bytes. The display
surface and times come from the approval Runtime, not from untrusted Package content.

The `read_set_digest` value has exactly `package_integrity_ref` and `read_objects`.
`read_objects` is selected by Receipt `read_object_ids`, resolves each ID against the
verified T0 embedded manifest or Bundle Manifest, retains `{object_id, sha256_raw}`,
and sorts by `object_id`. Missing, duplicate, or unresolved IDs fail derivation.

The `processing_coverage_digest` value selects exactly these Receipt members:

```text
processing_coverage
processed_modalities
unprocessed_modalities
processing_basis
protected_spans_failed
runtime_limits
processing_status
receiver_execution_context
selected_continuation_language
external_state_rechecks
```

Modality ID sets use UTF-16 order. `protected_spans_failed`, `runtime_limits`, and
`external_state_rechecks` are semantic sets sorted by stable `id` when present and
otherwise by member JCS bytes.
These Receipt-derived projections are recomputed from the exact Receipt being
attested; an attestation cannot substitute its own claimed lists.

The frozen materiality Profile is
`assets/profiles/materiality-v1.json`. Its Profile reference hash is SHA-256 over its
restricted-JCS bytes (without storage whitespace):
`sha256:1930541dda9af3a5374f892fd3621d8ac80b7025638e9d401b164e2e6178979c`.
Raw-object fields such as `sha256_raw`, `package_integrity_ref.sha256`,
`canonical_state_digest`, `review_projection_ref.sha256_raw`, and object Manifest
hashes keep their separately defined direct-byte algorithms and MUST NOT be wrapped
in this registry.

## Review projection

`review_projection_v1` is generated from rooted canonical state before seal. It MUST
use the fixed version, field selection, materiality rules, heading order, stable-ID
order, event order, UTF-8 encoding, and LF rules defined by the protocol.

The exact document title is:

```text
# Context Handoff Review Projection
```

The exact nine section headings, in order, are:

```text
## 1. Protocol and rooted state
## 2. Boundaries, requests, exclusions, and recipient
## 3. Current intent and phase
## 4. Active decisions and conflicts
## 5. Negative knowledge and questions
## 6. Constraints, sensitivity, freshness, and rechecks
## 7. Action graph
## 8. Coverage, inventory, omissions, modalities, and conflicts
## 9. Approval slot and detached-envelope policy
```

Every dynamic value is rendered as one restricted RFC 8785 JCS value in this exact
Markdown block form, where `<label>` is one of the fixed labels below and `<jcs>` is
one physical line:

```text
- <label> (JCS):

    <jcs>
```

There is one empty line between blocks and between sections. Dynamic text is never
interpolated into a Markdown heading, list label, code fence, or inline-code span.
This prevents Package content from changing review structure.

The fixed label sequence is:

1. `Protocol`, `Profiles`, `Package ID`, `Integrity kind`, `Integrity algorithm`,
   `Canonical state digest`, `Materiality profile`;
2. `Boundaries`, `Original user request refs`, `Material exclusion IDs`,
   `Recipient and sharing scope`;
3. `Current intent`, `Intent evolution events`, `Current phase`;
4. `Active decisions`, `Decision evolution events`, `Consistency claim`,
   `Conflict records`;
5. `Rejected, superseded, failed, or prohibited records`,
   `Answered and open questions`;
6. `Active constraints`, `Policy and sensitivity boundary`,
   `Freshness and recheck records`, `External state dependencies`;
7. `Complete active action graph`;
8. `Content coverage claim`, `Source inventory`, `Omissions`,
   `Artifact and modality records`, `Consistency and conflicts`;
9. `Approval statement slot`, `Detached-envelope policy`, followed by this exact
   notice as ordinary Markdown text:

```text
This is the pending-approval review projection for the exact root. Display the final `package_integrity_ref` separately after sealing and bind it with these review bytes in approval display evidence.
```

The renderer input is exactly two objects: canonical WARM input and a non-wire
`review_context`. The latter has required members `package_id`, `profiles`,
`integrity_kind`, `recipient_and_sharing_scope`, and `detached_envelope_policy`;
optional members are `protocol_id`, `integrity_algorithm`, and
`canonical_state_digest`. Defaults are `lossless-context-handoff` and `sha-256`.
If a context state digest is present, it MUST equal the digest recomputed from WARM.
The not-yet-computed Package root digest MUST NOT be an input or appear in the review
bytes.

Profiles and detached-envelope slots are sorted by their stable `id` and `opaque_id`
respectively using UTF-16 code-unit order. User-request and material-exclusion IDs,
Records, and action-graph actions, edges, and groups use the corresponding stable-ID
order. Transition events use causal topological order with UTF-16 event-ID order as
the tie breaker. Arrays whose protocol semantics are ordered retain that order.

Output is UTF-8 without BOM, uses LF only, and ends in exactly one LF. The title,
headings, labels, blank lines, four-space JCS indentation, notice, and final LF are
part of the committed bytes. The canonical golden vector is
`assets/vectors/review-projection-v1-minimal-001.json`; a renderer that produces a
different byte stream does not implement `review_projection_v1`.

The projection includes all material boundaries, original user request anchors,
intent and decision evolution, constraints, negative knowledge, omissions, conflicts,
artifacts, recipient and sharing scope, external dependencies, and the complete active
action graph projection.

T0 commits the exact HUMAN-VIEW length and raw digest in its control object. A Bundle
commits the `HANDOFF.md` object through its Manifest entry. A verifier reconstructs
the projection and compares exact bytes.

If the projection definition is unavailable or a required material field is absent,
`REVIEW_PROJECTION_CONFORMANCE` cannot pass and the approval gate cannot pass.

## T0 text transport

T0 is the following byte grammar. Literal spaces are one ASCII `SP`; every shown
line ending is one byte `LF` (`0x0A`); `CR`, BOM, leading or trailing spaces, and
unframed bytes are forbidden.

```text
LCH-T0 <major>.<minor> LF
control-byte-length: <control-length> LF
control-sha256: <64-lowercase-hex> LF
<exact control-length restricted-JCS UTF-8 bytes> LF
*embedded-frame
LCH-T0-HUMAN-VIEW LF
<exact review_projection_ref.byte_length bytes>
*detached-frame

embedded-frame =
  LCH-T0-EMBEDDED <ordinal> <object-id> <index>/<count> <chunk-char-length> LF
  <exact chunk-char-length base64url ASCII characters> LF

detached-frame =
  LCH-T0-DETACHED <opaque-id> <expected-type> <payload-byte-length> sha256:<64-lowercase-hex> LF
  <exact payload-byte-length bytes> [LF only when another detached-frame follows]
```

Decimal numbers use ASCII digits with no leading zero, except the value zero itself.
`major.minor` MUST equal the first two numeric components of the control object's
`protocol_version`. Object, slot, and type tokens use the stable-ID ASCII grammar.
The control delimiter LF is outside both `control-byte-length` and `control-sha256`.
The review bytes already end in exactly one LF under `review_projection_v1`; no
additional delimiter is inserted before the first detached header. A canonical
emitter always writes the `sha256:` prefix in detached headers. A compatibility
parser MAY accept a bare 64-hex detached hash but MUST canonicalize its reported
locator and MUST NOT emit that legacy spelling.

The T0 control object uses `embedded_objects` for its canonical ordered embedded-object
manifest. Every item uses exactly these keys and MUST NOT introduce near-synonym keys:

```text
object_id
ordinal
media_type
encoding
encoded_byte_length
decoded_byte_length
chunk_size
chunk_count
sha256_raw
```

`ordinal` fixes object order. `media_type` identifies the original object's media
type. `encoding` identifies the required unpadded RFC 4648 Section 5 base64url form.
`decoded_byte_length` and `sha256_raw` apply to the original object bytes.

Binary objects use unpadded RFC 4648 Section 5 base64url. Encoded data uses fixed
4096-character chunks with explicit indexes. `chunk_size` is 4096.
`encoded_byte_length` counts only base64url ASCII characters; it excludes frame
headers and LF bytes. `chunk_count` is
`ceil(encoded_byte_length / 4096)`, with zero for an empty object. Every chunk except
the final chunk is exactly 4096 characters. The final chunk contains the remaining
characters and MUST NOT use padding. Padding, implicit chunk order, or
implementation-selected wrapping is invalid.

Embedded-object records occur in contiguous `ordinal` order starting at one. Their
frames occur in ascending chunk-index order. An empty object has zero chunks and no
embedded frame; its decoded length and raw digest are still checked from the
manifest. The HUMAN-VIEW marker occurs only after all manifest entries have been
accounted for. Its exact bytes, length, final LF, and raw digest MUST match
`review_projection_ref`.

Optional post-seal envelopes use the length-prefixed detached grammar above.

The frame header is routing and parsing data only. It does not authenticate the
envelope issuer or payload.

The T0 integrity root is the exact JCS control bytes, not the whole text artifact.
`package_integrity_ref.kind` is `t0_control`. Its digest and byte length MUST match
the bytes declared by the T0 header.

Without a deterministic preprocessor, a Receiver MUST NOT mint structure, byte,
review, or security result objects. It uses the Receipt degradation rules and keeps
tools and side effects disabled.

In `assets/templates/t0-package.template.md`, each `__LCH_...__` sentinel denotes an
entire exact byte span. It is not a line-oriented textual substitution. Replacing a
sentinel MUST NOT retain the template's display LF unless that LF is part of the
grammar above. `bundle-HANDOFF.template.md` likewise denotes the complete review
bytes and introduces no wrapper, fence, heading, or extra newline.

## Bundle transport

A Bundle contains at least:

```text
HANDOFF.md
MANIFEST.json
MANIFEST.sha256
state/warm.json
```

It also contains required COLD objects and artifacts. Post-seal envelopes are stored
under `envelopes/`.

`MANIFEST.json` is the only Bundle integrity root. It is RFC 8785 JCS UTF-8 with no
BOM and no final LF. `MANIFEST.sha256` is exactly 64 lowercase hexadecimal characters
followed by one LF.

The Manifest object list includes `HANDOFF.md`, WARM, COLD, and material artifacts.
It excludes `MANIFEST.json`, `MANIFEST.sha256`, and all of `envelopes/`. This avoids a
self-hash cycle and keeps seal-then-attest possible.

`package_integrity_ref.kind` is `bundle_manifest`. Its digest and byte length bind the
exact JCS Manifest bytes.

`review_projection_ref` MUST resolve to the rooted `HANDOFF.md` object entry.
`HANDOFF.md` is a derived review projection, not the canonical machine state.

Object paths MUST be safe relative ASCII paths. Logical names and source-language
filenames MAY be preserved as metadata. Absolute paths, `..`, links, device files,
alternate data streams, duplicate paths, and case or Unicode collisions are invalid.

`envelopes/INDEX.json`, if present, is a non-authoritative routing hint. It MUST NOT
override actual envelope bytes or a computed raw digest.

## Detached envelopes

The protocol uses seal-then-attest in this fixed order:

1. Reserve stable `detached_envelope_slots` in the draft root.
2. Generate the review projection and freeze the T0 control or Bundle Manifest.
3. Compute `package_integrity_ref` and never rewrite rooted bytes.
4. Create approval statements, approval verifications, origin and coverage results,
   signatures, security results, Receipts, Receipt attestations, and authorization
   results as detached envelopes.
5. Bind each envelope to the exact root and all subject digests required by its role.
6. Never write an envelope digest, path, decision, or summary back into the root.

Adding, deleting, or reordering detached envelopes MUST NOT change the integrity
root. A detached object for an old root cannot satisfy a slot for a new root.

An `approval_statement` is issued by the actual approving principal. The Producer MAY
orchestrate a challenge but MUST NOT sign as that principal. An
`approval_verification` is a separate object issued by the approval verifier.

The statement directly carries the rooted review/state/scope/exclusion/recipient
subject. The verification carries `approval_statement_digest` and repeats the
root/review/state/scope/recipient/nonce bindings; it intentionally does not duplicate
`material_exclusions_digest`. A valid chain first recomputes the statement field and
then recomputes the complete statement digest. `display_evidence_digest` is
recomputed from evidence outside the Package, never self-proved by the verification.
`review_projection_result_ref` is null exactly for `NOT_RUN`; otherwise it locates
the actual review-result bytes whose subject and outcome match the chain. These
relationships establish structural subject binding only, not issuer authenticity.

## Candidate references

A Receiver calls an object a candidate only after safely capturing its complete raw
bytes and computing the actual SHA-256.

For a candidate, the Receipt MAY retain `{opaque_id, sha256_raw}` in the applicable
`verification_result_refs` slot even when later validation fails. The digest is the
digest of bytes actually received, not a declared digest.

Reference presence proves only that the object can be located by actual bytes. The
Receiver separately checks length, framing, Schema, expected slot type, issuer,
authority, trust anchor, subject root and state, recipient, tenant, issue time, and
expiry.

If no complete candidate bytes were captured for a required slot, the ref is `null`
and the Receipt summary is `NOT_RUN`. If candidate bytes exist but a required check
fails, the ref remains as a locator, the summary is `UNVERIFIED`, an issue identifies
the candidate, and its claimed payload is ignored.

Duplicate opaque IDs, one ID with several digests, an unknown required type, or a
slot/type mismatch are failures. An index entry or filename without captured bytes is
not a candidate.

## Receipt transport

A Receipt is a Receiver object, not part of the original Package root. It binds at
least the exact `package_integrity_ref`, `canonical_state_digest`, current receiving
`challenge_nonce`, Receiver identity and Runtime, `verification_mode`, actual read
set, processing coverage, selected actions, Runtime limits, and continuation status.

`verification_result_refs` are candidate locators. `verification_summary` is a
disposable cache derived from valid role-result payloads plus required-slot candidate
validation state. `observed_producer_claims` preserves Producer claim provenance.
Its three `package_claim_ref` values are fixed exact root locators:
`root.content_coverage`, `root.approval_claim`, and
`root.semantic_actionability_claim`; generated `claim_id` aliases are forbidden.

`receipt_attestation_ref` reserves only the stable opaque ID. The Receipt is sealed
before its attestation is created. The attestation digest is not written back into the
Receipt.

In the one-response `model_only` exception, the Receipt also binds the exact selected
action IDs, current challenge, Runtime execution context, limits, and read set. The
issuing Receiver invalidates the expected nonce after the immediate textual response.

## Legacy conversion metadata

A legacy conversion report uses exactly these format-detection keys:

```text
detection_rules
detection_confidence
parser_version
format_override
```

`format_override` MAY be `null`. A user override records a declared choice; it does
not prove source-format conformance. Except for the generic HANDOFF class below, a
non-null value MUST equal `conversion_origin`, originate from an explicit option
outside the untrusted legacy input, and MUST NOT bypass or relax the frozen exact
marker, protocol, version, parser, or detection rule. Exact supported input produces
the same detection and mapping with or without the override.

Release `0.1.0` defines two non-confusable HANDOFF conversion classes using existing
report fields:

| Class | Required report tuple | Meaning |
| --- | --- | --- |
| Exact v1 | `conversion_origin: handoff_markdown`, `source_version: handoff-md-v1`, `detection_rules: [handoff_md_v1_exact_marker]`, `detection_confidence: 1` | Deterministic parser for the exact first-line marker `# HANDOFF.md v1`. Override is null or merely records an explicit matching selection. |
| Generic user-overridden | `conversion_origin: handoff_markdown`, `source_version: handoff-md-generic`, `detection_rules: [handoff_md_generic_user_override]`, `detection_confidence: 0`, `format_override: handoff_markdown` | Conservative packaging of plain HANDOFF Markdown after explicit outside-input user selection. It is not detector conformance. |

The generic class requires UTF-8 without BOM and LF, safe-input checks, and exact
preservation of the original source bytes as a rooted COLD object. It maps only the
same exact `## Current Intent`, `## Decisions`, `## Constraints`, `## Rejected`, and
`## Next Action` headings when present; all other sections remain unmapped. Absence
of a recognized heading is not guessed from prose. Every mapped semantic remains
non-authoritative/proposed, content coverage is `PARTIAL`, continuity-eval
eligibility is `INELIGIBLE`, approval is `PROPOSED`, semantic actionability is
`BLOCKED`, and a warning identifies generic override conversion. If policy forbids
preserving the original bytes, conversion refuses or quarantines instead of claiming
this class.

Release `0.1.0` also freezes these exact OCH and LTM/CMP classes:

| Class | Required report tuple | Exact source discriminator |
| --- | --- | --- |
| OCH Snapshot v1 | `conversion_origin: och_snapshot`, `source_version: och-snapshot-v1`, `detection_rules: [och_snapshot_v1_exact_six_fields]`, `detection_confidence: 1` | Exactly six `###` fields, in order: `WHAT WE ARE DOING`, `CURRENT STATE`, `COMPLETED`, `DECISIONS`, `CONSTRAINTS`, `NEXT ACTION`. An optional title is exactly one nonempty `# ` H1 line followed only by blank lines before the first field. No other preamble, trailing prose, or field is allowed. |
| LTM CMP v0.1 | `conversion_origin: ltm_packet`, `source_version: ltm-cmp-v0.1`, `detection_rules: [ltm_cmp_v0_1_exact_version]`, `detection_confidence: 1` | Strict JSON object with `ltm_version: "0.1"`, all required CMP fields, and full conformance to the first-party v0.1 closed schema plus this exact discriminator. |
| LTM CMP v0.2 | `conversion_origin: ltm_packet`, `source_version: ltm-cmp-v0.2`, `detection_rules: [ltm_cmp_v0_2_exact_version]`, `detection_confidence: 1` | Strict JSON object with `ltm_version: "0.2"`, all required CMP fields, and full conformance to the first-party v0.2 closed schema. |

Both exact Markdown parsers require strict UTF-8 without BOM and LF line endings;
encoding normalization is not part of legacy detection.

The OCH field headings use three hash characters; an invented marker, `##` heading,
or `REJECTED` field is not OCH Snapshot v1. The permitted H1 title is preserved but
not mapped as a Snapshot field. Other wrapper prose is not silently ignored by the
exact parser. The converter enforces the
machine-checkable six-field and list shape. Semantic claims that a body is concise or
that `NEXT ACTION` is exactly one concrete observable action remain unverified unless
separate language/human evidence establishes them; confidence `1` classifies the
format/version only.

The two CMP classes share the existing `ltm_packet` conversion-origin identifier for
compatibility, but that identifier does not mean a generic or invented packet
format. Both require `id`, `created_at`, `goal`, and `next_step` in addition to the
exact `ltm_version`; v0.2 preserves its additive `parent_id`, `success_criteria`,
decision consequences, methods, and attempt confidence when present. No CMP `1.0`
class or near-synonym source version is defined.

Unknown or mismatched OCH and LTM/CMP versions remain rejected even with an override;
their versioned semantics cannot be inferred safely. An override MAY only record an
explicit matching selection for these exact classes. It never relaxes their syntax,
Schema, field rules, or version and never upgrades source authenticity,
completeness, approval, or semantic continuity.

Each deterministic mapping entry uses exactly these keys:

```text
rule_id
source_line
source_json_pointer
extraction_method
evidence_refs
```

`source_line` and `source_json_pointer` MAY be `null` when that locator form does not
apply. At least the applicable locator and mapping evidence are preserved. A
converter MUST NOT emit near-synonym keys for these fields.

## Timestamp syntax and calendar validity

Release `0.1.0` timestamp fields use the standard JSON Schema `date-time` format and
RFC 3339 semantics; it does not redefine that format as a narrower custom subset.
Both `T`/`t` and `Z`/`z` are accepted, year `0000` is lexically accepted, and second
`60` is accepted by the RFC 3339 leap-second production. Numeric offsets, including
`-00:00`, follow RFC 3339.

A regex is only a prefilter. Deterministic validation MUST also reject nonexistent
calendar dates and out-of-range time or offset components: hour `24`, minute `60`,
second greater than `60`, offset hour `24`, or offset minute `60`. Acceptance of a
`:60` value is lexical/structural only; release `0.1.0` does not ship a historical or
future leap-second schedule and therefore does not prove that the represented civil
instant was an actual announced leap second. An action that depends on that fact
requires external time validation.

## Text, language, and paths

Generated protocol text uses UTF-8 without BOM and LF. Wire keys, enums, IDs, hash
names, and internal paths are ASCII.

Every material natural-language value uses the existing `LocalizedText` structure
with a BCP 47 language tag and explicit `ltr` or `rtl` direction. `und` means unknown
language; `zxx` means non-linguistic content.

Release `0.1.0` pins `assets/registry/registry-lock.json`, the complete IANA Language
Subtag Registry snapshot dated `2026-08-08`, the complete IANA Language Tag
Extensions registry dated `2014-04-02`, and Unicode `15.1.0`. The subtag snapshot has
731799 bytes and raw SHA-256
`sha256:be21e91b6851f750a7b1a687f11209d46ad5a8471d6b10a1efc8d1dac4c8a926`; the
extensions snapshot has 1069 bytes and raw SHA-256
`sha256:fdf7764455c493c245a9b3b5b9cd3938391f0637302c3e943fde86aee652e376`.
A JSON Schema `bcp47` format or simplified regular expression is only a syntax
prefilter. It MUST NOT be reported as qualified BCP 47 validation. Qualified language
validation verifies both locked snapshots, resolves an exact grandfathered or
redundant tag before component parsing, enforces extlang Prefix, treats variant
Prefix as advisory, accepts only registered extension singletons, canonicalizes
extension sequences by singleton order, applies the remaining RFC 5646 registry
rules, and reports the matching Unicode data version. Until that deterministic check runs,
MULTILINGUAL Profile conformance is not PASS and language-dependent action readiness
is limited or blocked according to materiality.

The registered `MULTILINGUAL` status is `QUALIFIED_SUBSET`, limited to
`assets/vectors/language-unicode-v1-001.json`. PASS means that both locked RFC 5646
registries, the listed tags and extension rules, and the listed Unicode 15.1 fixture
operations matched in the reported Runtime. It does not prove that normalization,
protected-span preservation, or Bidi-control scanning ran over an actual Package;
those Package-content checks are separately reported and default to `NOT_RUN`.
Full UAX 9, UAX 29, and UTS 39 also remain `NOT_RUN`. A pass MUST NOT be generalized
to those algorithms, Package checks, or unseen languages.

For a required MULTILINGUAL selection, registry/vector PASS remains limited to its
declared qualification and excluded claims. Package-content normalization, source-
byte preservation, protected-span, and Bidi-control checks are a separate Receiver
Package-use gate and must actually run. Any applicable `NOT_RUN` prevents action
readiness even when the scoped vector qualification passed.

COLD source bytes MUST NOT be normalized, case-folded, width-folded, transliterated,
or rewritten. Derived protocol text MAY use the Profile-pinned normalization rule.

Translations, transliterations, OCR, summaries, and model restatements remain derived
views. They MUST NOT silently replace authoritative source text.

## Self-contained packages

A self-contained Package carries every material, transferable object required for
the declared scope and selected action. External URLs and local paths MAY be
provenance but MUST NOT be the only location for required evidence or an artifact.

For the v0.1 SELF_CONTAINED Profile's deterministic artifact rule, every artifact
Record is conservatively in scope because the wire has no artifact materiality field
or omission subject reference. It must be `PRESENT` and reference a complete rooted
object through a full-byte evidence span with matching raw digest. An omission may
make coverage honest but cannot satisfy or be guessed as a per-Record byte binding;
a BLOCKING/MATERIAL artifact omission or inventory gap makes the required Profile
fail.

Credentials, live permissions, external execution environments, and mutable service
state are represented through `external_state_dependencies`; they are not embedded
as secrets and are not evidence against self-containment when the dependency itself
is correctly declared.

A material policy exclusion that removes necessary decision evidence or an artifact
causes `PARTIAL`. A missing credential value does not by itself cause `PARTIAL` when
the required permission and reauthorization step are fully recorded.

## Limits and failure behavior

Before full parsing, a Receiver MUST enforce configured object count, raw and expanded
size, compression ratio, nesting, JSON depth, graph size, parse time, and token limits.

Unsupported required Profiles, unknown `must_understand` values, and incompatible
major versions cause rejection. Unknown optional extensions are preserved but not
activated.

No implementation may truncate a native Package silently. A known material omission
causes `PARTIAL`; an unknown source boundary causes `UNKNOWN`.

Language, modality, package-size, and security limitations affect Receipt processing
coverage and action readiness. They do not rewrite Package content coverage.

Wire-format conformance proves format and byte relationships only. It does not prove
origin, content truth, completeness, approval, authorization, Receiver understanding,
or semantic continuity.
