# Verification evidence (M8)

Skout separates an artifact's meaning from the coverage conclusion it supports.
Discovering an artifact does **not** establish that it passed in execution.
Skout uses static analysis and never executes the target agent or its tests.

## Evidence categories

The existing `EvalScenario` representation now extends a shared typed
`VerificationEvidence` model (category, name, source file/symbol/evidence, and
confidence). It retains the same eval ID, source type, assertions, references,
and content fingerprint. There is no separate evidence registry. Future
categories can be represented without inventing a pytest/JSONL source or eval ID;
they are not inputs to the eval matcher.

| Category | Meaning | Automatically populated in M8 |
| --- | --- | --- |
| `automated_test` | An identifiable automated test | Supported pytest functions and methods |
| `eval_case` | A defined evaluation scenario | Supported JSONL and Pydantic Evals cases |
| `runtime_guardrail` | Execution-time validation or enforcement logic | No; category reserved in the model |
| `quality_observation` | A recorded measurement or evaluation result | No; category reserved in the model |
| `requirement` | An expressed expectation or constraint | No; category reserved in the model |

M8 does not extract new guardrails, observations, or requirements. Existing
framework constructs, including output validators, remain behavior/source
information; they are not automatically evidence of their own coverage.
Unsupported artifacts are not assigned a category from filenames or keywords.

## What qualifies for matching and coverage

Only supported pytest/`automated_test` and JSONL or Pydantic
Evals/`eval_case` pairs enter the candidate index. Requirements, guardrails, and
observations are excluded even if a constructed scenario contains matching
symbols or expected outcomes. Changing a category cannot independently resolve
an existing finding.

An eligible category alone is insufficient for `covered`. The existing
behavior-specific functionality, condition/branch/failure, and outcome checks
still apply. A supported pytest call without outcome verification remains
partial; a JSONL case without `expected` does not verify an outcome. Mere dataset
presence is insufficient. Known tool wrapper calls still establish invocation
only, with no automatic failure-path or branch coverage.

No matching thresholds, behavior/eval fingerprints, stable finding IDs, finding
selection rules, or metric formulas change in M8. `add_eval` still records intent;
observed resolution is distinct from explicitly confirmed impact.

## Structured explanations

`BehaviorCoverageAssessment.structured_explanation` and
`Finding.structured_explanation` contain:

- `behavior`: the existing normalized `Behavior`, including ID, description,
  type, source file/symbol/evidence, condition, and action/outcome where known.
- `qualifying_evidence_found`: whether any supported test/case candidate was
  found for this behavior. This does **not** mean sufficient coverage or a passed
  execution, nor does `false` mean no tests exist anywhere in the repository.
- `reason_codes`: stable codes explaining the conclusion and its limits.
- `missing_dimensions`: `functionality`, `condition`, and/or `expected_outcome`.
  Failure-outcome verification is included in `expected_outcome`.
- `closest_eval_id`: the candidate with the fewest missing dimensions; ties use
  eval ID order. Missing dimensions describe that single candidate, not a union
  of evidence from separate tests. With no candidates, dimensions describe what
  the supported scan did not establish.
- `scan_completeness` and `limitations`: upstream completeness, unavailable eval
  paths where known, skipped unsupported patterns, and static-analysis limits.

The existing `matches` / `matched_eval_evidence` records now also contain
`evidence_type`, `source_file`, `source_symbol`, `name`, `source_evidence`, and
per-candidate `missing_dimensions`. Existing `MatchEvidence` booleans, candidate
reasons, confidence, classification, and eval IDs remain in place. Source line
numbers are retained only when extraction actually provided them.

Unavailable assessments omit top-level missing dimensions: missing analysis is
not evidence of absent tests. A finding's last known coverage status may remain
in history while `assessment_available` is false. Check availability before
interpreting that status. As before, sufficient known evidence can support a
covered assessment even when another source is incomplete; the limitation is
reported separately.

| Reason code | Meaning |
| --- | --- |
| `sufficient_matching_evidence` | At least one supported candidate meets the existing coverage rules |
| `no_qualifying_evidence` | No supported test/case candidate was discovered for this behavior |
| `functionality_not_matched` | Required functionality was not established |
| `condition_not_matched` | Required condition/branch evidence was not established |
| `expected_outcome_not_matched` | Required outcome or failure verification was not established |
| `partial_dimension_match` | Existing evidence supports partial coverage |
| `unsupported_evidence_pattern` | An unrecognized JSONL pattern was explicitly skipped |
| `scan_incomplete` | Upstream analysis or behavior-specific evidence was incomplete/unavailable |

Codes can occur together. An unsupported JSONL warning retains its existing
uncertainty handling; M8 does not broaden inference from unsupported patterns.

## CLI, JSON, and local history

Run `skout findings` after scanning for behavior locations, reasons, missing
dimensions, candidate evidence references, and limitations. The normal scan
summary and review commands are preserved; no new commands or flags are added.

`skout metrics --repository . --json` preserves its existing keys and adds
`verification_evidence` and `structured_explanation` to each exported finding.
The former includes match dimensions and source locations without excerpts or
free-form evidence details. The latter excludes the full behavior object to
preserve the export's existing omission of source contents; the finding already
provides its behavior ID, type, and source path. Full source-backed explanations
remain available in the domain models and local SQLite finding payloads.
`doctor --json` is unchanged. M9 adds `scan --baseline <ref> --json` for
read-only comparisons; ordinary scan output remains human-readable.

Old SQLite finding payloads remain readable with null/empty defaults for added
fields. Old eval scenarios infer their category from the existing source type.
An old match without source information retains unknown locations rather than
invented references. A later scan refreshes the explanation. No database schema
migration or state reset is needed; feedback and append-only history remain.

Skout cannot recognize every test/eval implementation, certify correctness, or
guarantee complete coverage. Unsupported patterns may produce unavailable
assessments or explicit warnings within the existing supported scope. These
categories do not introduce runtime analysis, source uploads, semantic matching,
or coverage percentages.

## Registration inventory boundary (M10.2a)

`BehaviorExtractionResult` additionally carries default-empty typed callable
capabilities and registration relationships. These are static source inventory
facts, not `VerificationEvidence`, `EvalScenario`, or new `Behavior` categories.
They do not enter candidate indexing, sufficiency decisions, finding selection,
SQLite payloads, metrics exports, doctor JSON, or M9 verification deltas.
Registration cannot establish invocation, reachability, expected outcome,
coverage, or a missing eval. Resolved bound methods remain inventory-only with
explicit unsupported behavior-assessment warnings. Old extraction payloads load
with empty defaults; existing behavior/finding identities remain unchanged.
See [Registration relationships](registration-relationships.md) for provenance,
source, identity, compatibility, and uncertainty contracts.
