# Runtime Capabilities

> The T0-T3 modes below describe the full LCH 0.1 audit protocol. They no longer
> choose the ordinary product format. For ordinary work, use
> `simple-workflow.md`: Markdown by default, ZIP only for required files, and an
> audit ZIP only when proof must travel.

Read this reference before `EXPORT`, `RECEIVE`, `VERIFY_STRUCTURE`, or `CONVERT_LEGACY` when runtime support is uncertain.

Treat this file as operational guidance. Do not derive new wire fields from its headings or checklists.

## Contents

- [Detect capabilities](#detect-capabilities)
- [Choose the transport mode](#choose-the-transport-mode)
- [Operate in T0](#operate-in-t0)
- [Operate in T1](#operate-in-t1)
- [Operate in T2](#operate-in-t2)
- [Operate in T3](#operate-in-t3)
- [Apply capability degradation](#apply-capability-degradation)
- [Keep profiles and results separate](#keep-profiles-and-results-separate)

## Detect capabilities

Inspect the current runtime. Do not infer capabilities from a product name.

- Check whether the runtime can read and write plain text.
- Check whether it can upload and open attachments.
- Check whether it can access a filesystem safely.
- Check whether it can run the Skill and deterministic scripts.
- Check whether it can process every required modality.
- Check whether it can process the authoritative source language.
- Check available context, object, archive, and token limits.
- Check whether tools and side effects can remain disabled during inspection.
- Record the capabilities actually used for this run.

Do not change semantic fields because a runtime is weaker or stronger.

## Choose the transport mode

Use the lowest mode that preserves every material object and state record.

| Mode | Available runtime support | Use |
| --- | --- | --- |
| T0 | Text only | One self-describing Markdown package |
| T1 | Attachments | One intact Bundle attachment, normally ZIP |
| T2 | Filesystem | A structured directory or ZIP Bundle |
| T3 | Scripts and Skill | Deterministic packing, hashing, validation, and conversion |

Do not label a mode as better evidence. A transport mode is not a verification result.

## Operate in T0

- Use the fixed `LCH-T0 <major.minor>` framing.
- Preserve the exact JCS control bytes and declared byte length.
- Preserve the canonical ordered embedded-object manifest.
- Encode embedded binary objects with unpadded RFC 4648 Section 5 base64url.
- Use fixed 4096-character chunks, explicit chunk indexes, lengths, and raw SHA-256.
- Keep the matching `LCH-T0-HUMAN-VIEW` review projection.
- Keep all material text and small artifacts inside the package.
- Refuse silent truncation when the package exceeds the target context.

When receiving T0 without a deterministic preprocessor, do not mint byte or security
result objects. Require the Receiver Receipt to show `BYTE_CONSISTENCY: NOT_RUN`, leave
`verification_result_refs.security_run` null, add an issue that security verification
did not run, and set `processing_status: SECURITY_LIMITED`. A Runtime-enforced text-only
posture may use the core one-response exception; inability to enforce isolation sets
`blocking_reasons[].code: SECURITY_BLOCKED` while `processing_status` remains
`SECURITY_LIMITED`. Keep tools and side effects disabled while reading. In `EXPORT`, no
deterministic preprocessor means no sealed native T0: produce only an explicit unverified
draft and no Receipt. In standalone `VERIFY_STRUCTURE`, report that the check did not run
without minting its result or a Receiver Receipt.

## Operate in T1

- Carry the same native Bundle used by T2 as one intact attachment, normally a ZIP.
- Keep `MANIFEST.json` as the only integrity root and preserve the complete logical object layout.
- Require every material object to be committed by the Manifest.
- Reject or ignore loose, unrooted attachments.
- Fall back to T0 when the runtime cannot preserve or reopen the intact Bundle.
- Verify that the runtime can open the Bundle and each required object before claiming it was processed.
- Preserve original bytes even when a derived text view exists.
- Set `processing_status` to `MODALITY_LIMITED` when a required attachment cannot be read.

Do not replace an unread image, audio file, video, or binary document with its summary.

## Operate in T2

- Use the Bundle layout and treat `MANIFEST.json` as its only integrity root.
- Check resource limits, paths, links, collisions, and archive depth before extraction.
- Recompute object hashes and `canonical_state_digest` when deterministic support exists.
- Treat `HANDOFF.md` as a derived view.
- Fail the derived view when its package or state summary conflicts with the Manifest.
- Keep `envelopes/` outside the Manifest root.

Do not use a local absolute path as the only location for a required object.

## Operate in T3

- Use the installed Skill only as workflow guidance.
- Use deterministic scripts for packing, hashing, validation, and frozen legacy mappings.
- Pin required canonicalization, Unicode, and registry versions.
- Validate before committing output.
- Keep independent result roles separate from the Producer.

Do not let script availability upgrade `CONTENT_COVERAGE_CLAIM`, origin, approval, or continuity results.

## Apply capability degradation

- Use `PARTIAL` when a known material source or object is missing.
- Use `UNKNOWN` when the source boundary itself is unknown.
- Keep package `content_coverage` unchanged when only the Receiver is limited.
- Lower Receipt `processing_coverage` when the Receiver cannot process required content.
- Use `LANGUAGE_LIMITED` when the authoritative language cannot be handled reliably.
- Use `MODALITY_LIMITED` when a required modality cannot be read.
- Use `PACKAGE_LIMITED` when local resource limits block safe processing.
- Use `SECURITY_LIMITED` with a precise issue when a required security scan did not run but the Runtime still enforces text-only isolation.
- Add `blocking_reasons[].code: SECURITY_BLOCKED` and block continuation when the required isolation posture itself cannot be enforced; keep `processing_status: SECURITY_LIMITED`.
- Set `continuation_status: BLOCKED` when a selected action lacks a required capability.

Never delete core fields, rewrite state, or turn a failure into success to fit the platform.

## Keep profiles and results separate

- Resolve artifact Profiles from the verified release registry. Release `0.1.0`
  supports core Markdown and self-contained, qualifies multilingual only for its
  registered vector scope, and marks confidential transport unsupported and
  non-selectable.
- Treat `LEGACY_CONVERTER` as an implementation capability.
- Treat `RECEIPT_CONFORMANCE` as a run result.
- Treat Profile conformance as a prerequisite, not a Continuity Eval result.

Do not claim that any runtime, Profile, model, language pair, or transport mode is currently verified unless an applicable independent result object and published evidence say so.
