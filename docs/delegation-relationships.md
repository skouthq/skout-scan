# Bounded dispatch, delegation, and fallback (M10.2c)

## Additive consumer contract

The existing registration relationship tuple gains `literal_dispatch`,
`one_hop_delegation`, and `exception_fallback` kinds. Defaulted metadata records
parent capability identity, existing parent relationship IDs, parent provenance,
dispatch key, exception condition, control conditions/evidence, registry/handler
references, and the contextual `orchestrated_internal` target role.
`registration` is the actual call-site reference for these relationship kinds;
parent provenance separately retains actual tool/callback registration evidence.
Canonical target definitions reuse `CallableCapability`; presence in that tuple
alone does not establish agent-facing eligibility.

Eligibility is frozen before child extraction: resolved tool registrations,
resolved orchestration callbacks, and known framework tool declarations qualify.
A recognized LangChain/CrewAI/OpenAI tool decorator establishes a declared tool
interface, even when deployment/owner usage is unknown; this does not claim that
an unknown custom factory is a verified agent owner. This distinction preserves
the original audit contract without allowing arbitrary helpers or `tools` names
as roots. New children never seed more traversal.

Existing behavior, M8 evidence/matching, findings, M9 deltas, feedback/SQLite,
metrics, CLI, and public JSON contracts remain unchanged. Internal serialization
is additive with empty/null defaults for old payloads. Every child edge is
structural source evidence, never proof of execution, failure propagation,
recovery success, deployment relevance, or test coverage. Child condition/failure
mapping is deferred: a resolved delegate definition can show a raise without
establishing how its guard composes with the parent or whether it propagates.

Baseline before implementation: 479 tests passed; original behavior recall
30/50, registration recall/precision 8/8, orchestration recall/precision 20/20,
and orchestration source references 48/48. Existing inventory, assessment,
finding, and relationship compatibility snapshots were captured before changes.

## Supported syntax and provenance

Only the existing source index establishes local callable identities. Analysis
starts inside unique resolved tool registrations, node/validator callbacks, or
known imported framework tool declarations. An unknown custom factory alone,
unregistered function, UI registry, plugin registry, or `execute` method name
cannot establish a parent. CrewAI Task executor references identify instances,
not callable parents. Source proofs are frozen before analysis starts, and all
parents are deduplicated by canonical callable ID.

### Literal dispatch

```python
HANDLERS = {"search": search, "retrieve": retrieve}


@tool  # Must resolve to an existing supported framework import.
def dispatch(key, query):
    return HANDLERS[key](query)
```

A registry must be a uniquely assigned module-local dictionary literal, with
unique string keys and uniquely resolved local function values. A selector name
represents possible routes; a literal string selector retains only its own key.
Multiple keys can share one canonical target while retaining distinct edges.
No route is claimed to have run.

Every registry-name use in the file must be its declaration or a direct indexed
call. Reassignments, item writes/deletions, `update`, `setdefault`, aliases,
argument/return escapes, reflection, computed entries, comprehensions and
external targets invalidate resolution. Unsupported selectors or control contexts
retain uncertain call-site records. This contract does not prove immutability
against arbitrary external Python execution, reflective aliases, or monkey-patching
outside the inspected file.

### One-hop calls

```python
adapter = StorageAdapter()


@tool
def read_record(key):
    return adapter.fetch(key)
```

Resolve the receiver, class and method using M10.2a's unique local-instance
resolver. Its rebinding, attribute mutation, inheritance, metaclass, descriptor
and dynamic-attribute exclusions remain in force. Direct unique local functions
are also supported, including direct awaited calls. Parent parameters, local
assignments/imports and nested declarations cannot be mistaken for global targets.
Aliases, external instances, computed attributes, `getattr`, and callback-return
calls remain uncertain. New targets retain the edge role `orchestrated_internal`;
a separately registered target can independently have its own registration.

Never follow a newly discovered child: `tool → adapter.fetch → helper` records
only the first edge. A child body is not traversed even when it is available.
If that child was independently registered before extraction, it can be analyzed
as its own proven parent, rather than as recursive traversal.

### Conditional fallback

```python
@tool
def read_record(key):
    try:
        return remote_lookup(key)
    except TimeoutError:
        return cached_record(key)
```

The handler retains its explicit condition and span; the fallback call remains
conditional. Allowlisted builtins are `TimeoutError`, `ConnectionError`,
`FileNotFoundError`, `PermissionError`, `OSError`, `KeyError`, `ValueError`, and
`LookupError`. Tuples require every exception to resolve; explicit `builtins`
imports/aliases work when unshadowed. Separate handlers retain separate links.
Bare handlers, `Exception`, `BaseException`, dynamic types, shadowed exceptions,
and unresolved fallback targets retain uncertain candidates, without definitions
or an internal target-role claim.

A fallback is not an unconditional delegation edge. An ordinary call outside a
handler is a one-hop link, even if its function happens to be named `fallback`.
The primary operation's raised exceptions are not inferred; neither handler
execution nor recovery success is established.

## Control, source and identity contract

