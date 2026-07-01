# NeuroSurgEpiAgent Efficiency Summary

> Publication-oriented efficiency telemetry. See caveats below.

- **Model alias:** `claude-sonnet-4-6`
- **Backend provenance (declared):** `glm-5.2 via CC-Switch`
- **Execution mode:** sequential
- **Parallel:** False
- **Statistically independent:** False
- **Arm B reuse configured:** False

## Per-arm efficiency

| Arm | Task outputs | Model calls (this run) | Calls/task | Elapsed total (s) | Mean elapsed/task (s) | Input tokens | Output tokens | CLI-reported cost | Estimated cost |
|-----|--------------|------------------------|------------|-------------------|-----------------------|--------------|---------------|-------------------|----------------|
| arm_a | 10 | 3 | 0.3000 | 140.1724 | 14.0172 | 7817 (10/10 avail) | 8623 (10/10 avail) | $0.217517 (complete; 10 reported) | N/A (incomplete; partial $0.000000 over 7 reported, 3 missing) |
| arm_b | 10 | 10 | 1.0000 | 391.2949 | 39.1295 | 10275 (10/10 avail) | 18896 (10/10 avail) | $0.556056 (complete; 10 reported) | N/A (incomplete; 10 missing) |

## Overall

- **Total tasks:** 10
- **Total task-arm outputs:** 20
- **Model calls this run:** 13
- **Reused outputs:** 0
- **Calls/task (overall):** 1.3000
- **Elapsed total (s):** 531.4674
- **Mean elapsed/task (s):** 26.5734 (available 20/0 missing)
- **Input tokens (overall):** 18092 (available 20/0 missing)
- **Output tokens (overall):** 27519 (available 20/0 missing)
- **Cache-read tokens (overall):** 980416 (available 20/0 missing)
- **Cache-creation tokens (overall):** 0 (available 20/0 missing)
- **CLI-reported cost (overall):** $0.773573 (complete; 20 reported)
- **Estimated cost (overall):** N/A (incomplete; partial $0.000000 over 7 reported, 13 missing)
_Totals omit reused outputs and never sum missing values as zero; an incomplete cost total is shown as N/A with its partial observed sum and coverage, never as $0._

## Caveats

1. Tasks are authored development items (benchmarks/tasks.example.yaml), not expert-validated gold standard; results are not suitable for publication or comparative-effectiveness claims.
2. Arms were executed sequentially within a single run (Arm A then Arm B per task). This is NOT parallel execution and the two arms are NOT statistically independent samples.
3. 'claude_cli_reported_cost_usd' is the cost reported by the Claude CLI for the session. It is NOT a vendor invoice and NOT evidence of cost-effectiveness.
4. 'estimated_cost_usd' is computed only from caller-supplied per-million-token prices and is None unless every rate required by the observed nonzero token categories was supplied. Vendor prices are never hard-coded by the tool.
5. Missing token/cost fields are never summed as zero; availability and missing counts are reported alongside every total.
6. When any non-reused output is missing a cost field, the corresponding cost '*_total' is None (an incomplete total is never displayed as $0); the observed '*_partial_sum_usd', the '*_complete' flag, and the availability/missing counts make the gap explicit. A genuinely-zero complete total (all measured outputs report the field, including structural zeros) is reported as 0.
