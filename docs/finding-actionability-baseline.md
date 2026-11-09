# Finding actionability baseline — captured before M11

Baseline: 770 passing tests; Ruff lint/format, production/audit mypy and diff checks pass. The working tree was clean. No target code/tests were executed.

These are actual pre-change CLI traces plus raw structured assessment views. Single-candidate experiments filter already extracted eval scenarios through the existing matcher; they are explicitly labelled and do not claim that the full repository has that isolated assessment. Partial/covered or uncertain assessments may have no selected finding. Full unabridged traces and structured facts are frozen in `tests/fixtures/actionability_audit/baseline.json`. Paths are replaced by `[workspace]`.

Existing provenance explains registration well. Missing dimensions are machine labels, next steps are generic or separated from the closest candidate, and default findings output repeats source/provenance/status detail. M11 should reuse provenance, preserve full detail on request, and translate the exact existing missing dimensions without making new sufficiency judgments.

## rejection_missing

Source repository: `examples/pydantic-ai-agent`; behavior `validate_refund`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: all extracted scenarios; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
  Limitation: Static evidence only; target code and tests were not executed. 
Unsupported test/eval implementations may not be recognized.
  Suggested scenario: Test validate_refund when decision.refund_amount > 500 and
verify ModelRetry or the documented fallback behavior.
  Observed resolution: no
  Confirmed impact: no
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## rejection_partial

Source repository: `tests/fixtures/rejection_audit`; behavior `partial`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_partial']; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_397b4da1744f4311db58e1fd`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## rejection_covered

Source repository: `tests/fixtures/rejection_audit`; behavior `refund`; status `covered`; confidence `high`; availability `available`.

Evidence view: ['test_negative_refund']; exclusions: ['negative.py']. Missing dimensions: []. Closest eval: `eval_5e8ff8efc9357c4d39374bd3`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## graph_missing

Source repository: `tests/fixtures/graph_ownership`; behavior `review_graph`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: []; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
No persisted findings for this repository.
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## graph_no_outcome

Source repository: `tests/fixtures/graph_ownership`; behavior `review_graph`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_no_outcome']; exclusions: []. Missing dimensions: [<CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_3ca94782c419fee63b214fb4`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
No persisted findings for this repository.
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## graph_wrong_owner

Source repository: `tests/fixtures/graph_ownership`; behavior `review_graph`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_wrong_graph']; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>]. Closest eval: `eval_8a7cdb07505314b8e71689d1`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
No persisted findings for this repository.
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## graph_ambiguous

Source repository: `tests/fixtures/graph_ownership`; behavior `review_graph`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['jsonl_conflicting']; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>]. Closest eval: `eval_43160ef818aeb1e1237f9c42`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
No persisted findings for this repository.
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## shared_scope

Source repository: `tests/fixtures/scope_audit/agents`; behavior `shared`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: all extracted scenarios; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
finding_a3336deb381749244a4f9d98
  Source: app.py
  Source evidence: beta = Agent("test", tools=[only_beta, shared])
  Explanation: No sufficient matching eval evidence was discovered in the 
supported scan.
  Behavior: behavior_b032769e35fef81fa0c2f9db (tool_invocation) — Pydantic AI 
agent beta can be invoked
  Location: app.py:34::beta
  Reasons: no_qualifying_evidence, functionality_not_matched, 
expected_outcome_not_matched
  Missing dimensions: functionality, expected_outcome
  Limitation: Static evidence only; target code and tests were not executed. 
Unsupported test/eval implementations may not be recognized.
  Suggested scenario: Run beta with a representative input and assert a 
meaningful result or invariant.
  Observed resolution: no
  Confirmed impact: no

```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## unknown_scope

Source repository: `tests/fixtures/scope_audit/agents`; behavior `unregistered`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: all extracted scenarios; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
  Limitation: Static evidence only; target code and tests were not executed. 
Unsupported test/eval implementations may not be recognized.
  Suggested scenario: Test unregistered when (not value) and verify RuntimeError
or the documented fallback behavior.
  Observed resolution: no
  Confirmed impact: no
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## no_candidates

Source repository: `tests/fixtures/scope_audit/agents`; behavior `only_alpha`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: all extracted scenarios; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
  Limitation: Static evidence only; target code and tests were not executed. 
Unsupported test/eval implementations may not be recognized.
  Suggested scenario: Invoke only_alpha with required inputs value and assert a 
meaningful result or invariant.
  Observed resolution: no
  Confirmed impact: no

finding_a0b6f8f876252f9c17ccbdbf
  Source: app.py
  Source evidence: def unregistered(value):
    if not value:
        raise RuntimeError(value)
    return value
  Explanation: No sufficient matching eval evidence was discovered in the 
supported scan.
  Behavior: behavior_abbcc3985193fa388b9796dc (tool_invocation) — Tool 
unregistered can be invoked
  Location: app.py:27::unregistered
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## wrong_condition

Source repository: `tests/fixtures/rejection_audit`; behavior `refund`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_wrong_condition']; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.CONDITION: 'condition'>]. Closest eval: `eval_c0ba0888f8f3fad722c8401d`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## wrong_exception

Source repository: `tests/fixtures/rejection_audit`; behavior `refund`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_wrong_exception']; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_b57290e0f2f454ef9d856cd5`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## invocation_no_assertion

