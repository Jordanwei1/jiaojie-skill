# Governance

Jiaojie uses founder-led governance during the `0.x` phase so the protocol can move quickly without pretending that early experiments are stable standards.

## Roles

- **Maintainer**: merges changes, manages releases and security responses;
- **Contributor**: submits code, cases, evaluation evidence or review;
- **Reviewer**: performs technical, language, security or evaluation review;
- **Independent reproducer**: reruns a published result without participating in its production.

One person may hold several roles in the project, but may not count as both producer and independent evaluator for the same run.

## Change classes

1. **Patch**: clarifications and compatible fixes;
2. **Feature**: additive optional fields, Profiles and tools;
3. **Protocol change**: required fields, semantics, canonicalization, status or security behavior;
4. **Claim change**: compatibility or verification status.

Protocol and claim changes require an Issue proposal, tests, migration impact, security analysis and explicit maintainer approval. Claim changes additionally require linked evidence.

## Compatibility

The `0.x` line may make breaking changes, but every breaking change must be listed in `CHANGELOG.md` with a migration path. A stable `1.0` requires published conformance tests, at least two independent implementations and community review.

## Evidence independence

Producer, Receiver, automatic scorer, human reviewer and independent reproducer are recorded separately. A project-owned result may become `PROJECT_VERIFIED`; only an unrelated third party can create `COMMUNITY_VERIFIED` evidence.

## Decisions

Technical discussion happens publicly when safe. The maintainer records accepted decisions in the relevant Issue or changelog. Security decisions may remain private until coordinated disclosure.
