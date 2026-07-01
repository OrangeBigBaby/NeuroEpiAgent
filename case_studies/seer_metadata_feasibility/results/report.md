# SEER metadata feasibility case study

> **Synthetic case study.** This run wrote a temp directory of
> placeholder SEER-shaped CSVs and inspected them with
> `SEERAdapter`. It does NOT read any real SEER*Stat export.

## Aggregate

- Files inspected: `13`
- Total bytes: `39,663`
- Unique schema fingerprints: `1`

## Capability split

- `metadata-inspection`: **supported** (this case study)
- `clinical-analysis`: **planned** (NOT exposed by SEERAdapter)

## Disclosure posture

- The synthetic data rows in the temp tree are NEVER written into the case-study outputs.
- Only file-level metadata (name, byte size, schema fingerprint) is emitted.
- Data-version field status: `needs_verification` (provided: `{}`)
