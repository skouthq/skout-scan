# Agent relevance and scope controls — M10.3

## Contract defined before implementation

Scope is an explicit developer-selected **declared structural surface**, not an
inference about deployment, importance, legacy code or runtime reachability.
The default scan and its serialization stay unchanged.

Selectable roots are uniquely assigned module-local Pydantic AI Agent, CrewAI
Agent and LangGraph StateGraph instances, established through recognized imports
and the existing provenance index. Unknown factories, class factories, imported
instances, arbitrary helper names and directory labels are not selectable roots.
Rebound/ambiguous known declarations are diagnostics, not selectable instances.
Readable selectors are `relative/file.py#symbol`; a short symbol is accepted only
when unique across all known root candidates. Root hashes exclude source lines,
formatting and absolute paths. Source moves/renames may change identity.

Traverse existing resolved links only: owner→tool/callback, executor→declared
Task, Task→registered tool, and callable→dispatch/delegate/fallback target.
This may follow several already extracted links, but never extracts new call
edges or expands M10.2c's one-hop source-analysis boundary. Shared callables may
belong to several roots without duplicating behavior/finding identities.

A behavior joins by exact canonical callable/source identity, verified registration
owner context, known graph owner, known agent invocation, or an assigned source
Task. Matching names in another file, target names and directory proximity are
not evidence. Registration-specific invocation records remain tied to their
actual owner; a callable's implementation behavior may be shared.

`in_scope` requires a resolved path. `out_of_scope` requires a resolved path to a
different selectable root, a closed selected surface, and complete supported
analysis. Unattached facts stay `unknown`. A selected unresolved outgoing link or
incomplete source prevents confident exclusion: non-connected facts stay unknown
rather than being called unrelated. A proven selected path still suffices for
inclusion. Unknown relationships and behaviors remain visible as diagnostics.

Run the existing full matcher and repository-wide persistence lifecycle before
projecting the selected view. Never pass a filtered behavior inventory into
persistence. Invalid selectors are rejected before any state write. Discovery
is read-only. Scoped counts and considered eval candidates are labelled; they
are not repository-wide counts or assertions that all candidate evals verify a
behavior. Scope attribution completeness is reported separately from scan
completeness and never drives the findings lifecycle.

M10.3 rejects `--scope` with `--baseline` before analysis. Membership changes,
renames and missing roots cannot be mistaken for coverage regressions. No config
presets, matching rules, coverage categories, metric formulas, SQLite schema,
feedback state, or lifecycle states change.

## List roots and select a surface

From this checkout, the public example can be inspected with:

```bash
skout scopes examples/pydantic-ai-agent
skout scopes examples/pydantic-ai-agent --json
skout scan examples/pydantic-ai-agent --scope 'agent.py#refund_agent'
skout scan examples/pydantic-ai-agent --scope 'agent.py#refund_agent' --json
```

For your own repository:

```bash
cd your-agent-repo
skout scopes .
```

Copy a selector from that list into `skout scan . --scope '<selector>'`. The
selector path is relative to the supplied scan directory, not inferred from Git
branches, deployment variables or directory labels. A unique root symbol or the
listed stable `scope_...` ID also works. Prefer the full selector if names repeat.
Quoted source paths containing spaces are supported.

Supported constructor provenance includes direct and qualified imports, plus
import aliases, for `pydantic_ai.Agent` / `pydantic_ai.agent.Agent`,
`crewai.Agent` / `crewai.agent.Agent`, and `langgraph.graph.StateGraph` /
`langgraph.graph.state.StateGraph`. Only direct unique module-variable assignments
qualify. Annotations are permitted; destructured/chained results, conditional or
rebound bindings and ambiguous types do not become selectable instances.

A recognized constructor with `*args` or `**kwargs` can still identify the root,
but opaque configuration may hide registrations. It is explicitly flagged and
cannot prove that other components are excluded. Literal dynamic tool collections
also retain their unresolved relationship diagnostics. Discovery prints known
ambiguous candidates separately; class factories, unknown/custom factories,
imported instances and helper functions are not promoted to roots.

