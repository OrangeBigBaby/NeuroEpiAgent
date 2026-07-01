# Changelog

All notable changes to NeuroSurgEpiAgent are recorded here. Versions follow
semantic versioning; the single source of truth for the release number is
`src/neurosurg_epi_agent/__init__.py` (`__version__`), read by `pyproject.toml`
via setuptools `dynamic = ["version"]`.

## [0.3.1] — 2026-07-02

A remediation release that makes CI reliable on every runner, unifies the
version metadata, and hardens the SEER / CDC WONDER adapters' security and
disclosure behavior. No raw research data is present in the repository now,
nor was it at any prior release.

### CI

- **Secret scan no longer self-triggers.** The v0.3.0 in-workflow scan matched
  its own `grep` expression (which listed `api_key|password|Bearer|...`), so
  the scan failed on the workflow file itself. Replaced with a standalone,
  unit-tested module `scripts/scan_tracked_secrets.py` (+ `tests/
  test_secret_scan.py`) that detects credential *assignments* and well-known
  token *shapes* (GitHub `ghp_…`, AWS `AKIA…`, Slack `xox…`, OpenAI `sk-…`,
  Google `AIza…`, PEM private-key headers) plus the local workspace path
  markers, while ignoring bare keyword mentions and placeholder values. A
  precise per-file allowlist covers policy docs; no broad directory ignores.
- **Symlink handling fixed on all runners.** NHANES / SEER / CDC WONDER
  `_walk_files` silently dropped symlinked files, so the inspect loop's
  `skipped_roots` branch was dead code; on CI (where symlinks work) the
  symlink-escape tests ran and failed. `_walk_files` now returns symlinked
  files so the loop records them in `skipped_roots` (matching CHARLS). The
  SEER/CDC symlink tests also switched from a bare `return` (which
  false-passed) to `pytest.skip`, with monkeypatch regression guards.
- **Workflow modernized:** `actions/checkout@v7`, `actions/setup-python@v6`
  (Node 24, clearing the Node 20 deprecation warnings), and
  `python -m pytest -ra`.
- **Final cross-platform correction:** the diagnostic wrapper briefly added
  after the first failed run used Bash control-flow syntax on Windows runners;
  it was replaced with one shell-neutral `python -m pytest` command. The SEER
  symlink test now places its target outside the inspected root (the previous
  fixture accidentally put the target inside the root and expected it to be
  ignored). The final Ubuntu/Windows matrix is green on Python 3.10/3.11/3.12.

### Version metadata

- Single source of truth for the release version: `__version__` is a literal in
  `__init__.py`; `pyproject.toml` reads it via `dynamic = ["version"]` +
  `attr`; `CITATION.cff` mirrors it. Case-study provenance records
  `__version__` instead of a hard-coded string. `tests/test_version_consistency.py`
  pins the chain (runtime, distribution metadata, pyproject, CITATION) and
  explicitly does **not** collapse the adapter protocol version
  (`ADAPTER_VERSION`) or per-adapter implementation versions onto the release
  version.

### SEER adapter (`src/neurosurg_epi_agent/adapters/seer.py`)

- `scripts/inspect_seer_exports.py` no longer corrupts its JSON when
  `NEUROSURG_EPI_SEER_ROOT` is unset (`text.replace("", token)` was inserting
  the token between every character). The defence-in-depth scrub now runs only
  for a real, non-empty path.
- `members` filter is now honored (basename or forward-slash relative path;
  traversal / absolute / drive-letter entries rejected).
- `max_member_bytes` is now the INSPECTION cap (Plan A): oversize files go to
  `skipped_roots` before their header is read; `sha256_max_bytes` is a separate
  hash cap.
- Single-file input reports the filename for `member_path`/`member_name`
  (was `"."`).
- `data_version`: empty / whitespace-only values count as missing; unknown keys
  are isolated in a `data_version_extensions` area and never treated as
  verified provenance; `product_type` / `export_date` / `seerstat_version` get
  conservative format checks.
- Adapter-level provenance now carries an explicit `schema_consistent` flag
  (`true` / `false` / `no_recognized_schema`) plus fingerprint counts.

### CDC WONDER adapter (`src/neurosurg_epi_agent/adapters/cdc_wonder.py`)

- Numeric disclosure rules are now enforced **independently of the Notes cell**
  (the original bug: an empty Notes cell short-circuited the row, so `Deaths=5`
  was silently treated as a stable count). `Deaths` 0-9 are flagged as
  suppression violations, 10-19 as unreliable; non-numeric Deaths cells are
  never coerced to 0; WONDER-vs-numeric conflicts are counted and surfaced via
  `disclosure_validation`.

### Documentation

- `docs/SEER_DATA_DICTIONARY.md` corrected: the column count is **247** (the
  earlier "269" was a comma-split artefact that double-counted quoted headers),
  marked as adapter-generated not hand-maintained, with the synthetic-test vs.
  real-smoke evidence clearly separated.
- Capability model unified across `README.md`, `docs/ROADMAP.md`,
  `config/databases.yaml`, `docs/MANUSCRIPT_PLAN.md`, `benchmarks/
  BENCHMARK_CARD.md`, and `manuscript/CLAIM_EVIDENCE_MATRIX.md`.
- The three arXiv example PDFs were removed (redistribution license not
  independently confirmable); `docs/literature/.../DOWNLOAD_MANIFEST.md` now
  keeps only the arXiv URL, citation metadata, and SHA-256 hashes.
- `docs/PUBLICATION_READINESS.md` and `docs/CODE_AVAILABILITY.md` no longer
  hard-code a test count (the count drifts; it is reported by CI and the
  release notes).
- `docs/REPOSITORY_RELEASE_CHECKLIST.md` updated to the current test count and
  the new scanner; boxes checked per actual completion.
- `docs/FINAL_REPORT.md` carries a correction notice: v0.3.0's CI was red, not
  green.

### Tests

- **460 collected** at v0.3.1. On the local Windows host, 456 pass and four
  OS-symlink tests skip because symlink privilege is unavailable. On GitHub
  Actions runners all 460 pass. Zero failures.
- Python: `>=3.10`, tested on 3.10 / 3.11 / 3.12 (Ubuntu + Windows).

### Reproduce

```powershell
git clone https://github.com/OrangeBigBaby/NeuroEpiAgent.git
cd NeuroEpiAgent
python -m pip install -e ".[dev]"
python -m pytest -ra
python scripts/scan_tracked_secrets.py --root .
```

### Data boundary (unchanged and explicit)

No SEER individual-level record, no locally downloaded NHANES `.XPT`, and no
CDC WONDER cell value is redistributed in this repository. The SEER and CDC
WONDER adapters are metadata-only; clinical analysis for SEER requires a
completed `docs/SEER_STUDY_CONTRACT.md`. The exact commit for this release is
the one tagged `v0.3.1` (see the release notes for the full SHA).

### Known limitations

- The benchmark is a 30-task **draft** (frozen at v0.1.0), not a gold standard;
  it awaits two-expert adjudication, so no generalizable agent-performance
  claim is made.
- The NHANES case study reports a descriptive weighted estimate; it is not
  causal/diagnostic/decision-support and does not implement complex-sampling
  variance.
- SEER clinical analysis, and planning adapters for CDC WONDER / SEER / CHARLS,
  remain out of scope (planned / not supported).

## [0.3.0] — 2026-07-01

Initial public release with case studies (NHANES aggregate, synthetic CDC
WONDER disclosure demo, synthetic SEER metadata feasibility) and the analysis-
implementation principles. See `docs/FINAL_REPORT.md` (with the v0.3.1
correction notice above).
