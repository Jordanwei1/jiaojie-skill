# Coding domain guidance

Use this reference for software implementation, debugging, maintenance, review, or release work.
Apply the core record model unchanged; this file adds capture priorities and checks, not wire fields.

## Capture priorities

- Identify each repository, module, branch, base revision, active worktree, and intended target revision.
- Capture staged, unstaged, untracked, generated, and ignored changes when they affect continuation.
- Record changed files as artifacts and connect each material change to its intent, decision, or attempt.
- Preserve exact errors, reproduction steps, observed outputs, and the conditions under which they occurred.
- Distinguish tests that passed, failed, were skipped, or were not run; include commands only as evidence.
- Capture runtime, toolchain, dependency, lockfile, schema, migration, and feature-flag assumptions.
- Preserve active architecture decisions, rejected approaches, failed fixes, and why each state changed.
- Record unresolved defects, review comments, merge conflicts, temporary workarounds, and known regressions.
- Capture completion criteria for implementation, review, testing, migration, rollout, and rollback actions.
- Preserve required code, patches, fixtures, logs, screenshots, diagrams, or build outputs as artifacts.

## Principals, time, and external state

- Attribute changes and decisions to the human, agent, reviewer, tool, or external author that produced them.
- Keep concurrent human or agent branches explicit; never collapse them by last-write-wins ordering.
- Record when repository, CI, registry, deployment, issue-tracker, or review state was last observed.
- Treat remote branches, pull requests, packages, services, credentials, and deployed behavior as external state.
- Require freshness checks before relying on mutable CI status, dependency versions, deployments, or incidents.
- Treat binary builds, UI screenshots, architecture diagrams, and profiler traces as non-text artifacts.

## Action and authorization checks

- Keep implementation, testing, review, migration, deployment, and rollback as distinct action nodes.
- Express build or test prerequisites through the existing action graph instead of prose ordering.
- Mark an action blocked when a required repository, environment, dependency, or artifact is unavailable.
- Do not infer permission to push, merge, deploy, publish, delete, rotate secrets, or modify production.
- Require current authorization and external-state revalidation for every side-effecting repository or service action.
- Never place secret values, private keys, tokens, or environment-file contents in the handoff package.

## Handoff checks

- Verify that the next receiver can reconstruct the exact stop point without the source machine.
- Verify that required files are embedded or honestly marked missing, not located only by an absolute path.
- Verify that active and rejected approaches cannot be confused after import.
- Verify that test claims cite actual output and are not upgraded from assumption to observation.
- Verify that dirty-worktree and uncommitted-change state is explicit when material.
- Verify that generated or binary artifacts include provenance, freshness, and raw-object references.
- Verify that stale remote state triggers revalidation rather than reopening settled design decisions.
- Block continuation when unresolved conflicts could change the selected patch or release action.
