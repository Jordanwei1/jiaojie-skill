# Result Model

> Scope: full LCH 0.1 audit results. Ordinary receives return a concise chat
> receipt and do not create these detached result objects or a receipt file.

This document is the normative release `0.1.0` definition of protocol claim and
result meanings. It fixes issuer boundaries, legal values, subject binding, and the
distinction between object location and trust. Other references and implementations
MUST remain equivalent and MUST NOT create synonymous result names.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative as defined by
RFC 2119 and RFC 8174.

## Contents

- [Claims, results, and summaries](#claims-results-and-summaries)
- [Role authority](#role-authority)
- [Producer claims](#producer-claims)
- [Conformance and trust results](#conformance-and-trust-results)
- [Inventory results](#inventory-results)
- [Approval results](#approval-results)
- [Authorization results](#authorization-results)
- [Receipt and security results](#receipt-and-security-results)
- [Semantic run and benchmark results](#semantic-run-and-benchmark-results)
- [NOT_RUN, UNVERIFIED, UNKNOWN, PARTIAL, and FAIL](#not_run-unverified-unknown-partial-and-fail)
- [Candidate references and summaries](#candidate-references-and-summaries)
- [Subject binding](#subject-binding)
- [No-mint and model-only rules](#no-mint-and-model-only-rules)
- [Legacy conversion](#legacy-conversion)

## Claims, results, and summaries

A **Package claim** is a statement made by the Producer inside the integrity root. It
describes what the Producer observed or asserts. It is not an independent result.

A **result object** is issued by one role with authority for one exact subject. It
binds to the Package root, state, and additional role-specific digests. It remains a
detached envelope.

A **Receipt summary** is a disposable Receiver cache. It is derived from valid
role-result payloads plus candidate-slot validation state. It MUST NOT be treated as a
new result issued by the Receiver.

A **benchmark conclusion** is an aggregate over registered runs. It MUST include the
claim scope, sample size, repeats, failures, and uncertainty. It is not a Package
property.

WARM `current_projection` is a derived state cache, not a Package claim or result.
Only `transition_events` and the active `action_graph` revision determine the state it
displays. A Receiver or verifier MUST NOT upgrade a cached projection into an
independent result.

No production Package contains `LOSSLESS_CONFORMANCE` or `LOSSLESS_PASS`.

The enum tables below describe end-to-end Receipt display domains. `NOT_RUN` is a
summary value for an absent applicable result candidate and `UNVERIFIED` is a summary
value for captured but invalid candidate bytes. Neither is a deterministic
structure/review result payload minted merely to report that a check did not run or
that another issuer's candidate was invalid. The owning role emits no object in the
first case; candidate validation ignores the claimed payload in the second. This does
not alter the separate Producer claim `STRUCTURE_SELF_CHECK: NOT_RUN`.

## Role authority

| Role | May issue | Must not issue |
| --- | --- | --- |
| Producer | Package claims, evidence references, envelope slots | verified coverage, verified origin, approval verification, current authorization, semantic result |
| Converter | conversion report, mapping evidence, conservative Package claims | upgraded facts, objective completeness, Receiver result, benchmark result |
| Deterministic verifier | structure, byte-consistency, review-projection result | origin, coverage, semantic continuity, current authorization |
| Trust verifier | origin or signature result | coverage, approval decision, current authorization |
| Coverage auditor | inventory authenticity and coverage result | Receiver understanding, current authorization |
| Approval verifier | approval authenticity, verified decision, subject checks, approval gate | current side-effect authorization |
| Security runner | one scoped security run result | security of untested Runtime, tool, Package, or configuration |
| Receiver | Receipt, processing coverage, selected actions | another role's result unless it emits a distinct role object under valid authority |
| Authorization issuer | one current action-scoped authorization result | blanket or future authority |
| Eval runner | one frozen Receiver run result | generalized benchmark conclusion |
| Benchmark aggregator | scoped aggregate | claim outside registered evidence |

One implementation MAY perform several roles, but it MUST emit distinct objects with
distinct authorities and exact subject bindings. Implementation identity does not
collapse role boundaries.

The actual approving principal issues `approval_statement`. The Producer MAY
orchestrate the interaction but MUST NOT impersonate that principal.

## Producer claims

The root may contain only these Producer claim families and their defined metadata:

```text
STRUCTURE_SELF_CHECK: NOT_RUN | CLAIMED_PASS | CLAIMED_WARN | CLAIMED_FAIL
BYTE_DIGESTS_PRESENT: YES | NO
ORIGIN_CLAIM: UNSPECIFIED | CLAIMED
CONTENT_COVERAGE_CLAIM: COMPLETE | PARTIAL | UNKNOWN
CONSISTENCY_CLAIM: CONSISTENT | DECLARED_CONFLICT | UNKNOWN
SEMANTIC_ACTIONABILITY_CLAIM: SEMANTICALLY_READY | BLOCKED | UNKNOWN
APPROVAL_CLAIM: PROPOSED
CONTINUITY_EVAL_ELIGIBILITY_CLAIM: ELIGIBLE | INELIGIBLE | UNKNOWN
DETACHED_ENVELOPE_SLOTS: []
```

`COMPLETE` MUST be displayed as `COMPLETE (PRODUCER_CLAIM)`. It means only that the
Producer declares no material omission within an anchored scope.

`SEMANTICALLY_READY` is not `continuation_status: READY`, and neither value authorizes
a side effect.

`APPROVAL_CLAIM` remains `PROPOSED` in the root after seal. Detached approval objects
MUST NOT rewrite it.

## Conformance and trust results

The legal conformance and origin values are:

```text
STRUCTURE_CONFORMANCE: PASS | WARN | FAIL | UNVERIFIED | NOT_RUN
BYTE_CONSISTENCY: VERIFIED | UNVERIFIED | FAIL | NOT_RUN
ORIGIN_VERIFICATION: UNAUTHENTICATED | UNVERIFIED | TRANSPORT_AUTHENTICATED | SIGNATURE_VERIFIED | FAIL | NOT_RUN
REVIEW_PROJECTION_CONFORMANCE: PASS | FAIL | UNVERIFIED | NOT_RUN
```

`STRUCTURE_CONFORMANCE` covers Schema shape, fields, state-machine rules,
references, Profile requirements, structural graph rules, and the independent LCH
deterministic format checks. Those checks validate RFC 3986 absolute ASCII URIs and
percent encoding, RFC 3339 timestamps, and release-pinned RFC 5646 language tags as
specified by `wire-format.md` and `conformance.md`. The release's default JSON Schema
2020-12 `format` keywords are annotations; a generic validator that ignores them
cannot support `STRUCTURE_CONFORMANCE: PASS` or `WARN`. Structure conformance does
not prove truth or completeness.

`STRUCTURE_CONFORMANCE: WARN` is required when all required structural rules pass but
the root contains an unknown Profile ID or unsupported Profile version marked
`required: false`. The verifier preserves that entry but keeps it inert, includes an
`issues[]` warning with code `LCH-OPTIONAL-PROFILE-INERT`, and does not let the entry
satisfy a capability or affect semantics. A Receiver that emits a Receipt surfaces
the same nonblocking processing issue. The corresponding condition with
`required: true` is `FAIL`; an exact non-selectable/`UNSUPPORTED` registered pair or
any registered Feature ID in `profiles` is also `FAIL` regardless of `required`.

`BYTE_CONSISTENCY` covers the exact `package_integrity_ref`, all objects committed by
that root, the canonical state digest when required, and review projection byte
commitments. It does not prove origin.

`ORIGIN_VERIFICATION` has distinct meanings:

- `NOT_RUN`: no trust-verification result was issued;
- `UNVERIFIED`: authentication material exists but issuer, trust anchor, or subject
  binding cannot be established;
- `UNAUTHENTICATED`: a trust verifier established that no verifiable authentication
  was supplied;
- `TRANSPORT_AUTHENTICATED`: the declared transport binding passed;
- `SIGNATURE_VERIFIED`: the declared signature and subject binding passed;
- `FAIL`: an authorized origin check detected a mismatch or invalid proof.

`REVIEW_PROJECTION_CONFORMANCE: PASS` requires deterministic reconstruction and exact
byte comparison. A visually similar rendering is insufficient.

A valid deterministic structure-result payload contains only `PASS | WARN | FAIL`;
a valid deterministic review-result payload contains only `PASS | FAIL`.
`UNVERIFIED | NOT_RUN` in these two displayed families are Receiver candidate-state
summaries, not verifier-issued payloads.

The CLI display tokens `STRUCTURE_PASS`, `STRUCTURE_WARN`, and `STRUCTURE_FAIL` are
non-wire aliases mapped one-to-one to `STRUCTURE_CONFORMANCE`. They MUST NOT appear as
a second wire result family.

## Inventory results

The three inventory dimensions are independent and use only these legal subsets:

```text
INVENTORY_AUTHENTICITY:
  VERIFIED | UNVERIFIED | FAIL | NOT_RUN
INVENTORY_SCOPE_COVERAGE:
  VERIFIED | PARTIAL | UNKNOWN | UNVERIFIED | FAIL | NOT_RUN
PACKAGE_VS_INVENTORY_COVERAGE:
  VERIFIED | PARTIAL | UNKNOWN | UNVERIFIED | FAIL | NOT_RUN
```

`INVENTORY_AUTHENTICITY` asks whether the inventory itself is backed by a trusted
platform export, issuer, or frozen fixture. It does not ask whether the inventory
covers the declared scope.

`INVENTORY_SCOPE_COVERAGE` asks whether the trusted inventory covers the anchored
scope. It does not ask whether the Package contains those objects.

`PACKAGE_VS_INVENTORY_COVERAGE` asks whether the Package includes the material
objects in the inventory. It does not prove Receiver processing or understanding.

Every coverage result binds the exact scope, inventory, materiality/Profile, Package
root, and canonical state digests. A Producer-created inventory cannot authenticate
itself merely because Package and inventory agree.

## Approval results

Approval is split into a statement and a verification. The legal displayed result
families are:

```text
APPROVAL_STATEMENT_AUTHENTICITY: VERIFIED | UNVERIFIED | FAIL | NOT_RUN
APPROVAL_VERIFIED_DECISION: APPROVED | REVIEWED | DENIED | UNKNOWN
REVIEW_PROJECTION_CONFORMANCE: PASS | FAIL | UNVERIFIED | NOT_RUN
APPROVAL_GATE: PASS | FAIL | NOT_RUN
```

An `approval_statement` preserves the approving principal's actual decision:
`APPROVED`, `REVIEWED`, or `DENIED`. Authenticity does not change that decision.

An `approval_verification` independently evaluates statement authenticity, verified
decision, subject match, recipient match, time validity, review projection
conformance, challenge or signature evidence, and the final approval gate.
If its `review_projection_conformance` is `NOT_RUN`,
`review_projection_result_ref` is JSON `null` and no review result is minted. For
`PASS` or `FAIL`, the ref resolves to a valid deterministic review-result payload
bound to the same root and canonical state.

`APPROVAL_GATE: PASS` requires all of the following for the exact sealed root:

- statement authenticity is `VERIFIED`;
- verified decision is `APPROVED`;
- subject, recipient, and time requirements pass;
- review projection conformance is `PASS`;
- anti-replay requirements pass.

`REVIEWED` and `DENIED` never pass the gate. A genuine `DENIED` statement is not an
approval failure that may be coerced to `APPROVED`; it is the verified decision.

Approval candidate validity is chain-specific. The Receiver recomputes the
statement's root/review/state bindings, `scope_digest`,
`material_exclusions_digest`, and `recipient_binding_digest`; recomputes
`approval_statement_digest` over the complete direct statement payload; matches the
verification's repeated root/review/state/scope/recipient/nonce fields; validates
`review_projection_result_ref` against the actual deterministic review-result
candidate and matching outcome; and recomputes `display_evidence_digest` from the
complete external evidence and exact displayed review/response bytes. The
verification intentionally does not repeat `material_exclusions_digest`; the
validated statement digest commits it.

Once statement authenticity is `VERIFIED`, the verification's
`verified_decision` exactly equals the statement decision. Otherwise the Receiver
displays `UNKNOWN`; it never trusts a detached verification's positive decision in
advance of statement authentication. Subject match, recipient match, time validity,
review outcome, and the final gate are recomputed from the bound chain and external
evidence, not copied from the verification payload.

Those byte and semantic bindings do not authenticate either issuer. Missing issuer
evidence, trust anchor, expected recipient, current time, nonce/replay state, display
evidence, or response bytes makes a captured approval chain `UNVERIFIED` and
blocking. The Receiver retains actual candidate locators, ignores claimed positive
payloads, displays statement authenticity `UNVERIFIED`, verified decision `UNKNOWN`,
and approval gate `FAIL`. With no complete approval-verification candidate bytes,
those values are respectively `NOT_RUN`, `UNKNOWN`, and `NOT_RUN`.

Approval to transfer a Package is separate from current authorization to perform an
action.

## Authorization results

Each current action authorization is a dedicated `authorization_result` whose
payload result is:

```text
AUTHORIZED | DENIED
```

It binds the receiving challenge, Package root, canonical state, action, current
principal, tenant, resource, operation, purpose, constraints, issue time, expiry, and
trust anchor.

If issuer, current challenge, exact subject, or time cannot be established, the
Receipt uses `UNKNOWN` or `REAUTHORIZATION_REQUIRED`; it MUST NOT invent an
`AUTHORIZED` result.

The Receiver derives only this summary:

```text
AUTHORIZATION_SUMMARY: NOT_APPLICABLE | ALL_REQUIRED_AUTHORIZED | REAUTHORIZATION_REQUIRED | DENIED | UNKNOWN
```

`NOT_APPLICABLE` is legal only when no selected action requires authorization.
Historical Package approval, old consent, or an origin signature cannot satisfy a
current authorization requirement.

## Receipt and security results

The remaining conformance and security result families are:

```text
RECEIPT_CONFORMANCE: PASS | FAIL | NOT_RUN
SECURITY_RUN_RESULT: PASS | FAIL | NOT_RUN
```

`RECEIPT_CONFORMANCE` checks that a Receipt binds the exact root, state, challenge,
read set, processing coverage, Runtime, selected actions, and required summaries. It
does not prove semantic understanding.

`SECURITY_RUN_RESULT` applies only to the recorded Package, malicious fixture,
Runtime, sandbox, tool posture, permissions, and run. It does not prove security for
another environment.

The Receipt has `verification_result_refs.security_run` as an object locator. It does
not define a `security_run` member in `verification_summary`. When no security run
object exists, this ref remains `null`, an issue records that the run did not occur,
and `processing_status` reflects `SECURITY_LIMITED` where applicable.

If required isolation cannot be enforced, the Receipt keeps
`processing_status: SECURITY_LIMITED`, adds
`blocking_reasons[].code: SECURITY_BLOCKED`, and blocks continuation.

## Semantic run and benchmark results

Semantic and aggregate result families are:

```text
RECEIVER_RUN_RESULT: PASS | FAIL | NOT_RUN
I18N_RUN_RESULT: PASS | FAIL | NOT_APPLICABLE | NOT_RUN
BENCHMARK_RESULT: {score, observed_hard_gate_pass_rate, n, repeats, confidence_interval} | NOT_RUN
```

`RECEIVER_RUN_RESULT: PASS` applies to one frozen Producer, Receiver, model, Runtime,
language, tool posture, permission state, external state, and case. It cannot be
copied into a production Package.

`I18N_RUN_RESULT` applies to the registered language pair, direction, model pair,
domain, and fixture.

`BENCHMARK_RESULT` MUST report observed evidence only. It MUST NOT generalize beyond
the registered claim scope or omit failed runs.

No Receipt self-assessment, structural PASS, byte VERIFIED result, or high score may
be converted into universal losslessness.

## NOT_RUN, UNVERIFIED, UNKNOWN, PARTIAL, and FAIL

These values are not synonyms:

- `NOT_RUN` means no complete candidate bytes were safely captured for the
  applicable result slot, including when the owning role did not issue a result
  object.
- `UNVERIFIED` means complete candidate bytes exist, but framing, Schema, issuer,
  authority, trust, subject, recipient, time, or required verification coverage did
  not establish a valid role result.
- `UNKNOWN` is legal only where the result family allows an indeterminate trusted
  boundary or decision.
- `PARTIAL` is legal only where the result family allows an established material
  coverage gap.
- `FAIL` means an authorized check ran and detected a mismatch, contradiction,
  tampering condition, or failed rule.

An implementation MUST use the legal subset for the specific result family. For
example, `INVENTORY_AUTHENTICITY` does not accept `PARTIAL` or `UNKNOWN`.

A required `NOT_RUN`, `UNVERIFIED`, or `FAIL` blocks only the actions for which that
result is required. A known applicable `FAIL` cannot be waived by the model-only
text exception.

## Candidate references and summaries

A detached object becomes a candidate only after complete raw bytes are safely
captured and the Receiver computes their actual SHA-256.

`verification_result_refs` MAY retain the actual `{opaque_id, sha256_raw}` locator for
a candidate regardless of its claimed positive, negative, partial, unknown, failed,
or unverified payload.

Reference presence proves neither trust nor outcome. The Receiver validates the
candidate under the owning role's requirements.

The summary algorithm is:

1. No complete candidate bytes for a required slot: ref is `null`; summary is
   `NOT_RUN`; add a missing-candidate issue.
2. Candidate bytes captured, but any required validation fails: retain the actual
   locator; summary is `UNVERIFIED`; add an issue; ignore the candidate's payload.
3. Candidate is a valid role result with exact subject binding: preserve its legal
   payload outcome, including adverse `FAIL`, `PARTIAL`, `UNKNOWN`, `REVIEWED`, or
   `DENIED` values.

The summary MUST expose every applicable adverse outcome. It MUST NOT omit an invalid
or missing required slot to create a cleaner display.

## Subject binding

Every detached result binds the exact `package_integrity_ref` and the
`canonical_state_digest` when required. Role-specific subjects add the relevant
scope, inventory, materiality, Profile, review, statement, recipient, tenant,
challenge, action, resource, operation, purpose, constraints, read set, processing
coverage, time, and Runtime digests.

A result for one root, state, recipient, action, Runtime, or time MUST NOT be reused
for another. Adding a detached object cannot retroactively change the root.

A raw digest validates bytes only. It does not establish issuer identity, authority,
truth, approval, or current permission.

Every protocol field named `scope_digest`, `material_exclusions_digest`,
`recipient_binding_digest`, `display_evidence_digest`,
`materiality_profile_digest`, `package_profile_digest`, `read_set_digest`,
`processing_coverage_digest`, `purpose_digest`, `constraints_digest`,
`inventory_digest`, `approval_statement_digest`, `receipt_sha256`, or
`revision_digest` uses the closed
`lch-derived-digest-v1` registry in `wire-format.md`. A role MUST recompute the exact
registered projection; it MUST NOT accept an ad-hoc hash merely because it is
syntactically a SHA-256 value. Purpose and constraints come from the current external
authorization request, and Receipt projections come from the exact Receipt being
attested.

## No-mint and model-only rules

When a deterministic verifier did not run, it MUST NOT mint a structure, byte, or
review result object. If no complete candidate bytes were captured for the applicable
slot, the Receipt summary uses `NOT_RUN`; if candidate bytes were captured, the
candidate-validation algorithm still applies.

When a security runner did not run, it MUST NOT mint a security result object.
If no security-result candidate bytes were captured,
`verification_result_refs.security_run` remains `null`, and an issue records the
missing run. There is no `security_run` member in `verification_summary`.

A `model_only` Receiver MUST NOT issue deterministic, origin, coverage, approval,
security, semantic-run, or benchmark result objects at all. It MAY preserve a valid
result issued by the owning role, or derive `NOT_RUN` and `UNVERIFIED` display values
from candidate-slot state, without becoming that result's issuer.

The one-response text-only exception changes action readiness for one immediate
language-only response. It does not change any result value and MUST NOT create a
result object.

## Legacy conversion

The first-version Converter emits only conservative Package claims. It keeps
`CONTENT_COVERAGE_CLAIM: PARTIAL`,
`CONTINUITY_EVAL_ELIGIBILITY_CLAIM: INELIGIBLE`, empty coverage result references,
and `APPROVAL_CLAIM: PROPOSED`.

Its conversion report uses `detection_rules`, `detection_confidence`,
`parser_version`, and `format_override`. Each mapping entry uses `rule_id`,
`source_line`, `source_json_pointer`, `extraction_method`, and `evidence_refs`.
`format_override`, `source_line`, and `source_json_pointer` MAY be `null` under the
conditions defined by `wire-format.md`.

A non-null `format_override` records an explicit outside-input selection. For exact
v1 HANDOFF, OCH, and LTM it never authorizes a detector or version mismatch. For the
sole generic HANDOFF exception, it selects the frozen `handoff-md-generic` class with
confidence `0`, exact original-byte preservation, conservative five-heading mapping,
warnings, and `PARTIAL/INELIGIBLE/PROPOSED/BLOCKED` output. This is not detector
conformance and never upgrades source authenticity, approval, or continuity.

The exact versioned classes are `och-snapshot-v1` with the canonical ordered six
`###` fields, and dennisdevulder/ltm CMP `ltm-cmp-v0.1` or `ltm-cmp-v0.2` selected by
exact `ltm_version` and the corresponding closed first-party Schema. Invented CMP
`1.0` labels and OCH layouts containing an invented marker, `##` fields, or
`REJECTED` are unsupported. Unknown OCH/CMP versions remain rejected even when an
override was supplied. Successful exact parsing leaves all imported semantic
authority conservative; a source-declared CMP provenance hash is not a verified
digest of the bytes received by this converter.

The Converter MUST NOT emit `RECEIVER_RUN_RESULT`, even as `NOT_RUN`. Only an Eval
runner for an actual frozen Receiver run may create that result.

Successful conversion does not establish native-source authenticity, objective
completeness, approval, self-containment, or semantic continuity.