Source repository: `tests/fixtures/rejection_audit`; behavior `partial`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: ['test_partial']; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_397b4da1744f4311db58e1fd`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## name_only

Source repository: `tests/fixtures/rejection_audit`; behavior `validate_refund`; status `potentially_uncovered`; confidence `medium`; availability `available`.

Evidence view: ['test_name_only_ModelRetry']; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_2ac726971641aa3269709592`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## multiple_conditions

Source repository: `tests/fixtures/rejection_audit`; behavior `refund`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: []; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## jsonl_exception_text

Source repository: `tests/fixtures/rejection_audit`; behavior `validate_refund`; status `partially_covered`; confidence `medium`; availability `available`.

Evidence view: jsonl; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_53b9a7d683ab1605c5feeb05`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## pydantic_exception_text

Source repository: `tests/fixtures/rejection_audit`; behavior `validate_refund`; status `potentially_uncovered`; confidence `medium`; availability `available`.

Evidence view: pydantic_eval; exclusions: ['negative.py']. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `eval_97a104c1d8712784503edb89`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_611690… │ open   │ potentially_un… │ -              │ first agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b8b26a… │ open   │ potentially_un… │ -              │ second agent   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_b9aa2c… │ open   │ potentially_un… │ -              │ beta agent     │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_cc00c8… │ open   │ potentially_un… │ -              │ plain tool     │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## unsupported_dynamic

Source repository: `tests/fixtures/rejection_audit`; behavior `unknown`; status `potentially_uncovered`; confidence `medium`; availability `available`.

Evidence view: all extracted scenarios; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>]. Closest eval: `eval_4b7d5b673316ebec08310ba7`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
  Limitation: The scan is incomplete; this assessment uses only the available 
supported evidence.
  Suggested scenario: Invoke unknown with required inputs amount and assert a 
meaningful result or invariant.
  Observed resolution: no
  Confirmed impact: no

finding_5a48ed0e582323ad6862e7bb
  Source: negative.py
  Source evidence: def uncertain(amount: int):
    if amount < 0:
        raise ValueError("ambiguous agent")
    return amount
  Explanation: No sufficient matching eval evidence was discovered in the 
supported scan.
  Behavior: behavior_98b1de6956c01f95a8bcae56 (tool_invocation) — Pydantic AI 
tool uncertain can be invoked by rebound
  Location: negative.py:23::uncertain
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.

## incomplete_scan

Source repository: `tests/fixtures/rejection_audit`; behavior `partial`; status `potentially_uncovered`; confidence `high`; availability `available`.

Evidence view: []; exclusions: []. Missing dimensions: [<CoverageDimension.FUNCTIONALITY: 'functionality'>, <CoverageDimension.CONDITION: 'condition'>, <CoverageDimension.EXPECTED_OUTCOME: 'expected_outcome'>]. Closest eval: `None`.

Actual existing CLI excerpt (from the full repository view, not a fabricated finding for an isolated assessment):

```text
                              Skout Scan findings                               
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Finding ID      ┃ Status ┃ Coverage        ┃ Classification ┃ Title          ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ finding_084fb0… │ open   │ potentially_un… │ -              │ bound agent    │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_3276e6… │ open   │ potentially_un… │ -              │ rebound agent  │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_599d8e… │ open   │ potentially_un… │ -              │ unknown tool   │
│                 │        │                 │                │ invocation is  │
│                 │        │                 │                │ potentially    │
│                 │        │                 │                │ uncovered      │
│ finding_5a48ed… │ open   │ potentially_un… │ -              │ uncertain tool │
│                 │        │                 │                │ invocation is  │
```

Source facts and all candidate evidence are retained in the frozen JSON. Available review choices remain add_eval, valid_later, already_covered, not_relevant, suppressed or skip. No engineer-usefulness claim has been validated.