`scopes` uses the normal include/exclude configuration and supports repeatable
`--exclude`. It is read-only and never initializes `.agentguard/`. Unknown,
ambiguous, unsupported or no-longer-present selectors fail without falling back
to a repository-wide scan, and before creating or updating state. The error lists
available qualified selectors or points to source/exclusion/completeness checks.

## Membership and structural context

| Existing fact | Supported scope connection |
|---|---|
| Agent registers tool / validator | Owner to the canonical callable, with original registration evidence. |
| Graph registers node callback | Exact graph owner to canonical callback. |
| CrewAI Task declares executor | Known executor agent to its Task; Task tool registrations can then be followed. |
| Literal dispatch | Parent callable to each known possible target. Keys remain distinct relationship records. |
| One-hop delegation | Parent callable to resolved local delegate. No new child-body traversal. |
| Exception fallback | Parent callable to target with the existing conditional handler evidence. No execution/recovery claim. |

Traversal is directed. Sharing a tool does not pull the other agent itself into
the selected surface. Existing cycles and repeated links are visited once, and
there is no relationship-count truncation. A callable already independently
recognized by extraction can have its own existing outgoing links; scope follows
those records without discovering any additional source calls.

Implementation behaviors attach through exact file/qualified-symbol provenance.
Constructor-specific CrewAI invocation records retain their actual registration
owner; shared implementation facts may belong to both agents. CrewAI workflow
transitions attach to the known source Task's executor association, not merely a
target name or crew ordering label. Graph transitions attach to the exact known
graph owner. Relationship-only capabilities stay context and create no new
coverage-assessable behavior or finding.

Known membership is not necessarily exclusive. In the controlled shared-tool
fixture, `shared` belongs to both `alpha` and `beta`, using the same existing
behavior and finding IDs. `only_alpha` belongs to alpha; `only_beta` belongs to
beta. A standalone tool without a proven root path remains unknown.

Unknown membership is visible, not silently discarded. It can result from no
proven root path, incomplete/unreadable source, unavailable behavior evidence,
ambiguous owners, unresolved imports, dynamic registration or an unanchored
uncertain relationship. An unresolved selected outgoing link or globally
unanchored uncertain wiring prevents confident exclusions. Incomplete extraction
also prevents exclusion, even where another component appears independent.
This deliberately prefers abstention over false irrelevance.

## Text and JSON reporting

M11 adds optional [guidance](finding-quality-actionability.md) to finding
presentation copies after complete persistence and membership classification.
Shared behavior guidance is identical across scopes; selected-owner provenance
remains separate. Default scoped text stays concise. Scoped finding JSON adds
only `guidance`, with reference-only source evidence; assessment fields, scope
membership, counts and uncertainty semantics are unchanged.

M10.2e adds optional [rejection provenance](rejection-provenance-enrichment.md)
inside existing assessment/finding structured explanations. Shared rejections
retain all verified owners; `selected_owner_identity` distinguishes the selected
owner only when it is among them. It is presentation context and is never stored
as a repository-wide selected-owner fact. Scope membership, original IDs,
evidence sufficiency and persistence-before-filtering remain unchanged.

Scoped text reports the selected root, full scan completeness, scope-attribution
completeness, behavior/open-finding counts for all three memberships, selected
open findings, and separate outside/unknown diagnostics. Long diagnostics are
explicitly limited to 25 rows per section with a pointer to complete JSON output.
No analysis or traversal is truncated.

Scoped JSON has the following fields:

- `scope`: selected root/provenance, membership counts, attribution completeness
  and limitations. Finding counts mean open, non-suppressed findings.
- `behaviors` and `assessments`: selected behaviors and their exact repository-wide
  M8 assessments, without re-matching or changing confidence/coverage thresholds.
