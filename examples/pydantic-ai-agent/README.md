# Pydantic AI refund assistant example

Follow one potential eval gap from discovery through review, test addition, and
observed resolution. This example uses **Pydantic AI and Pydantic Evals**.

## What this example demonstrates

This example demonstrates how Skout Scan identifies a potentially untested
failure path in a Pydantic AI refund assistant.

The assistant includes existing tests and evals, but they don't verify what
happens when a refund exceeds $500. Skout identifies this potential gap, lets
you review it, and recognizes when you add a test that verifies the missing
behavior.

The example uses Pydantic AI agents, tools, structured outputs, and an output
validator that raises `ModelRetry`. Skout analyzes the code statically without
executing the agent or its tests. No LLM API key is required.

## Prerequisites

- Python **3.12 or newer**. The commands below use `python3.12`.
- Git.
- Skout Scan installed with pip, as shown below.
- No Pydantic AI installation or LLM API key is needed for static scanning.

## Getting started

Start in a directory where you want to keep the walkthrough. Create a new,
empty workspace so the virtual environment and clone have clear locations:

```bash
mkdir skout-example-workspace
cd skout-example-workspace

python3.12 -m venv .venv
source .venv/bin/activate
pip install skout-scan

git clone https://github.com/skouthq/skout-scan.git
cd skout-scan/examples/pydantic-ai-agent
```

**Run every command below from `skout-scan/examples/pydantic-ai-agent`.**
The files `agent.py`, `evals.py`, `requirements.txt`, and `tests/` should be present.
You can check the installed scanner with `skout --version`.

## Discover the gap

```bash
skout doctor
skout scan .
skout findings
```

`doctor` checks whether Skout can assess the repository; readiness does not mean
that the agent has adequate eval coverage. In the initial example:

- Pydantic AI and Pydantic Evals are detected.
- Agent, tool, dependency, structured-output, validator, Case, and Dataset
  evidence is reported.
- Four behaviors and two deterministic candidate pairs are found.
- Two behaviors have coverage evidence.
- One actionable finding surfaces the high-value `ModelRetry` path as a
  potential gap.

In `agent.py`, `validate_refund` raises `ModelRetry` when
`decision.refund_amount > 500`. Existing tool tests and the Pydantic Evals
example do not verify that validator failure outcome. Skout should report it as
`potentially_uncovered`, with source evidence and a suggested eval scenario.

Note the finding ID shown by `skout findings` so you can compare it after the
second scan. IDs are derived from source identity, not supplied by this README.

## Review the finding

```bash
skout review
```

Read the source evidence and suggested scenario. At the classification prompt,
type `add_eval` and press Enter. This records your **intent** to add or modify an
eval. It does not generate a test, execute anything, or resolve the finding.

You can run `skout findings` again to see the persisted classification. The
finding should still be open and potentially uncovered at this stage.

## Add the missing eval

If `tests/test_retry.py` already exists, stop and follow the troubleshooting
instructions below rather than overwriting it. Otherwise, enable the supplied
solution:

```bash
cp tests/solutions/test_retry.py.example tests/test_retry.py
```

The supplied test constructs a `RefundDecision` with refund amount 900 and uses
`pytest.raises(ModelRetry)` around `validate_refund`. Its assertion provides
explicit high-value condition evidence; the exception check verifies the
expected failure outcome. The inactive `.example` file is not a discovered
Python test until you copy it to `tests/test_retry.py`.

## Verify resolution

```bash
skout scan .
skout findings
```

Keep the **same local example directory and `.agentguard/` state** for both
scans. Do not delete scan state, reclone, or switch repositories between them.
Skout stores history in `.agentguard/agentguard.db` under this example directory.

Skout should now recognize the new test evidence, report no open findings, and
show the original validator finding as `resolved` with coverage `covered`.
Compare the finding ID: it should be unchanged, and `add_eval` should persist.
Skout records observed resolution; it does not claim it ran the test or
independently prove that the finding caused your test change.

## Reset the example

Only remove `tests/test_retry.py` if it is still the unchanged supplied solution.
From the same example directory, compare it before removing it:

```bash
if cmp -s tests/solutions/test_retry.py.example tests/test_retry.py; then
    rm tests/test_retry.py
else
    printf '%s\n' 'Test is missing or modified; leave it unchanged.' >&2
fi
```

This removes the supplied test only if it hasn't been modified. Skout retains
the scan history, so rescanning can reopen the original finding. Review
classifications also persist, so review may not prompt for it again.

For a completely fresh walkthrough, create a new workspace and clone the
repository again. Do not remove `.agentguard/` during the resolution sequence;
any intentional history reset should be limited to a disposable copy.

## Optional: execute the example tests

If you want to run the illustrative tests separately, install the example's
framework and test dependencies in the active environment:

```bash
pip install -r requirements.txt
python -m pytest
```

This executes the tests and imports the agent, unlike Skout's static analysis.
It is optional and is not needed to reproduce the finding-to-resolution loop.
The example uses Pydantic AI's test model rather than a hosted LLM; it does not
require an LLM API key. Optional dependencies are unpinned, so compatibility
can vary with future framework releases.

## Troubleshooting

- **`skout: command not found`:** reactivate the workspace virtual environment.
  From the example directory, run `source ../../../.venv/bin/activate`, then
  `python -m pip install skout-scan` and `skout --version`. This relative path
  assumes the workspace layout shown above.
- **Wrong directory or unexpected results:** run `pwd` and confirm you are in
  `skout-scan/examples/pydantic-ai-agent`, with `agent.py` and `tests/` present.
  Scanning the project root or another example analyzes a different repository
  surface and stores separate state. Return to this example before reviewing
  or rescanning.
- **The copied solution already exists:** compare it with
  `cmp tests/solutions/test_retry.py.example tests/test_retry.py`. If identical,
  it is already enabled; proceed to the second scan. If different, preserve your
  edits and use a fresh clone for the walkthrough.
- **The initial finding is missing:** check whether `tests/test_retry.py` was
  already enabled. Use the guarded reset above only for the unchanged solution,
  then rescan. Retained history may show the finding as reopened rather than new.
  Also check `skout doctor` warnings and confirm the example directory is correct.
- **Python version errors:** run `python --version` in the active environment.
  Skout requires Python 3.12+. If `python3.12` is unavailable, install Python
  3.12+ first and create the virtual environment using that interpreter; renaming
  or reactivating an older environment does not upgrade its Python version.

## Walkthrough validation

This sequence was verified with the published `skout-scan` **0.1.8** package in
an isolated Python 3.12 environment and a fresh clone. Discovery produced the
validator finding, review persisted `add_eval` without resolving it, and adding
the supplied test followed by rescanning resolved the same finding ID. The
reset retained history and reopened the finding. No example code or tests were
executed during this validation.
