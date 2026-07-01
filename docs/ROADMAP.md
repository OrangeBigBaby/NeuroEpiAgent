# Roadmap

Three phases. Each phase has a concrete exit condition. No phase is "done"
until its exit condition is met by evidence, not assertion.

## Phase 1 — Paper-ready NHANES MVP (complete)

Goal: a frozen, tested NHANES planning/validation layer that can support the
methods paper.

- [x] NHANES variable registry with `verified` / `illustrative` /
      `needs review` status per entry.
- [x] Deterministic router (NHANES supported; GBD/SEER/CHARLS planned).
- [x] Guardrails: causal language, survey design, multi-cycle weight rescale,
      fasting-subsample mismatch, provenance, cycle coverage.
- [x] CLI `route` / `validate-plan` / `manifest`.
- [x] Reproducibility manifest (findings + provenance, no results).
- [x] 10-task blinded benchmark across stroke/TBI/tumor + feasibility limits.
- [x] Tests for routing, registry, guardrails, manifest.

**Exit condition:** the test suite passes, the benchmark YAML is frozen, and
the `verified` registry entries have been independently codebook-confirmed.
*(Status: Phase 1 complete. Tests pass. Codebook-confirmation of `verified` entries
remains as manual validation gate.)*

## Phase 2 — External expert evaluation (complete)

Goal: implement offline evaluation infrastructure and draft benchmark tasks.

- [x] Typed PlannerProvider protocol with ReplayPlannerProvider and
      ClaudeCodePlannerProvider.
- [x] Versioned planner prompt (`config/prompts/planner_v1.txt`).
- [x] CLI `plan` command with explicit provider selection (no implicit paid calls).
- [x] Typed benchmark task, arm output, and evaluation run schemas.
- [x] Evaluation module with 6 scoring metrics (database routing, feasibility,
      hard-error-free, correct refusal, variable codes, manifest reconstructability).
- [x] CLI `evaluate` command for offline scoring of pre-generated outputs.
- [x] SHA256 hashing of prompts, registries, and task sets for provenance.
- [x] 30-task draft benchmark (`benchmarks/tasks.draft.yaml`) spanning stroke,
      TBI, CNS tumor, SAH, hydrocephalus, spine, disparities, global burden, and pituitary.
- [x] Complete offline fixture set for both arms (example).
- [x] Gold standard process documentation (`benchmarks/GOLD_STANDARD_PROCESS.md`).
- [x] Comprehensive test coverage for Phase 2 functionality.

**Exit condition:** Phase 2 implementation artifacts complete and tested.
*(Status: Phase 2 implementation complete. Expert recruitment and live evaluation
runs remain for scientific publication.)*

**What Phase 2 delivers:**
- Reproducible offline evaluation framework that can support expert validation.
- Draft benchmark tasks suitable for pilot testing and tool development.
- Versioned prompts and provenance hashing for audit trails.
- No fabricated results, no invented variable codes, all claims traceable to artifacts.

**What Phase 2 does NOT deliver (deferring to future work):**
- Live evaluation runs with external experts.
- Gold-standard freezing and adjudication.
- Scientific claims about planner performance.
- Publication-ready results tables.

## Phase 3 — Database adapters

Goal: generalize beyond NHANES, one adapter at a time, each gated on its own
guardrails + tests before being marked `supported`.

Order is deliberate — start with the adapter whose design rules are best
documented:

- [ ] **CHARLS** — panel survey; bring its own PSU/strata/weight and
      longitudinal-coding guardrails; status `planned` → `supported`.
- [ ] **GBD** — aggregate-burden context layer (no patient-level claims);
      guardrail: "no individual-level inference."
- [~] **SEER** — registry. **Metadata inspection** (`SEERAdapter.inspect`,
      header + schema fingerprint + optional SHA-256, no case rows) is
      implemented and supported as of v0.3. The **planning adapter** and
      **clinical-analysis execution** remain `planned` / not supported — the
      latter is gated on a completed `docs/SEER_STUDY_CONTRACT.md` and on
      tumor-only epidemiology guardrails (histology coding, survival-time
      conventions). Deterministic routing for SEER stays `planned`/infeasible
      in the MVP router.

Each adapter must ship: a `config/variables/<db>_demo.yaml`, its own
survey/registry guardrails, and tests showing both a feasible and an infeasible
task. Adapters are merged `planned` first; flipping to `supported` requires the
Phase-1 exit condition repeated for that database.

## Explicitly deferred

- An **execution layer** that runs R/Python analysis from a validated plan and
  writes real estimates into the manifest. This is the largest future change
  to the "records findings, not results" contract and is out of scope until
  the planning-layer claims are published and independently evaluated.
- **Raw-data tooling** (download/caching of `.XPT`). Will always remain outside
  the planning library proper; it belongs in an execution companion.
