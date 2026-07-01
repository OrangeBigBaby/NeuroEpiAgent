# Contributing

Thanks for considering a contribution. NeuroSurgEpiAgent is a research-grade
tool, so contributions that protect correctness and reproducibility are valued
over feature breadth.

## The one rule that matters most

**Never introduce a variable code, citation, result, or performance number
that you have not personally confirmed.** The whole point of the project is
that the LLM is *not* the source of truth. If you are unsure of a codebook stem,
mark the variable `status: needs review` or `illustrative` and say so in
`ref_notes` — do not guess and mark it `verified`.

## Ways to contribute

- **Variable registry entries** — new NHANES mappings, each with an explicit
  `status` and a `ref_notes` pointer to the codebook (not a paper).
- **Guardrails** — new deterministic checks for NHANES survey design or
  epidemiological language policy. Guardrails must be rules, not heuristics,
  and must never auto-rewrite variable names.
- **Tests** — every new guardrail or registry rule needs a test that shows it
  firing on a bad input and passing on a good one.
- **Adapters** — CHARLS / GBD / SEER are scaffolded as `planned`. Bring one to
  `supported` only with its own guardrails and tests; see `docs/ROADMAP.md`.

## Development workflow

```powershell
# from the NeuroSurgEpiAgent folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## Pull request checklist

- [ ] `pytest` passes locally.
- [ ] No new `verified` status without a codebook reference in `ref_notes`.
- [ ] No causal language (`proves`, `causes`, `first ever`, …) in any output or
      test fixture *unless* the fixture exists to show the guardrail firing.
- [ ] No fabricated results, citations, or performance numbers anywhere.
- [ ] Registries changed → registry tests updated.

## Scope we will not merge in the MVP

- Auto-fetching raw NHANES data or any network call inside the package.
- Treating GBD/SEER/CHARLS as active data sources.
- LLM-generated variable names or statistical validity decisions.
- Raw data, derived datasets, or `.codex/` / `.venv` session artifacts in
  any commit. See `docs/DATA_GOVERNANCE.md` for the exclusion list and
  the rationale.
