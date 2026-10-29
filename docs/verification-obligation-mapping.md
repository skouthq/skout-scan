# Verification obligation mapping — M10.2d

This is a development-only contract study. No production extraction, matching,
coverage assessment, finding, persistence, comparison, CLI, or JSON behavior changes.

## Three separate concepts

A **structural relationship** records source-backed wiring: a registration,
callback, executor, dispatch target, delegation, or handler-local call. It proves
neither execution nor test coverage.

A **verification obligation** is a concrete observable claim with explicit
functionality, condition and outcome. Eligibility means that a deterministic
claim can be stated; it does not mean that the existing matcher can assess it,
that it is important in production, or that it warrants a high-confidence finding.

**Verification evidence** is an extracted `EvalScenario` of a qualifying M8
source/category pair. Pytest tests, JSONL cases and Pydantic Evals cases remain
candidates until functionality, condition and expected outcome are verified.
Requirements, runtime guardrails and quality observations cannot establish coverage.
A test name, expected field, registration or source span alone is insufficient.

## Prototype and eligibility rules

[obligations.py](../tools/behavior_audit/obligations.py) consumes only existing
`BehaviorExtractionResult` models, canonical capabilities, typed relationships,
conditions/actions and source references. It does not read or parse source,
re-extract callback bodies, trace helpers, interpret prompts or inspect tests.
The separate audit runner uses existing repository discovery, extraction, eval
parsing and M8 matching; it writes only an explicitly selected report.

[Audit-only models](../tools/behavior_audit/obligation_models.py) retain candidate
and optional obligation identities, origin links, parent/target identities,
claim type, functionality/condition/outcome, source evidence, required verification
dimensions, reason code, matcher contract, existing behavior correspondence,
structural guards, uncertainty and raw mapping count. Eligible claims require
explicit facts; context and abstentions cannot have obligation IDs.

| Eligibility | Meaning |
|---|---|
| `eligible` | Explicit source facts support a concrete testable claim; evidence compatibility is assessed separately. |
| `context_only` | Wiring is known but does not independently provide an observable behavioral contract. |
| `insufficient_evidence` | A target, condition, parent proof, available behavior or other required typed fact is missing. |
| `unsupported` | An extracted handler/control form lacks the approved interpretation contract. |
| `ambiguous` | Existing provenance resolution is ambiguous; no target/obligation is guessed. |

Every record also distinguishes a new obligation, existing behavior enriched with
provenance, structural context, or unsupported/uncertain interpretation. Resolved
registration alone never becomes a behavioral obligation. Existing guarded raises
can be enriched only through resolved tool or validator registrations. Existing
conditional graph transitions can be enriched through resolved graph-owner links;
that association does not claim that a particular callback produced a state change.

M10.2c literal dispatch permits the narrow claim that, **at the recorded lookup
site**, a literal registry key selects its known target. All extracted control
conditions remain attached. It does not establish which dispatcher argument
supplies that key, whether the site is reached, or what the handler returns.

An explicit exception fallback permits the claim that, **if the recorded handler
is entered under its preserved conditions**, it invokes the named local fallback.
It does not establish primary failure, exception reachability, propagation,
fallback success, or recovery. Missing handler context abstains.

## Decision matrix and source evidence

The sources below are pinned by the independent inventory. Decisions are about
these extracted facts, not all possible implementations of each framework.

