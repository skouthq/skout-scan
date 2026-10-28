# M10.1 — Agent behavior discovery audit

This development-only audit measures whether the existing extractor discovers a
source-curated agent execution contract. It does **not** measure agent eval
coverage, change production behavior, or create findings. Package version at the
audit is 0.1.9; the existing regression baseline was **266 passing tests**.

## Reproduce

From a development checkout with the existing development dependencies installed:

```bash
python -m tools.behavior_audit --output docs/behavior-discovery-audit.json
pytest tests/test_behavior_audit.py
```

The utility calls the production `scan_repository` and `extract_behaviors`
functions. Its exact correspondence checks compare records, not Python programs;
it is not a second behavior extractor. It never calls eval extraction, matching,
finding selection, SQLite, feedback, Git, target imports, or network services.
The only optional write is the explicit report destination. Output inside an
audited repository, its state directory, or the inventory itself is rejected.

## Current extraction pipeline

Repository discovery loads local configuration, applies repository-relative
includes/excludes, sorts artifacts, and does not follow symlinks. Python artifacts
are parsed as AST, never imported. Test paths are excluded from behavior discovery.
The generic extractor and framework-specific CrewAI/Pydantic AI extractors return
typed behaviors, source evidence, warnings, errors, and completeness.

Current behavior types are `tool_invocation`, `tool_failure`,
`conditional_branch`, `workflow_transition`, `fallback`, and `escalation`.

- Generic module-level functions qualify through decorators ending in `tool` or
  `function_tool`, literal collections assigned to `tools`/`*_tools`, call keyword
  `tools=[function]`, or `.bind_tools([function])`. These generic rules do not
  establish framework import provenance. Bound methods are not resolved there.
- Inside recognized tools, explicit conditions, raises, failure returns, and
  escalation/handoff calls can produce records. A helper call is not a recovered
  helper contract. Exception-handler fallback relationships are not fully modeled.
- LangGraph graph edges and literal conditional route maps produce transitions;
  node callback execution contracts are not independently represented. Retry,
  fallback, and escalation categorization uses existing structural/name rules;
  the audit adds no such rules.
- CrewAI supports known tool definitions, Agent/Task tool lists, task context,
  sequential task order, supported CrewBase/Flow declarations, and static
  configuration. A tool callable and its owner-specific availability records are
  distinct relationships. Task-to-Agent execution assignment is not equivalent
  to task ordering or tool availability.
- Pydantic AI supports known Agent imports/construction, recognized tool and
  output-validator registration, structured output metadata, and explicit
  ModelRetry branches/outcomes. Dynamic tools generate warnings/incompleteness;
  their runtime contents are not guessed. A validator's branch/failure records do
  not independently represent invocation of the validator callback itself.

Behavior identity uses versioned hashes of normalized structural identity,
including source type, relative path, subject, behavior type, condition, and
action. Fingerprints use AST structure without physical line attributes.
Line/formatting edits therefore differ from a path move or material contract
change. Evidence comes from AST source segments and physical spans. Framework
extractors retain their existing identity/evidence contracts. Audit expectation
IDs are human-authored local labels, **not** replacements for production IDs.

M8 assesses typed invocation, condition, outcome, and verification evidence;
registration alone does not establish tested coverage. Finding selection and
SQLite lifecycle updates occur downstream in ordinary scanning, outside this
utility. M9 compares extracted inventories and fingerprints; it cannot directly
compare a contract absent from both inventories. None of those contracts changed.

## Ground truth and methodology

The independent inventory is
[`inventory.json`](../tests/fixtures/behavior_audit/inventory.json). It contains
**58** manually authored expectations across **14** repositories: all three public
examples and 11 minimal controlled fixtures. Expected contracts and selectors were
written before the first audit run, from source rather than actual behavior IDs
or scanner output. Python source files are pinned by SHA-256; anchors and line
spans are checked before scanning. Formatting-only source positions/hashes were
refreshed before the first run. One later metadata clarification marks negative
controls `outside_agent_contract` rather than `in_scope`; it changed no expected
discovery outcome, selector, classification, or structural metric.

