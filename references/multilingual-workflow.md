# Multilingual Workflow

Read this reference when source content, continuation output, or evidence uses more than one language or writing direction.

Treat this file as operational guidance. Keep wire identifiers exactly as defined by the protocol.

## Contents

- [Separate the three fidelity questions](#separate-the-three-fidelity-questions)
- [Preserve protocol text](#preserve-protocol-text)
- [Build the language profile](#build-the-language-profile)
- [Create LocalizedText](#create-localizedtext)
- [Preserve authority](#preserve-authority)
- [Protect non-translatable spans](#protect-non-translatable-spans)
- [Handle Unicode safely](#handle-unicode-safely)
- [Generate multilingual HOT](#generate-multilingual-hot)
- [Receive and report limits](#receive-and-report-limits)
- [Registered qualification scope](#registered-qualification-scope)
- [Bound claims](#bound-claims)

## Separate the three fidelity questions

- Verify byte fidelity with encoding, lengths, and hashes.
- Verify text fidelity with Unicode scalars, source bytes, and direction metadata.
- Evaluate semantic continuity with receipts and independent cross-model tests.

Do not infer semantic continuity from byte or text fidelity.

## Preserve protocol text

- Generate protocol Markdown, JSON, and text manifests as UTF-8 without BOM.
- Use LF for generated protocol text.
- Follow RFC 8259 for JSON.
- Keep keys, enums, IDs, internal paths, and hash names as ASCII wire identifiers.
- Apply NFC only to newly generated protocol text when the selected Profile requires it.
- Never normalize, case-fold, width-fold, transliterate, or rewrite COLD source bytes.
- Store undecodable source as binary and record its encoding.
- Never insert replacement characters silently.

## Build the language profile

- Record each source language with a valid BCP 47 tag.
- Use `und` when the language is unknown.
- Use `zxx` for non-linguistic content.
- Select `selected_continuation_language` from `continuation_language_ranges`.
- Keep `translation_policy: original_authoritative` unless the protocol supplies another allowed value.
- Validate tags with a qualified parser and both release-pinned IANA registries.
- Pin the Unicode and display algorithm versions used by the release.

For release `0.1.0`, first verify `assets/registry/registry-lock.json`, the exact
`iana-language-subtag-registry-2026-08-08.txt` bytes (731799 bytes; SHA-256
`be21e91b6851f750a7b1a687f11209d46ad5a8471d6b10a1efc8d1dac4c8a926`), and the exact
`iana-language-tag-extensions-registry-2014-04-02.txt` bytes (1069 bytes; SHA-256
`fdf7764455c493c245a9b3b5b9cd3938391f0637302c3e943fde86aee652e376`). Then use
RFC 5646 validation with exact redundant-tag lookup before component parsing and
accept only extension singletons registered in the locked extensions registry. A
Schema format or regex check is only a syntax prefilter. If the qualified check is
unavailable, report the language/Profile check as not run or unsupported and do not
issue MULTILINGUAL PASS.

For release `0.1.0`, a qualified claim is limited to the exact cases in
`assets/vectors/language-unicode-v1-001.json`. Passing those cases does not qualify
unseen tags, languages, scripts, transformations, or display behavior.

Do not validate BCP 47 with a simplified regular expression.

## Create `LocalizedText`

- Assign a stable `text_id`.
- Store the exact `value`.
- Set `lang` and explicit `dir: ltr | rtl`.
- Choose an existing `kind`, `authority`, and `fidelity` value.
- Link translations, transliterations, and summaries with `translation_of`.
- Record `translation_method` and `review_status`.
- Keep the canonical assertion separate from source excerpts.
- Link each material assertion to one or more COLD `evidence_spans`.

Do not present a canonical assertion as a verbatim user quote.

## Preserve authority

- Keep the original source authoritative.
- Mark translations, transliterations, summaries, and model restatements as `derived_view`.
- Keep machine translations unreviewed until a valid review occurs.
- Use `user_confirmed_parallel` only after explicit user confirmation.
- Report conflicts between a canonical assertion and a user-confirmed parallel text.
- Block only the actions affected by a material language conflict.

Never let a fluent translation replace or outrank its source.

## Protect non-translatable spans

Preserve these values exactly and place translations beside them:

- code, commands, regular expressions, SQL, and configuration keys;
- paths, URLs, Git refs, API names, hashes, UUIDs, and stable IDs;
- numbers, currencies, units, dates, times, and time zones;
- formulas, names, legal terms, quotations, and user-protected wording.

Record the existing protected-span data: `span_id`, category, original value, COLD object ID, UTF-8 byte offsets, protection policy, and raw hash.

Add an existing typed value for execution-sensitive quantities, money, instants, local dates, time windows, or entities. Preserve the source and create `material_ambiguity` when parsing is not unambiguous.

Do not guess the locale for values such as `01/02`, `1,234`, a currency symbol, a unit, a calendar, or daylight-saving time.

## Handle Unicode safely

- Preserve COLD and protected-span bytes regardless of normalization or display.
- Apply NFC or NFKC only to the derived test values for which the registered vector
  gives an expected result.
- Detect and report the exact Bidi-control code points covered by the registered
  vector without deleting or reordering the source.
- If an implementation independently supports UAX 29 segmentation, split text only
  at extended grapheme-cluster boundaries and record that separate run.
- If an implementation independently supports UAX 9 rendering, render logical-order
  text using that separately versioned and tested implementation.
- If an implementation independently supports UTS 39 checks, report its exact scope
  and version separately.
- Preserve Emoji ZWJ sequences, Hangul Jamo, and combining sequences even when the
  full UAX 29 algorithm did not run.
- Do not assume that words are separated by spaces.
- Store RTL content in logical order.
- Display Bidi controls visibly in HOT and CONTROL surfaces.
- Warn on detected Bidi controls. Do not claim mixed-script or confusable detection
  unless a separately qualified UTS 39 check ran.
- Keep those characters unchanged in COLD.
- Run secret and PII detection on normalized detection copies only.

## Generate multilingual HOT

- Put fixed IDs, enums, coverage states, `ready_action_ids`, and `recommended_action_id` in HOT/CONTROL.
- Put the selected continuation-language rendering in HOT/VIEW.
- Put authoritative source text in HOT/SOURCE.
- Generate one authoritative source view and one continuation view by default.
- Avoid mechanically translating all WARM and COLD content.
- Keep every HOT statement traceable to WARM and COLD.

## Receive and report limits

- Read HOT/CONTROL and HOT/SOURCE before trusting HOT/VIEW.
- Compare negation, modality, actor, object, order, numbers, units, money, dates, and time zones.
- Check that `REJECTED`, `FAILED`, and `SUPERSEDED` did not drift.
- Check that uncertainty did not become certainty.
- Check every protected span.
- Preserve unreadable authoritative content in the package.
- Set `processing_status: LANGUAGE_LIMITED` when the target model cannot handle the authoritative language reliably.
- Set `continuation_status: BLOCKED` when the language limitation blocks a selected action.

Do not change package `content_coverage` merely because the Receiver has a language limitation.

## Registered qualification scope

`urn:lch:profile:multilingual` version `0.1.0` is
`QUALIFIED_SUBSET`. Its registered vector covers:

- exact release-lock date, size, and raw hash verification;
- the listed RFC 5646 registered, case-canonicalization, exact redundant,
  deprecated/preferred, grandfathered, registered-extension, unregistered-extension,
  private-use, unknown, ordering, and duplicate cases;
- extlang Prefix as mandatory, variant Prefix as advisory, and registered extension
  sequences in canonical singleton order;
- the listed Unicode 15.1.0 NFC-versus-NFKC cases;
- exact preservation of the listed source bytes and protected spans;
- code-point-presence detection for the listed Bidi controls.

The vector records `UAX9`, `UAX29`, and `UTS39` as `NOT_RUN`. Passing it MUST NOT be
reported as full conformance to any of those algorithms.

The fixture operations do not establish that normalization, protected-span
preservation, or Bidi-control scanning ran over the received Package. Those three
Package-content checks are separately reported and remain `NOT_RUN` unless the
Receiver actually performs them on the authoritative Package bytes.

For a Package selecting MULTILINGUAL with `required: true`, vector PASS remains the
registry's scoped qualification and does not cover its explicitly excluded Package-
content claims. The Receiver must separately inspect the actual Package for
generated-text NFC, authoritative-source-byte preservation, protected spans, and
Bidi controls. A check may pass an empty set only after inspection establishes that
it is empty. If any applicable check remains `NOT_RUN`, record the language
limitation and issue and keep every action requiring multilingual Package processing
blocked; do not generalize the scoped vector PASS.

## Bound claims

Claim structural compatibility for valid Unicode only within the protocol rules. Claim semantic validation only for model pairs, language pairs, domains, versions, and test conditions supported by published evidence.

Do not claim universal multilingual losslessness, full RFC 5646 coverage beyond the
registered cases, complete UAX 9/UAX 29/UTS 39 conformance, or current verification
from this workflow alone.
