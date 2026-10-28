# M10.2 — Proposed generalized extraction improvements

This is the source-backed implementation plan. Priorities 1, 2 and 3 are now
implemented as M10.2a, M10.2b and M10.2c under their bounded contracts.
It follows the [M10.1 audit](behavior-discovery-audit.md) and its
[machine-readable observations](behavior-discovery-audit.json). No priority is
based on reproducing external Easentic feedback.

## Priorities and scoring

Scores are engineering judgments on a 1–5 scale, not empirical measurements.
For generalizability, importance, feasibility, and potential coverage value,
**5 is more favorable**. For precision risk and complexity, **5 is higher cost or
risk**. Do not sum opposite-direction scores into a misleading single total.

| Priority / capability | Generalizability | Importance | Feasibility | Precision risk | Coverage value | Complexity |
|---|---:|---:|---:|---:|---:|---:|
| 1. Provenance-backed registration and bound callable relationships | 5 | 5 | 4 | 3 | 5 | 4 |
| 2. Explicit orchestration callback/executor contracts | 4 | 5 | 4 | 3 | 5 | 3 |
| 3. Bounded literal dispatch and one-hop delegation | 4 | 4 | 3 | 4 | 4 | 4 |

These improve the extraction input to coverage reasoning; none automatically
establish a missing eval, covered status, or operational relevance. Broader
relevance/scope controls belong to M10.3. No path-name-based active/legacy rules,
full reachability, provider calls, or runtime execution are proposed.

## 1. Provenance-backed registration and bound callable relationships

**Evidence.** `negative_controls/app.py:6,18` produces two incorrect tool
promotions despite correct source locations. `multiple_entries/app.py:16–17`
contains two explicit Pydantic AI bound-method registrations that remain
ambiguous/incomplete. `shared_tools/app.py:8–9` finds the callable once but loses
its two registration owners. See these paths under
[`tests/fixtures/behavior_audit`](../tests/fixtures/behavior_audit/).

**Capability and AST contract.** Separate a callable capability from an explicit
owner-to-callable registration relationship. Build a file-local import/declaration
index, restricted to static `Import`, `ImportFrom`, `Assign`, `AnnAssign`,
`FunctionDef`, `AsyncFunctionDef`, and `ClassDef` statements. Recognize known
framework registration constructors/decorators through their imports and simple
import aliases, not just the terminal spelling `tool` or keyword `tools`.
Resolve literal list/tuple/set entries to local functions. For an attribute entry
such as `records.read`, require a uniquely assigned, non-rebound local
`records = RecordsAdapter()` and a uniquely defined `RecordsAdapter.read` with no
inheritance/metaclass/dynamic-attribute ambiguity. Never execute its constructor.
Retain both the registration expression and the resolved method identity.

**Registration evidence and exclusions.** A relationship requires a recognized
agent/framework registration call and the literal callable entry. A method name,
plain call, UI `tools` keyword, or unrelated identity decorator is insufficient.
Exclude test helpers, ordinary unregistered methods, dynamic `getattr`, computed
collections, runtime mutation, unresolved external receivers, ambiguous rebinding,
star imports, and arbitrary aliases/data-flow chains. A framework-decorated but
unattached tool remains a declared capability with unknown operational use.

The controlled `agent_contract.py` proves intent for the audit reviewer. It does
not justify inferring arbitrary factory semantics in production. Initially support
framework-provenance relationships; leave custom-factory ownership unresolved
unless an independently specified deterministic contract is approved. Do not add
an allowlist of fixture factory/class names. Preserve the current generic plain
function discovery as a compatibility case; tightening false promotions must be
an explicit, tested change rather than silently dropping every unrecognized
factory. Locally resolved non-agent declarations provide stronger negative evidence
than unknown external provenance. Unknown must not be presented as confirmed
non-agent or confirmed agent ownership.