A meaningful behavior is an operation, decision, condition, transition, or failure
path in an externally observable or explicitly orchestrated agent contract.
Evidence must establish registration, wiring, or dispatch. Ordinary helpers and
unused functions are negative controls. The small `agent_contract.py` fixtures
explicitly store and dispatch their registered callables, so their agent-facing
contract does not depend on the spelling of a factory name. They are inspected,
never executed. The public examples are unchanged.

The inventory is a **single-reviewer, bounded contract**, not an exhaustive list
of every behavior a human could infer. Atomic conditions and outcomes are separate
expectations. Callable capabilities and owner relationships are also separate;
shared availability is not automatically duplicate behavior.

Correspondence requires exact relative file, subject, symbol, type, optional
action target/outcome, valid source evidence, and an intersecting curated span.
Multiple candidates or competing expectations are ambiguous. Parent/container
evidence can support `partial`, never full discovery. An absent expectation under
incomplete extraction remains ambiguous. Uncertain expectations stay uncertain.
Unmapped extractions remain `unexpected_unreviewed`, excluded from precision until
reviewed; this corpus currently has none. No fuzzy semantic correspondence is used.

## Corpus and architecture results

| Corpus | Confirmed expected | Correct | Missed | Partial | Ambiguous confirmed | Reviewed actual |
|---|---:|---:|---:|---:|---:|---:|
| Public LangGraph | 8 | 3 | 5 | 0 | 0 | 3 |
| Public CrewAI | 10 | 8 | 2 | 0 | 0 | 8 |
| Public Pydantic AI | 5 | 4 | 0 | 1 | 0 | 4 |
| Controlled fixtures | 27 | 15 | 6 | 4 | 2 | 17 |
| Total | 50 | 30 | 13 | 5 | 2 | 32 |

Controlled fixtures cover decorated tools, plain registration, adapter delegation,
shared tools, literal skill dispatch, graph routing, explicit failure/fallback,
internal helpers/test utilities, multiple bound-method agent entries, dynamic
registration, and non-agent tool-like APIs. Naming-independence tests move **all
11** controlled structures under each of `module`, `v1`, `v2`, and `legacy`.
Recognition/classification remains equivalent; paths and IDs need not remain equal.
The neutral corpus requires no legacy code or active-directory inference.

## Discovery measurements

- **Overall recall: 30/50 = 60%.** All 50 confirmed positive expectations count,
  including 20 outside currently supported extraction patterns. Of those 20,
  13 are missed, five partial, and two ambiguous because extraction is incomplete.
- **Supported-pattern recall: 30/30 = 100%.** This is the documented supported
  subset of this small corpus, not a general framework support guarantee.
- **Reviewed structural precision: 30/32 = 93.75%.** The numerator is structurally
  valid agent-facing or orchestrated-internal records; the denominator is all
  reviewed raw extraction records, counting distinct owner relationships once.
  There are zero excluded unreviewed extraction records.
- Role-specific reviewed precision is **16/16 agent-facing**, **14/14
  orchestrated-internal**, and **0/2 implementation-detail promotions**. Unknown
  role has denominator zero and rate null.
- Seven negative expectations produce **five correctly absent** and **two
  unexpected promotions**. One additional dynamic capability expectation is
  unconfirmed/uncertain and excluded from the recall denominator.
- Across all 58 expectations: 30 correct, 13 missed, five partial, three ambiguous
  (including that uncertain expectation), two unexpected, five correctly absent.

These are **discovery audit** measurements, not a numeric behavioral test-coverage
percentage. They are not added to `skout metrics`.

### Pattern-level results

`S` = currently supported; `U` = unsupported contract; `N` = negative control.
Ambiguous includes the unconfirmed dynamic expectation; expected counts exclude it.

