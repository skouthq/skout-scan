# LangGraph refund assistant example

## What this example demonstrates

**Framework:** LangGraph

The workflow uses static routine-refund and review subgraphs, a normal edge, and
literal conditional routes. The active eval covers automatic approval for a
small refund. The high-value review route to `escalate_refund` is intentionally
left uncovered.

Skout only reads these files. No framework installation, API key, model call,
or network access is required for the demo.

## Run

From this directory:

```bash
skout doctor
skout scan .
```

Expected result:

- LangGraph is detected.
- Three workflow behaviors and two deterministic candidate pairs are found.
- The automatic refund path has coverage evidence.
- One actionable finding surfaces the high-value escalation route as
  potentially uncovered.

Finding IDs are intentionally omitted because they are derived from source
identity.

## Resolve the finding

Enable the supplied escalation eval and scan again:

```bash
cp evals/escalation_path.jsonl.example evals/escalation_path.jsonl
skout scan .
```

Skout should preserve the finding identity, report no open findings, and record
the escalation finding as resolved with the new JSONL eval as evidence. Remove
the copied `.jsonl` file to restore the original demo state.

To execute the illustrative pytest test separately, install the optional
dependencies from `requirements.txt`. Running target tests is not part of the
Skout scan.
