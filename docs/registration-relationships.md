# Registration relationships (M10.2a)

## Representation and consumer boundary

A callable capability and its owner-to-callable registration are distinct typed
inventory records. `BehaviorExtractionResult` adds `callable_capabilities` and
`registration_relationships`, both defaulting to empty tuples for old payloads.
A capability has a canonical relative-file/qualified-definition identity, its
source definition evidence, and an optional existing behavior ID. Bound methods
are represented as capabilities, **not new tool invocation behaviors**.

A relationship has a versioned stable ID, registration kind, owner identity,
raw referenced expression, optional resolved callable identity, framework
provenance, resolution status/reason, registration evidence, optional definition
evidence, and structural fingerprint. Unknown provenance never becomes verified
ownership. Unresolved target records retain the real registration expression and
never invent a callable definition.

The new tuples enrich the internal extraction inventory only. Existing consumers
(matcher, eval extractor, finding selection, SQLite lifecycle, metrics, doctor,
CLI, and M9 comparison) continue consuming existing behavior/construct fields.
No new relationship is qualifying M8 verification evidence. No relationships are
persisted or added to public CLI JSON; existing JSON keys and database payloads
remain unchanged. Direct serialization of `BehaviorExtractionResult` gains two
additive defaulted fields; callers reading it must tolerate those fields.
Existing behavior IDs/fingerprints are not rewritten to attach ownership.

The intentional compatibility correction is limited to generic name-only
recognition contradicted by local declarations: a locally declared non-framework
`tool` decorator or non-agent constructor with `tools=` no longer establishes a
new generic tool behavior. Unknown external factories retain historical generic
plain-function discovery, but do not gain verified registration ownership.
No coverage threshold or relevance filter is changed.

## Identity contract

Capabilities use relative file plus qualified definition. Registration IDs hash
a versioned canonical structure containing relative path, owner, kind, resolved
callable identity (or normalized raw expression when unresolved), and framework
provenance. Registration fingerprints normalize the individual registration
expression, not an entire owner constructor or callable body. Physical lines,
comments, whitespace, timestamps, traversal order, and absolute roots do not
participate. Duplicate equivalent owner registrations collapse; different owners
remain separate. Material owner/target changes alter link IDs; path moves may too.

Implementation details, supported forms, limitations, and measured compatibility
results are recorded below after implementation validation.

## Supported source forms

Only file-local, unambiguous module bindings establish provenance. Recognized
constructors are `pydantic_ai.Agent` / `pydantic_ai.agent.Agent` and
`crewai.Agent`, `crewai.agent.Agent`, `crewai.Task`, `crewai.task.Task`.
Direct imports, `as` import aliases, and qualified module imports are supported.
Their literal `tools=[...]`, `tools=(...)`, and `tools={...}` entries produce
relationships. Pydantic AI `@agent.tool` and `@agent.tool_plain` produce owned
registration facts. Existing Pydantic `Tool(function)` and uniquely assigned
`wrapped = Tool(function)` forms resolve only to a unique local function.

Known LangChain and CrewAI tool decorators and `agents.function_tool`, including
import aliases, establish declared capabilities without inventing an owner.
An unattached declared tool is not evidence of deployed use. Generic unknown
factories and `bind_tools` keep existing behavior-discovery compatibility, but
unknown factories do not gain resolved ownership. No LangGraph node callbacks,
Task executor assignments, output-validator callbacks, skills, or delegation
relationships are added in M10.2a.

Literal local functions resolve to their own definitions. Bound attributes
resolve only through a unique direct local constructor assignment, a unique
undecorated local class without inheritance/metaclass arguments, and a unique
undecorated method definition. Method identity is qualified by the defining class;
two classes' `read` methods remain distinct. Two receivers of one method share
its callable definition, retaining their raw registration expressions.

## Conservative boundaries

