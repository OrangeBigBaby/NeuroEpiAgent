# Security Policy

## Scope

NeuroSurgEpiAgent is an offline planning and validation library. It reads local
YAML registries, evaluates deterministic rules, and writes YAML manifests. It
makes **no network calls**, fetches **no datasets**, and executes **no user
R/Python analysis code**. The package surface that handles untrusted input is
therefore small: the CLI and the registry/plan loaders.

## Reporting a vulnerability

Email the maintainers rather than opening a public issue, so a fix can ship
before details are public. Include:

- a minimal YAML plan or registry that triggers the behaviour,
- what you expected vs. what happened,
- the package version (`neurosurg_epi_agent.__version__`).

## Threat model & guarantees

| Concern | Status |
|---|---|
| Remote code execution via plan/registry YAML | Mitigated: only `yaml.safe_load` is used. |
| Prompt-injection from LLM into variable names | Mitigated: variable names are validated by Pydantic and never executed; they are emitted as plain strings in the manifest. |
| Fabricated clinical results leaking out | Mitigated by design: the engine emits *findings and provenance*, never estimates. |
| Insecure deserialization | `safe_load` only; no arbitrary object construction. |

If you extend the package, **do not** add `yaml.load` without `Loader=SafeLoader`,
do not `eval`/`exec` plan fields, and do not introduce network calls.

## Not in scope

- Security of downstream R/Python analysis code that a user writes from a
  validated plan — that runs outside this library.
- Access controls for GBD/SEER registry data (adapter not yet implemented).