Inspect only direct call expressions, awaited calls, assignment RHS calls and
return calls in the frozen parent's own body. Explicit `if`/`else` guards and a
single `try` level retain context. Calls under nested `try`, loops, or context
managers are uncertain. Nested definitions, call arguments, comprehensions,
conditional expressions, match arms, and exception-group handlers are not
followed. This is a bounded AST inventory, not a call graph or reachability model.
Existing scanner file/resource limits and completeness handling remain intact;
there is no additional relationship-count truncation. Work is bounded by the
input AST, frozen parent set, and literal dictionary size.

New defaulted fields are `parent_callable_id`, `parent_relationship_ids`,
`parent_provenance`, `dispatch_key`, `exception_condition`, `conditions`,
`context_evidence`, `registry_evidence`, `handler_evidence`, and `target_role`.
Every candidate retains the real call expression as `registration`, parent
registration/declaration proofs separately, and resolved targets' actual
`CallableCapability.definition`. Dispatch records retain the real literal
registry; fallbacks retain the real handler. References include file, symbol,
span, kind, and source excerpt internally. Audit JSON recursively omits excerpts
and contains no absolute roots.

IDs use the existing digest convention with a `delegation-v1` identity payload:
relative file, canonical parent, kind, key/handler, resolved target (or normalized
unresolved expression), normalized call AST, and structural guard/try context.
Fingerprints hash the same structural payload under `delegation-content-v1`.
Whitespace, comments, lines, scan order, timestamps and absolute roots do not
participate. Key, target, parent or handler changes are material. Identical calls
in identical structural contexts deduplicate; separate branch/handler/try
contexts and different parents remain separate. Path/symbol renames can change
identity. Full target bodies are referenced, not included in call-edge identity.

## Audit and compatibility

[Source-first expectations](../tests/fixtures/delegation_audit/inventory.json)
pin fixture bytes, parents, keys, targets, definitions, handlers, and call anchors.
They were authored before the new audit's first run. Original M10.1/a/b sources
and inventories are unchanged. The
[structured report](delegation-relationships-audit.json) measures relationships
separately from behavioral recall and eval coverage.

| Measure | Before M10.2c | After M10.2c |
|---|---:|---:|
| Original behavior recall | 30/50 | 30/50 |
| Original supported recall / reviewed precision | 30/30 / 30/30 | 30/30 / 30/30 |
| M10.2a registration recall / reviewed precision | 8/8 / 8/8 | 8/8 / 8/8 |
| M10.2b orchestration recall / reviewed precision | 20/20 / 20/20 | 20/20 / 20/20 |
| Historical skill routes represented | 0/2 | 2/2 |
| Historical adapter relationship represented | 0/1 | 1/1 |
| Historical exception fallback represented | 0/1 | 1/1 |
| Curated literal dispatch relationships | No contract | 5/5 |
| Curated one-hop delegation relationships | No contract | 4/4 |
| Curated exception fallback relationships | No contract | 3/3 |
| Curated reviewed resolved precision | No contract | 12/12 |
| Curated resolution outcomes | No contract | 21/21 |
| New relationship source references | No contract | 64/64 |
| Incorrect promotions / unexpected resolved relationships | No contract | 0 / 0 |

The curated report retains eight unresolved and one ambiguous case, excluded
from positive recall and resolved precision. There are no unreviewed records in
that report. These fixtures have a single source reviewer and are not a
production-wide accuracy estimate. The adapter's internal `LookupError` remains
unmapped to the parent; relationship discovery does not improve the frozen
original behavior denominator. The external primary lookup remains unresolved.

Pre-change snapshots cover original corpus roots plus a/b controlled fixtures:
full behavior objects (including IDs/fingerprints/source), full M8 assessments
and explanations, finding IDs, canonical capability IDs and all old relationship
fields/IDs/fingerprints. New defaulted fields are excluded only when comparing
old relationship payloads. Existing public-example tests preserve unchanged and
solution-added M9 comparison hashes. A separate test retargets only a structural
callback delegation and verifies no new coverage delta. Existing lifecycle,
feedback, metrics and persistence regression tests remain authoritative; no
SQLite schema, storage consumer, or matching code changed. Isolation tests
preserve existing state bytes, forbid network/subprocess/SQLite access, and check
that scanning creates no state. The old external Easentic checkout was not used.

## Reproduce

```bash
python -m tools.behavior_audit --output docs/behavior-discovery-audit.json
python -m tools.behavior_audit.registrations --output docs/registration-relationships-audit.json
python -m tools.behavior_audit.orchestration --output docs/orchestration-relationships-audit.json
python -m tools.behavior_audit.delegation --output docs/delegation-relationships-audit.json
pytest tests/test_delegation.py tests/test_orchestration.py
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```

Reports are deterministic; only the selected report is written. No target module
is imported, no target test is run, and no persistence is required. The fixture
hashes are input-integrity checks, not an independent semantic proof.

## Remaining limits