- `considered_evidence`: all extracted eval candidates considered for those
  behaviors. Presence in this list is not sufficient verification; inspect each
  assessment and match explanation, including M10.2f owner checks.
- `findings`: selected open, non-suppressed findings using existing IDs and fields.
- `out_of_scope_findings` / `unknown_findings`: separately labelled open diagnostics.
- `behavior_membership`, `relationship_membership`, `capability_membership`:
  classifications, reasons, known owning roots, witness relationship IDs and real
  source references for the complete extracted inventory.
- `repository_summary`: explicitly repository-wide counts and lifecycle totals.
- `completeness`: full-pipeline scan completeness. Scope attribution has its own
  completeness; uncertainty never changes persistence completeness or coverage.

JSON follows baseline-comparison conventions: source references remain, excerpts
are omitted recursively. Roots/selectors contain no object addresses, absolute
checkout roots or temporary paths. The report's repository field identifies the
user-supplied scan location, as other scan reports do. Scope discovery and
membership are deterministic; persisted finding timestamps and lifecycle counts
can legitimately change on repeated scans.

Ordinary scans and existing baseline JSON retain their original fields and
behavior. `skout scan . --json` without `--scope` or `--baseline` remains unsupported.
No `agentguard.toml` fields, implicit scope presets or environment-based selection
are added. Scope is orthogonal to file include/exclude rules.

## Findings, feedback and persistence

A successful scoped scan runs the complete existing repository scan, matcher and
findings lifecycle before projecting the selected view. It may initialize or
update repository-level `.agentguard/agentguard.db`, just like an ordinary scan.
Only presentation is scoped. `skout findings`, `skout review`, feedback commands,
and metrics remain repository-wide; scope does not change their queues or
formulas. Suppression remains a user feedback choice, not a scope disposition.

A scope filter alone never deletes, resolves or marks outside/unknown findings
no longer observed. Actual source/eval/configuration changes are still processed
by the ordinary full lifecycle, including legitimate resolution outside the
selected surface. This distinction avoids stale state while preserving history.
Normal include/exclude changes retain their existing repository-scan semantics;
they are not an implicit agent-scope selection.

Tests compare scoped→ordinary and ordinary→ordinary sequences with identical
scan times: stored findings, classifications, feedback, history (apart from
random event IDs) and metrics agree. Existing invalid-selector state bytes remain
unchanged. Source-only discovery/auditing never opens SQLite. Confirmed impact
still requires the existing explicit user confirmation; scope cannot infer it.

## M9 comparison boundary

`--scope` combined with `--baseline` or `--all-changes` returns a clear nonzero
error before analysis, snapshot creation or state changes. Run unscoped M9 and
scoped scans separately. This applies whether a root exists in both revisions,
only one revision, was moved/renamed, or has uncertain baseline membership.
M10.3 does not invent cross-snapshot root identity or reinterpret registration
changes as coverage changes. Ordinary M9 behavior remains unchanged.

## Independent controlled audit

[Source-first inventory](../tests/fixtures/scope_audit/inventory.json) declares
expected roots, scope/item membership, rationale, references through pinned
sources, and pending human-review status. Expectations were authored before the
first scope-audit run, rather than copied from computed membership. Seven fixture
repositories cover independent agents, shared tools, graph callbacks/routes,
CrewAI executor/Task links, validators, dispatch, delegation, fallback, ambiguous
receivers and negative/unregistered helpers. Original M10.1–M10.2f expectations
and sources remain unchanged.

The [structured scope audit](agent-scope-audit.json) records:

