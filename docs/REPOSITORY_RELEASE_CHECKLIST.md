# Repository Release Checklist

This checklist is the final gate before tagging a public release. It is
intentionally strict: every item is either met (with evidence) or blocks the
release.

## 1. Tests pass on a clean clone

- [ ] `python -m venv .venv && .\.venv\Scripts\Activate.ps1`
- [ ] `pip install -e ".[dev]"`
- [ ] `pytest -q` reports `342 passed, 2 skipped` (the Phase 0 baseline)
      plus any net-positive additional tests, and zero failures.
- [ ] No test depends on `E:\Nhance\...` or any other absolute path.
- [ ] No test reads from `02_data_raw/`, `03_data_processed/`,
      `SEERdatabase/`, or `data/cache/`.

## 2. `.gitignore` is intact and the staged tree is clean

- [ ] `git status --short` shows the intended changes only.
- [ ] `git status --short --ignored` shows only paths that should be
      ignored (no tracked file matches an ignored pattern).
- [ ] `git diff --cached --name-only | grep -E '(\.XPT|\.xpt|\.dta|\.sas7bdat|\.parquet|\.feather|\.duckdb|\.csv|case_listing|export_C)'`
      returns empty.
- [ ] `git diff --cached --name-only | grep -E '^(\.codex/|\.venv/|02_data_raw/|03_data_processed/|data/cache/|manifests/local/)'`
      returns empty.
- [ ] `git ls-files | xargs -I {} wc -c {} | sort -n | tail` shows no file
      over 50 MB.
- [ ] `git ls-files` contains no file that is itself a directory (no
      nested-repo checkin).

## 3. Sensitive-information scan

- [ ] `git ls-files | xargs grep -l -E '(api_key|apikey|token|secret|password|Bearer|C:\\Users|E:\\Nhance)' 2>/dev/null`
      returns empty, except for this very file and `docs/DATA_GOVERNANCE.md`
      where the strings appear as policy language, not as actual secrets.
- [ ] `git ls-files | xargs grep -l 'E:\\Nhance'` returns empty
      (`DATA_GOVERNANCE.md` etc. intentionally reference the policy text,
      not real paths).
- [ ] `.env.example` exists; `.env` does not exist or is git-ignored.

## 4. CI is green

- [ ] `.github/workflows/tests.yml` runs on Windows and Ubuntu Python
      3.10 / 3.11 / 3.12.
- [ ] CI does NOT download SEER / CDC WONDER / NHANES data (it only runs
      the synthetic fixtures and the test suite).
- [ ] The latest CI run on `main` is green for the commit being tagged.

## 5. Documentation aligned

- [ ] `README.md` is the public-facing entry point and matches the
      current capability matrix (planning / metadata inspection /
      analysis execution / publication-ready evidence).
- [ ] `docs/ROADMAP.md` reflects the current phase status.
- [ ] `docs/MANUSCRIPT_PLAN.md` and `manuscript/CLAIM_EVIDENCE_MATRIX.md`
      match each other — every claim cited in the manuscript plan has an
      evidence status (`supported` / `needs evidence` / `inferred`).
- [ ] `docs/DATA_GOVERNANCE.md` and `docs/DATA_PROVENANCE.md` are in sync
      with what the code actually does.

## 6. CITATION.cff is current

- [ ] `CITATION.cff` lists the current version, release date, and the
      GitHub repository URL (https://github.com/OrangeBigBaby/NeuroEpiAgent).
- [ ] Authors and ORCIDs (if any) are accurate.

## 7. Version, commit, and dependency metadata are recorded

- [ ] `pyproject.toml` version matches the release tag (`vMAJOR.MINOR.PATCH`).
- [ ] Git tag created locally (`git tag -a vMAJOR.MINOR.PATCH -m "..."`).
- [ ] Tag pushed (`git push origin vMAJOR.MINOR.PATCH`).
- [ ] GitHub Release drafted with:
  - commit SHA (full, not abbreviated)
  - Python version (`python --version`)
  - dependency versions (`pip freeze > requirements.lock.txt`)
  - data versions (NHANES cycle / WONDER query date / SEER submission)
  - run date (UTC)
  - SHA-256 of every committed `results/*.json` artifact

## 8. Public case-study outputs pass disclosure checks

- [ ] Every CDC WONDER aggregate output has been disclosure-checked:
      no `Deaths <= 9` cell in any table, no `Deaths < 20` rate presented
      without an `unstable / unreliable` flag.
- [ ] Every SEER aggregate output contains zero case rows.
- [ ] Every manuscript figure has a corresponding script in `scripts/` or
      `case_studies/` that produces it from public inputs.

## 9. Code Availability and Data Availability statements drafted

- [ ] Code Availability text matches the GitHub URL and the release tag.
- [ ] Data Availability text splits the three sources:
  - NHANES: public.
  - CDC WONDER: aggregated, NCHS publication restrictions.
  - SEER: requires independent SEER DUA application; repo does not
    redistribute individual-level records.

## 10. Sign-off

- [ ] Repository maintainer signed off in the GitHub Release notes.
- [ ] If the release is a paper submission candidate, the corresponding
      author confirms that every manuscript number traces to a result
      file (and the trace is recorded in
      `manuscript/CLAIM_EVIDENCE_MATRIX.md`).