Rebindings, conditional bindings, chained assignments, star imports, unknown
external definitions, assignment aliases, dynamic attributes, computed tool
collections, inheritance, descriptors, custom attribute lookup, custom `__new__`,
method overwrites, and explicit monkey-patching do not resolve confidently.
Module-level import provenance is not inferred from nested imports. Supported
indexing covers imports, assignments, functions, and classes; other binding and
mutation forms invalidate resolution rather than adding data-flow reasoning.
Explicit global rebinding declarations also invalidate the affected symbols.

A known framework owner with an unresolvable target retains `unresolved` or
`ambiguous` status and the real registration expression, with no invented target
reference. A factory with unknown framework provenance retains an unresolved
relationship and no verified callable/owner association. A passive local
storage-only constructor and a local identity decorator are the demonstrated
negative controls: their generic name-only promotions are removed. This tightening
is deliberately narrow; an arbitrary local factory or custom dispatch class is
not presumed non-agent merely because Skout does not recognize it.

The pre-existing framework behavior extractors retain their historical supported
scope and compatibility rules; this index governs the new ownership facts. It is
not a complete rewrite of legacy behavior provenance. A legacy discovery without
verified ownership must not be interpreted as a resolved new relationship.

Static local resolution cannot rule out arbitrary indirect mutation, import-time
replacement, or effects of unknown helper calls. It does not perform a whole-program
alias, effect, reachability, or Python descriptor analysis. Known direct ambiguity
is rejected; no claim of complete runtime identity verification is made.

## Coverage and persistence

Bound methods resolved by this milestone receive capability/relationship records,
not executable `Behavior` records. The former dynamic-tool warning becomes
`registration_only_callable`: registration resolved, but executable behavior/eval
assessment remains unsupported. Extraction stays conservatively incomplete in
those cases. This avoids both a misleading unresolved-registration message and a
new coverage/finding inference. Unknown dynamic tool warnings remain unchanged.

Existing callable behaviors retain their original IDs/fingerprints. A capability
can reference an existing behavior ID, but that backlink is not evidence of test
coverage. Unchanged public examples preserve all behavior records, assessment
payloads, finding IDs, and existing resolution tests. M8 evidence, M9 comparisons,
SQLite schema/payloads, classifications, metrics, and public CLI JSON are unchanged.
No additional findings are generated from the new relationship tuples.

## Audit results and reproduction

```bash
python -m tools.behavior_audit --output docs/behavior-discovery-audit.json
python -m tools.behavior_audit.registrations --output docs/registration-relationships-audit.json
pytest tests/test_registrations.py tests/test_behavior_audit.py
```

The original 58 source-curated expectations and all original fixture sources are
unchanged. New registration ground truth is separately source-authored in
`tests/fixtures/registration_audit/inventory.json`, with five pinned Python files,
13 expected outcomes, explicit forbidden ownership, and bound-method identities.
It was authored before scanning the new corpus. `public_baseline.json` records
behavior IDs/fingerprints, finding IDs, and complete assessment hashes captured
before implementation; it is a compatibility snapshot, not discovery ground truth.

| Measure | Before M10.2a | After M10.2a |
|---|---:|---:|
| Original behavior recall | 30/50 | 30/50 |
| Original supported-pattern recall | 30/30 | 30/30 |
| Reviewed original behavior precision | 30/32 | 30/30 |
| Original negative controls promoted | 2 | 0 |
| Original bound-method registrations resolved as relationships | 0/2 | 2/2 |
| New corpus positive registrations resolved | No relationship model | 8/8 |
| New corpus reviewed resolved-registration precision | No relationship model | 8/8 |
| New corpus bound methods resolved | No relationship model | 2/2 |
| Known shared fixture capability / owner links | No relationship model | 1 / 2 |
| New corpus reviewed resolution outcomes | No relationship model | 13/13 |
| New corpus incorrect verified ownership | No relationship model | 0 |
| Original behavior source references | 32/32 | 30/30 |
| New corpus registration/definition references | No relationship model | 21/21 |

