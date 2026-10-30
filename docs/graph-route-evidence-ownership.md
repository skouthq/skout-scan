# Graph route evidence ownership — M10.2f

## Recognition contract (defined before the matcher change)

Only existing LangGraph conditional-route behaviors are gated: the behavior has
LangGraph source type and `conditional_workflow_edge` evidence. Tool/validator
conditions, non-LangGraph workflows and ordinary graph edges retain their rules.

Ownership requires an exact `repository-relative Python source file#graph symbol`,
with case-sensitive matching. Neither route strings, callback identity, names,
descriptions nor legacy `metadata.tools` establish this identity.

Two evidence contracts are supported:

1. A pytest scenario directly invokes `.invoke(...)` or `.ainvoke(...)` on a
   statically known local LangGraph StateGraph owner, optionally through an
   immediately preceding `.compile()` call. Module-level direct imports and
   qualified module imports, including import aliases, must resolve uniquely to
   that owner. Parameters, local rebinding, arbitrary assigned aliases, compiled
   variable aliases, unknown factories, dynamic attributes and ambiguous module
   paths do not qualify. This proves a source-supported invocation reference,
   not successful execution or a passing test.
2. A JSONL or Pydantic Evals scenario explicitly declares
   `metadata.graph_owner = {"source_file": "workflow.py", "symbol": "review_graph"}`.
   Exactly these two nonempty string fields are required. The file and symbol
   must resolve to a unique, unmodified known StateGraph declaration in the same
   scanned repository. This is a **declared eval subject**, not invocation or
   runtime evidence. Condition and expected target/outcome are independently
   mandatory. Legacy `metadata.tools` hints do not become this explicit contract.

Source definitions reuse the existing provenance index: known framework imports,
unique direct module assignments and mutation/rebinding checks. No graph code is
executed. No aliases are inferred from names or from cross-module data flow.
Direct relative imports and complex invocation/compile pipelines remain unsupported.

The typed matcher check distinguishes `verified_owner`, `unverified_owner`,
`conflicting_owner`, and `ambiguous_owner`. Multiple distinct verified graph
subjects conflict; unresolved explicit assertions or ambiguous graph declarations
cannot be rescued by a matching route string. Multiple legacy subject hints are
ambiguous, not runtime evidence. A single legacy hint stays unverified.

Condition/outcome evidence with an unverified, conflicting or ambiguous owner
remains conservatively partial when existing M8 evidence dimensions warrant it;
it never becomes covered. Missing ownership is reported as missing functionality,
with explicit ownership reason codes and source references. This does not claim
that the graph has no tests. Evidence from different scenarios is not combined.

## Root cause and precise matcher change

M8 checked subject identity for tools and ordinary conditions, but its generic
workflow/escalation branch accepted condition + target + assertion/expected data
without requiring the graph owner. JSONL token overlap could also masquerade as
subject identity. Thus two graphs with identical route labels, conditions and
callbacks could verify one another.

`check_graph_owner` is a typed sufficiency check before candidate classification.
It gates only behaviors with LangGraph source type and existing
`conditional_workflow_edge` evidence. Covered now requires verified ownership,
matching condition, matching action target, and supported outcome verification
within the same scenario. Ownership references have a dedicated candidate index;
non-graph matching ignores the additional graph references and definition proofs.
Tool wrappers, failure/validator checks and ordinary workflow edges keep their rules.

When an owner is verified but condition/outcome is absent, the candidate remains
partial. If ownership is unverified/conflicting/ambiguous but condition or target
matches, it is also partial, with missing `functionality`. With no materially
matching dimensions, existing inconclusive/potentially-uncovered rules remain.
Missing ownership alone does not force a new uncovered conclusion.

New structured reason codes use the existing explanation schema:

- `graph_owner_not_verified`: no supported source binding, including legacy hints.
- `graph_owner_mismatch`: verified subject(s) conflict with the required graph.
- `graph_owner_ambiguous`: ambiguous declaration/import path or multiple weak hints.

Match details expose the expected `file#symbol`, ownership state, supported
subjects and evidence mode. Condition/outcome details remain intact. Assessment
text explicitly avoids saying the graph has no tests, and declared subjects are
never described as observed execution. Existing reason codes explain condition
and outcome failures; no redundant route-condition/target codes are introduced.

