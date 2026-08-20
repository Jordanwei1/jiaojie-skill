# Security Policy

## Supported versions

Security fixes target the latest tagged release and the current `main` branch. Pre-release versions may change format while a fix is being prepared.

## Report privately

Do not open a public Issue for an exploitable vulnerability or a report containing secrets, private handoffs, malicious archives, or personal data.

Use GitHub's **Security → Report a vulnerability** private reporting flow for this repository. Include:

- affected version or commit;
- exact command and minimal synthetic input;
- expected and actual behavior;
- security impact and whether exploitation requires user action;
- any suggested mitigation.

If private vulnerability reporting is unavailable, open a public Issue containing only the words “Security contact requested”; do not attach the exploit or sensitive material.

## Scope priorities

High-priority areas include archive traversal, symlink escape, decompression limits, Manifest substitution, hash confusion, Unicode controls, Prompt Injection boundary bypass, secret leakage, replay, unsafe legacy conversion, and transfer of historical authority.

## Handling

The maintainer will acknowledge a complete report when reviewed, reproduce it with synthetic data, prepare a fix and regression test, and coordinate disclosure. No response-time guarantee is made for this volunteer project.

## Safe research

Use synthetic data and local test directories. Do not test against other people's repositories, accounts, production systems, or private handoff packages without explicit authorization.
