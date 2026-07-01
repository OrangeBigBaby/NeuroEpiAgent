# Code Availability (suggested text)

> The text below is a suggested Code Availability paragraph for a manuscript
> that uses NeuroSurgEpiAgent. Edit the placeholders before submission.

> Source code, synthetic test fixtures, analysis-implementation
> specification, and disclosure-checked case-study outputs are
> available at https://github.com/OrangeBigBaby/NeuroEpiAgent,
> archived under release tag `v0.3.0` (commit `{{COMMIT_SHA}}`). The
> repository ships the Python package `neurosurg-epi-agent` (version
> `0.3.0`), the `CDCWonderAdapter` (metadata-only inspection of CDC
> WONDER exports), the `SEERAdapter` (metadata-only inspection of
> SEER\*Stat exports), and three case studies: an aggregate-only
> NHANES 2017-2018 stroke-prevalence demonstration, a synthetic
> CDC WONDER disclosure-checked workflow, and a synthetic SEER
> metadata/feasibility inspection. SEER individual-level records and
> locally downloaded source files are not redistributed under the
> applicable data-use agreement. The repository's CI workflow
> (`.github/workflows/tests.yml`) runs `pip install -e ".[dev]"` and
> `pytest` on every push to `main` without downloading any NHANES,
> CDC WONDER, or SEER data, ensuring a reviewer can reproduce the
> test suite (currently 392 passed, 2 skipped) from a clean clone
> without network access to restricted databases. The repository's
> data-handling boundary is documented in `docs/DATA_GOVERNANCE.md`;
> the per-source provenance policy is documented in
> `docs/DATA_PROVENANCE.md`; and the analysis-implementation rules
> any clinical case-study script must satisfy are documented in
> `docs/ANALYSIS_IMPLEMENTATION_PRINCIPLES.md`.