The public JSON field structure is unchanged. New references use the existing
`ReferencedSymbol`/`SourceEvidence` fields and append evidence kinds
`graph_owner_invocation`, `graph_owner_assertion`, `graph_owner_ambiguous` or
`graph_owner_unverified`. Exact canonical identity lives in `qualified_name`;
raw calls/references remain available, including the actual invocation excerpt.
Eval IDs and content fingerprints still come from their original source content,
not the added ownership facts. Existing saved model payloads remain readable.

## Supported examples

A supported pytest invocation, with a uniquely resolved module-level import:

```python
from workflow import review_graph as graph


def test_review_route():
    result = graph.compile().invoke({"choose": "escalate", "amount": 900})
    assert result["route"] == "escalate"
```

Async `ainvoke` and qualified module imports work under the same source contract.
Direct `.invoke`/`.ainvoke` references are also recognized. This is static
invocation evidence, not validation that the API call will run successfully.
Nested helper/lambda bodies cannot prove invocation by the enclosing test.

A supported explicit JSONL subject assertion:

```json
{"input":{"choose":"escalate"},"expected":{"route":"escalate"},"metadata":{"graph_owner":{"source_file":"workflow.py","symbol":"review_graph"}}}
```

Pydantic Evals `Case(metadata={"graph_owner": ...})` uses the same literal contract.
The declaration must exist in the scanned repository under that exact relative
path and symbol, with a known LangGraph import, unique assignment and no detected
rebinding/mutation. Source text cannot be executed to resolve a missing subject.

`metadata.tools=["review_graph"]`, names/descriptions containing the graph, a
helper returning `"escalate"`, or a correct target with the wrong graph cannot
establish ownership. Multiple legacy hints with no stronger explicit binding
are ambiguous. A verified assertion is the explicit subject contract; unrelated
legacy tool hints are not silently promoted to additional verified graph owners.

## Reproduction and measurements

Baseline before implementation: **586 tests**, Ruff lint/format, production and
audit-tooling mypy, and diff checks passed. All five earlier reports reproduced.
Focused tests failed for the original three negative cases before production
changes; the initial ownership regression run had 12 failures and five passes.

The immutable historical M10.2d report is
[verification-obligation-audit-m10-2d.json](verification-obligation-audit-m10-2d.json).
Its independent expected decisions and input artifacts are unchanged. The current
[obligation report](verification-obligation-audit.json) is regenerated with current
rules; the new [ownership report](graph-route-ownership-audit.json) records actual
before/after assessments, source references, owner states, reasons, positives,
negatives and compatibility observations.

| Original control | Before | After | Explanation |
|---|---|---|---|
| `route_wrong_owner` (JSONL) | covered | partially_covered | Legacy wrong-graph hint is not verified ownership. |
| `route_helper_only` (JSONL) | covered | partially_covered | Helper hint does not bind the graph owner. |
| `pydantic_route_wrong_owner` | covered | partially_covered | Matching route literals cannot establish ownership. |
| `route_supported` (legacy JSONL positive) | covered | partially_covered | Correct-looking `tools` hint is still not the explicit subject contract. |
| New source-bound pytest and explicit JSONL/Pydantic controls | See report | covered | Verified owner, correct condition and verified target. |

Original evidence agreement is **18/21 before, 20/21 after**, not 21/21. The
remaining disagreement is the old metadata-only positive. All **3/3 original
false coverage cases** are fixed. New source-pinned control agreement and source
traceability are **17/17** each. Obligation eligibility remains **55/55**;
M10.2f does not reclassify obligations or add categories. These are curated static
controls, not production-wide accuracy, runtime results or coverage percentages.

The supplied LangGraph solution eval now includes the explicit `graph_owner`
binding. This preserves the real public-example resolution walkthrough without
weakening ownership checks or editing the original M10.2d controls. Its eval
content fingerprint and M9 supplied-solution report legitimately change; source
behaviors, finding IDs and their identity rules do not.

