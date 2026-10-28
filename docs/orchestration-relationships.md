# Explicit orchestration relationships (M10.2b)

## Additive inventory and consumer contract

M10.2b extends the existing `RegistrationRelationship` and extraction inventory.
The additional kinds are `graph_node_callback`, `task_agent_executor`, and
`output_validator_callback`. Optional `registered_identity`, `executor_identity`,
and default-empty `limitations` fields preserve old payload compatibility.
Callbacks reuse the canonical `CallableCapability` identity and definition model.
CrewAI executor references identify unique agent assignments, not callable tools.

Registration source and resolved definition evidence remain distinct. A known
owner with an unsupported/dynamic target can retain an unresolved/ambiguous
source-backed record without an invented definition. Arbitrary graph-like,
task-like, or validator-like objects do not establish framework provenance.

The existing behavior, assessment, finding, M8 evidence, SQLite, metric, CLI JSON,
and M9 delta consumers remain unchanged. Relationships are not execution or eval
verification evidence. No callback/body is promoted into new coverage behavior.
Source-reference metadata may change after line movement; IDs and fingerprints
exclude source positions, comments, whitespace, scan order, and absolute roots.
Tool-registration identity generation from M10.2a is unchanged.

The implementation reuses the M10.2a source index, resolution statuses, capability
identity, source evidence, relationship model, and extraction tuple. New callback
registration recognition is isolated from behavior/edge/failure extraction.

Baseline before implementation: 402 tests passed; original behavior recall 30/50,
reviewed precision 30/30; registration recall/precision 8/8; registration source
references 21/21. Public-example behavior/assessment/finding and M9 comparison
snapshots were captured before implementation, including unchanged inventories
and supplied solution evals in disposable copies.

## Supported source contracts

All three forms require unique file-local module bindings and known framework
imports. Direct imports, `as` import aliases, and qualified module imports reuse
`SourceIndex.resolve_import`. Attribute/assignment mutations and rebinding reuse
M10.2a's conservative invalidation rules. Tool and orchestration extraction share
one index instance per artifact.

### LangGraph nodes

Supported owners are direct assignments of `langgraph.graph.StateGraph` or
`langgraph.graph.state.StateGraph`. A direct module-level call of the exact form
`graph.add_node("literal", callback)` binds a literal node name to a unique local
sync/async function. The node's `registered_identity` is scoped by
`owner_identity`; node names alone are not globally unique. A callback shared by
multiple nodes/graphs has one canonical capability per definition and distinct
owner/node links. Duplicate equivalent registrations collapse. Conflicting
callbacks for the same owner/node remain ambiguous instead of guessing which
registration wins or whether execution would reject the graph.

Initially, keyword-form registrations, extra registration arguments, fluent
chains, nested/conditional calls, bound graph methods, lambdas, generated functions,
and imported/unresolved functions are outside the resolved contract. Dynamic node
names retain unresolved source-backed records when their owner is known. An
arbitrary object's `add_node` method or an unknown graph constructor does not
establish a LangGraph relationship.

### CrewAI task executors

Supported Task constructors are `crewai.Task` and `crewai.task.Task`. An explicit
`agent=worker` argument resolves only when `worker` uniquely names a direct local
`crewai.Agent` or `crewai.agent.Agent` assignment. The task is the relationship
owner and registered identity; its executor is the canonical `file#worker`
identity. Several tasks can reference that identity without creating duplicate
agent or callable capabilities.

Task registration evidence points to the actual `Task(..., agent=...)` call;
executor definition evidence points to the known Agent assignment. Context,
ordering, crew membership, and process settings never imply an executor.
Computed/imported agent instances remain unresolved; reassigned task/agent owners
remain ambiguous. Unknown Task constructors do not establish CrewAI provenance.

### Pydantic AI output validators

A direct module-level `@agent.output_validator` on a unique local sync/async
function creates an `output_validator_callback` relationship when `agent` is a
uniquely assigned `pydantic_ai.Agent` or `pydantic_ai.agent.Agent`. Registration
and function-definition references are separate. The registered identity is the
qualified local callback; the capability uses the same canonical identity scheme
as tools, without becoming an LLM-selectable tool or a new invocation behavior.

Called/computed decorators, nested callbacks, unknown factory receivers, and
unrelated decorators do not qualify. Stacked unsupported decorators or rebound
callbacks remain uncertain. A previously known but reassigned agent retains an
ambiguous registration without an invented callable definition. Conditions,
ModelRetry outcomes, and existing failure behaviors remain separate and unchanged.

## Identity and resolution

New links use the existing `registration_` prefix with a separate versioned
`orchestration-v1` canonical payload: relative path, kind, framework provenance,
owner, registered node/task/validator, and resolved callable/executor identity.
Raw target structure distinguishes unresolved expressions; unresolved graph
registrations also include normalized registration structure so different dynamic
node expressions do not collapse. Source positions and absolute roots never
participate. Owner, literal node, and target changes are material; whitespace,
comments, and unrelated line shifts are not. Source-file moves and symbol renames
may change identities; rename-invariant tracking is not claimed.

