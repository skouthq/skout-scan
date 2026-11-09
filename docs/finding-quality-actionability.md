# Finding quality and actionability — M11

M11 turns existing findings into source-backed verification guidance. It explains
what was identified, what the source declares needs verification, which supported
evidence was considered, which dimensions remain unverified, and a bounded next
step. It does not infer business importance or change coverage, selection or
lifecycle semantics. Human usefulness is **not yet validated**.

## Developer-experience baseline

[The pre-change study](finding-actionability-baseline.md) captures 19 actual
assessment/evidence views with frozen CLI traces and structured explanations in
[baseline.json](../tests/fixtures/actionability_audit/baseline.json). It was captured
before production presentation changed, against the clean 770-test baseline.
The complete technical snapshots and nine prior audit hashes were captured too.
Temporary workspace paths were replaced with `[workspace]` in the frozen traces.

M10.2e already provides good declaration/registration provenance. M11 reuses it.
The previous default findings view repeated source excerpts, registration details,
reason codes, candidate records and a separate generic suggested scenario. Missing
dimensions were mostly machine labels. The new default view groups the behavior,
evidence and next step; full existing diagnostics remain available on request.

Some audit cases isolate existing eval scenarios before calling the unchanged M8
matcher. These are explicitly evidence experiments, not claims about a normal
full-repository scan. Partial, covered or uncertain assessment contexts may have
no selected actionable finding. M11 never promotes them into findings.

## Architecture and representation

`guidance.py` reads existing `CoverageExplanation`, behavior condition/action,
M8 candidate matches, availability/confidence/completeness, and optional M10.2e
provenance. It reads no source files, parses no source, performs no matching, and
calls no network, model or target code.

`FindingGuidance` contains the existing finding/behavior IDs, behavior summary,
verification goal, presentation interpretation, all original candidate evidence,
original closest eval ID, typed missing-dimension explanations and actions, a
suggested next step, source references, reason codes and limitations. The
`GuidanceGap` dimension always comes from the existing M8 explanation.

The interpretation labels `assessable_gap`, `partial_evidence`, `covered_context`
and `analysis_uncertain` describe presentation context. They are neither new
coverage statuses nor business priorities. Existing coverage/confidence fields
remain authoritative and unchanged.

`with_guidance` returns a copy after selection/lifecycle. Ordinary scans render
existing persisted results; findings/review derive context while reading records.
Scoped projection attaches optional guidance only after full repository
persistence and scope classification. The same underlying shared rejection has
identical guidance in both agent scopes. M10.2e's existing selected-owner field
still distinguishes the current scope from the complete verified owner set.

Guidance is never supplied to finding selection, matching or persistence. It is
not saved as authoritative SQLite state. Historical findings default to no
guidance and serialize exactly as before; missing structured explanations fall
back to the existing presentation. No schema migration is needed.

## Supported source contracts and summaries

Guidance is available only from an existing behavior with a faithful contract:

| Existing source fact | Summary/goal boundary |
|---|---|
| Explicit guarded `raise` with exception outcome | Names the callable, exact extracted condition and exception. No invented numeric input or fixture. |
| Conditional `transition` with known target | Names the graph, exact condition and target; verification must identify the correct graph. |
| `tool_invocation` (including existing Agent invocation) | Describes a declared invocation surface and meaningful result/invariant verification; does not invent an output. |
| Existing `return` or `call` action with known outcome/target | Describes that explicit source action and condition where present, without inferring hidden return semantics, propagation or runtime execution. |

These contracts can occur in the existing tool failure, invocation, conditional,
escalation or fallback behavior categories. Unsupported/unconditional actions
without a faithful contract receive no new scenario. Registration-only tools,
Task assignments, node callbacks, literal dispatch and internal delegation or
fallback relationships do not become behaviors or guidance concerns merely from
being structural records.

## Evidence-to-action mapping

The source contract and verification evidence remain separate. Registration proves
a declared association, not that a tool ran or an eval verified its rejection.
All original `BehaviorEvalMatch` records are retained, including IDs, names,
source references, evidence types, status/confidence, matching booleans and missing
dimensions. M11 does not rank candidates or combine dimensions across candidates.
It preserves the exact closest eval ID chosen by M8.