The older `examples/refund_agent` stand-in is not a known framework graph owner.
One existing conditional-route assessment changes from potentially uncovered to
partial because some route dimensions are present but ownership is not verified.
No new finding is selected there. Its old full assessments were reconstructed
with the original scanner from Git HEAD and verified against the historical
M10.2a checksum; no target example code was executed. That comparison is included
in the post-fix report rather than hidden by replacing the historical checksum.

## Identity, findings and M9

All captured behavior IDs, content fingerprints, source evidence, M10.2a–c
relationships and selected finding IDs remain unchanged. Non-conditional-graph
assessments match the saved full observations. The four structural audit reports
remain byte-identical. The M10.2d eligibility inventory and decisions are unchanged;
its evidence results intentionally differ, with the original report preserved.

No finding threshold, category, SQLite schema, review history or metric formula
changes. Partial ownership evidence has medium confidence and does not independently
create a new high-confidence finding. An existing falsely resolved finding can
reopen under the existing lifecycle, using the same ID and retained feedback.
Tests seed the actual historical assessment, verify reopening and refreshed
ownership explanation, and preserve all prior history events. Reopening does not
establish a user code regression or confirmed customer impact.

M9 re-analyzes both baseline and current source with the same running matcher.
It does not compare a persisted old-matcher status with a new-matcher scan.
Same-snapshot comparisons are deterministic and create no false improvement or
regression. Adding valid owner-bound evidence can improve coverage; removing it
can regress coverage; adding another graph/helper cannot falsely improve it.
Assessment changes after upgrading Skout may reflect this rule correction, even
when user source did not change. No public migration system or version bump is
introduced. Historical test snapshots remain intact; only graph-specific expected
semantic compatibility assertions are scoped to the documented correction.

## Bounds and validation

Known graph owners require direct module-level StateGraph construction via
recognized framework imports. File/module import resolution is repository-local,
including the conventional `src/` module spelling; competing paths are ambiguous.
Arbitrary aliases/re-exports, relative imports, compiled-variable tracing,
conditional factories, inherited graph APIs, compile calls with arguments,
fixture inference, dynamic monkey-patching and runtime reachability are unsupported.
External mutations and arbitrary test assertion/data-flow semantics remain outside
this bounded static contract. Metadata assertions cannot prove that a test passed.

The controlled graph fixture has explicit entry/finish configuration and shared
callbacks. Its positive source shape is realistic, but target tests are not run.
The original matcher observations remain byte-identical after that fixture setup
refinement. Hashes pin the control sources, historical report, before assessments
and pre-change compatibility observations.

```bash
python -m tools.behavior_audit.obligation_audit --output docs/verification-obligation-audit.json
python -m tools.behavior_audit.graph_ownership --output docs/graph-route-ownership-audit.json
pytest tests/test_graph_ownership.py
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```

Isolation tests forbid network, subprocess and SQLite access during the audit,
add an executable trap to copied source, retain seeded state bytes and verify no
extra state directory appears. Target Python is never imported or executed.
No rejection-provenance enrichment, new dispatch/fallback coverage, callback-state
verification, full reachability, LLM, network integration, scope features, release
metadata, commits, push, tags or publication are included.


## Final validation and file manifest

Baseline: **586 passed**. Final: **642 passed**, including 56 new tests.
`ruff check .`, `ruff format --check .` (147 files), `mypy src/agentguard`
(31 modules), `mypy tools/behavior_audit` (11 modules), and `git diff --check`
pass. All six current reports regenerate byte-for-byte twice; the four
structural reports and archived M10.2d report match their pre-fix bytes.
Documentation links/fences and all 17 control source references validate.
No package/version, README, SQLite, feedback/lifecycle implementation or release
changes were made. No target code execution, network, commit, push, tag or publish.

