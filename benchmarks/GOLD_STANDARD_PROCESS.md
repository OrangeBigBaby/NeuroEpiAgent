# Gold Standard Process for NeuroSurgEpiAgent Benchmark

## Status: DRAFT - NOT READY FOR CLINICAL OR SCIENTIFIC CLAIMS

This document describes the required gold standard process for the NeuroSurgEpiAgent
benchmark. **The current `tasks.draft.yaml` is a preliminary draft and cannot support
scientific claims.** Achieving gold standard status requires the process below.

---

## Expert Recruitment and Independence

### Minimum Requirement: Two Independent Experts

- **Expert 1:** Board-certified neurologist or neurosurgeon with ≥5 years of clinical
  practice and epidemiology research experience.
- **Expert 2:** Epidemiologist (PhD or DrPH) with ≥3 years of NHANES or complex
  survey design experience, or a second neurologist/neurosurgeon meeting Expert 1 criteria.

### Conflict of Interest and Independence

- Experts must be independent of the NeuroSurgEpiAgent development team.
- No financial stake in the tool's success or failure.
- No involvement in prior NHANES analyses that used the same variables.
- Signed conflict-of-interest disclosure required before participation.

### Compensation

- Experts compensated at fair market rate for their time.
- Payment not contingent on any specific evaluation outcome.
- Compensation agreement documented before gold-standard authoring begins.

---

## Gold Standard Authoring Process

### Phase 1: Task Development and Verification

1. **Initial Task Drafting**
   - Development team proposes draft tasks (as in `tasks.draft.yaml`).
   - Each task includes: clinical question, expected routing, feasibility assessment,
     rationale, domain.

2. **Expert Review and Revision**
   - Expert 1 reviews each task for clinical accuracy and NHANES feasibility.
   - Expert 2 reviews each task for epidemiological soundness and survey-design
     feasibility.
   - Experts independently flag items they believe are incorrect or uncertain.

3. **Adjudication Session**
   - Both experts meet (virtual or in-person) to discuss flagged items.
   - Development team attends as observers only, does not vote.
   - Consensus reached on:
     - Correct database routing
     - Correct feasibility assessment
     - Appropriate rationale wording
     - Variable code selections (from registry only)

4. **Freezing the Gold Standard**
   - After adjudication, `expected_*` fields are locked.
   - Versioned commit with both experts' sign-off recorded.
   - Git annotated tag: `gold-standard-vX.Y.Z`
   - SHA256 hash of the frozen task set recorded in evaluation manifests.

### Phase 2: Leakage Control

#### Strict Separation of Roles

- **Gold Standard Authors** (Experts): Write the expected behavior, NEVER run any
  planner system.
- **Evaluation Runners**: Execute arms, NEVER see expected outcomes during execution.
- **Data Analysts**: Score results, NEVER modify gold standard.

#### Information Flow Control

1. **Before Any Arm Execution**
   - Gold standard frozen with signed-off expected outcomes.
   - Evaluation runners receive tasks with `expected_*` fields redacted.
   - Only task IDs and free-text questions are visible during planning.

2. **During Arm Execution**
   - Evaluation runners do not access gold standard file.
   - Raw outputs collected with timestamps and provenance metadata.
   - No discussion of feasibility/routing during execution phase.

3. **During Scoring**
   - Gold standard unmasked only after all arms complete.
   - Automated scoring compares outputs to frozen expected values.
   - Any discrepancies manually reviewed by both experts.

#### Version Control and Timestamps

- All gold standard changes tracked in git with expert sign-off.
- Evaluation runs timestamped and hashed against specific gold standard version.
- Any amendment to gold standard requires new version + expert re-signature.

---

## Amendment Policy

### When Amendments Are Required

Amendments are permitted only in these circumstances:

1. **NHANES Codebook Error**: A variable code that gold standard assumed existed
   does not actually exist in a specific cycle.
2. **Documentation Error**: NHANES releases updated documentation that changes
   interpretation of a variable.
