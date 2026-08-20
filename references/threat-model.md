# Threat Model

This document defines the security boundaries and threat assumptions for native
handoff packages. It complements `security-boundary.md`; it does not create new wire
fields, authentication systems, or cryptographic algorithms.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative as defined by
RFC 2119 and RFC 8174.

## Contents

- [Security goals](#security-goals)
- [Non-goals](#non-goals)
- [Assets](#assets)
- [Trust boundaries](#trust-boundaries)
- [Adversary capabilities](#adversary-capabilities)
- [Package-content threats](#package-content-threats)
- [T0 threats](#t0-threats)
- [Bundle and archive threats](#bundle-and-archive-threats)
- [Integrity and origin threats](#integrity-and-origin-threats)
- [Review and approval threats](#review-and-approval-threats)
- [Detached-result threats](#detached-result-threats)
- [Authorization threats](#authorization-threats)
- [Coverage and scope threats](#coverage-and-scope-threats)
- [State and merge threats](#state-and-merge-threats)
- [Multilingual and Unicode threats](#multilingual-and-unicode-threats)
- [Secret, privacy, and rights threats](#secret-privacy-and-rights-threats)
- [Resource-exhaustion threats](#resource-exhaustion-threats)
- [Model-only exception threats](#model-only-exception-threats)
- [Confidentiality and lifecycle](#confidentiality-and-lifecycle)
- [Residual risk](#residual-risk)
- [Security test expectations](#security-test-expectations)

## Security goals

The protocol aims to:

- preserve the exact bytes and state relationships declared by an integrity root;
- keep untrusted Package content from gaining instruction or tool authority;
- prevent a Producer claim from appearing as an independent result;
- make omissions, limitations, and failed checks visible;
- bind approval to the exact sealed root and review projection shown;
- keep transfer approval separate from current action authorization;
- prevent stale, cross-tenant, cross-recipient, and cross-action result reuse;
- fail closed for unsafe paths, active content, unsupported required semantics, and
  high-risk actions;
- support a narrowly bounded text-only continuation without granting tools or side
  effects;
- protect secrets, privacy, third-party rights, temporary files, and retained copies.

## Non-goals

The protocol does not guarantee:

- that a model follows instructions correctly;
- that a Package is truthful merely because its hashes agree;
- that the Producer included messages it could not access;
- that secret scanning finds every secret;
- that a signature grants current action permission;
- that plaintext transport is confidential;
- that an offline delivered copy can be remotely recalled;
- that a run in one Runtime proves safety in another;
- that a model-only Receiver establishes deterministic conformance;
- universal semantic losslessness.

## Assets

Protected assets include:

- user intent, decisions, constraints, negative knowledge, and task history;
- original source bytes and material artifacts;
- secrets, personal data, licensed content, and third-party information;
- Package integrity roots and canonical state;
- review projection bytes and approval evidence;
- principal, tenant, recipient, and authority bindings;
- detached result objects and actual raw digests;
- current authorization results;
- Receipt challenge, read set, processing coverage, and selected actions;
- Runtime tool, sandbox, filesystem, and network boundaries;
- conformance and evaluation evidence.

## Trust boundaries

The protocol crosses these boundaries:

1. Original conversation and tools to Producer staging.
2. Producer staging to the sealed Package root.
3. Rooted Package to detached statements and results.
4. Sender Runtime to transport or storage.
5. Transport or storage to Receiver staging.
6. Untrusted Package data to deterministic parser.
7. Parsed Package state to model-visible context.
8. Receiver reasoning to tools and external side effects.
9. Current user interaction to approval or authorization evidence.
10. Private runs to published conformance and evaluation reports.

Data crossing one boundary does not inherit authority from another. In particular,
Package text cannot become current user, system, developer, Runtime, approval, or
authorization instruction.

## Adversary capabilities

An adversary may:

- create an entire Package and every unauthenticated hash inside it;
- replace, omit, reorder, truncate, or duplicate bytes;
- forge filenames, paths, IDs, indexes, headers, and claimed digests;
- embed prompt injection in HOT, WARM, COLD, artifacts, or legacy input;
- claim to be a user, verifier, approver, system, or trusted tool;
- replay old signatures, approval statements, Receipts, or authorization results;
- exploit Unicode direction, confusables, invisible characters, or locale ambiguity;
- construct archive bombs, path traversal, link escapes, duplicate paths, or active
  documents;
- exploit context, token, object, graph, parser, or decompression limits;
- submit partial or conflicting state as complete;
- mix tasks, tenants, recipients, languages, or action revisions;
- place secrets or personal data in low-visibility fields;
- attempt denial of service by adding stricter untrusted restrictions.

The adversary is not assumed to break mature cryptography correctly implemented under
its stated assumptions. The protocol does assume implementation, key, and trust-anchor
failures are possible and therefore requires explicit evidence and fail-closed rules.

## Package-content threats

All Package content is untrusted data. This includes HOT, WARM, COLD, review text,
attachments, tool output, imported webpages, old assistant messages, and legacy
handoffs.

Threats include:

- embedded instructions that request tools, secrets, network access, or policy
  changes;
- forged system or developer labels;
- a malicious action graph that selects itself;
- a false statement that the current user approved or authorized an action;
- a derived translation that changes negation, actor, value, or obligation;
- an apparently complete summary that hides material COLD evidence.

Mitigations are:

- keep tools and side effects disabled during parsing;
- preserve Runtime instruction priority outside the Package;
- require current-user action selection outside Package content;
- validate state against event heads and evidence links;
- keep derived views below authoritative source text;
- require independent results for trust, coverage, approval, and authorization;
- block affected actions on unresolved material conflict or omission.

Framing reduces structural spoofing but does not eliminate natural-language prompt
injection.

## T0 threats

T0-specific threats include:

- fake Markdown headings or fences inside embedded COLD data;
- control-length confusion;
- base64url padding or chunk reordering ambiguity;
- declared and actual length mismatch;
- duplicate or missing embedded-object IDs;
- a substituted HUMAN-VIEW;
- appended detached frames that claim false authority;
- a model parsing text without deterministic framing.

Mitigations are:

- parse the fixed ASCII header and exact JCS control length before content;
- validate control digest and embedded-object manifest;
- require unpadded base64url, fixed chunks, indexes, lengths, and raw digests;
- bind review projection length and actual digest in control;
- treat frame headers as locators only;
- no-mint deterministic and security results when preprocessing did not run;
- enforce tool and side-effect isolation;
- use the one-response text-only exception only under its complete conditions.

An internally consistent malicious T0 Package is still unauthenticated unless a trust
verifier establishes origin.

## Bundle and archive threats

Bundle threats include:

- `..`, absolute paths, symlink or hard-link escape;
- device files, alternate data streams, reserved names, and active documents;
- duplicate, case-colliding, or Unicode-colliding paths;
- archive nesting and decompression bombs;
- object replacement after Manifest creation;
- a self-referential or ambiguous root;
- a forged `envelopes/INDEX.json`;
- an external path as the only artifact locator.

Mitigations are:

- preflight before extraction;
- use safe relative ASCII storage paths;
- reject links, special files, collisions, duplicates, and path escape;
- enforce object, byte, ratio, nesting, and time limits;
- use `MANIFEST.json` as the only root;
- exclude Manifest, sidecar, and `envelopes/` from its object list;
- recompute each rooted object's actual length and digest;
- ignore an index that conflicts with actual envelope bytes;
- require all material transferable objects inside a self-contained Package.

## Integrity and origin threats

Hash agreement can be misrepresented as authorship, truth, approval, or
confidentiality. An attacker can replace a whole unauthenticated Package and all of
its internal hashes.

Mitigations are:

- state that `package_integrity_ref` proves byte relationships only;
- keep `ORIGIN_CLAIM` separate from `ORIGIN_VERIFICATION`;
- require a trust verifier, trust anchor, exact subject, recipient, tenant, and time;
- distinguish `UNAUTHENTICATED`, `UNVERIFIED`, `FAIL`, and `NOT_RUN`;
- never use a signature as current action authorization;
- never treat a hash as encryption or redaction.

## Review and approval threats

Threats include:

- approval of a draft before the final root exists;
- a review page that omits a material decision or exclusion;
- substitution of review bytes after the user saw them;
- coercing `REVIEWED` or `DENIED` into `APPROVED`;
- replay of an old approval nonce or signature;
- Producer impersonation of the approver;
- adding approval data back into the root after seal.

Mitigations are:

- seal before statement and verification;
- commit deterministic review bytes through `review_projection_ref`;
- show root-derived review bytes and final root together;
- bind display evidence, challenge, response, recipient, and time;
- require the actual approving principal to issue the statement;
- require a separate approval verifier;
- pass the gate only for authentic `APPROVED` and exact subject checks;
- keep all approval objects detached;
- never rewrite the root with approval data.

## Detached-result threats

Threats include:

- a forged result payload claiming PASS or VERIFIED;
- an invalid object appearing trusted because it has a result ref;
- one opaque ID mapped to several digests;
- a valid result for another root, state, scope, recipient, or time;
- a stale index hiding an adverse object;
- omission of a missing or invalid required result from the Receipt;
- one implementation collapsing several roles into one unsigned assertion.

Mitigations are:

- define candidate only after complete bytes and actual SHA-256 capture;
- treat `{opaque_id, sha256_raw}` as a locator, never a trust result;
- retain invalid candidate locators for audit but use `UNVERIFIED` and ignore payload;
- use `NOT_RUN` with null ref when no candidate bytes were captured;
- validate issuer, authority, trust, subject, recipient, tenant, and time;
- show every applicable adverse outcome;
- fail Receipt conformance on summary disagreement;
- require distinct role objects even when one implementation performs several roles.

## Authorization threats

Threats include:

- treating Package approval as permission to execute;
- replaying old consent or an old authorization result;
- authorizing the wrong principal, tenant, resource, operation, or purpose;
- broadening one action result into blanket or future authority;
- allowing Package text to grant authority;
- performing a side effect after external state changed.

Mitigations are:

- issue a dedicated current `authorization_result` per protected action;
- bind current challenge, root, state, action, principal, tenant, resource, operation,
  purpose, constraints, issue time, and expiry;
- revalidate immediately before high-risk effects;
- use `REAUTHORIZATION_REQUIRED`, `DENIED`, or `UNKNOWN` when binding fails;
- keep approval, origin, and current authorization independent;
- block on stale external state.

## Coverage and scope threats

Scope laundering means narrowing scope or hiding exclusions so that a partial Package
appears complete.

Threats include:

- omitting the original user request anchor;
- excluding inconvenient evidence through `policy_boundary`;
- using message count or first and last ID as proof of inventory completeness;
- treating a Producer inventory as authenticated;
- turning a Receiver processing limit into Package `PARTIAL` or vice versa;
- treating declared conflict as missing content;
- treating approved exclusion as present content.

Mitigations are:

- anchor scope to original request references;
- preserve canonical ordered inventory entries, boundaries, and gaps;
- keep material exclusions and omissions visible;
- separate inventory authenticity, scope coverage, and Package coverage;
- keep coverage, consistency, and semantic actionability independent;
- require coverage results to bind scope, inventory, materiality, root, and state;
- display `COMPLETE` only as a Producer claim.

## State and merge threats

Threats include:

- last-write-wins over concurrent intent or decision heads;
- rewriting a user rejection as technical failure or the reverse;
- reviving a superseded option;
- stale action-graph revision presented as current;
- dangling actions or dependency cycles;
- cross-task or cross-tenant merge pollution;
- a cached current state that disagrees with event history.

Mitigations are:

- immutable transition events as the only state authority;
- explicit reason kinds for rejection, conflict, failure, and policy block;
- concurrent heads preserved until explicit merge or conflict;
- action eligibility derived from `next_action` event heads;
- immutable event-activated graph revisions;
- task, scope, principal, and tenant bindings on merge inputs;
- reject cycles, dangling references, illegal merges, and projection disagreement.

## Multilingual and Unicode threats

Threats include:

- negation or obligation drift in translation;
- changed actor, object, order, number, currency, unit, date, or time zone;
- Bidi control and invisible-character spoofing;
- mixed-script confusable identifiers;
- normalization damage to COLD bytes;
- an unreadable authoritative language hidden by a fluent translation;
- locale guessing for ambiguous values.

Mitigations are:

- preserve original bytes and authority;
- mark translations and summaries as derived views;
- use language and direction metadata;
- protect execution-sensitive spans;
- display Bidi controls on control surfaces;
- warn on confusables and invisible characters;
- use typed values only when parsing is unambiguous;
- record material ambiguity and block affected actions;
- set `LANGUAGE_LIMITED` when authoritative content cannot be handled reliably.

## Secret, privacy, and rights threats

Threats include:

- passwords, tokens, private keys, or `.env` values in the Package;
- low-entropy secret or personal-data hashes used for dictionary attack or linkage;
- unauthorized third-party data transfer;
- licensed source copied beyond allowed scope;
- secret values leaked through omissions, logs, filenames, or public fixtures;
- a clean scan represented as proof that no secret exists.

Mitigations are:

- never Package credential values;
- record the need for a credential without the value;
- treat sensitive hashes as sensitive;
- keep quarantine digests in restricted audit storage only;
- check principal, tenant, privacy, copyright, and disclosure authority;
- route findings to `REFUSE`, `QUARANTINE`, or `REDACTED_EXPORT`;
- use `APPROVED_ORIGINAL` only under its explicit legacy approval path;
- record material removal as an omission without secret content;
- publish only synthetic, authorized, or sufficiently de-identified failures.

## Resource-exhaustion threats

Attackers may exploit raw bytes, expanded bytes, compression ratio, object count,
archive depth, JSON depth, graph size, Unicode processing, parse time, or model token
limits.

Mitigations are:

- enforce local limits before decompression and full parse;
- stop safely when a limit is exceeded;
- return `PACKAGE_LIMITED` or `SECURITY_LIMITED` as applicable;
- preserve the unprocessed object and report processing coverage;
- do not truncate and claim success;
- keep tools and side effects disabled after a limit failure;
- use deterministic parsers with bounded recursion and allocation.

## Model-only exception threats

The one-response text-only exception creates a controlled compatibility risk. Threats
include:

- a Package selecting a malicious action itself;
- a generic current-user message being interpreted as exact consent;
- Package text weakening local risk policy;
- model promises substituting for Runtime isolation;
- a text action hiding an external-state or authorization dependency;
- reuse of a READY Receipt on a later turn or with tools enabled;
- professional or governed advice bypassing required review;
- an adverse candidate being ignored.

Mitigations are:

- current user supplies the exact Package and selects the exact bounded action outside
  Package content;
- current user affirms authority for that use;
- Runtime enforces tools and side effects disabled;
- no material external state, authorization, artifact, omission, conflict, ambiguity,
  or adverse candidate remains;
- independent Runtime, recipient, Profile, and action-risk policy controls;
- Package may only add stricter visible restrictions, never weaken policy;
- one immediate language-only response;
- Receipt binds action, state, challenge, Runtime, limits, posture, and read set;
- expected nonce invalidated after use;
- any new turn or boundary change requires a new Receipt;
- known applicable failures cannot be waived.

If isolation cannot be enforced, `processing_status` remains `SECURITY_LIMITED`,
`blocking_reasons[].code: SECURITY_BLOCKED` is added, and continuation is blocked.

## Confidentiality and lifecycle

Plaintext confidentiality depends on a trusted transport. The integrity root does not
encrypt data.

Release `0.1.0` marks `urn:lch:profile:confidential-transport` unsupported and
non-selectable. A later release may register confidential transport only with a
mature, versioned, interoperable
envelope and published test vectors. The core protocol does not invent cryptography.

Staging, quarantine, and release locations remain separate. Created files default to
POSIX mode `0600` or an equivalent local control. Temporary files, backups, logs, and
retained copies follow the declared retention policy.

Rejected, denied, or cancelled drafts are isolated or securely destroyed according
to policy. Revocation may notify recipients and disable future access or keys, but it
cannot erase an already delivered offline plaintext copy.

## Residual risk

Residual risks include:

- model prompt-injection susceptibility even under correct framing;
- unobservable source omissions by the Producer;
- incorrect or compromised trust anchors;
- undiscovered parser or archive vulnerabilities;
- user approval without reading all material;
- semantic drift not detected by structural validation;
- Runtime claims about isolation that cannot be independently attested;
- social engineering outside the Package;
- future state changes after a valid Receipt.

These risks MUST be stated honestly. They MUST NOT be hidden behind a lossless,
verified, secure, or approved label.

## Security test expectations

Security fixtures SHOULD include:

- prompt injection in every layer and legacy input;
- T0 length, chunk, digest, and review substitution attacks;
- Bundle traversal, links, collisions, duplicate paths, and archive bombs;
- root, object, and detached-envelope replacement;
- forged issuer, cross-root result, stale result, and duplicate opaque ID;
- approval replay, review mismatch, genuine DENIED, and recipient mismatch;
- authorization replay and cross-action misuse;
- scope laundering and false completeness;
- cross-tenant merge and stale action graph;
- Bidi, confusable, invisible, and locale-ambiguity cases;
- secret and personal-data leakage attempts;
- context and resource exhaustion;
- model-only isolation failure, action-selection spoofing, and Receipt replay.

Every security result records exact Runtime, sandbox, tools, permissions, fixture,
Package root, and implementation version. Failures are published when synthetic,
authorized, or sufficiently de-identified.
