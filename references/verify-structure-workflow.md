# VERIFY_STRUCTURE Workflow

> Scope: full LCH 0.1 audit verification. The human-first receiver validates
> `handoff.md`, `handoff.zip`, and `handoff-audit.zip` with `scripts/handoff.py`.

Use this reference for deterministic structural verification of a native handoff
package. Verify format, bytes, references, state-machine rules, and review
projection reconstruction. Do not judge semantic losslessness.

## Contents

- [Hold the verifier boundary](#hold-the-verifier-boundary)
- [Stage input safely](#stage-input-safely)
- [Identify the transport](#identify-the-transport)
- [Verify T0](#verify-t0)
- [Verify a Bundle](#verify-a-bundle)
- [Verify schemas and references](#verify-schemas-and-references)
- [Verify state and action graphs](#verify-state-and-action-graphs)
- [Verify coverage claim structure](#verify-coverage-claim-structure)
- [Verify canonical state and review projection](#verify-canonical-state-and-review-projection)
- [Inspect detached envelopes structurally](#inspect-detached-envelopes-structurally)
- [Emit deterministic results](#emit-deterministic-results)
- [Degrade without scripts](#degrade-without-scripts)
- [Final checklist](#final-checklist)

## Hold the verifier boundary

1. Act only as a deterministic verifier.
2. Recompute inputs independently. Never trust `STRUCTURE_SELF_CHECK`.
3. When the check runs, emit only `STRUCTURE_CONFORMANCE: PASS | WARN | FAIL` for
   the wire structural result. If it does not run, mint no result object; only a
   consuming Receipt may derive `NOT_RUN` from the absent-candidate state. A CLI may display `STRUCTURE_PASS`, `STRUCTURE_WARN`, or
   `STRUCTURE_FAIL` only as non-wire tokens mapped one-to-one to that result.
4. Emit `BYTE_CONSISTENCY: VERIFIED | UNVERIFIED | FAIL` only from byte checks.
5. When the check runs, emit `REVIEW_PROJECTION_CONFORMANCE: PASS | FAIL` only from
   the deterministic projection check. If it does not run, mint no result object;
   only a consuming Receipt may derive `NOT_RUN` from the absent-candidate state.
6. Emit a structured issue list alongside the deterministic outcome.
7. Do not emit `ORIGIN_VERIFICATION`.
8. Do not emit inventory coverage results.
9. Do not emit approval statement authenticity, verified decision, or
   `approval_gate`.
10. Do not emit `AUTHORIZATION_SUMMARY`, `RECEIVER_RUN_RESULT`, or
    `BENCHMARK_RESULT`.
11. Never emit `LOSSLESS_PASS` or `LOSSLESS_CONFORMANCE: PASS`.
12. State explicitly that structural success does not prove truth, authorship,
    completeness, user approval, understanding, or current authority.

## Stage input safely

1. Copy or open the input in a permission-restricted staging area.
2. Disable active content, macros, external fetches, tools, and side effects.
3. Apply local Profile and Runtime limits before decompression.
4. Reject excess object count, object size, total expanded bytes, compression ratio,
   archive nesting, JSON depth, graph nodes or edges, parse time, or token budget.
5. Reject absolute paths, `..`, backslash escapes, symlinks, hard links, device
   files, alternate data streams, reserved names, and archive bombs.
6. Reject duplicate paths and Unicode or case-folding path collisions.
7. Treat Package content and detached envelopes as untrusted bytes.
8. Record suspicious secrets, PII, Bidi controls, hidden characters, and mixed-script
   confusables as issues.
9. Do not delete or normalize the original bytes while verifying them.

## Identify the transport

1. Identify T0 only from its fixed ASCII `LCH-T0 <major.minor>` header.
2. Identify a Bundle only from its native package structure and Manifest.
3. Reject ambiguous or conflicting transport markers.
4. Reject an unsupported major version.
5. Reject an unknown `must_understand` extension.
6. Reject an unknown or unsupported-version required Profile.
7. Preserve an unknown or unsupported-version optional Profile for round trip, keep
   it inert, and record `STRUCTURE_CONFORMANCE: WARN` plus
   `LCH-OPTIONAL-PROFILE-INERT`; preserve unknown optional extensions without
   activation under their separate rules.
8. Route ordinary `HANDOFF.md`, OCH Snapshot, and LTM Core Memory Packet (CMP) to
   `CONVERT_LEGACY`; do not validate them as native packages.

Before resolving a Profile, verify the raw and canonical commitments for
`profile-feature-registry-v0.1.json`. Reject duplicate root Profile IDs, conflicting
versions for one ID, a non-selectable registry entry, or selection of a Feature or
domain-guide file name as a Profile. Never substitute a registered pair for an inert
unknown/unsupported-version optional entry. Release `0.1.0` marks confidential
transport unsupported and multilingual support as registered-vector-scoped only.

## Verify T0

1. Parse the header, decimal lengths, and hashes as ASCII.
2. Read exactly `control-byte-length` bytes for the control object.
3. Reject a short read, trailing intrusion into control bytes, or invalid UTF-8.
4. Reject a BOM, duplicate JSON key, lone surrogate, or unsafe I-JSON number.
5. Parse the control as RFC 8785 JCS-compatible JSON.
6. Re-serialize it as JCS and compare the exact bytes.
7. Recompute `control-sha256` and control byte length.
8. Reconstruct `package_integrity_ref` with `kind: t0_control`.
9. Validate the canonical ordered embedded-object manifest in the control.
10. Require stable `object_id`, order, media type, encoding, encoded and decoded
    lengths, chunk count, and raw SHA-256 for every embedded object.
11. Parse each object by declared length and order.
12. Require RFC 4648 section 5 unpadded base64url.
13. Require fixed 4096-character chunks except the final chunk.
14. Decode each object and recompute its raw length and SHA-256.
15. Reject a missing, extra, reordered, truncated, or duplicate object.
16. Read the exact `LCH-T0-HUMAN-VIEW` byte stream by its committed length.
17. Compare its projection version, length, and raw digest to
    `review_projection_ref` in the control.
18. Parse each `LCH-T0-DETACHED` frame only after the rooted content and view.
19. Validate frame opaque ID, type, byte length, and raw SHA-256.
20. Exclude detached frames from the T0 integrity root.
21. Do not interpret a matching frame hash as envelope authenticity.

## Verify a Bundle

1. Require `HANDOFF.md`, `MANIFEST.json`, `MANIFEST.sha256`, WARM, COLD, and all
   objects declared required by the selected Profiles.
2. Read `MANIFEST.json` as exact UTF-8 bytes.
3. Reject a BOM, final LF, duplicate JSON key, lone surrogate, or unsafe I-JSON
   number.
4. Re-serialize the Manifest using RFC 8785 JCS and require exact byte equality.
5. Require `MANIFEST.sha256` to contain 64 lowercase hexadecimal characters and one
   LF only.
6. Recompute the Manifest digest and byte length.
7. Reconstruct `package_integrity_ref` with `kind: bundle_manifest`.
8. Require every rooted path to be safe, relative, and unique.
9. Require every rooted object to exist.
10. Recompute each object's exact `byte_length` and `sha256_raw` without newline,
    Unicode, BOM, whitespace, or case normalization.
11. Confirm that the object list includes `HANDOFF.md`, WARM, COLD, and artifacts.
12. Confirm that the object list excludes `MANIFEST.json`, `MANIFEST.sha256`, and
    all of `envelopes/`.
13. Match `review_projection_ref` to the rooted `HANDOFF.md` object entry.
14. Treat `envelopes/INDEX.json` as non-authoritative routing data.
15. Reject a derived `HANDOFF.md` package or state summary that conflicts with the
    Manifest and WARM.

## Verify schemas and references

Before using any qualification vector, verify the raw and canonical catalog lock for
`assets/vectors/index.json`, then verify each vector's raw and canonical commitment.
Require exactly the four cataloged vector JSON files and no extra vector JSON; reject
missing, duplicate, extra, uncataloged, or mismatched vectors. Core qualification
uses JCS, review, and derived-digest vectors; multilingual qualification uses only
the language/Unicode vector.

1. Verify the raw and restricted-JCS canonical commitments for
   `assets/registry/schema-catalog-v0.1.json`.
2. Require each catalog ID and path exactly once; verify every mapped local Schema's
   raw length, raw SHA-256, and embedded `$id`.
3. Pre-register every `urn:lch:schema:0.1:<name>` mapping and the built-in JSON
   Schema 2020-12 dialect before resolving any `$ref`.
4. Forbid network, file-URI, or other remote/dynamic Schema retrieval. Fail closed
   on any missing, unlisted, mismatched, or unresolved resource.
5. Validate the root and rooted structured objects against the selected versioned
   Schemas.
6. Require the fixed `$schema` and `$id` values for that release.
7. Require HOT, WARM, and COLD according to the selected Profile.
8. Validate all ASCII wire identifiers without translation.
9. Validate every enum against its owning record type.
10. Validate every timestamp with standard JSON Schema `date-time` and RFC 3339
    semantics. Accept year `0000`, lowercase `t`/`z`, `-00:00`, and lexical second
    `60`; reject invalid calendar dates, hour `24`, minute `60`, second `61`, offset
    hour `24`, and offset minute `60`. Do not infer a real leap event from `:60`.
11. Require globally valid stable IDs where the Schema requires them.
12. Reject duplicate IDs, including duplicate root Profile IDs.
13. Reject dangling object, source, evidence, transition, action, edge, group,
   artifact, omission, and claim references.
14. Require every critical WARM record to reference COLD evidence or an explicit
    omission.
15. Validate byte ranges against the referenced COLD object's exact bytes.
16. Validate raw hashes attached to evidence spans and artifacts.
17. Validate `must_understand`, required Profiles, and Profile versions against the
    verified release registry.
18. Validate `resource_requirements` as measured values, not Receiver limits.
19. Under required SELF_CONTAINED v0.1, conservatively check every artifact Record.
    Require `availability: PRESENT` and one evidence span covering a complete rooted
    object from byte zero through its exact length with matching raw digest. Reject
    `MISSING`, `EXTERNAL_ONLY`, `REDACTED`, partial spans, URLs, and paths. Do not
    pair anonymous omissions to Records by count, order, prose, or invented IDs;
    omissions remain coverage evidence and do not establish self-containment. Fail
    required SELF_CONTAINED for every category `artifact` omission or inventory gap
    whose materiality is BLOCKING or MATERIAL.
20. Under required MULTILINGUAL, keep the Receiver Package-use/actionability gate
    blocked until normalization, source-byte preservation, protected-span, and
    Bidi-control checks have actually inspected the Package, even when the separately
    scoped registry/vector qualification passed.
21. When conversion metadata exists, require `mapping_report`, original input
    preservation, and `source_sha256` references to agree with the rooted source.
22. Do not upgrade a source-declared hash into a verifier result.

## Verify state and action graphs

1. Validate each record's orthogonal state axes by record type.
2. Reject a mutable catch-all status that replaces the required axes.
3. Validate immutable transition events and allowed type-specific transitions.
4. Require each event to reference valid previous heads.
5. Reject event cycles, missing heads, forged causal edges, repeated stream
   sequences, reverse sequences, and illegal merges.
6. Preserve unordered concurrent heads.
7. Reject a unique current projection when unresolved concurrent heads remain.
8. Derive `supersedes` from event reasons and edges.
9. Reject a cached lifecycle or current state that disagrees with event heads.
10. For the resolved Record type, require `from` and `to` to contain only its legal
    axes and values. A single-parent update may use a matching nonempty partial
    `from` and partial `to`. For a multi-parent merge, sort predecessor event IDs by
    UTF-16 order, require `from` to equal the first parent's complete projection,
    and require `to` to include every axis on which any parent differs. Require
    genesis `to` and every resulting head to establish the complete type-specific
    axis set. The graph pseudo-record permits only lifecycle and activates to
    `ACTIVE`.
11. Validate the active `action_graph_revision`, recompute its digest, reject a
    self/duplicate predecessor, and match its activation event and lineage claims.
12. Require each action to reference one `next_action` record.
13. Require `eligibility_projection` to agree with the action event heads.
14. Require unique action, edge, and group IDs and validate every reference.
15. Normalize `A REQUIRES B` as dependency arc `B -> A` and `A BEFORE B` as
    `A -> B`; reject cycles over their union, including mixed-relation cycles.
16. Keep `ENABLES` source-to-target and `EXCLUDES` symmetric; do not treat either as
    a differently directed `REQUIRES` edge.
17. Validate `PARALLEL`, `EXACTLY_ONE`, `AT_LEAST_ONE`, and `ORDERED` groups.
18. Reject self, duplicate, or reverse `EXCLUDES` edges after canonical ordering.
19. Reject stale revisions, dangling actions, and direct double-written state.
20. Validate completion criteria, capability requirements, authorization specs, and
    external-state check references structurally.

## Verify coverage claim structure

1. Treat `content_coverage.claim` as a Producer claim only.
2. For `COMPLETE`, require a scope anchored to original user request references.
3. Require a canonical source inventory and capture boundary.
4. Require a material-exclusion list and omissions list.
5. Require `approval_statement_slot` and the required detached-envelope policy.
6. Apply the claim table in `conformance.md`: `COMPLETE` requires FULL source
   access, FULL_WITHIN_SCOPE raw coverage, FULL or genuinely NOT_APPLICABLE artifact
   coverage, and no BLOCKING/MATERIAL omission or inventory gap. Known material gaps
   require `PARTIAL`; undecidable coverage without a known gap requires `UNKNOWN`.
   Empty omission arrays never override incomplete coverage dimensions.
7. Permit `artifact_coverage: NOT_APPLICABLE` only when scope, inventory, Records,
   and the action graph contain no material artifact requirement; otherwise reject
   it regardless of the overall coverage claim.
8. Reject a material missing item paired with a `COMPLETE` claim.
9. Require `PARTIAL` for known material missing content.
10. Require `UNKNOWN` when the source boundary is unknown and no established
    material gap already requires `PARTIAL`; `PARTIAL` has precedence.
11. Do not require post-seal approval objects to appear in the integrity root.
12. Do not downgrade or upgrade content coverage merely because a detached approval
    envelope is missing.
13. Do not issue inventory authenticity or coverage results from this structural
    check.
14. Keep consistency and semantic actionability separate from coverage.

## Verify canonical state and review projection

1. Build `state_projection_v1` from the specified JSON Pointer inclusion and
   exclusion rules.
2. Include WARM assertions, transition events, action graph, boundaries, coverage,
   omissions, authoritative language objects, and referenced raw hashes.
3. Exclude package ID, creation time, Producer and Runtime metadata, storage paths,
   rendered views, derived translations, signatures, and Receipts.
4. Sort set-like arrays by stable ID.
5. Preserve causal order for ordered event streams.
6. Apply the fixed Unicode version and NFC only to protocol-generated text.
7. Preserve COLD original bytes and include only their raw hashes in the state
   projection.
8. Serialize the projection using RFC 8785 JCS.
9. Recompute `canonical_state_digest` and compare it exactly.
10. Rebuild `review_projection_v1` from verified canonical state.
11. Apply the unique nine-section field-selection table in `protocol-core.md`,
    including original requests, intent endpoint and phase, all active constraints,
    material answered/open questions, the complete action projection, inventory,
    unreadable modalities, conflicts, approval slot, and envelope policy.
12. Use UTF-8, no BOM, LF, fixed headings, fixed section order, stable-ID ordering,
    and causal transition ordering.
13. Apply the versioned required/optional conditions, escaping rules, materiality
    profile, and golden bytes.
14. Reject summary truncation of material content.
15. Compare rebuilt review bytes exactly with T0 HUMAN-VIEW or Bundle `HANDOFF.md`.
16. Return `REVIEW_PROJECTION_CONFORMANCE: FAIL` for any byte mismatch, omitted
    material section, unavailable versioned projection definition, materiality
    mismatch, or incorrect projection reference.
17. Never allow approval verification to pass when this projection result is not
    `PASS`.

## Inspect detached envelopes structurally

1. Keep detached envelopes outside the package integrity root.
2. Validate each envelope's byte length and raw digest before parsing it.
3. Validate opaque ID uniqueness and expected type when a slot applies.
4. Validate that an envelope subject names the same `package_integrity_ref` and
   `canonical_state_digest` when those bindings are required.
5. Reject a duplicate ID, one ID with multiple digests, an unknown required type,
   a slot/type mismatch, or an index that conflicts with actual bytes.
6. Do not call a statement authentic because its structure is valid.
7. Do not call a signature trusted because its encoding is valid.
8. Do not derive approval or authorization from a structurally valid envelope.
9. Emit a structured missing-envelope issue for a required slot. Do not sign a
   `NOT_RUN` or `UNVERIFIED` result for another role; the owning role or Receiver
   derives its own summary. Do not rewrite the root.
10. Confirm that adding, deleting, or reordering detached envelopes does not change
    `package_integrity_ref`.
11. For an approval statement, recompute and compare the rooted review/state,
    `scope_digest`, `material_exclusions_digest`, and `recipient_binding_digest`.
12. For an approval verification, recompute the complete direct
    `approval_statement_digest`, cross-match its repeated root/review/state/scope/
    recipient/nonce fields, and enforce the null-or-valid
    `review_projection_result_ref` rule.
13. Recompute `display_evidence_digest` only when the complete external evidence and
    exact displayed review/response bytes are available. Otherwise report the
    approval candidate `UNVERIFIED` and blocking; do not authenticate it through a
    structural result.

## Emit deterministic results

1. Emit `STRUCTURE_CONFORMANCE: FAIL` for a required Schema, graph, reference,
   path, Profile, or integrity-rule failure.
2. Emit `STRUCTURE_CONFORMANCE: WARN` only when the package remains structurally
   processable and the issue is nonblocking under an activated selected Profile or
   is an unknown/unsupported-version optional Profile preserved inert under the
   release `0.1.0` rule. For the latter, include the
   `LCH-OPTIONAL-PROFILE-INERT` warning and do not activate or interpret the entry.
3. Emit `STRUCTURE_CONFORMANCE: PASS` only after every required structural check
   passes.
4. Emit `BYTE_CONSISTENCY: VERIFIED` only after recomputing the root and every
   required rooted object's bytes.
5. Emit `BYTE_CONSISTENCY: UNVERIFIED` only from a legal deterministic result object
   when verification ran but could not establish coverage over all required bytes.
   When verification did not run, do not mint the object. A consuming Receipt uses
   `NOT_RUN` only when it captured no complete candidate bytes for the slot;
   otherwise it applies candidate validation.
6. Emit `BYTE_CONSISTENCY: FAIL` for a digest, length, canonicalization, or rooted
   object mismatch.
7. Emit `REVIEW_PROJECTION_CONFORMANCE: PASS` only after deterministic rebuild and
   exact byte comparison.
8. When deterministic reconstruction did not run, do not mint a review result
   object. A consuming Receipt uses `REVIEW_PROJECTION_CONFORMANCE: NOT_RUN` only
   when it captured no complete candidate bytes for the slot; otherwise it applies
   candidate validation.
9. Include precise issues without leaking secret values.
10. Keep the result bound to the exact `package_integrity_ref`,
    `canonical_state_digest`, Profile versions, implementation version, and run
    time through the protocol's result object.
11. Return a nonzero process status for structural or byte failure when using the
    deterministic CLI.

## Degrade without scripts

1. Do not pretend that manual or model inspection is deterministic verification.
2. Perform a best-effort safety and readability review only.
3. Report that `VERIFY_STRUCTURE` was not deterministically run.
4. Do not mint a `STRUCTURE_CONFORMANCE` result object or emit its CLI display
   token. A consuming Receipt uses `STRUCTURE_CONFORMANCE: NOT_RUN` only when it
   captured no complete candidate bytes for the slot.
5. Do not mint a `BYTE_CONSISTENCY` result object. A consuming Receipt uses
   `BYTE_CONSISTENCY: NOT_RUN` only when it captured no complete candidate bytes for
   the slot.
6. Do not mint a review result object. A consuming Receipt uses
   `REVIEW_PROJECTION_CONFORMANCE: NOT_RUN` only when it captured no complete
   candidate bytes for the slot. Captured candidates in steps 4 through 6 instead
   follow the Receiver's candidate-validation algorithm.
7. Keep tools and side effects disabled for unverified T0 content.
8. List the exact checks that require a deterministic Runtime.
9. Route the package to `validate_handoff.py` or `verify_handoff.py` when those thin
   entries become available.

## Final checklist

- [ ] Stage the package without executing active content.
- [ ] Identify one native transport and exact protocol version.
- [ ] Apply path, archive, graph, parse, and byte limits first.
- [ ] Recompute the T0 control or Bundle Manifest root.
- [ ] Recompute every required rooted object digest and length.
- [ ] Validate Schemas, IDs, references, transitions, and action graph.
- [ ] Check Producer coverage claims structurally without upgrading them.
- [ ] Recompute `canonical_state_digest`.
- [ ] Rebuild and byte-compare `review_projection_v1`.
- [ ] Keep detached envelope structure separate from issuer trust.
- [ ] Emit only deterministic verifier results.
- [ ] State that structural success does not prove semantic continuity.
