# Pydantic AI refund assistant example

## What this example demonstrates

**Framework:** Pydantic AI and Pydantic Evals

The example uses `Agent(...)`, `RunContext` dependencies, a registered tool, a
structured `RefundDecision` output, and an output validator with an explicit
`ModelRetry` path. The active Pydantic Evals dataset and tool test provide
positive matching evidence. The high-value validator retry is intentionally
left uncovered.

Skout only reads these files. No framework installation, API key, model call,
eval execution, or network access is required for the demo.

## Run

From this directory:

```bash
skout doctor
skout scan .
```

Expected result:

- Pydantic AI and Pydantic Evals are detected.
- Agent, tool, dependency, structured-output, validator, Case, and Dataset
  evidence is reported.
- Four behaviors and two deterministic candidate pairs are found.
- Two behaviors have coverage evidence.
- One actionable finding surfaces the high-value `ModelRetry` path as a
  potential gap.

Finding IDs are intentionally omitted because they are derived from source
identity.

## Resolve the finding

Enable the supplied retry test and scan again:

```bash
cp tests/solutions/test_retry.py.example tests/test_retry.py
skout scan .
```

Skout should preserve the finding identity, report no open findings, and record
the validator finding as resolved with the new test as evidence. Remove the
copied test to restore the original demo state.

To execute the illustrative tests separately, install the optional dependencies
from `requirements.txt`. Running target tests or evals is not part of the Skout
scan.
