# CrewAI refund assistant example

Follow one potential eval gap from discovery through review, eval addition, and
observed resolution. This example uses **CrewAI**.

## What this example demonstrates

This refund assistant has an existing order-lookup test, but no eval verifying
its high-value refund escalation tool. Skout identifies the potential gap,
lets you review it, and observes resolution after you add a matching test.

The example declares a refund analyst, two sequential tasks, a `Crew`, and two
static tools: `lookup_order` and `escalate_refund`. The active test verifies
`lookup_order`; `escalate_refund` is intentionally untested. High-value policy
is described by the crew, not enforced by a numeric branch in this tool.

Skout analyzes the code statically without executing the crew or its tests.
No LLM API key is required for scanning.

## Prerequisites

- Python **3.12 or newer**. The commands below use `python3.12`.
- Git.
- Skout Scan installed with pip, as shown below.
- No CrewAI installation or LLM API key is needed for static scanning.

## Getting started

Start in a directory where you want to keep the walkthrough. Create a new,
empty workspace so the virtual environment and clone have clear locations:

```bash
mkdir skout-crewai-workspace
cd skout-crewai-workspace

python3.12 -m venv .venv
source .venv/bin/activate
pip install skout-scan

git clone https://github.com/skouthq/skout-scan.git
cd skout-scan/examples/crewai-agent
skout --version
```

Clone to try the example; no fork is necessary unless you want your own copy
for contributing changes. The virtual environment remains active as you change
folders. Installing framework dependencies is optional for static scanning.

**Run every subsequent command from `skout-scan/examples/crewai-agent`.**
Confirm that `crew.py`, `requirements.txt`, and the example evidence directories
are present.

## Discover the gap

```bash
skout doctor
skout scan .
skout findings
```

`doctor` checks repository assessability, not agent quality or adequate eval
coverage. With the initial example and the validated scanner version:

- CrewAI and static agent, task, crew, tool, and task-order constructs are detected.
- Eight behaviors and three deterministic candidate pairs are found.
- `lookup_order` has coverage evidence.
- One actionable finding surfaces `escalate_refund` as a high-confidence,
  potentially uncovered tool behavior.

Read the source evidence and suggested test in `skout findings`. Note the
finding ID so you can compare it after rescanning; IDs derive from source identity.

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

If `tests/test_escalation.py` already exists, follow troubleshooting below rather
than overwriting it. Otherwise, enable the supplied solution:

```bash
cp tests/solutions/test_escalation.py.example tests/test_escalation.py
```

The supplied test calls `escalate_refund` with an order ID and the reason
`amount exceeds automatic limit`. It asserts that the returned `status` is
`escalated` and that the returned `reason` matches. It verifies the tool's
outcome; it does not execute the crew or test how a model chooses the tool.
The inactive `.example` file becomes a discovered Python test only after copying.

## Verify resolution

```bash
skout scan .
skout findings
```

Keep the **same local example directory and `.agentguard/` state** for both
scans. Do not delete state, reclone, or switch repositories between them.
History lives in `.agentguard/agentguard.db` under this example directory.

Skout should recognize the new test evidence, report no open findings, and show
the escalation tool finding as `resolved` with coverage `covered`.
The original finding ID should be unchanged and `add_eval` should persist.
This is observed resolution, not proof of test execution or confirmed product
impact. Confirmed impact requires separate user confirmation that the finding
caused or influenced the eval change.

## Reset the example

Only remove `tests/test_escalation.py` if it is still the unchanged supplied
solution. From the same example directory, compare it before removing it:

```bash
if cmp -s tests/solutions/test_escalation.py.example tests/test_escalation.py; then
    rm tests/test_escalation.py
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
These tests import `crew.py`, which constructs CrewAI agents, tasks, and a crew.
They call the local tools rather than invoking `kickoff`; they do not test the
crew's runtime orchestration. Framework setup or provider configuration may
still be required during imports, and dependencies are unpinned. Optional test
execution was not validated here; static scanning needs neither CrewAI nor a key.

## Troubleshooting

- **`skout: command not found`:** from this example directory, reactivate with
  `source ../../../.venv/bin/activate`, then run
  `python -m pip install skout-scan` and `skout --version`. This path assumes
  the workspace layout above.
- **Wrong directory:** check `pwd` and confirm you are in
  `skout-scan/examples/crewai-agent`, with `crew.py` present. Scanning
  the project root or another example analyzes different code and stores
  separate state. Return here before review or rescan.
- **Solution already exists:** compare with
  `cmp tests/solutions/test_escalation.py.example tests/test_escalation.py`.
  If identical, it is already enabled; proceed to the second scan. If modified,
  preserve your edits and use a fresh clone for the walkthrough.
- **Initial finding missing:** check whether `tests/test_escalation.py` is enabled.
  Use the guarded reset only for the unchanged supplied solution, then rescan.
  Retained history may show a reopened finding rather than a new one. Also
  review `skout doctor` warnings and confirm the working directory.
- **Python incompatibility:** run `python --version` in the active environment.
  Skout requires Python 3.12+. Install a compatible interpreter and create a new
  virtual environment with it; activating an older environment does not upgrade Python.

## Walkthrough validation

Verified using published `skout-scan` **0.1.8** in a fresh temporary clone with
Python 3.12. Doctor, initial scan, findings, and real CLI `add_eval` review were
checked. Review left the finding open; enabling the supplied pytest test and
rescanning resolved the same ID with `covered` status and `add_eval` retained.
The guarded reset retained history and a subsequent scan reopened the gap.
No example code, tests, or agent model calls were executed during validation.