| Pattern | Expected | Correct | Missed | Partial | Ambiguous | Unexpected | Support |
|---|---:|---:|---:|---:|---:|---:|---|
| adapter_delegation | 3 | 1 | 1 | 1 | 0 | 0 | S,U |
| agent_task_delegation | 2 | 0 | 2 | 0 | 0 | 0 | U |
| bound_method_registration | 2 | 0 | 0 | 0 | 2 | 0 | U |
| conditional_graph_routing | 3 | 3 | 0 | 0 | 0 | 0 | S |
| decorated_tool | 2 | 2 | 0 | 0 | 0 | 0 | S |
| dynamic_registration | 1 | 1 | 0 | 0 | 1 | 0 | S,U |
| failure_and_fallback | 4 | 3 | 0 | 1 | 0 | 0 | S,U |
| graph_node_registration | 8 | 0 | 8 | 0 | 0 | 0 | U |
| internal_helper | 0 | 0 | 0 | 0 | 0 | 0 | N |
| multiple_entry_points | 2 | 2 | 0 | 0 | 0 | 0 | S |
| nonagent_tool_like_api | 0 | 0 | 0 | 0 | 0 | 2 | N |
| plain_registration | 1 | 1 | 0 | 0 | 0 | 0 | S |
| public_crewai_relationships | 6 | 6 | 0 | 0 | 0 | 0 | S |
| public_crewai_tools | 2 | 2 | 0 | 0 | 0 | 0 | S |
| public_graph_routes | 3 | 3 | 0 | 0 | 0 | 0 | S |
| public_pydantic_contract | 4 | 4 | 0 | 0 | 0 | 0 | S |
| registered_callback | 1 | 0 | 0 | 1 | 0 | 0 | U |
| shared_tool | 3 | 1 | 2 | 0 | 0 | 0 | S,U |
| skill_dispatch | 3 | 1 | 0 | 2 | 0 | 0 | S,U |

Full per-repository metrics, expected contracts, actual IDs/references,
classifications, source hashes, uncertainty, and hypotheses are in
[`behavior-discovery-audit.json`](behavior-discovery-audit.json).

## Source-reference accuracy

All **32/32 paths** and **32/32 locations** pass validation; there are **zero
missing references, zero incorrect paths, and zero incorrect locations**.
Validation checks real repository-contained files, bounded line spans, source
text corresponding to each excerpt, and curated span intersection for correct
matches. Tests deliberately corrupt paths, spans, excerpts, and missing evidence;
those never count as full discovery. Text correspondence does not prove runtime
reachability or correct agent registration: the two false promotions have valid
source locations too. The JSON contains references, not source excerpts.

## Confirmed gaps and hypotheses

Observations below are reproduced by the current extractor. Proposed causes are
hypotheses informed by source inspection, not changes made by this milestone.
Every detailed gap row includes its supporting location, feasibility, risk,
observation, separate hypothesis, and downstream impact in the JSON.

