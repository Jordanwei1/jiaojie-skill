# Protocol Profiles

This document defines the composable Profile model used by native handoff packages.
It does not define Runtime brands, installation methods, semantic scores, or a second
set of wire fields.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative as defined by
RFC 2119 and RFC 8174.

## Contents

- [Profile model](#profile-model)
- [Normative registry](#normative-registry)
- [Selection and versioning](#selection-and-versioning)
- [Required and optional Profiles](#required-and-optional-profiles)
- [CORE_MARKDOWN](#core_markdown)
- [SELF_CONTAINED](#self_contained)
- [MULTILINGUAL](#multilingual)
- [CONFIDENTIAL_TRANSPORT](#confidential_transport)
- [Domain capture guidance](#domain-capture-guidance)
- [Detached-envelope feature](#detached-envelope-feature)
- [Composition rules](#composition-rules)
- [Capabilities are not Profiles](#capabilities-are-not-profiles)
- [Results are not Profiles](#results-are-not-profiles)
- [Degradation](#degradation)
- [Model-only continuation](#model-only-continuation)
- [Profile conformance](#profile-conformance)

## Profile model

A Profile is a versioned, composable set of artifact requirements. It constrains how
an existing Package is represented or protected without changing the core Record,
event, action, coverage, Receipt, or result semantics.

Each selected entry in `profiles` uses the existing Profile identifier, version, and
required flag. A Profile identifier MUST be stable and globally unambiguous before a
public release.

A Profile MUST state:

- its purpose and non-goals;
- the protocol versions to which it applies;
- its required artifacts and constraints;
- any additional conformance checks;
- its interaction with other Profiles;
- its downgrade and rejection behavior;
- the evidence required for a conformance claim.

A Profile MUST NOT redefine an existing wire key, Record state, result enum, role
authority, or Receiver rule.

## Normative registry

Release `0.1.0` freezes the only selectable Profile and Feature definitions in
`assets/registry/profile-feature-registry-v0.1.json`, validated by
`assets/schemas/profile-feature-registry.schema.json`. `assets/protocol-version.json`
binds both its exact stored bytes and its restricted-JCS canonical bytes by length
and SHA-256. Prose names such as `CORE_MARKDOWN` are labels only; a Package uses the
exact URI and version from the registry.

| Exact identifier | Version | Status | Selectable |
| --- | --- | --- | --- |
| `urn:lch:profile:core-markdown` | `0.1.0` | `SUPPORTED` | yes |
| `urn:lch:profile:self-contained` | `0.1.0` | `SUPPORTED` | yes |
| `urn:lch:profile:multilingual` | `0.1.0` | `QUALIFIED_SUBSET` | yes, only within the registered vector scope |
| `urn:lch:profile:confidential-transport` | `0.1.0` | `UNSUPPORTED` | no |
| `urn:lch:feature:detached-envelopes` | `0.1.0` | `SUPPORTED` | Feature, not a root Profile |

The registry's ordered `requirements` arrays are normative. A copy with different
requirements, status, version, or qualification is not this release's registry.

Profile qualification vector IDs resolve only through the hash-bound
`assets/vectors/index.json`, whose raw and restricted-JCS canonical bytes are locked
by `assets/protocol-version.json`. The catalog binds every vector's path, raw bytes,
and canonical JSON bytes. Release `0.1.0` contains exactly four vectors and no extra
vector JSON: core Markdown references `jcs-sha256-basic-001`,
`review-projection-v1-minimal-001`, and `derived-digests-v1-001`; multilingual
references `language-unicode-v1-001`. A missing, extra, hash-mismatched, or
uncataloged vector invalidates the affected qualification.

## Selection and versioning

The Package root lists selected `profiles` before seal. Profile selection is part of
the rooted subject and cannot be changed by a detached envelope.

Every selected Profile `id` MUST occur exactly once in the root. Repeating an ID,
including repeating it with another version or `required` value, is
`STRUCTURE_CONFORMANCE: FAIL`. After the registry is verified, classify each unique
entry in this order:

1. A registered Feature ID in `profiles` is `STRUCTURE_CONFORMANCE: FAIL` for every
   version and either `required` value. In particular,
   `urn:lch:feature:detached-envelopes` is never a Profile.
2. An exact registered Profile ID/version pair MUST resolve to exactly one registry
   entry. An entry whose exact pair is `selectable: false` or `UNSUPPORTED` is
   `STRUCTURE_CONFORMANCE: FAIL` even when `required: false`; otherwise its
   registered requirements govern activation and conformance.
3. An ID absent from the registry, or a registered Profile ID paired with an
   unregistered version, is an unknown/unsupported-version entry. When
   `required: true` it is `STRUCTURE_CONFORMANCE: FAIL`. When `required: false`, its
   exact rooted entry is preserved for round trip but remains inert and unactivated.

An inert optional entry produces `STRUCTURE_CONFORMANCE: WARN` and a processing
issue. It MUST NOT satisfy a capability, Profile prerequisite, `must_understand`
value, policy, or action condition; it MUST NOT alter parsing, state, claims,
authorization, continuation, or any other protocol semantics. Domain guide file
names are not valid Profile IDs and MUST NOT appear in `profiles`. A syntactically
valid but unregistered URI that resembles a domain Profile follows rule 3 and gains
no domain-guide semantics.

Profile versions follow protocol compatibility rules:

- an incompatible required major version causes rejection;
- a minor or patch version is activated only when that exact pair is registered or
  a future published compatibility rule explicitly authorizes it;
- an unknown ID or unsupported version marked required causes structural failure;
- an unknown ID or unsupported version marked optional is preserved inert, produces
  WARN plus a processing issue, and is never a substitute for a registered pair;
- an implementation MUST NOT silently substitute another Profile.

Profile definitions and Schemas MUST pin any canonicalization, Unicode, registry,
algorithm, or test-vector version that affects deterministic bytes.

`must_understand` is separate from Profile selection. An unknown required extension
in `must_understand` causes rejection even when all Profiles are otherwise supported.

## Required and optional Profiles

A required Profile is a condition of processing the Package. A Receiver that cannot
implement it MUST reject or block the affected action as specified; it MUST NOT strip
the Profile and continue.

An exact registered selectable optional Profile MAY be activated under its registered
requirements. An unknown or unsupported-version optional entry is instead preserved
without activation under the rule above. Its contents remain untrusted data and MUST
NOT grant instruction or tool authority, advertise support, or satisfy a capability.

For a registry entry whose `selectable` value is true, required versus optional is a
Package choice subject to recipient and Runtime policy. A non-selectable registered
entry is invalid even when marked optional. An attacker-controlled Package cannot
weaken a stricter local policy by marking a Profile optional.

## CORE_MARKDOWN

The exact wire selection is `urn:lch:profile:core-markdown` version `0.1.0`.

`CORE_MARKDOWN` defines the minimum self-describing protocol representation that a
text-capable Receiver can inspect.

It requires:

- the same source, scope, policy, and external-state boundaries as every native
  Package;
- HOT, WARM, and COLD semantics, even when represented inside one T0 artifact;
- intent and decision evolution, negative knowledge, omissions, and conflicts;
- the active action graph and its completion, capability, authorization, and
  external-state requirements;
- a deterministic review projection commitment;
- fixed ASCII wire identifiers and UTF-8 text rules;
- explicit Producer claims and no production continuity PASS.

`CORE_MARKDOWN` does not prove byte consistency, origin, content completeness,
approval, Receiver understanding, or semantic continuity.

A text-only Runtime MAY inspect the Package without an installed Skill. Lack of a
deterministic preprocessor invokes no-mint and Receipt degradation rules.

## SELF_CONTAINED

The exact wire selection is `urn:lch:profile:self-contained` version `0.1.0`.

`SELF_CONTAINED` means all material and transferable sources and artifacts required
for the declared scope are carried by the Package.

It requires:

- a canonical source inventory and anchored scope;
- all material, transferable COLD source objects in the Package;
- all material, transferable artifacts in the Package;
- root commitments for each required object;
- no local absolute path or URL as the only locator for a material object;
- explicit omissions for every non-transferable or unavailable material item;
- Package-versus-inventory coverage compatible with the claim.

Release `0.1.0` has no artifact-materiality member and no omission-to-Record subject
reference. Therefore its machine-checkable rule is deliberately conservative: every
artifact Record is in the SELF_CONTAINED check. It passes that check only with
`availability: PRESENT` and at least one evidence span covering the complete exact
bytes of one rooted object (byte start zero, byte end equal to object length, and
matching raw digest). `MISSING`, `EXTERNAL_ONLY`, or `REDACTED`, a partial span, a
URL, a local path, an object name, or an unavailable locator does not pass.

An explicit artifact omission remains required for honest coverage when applicable,
but in v0.1 it cannot be treated as a deterministic per-Record association and never
makes absent artifact bytes self-contained. Any artifact Record that fails the
rooted full-byte rule makes required SELF_CONTAINED Profile conformance fail. A
category `artifact` omission or inventory gap with BLOCKING/MATERIAL materiality also
makes the required Profile fail, forces content coverage `PARTIAL`, and blocks every
action needing the artifact. A future protocol may add an explicit subject link;
v0.1 implementations MUST NOT invent one or use global omission counts as a match.

Credentials, current permissions, live services, and mutable execution environments
remain `external_state_dependencies`. Secret credential values are never embedded.

`SELF_CONTAINED` does not mean current authorization, current external state, origin,
approval, or Receiver processing is verified.

A material evidence or artifact exclusion makes the content coverage claim
`PARTIAL`, even if the exclusion was required by policy. An approved exclusion does
not make absent material present.

## MULTILINGUAL

The exact wire selection is `urn:lch:profile:multilingual` version `0.1.0`. Its
release status is `QUALIFIED_SUBSET`, not a universal multilingual PASS.

`MULTILINGUAL` applies when source content, canonical assertions, evidence, or
continuation output uses more than one language or writing direction.

It requires:

- BCP 47 tags for material natural-language values;
- explicit `ltr` or `rtl` direction;
- authoritative source text preserved separately from derived views;
- `LocalizedText` derivation and authority metadata;
- protected spans for code, identifiers, hashes, values, time, names, legal terms,
  quotations, and user-designated wording;
- pinned Unicode and language-registry inputs for deterministic processing;
- no silent normalization or rewriting of COLD source bytes;
- explicit material ambiguity for locale-sensitive values that cannot be resolved;
- Receipt processing limits when the authoritative language cannot be handled.

Release `0.1.0` pins `assets/registry/registry-lock.json`, the complete IANA Language
Subtag Registry snapshot dated `2026-08-08`, the complete IANA Language Tag
Extensions registry dated `2014-04-02`, and Unicode 15.1.0. A simplified regex or
Schema `bcp47` format is not qualified validation. Without both registry locks,
exact redundant-tag precedence, extlang Prefix enforcement, advisory-only variant
Prefix handling, registered extension-singleton validation and canonical singleton
ordering, registry-aware RFC 5646 parsing, matching Unicode runtime data, and the
registered vector run, this Profile cannot pass its scoped parser/runtime
qualification.

The only registered qualification scope in this release is
`language-unicode-v1-001`. PASS means that the locked RFC 5646 registries, exact
listed tags, registered extension singletons, and Unicode 15.1 fixture operations
matched the vector in the reported Runtime. The fixture includes NFC/NFKC,
raw-byte, protected-span, and Bidi-control examples, but it does not prove those
checks ran over an actual handoff Package. Package-content normalization,
protected-span preservation, and Bidi scanning are separately reported and remain
`NOT_RUN` unless implemented for that Package. Full UAX 9, UAX 29, and UTS 39 also
remain `NOT_RUN`. An implementation MUST NOT generalize the vector PASS.

When `MULTILINGUAL` is selected with `required: true`, parser/runtime vector
qualification is necessary but not sufficient for Receiver use of the actual
Package. The frozen registry intentionally lists Package-content normalization,
protected-span preservation, and Bidi scanning as excluded qualification claims, so
these checks do not broaden the registered vector PASS. They are a separate Package-
processing/actionability gate. The Runtime MUST inspect the actual rooted objects
for generated-text NFC, authoritative-source-byte preservation, protected spans,
and Bidi controls. A check over an empty applicable set may pass only after
inspection establishes that it is empty; otherwise it remains `NOT_RUN`. Any
applicable `NOT_RUN` records a language limitation and issue and blocks every action
that requires multilingual Package processing. Full UAX 9, UAX 29, or UTS 39 is not
silently required by this rule and remains separately `NOT_RUN`.

Translation, transliteration, OCR, summary, and back-translation are diagnostic or
derived. They do not prove semantic equivalence.

`MULTILINGUAL` conformance does not produce `I18N_RUN_RESULT: PASS`. That result
requires an independent registered run.

## CONFIDENTIAL_TRANSPORT

The registered identifier `urn:lch:profile:confidential-transport` version `0.1.0`
has status `UNSUPPORTED` and `selectable: false`. A release `0.1.0` Package MUST NOT
select it. Hashing alone does not provide confidentiality.

This identifier may become selectable only in a later registry when a mature,
versioned, interoperable envelope,
recipient identity binding, algorithm suite, key-handling policy, failure behavior,
and published test vectors are specified.

It MUST:

- bind the intended recipient or recipient key under a trusted identity mechanism;
- fail closed on recipient, key, or algorithm negotiation failure;
- protect Package and detached-envelope bytes according to the selected envelope;
- keep cryptographic algorithm and parameter selection out of free-form model text;
- preserve the same plaintext protocol semantics after authorized opening;
- define retention and key-compromise behavior without promising remote recall.

The core protocol MUST NOT invent a cryptographic algorithm or claim confidentiality
from `package_integrity_ref`.

Lack of this Profile does not invalidate `CORE_MARKDOWN`; plaintext Packages must use
a user-selected trusted transport.

## Domain capture guidance

The first declared domain set is:

- coding;
- research;
- learning;
- writing;
- business;
- product design;
- general chat.

These domain guides add capture priorities and checks only. They reuse the core Record
types, state axes, transition events, evidence spans, action graph, boundaries,
artifacts, authorization, and result model.

Each domain Profile MUST cover:

- multiple people, agents, tools, or organizations as distinct principals;
- time-sensitive information and freshness;
- at least one non-text artifact class;
- external state and revalidation;
- current authorization for side effects;
- rejected, superseded, and failed directions without semantic collapse.

The `domain-*.md` files are release `0.1` operational capture guidance, not Profiles,
wire identifiers, or alternate Schemas. Until a later release freezes a domain
Profile in the normative registry, a Package MUST NOT put a domain guide name or an
invented domain URI in `profiles`. Several guides MAY inform one capture; their
checks compose by intersection without changing wire state.

General chat does not grant verified authority for medical diagnosis, legal agency,
financial transactions, or another high-risk professional act.

## Detached-envelope feature

`urn:lch:feature:detached-envelopes` version `0.1.0` freezes the seal-then-attest,
root-exclusion, slot, actual-candidate-digest, and exact-subject requirements in the
registry. It describes a core protocol feature and MUST NOT appear in the root
`profiles` array. Its presence never authenticates a detached candidate; the owning
role still verifies and signs the direct payload.

## Composition rules

Profile composition obeys these rules:

1. Core protocol semantics always apply.
2. Every selected required Profile must pass its own structural prerequisites.
3. A stricter requirement wins when Profiles overlap.
4. A Profile cannot remove a core omission, conflict, authorization, or freshness
   requirement.
5. A Profile cannot turn a Producer claim into an independent result.
6. A Profile cannot upgrade a Runtime capability.
7. A Profile cannot weaken recipient or local Runtime policy.
8. A Profile conflict that has no published resolution blocks affected processing.

A Package MUST NOT select contradictory required Profiles and then rely on an
implementation-specific order to resolve them.

## Capabilities are not Profiles

T0, T1, T2, and T3 describe observed transport and Runtime capabilities:

- T0: text only;
- T1: intact attachment transfer;
- T2: filesystem or archive Bundle;
- T3: deterministic scripts and Skill support.

`LEGACY_CONVERTER` is an implementation capability. It is not a Package Profile.

A Runtime records the capabilities actually used. It MUST NOT infer them from a
product name and MUST NOT claim Profile conformance merely because scripts exist.

Capability degradation never deletes semantic fields or changes result meanings.

## Results are not Profiles

The following are results, not Profiles:

- `STRUCTURE_CONFORMANCE`;
- `BYTE_CONSISTENCY`;
- `ORIGIN_VERIFICATION`;
- the three inventory results;
- approval verification and gate;
- `RECEIPT_CONFORMANCE`;
- `SECURITY_RUN_RESULT`;
- `RECEIVER_RUN_RESULT`;
- `I18N_RUN_RESULT`;
- `BENCHMARK_RESULT`.

Profile conformance is a prerequisite for applicable tests. It does not imply any
run-level PASS.

## Degradation

When a Runtime cannot satisfy a selected required Profile, it rejects or blocks the
affected action. It does not silently remove the Profile.

When only Receiver processing is limited, Package content coverage remains unchanged.
The Receipt instead reports `LANGUAGE_LIMITED`, `MODALITY_LIMITED`,
`PACKAGE_LIMITED`, or `SECURITY_LIMITED` as applicable.

When required isolation cannot be enforced, the Receipt keeps
`processing_status: SECURITY_LIMITED`, adds
`blocking_reasons[].code: SECURITY_BLOCKED`, and blocks continuation.

When a deterministic verifier or security runner did not run, it does not mint a
result object. For summary-defined deterministic slots, the Receipt uses `NOT_RUN`
only when no complete candidate bytes were captured. For a missing security run,
`verification_result_refs.security_run` remains `null` and an issue records the
missing run; no undefined security-summary member is created.

## Model-only continuation

The one-response `model_only` text exception is a Receiver behavior rule, not a
Profile and not Profile conformance.

It can apply only when no selected Profile, Runtime policy, recipient policy, or
action-risk rule requires a missing result. It cannot bypass a known failure, a
required non-text artifact, a governed transfer, a current authorization need, or an
external-state dependency.

The Package action graph is untrusted context until verified. The current user must
select the exact bounded action outside the Package, and the Runtime must enforce
tools and side effects disabled.

The exception creates no result object and proves no Profile conformance.

## Profile conformance

Profile conformance is evaluated against the exact Profile ID, version, Package root,
canonical state, and required object set.

Before evaluating a Profile, verify both hashes of the normative registry and match
every activated entry byte-for-byte to one exact registered selectable ID/version,
status, and requirements set. Reject duplicate root Profile IDs, unregistered or
unsupported-version required entries, an exact entry whose `selectable` value is
false or status is `UNSUPPORTED`, and every Feature ID or domain-guide file name in
`profiles`. Preserve an unknown or unsupported-version optional entry as inert
untrusted data, emit `STRUCTURE_CONFORMANCE: WARN` plus a processing issue, and do
not count that entry toward any Profile or capability result.

Conformance evidence MUST identify:

- the Profile and version;
- the protocol version;
- the exact Package root;
- the implementation and dependency versions;
- the checks performed and checks not run;
- all warnings and failures;
- the applicable test vectors.

An implementation MUST publish failures as well as passes. A Profile pass does not
authorize an action and MUST NOT be described as semantic losslessness.