| Existing missing dimension/reason | Guidance |
|---|---|
| `functionality` | Target the actual source file/qualified symbol. For a graph, use a supported invocation or validated explicit owner binding. |
| `condition` | Exercise the exact extracted condition. No concrete value, argument construction or fixture is invented. |
| `expected_outcome` | Assert the extracted exception, route target or explicit action outcome; invocation goals require a meaningful result/invariant. |
| Graph owner mismatch/ambiguous/unverified reason | Explain the unverified graph identity and request supported identity evidence only when functionality is actually missing. |
| No qualifying evidence | Say no supported candidates were discovered; propose only the dimensions M8 recorded. |
| Unavailable/low-confidence/incomplete/unsupported analysis | Recommend inspecting the analysis/evidence first, withhold concrete test actions, retain uncertainty and the existing finding. |

Covered assessments are useful explanation context but recommend no additional
verification step. When a historical finding's assessment is unavailable, stale
missing dimensions are not presented as a current gap. Known dimensions may still
be shown for an available assessment from an incomplete scan, but concrete action
fields remain empty and the next step asks for analysis review.

Nothing generates executable tests, fixtures, dependency injection, provider
configuration, graph API calls or implementation changes. A source expression may
appear verbatim in a scenario description; M11 does not solve it to manufacture
an example input. Existing unsupported matching patterns remain unsupported.

## CLI and JSON behavior

```bash
skout scan .
skout findings
skout findings --details
skout review
skout review --details
skout scan . --scope 'agent.py#refund_agent'
skout scan . --scope 'agent.py#refund_agent' --json
skout metrics --repository . --json
```

Default scan details remain limited to the existing five-finding preview, with a
short behavior/next-step summary. Scoped scans retain their existing finding and
uncertainty sections. The default findings/review views distinguish source facts,
the existing closest evidence, missing verification and next step. Full source,
registration IDs, candidate diagnostics and original suggested-scenario text are
retained by `--details`. Review classifications and prompts work as before.

Scoped finding JSON and the existing metrics export gain optional `guidance` on
finding objects. Old fields, IDs, statuses, confidence and lifecycle data stay in
place. Assessment JSON, root-discovery JSON and M9 JSON remain unchanged. This is
not a new JSON protocol; standalone `skout scan . --json` remains unsupported.
`--scope` with `--baseline`/`--all-changes` remains rejected.

Source and evidence references reuse extracted locations. Scoped JSON removes
nested excerpts as before. Metrics export also removes nested excerpts and
candidate diagnostic detail strings, preserving its existing export boundary.
No new files are read to expand guidance. Candidate order is preserved; source
reference ordering is deterministic and contains no temporary roots or timestamps.

Feedback still uses `add_eval`, `valid_later`, `already_covered`, `not_relevant`,
`suppressed`, or `skip` in review. `add_eval` records intent; guidance does not
create a test, prove it passed, resolve a finding, or confirm impact. Actual source
and eval changes continue through the original scan/lifecycle logic.

## Independent controlled audit

[The source-pinned expectations](../tests/fixtures/actionability_audit/inventory.json)
were curated before guidance implementation. They specify source summary facts,
verification goals, allowed evidence/actions, expected missing dimensions,
forbidden claims, source-reference requirements, uncertainty and pending human
review. Earlier M10.1–M10.3 source/expectation inventories are unchanged.

Two new exception-text controls initially inherited a manual `ValueError` default;
re-reading their pinned validator source corrected those expectations to
`ModelRetry`. This correction is recorded in the new inventory. No production
assessment, old ground truth or matching rule was changed to fit the audit.

[The deterministic report](finding-actionability-audit.json) validates claims
against both independent source facts and original M8 fields, not recommendation
string equality. Tests deliberately inject an invented exception into expectations
and verify that the audit detects it.

| Measure | Result | Unit |
|---|---:|---|
| Factual correctness | 76/76 | Reviewed subject, condition, action and outcome claims |
| Missing-evidence correctness | 38/38 | Independently expected missing dimensions |
| Exact dimension sets | 19/19 | No omitted/extra dimensions per case |
| Action specificity | 16/16 | Reviewed concrete recommendations |
| Source-backed action steps | 33/33 | Individual dimension-specific actions |
| Unsupported-claim rate | 0/19 | Reviewed recommendations containing unsupported claims |
| Source-reference accuracy | 91/91 | Reviewed reference occurrences |
| Uncertainty abstention | 2/2 | Incomplete/dynamic cases withholding concrete test actions |
| Determinism | 19/19 | Equivalent-input guidance comparisons |
| Technical compatibility | 20/20 | Frozen raw inventory/M8/findings/scope/M9 snapshots |
| Prior audit compatibility | 9/9 | Saved technical audit report hashes |

