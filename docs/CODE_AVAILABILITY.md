# Code Availability (suggested text)

> The text below is a suggested Code Availability paragraph for a manuscript
> that uses NeuroSurgEpiAgent. Edit the placeholders before submission.

> Source code, synthetic test fixtures, analysis specifications, and
> disclosure-checked aggregate outputs are available at
> https://github.com/OrangeBigBaby/NeuroEpiAgent, archived under release
> tag `v0.2.0` (commit `{{COMMIT_SHA}}`). The repository ships the
> Python package `neurosurg-epi-agent` (version `0.2.0`), the
> `CDCWonderAdapter` (metadata-only inspection of CDC WONDER exports)
> and the `SEERAdapter` (metadata-only inspection of SEER\*Stat
> exports). SEER individual-level records and locally downloaded source
> files are not redistributed under the applicable data-use agreement.
> The repository's CI workflow
> (`.github/workflows/tests.yml`) runs `pip install -e ".[dev]"` and
> `pytest` on every push to `main` without downloading any NHANES,
> CDC WONDER, or SEER data, ensuring a reviewer can reproduce the
> test suite from a clean clone without network access to restricted
> databases. The repository's data-handling boundary is documented in
> `docs/DATA_GOVERNANCE.md`; the per-source provenance policy is
> documented in `docs/DATA_PROVENANCE.md`.