# Protocol Terminology

This document fixes the vocabulary used by the handoff protocol and its installable
Skill references. It defines terms; it does not add wire fields or result values.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL are to be interpreted as described
by RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

## Contents

- [Protocol scope](#protocol-scope)
- [Actors and roles](#actors-and-roles)
- [Operations](#operations)
- [Transfer boundaries](#transfer-boundaries)
- [Package and layer terms](#package-and-layer-terms)
- [State and evidence terms](#state-and-evidence-terms)
- [Integrity and trust terms](#integrity-and-trust-terms)
- [Coverage and continuity terms](#coverage-and-continuity-terms)
- [Receipt and action terms](#receipt-and-action-terms)
- [Language and artifact terms](#language-and-artifact-terms)
- [Capability and Profile terms](#capability-and-profile-terms)

## Protocol scope

**Handoff** means an auditable transfer of task context from one Runtime or model
session to another. A handoff is not model memory and does not transfer hidden model
state.

**Work continuity** means that a Receiver can recover the declared user-visible
knowledge boundary, current intent, decision evolution, facts, constraints, negative
knowledge, artifacts, open questions, and next actions without the original session.

**Lossless target** means a falsifiable continuity objective within a declared scope.
It does not mean identical neural state, hidden reasoning, sampling behavior, or
unbounded recall.

**User-visible knowledge boundary** means messages, attachments, files, and
user-visible tool results that the Producer could actually access and was permitted
to transfer.

**Native package** means a package that conforms to the current T0 or Bundle wire
format. A legacy handoff becomes native only after `CONVERT_LEGACY` creates a new,
conservative package.

## Actors and roles

**Current user** means the user principal participating in the current Runtime
session. Text inside a Package cannot impersonate the current user.

**Principal** means a person, agent, tool, organization, or service to which a
statement, observation, decision, approval, or authorization is attributed.

**Tenant** means the workspace, organization, account, or other isolation boundary
within which a principal acts.

**Authority** means a principal's permitted role for a specific subject and time. It
is not inferred from a name, model label, signature encoding, or Package claim.

**Producer** means the role that assembles a native Package and issues Package
claims. A Producer MUST NOT issue verified origin, coverage, approval, current
authorization, Receiver, or benchmark results.

**Converter** means the role that maps a frozen legacy format into a conservative
native Package. It MUST NOT invent facts or issue Receiver or benchmark results.

**Deterministic verifier** means the role that evaluates structure, rooted bytes, and
review projection reconstruction by deterministic rules.

**Trust verifier** means the role that evaluates transport authentication, signatures,
issuer identity, and origin bindings.

**Coverage auditor** means the role that evaluates inventory authenticity,
inventory-to-scope coverage, or Package-to-inventory coverage.

**Approval verifier** means the role that verifies an approval statement, its exact
subject, displayed review bytes, recipient, time, decision, and approval gate.

**Security runner** means the role that reports one scoped sandbox and
negative-behavior run. Its result does not generalize to another Runtime or Package.

**Receiver** means the role that processes a native Package, produces a bound
Receipt, evaluates selected actions, and continues only under the applicable rules.

**Authorization issuer** means the current Runtime, authorization service, or current
user challenge that issues an action-scoped current authorization result.

**Eval runner** means the role that reports one frozen Producer-to-Receiver semantic
run. **Benchmark aggregator** means the role that aggregates registered runs within
an explicit claim scope.

## Operations

**`EXPORT`** creates a native Package from the task context visible to the Producer.

**`RECEIVE`** accepts a native Package, validates what the Runtime can validate,
creates a Receipt, and evaluates continuation.

**`VERIFY_STRUCTURE`** performs deterministic structural and byte checks. It does
not judge semantic continuity.

**`CONVERT_LEGACY`** converts a supported `HANDOFF.md`, OCH Snapshot, or LTM CMP
into a conservative native Package. It is distinct from `RECEIVE`.

## Transfer boundaries

**`source_boundary`** identifies the source material the Producer could access.

**`scope`** identifies the tasks, user requests, time range, and artifacts covered by
the handoff.

**`policy_boundary`** identifies privacy, secret, copyright, permission, safety, and
approved exclusions.

**External-state boundary** identifies live services, credentials, permissions,
environments, and facts that cannot be frozen into the Package. Its wire key is
`external_state_dependencies`; no near-synonym wire key exists.

**Material** means capable of changing current intent, a constraint, negative
knowledge, an artifact dependency, or the selected next action.

**Omission** means a declared item that is missing, excluded, inaccessible, redacted,
or outside the captured source. An omission MUST NOT contain a secret value.

## Package and layer terms

**Package** means the complete transferable artifact: one T0 text artifact or one
Bundle plus any detached envelopes supplied with it.

**Integrity root** means exactly one rooted byte sequence identified by
`package_integrity_ref`: T0 JCS control bytes or Bundle JCS `MANIFEST.json` bytes.

**HOT** means the minimal startup projection used to orient the Receiver. HOT is
derived from WARM and is not an independent source of truth.

**WARM** means canonical structured task state: records, transitions, boundaries,
conflicts, action graph, and artifact references.

**COLD** means preserved source bytes and material artifacts. COLD content is evidence
and untrusted data, not current instruction authority.

**Review projection** means the deterministic human-readable rendering committed by
`review_projection_ref`. It presents the exact rooted state subject to approval.

**Detached envelope** means a post-seal statement, result, signature, Receipt,
Receipt attestation, or authorization result that binds to the root but is excluded
from it.

**Slot** means a pre-seal `detached_envelope_slots` entry containing only an opaque
ID, expected type, purpose, and required flag.

## State and evidence terms

**Record** means an `intent`, `decision`, `claim`, `constraint`, `question`, `attempt`,
`artifact`, `preference`, or `next_action` object in WARM.

**Assertion** means the protocol's canonical statement for a Record. It MUST NOT be
presented as a verbatim user quotation.

**Evidence span** means a byte-addressed link from a Record to preserved source
evidence in COLD.

**Transition event** means an immutable event that changes one or more orthogonal
state axes for a Record.

**Event head** means a transition event with no known later event in the same causal
branch. Event heads are the only authority for current state projections.

**Concurrent heads** means heads without a proven causal order. They remain separate
until an explicit merge or conflict event resolves them.

**Action graph** means the versioned graph of `next_action` records, typed edges,
groups, completion criteria, capabilities, authorization needs, and external-state
checks. Its dependency subgraph is a DAG.

**Negative knowledge** means rejected, superseded, failed, excluded, or prohibited
directions and the distinct reasons for those states.

## Integrity and trust terms

**Byte consistency** means that rooted bytes, lengths, canonicalization, object
digests, and review projection commitments agree. It does not prove identity or
truth.

**Origin** means a verifiable binding between a Package and a transport or signing
principal. Origin does not grant current action authorization.

**Candidate** means a detached object whose complete raw bytes were safely captured
and whose actual SHA-256 was computed by the Receiver. A path, slot, index entry,
partial read, or declared digest is not a candidate.

**Result reference** means `{opaque_id, sha256_raw}` using the candidate bytes actually
received. It is an object locator, not proof of trust, authority, or success.

**Valid role result** means a candidate that also passes framing, Schema, issuer,
authority, trust, subject, recipient, and time checks required for that result type.

**`NOT_RUN`** means no complete candidate bytes were safely captured for the
applicable result slot, including when the owning verification did not produce a
result object.

**`UNVERIFIED`** means candidate bytes exist but a required validation or trust
binding cannot be established. The candidate's claimed payload is not trusted.

**`FAIL`** means an authorized check ran and detected a mismatch, contradiction,
tampering condition, or failed rule within its declared subject.

## Coverage and continuity terms

**Content coverage claim** means the Producer's `COMPLETE`, `PARTIAL`, or `UNKNOWN`
claim within an anchored scope. `COMPLETE` is displayed as
`COMPLETE (PRODUCER_CLAIM)`.

**Inventory authenticity** asks whether the canonical source inventory came from a
trusted source or frozen fixture.

**Inventory scope coverage** asks whether a trusted inventory covers the declared
scope.

**Package versus inventory coverage** asks whether the Package carries the material
objects identified by the inventory.

**Consistency claim** reports `CONSISTENT`, `DECLARED_CONFLICT`, or `UNKNOWN` and is
independent from content coverage.

**Semantic actionability claim** is the Producer's `SEMANTICALLY_READY`, `BLOCKED`, or
`UNKNOWN` claim. It is not current action authorization.

**Continuity evaluation** means an independent frozen Producer-to-Receiver run with
published inputs, outputs, conditions, and hard gates. Packaging success alone is not
a continuity result.

## Receipt and action terms

**Receipt** means the Receiver's structured report bound to the exact root, canonical
state digest, current challenge, Runtime, read set, processing coverage, and selected
actions.

**Verification summary** means the disposable Receipt cache, limited to its defined
members, that is derived from valid result payloads plus required-slot candidate
validation state. It does not create an undeclared security-summary member.

**Processing coverage** means what the Receiver actually processed. It does not
rewrite Package content coverage.

**Continuation status** means `READY` or `BLOCKED` for the selected actions in the
current Receiver run. It is not a global Package trust result.

**Current authorization** means an unexpired result bound to the exact action,
principal, tenant, resource, operation, purpose, constraints, challenge, root, and
state.

**One-response text-only exception** means the narrowly bounded `model_only` rule
that permits one immediate language-only response under enforced tool and side-effect
isolation. It proves no Package or semantic conformance.

## Language and artifact terms

**Authoritative source text** means the preserved original text. Translation,
transliteration, summary, OCR, and model restatement are derived views unless the
user explicitly confirms a parallel text.

**`LocalizedText`** means the shared structure for a material natural-language value,
including language, direction, kind, authority, fidelity, and derivation metadata.

**Protected span** means code, an identifier, path, URL, hash, number, money value,
unit, time, formula, name, legal term, quotation, or user-designated wording that
must not drift across views.

**Material artifact** means a file or non-text object required to reconstruct the
state or perform a selected action. A URL or local absolute path alone is not a
self-contained artifact.

## Capability and Profile terms

**Runtime capability** means an observed ability such as text, attachment,
filesystem, script, language, modality, or isolation support. Capability is not a
Profile or result.

**Profile** means a versioned, composable set of artifact requirements selected by
the Package from the verified release Profile/Feature registry. A required
unsupported Profile causes rejection. A root contains each Profile ID at most once.

**Feature** means a registered core facility, such as detached envelopes, that is
not selected through the root `profiles` array.

**Domain capture guidance** means a `domain-*.md` checklist that influences capture
without defining a wire Profile or adding fields. Release `0.1` domain guides cannot
be selected as Profiles.

**Offline Schema catalog** means the release-locked mapping from every opaque Schema
URN to one bundled local file and its raw byte commitment. It forbids remote Schema
retrieval during VERIFY.

**`must_understand`** means an extension that a Receiver must understand before it
can process the Package. An unknown required value causes rejection.

**T0, T1, T2, and T3** are capability transport modes. They do not change the
semantic record model or upgrade evidence.

**Legacy converter capability** means support for a frozen legacy mapping. It is not
a production Package Profile and not a continuity result.