3. **Typographical Error**: Clear typo in gold standard that both experts agree
   is an error (e.g., misspelled variable name).

### Amendment Process

1. Document the error with primary source evidence (codebook screenshot, NHANES
   documentation).
2. Both experts review and independently confirm the amendment is warranted.
3. Amendment logged with:
   - Git commit with `[AMENDMENT]` prefix
   - Both experts' sign-off comments
   - New version tag (increment patch version: vX.Y.Z → vX.Y.(Z+1))
4. All prior evaluation runs marked with "superseded by gold-standard-vX.Y.(Z+1)"

### Amendments Are NOT Permitted For

- Post-hoc justification of failed evaluation items
- Adjusting expected outcomes to better match a specific planner's behavior
- Adding new tasks after evaluation has begun

---

## Scoring and Adjudication

### Automated Scoring Metrics

The evaluation module scores each task on these metrics against the frozen gold standard:

1. **Database Routing**: Does the plan's `database` match `expected_database`?
2. **Feasibility Assessment**: Does the plan's `feasible` match `expected_feasible`?
3. **Hard Error Free**: Did the planner generate a plan without crashing/timeout?
4. **Correct Refusal**: Did the planner correctly refuse infeasible tasks?
5. **Variable Codes**: Are all variable codes from the allowed registry set?
6. **Manifest Reconstructability**: Can the plan be serialized/deserialized correctly?

### Manual Adjudication of Borderline Cases

When automated scoring is ambiguous (e.g., partial refusal, caveated refusal):

1. Both experts independently review the specific output.
2. Experts categorize as:
   - **Correct behavior**: Matches clinical and epidemiological best practice
   - **Acceptable but suboptimal**: Technically correct but could be improved
   - **Incorrect**: Violates clinical or survey-design principles

3. If experts disagree, a third adjudicator (independent senior epidemiologist)
   breaks the tie.

### Final Reporting

Results tables include:

- Per-task binary scores (pass/fail) for each metric
- Per-arm aggregate scores (proportion passed, 95% CI if N≥30)
- Manual adjudication notes for borderline items
- Explicit statement: "Draft evaluation - not suitable for publication"

---

## Current Status: DRAFT

### What Exists Now

- **`tasks.draft.yaml`**: 30 preliminary tasks spanning stroke, TBI, CNS tumor,
  SAH, hydrocephalus, spine, disparities, global burden, and pituitary.
- **Variable registry**: `nhanes_demo.yaml` with `verified`/`illustrative`/`needs review`
  status tags.
- **Scoring module**: `evaluation.py` with automated metric computation.

### What Is Missing for Gold Standard

1. **Expert Recruitment**: No independent experts have been recruited or signed off.
2. **Adjudication**: No expert consensus process has occurred.
3. **Freezing**: Tasks have not been frozen with expert sign-off and versioning.
4. **Leakage Control**: No controlled evaluation run with blinded task execution.
5. **Codebook Confirmation**: `verified` status variables have not been independently
   confirmed against NHANES codebooks.

### Explicit Limitation

**The draft task set and any evaluation results from it cannot support scientific claims
about NeuroSurgEpiAgent's performance, clinical utility, or comparison to other systems.**

Results from draft evaluation are appropriate only for:
- Internal testing and development
- Pilot evaluation of scoring logic
- Tool development and debugging

---

## Path to Gold Standard

To achieve gold standard status, the following sequence must complete:

1. Recruit two independent experts meeting the criteria above.
2. Experts review and adjudicate all tasks in `tasks.draft.yaml`.
3. Experts independently verify `verified` variable codes against NHANES codebooks.
4. Freeze the agreed-upon gold standard with version tag and expert sign-off.
5. Conduct blinded evaluation run with leakage control.
6. Adjudicate any borderline cases manually.
7. Both experts countersign the final results table.

Only after all steps are complete can the benchmark be described as "gold standard"
or support scientific claims in publication.