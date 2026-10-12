# LangGraph refund assistant example

Follow one potential eval gap from discovery through review, eval addition, and
observed resolution. This example uses **LangGraph**.

## What this example demonstrates

This refund workflow has eval evidence for routine approval, but lacks evidence
for its high-value escalation route. Skout identifies the potential gap and can
observe resolution when you add the supplied matching eval scenario.

The workflow declares a routine-refund subgraph and a review subgraph, static
transitions, and literal conditional routes. Existing evidence covers automatic
approval for a small refund. The review route to `escalate_refund` for refunds
above 500 is intentionally left uncovered.

Skout reads code and JSONL evidence statically without executing the workflow
or its tests. No LLM API key is required for scanning.

## Prerequisites

- Python **3.12 or newer**. The commands below use `python3.12`.
- Git.
- Skout Scan installed with pip, as shown below.
- No LangGraph installation or LLM API key is needed for static scanning.

## Getting started

Start in a directory where you want to keep the walkthrough. Create a new,
empty workspace so the virtual environment and clone have clear locations:

```bash
mkdir skout-langgraph-workspace
cd skout-langgraph-workspace

python3.12 -m venv .venv
source .venv/bin/activate
pip install skout-scan

git clone https://github.com/skouthq/skout-scan.git
cd skout-scan/examples/langgraph-agent
skout --version
```

Clone to try the example; no fork is necessary unless you want your own copy
for contributing changes. The virtual environment remains active as you change
folders. Installing framework dependencies is optional for static scanning.

**Run every subsequent command from `skout-scan/examples/langgraph-agent`.**
Confirm that `workflow.py`, `requirements.txt`, and the example evidence directories
are present.

## Discover the gap

```bash
skout doctor
skout scan .
skout findings
```

`doctor` checks repository assessability, not agent quality or adequate eval
coverage. With the initial example and the validated scanner version:

- LangGraph is detected.
- Three workflow behaviors and two deterministic candidate pairs are found.
- The routine approval path has coverage evidence.
- One actionable finding surfaces the high-value review route to
  `escalate_refund` as potentially uncovered.

`select_review_route` selects `escalate` when `refund_amount > 500`; the review
graph maps that route to `escalate_refund`. Read the source evidence and suggested
eval in `skout findings`. Note the finding ID so you can compare it after
rescanning; IDs derive from source identity.

## Review the finding

```bash
skout review
```

Read the finding, source evidence, and suggested eval. At the classification
prompt, type `add_eval` and press Enter. This records your **intent** to add or
modify an eval. It does not generate an eval, execute agent code, or resolve
the finding. Run `skout findings` again if you want to see the classification;
the finding should still be open and potentially uncovered.

## Add the missing eval

If `evals/escalation_path.jsonl` already exists, follow troubleshooting below rather
than overwriting it. Otherwise, enable the supplied solution:

```bash
cp evals/escalation_path.jsonl.example evals/escalation_path.jsonl
```

This is a **JSONL eval scenario, not a pytest test**. Its input includes
`select_review_route: "escalate"` and `refund_amount: 900`; its expected path
contains `escalate_refund`. Metadata links it to `review_graph`. These fields
provide static condition, graph, and expected-route evidence for the missing
high-value path. Skout does not execute this scenario. The inactive `.example`
file becomes a discovered JSONL dataset only after copying.

## Verify resolution

```bash
skout scan .
skout findings
```

Keep the **same local example directory and `.agentguard/` state** for both
scans. Do not delete state, reclone, or switch repositories between them.
History lives in `.agentguard/agentguard.db` under this example directory.

Skout should recognize the new JSONL eval evidence, report no open findings, and show
the high-value escalation route finding as `resolved` with coverage `covered`.
The original finding ID should be unchanged and `add_eval` should persist.
This is observed resolution, not proof of test execution or confirmed product
impact. Confirmed impact requires separate user confirmation that the finding
caused or influenced the eval change.

## Reset the example

Only remove `evals/escalation_path.jsonl` if it is still the unchanged supplied
solution. From the same example directory, compare it before removing it:

```bash
if cmp -s evals/escalation_path.jsonl.example evals/escalation_path.jsonl; then
    rm evals/escalation_path.jsonl
else
    printf '%s\n' 'Solution is missing or modified; leave it unchanged.' >&2
fi
```

This restores the missing-eval setup while retaining scan history. Rescanning
can reopen the original finding. Its classification persists, so review may
not prompt for it again.

For a completely fresh walkthrough, create a new disposable workspace and
clone again. Do not remove `.agentguard/` during the resolution sequence.

## Optional: execute the example tests

To execute the illustrative pytest tests separately, install the framework and
test dependencies in the active environment:

```bash
pip install -r requirements.txt
python -m pytest
```

Test execution imports example code and is separate from Skout's static
scanning. It is not needed for the finding-to-resolution walkthrough.
The pytest test calls the local `approve_refund` function and asserts that the
returned route is `approved`. It does not run an LLM or invoke a compiled graph.
The supplied JSONL escalation scenario is static evidence for Skout;
`python -m pytest` does not automatically execute that dataset. Framework
dependencies are unpinned, and optional test execution was not validated here.

## Troubleshooting

- **`skout: command not found`:** from this example directory, reactivate with
  `source ../../../.venv/bin/activate`, then run
  `python -m pip install skout-scan` and `skout --version`. This path assumes
  the workspace layout above.
- **Wrong directory:** check `pwd` and confirm you are in
  `skout-scan/examples/langgraph-agent`, with `workflow.py` present. Scanning
  the project root or another example analyzes different code and stores
  separate state. Return here before review or rescan.
- **Solution already exists:** compare with
  `cmp evals/escalation_path.jsonl.example evals/escalation_path.jsonl`.
  If identical, it is already enabled; proceed to the second scan. If modified,
  preserve your edits and use a fresh clone for the walkthrough.
- **Initial finding missing:** check whether `evals/escalation_path.jsonl` is enabled.
  Use the guarded reset only for the unchanged supplied solution, then rescan.
  Retained history may show a reopened finding rather than a new one. Also
  review `skout doctor` warnings and confirm the working directory.
- **Python incompatibility:** run `python --version` in the active environment.
  Skout requires Python 3.12+. Install a compatible interpreter and create a new
  virtual environment with it; activating an older environment does not upgrade Python.

## Walkthrough validation

Verified using published `skout-scan` **0.1.8** in a fresh temporary clone with
Python 3.12. Doctor, initial scan, findings, and real CLI `add_eval` review were
checked. Review left the finding open; enabling the supplied JSONL scenario and
rescanning resolved the same ID with `covered` status and `add_eval` retained.
The guarded reset retained history and a subsequent scan reopened the gap.
No example code, tests, JSONL scenarios, or agent model calls were executed during validation.