| Observation and source | Taxonomy | Root-cause hypothesis / feasibility and risk |
|---|---|---|
| Adapter wrapper found, delegation partial, internal LookupError path missed: `adapter_delegation/app.py:7,17` | `unsupported_adapter_delegation` | Extraction walks the registered body, not the resolved adapter method. Bounded local delegation feasible; recursively promoting every helper would be risky. |
| Shared callable appears once; two owner relationships absent: `shared_tools/app.py:8–9` | `unsupported_registration_pattern` | Generic collection recognition collects function names without retaining registration owners. Literal relationships are feasible; do not duplicate the capability. |
| Dispatcher found; two literal skill routes partial: `skill_dispatch/app.py:18` | `unsupported_skill_dispatch` | Subscript call targets lack explicit per-key dispatch records. A fixed dictionary is tractable; runtime registry mutation is not. |
| Eight graph callback contracts missed across controlled/public graphs; route transitions found: `graph_routing/app.py:21–23`, public `workflow.py:39–46` | `unsupported_registration_pattern` | Edge extraction and node callable registration are separate contracts; node callbacks are not extracted as operations. Explicit local callback mapping is feasible. |
| Timeout→cached fallback partial: `failure_fallback/app.py:16` | `unsupported_adapter_delegation` | Handler context plus delegated target is not retained. Bounded explicit handler edges are feasible; arbitrary exception/data-flow reasoning is not. |
| Two bound-method relationships ambiguous with dynamic-tool warnings: `multiple_entries/app.py:16–17` | `identity_ambiguity` | Receiver/method resolution is unavailable. Known local instances could be supported conservatively; aliasing/rebinding remains uncertain. |
| Two Task→Agent execution assignments missed: public `crew.py:26,33` | `unsupported_registration_pattern` | Tools/context/order are represented, but executor assignment is not. Explicit constructor references are feasible. |
| Registered validator callback only partially represented: public `agent.py:34` | `unsupported_tool_invocation` | Explicit retry branch and failure exist, but no distinct callback invocation contract. A callback must not be mislabeled as an LLM-selected tool. |
| Two non-agent helpers promoted: `negative_controls/app.py:6,18` | `internal_helper_promoted` | Generic `tools=` and decorator terminal-name recognition lack provenance. Registration validation should precede expansion of discovery. |

The unavailable plugin contents in `dynamic_registration/app.py:4` are
`unresolved_dynamic_registration`, **not a confirmed miss**. The declared Agent
is still discovered and the production extractor emits an incomplete warning.

There is no demonstrated `duplicate_behavior_representation` defect in this
corpus: one shared callable is returned, and CrewAI owner relationships represent
different source-backed contracts. There are no confirmed incorrect references.
Those taxonomy categories remain available for future audits; zero observations
are not evidence that they never occur.

### Downstream impact

Missing operations/relationships leave the behavior inventory incomplete. A
missing behavior cannot reach eval matching or actionable finding selection;
this is an extraction gap, **not an observed matcher failure or an immediate
missing-eval finding**. M8 cannot explain the omitted contract, and M9 cannot
directly compare changes to it. Existing parent/callback/route records can still
carry their own explanations and fingerprints; this does not establish complete
representation of their delegated contracts.

False promotions may instead introduce non-agent concerns into matching,
selection, M8 explanations, and M9 comparisons. A correct source location alone
cannot justify the agent relationship. The audit creates no findings and does
not demonstrate that every such record would pass production selection thresholds.

## Relevance and confidence limitations

Actual record roles: **16 agent-facing, 14 orchestrated-internal, two implementation
details, zero unknown roles**. Separate operational annotations: **29 within the
curated agent contract, two outside it, one unknown**. A declared but unattached
framework tool (`decorated_tool/app.py:14`) is structurally valid, while operational
use remains unknown. Registration does not prove deployment, business importance,
active use, or an engineer's willingness to add an eval.

External qualitative feedback reported 152 behaviors, 9,206 pytest scenarios,
17 high-confidence findings, 11 `not_relevant`, six `valid_later`, no `add_eval`,
and findings focused on older LangChain wrappers. This is unverified feedback
from an unavailable current repository. **No Easentic checkout, old calibration
script, or prior Easentic results were used, read, scanned, or treated as ground
truth for this audit.** No reported finding has been independently reproduced.
The feedback motivates questions, not fixture outcomes or directory heuristics.

This small curated corpus, one source reviewer, exact authored selectors, and
synthetic adapter/dispatch fixtures cannot establish production-wide precision
or recall. Supported expectations are deliberately simple and do not cover every
supported syntax. Source hashes pin Python inputs, not a formal semantic oracle.
Local configuration and the installed extractor also affect regeneration;
the golden report detects drift. No second-reviewer agreement, runtime validation,
operational relevance study, or new resolution/impact measurement is claimed.

## M10.2 priorities

