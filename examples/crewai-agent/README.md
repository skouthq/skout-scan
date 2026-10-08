# CrewAI refund assistant example

## What this example demonstrates

**Framework:** CrewAI

The example declares a refund analyst, two sequential tasks, a `Crew`, and two
static tools. The active test verifies `lookup_order`. The
`escalate_refund` tool used for high-value refunds is intentionally untested.

Skout only reads these files. No framework installation, API key, model call,
or network access is required for the demo.

## Run

From this directory:

```bash
skout doctor
skout scan .
```

Expected result:

- CrewAI and its static agent, task, crew, tool, and task-order constructs are
  detected.
- Eight behaviors and three deterministic candidate pairs are found.
- `lookup_order` has coverage evidence.
- One actionable finding surfaces `escalate_refund` as a high-confidence
  potential gap.

Finding IDs are intentionally omitted because they are derived from source
identity.

## Resolve the finding

Enable the supplied escalation test and scan again:

```bash
cp tests/solutions/test_escalation.py.example tests/test_escalation.py
skout scan .
```

Skout should preserve the finding identity, report no open findings, and record
the escalation finding as resolved with the new test as evidence. Remove the
copied test to restore the original demo state.

To execute the illustrative tests separately, install the optional dependencies
from `requirements.txt`. Running target tests is not part of the Skout scan.