Fingerprints cover normalized registration/target structure, not callback bodies.
Task fingerprints isolate the `agent=` relationship so edits to context or task
descriptions do not masquerade as executor changes. Full call source remains in
evidence. A relationship fingerprint is not a proof of implementation equivalence.

Resolved callable links retain real registration and definition references. Task
links instead retain a known agent declaration and `executor_identity`.
Unresolved/ambiguous links retain real registration evidence with explicit reason
and limitations, without invented targets. If even framework-owner provenance is
unknown, no relationship is confidently inferred from method spelling alone.

The new optional relationship fields default to null/null/empty for old payloads.
Existing tool relationship IDs, fingerprints, resolution, references, and other
fields remain unchanged. Direct serialization of the internal model adds these
fields and admits three new kinds; internal consumers must tolerate additive
fields and ignore kinds they cannot consume. Public CLI JSON is unchanged.

## Independent audit and compatibility

The new source-first inventory is
[`inventory.json`](../tests/fixtures/orchestration_audit/inventory.json). Its
anchors and SHA-256 pins cover the original graph routing fixture, all three
primary public examples, and five new controlled source files. The 28 expected
outcomes were authored before scanning that corpus; formatting-only pins/anchors
were refreshed before its first run. No actual relationship IDs were used to
construct expectations. The original M10.1/M10.2a fixture sources and inventories
were not changed.

The separate [orchestration audit](orchestration-relationships-audit.json) reports:

| Contract | Previously represented orchestration links | Current confirmed links |
|---|---:|---:|
| Original graph callback targets | 0 | 8/8 |
| Original CrewAI executor targets | 0 | 2/2 |
| Original Pydantic validator target | 0 | 1/1 |
| All curated LangGraph positive cases | No model support | 12/12 |
| All curated CrewAI positive cases | No model support | 5/5 |
| All curated Pydantic AI positive cases | No model support | 3/3 |

Overall orchestration recall is **20/20**, reviewed resolved precision **20/20**,
and reviewed resolution outcomes **28/28**. Eight cases remain explicitly uncertain
(five unresolved, three ambiguous) and are excluded from positive recall/resolved
precision. There are zero unreviewed extractions and zero incorrect ownership
promotions in the reviewed corpus. All **48/48** registration/definition references
validate against actual source. These single-reviewer curated numbers are neither
production-wide accuracy estimates nor behavioral eval-coverage percentages.

Existing behavior audit recall remains **30/50**, supported recall **30/30**, and
reviewed precision **30/30**. New orchestration links are not counted as executable
behavior discoveries. M10.2a remains **8/8** registration recall/precision,
**2/2** bound-method resolution, and **21/21** source references. Its report filters
orchestration kinds out of the legacy tool-relationship section. Inventory
capabilities may grow with callbacks, but tool-registration scoring does not.

The compatibility snapshot in
[`compatibility_baseline.json`](../tests/fixtures/orchestration_audit/compatibility_baseline.json)
was captured before implementation, independently of new expected discovery.
Tests compare every existing M10.2a relationship payload (excluding only the new
empty defaults), preserve existing capabilities, and compare full primary-example
behavior/assessment hashes and finding IDs. Primary counts remain LangGraph 3/1,
CrewAI 8/1, and Pydantic AI 4/1 behaviors/findings. Supplied solution evals still
resolve the original findings in existing lifecycle tests.

M9's unchanged and supplied-solution comparison reports match their pre-change
hashes for all three examples. Retargeting a graph callback alone changes the
relationship ID but adds no user-facing M9 coverage delta. No matching rules,
M8 evidence, finding thresholds, SQLite schema, feedback, history, metric formulas,
public CLI behavior, or release metadata changed.

## Reproduce

From the repository's development environment:

```bash
python -m tools.behavior_audit --output docs/behavior-discovery-audit.json
python -m tools.behavior_audit.registrations --output docs/registration-relationships-audit.json
python -m tools.behavior_audit.orchestration --output docs/orchestration-relationships-audit.json
pytest tests/test_orchestration.py
```

The harness calls the existing scanner/extractor, validates pinned inputs and
source references, and writes only the explicitly selected report. JSON omits
source excerpts and absolute roots. No target source is imported or executed.
Isolation tests block network/subprocess/SQLite access, retain existing state
bytes, and verify scanning creates no state directory. Directory-name variants
are tests only; no naming-based active-code heuristic exists.

## Limitations and deferred scope