See [the extraction plan](m10-2-extraction-plan.md). Priorities are registration
provenance and bound callable relationships, explicit orchestration callback
contracts, and bounded literal dispatch/delegation. They are proposals only;
M10.1 changes no production extractor, matcher, ID, persistence, metrics, or CLI.

## Validation

Harness tests must pass even while discovery gaps remain in the report. Tests
cover negative/unknown/incomplete cases, source corruption, ambiguous identities,
reviewed denominators, report reproducibility, unchanged source/state, no target
execution/network/SQLite, and 44 directory-move variants. Existing public-example
and M8/M9 regressions remain part of the full suite.

Recorded validation results:

| Check | Result |
|---|---|
| Existing baseline before implementation | 266 passed |
| Final full `pytest` | 332 passed (66 audit tests) |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed, 102 files |
| `mypy src/agentguard` | Passed, 26 source files |
| Additional `mypy tools/behavior_audit` | Passed, four audit modules |
| `git diff --check` | Passed |
| Regenerate JSON to a separate temporary file | Byte-identical |
| Relative documentation links | Valid |

The sole test infrastructure adjustment adds the repository root to pytest's
`pythonpath` beside `src`, so the development-only `tools` package can be imported.
It does not change the wheel/sdist configuration or installed CLI. No existing
production or example source file, root README, or version value was changed.

## Changed-file manifest

- [docs/behavior-discovery-audit.json](../docs/behavior-discovery-audit.json)
- [docs/behavior-discovery-audit.md](../docs/behavior-discovery-audit.md)
- [docs/m10-2-extraction-plan.md](../docs/m10-2-extraction-plan.md)
- [pyproject.toml](../pyproject.toml)
- [requirements.md](../requirements.md)
- [tests/fixtures/behavior_audit/adapter_delegation/agent_contract.py](../tests/fixtures/behavior_audit/adapter_delegation/agent_contract.py)
- [tests/fixtures/behavior_audit/adapter_delegation/app.py](../tests/fixtures/behavior_audit/adapter_delegation/app.py)
- [tests/fixtures/behavior_audit/decorated_tool/agent_contract.py](../tests/fixtures/behavior_audit/decorated_tool/agent_contract.py)
- [tests/fixtures/behavior_audit/decorated_tool/app.py](../tests/fixtures/behavior_audit/decorated_tool/app.py)
- [tests/fixtures/behavior_audit/dynamic_registration/app.py](../tests/fixtures/behavior_audit/dynamic_registration/app.py)
- [tests/fixtures/behavior_audit/failure_fallback/agent_contract.py](../tests/fixtures/behavior_audit/failure_fallback/agent_contract.py)
- [tests/fixtures/behavior_audit/failure_fallback/app.py](../tests/fixtures/behavior_audit/failure_fallback/app.py)
- [tests/fixtures/behavior_audit/graph_routing/app.py](../tests/fixtures/behavior_audit/graph_routing/app.py)
- [tests/fixtures/behavior_audit/internal_helpers/app.py](../tests/fixtures/behavior_audit/internal_helpers/app.py)
- [tests/fixtures/behavior_audit/internal_helpers/tests/helpers.py](../tests/fixtures/behavior_audit/internal_helpers/tests/helpers.py)
- [tests/fixtures/behavior_audit/inventory.json](../tests/fixtures/behavior_audit/inventory.json)
- [tests/fixtures/behavior_audit/multiple_entries/app.py](../tests/fixtures/behavior_audit/multiple_entries/app.py)
- [tests/fixtures/behavior_audit/negative_controls/app.py](../tests/fixtures/behavior_audit/negative_controls/app.py)
- [tests/fixtures/behavior_audit/plain_registration/agent_contract.py](../tests/fixtures/behavior_audit/plain_registration/agent_contract.py)
- [tests/fixtures/behavior_audit/plain_registration/app.py](../tests/fixtures/behavior_audit/plain_registration/app.py)
- [tests/fixtures/behavior_audit/shared_tools/agent_contract.py](../tests/fixtures/behavior_audit/shared_tools/agent_contract.py)
- [tests/fixtures/behavior_audit/shared_tools/app.py](../tests/fixtures/behavior_audit/shared_tools/app.py)
- [tests/fixtures/behavior_audit/skill_dispatch/agent_contract.py](../tests/fixtures/behavior_audit/skill_dispatch/agent_contract.py)
- [tests/fixtures/behavior_audit/skill_dispatch/app.py](../tests/fixtures/behavior_audit/skill_dispatch/app.py)
- [tests/test_behavior_audit.py](../tests/test_behavior_audit.py)
- [tools/__init__.py](../tools/__init__.py)
- [tools/behavior_audit/__init__.py](../tools/behavior_audit/__init__.py)
- [tools/behavior_audit/__main__.py](../tools/behavior_audit/__main__.py)
- [tools/behavior_audit/models.py](../tools/behavior_audit/models.py)
- [tools/behavior_audit/runner.py](../tools/behavior_audit/runner.py)