Five new-corpus relationships remain unresolved/ambiguous and are excluded from
positive registration recall/resolved precision. No actual relationship is
unreviewed in this corpus. A resolved relationship's definition and registration
must both validate against real source spans. Relationship and original behavior
metrics are **not combined**. These single-reviewer curated counts do not estimate
production-wide accuracy or operational relevance. Source excerpts are excluded
from the JSON reports. Nothing from the unavailable Easentic repository was used.

The original controlled shared-tool fixture uses a custom factory; its ownership
correctly remains unknown. Shared verified ownership is demonstrated separately
using known Pydantic AI constructors, without changing the original expectations.

### Explicit compatibility impact of the two negative controls

The captured pre-change audit records for `format_label` and `encode_label`,
replayed through the unchanged matcher and pure finding selection, select
`finding_d6dbf0283a260b4b860fb822` and
`finding_fb505a4ecaeeff472323baf2` as potentially uncovered. After the isolated
name-only correction, this controlled repository has zero behavior records and
zero selected findings. This is a structural false-promotion correction, not a
new test or observed resolution. The existing disappearance lifecycle retains
history/feedback as `no_longer_observed`; it must not credit test resolution or
confirmed impact. No real user database was opened or migrated for this check.

The original audit corpus now has seven resolved and eight unresolved
registration records, with 22/22 registration/definition references validated
against source. These counts are separate from the new corpus's 13 reviewed
resolution outcomes. The three primary public examples retain their original
behavior/finding counts: LangGraph 3/1, CrewAI 8/1, and Pydantic AI 4/1.

## Validation

Baseline: 332 tests passed. Final `pytest`: **402 passed**, including 70 new
registration tests and the existing M8/M9, example resolution, feedback, and
SQLite regressions. `ruff check .`, `ruff format --check .` (111 files),
`mypy src/agentguard` (27 files), additional `mypy tools/behavior_audit` (five
files), and `git diff --check` pass. Both audit JSON artifacts regenerate
byte-for-byte. Relative documentation links validate. The original inventories,
public example source, README, package configuration, and version are unchanged.
No release, commit, push, target-code execution, network access, or user-state
migration was performed.

## Changed files

- [docs/behavior-discovery-audit.json](../docs/behavior-discovery-audit.json)
- [docs/behavior-discovery-audit.md](../docs/behavior-discovery-audit.md)
- [docs/m10-2-extraction-plan.md](../docs/m10-2-extraction-plan.md)
- [docs/registration-relationships-audit.json](../docs/registration-relationships-audit.json)
- [docs/registration-relationships.md](../docs/registration-relationships.md)
- [docs/verification-evidence.md](../docs/verification-evidence.md)
- [requirements.md](../requirements.md)
- [src/agentguard/extractors/behaviors.py](../src/agentguard/extractors/behaviors.py)
- [src/agentguard/extractors/registrations.py](../src/agentguard/extractors/registrations.py)
- [src/agentguard/models.py](../src/agentguard/models.py)
- [tests/fixtures/registration_audit/aliases.py](../tests/fixtures/registration_audit/aliases.py)
- [tests/fixtures/registration_audit/bound.py](../tests/fixtures/registration_audit/bound.py)
- [tests/fixtures/registration_audit/inventory.json](../tests/fixtures/registration_audit/inventory.json)
- [tests/fixtures/registration_audit/negative.py](../tests/fixtures/registration_audit/negative.py)
- [tests/fixtures/registration_audit/public_baseline.json](../tests/fixtures/registration_audit/public_baseline.json)
- [tests/fixtures/registration_audit/shared.py](../tests/fixtures/registration_audit/shared.py)
- [tests/fixtures/registration_audit/unresolved.py](../tests/fixtures/registration_audit/unresolved.py)
- [tests/test_behavior_audit.py](../tests/test_behavior_audit.py)
- [tests/test_registrations.py](../tests/test_registrations.py)
- [tools/behavior_audit/registrations.py](../tools/behavior_audit/registrations.py)
- [tools/behavior_audit/runner.py](../tools/behavior_audit/runner.py)