**Model mapping.** Preserve existing `tool_invocation` capability IDs where their
meaning is unchanged. Add an explicit registration relationship representation
(owner, callable identity, registration kind, evidence) rather than a second
indistinguishable invocation. Prefer an internal extraction relationship model
attached to the inventory; if exposing it through production models/JSON becomes
necessary, specify additive defaults and consumer handling before implementation.
No matcher may treat registration as observed invocation. A shared callable has
one capability and two owner links. A bound method is not an agent entry invocation.

**Source and identity.** Capability evidence points to the function/method; owner
link evidence points to the registration element and owning constructor. Relative
path, qualified callable, owner, relationship kind, and structural registration
form define a versioned link ID, excluding line numbers and whitespace. Existing
behavior IDs/fingerprints remain untouched; new link fingerprints normalize AST
registration structure, not source layout. Do not hash the entire owner's body
for every shared relationship.

**Risks.** Shadowed imports, subclasses, receiver reassignment, callable instances,
and UI/plugin systems with tool-like APIs can mislead local resolution. Conservative
rejection/uncertainty is preferable to general wrapper inference.

**Regression fixtures and acceptance.** Keep all M10.1 cases and baseline IDs;
add imported/qualified/aliased known framework registrations, local shadowed
imports, local non-agent constructors/decorators, two receivers with same method
name, ambiguous receiver assignment, external receiver, and method descriptor
cases. Two independently configured known agents must retain distinct owner links;
one shared callable must not become two capabilities. Simple known bound methods
must resolve with both source references. Dynamic cases must remain unknown.
Negative controls must not gain verified agent ownership. Any intentional change
to existing generic false-positive output needs a documented compatibility test;
no threshold or operational-relevance filter may substitute for source evidence.

## 2. Explicit orchestration callback and executor contracts

**Evidence.** Eight node callback contracts are missed while graph transitions are
correct: controlled `graph_routing/app.py:21–23` and public
[`workflow.py:39–46`](../examples/langgraph-agent/workflow.py). Two CrewAI
Task→Agent assignments are absent at
[`crew.py:26,33`](../examples/crewai-agent/crew.py). Pydantic AI validator callback
invocation is only partially represented at
[`agent.py:34`](../examples/pydantic-ai-agent/agent.py), despite correctly extracted
retry condition and ModelRetry outcome.

**Capability and AST contract.** For a receiver already known to be a supported
StateGraph instance, recognize `graph.add_node("literal", local_callable)` and
store the literal node→callable association. Require a uniquely resolved local
function initially. For known CrewAI `Task` constructors, record an explicit
`agent=known_agent` assignment separately from context and sequential edges.
For known Pydantic AI agents, record `@agent.output_validator` registration as a
validator callback contract. Reuse existing framework indexes; do not infer graph,
agent, task, or validator roles from method/class spelling alone.

**Registration evidence and exclusions.** Require both known owner provenance and
explicit registration/wiring. Exclude arbitrary objects exposing `add_node`,
unknown imported callbacks, dynamic node names/route maps, lambdas with unsupported
identity, unresolved agents, computed task assignments, and runtime decorators.
Do not assume every registered node runs, infer graph-wide reachability, or
promote all callback helper bodies. Preserve supported transition records.

**Model mapping.** Represent node callback registration, Task executor assignment,
and validator callback registration as explicit orchestration relationships.
They are neither LLM-selectable tools nor already-tested runtime invocations.
Specify a dedicated operation/relationship kind and additive model defaults if
production inventory exposure is required; do not overload `tool_invocation` or
`workflow_transition` so downstream consumers silently misinterpret them.
Existing retry branch/failure and graph edge records remain separate atomic facts.
Before integration, explicitly specify which new contracts the existing matcher
can consume; leave unsupported evidence inconclusive rather than changing M8
verification rules to manufacture coverage.