These are separate controlled measurements, not a combined score, behavioral
coverage percentage, actionable-gap precision or proof of engineer usefulness.
Human review remains pending and human usefulness remains **not yet validated**.

## Limitations and release readiness

Guidance is bounded by the current extractor/matcher's evidence contracts. It
cannot recognize arbitrary fixtures, wrappers, data flow, runtime execution or
new graph invocations. Existing M8 false positives/negatives are not repaired by
rewriting advice. Missing canonical provenance is not evidence of irrelevance.

Historical records without structured behavior/explanation data retain the old
view. Unsupported source actions receive no invented scenario. Incomplete or
unavailable evidence produces review-oriented guidance rather than an assertion
that a test is missing. Unknown scope membership stays diagnostic even if a
faithful verification goal can be described.

The milestone is intended for inclusion in the next release after final checks.
Independent engineer review is still needed to establish usefulness; no claim of
that validation, version bump or automatic release is part of this work.

## Developer-review comparison

These are actual pre-change explanation strings and current generated guidance fields. They are not fabricated terminal transcripts. The original complete CLI traces are frozen in the baseline study. Single-candidate graph/rejection views and covered/medium-confidence contexts are labelled experiments; describing them does not select a new finding.

### Potentially uncovered validator rejection

Existing assessment explanation:

> No sufficient matching eval evidence was discovered in the supported scan.

Current guidance:

- **Behavior:** validate_refund raises ModelRetry when decision.refund_amount > 500
- **Verification goal:** Verify that validate_refund raises ModelRetry when decision.refund_amount > 500.
- **Missing:** functionality, condition, expected_outcome
- **Next step:** Target agent.py::validate_refund. Exercise the explicit condition decision.refund_amount > 500. Explicitly assert ModelRetry.

No supported candidate was discovered in this evidence view.

Source: `agent.py:38`.

Registered owners: `agent.py#refund_agent`. Shared owners retain one finding and the same guidance; selected-owner identity is shown separately.

Added: a concrete verification goal and actions tied to the original missing dimensions. Consolidated: repeated source/provenance/assessment paragraphs; full original detail remains under `--details`. Remaining uncertainty: static supported evidence only; no target execution or engineer usefulness validation.

### Partially covered tool rejection

Existing assessment explanation:

> Existing evals exercise the same functionality but do not deterministically verify this exact condition and expected outcome.

Current guidance:

- **Behavior:** partial raises ValueError when (amount < 0)
- **Verification goal:** Verify that partial raises ValueError when (amount < 0).
- **Missing:** expected_outcome
- **Next step:** Explicitly assert ValueError.

Existing evidence: `test_partial` (automated_test; partially_covered). Closest ID remains `eval_397b4da1744f4311db58e1fd`.

Source: `agent.py:37`.

Registered owners: `agent.py#alpha`. Shared owners retain one finding and the same guidance; selected-owner identity is shown separately.

Added: a concrete verification goal and actions tied to the original missing dimensions. Consolidated: repeated source/provenance/assessment paragraphs; full original detail remains under `--details`. Remaining uncertainty: static supported evidence only; no target execution or engineer usefulness validation.

### Conditional LangGraph route (isolated missing-evidence view)

Existing assessment explanation:

> No sufficient matching eval evidence was discovered in the supported scan.

Current guidance:

- **Behavior:** review_graph selects escalate when (choose == 'escalate')
- **Verification goal:** Verify that review_graph selects escalate when (choose == 'escalate') for the correct graph.
- **Missing:** functionality, condition, expected_outcome
- **Next step:** Target workflow.py::review_graph. Use a supported graph invocation or validated explicit owner binding. Exercise the explicit condition (choose == 'escalate'). Assert the route target escalate for review_graph.

No supported candidate was discovered in this evidence view.

Source: `workflow.py:24`.

Added: a concrete verification goal and actions tied to the original missing dimensions. Consolidated: repeated source/provenance/assessment paragraphs; full original detail remains under `--details`. Remaining uncertainty: static supported evidence only; no target execution or engineer usefulness validation.