| Created/modified file | Purpose |
|---|---|
| [docs/change-aware-coverage.md](../docs/change-aware-coverage.md) | Same-current-matcher upgrade and M9 interpretation. |
| [docs/verification-evidence.md](../docs/verification-evidence.md) | Approved ownership sufficiency and reason codes. |
| [docs/verification-obligation-audit.json](../docs/verification-obligation-audit.json) | Current evidence observations; original decisions remain unchanged. |
| [docs/verification-obligation-integration-plan.md](../docs/verification-obligation-integration-plan.md) | Status of the implemented narrow gate; other integration remains deferred. |
| [docs/verification-obligation-mapping.md](../docs/verification-obligation-mapping.md) | Historical versus current evidence-report links and measurements. |
| [docs/graph-route-evidence-ownership.md](../docs/graph-route-evidence-ownership.md) | Recognition, root cause, migration, limitations, validation and file manifest. |
| [docs/graph-route-ownership-audit.json](../docs/graph-route-ownership-audit.json) | Post-fix original/control assessments, references and compatibility. |
| [docs/verification-obligation-audit-m10-2d.json](../docs/verification-obligation-audit-m10-2d.json) | Byte-identical historical pre-fix report. |
| [examples/langgraph-agent/evals/escalation_path.jsonl.example](../examples/langgraph-agent/evals/escalation_path.jsonl.example) | Migrate the supplied solution to explicit source-bound graph ownership. |
| [requirements.md](../requirements.md) | M10.2f acceptance and isolation contract. |
| [src/agentguard/extractors/evals.py](../src/agentguard/extractors/evals.py) | Attach supported graph evidence after existing eval parsing. |
| [src/agentguard/extractors/graph_evidence.py](../src/agentguard/extractors/graph_evidence.py) | Unique source declarations, bounded import/invocation and explicit subject assertions. |
| [src/agentguard/matchers/coverage.py](../src/agentguard/matchers/coverage.py) | Graph-only ownership gate, candidate index and missing functionality. |
| [src/agentguard/matchers/graph_ownership.py](../src/agentguard/matchers/graph_ownership.py) | Typed verified/unverified/conflicting/ambiguous ownership check. |
| [src/agentguard/matchers/explanations.py](../src/agentguard/matchers/explanations.py) | Ownership limitations in existing structured reasons. |
| [src/agentguard/models.py](../src/agentguard/models.py) | Three additive CoverageReason enum values; no required payload fields. |
| [tests/test_obligation_mapping.py](../tests/test_obligation_mapping.py) | Retain historical observations while testing current 20/21 agreement. |
| [tests/test_orchestration.py](../tests/test_orchestration.py) | Explicitly audit the migrated LangGraph solution comparison instead of claiming old hash compatibility. |
| [tests/test_registrations.py](../tests/test_registrations.py) | Retain full non-graph assessment checks and document graph-only differences. |
| [tests/test_graph_ownership.py](../tests/test_graph_ownership.py) | 56 ownership, evidence, identity, M9, lifecycle, isolation and audit tests. |
| [tests/fixtures/graph_ownership/compatibility_baseline.json](../tests/fixtures/graph_ownership/compatibility_baseline.json) | Full pre-fix behavior/relationship hashes, assessments, finding IDs and M9 observations. |
| [tests/fixtures/graph_ownership/pre_fix_assessments.json](../tests/fixtures/graph_ownership/pre_fix_assessments.json) | Actual original-matcher observations for the new controls. |
| [tests/fixtures/graph_ownership/inventory.json](../tests/fixtures/graph_ownership/inventory.json) | Independent expected control decisions and pinned source/historical hashes. |
| [tests/fixtures/graph_ownership/workflow.py](../tests/fixtures/graph_ownership/workflow.py) | Two known graphs sharing route conditions, labels and callbacks. |
| [tests/fixtures/graph_ownership/tests/evidence.py](../tests/fixtures/graph_ownership/tests/evidence.py) | Source-only pytest invocation/identity controls. |
| [tests/fixtures/graph_ownership/evals/cases.jsonl](../tests/fixtures/graph_ownership/evals/cases.jsonl) | Explicit, wrong, legacy, conflicting and missing subject controls. |
| [tests/fixtures/graph_ownership/evals/pydantic_cases.py](../tests/fixtures/graph_ownership/evals/pydantic_cases.py) | Pydantic Evals subject assertion controls. |
| [tools/behavior_audit/graph_ownership.py](../tools/behavior_audit/graph_ownership.py) | Deterministic read-only before/after audit runner. |