Only supported direct module-level declarations/registrations are recognized.
Unsupported shapes can be omitted when framework provenance cannot be established,
or retained as uncertain when the known source owner justifies a candidate.
No arbitrary aliases, imported callback implementations, recursive call graph,
callback return interpretation, runtime reachability, deployment importance,
agent selection, guardrails, or dynamic graph execution is inferred. M10.2c now separately supports bounded skill
dispatch and adapter delegation; see the follow-up below. No unavailable Easentic
checkout was inspected or used.

## Validation results

Baseline `pytest`: **402 passed**. Final `pytest`: **479 passed**, including 77
new orchestration tests. `ruff check .`, `ruff format --check .` (120 files),
`mypy src/agentguard` (28 source files), additional `mypy tools/behavior_audit`
(six audit modules), and `git diff --check` pass. All three audit reports regenerate
byte-for-byte, omit source excerpts/absolute roots, and retain M10.2a metrics.
Relative documentation links validate. Original fixture sources/inventories,
examples, README, package configuration, and version are unchanged. No user state
was changed, no target code executed, and no network/release/commit/push occurred.

## Changed files

| File | Purpose |
|---|---|
| [docs/behavior-discovery-audit.json](../docs/behavior-discovery-audit.json) | Regenerated original inventory with separate orchestration records. |
| [docs/behavior-discovery-audit.md](../docs/behavior-discovery-audit.md) | M10.2b results without rescoring original behavior expectations. |
| [docs/m10-2-extraction-plan.md](../docs/m10-2-extraction-plan.md) | Current priority-2 completion and priority-3 deferral. |
| [docs/orchestration-relationships-audit.json](../docs/orchestration-relationships-audit.json) | Deterministic source-backed orchestration results. |
| [docs/orchestration-relationships.md](../docs/orchestration-relationships.md) | Recognition, identity, uncertainty, consumer, audit, and validation documentation. |
| [docs/registration-relationships-audit.json](../docs/registration-relationships-audit.json) | Regenerated M10.2a report; original scoring unchanged. |
| [docs/registration-relationships.md](../docs/registration-relationships.md) | Shared model extension and compatibility boundary. |
| [requirements.md](../requirements.md) | M10.2b recognition, safety, audit, and completion contract. |
| [src/agentguard/extractors/behaviors.py](../src/agentguard/extractors/behaviors.py) | Shared index integration and canonical inventory merge. |
| [src/agentguard/extractors/orchestration.py](../src/agentguard/extractors/orchestration.py) | Conservative graph callback, task executor, and validator extraction. |
| [src/agentguard/extractors/registrations.py](../src/agentguard/extractors/registrations.py) | Reusable capability factory and explicit decorator-resolution allowance. |
| [src/agentguard/models.py](../src/agentguard/models.py) | Three orchestration kinds and additive defaulted metadata. |
| [tests/fixtures/orchestration_audit/compatibility_baseline.json](../tests/fixtures/orchestration_audit/compatibility_baseline.json) | Pre-implementation tool/public-example/M9 compatibility observations. |
| [tests/fixtures/orchestration_audit/crew.py](../tests/fixtures/orchestration_audit/crew.py) | Distinct tasks, shared executors, aliases, and context-only negative. |
| [tests/fixtures/orchestration_audit/graph.py](../tests/fixtures/orchestration_audit/graph.py) | Shared/async nodes and graph transitions. |
| [tests/fixtures/orchestration_audit/inventory.json](../tests/fixtures/orchestration_audit/inventory.json) | Source-first expected relationships and source hashes. |
| [tests/fixtures/orchestration_audit/negative.py](../tests/fixtures/orchestration_audit/negative.py) | Unrelated graph/task/validator APIs. |
| [tests/fixtures/orchestration_audit/uncertain.py](../tests/fixtures/orchestration_audit/uncertain.py) | Imported, dynamic, and rebound targets and owners. |
| [tests/fixtures/orchestration_audit/validators.py](../tests/fixtures/orchestration_audit/validators.py) | Sync/async validators and explicit ModelRetry separation. |
| [tests/test_orchestration.py](../tests/test_orchestration.py) | 77 recognition, source, identity, audit, isolation, and compatibility tests. |
| [tools/behavior_audit/orchestration.py](../tools/behavior_audit/orchestration.py) | Independent read-only orchestration audit harness. |
| [tools/behavior_audit/registrations.py](../tools/behavior_audit/registrations.py) | Keep orchestration outside legacy tool-relationship scoring. |


## M10.2c extension

Resolved callback capabilities may seed [bounded delegation](delegation-relationships.md)
through their existing source-backed registrations. This does not turn Task
executor instances into callable parents. New child edges retain parent proof
and the contextual internal role, never recursively becoming roots. Existing
orchestration fields/IDs/fingerprints and its 20/20 recall/precision, 28/28
resolution outcomes and 48/48 reference scores remain unchanged. The shared
relationship model gains defaulted metadata only; original and public-example
M8/M9 snapshots still match. Historical validation/file counts above describe
M10.2b; M10.2c has its own tests and separate structured report.