### Shared-owner scoped rejection

Existing assessment explanation:

> No sufficient matching eval evidence was discovered in the supported scan.

Current guidance:

- **Behavior:** shared raises LookupError when (value == 'bad')
- **Verification goal:** Verify that shared raises LookupError when (value == 'bad').
- **Missing:** functionality, condition, expected_outcome
- **Next step:** Target app.py::shared. Exercise the explicit condition (value == 'bad'). Explicitly assert LookupError.

No supported candidate was discovered in this evidence view.

Source: `app.py:22`.

Registered owners: `app.py#alpha`, `app.py#beta`. Shared owners retain one finding and the same guidance; selected-owner identity is shown separately.

Added: a concrete verification goal and actions tied to the original missing dimensions. Consolidated: repeated source/provenance/assessment paragraphs; full original detail remains under `--details`. Remaining uncertainty: static supported evidence only; no target execution or engineer usefulness validation.

### Complete controlled-case review matrix

Each row keeps the exact original M8 assessment and missing dimensions. Full candidate/source/uncertainty data is in the audit report; these short recommendations do not replace it.

| Case | Existing assessment | Evidence considered | Missing dimensions | Current next step |
|---|---|---|---|---|

| rejection_missing | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target agent.py::validate_refund. Exercise the explicit condition decision.refund_amount > 500. Explicitly assert ModelRetry. |

| rejection_partial | partially_covered | test_partial | expected_outcome | Explicitly assert ValueError. |

| rejection_covered | covered | test_negative_refund | none | Inspect the matched evidence; this assessment indicates no missing verification step. |

| graph_missing | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target workflow.py::review_graph. Use a supported graph invocation or validated explicit owner binding. Exercise the explicit condition (choose == 'escalate'). Assert the route target escalate for review_graph. |

| graph_no_outcome | partially_covered | test_no_outcome | expected_outcome | Assert the route target escalate for review_graph. |

| graph_wrong_owner | partially_covered | test_wrong_graph | functionality | Target workflow.py::review_graph. Use a supported graph invocation or validated explicit owner binding. |

| graph_ambiguous | partially_covered | jsonl_conflicting | functionality | Target workflow.py::review_graph. Use a supported graph invocation or validated explicit owner binding. |

| shared_scope | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target app.py::shared. Exercise the explicit condition (value == 'bad'). Explicitly assert LookupError. |

| unknown_scope | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target app.py::unregistered. Exercise the explicit condition (not value). Explicitly assert RuntimeError. |

| no_candidates | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target app.py::only_alpha. Exercise the explicit condition (not value). Explicitly assert ValueError. |

| wrong_condition | partially_covered | test_wrong_condition | condition | Exercise the explicit condition (amount < 0). |

| wrong_exception | partially_covered | test_wrong_exception | expected_outcome | Explicitly assert RuntimeError. |

| invocation_no_assertion | partially_covered | test_partial | expected_outcome | Explicitly assert ValueError. |

| name_only | potentially_uncovered | test_name_only_ModelRetry | functionality, condition, expected_outcome | Target agent.py::validate_refund. Exercise the explicit condition output.amount > 500. Explicitly assert ModelRetry. |

| multiple_conditions | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Target agent.py::refund. Exercise the explicit condition (amount > 1000). Explicitly assert RuntimeError. |

| jsonl_exception_text | partially_covered | line_2 | condition, expected_outcome | Exercise the explicit condition output.amount > 500. Explicitly assert ModelRetry. |

| pydantic_exception_text | potentially_uncovered | retry | functionality, condition, expected_outcome | Target agent.py::validate_refund. Exercise the explicit condition output.amount > 500. Explicitly assert ModelRetry. |

| unsupported_dynamic | potentially_uncovered | test_unrelated, test_negative_refund, test_wrong_condition | functionality, condition | Review the unavailable, incomplete or unsupported evidence before deciding whether to add a verification scenario. |

| incomplete_scan | potentially_uncovered | no candidates | functionality, condition, expected_outcome | Review the unavailable, incomplete or unsupported evidence before deciding whether to add a verification scenario. |

## Final validation and file manifest