No recursive traversal, general data-flow/alias analysis, dynamic registries,
cross-module targets, arbitrary wrapper inference, deployment relevance, inferred
exception propagation, semantic child-guard composition, or M10.3 scope selection
is implemented. Structural success cannot determine which routes execute or what
evals verify. Unknown mutation sources outside the bounded file contract remain
a precision risk; known escapes/reflection are rejected rather than guessed.
No matching thresholds, public CLI/JSON outputs, metrics, feedback history,
release metadata, or promotional README content changed.


## Validation and file manifest

Baseline: **479 tests passed**. Final: **549 tests passed**, including 70 new
M10.2c tests. `ruff check .`, `ruff format --check .` (130 files),
`mypy src/agentguard` (29 modules), `mypy tools/behavior_audit` (7 modules), and
`git diff --check` pass. All four report files reproduce byte-for-byte on two
consecutive runs; the three earlier reports' complete metrics match baseline.
Edited documentation links and code fences validate. Original fixture sources,
inventories, public examples, production matching/storage/CLI code, and package
version remain unchanged. No target execution, network, live-state deletion,
commit, push, tag, or publish occurred.

| Added/modified file | Purpose |
|---|---|
| [src/agentguard/extractors/delegation.py](../src/agentguard/extractors/delegation.py) | Frozen parent eligibility and bounded dispatch, delegation and fallback extraction. |
| [src/agentguard/extractors/behaviors.py](../src/agentguard/extractors/behaviors.py) | Merge additive capabilities and relationships using the shared index. |
| [src/agentguard/models.py](../src/agentguard/models.py) | Three relationship kinds and backward-compatible defaulted provenance/context fields. |
| [tests/test_delegation.py](../tests/test_delegation.py) | 70 recognition, exclusion, identity, compatibility, source and isolation tests. |
| [tests/test_orchestration.py](../tests/test_orchestration.py) | Explicit old-kind/schema projection for the original registration snapshot. |
| [tests/fixtures/delegation_audit/adapter.py](../tests/fixtures/delegation_audit/adapter.py) | Two classes, shared target and independently registered async callback. |
| [tests/fixtures/delegation_audit/ambiguous.py](../tests/fixtures/delegation_audit/ambiguous.py) | Rebound receiver remains ambiguous. |
| [tests/fixtures/delegation_audit/dispatch.py](../tests/fixtures/delegation_audit/dispatch.py) | Literal routes, shared target and unregistered caller. |
| [tests/fixtures/delegation_audit/fallback.py](../tests/fixtures/delegation_audit/fallback.py) | Two explicit handlers, tuple condition and external primary. |
| [tests/fixtures/delegation_audit/negative.py](../tests/fixtures/delegation_audit/negative.py) | Non-agent UI/plugin/adapter naming controls. |
| [tests/fixtures/delegation_audit/uncertain.py](../tests/fixtures/delegation_audit/uncertain.py) | Mutated registry, external receiver and catch-all handlers. |
| [tests/fixtures/delegation_audit/inventory.json](../tests/fixtures/delegation_audit/inventory.json) | Source-first expectations and pinned fixture hashes. |
| [tests/fixtures/delegation_audit/compatibility_baseline.json](../tests/fixtures/delegation_audit/compatibility_baseline.json) | Pre-M10.2c full behavior/assessment/finding and old relationship hashes. |
| [tools/behavior_audit/delegation.py](../tools/behavior_audit/delegation.py) | Read-only relationship audit and deterministic structured report. |
| [tools/behavior_audit/registrations.py](../tools/behavior_audit/registrations.py) | Explicit tool-kind scoring excludes new relationship categories. |
| [tools/behavior_audit/runner.py](../tools/behavior_audit/runner.py) | Recursively omit source excerpts from additive audit metadata. |
| [requirements.md](../requirements.md) | Approved M10.2c recognition, safety and completion contract. |
| [docs/m10-2-extraction-plan.md](../docs/m10-2-extraction-plan.md) | Priority-3 completion, bounded implementation and deferred child semantics. |
| [docs/delegation-relationships.md](../docs/delegation-relationships.md) | Exact recognition, identity, consumer, audit and compatibility documentation. |
| [docs/delegation-relationships-audit.json](../docs/delegation-relationships-audit.json) | Separate curated relationship measurements and source references. |
| [docs/registration-relationships.md](../docs/registration-relationships.md) | Shared index/model extension and unchanged registration boundary. |
| [docs/orchestration-relationships.md](../docs/orchestration-relationships.md) | Callback eligibility, internal child role and unchanged orchestration results. |
| [docs/behavior-discovery-audit.md](../docs/behavior-discovery-audit.md) | New relationship results without rescoring original behavioral ground truth. |
| [docs/behavior-discovery-audit.json](../docs/behavior-discovery-audit.json) | Regenerated original report with additive structural inventory. |
| [docs/registration-relationships-audit.json](../docs/registration-relationships-audit.json) | Regenerated registration report; registration scores unchanged. |
| [docs/orchestration-relationships-audit.json](../docs/orchestration-relationships-audit.json) | Regenerated orchestration report with defaulted additive metadata. |
