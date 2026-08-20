# Jiaojie evaluation

This directory defines how semantic continuity evidence is produced and admitted. It intentionally contains no fabricated model or Runtime result.

## Three separate questions

1. **Producer extraction** — did the handoff preserve the gold state from the source context?
2. **Receiver continuity** — did a context-isolated Receiver recover the correct state and next action?
3. **End to end** — does the full Producer → artifact → Receiver path pass the scorecard and every hard gate?

Passing JSON Schema, hashes, or archive checks proves only deterministic structure. It does not prove source truth, current authority, semantic continuity, or cross-model compatibility.

## Required run artifacts

Every admitted run directory must contain:

- `run.json` — exact model/Runtime/language roles, date, capabilities, sampling policy and hashes;
- `input/` — source context or case reference and exact prompts;
- `artifact/` — the handoff given to the Receiver;
- `output/` — raw Producer and Receiver responses;
- `score.json` — automatic and human judgments, hard gates and limitations;
- `README.md` — a human-readable reproduction command and result.

Secrets and private production conversations are forbidden. Use public synthetic cases unless every right and privacy boundary is documented.

## Status levels

| Status | Meaning |
| --- | --- |
| `NOT_RUN` | target exists in the plan but has no admitted evidence |
| `RAW_CAPTURED` | raw run exists but has not passed admission and scoring |
| `PROJECT_VERIFIED` | project-owned run passed the contract |
| `INDEPENDENTLY_REPRODUCED` | unrelated third party reproduced the result |
| `FAILED` | admitted run failed one or more requirements |
| `DISPUTED` | valid evidence conflicts and remains unresolved |

Success and failure use the same retention rule. Repeated attempts are all counted; do not select only the best sample.

See [`continuity-scorecard.md`](continuity-scorecard.md), [`run-template.json`](run-template.json), and [`compatibility-matrix.json`](compatibility-matrix.json).
