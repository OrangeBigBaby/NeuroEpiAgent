# Repository Release Checklist

This checklist is the final gate before tagging a public release. It is
intentionally strict: every item is either met (with evidence) or blocks the
release.

## 1. Tests pass on a clean clone

- [x] `python -m venv .venv && .\.venv\Scripts\Activate.ps1`
- [x] `pip install -e ".[dev]"`
- [x] `python -m pytest -ra` reports zero failures. At v0.3.1 the suite is
      **442 collected** (438 passed, 4 symlink-skipped on hosts without
      OS symlink privilege; all 442 pass on CI runners that support symlinks).
      This line is the v0.3.1 count — re-read it from the latest CI run before
      tagging so it cannot drift.
- [x] No test depends on `E:\Nhance\...` or any other absolute path.
- [x] No test reads from `02_data_raw/`, `03_data_processed/`,
      `SEERdatabase/`, or `data/cache/`.

## 2. `.gitignore` is intact and the staged tree is clean

- [ ] `git status --short` shows the intended changes only (check at release time).
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

- [x] `python scripts/scan_tracked_secrets.py --root .` exits 0 and prints
      `secret scan: clean`. The scanner is a standalone, unit-tested module
      (`scripts/scan_tracked_secrets.py` + `tests/test_secret_scan.py`); it
      detects credential assignments and well-known token shapes plus the
      local workspace path markers, and cannot self-trigger on its own rules
      (it matches assignments, not bare keywords). Policy docs that
      legitimately mention these strings are covered by an exact-path
      allowlist (`docs/DATA_GOVERNANCE.md`, `docs/DATA_PROVENANCE.md`,
      `SECURITY.md`, and this file).
- [x] `.env.example` exists; `.env` does not exist or is git-ignored.

## 4. CI is green

- [x] `.github/workflows/tests.yml` runs on Windows and Ubuntu Python
      3.10 / 3.11 / 3.12 using `actions/checkout@v7` + `actions/setup-python@v6`
      (Node 24, no deprecation warnings) and `python -m pytest -ra`.
- [x] CI does NOT download SEER / CDC WONDER / NHANES data (it only runs
      the synthetic fixtures and the test suite).
- [ ] The latest CI run on `main` is green for the commit being tagged
      *(must be verified after pushing the v0.3.1 candidate commit; v0.3.0's
      CI was red — the self-trigger secret-scan and the symlink tests fixed
      in this release).*

## 5. Documentation aligned

- [x] `README.md` is the public-facing entry point and matches the
      current capability matrix (deterministic routing / planning adapter /
      metadata inspection / analysis execution / publication-ready evidence).
- [x] `docs/ROADMAP.md` reflects the current phase status.
- [x] `docs/MANUSCRIPT_PLAN.md` and `manuscript/CLAIM_EVIDENCE_MATRIX.md`
      match each other — every claim cited in the manuscript plan has an
      evidence status (`supported` / `needs evidence` / `inferred`).
- [x] `docs/DATA_GOVERNANCE.md` and `docs/DATA_PROVENANCE.md` are in sync
      with what the code actually does.

## 6. CITATION.cff is current

- [x] `CITATION.cff` lists the current version (`0.3.1`), release date
      (`2026-07-01`), and the GitHub repository URL
      (https://github.com/OrangeBigBaby/NeuroEpiAgent).
- [x] Authors and ORCIDs (if any) are accurate.

## 7. Version, commit, and dependency metadata are recorded

- [x] `pyproject.toml`/`__init__.py` version matches the release tag
      (`0.3.1`) — single source of truth via setuptools `dynamic = ["version"]`
      + `attr = "neurosurg_epi_agent.__version__"`; pinned by
      `tests/test_version_consistency.py`.
- [ ] Git tag created locally (`git tag -a v0.3.1 -m "..."`).
- [ ] Tag pushed (`git push origin v0.3.1`).
- [x] Auditable dependency snapshot recorded in `constraints.txt` (one
      verified-good set; CI still tests against latest). Update policy is
      documented in that file.
- [ ] GitHub Release drafted with:
  - commit SHA (full, not abbreviated)
  - Python version range (`>=3.10`; tested 3.10 / 3.11 / 3.12)
  - dependency snapshot (`constraints.txt`)
  - data versions (NHANES cycle / WONDER query date / SEER submission)
  - run date (UTC)
  - SHA-256 of every committed `results/*.json` artifact

## 8. Public case-study outputs pass disclosure checks

- [x] Every CDC WONDER aggregate output is disclosure-checked **by code**:
      `CDCWonderAdapter` flags `Deaths` 0-9 as suppression violations and
      10-19 as unreliable, independently of the Notes cell, and never coerces
      a non-numeric Deaths to 0 (`tests/test_cdc_wonder_adapter.py`).
- [x] Every SEER aggregate output contains zero case rows — the SEER adapter
      is metadata-only and never emits row content
      (`tests/test_seer_adapter.py`).
- [x] Every manuscript figure has a corresponding script in `scripts/` or
      `case_studies/` that produces it from public inputs
      (`scripts/build_paper_figures.py`; case-study runners).

## 9. Code Availability and Data Availability statements drafted

- [x] Code Availability text (`docs/CODE_AVAILABILITY.md`) matches the GitHub
      URL and the release tag (`v0.3.1`); `{{COMMIT_SHA}}` is filled in with
      the final tagged commit SHA at release time.
- [x] Data Availability text (`docs/DATA_AVAILABILITY.md`) splits the three
      sources:
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

> **v0.3.1 status:** the code/test/doc items above are checked per actual
> completion. The unchecked items (staged-tree inspection at release time,
> the live CI-green verification, tag push, GitHub Release, and maintainer
> sign-off) are the outward-facing steps that complete the release; they are
> checked when each actually happens, not pre-checked.