**Source and identity.** Include owner, literal node/task/validator identity,
resolved callback/executor, relationship kind, and relative registration path.
Point evidence to registration and resolved callback definition when available.
Keep line numbers out of link identity. Node rename/rebinding is a material
relationship change; source movement may change path identity. Normalize wiring
AST for fingerprints; preserve existing transition/callback failure IDs.

**Risks.** Registration does not prove runtime invocation. Context edges do not
imply the same executor, and a callable may be registered under several nodes.
Count distinct associations without duplicating shared callable capabilities.

**Regression fixtures and acceptance.** Cover same callback under two node names,
two graphs with equal node names, direct/conditional edges, unrelated graph-like
objects, imported/unresolved callbacks, Task executor versus context/order,
validator condition/outcome versus callback, shadowed framework imports, dynamic
names, and whitespace/line moves. The eight explicit local graph callback
contracts, two supported Task assignments, and validator callback must gain typed
source-backed relationships without altering the existing 15 public-example
records or asserting automatic execution/coverage. Additions require approved
consumer/model tests; unknown cases must remain unknown.

## 3. Bounded literal dispatch and one-hop delegation

**Evidence.** `skill_dispatch/app.py:18` discovers its parent tool but not its two
fixed routes. `adapter_delegation/app.py:17` discovers the wrapper, not the
resolved delegate or its explicit failure condition. `failure_fallback/app.py:16`
lacks an exception-to-fallback relationship even though its explicit validation
branch/failure is discovered. These are related call-relationship omissions, not
evidence that all helpers should become agent-facing behaviors.

**Capability and AST contract.** Start only inside an already established
agent-facing operation or orchestration callback. Recognize calls of the exact
form `REGISTRY[key](...)` when `REGISTRY` is a single-assignment local literal
`Dict` mapping string constants to uniquely resolved local functions. Record
possible key→target dispatch relationships, not observed routes. For one-hop
`receiver.method(...)`, reuse priority 1's conservative local-instance resolution
and record the delegation relationship. An explicit `except KnownException`
containing a directly resolved fallback call can attach the handler condition to
that call edge; bare catch-all/runtime exception relationships remain uncertain.

Only inspect a directly resolved delegate's explicit condition/raise when the
parent relationship is known; preserve that origin and condition on the child
contract. Do not infer that every argument always reaches it, propagate arbitrary
constraints, or equate an adapter's internal failure with an unconditional public
failure. If parent-to-child condition composition is not representable without
semantic guessing, report the relationship only and defer the child failure.

**Registration evidence and exclusions.** Require the parent registration and the
exact source call/registry/handler. Exclude computed dictionary keys/values,
registry updates, unknown extensions, reassignment, external targets, recursive
traversal, arbitrary aliases, reflective calls, callback return values, and
unregistered internal entry points. Never promote all adapter methods or helper
conditionals based on naming, directory placement, or similarity.

**Model mapping.** Reuse explicit relationship records for dispatch/delegation;
include parent identity, literal route or handler condition, resolved target, and
raw call. Keep child role `orchestrated_internal`, not automatically `agent_facing`.
Use existing condition/failure types only where the explicit source fact fits
without losing parent/handler semantics; otherwise defer that subcase. Parent
invocation alone must not establish route/failure/outcome verification in M8.
No matcher or finding threshold changes are bundled with this extraction work.

**Source and identity.** Evidence includes the parent call and registry entry or
local method definition; handler-aware edges include the relevant `except` span.
Use parent identity + relationship kind + literal route/condition + resolved
qualified target + relative path, never physical line numbers. Fingerprints cover
the normalized relevant AST only. Multiple parent callers may share a child
capability but retain distinct call edges. Existing parent behavior IDs remain
stable; an edited route target is a material new relationship.

**Risks.** Literal dictionaries may still be mutated at runtime, local objects may
be rebound, a method may be overridden, and exception propagation may be handled
elsewhere. Limit recognition to source-provable cases; do not promise complete
interprocedural reasoning. This priority has the highest precision risk and
should follow the provenance/index work rather than bypass it.