## M10.2a follow-up: registration relationships

The preceding measurements/taxonomy preserve the historical M10.1 analysis. The
JSON report is regenerated against the current extractor. Its original 58
source-first expectations and fixture sources remain unchanged; only observed
results changed. Generic false promotions for the passive local constructor and
identity decorator now become correctly absent. There are 30 actual behavior
records, 30/50 overall recall, 30/30 supported recall, 30/30 reviewed precision,
seven correctly absent controls, and 30/30 correct source references. The 13
missed, five partial, and three ambiguous expectations otherwise remain unchanged.

Separate additive capability/registration records resolve both eligible bound
methods in the original multiple-entry fixture. The original behavior expectations
remain ambiguous under conservative incomplete **behavior assessment**, rather than
being counted as newly discovered invocation behaviors. Their warnings now state
`registration_only_callable` instead of incorrectly calling registration unresolved.
Original custom factories do not gain verified framework ownership.

The new [registration audit](registration-relationships-audit.json) independently
reports 8/8 positive registrations, 8/8 reviewed resolved precision, 2/2 bound
methods, 13/13 reviewed resolution outcomes, zero incorrect ownership promotions,
and 21/21 valid relationship/definition references. Five uncertain/unresolved
outcomes stay outside positive recall/precision. The known shared fixture has one
capability and two owner links. No score combines behavior and relationship recall.

See [the implementation contract](registration-relationships.md) for supported
forms, exclusions, identity/consumer boundaries, public-example compatibility,
and reproduction. Historical file manifests above describe M10.1, not the
additional M10.2a files. No production corpus or Easentic validation is claimed.

## M10.2b follow-up: explicit orchestration contracts

All eight original graph-node callback associations, two CrewAI task executor
assignments, and the Pydantic AI output-validator registration now have resolved
source-backed orchestration relationships. They reuse M10.2a's canonical
capabilities and relationship inventory. They do not become tool invocation or
eval evidence, so original behavior recall/precision remain 30/50 and 30/30;
the historical missing/partial behavior classifications are not rewritten to
manufacture a recall improvement.

The [separate orchestration audit](orchestration-relationships-audit.json) records
20/20 confirmed relationships (LangGraph 12/12, CrewAI 5/5, Pydantic AI 3/3),
20/20 reviewed resolved precision, 28/28 resolution outcomes, and 48/48 valid
source references. Eight unsupported/ambiguous cases remain uncertain and are
excluded from positive recall/precision. No reviewed ownership false promotion
or unreviewed extraction occurs. Existing M10.2a metrics remain unchanged.

Original fixtures and ground truth are unchanged. See the
[orchestration contract](orchestration-relationships.md) for source-provenance,
identity, consumer boundaries, independent inventories, and pre/post compatibility
checks. New structured records are present in the regenerated inventory JSON;
ordinary behavior assessments, finding IDs, M8/M9 semantics, and persistence are
unchanged. No production-wide accuracy or runtime execution claim is made.