| Relationship | Default eligibility | Additional facts needed | Matcher compatibility | Main risk / source |
|---|---|---|---|---|
| `constructor_tool` | Context only | Existing explicit guarded raise/outcome on the same canonical callable | Supported rejection shapes can reuse M8 | Owner fanout: [shared callable](../tests/fixtures/obligation_audit/agent.py#L8), [bound registrations](../tests/fixtures/registration_audit/bound.py#L16) |
| `decorator_tool` | Context only | The same explicit implementation facts; do not duplicate constructor registration | Existing behavior dependent | Registration is not outcome proof: [tool decorator](../tests/fixtures/obligation_audit/agent.py#L8) |
| `graph_node_callback` | Context only | Existing conditional-transition fact; callback state transformations require additional typed extraction | Conditional routes need ownership binding tightened; no new callback-state contract | Wrong graph/helper can match: [node wiring](../examples/langgraph-agent/workflow.py#L39), [conditional routes](../examples/langgraph-agent/workflow.py#L47) |
| `task_agent_executor` | Context only | Independently extracted observable task behavior and verified output, not description text | Not assessable from assignment | Expected-output strings are configuration: [CrewAI tasks](../examples/crewai-agent/crew.py#L26), [shared executors](../tests/fixtures/orchestration_audit/crew.py#L7) |
| `output_validator_callback` | Context only; explicit rejection may be eligible | Existing condition, `raise ModelRetry`, same callback identity, available source evidence | Tested pytest rejection shapes can reuse M8 | False verification from invocation alone: [validator](../examples/pydantic-ai-agent/agent.py#L34), [controlled validators](../tests/fixtures/orchestration_audit/validators.py#L7) |
| `literal_dispatch` | Eligible only for a resolved key-to-target selection claim | Proven parent, immutable-under-contract registry, literal key, target definition, call site and guards | New matcher contract required | Adjacent key/helper assertion is not route proof: [literal routes](../tests/fixtures/delegation_audit/dispatch.py#L14) |
| `one_hop_delegation` | Context only | Independently extracted observable parent contract; explicit child-to-parent semantics if ever proposed | Not assessable from the edge | Internal failure propagation is unknown: [Storage.fetch](../tests/fixtures/delegation_audit/adapter.py#L9) |
| `exception_fallback` | Eligible only for a resolved conditional invocation claim | Known handler condition, local target, parent proof and call/handler references | New matcher contract required | Directly testing the fallback does not prove the parent handler invokes it: [handlers](../tests/fixtures/delegation_audit/fallback.py#L14) |

Callback identity, graph edge, conditional route, state transformation and failure
are distinct claims. In particular, an explicit returned dictionary in source
is not a new typed behavior available to this prototype. It is not reparsed to
manufacture one. Likewise, a delegate definition containing `LookupError` does
not establish an agent-facing propagated failure.

## Independent ground truth and method

[inventory.json](../tests/fixtures/obligation_audit/inventory.json) pins sources,
source anchors, expected eligibility, rationale, matching requirements, existing
behavior correspondence, uncertainty and human-review status. It uses all three
public examples, existing M10.2a–c controlled fixtures, internal-helper negatives,
and one small shared-rejection fixture. Easentic is not used.

The initial source-first decisions and evidence controls were authored before the
mapping prototype. Follow-up review filled four negative-control omissions from
previously pinned source/prior audit expectations and corrected two source-anchor
errors. No positive eligibility decision was changed to fit prototype output.
Original M10.1–M10.2c fixture sources and expectations are unchanged. The audit
asserts source hashes and anchor spans and reports unreviewed extractions rather
than counting them as precision successes. A test deliberately changes expected
eligibility and verifies that prototype output stays identical while audit
agreement falls. These are source-curated decisions from this coding task; explicit
`human_review_status` is `pending`. No independent human sign-off, second-reviewer
agreement or production-wide accuracy is claimed.

The eval artifacts are deliberately controlled static inputs, including missing
assertions, wrong conditions and wrong targets. They are not executed, and this
report does not claim those target tests pass. Pytest runs the scanner's regression
tests, not these evidence artifacts.

## Pattern-level results

[Structured report](verification-obligation-audit.json) contains every candidate,
source reference, expected decision, audit outcome and evidence experiment.

| Primary origin kind | Reviewed decisions correct | Eligible precision | Eligible recall |
|---|---:|---:|---:|
| Constructor tool | 10/10 | 1/1 | 1/1 |
| Decorator tool | 2/2 | 0/0 | 0/0 |
| Graph callback | 12/12 | 2/2 | 2/2 |
| Task executor | 8/8 | 0/0 | 0/0 |
| Validator callback | 6/6 | 2/2 | 2/2 |
| Literal dispatch | 4/4 | 3/3 | 3/3 |
| One-hop delegation | 9/9 | 0/0 | 0/0 |
| Exception fallback | 4/4 | 2/2 | 2/2 |
| Total | 55/55 | 10/10 | 10/10 |

A `0/0` means there is no eligible obligation in that group, not perfect precision.
For a multi-kind existing callable, the deterministic primary kind is used once
for grouping; all actual origin IDs remain available. The shared rejection has
constructor and decorator provenance but is counted once under constructor.

There are **10 eligible claims**: three existing explicit rejections, two existing
conditional graph routes, three new literal selections, and two new conditional
fallback invocations. Five enrich existing behaviors; five would need new future
obligation representations. The remaining **45** comprise 28 context-only,
11 insufficient-evidence, two unsupported and four ambiguous records.

| Quality measure | Result | Interpretation |
|---|---:|---|
| Eligibility precision | 10/10 | Reviewed eligible claims with correct independently expected decisions |
| Eligibility recall | 10/10 | Independently expected eligible claims correctly mapped |
| Source traceability | 55/55 | Each candidate has complete valid source references |
| Individual source-reference accuracy | 134/134 | Real file, bounded span and matching excerpt internally |
| Abstention correctness | 45/45 | Expected exclusions remain ineligible |
| Actionability proxy | 10/10 | Each eligible claim expresses a concrete testable scenario; no engineer intent measured |
| Duplicate mapping rate before consolidation | 9/64 | Shared-owner join fanout and equivalent branch/failure mappings |
| Duplicate candidates after consolidation | 0/55 | No residual duplicate obligation identity among audited candidates; also 0/10 among eligible claims |
| Unreviewed candidates | 0 | No extra extraction silently enters precision |

Do not combine these measures with original behavior recall, relationship recall,
or any product coverage percentage.

## Deduplication and identity

Registration context records remain distinct source facts without obligation IDs.
For observable existing facts, group by source file, subject, normalized condition,
and action kind/target/outcome. Prefer the existing `tool_failure` ID over its
identical conditional-raise representation, retaining both behavior IDs and all
registration owners as provenance. Shared registrations create no owner-specific
obligations without owner-specific behavior facts. Exact repeated extraction
records and input ordering do not change output. Different literal keys remain
different obligations even if they share a target.

Existing obligations retain the existing behavior ID; no finding ID is created.
New audit-only IDs hash a versioned M10.2c relationship ID under
`prototype-obligation-v1`, with an `audit_obligation_` prefix. They inherit parent,
key/handler, target, call-site and structural-context stability without line numbers,
comments, whitespace, temporary roots or timestamps. Identities are repository-local,
not a global cross-repository identity claim. Paths/symbol moves or material
relationship changes may change identity. Owner renames change provenance links
but preserve an existing rejection obligation's behavior ID when its behavior
identity is unchanged.

No prototype identity is persisted. Future identity, removal, comparison and
feedback rules are specified in the [integration plan](verification-obligation-integration-plan.md).

## Evidence sufficiency results

The audit passes exact existing `Behavior` and extracted `EvalScenario` objects
to the unmodified matcher, one scenario at a time. It does not synthesize
`Behavior` instances for new relationship claims and contains no replacement
coverage evaluator.

- **Three existing rejections:** current M8 is sufficient for the tested pytest
  shape: matching callable, matching literal condition and explicit expected
  exception. Merely invoking the callable remains partial. Wrong condition,
  wrong callable, helper-only evidence and similar names do not establish coverage.
  The public refund example's supplied solution independently preserves the
  obligation ID and changes its existing M8 assessment to covered.
- **JSONL/Pydantic Evals:** supported source/category qualification is necessary
  but not sufficient. An `expected`/`expected_output` exception string alone does
  not create M8 expected-exception assertion evidence; neither control covers
  the explicit rejection. Arbitrary evaluators are not interpreted.
- **Existing conditional routes:** correct route input plus expected route works;
  missing outcome and adjacent route do not cover the selected route. However,
  wrong-graph and helper-only JSONL controls, and a wrong-owner Pydantic Evals
  case, are also marked covered. The current non-tool branch matcher does not
  require matching graph identity. These three disagreements remain reported;
  production matching is unchanged.
- **Literal selections and exception fallbacks:** 12 controls include selection/
  fallback spies, no outcome, adjacent route or wrong exception, helper-only,
  wrong callable and similar-name cases. They are parsed and source-backed but
  not assessed: no existing behavior represents the key/target or handler/target
  claim faithfully. The prototype labels the missing contract rather than
  converting either claim into generic tool invocation coverage.

There are **18/21 agreements** for experiments actually run through M8 and
**12 additional unassessed controls**. These are evidence-sufficiency experiments,
not eligibility precision. Three eligible rejections are tagged
`existing_matcher_sufficient`; the two existing routes and five new relationship
claims are tagged `matcher_extension_required`. All context/abstention records
are `not_assessable`. These tags describe bounded evidence shapes, not universal
correctness across arbitrary tests, aliasing or data flow.

## Compatibility, reproduction and limits

The pre-change baseline was **549 passing tests**. Complete saved hashes cover
behaviors/IDs/fingerprints, canonical capabilities, all M10.2a–c relationship fields,
M8 assessments/explanations and finding IDs for the public examples and controlled
fixture roots. Existing public-example M9 unchanged/solution comparisons and
feedback/lifecycle tests remain in the full suite. The four earlier audit reports
must regenerate byte-for-byte with unchanged metrics: behavior recall 30/50,
registration recall/precision 8/8, orchestration recall/precision 20/20, and
delegation recall/precision 12/12. No schema migration or live-state deletion exists.

```bash
python -m tools.behavior_audit.obligation_audit --output docs/verification-obligation-audit.json
pytest tests/test_obligation_mapping.py
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```

The new audit output also reproduces byte-for-byte. Isolation tests prohibit
network/subprocess/SQLite access, append an executable trap to a disposable source,
preserve existing state bytes, and verify no new `.agentguard/` state is created.
The pure mapper works with file reads blocked. Original fixtures, public examples,
source code, version, README, CLI and persisted feedback remain unchanged.

This study does not establish runtime reachability, deployment importance, general
semantic equivalence, complete mutation/alias reasoning, callback state outputs,
child exception propagation, or recovery success. It adds no LLM, telemetry,
network service, new production finding, matching threshold, lifecycle state or
M10.3 relevance rule. Eligibility can be precise within this curated corpus while
still being a poor predictor of whether an engineer wants a test; that requires
separate real-world validation.

## Validation and changed files

Actual baseline: **549 passed**. Final full suite: **586 passed**, including 37
new obligation tests. `ruff check .`, `ruff format --check .` (139 files),
`mypy src/agentguard` (29 modules), `mypy tools/behavior_audit` (10 modules), and
`git diff --check` pass. All five reports regenerate byte-for-byte twice; the
four historical report files are byte-identical to the pre-M10.2d baseline.
All experiment source references, documentation links and code fences validate.
No production files, original examples/fixtures/reports or release metadata changed.

| New/modified file | Purpose |
|---|---|
| [requirements.md](../requirements.md) | Development-only M10.2d acceptance and isolation contract. |
| [verification-obligation-mapping.md](verification-obligation-mapping.md) | Decisions, evidence experiments, metrics, identity and limitations. |
| [verification-obligation-integration-plan.md](verification-obligation-integration-plan.md) | Prioritized future recognition, evidence, identity and lifecycle contracts. |
| [verification-obligation-audit.json](verification-obligation-audit.json) | Deterministic candidates, audit decisions and actual M8 observations. |
| [obligation_models.py](../tools/behavior_audit/obligation_models.py) | Typed audit-only candidates, evidence requirements and independent corpus schema. |
| [obligations.py](../tools/behavior_audit/obligations.py) | Pure mapping and consolidation of existing extracted facts. |
| [obligation_audit.py](../tools/behavior_audit/obligation_audit.py) | Read-only source-pinned evaluation, actual M8 experiments and report generation. |
| [test_obligation_mapping.py](../tests/test_obligation_mapping.py) | 37 eligibility, identity, evidence, isolation, compatibility and corpus validation tests. |
| [inventory.json](../tests/fixtures/obligation_audit/inventory.json) | Independently curated expected decisions, duplicate notes, evidence controls and human-review status. |
| [compatibility_baseline.json](../tests/fixtures/obligation_audit/compatibility_baseline.json) | Pre-change full production-inventory and assessment hashes/finding identities. |
| [agent.py](../tests/fixtures/obligation_audit/agent.py) | Shared registered callable with an explicit guarded rejection. |
| [evidence.py](../tests/fixtures/obligation_audit/tests/evidence.py) | Pytest-shaped positive/negative evidence artifacts, never executed. |
| [routes.jsonl](../tests/fixtures/obligation_audit/evals/routes.jsonl) | Route ownership, adjacent condition, missing outcome and expected-exception controls. |
| [pydantic_cases.py](../tests/fixtures/obligation_audit/evals/pydantic_cases.py) | Pydantic Evals qualification versus actual exception/route sufficiency controls. |