**Regression fixtures and acceptance.** Cover two literal routes, unknown key,
mutated/computed registry, shared target under two keys, registered versus
unregistered caller, unique local adapter versus ambiguous/external receiver,
cyclic helper calls, two distinct handlers, and explicit fallback versus generic
helper call. The two skill routes and resolvable one-hop adapter relationship must
be represented with correct source and parent identity. No unrelated helper gains
agent-facing status. Handler evidence must stay conditional; child failures that
cannot preserve conditions remain deferred. Formatting and line-move identity,
review history, source reference, M8 outcome dimensions, and M9 change regressions
must pass before these records are integrated into production assessment.

## Implementation boundaries and deferred work

Implement each priority as a separately tested change after its model/consumer
contract is accepted. Run the audit after each change; do not alter the original
expected contracts simply to make scores improve. Review new actual records
before including them in precision. Preserve legacy persisted IDs and use additive
payload defaults if new fields are introduced. No SQLite schema reset or feedback
migration by deletion is acceptable.

Dynamic plugin contents, arbitrary aliases, cross-module data-flow, full
reachability, production importance, automatic active-code selection, generic
wrapper tracing, and relevance filtering remain deferred. The audit provides no
basis to promise new matching/coverage behavior for newly represented contracts.
Those integration decisions must retain invocation/condition/outcome verification
and explicit uncertainty, and must be validated separately.

## M10.2a implementation status

Priority 1 is implemented with the bounded contract in
[Registration relationships](registration-relationships.md). The index supports
known Pydantic AI/CrewAI owner registrations and known tool declarations,
conservative local bound methods, and independent shared ownership. New
capabilities/relationships are additive internal extraction fields, outside
coverage/matching/selection/persistence and M9 delta consumers. Corrected generic
false promotions are limited to the demonstrated passive local constructor and
identity-decorator cases; unknown custom factories retain generic compatibility.

Original curated expectations remain unchanged. The original behavior audit and
separate registration audit record their own denominators. Priority 2 and
priority 3 remain **unimplemented**; no node/executor/validator callback or
skill/delegation analysis is bundled into M10.2a.


## M10.2b implementation status

Priority 2 is implemented under the bounded
[orchestration relationship contract](orchestration-relationships.md). Shared
provenance/capability infrastructure and the existing relationship tuple now
represent direct LangGraph node callbacks, explicit CrewAI task executors, and
Pydantic AI output validators. Facts remain outside matching, finding selection,
M8 verification evidence, persistence, and user-facing M9 deltas.

All 11 original target associations satisfy the approved static contract. The
separate source-first audit also tests shared/async callbacks, framework aliases,
multiple owners, direct/conditional edges, context versus executors, and
uncertain/dynamic/negative cases. Existing behavioral and registration ground
truth is unchanged. See the contract for exact supported syntax, identity and
source rules, measured results, limitations, and compatibility snapshots.
Priority 3 is now implemented separately as M10.2c; see its status below.


## M10.2c implementation status

Priority 3 is implemented under the [delegation contract](delegation-relationships.md).
The frozen proven-parent set and M10.2a resolver support local literal registry
routes, one-hop methods/functions, and exception-guarded fallbacks. New targets
remain contextual `orchestrated_internal` capabilities, outside M8 evidence,
matching, findings, persistence, and M9 coverage deltas. Delegated failure/guard
composition remains deferred rather than inferring exception propagation.

All four historical target relationships are represented: two skill routes,
one adapter link, and one explicit TimeoutError fallback. The separate curated
audit records 12/12 resolved relationships, 21/21 reviewed resolution outcomes,
64/64 references, eight unresolved and one ambiguous case, and zero incorrect
promotions. Original behavior, registration and orchestration scores and ground
truth remain unchanged. No M10.3 scope rules or recursive discovery are included.
