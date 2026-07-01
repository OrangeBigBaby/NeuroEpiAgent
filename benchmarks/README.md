# Benchmarks

Ten blinded benchmark tasks covering **stroke**, **TBI**, and **tumor** questions,
plus the NHANES feasibility limits the agent must respect.

## What these tasks test

These are **planning/feasibility** benchmarks, not clinical-effect benchmarks.
Each task pins the *expected deterministic behaviour* of the MVP — which
database it should route to, whether the question is feasible at all, and which
guardrail is in play. They deliberately mix:

- feasible NHANES questions (route → NHANES, pass design checks),
- infeasible NHANES questions (refuse / caveat — e.g. surgery, histology),
- questions whose only plausible source is a **planned** adapter (GBD/SEER/CHARLS),
  which the MVP must mark infeasible rather than silently answer.

## File

- `tasks.example.yaml` — 10 tasks across stroke/TBI/tumor + cross-cutting.

## Running the routing tasks

```powershell
# per task
neurosurg-epi route --question "Does bariatric surgery reduce stroke recurrence?"
```

The expected outcome for that task is `feasible: false` with a caveat that NHANES
has no procedure data — see `expected_reason` in the YAML.

## What the MVP must NOT do on any task

- Invent a NHANES variable code or TBI item that does not exist.
- Route a tumor-histology question to NHANES as feasible.
- Treat GBD/SEER/CHARLS as active data sources.
- Emit a causal claim ("surgery reduces recurrence") without a guardrail error.

## Out of scope here

Statistical-effect benchmarks (do pooled estimates reproduce?) require a real
analysis harness and raw NHANES data, which is intentionally **not** part of this
planning-only MVP — see `docs/ROADMAP.md`.