Baseline: **770 tests passed**. Final: **810 tests passed**, including 40 new
M11 tests. Ruff lint and formatting (171 Python files), production mypy (35
modules), audit mypy (15 modules), and `git diff --check` pass. Documentation
fences and relative links validate. All eight current technical audit reports
regenerate byte-for-byte unchanged; all nine historical audit hashes, including
the archived M10.2d study, match. Two new guidance audit regenerations are identical
to the saved report.

Compatibility tests preserve raw behavior/eval inventories, IDs/fingerprints,
assessment status/confidence/matches/dimensions, M9 outputs, scope membership and
finding selection across 20 saved snapshots. Read-only findings/review views
preserve database bytes, feedback, lifecycle data and calculated metrics. Three
previous verbose-output assertions now request `--details`; no historical source
expectation or technical snapshot was rewritten to accept a presentation change.

The installed CLI was checked against a disposable public Pydantic AI example:
`scan`, default/detailed `findings`, scoped scan JSON, supplied-solution rescan and
metrics JSON all worked. Actual guidance identified `validate_refund`, condition
`decision.refund_amount > 500`, exception `ModelRetry`, and owner
`agent.py#refund_agent`. The original
`finding_f232f8c4fbb9aae3723cde30` moved from `potentially_uncovered`/`open` to
`covered`/`resolved`; confirmed impact remained false. The covered metrics export
contained guidance without source excerpts. No target code or tests were executed.

M11 is technically ready for inclusion in the next release. No implementation
blocker remains from these checks; independent engineer validation of usefulness
is still pending. No release, version bump, commit, push or tag was performed.

| Created or modified file | Purpose |
|---|---|
| [README.md](../README.md) | Discover concise guidance and the two `--details` options. |
| [requirements.md](../requirements.md) | M11 presentation and compatibility contract. |
| [docs/finding-actionability-baseline.md](finding-actionability-baseline.md) | Pre-change developer-experience study and actual old output excerpts. |
| [docs/finding-quality-actionability.md](finding-quality-actionability.md) | Design, mappings, comparisons, limitations, validation and manifest. |
| [docs/finding-actionability-audit.json](finding-actionability-audit.json) | Deterministic claim/evidence/action audit. |
| [docs/verification-evidence.md](verification-evidence.md) | Guidance versus unchanged M8 judgments. |
| [docs/agent-scope-controls.md](agent-scope-controls.md) | Scoped presentation-copy guidance contract. |
| [docs/rejection-provenance-enrichment.md](rejection-provenance-enrichment.md) | Compact versus full provenance presentation. |
| [src/agentguard/models.py](../src/agentguard/models.py) | Typed guidance/gaps and optional finding presentation field. |
| [src/agentguard/guidance.py](../src/agentguard/guidance.py) | Pure generation, conservative actions and rendering. |
| [src/agentguard/cli.py](../src/agentguard/cli.py) | Compact scan/findings/review presentation; full diagnostic options. |
| [src/agentguard/scopes.py](../src/agentguard/scopes.py) | Attach guidance after full persistence and membership classification. |
| [src/agentguard/scope_reporting.py](../src/agentguard/scope_reporting.py) | Concise in-scope guidance with unchanged unknown diagnostics. |
| [src/agentguard/metrics/calculator.py](../src/agentguard/metrics/calculator.py) | Optional reference-only guidance in export; no calculation changes. |
| [tests/test_guidance.py](../tests/test_guidance.py) | 40 claim, uncertainty, JSON, scope, persistence, lifecycle and audit tests. |
| [tests/test_cli.py](../tests/test_cli.py) | Preserve full-diagnostic assertions using `--details`. |
| [tests/test_rejection_provenance.py](../tests/test_rejection_provenance.py) | Preserve verbose provenance assertions using `--details`. |
| [tests/fixtures/actionability_audit/inventory.json](../tests/fixtures/actionability_audit/inventory.json) | Independent source facts, actions, evidence and uncertainty expectations. |
| [tests/fixtures/actionability_audit/baseline.json](../tests/fixtures/actionability_audit/baseline.json) | Frozen pre-presentation traces/assessments and technical compatibility hashes. |
| [tools/behavior_audit/actionability_cases.py](../tools/behavior_audit/actionability_cases.py) | Curated evidence views through the existing matcher. |
| [tools/behavior_audit/actionability.py](../tools/behavior_audit/actionability.py) | Independent claim validation and reproducible audit command. |

Reproduce with:

```bash
python -m tools.behavior_audit.actionability --output docs/finding-actionability-audit.json
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```