| Measure | Result | Unit |
|---|---:|---|
| Membership precision | 54/54 | Reviewed items classified in scope |
| Membership recall | 54/54 | Independently expected in-scope items |
| Exclusion precision | 12/12 | Reviewed items classified outside |
| Unknown correctness | 16/16 | Independently expected unknown items |
| Membership decisions | 82/82 | Distinct repository/scope/item pairs across curated groups |
| Root discovery | 7/7 | Complete expected root inventories per fixture repository |
| Source accuracy | 182/182 | Reference occurrences with real paths, spans and source text |
| Expected relevant findings retained | 4/4 | Reviewed structurally relevant findings |
| Expected outside findings excluded | 2/2 | Reviewed outside findings, still in full state |
| Expected unknown findings diagnosed | 2/2 | Reviewed unknown findings, kept separate |

Forty other membership records are explicitly unreviewed and excluded from quality
numerators/denominators. Human review remains pending. These counts measure
controlled structural membership, not operational relevance, deployment,
engineer willingness to act, or actionable-finding precision. No behavioral
coverage percentage or product metric is introduced.

The controlled two-agent CLI run actually produced 7 in-scope, 4 out-of-scope and
3 unknown behaviors; 5 selected, 3 outside and 2 unknown open findings; and all
10 findings in repository state. These are fixture observations, not promised
output counts for arbitrary repositories.

## Limitations and reproduction

Only the three declared constructor-root patterns are supported. CrewBase/class
factories, Flow-only entry points, arbitrary imported/re-exported instances,
unknown factories and dynamic aliases are not selectable merely because behavior
extraction supports some related syntax. Existing extraction/matching limits,
including unsupported data flow and aliasing, remain in effect. Scope does not
repair or reinterpret M8 evidence semantics.

Root IDs exclude whitespace, comments, physical lines, timestamps and absolute
paths, but may change after path, symbol or kind changes. Without supported
provenance, similar names do not connect components. All scope roots and members
are declared structure, not proof of actual execution or complete reachability.
M10.2e enrichment, new coverage categories, matching changes, runtime traces,
LLMs, hosted services, policies and persistent scope presets remain out of scope.

```bash
python -m tools.behavior_audit.scopes --output docs/agent-scope-audit.json
pytest tests/test_scopes.py
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```

Audit isolation tests block network, subprocess and SQLite, include executable
traps in copied source, preserve existing state bytes, and verify no state is
created by discovery/auditing. Directory-name tests cover `agent`, `v1`, `v2`,
`legacy` and `module` without naming heuristics. No target module is imported or
executed. This milestone does not bump versions, publish, commit, tag or push.

## Implementation validation

The pre-change suite passed 642 tests. Final validation passed 707 tests,
including 65 scope tests; Ruff lint and format checks (157 files); mypy for
`src/agentguard` (33 modules) and `tools/behavior_audit` (12 modules); and
`git diff --check`. Markdown fences and relative documentation links were checked.
All six current M10.1–M10.2f audit reports regenerated byte-for-byte against the
pre-change reports. Two scope-audit regenerations matched the checked-in-intent
JSON exactly. Compatibility tests also preserve the archived report hashes and
fixture behavior, relationship, eval, assessment, finding-ID and unchanged-M9
snapshots.

The installed console entry point listed roots in all three public examples.
A fresh temporary two-agent fixture reproduced the counts above and preserved
all 10 repository-level findings. Discovery created no local state. Selectors
remain available as complete copyable lines even when the summary table truncates
columns on a narrow terminal.

Implementation files: `src/agentguard/scopes.py`, `scope_reporting.py`,
`models.py` and `cli.py`; `tests/test_scopes.py`; and
`tools/behavior_audit/scopes.py`. New fixture files under
`tests/fixtures/scope_audit/` are `agents/app.py`, `agents/negative.py`,
`bound/app.py`, `chains/app.py`, `unknown/app.py`, `inventory.json` and
`compatibility_baseline.json`. Documentation comprises this file,
`docs/agent-scope-audit.json`, `docs/change-aware-coverage.md`, `requirements.md`
and the README scope paragraph. Matching, extraction, lifecycle, persistence and
metrics implementations, release metadata and earlier fixture sources are unchanged.
