# Rejection provenance enrichment — M10.2e

## Contract and architecture

This milestone adds explanation context to **existing** guarded rejection
behaviors. It adds no behavior, finding, verification category, matching rule or
scope edge. Registration means a declared capability surface, not execution,
deployment, importance, safety or proof that an eval is missing everywhere.

The raw extractor and M8 matcher remain unchanged. After matching, the ordinary
scan calls `enrich_rejection_explanations` with the full extraction, raw matching
result and existing M10.3 root inventory. It returns copied explanations only.
The unchanged findings selector/lifecycle receives this complete enriched result.
`findings` and `review` display optional saved context. Raw `analyze_snapshot`,
M9 comparisons and development audits continue consuming unchanged M8 judgments.

Scoped scans also enrich the complete repository result before persistence.
`project_scope` adds the selected owner only to copies used for presentation.
It still uses M10.3's original membership graph and retains all resolved owners
for shared callables. Selected-owner context is never saved as a repository-wide
fact. Outside/unknown findings remain in the existing lifecycle.

The pure join consumes typed facts only: it does not reparse rejection bodies,
interpret descriptions/excerpts, resolve extra aliases, follow delegation or
build another scope graph. M10.3 discovery reuses the existing file-local
provenance index to supply actual Agent declaration references.

## Eligibility and source chain

All of these must hold:

1. An existing `tool_failure` or `conditional_branch` has a nonempty explicit
   condition and a `raise` action with an extracted exception outcome.
2. The behavior is available, with real source references. Its exact relative
   source file and qualified source symbol identify one existing canonical
   `CallableCapability`; its evidence lies within that definition's source span.
3. An existing resolved `constructor_tool`, `decorator_tool` or
   `output_validator_callback` identifies that same callable ID and definition.
4. The relationship's owner is a uniquely resolved direct Pydantic AI or CrewAI
   Agent declaration from the existing root inventory, in the same source file.
5. Actual declaration, registration, definition and rejection references exist.

The source chain is Agent declaration → registration relationship → canonical
callable → existing conditional rejection. Line numbers locate source evidence;
they are not identity or name-similarity joins. Framework labels, exception names,
proximity, directory labels and tests cannot establish ownership.

Supported forms are the existing recognized import/alias forms for direct
Pydantic AI and CrewAI Agent constructors with literal tool collections;
Pydantic AI `@agent.tool`, `@agent.tool_plain`; and single
`@agent.output_validator` registrations with an already extracted conditional
`ModelRetry`. Existing wrapper forms qualify only if existing extraction already
supplies the same resolved canonical capability and rejection. This milestone
adds no registration or rejection discovery.

Method-call registrations such as `agent.tool_plain(function)`, imported callable
instances, class factories, arbitrary aliases/re-exports and unproven bound
receivers do not gain support. Task-only tool registration does not invent an
Agent owner via executor inference. LangGraph callbacks and internal delegated
adapter failures are not attributed as registered agent rejections. Source or
identity gaps cause abstention, not a parallel source-analysis pass.

## Representation and shared concerns

`CoverageExplanation.rejection_provenance` is an optional typed
`RejectionProvenance`. Historical explanations without it remain readable. Its key
is omitted when there is no verified context, preserving raw M8 serialization.
It contains:

- `primary_behavior_id`: existing `tool_failure` identity preferred over an
  equivalent conditional-raise record; no new concern ID is generated.
- `related_behavior_ids`: all equivalent existing representations retained in
  the inventory, grouped by canonical callable, normalized condition and exact
  action kind/target/outcome.
- `callable_id`, relative source file, qualified source symbol, original typed
  condition and action/outcome, real definition/behavior evidence.
- `registrations`: every distinct resolved relationship ID/kind, owner identity,
  Agent declaration evidence, registration evidence and callable definition.
- Sorted `owner_identities`, resolved provenance status and limitations.
- Optional `selected_owner_identity`, set only in a scoped view when that owner
  is actually present in the verified owner set.

Different conditions, actions, outcomes or canonical callables never consolidate.
One shared callable retains one existing concern and finding while listing both
registrations/owners. Equivalent branch/failure facts share context; neither
record is deleted. Existing finding deduplication and selection remain unchanged.
Owner-specific existing source facts are not rewritten into a shared obligation.

Unresolved or ambiguous registrations, missing declarations, conflicting callable
identity, absent references and unavailable behaviors receive no verified
attribution. Other independently resolved registrations may still be retained;
known unverified links with the same canonical identity are explicitly noted.
Omitted context means unsupported attribution, not irrelevant/unreachable code.

## Presentation and verification evidence

Actual public-example source yields the validator context `agent.py::validate_refund`,
registered by `agent.py#refund_agent`, condition `decision.refund_amount > 500`, and
explicit outcome `ModelRetry`. Its real declaration, registration, condition and
raise locations accompany existing behavior/finding IDs. Paths, conditions,
IDs and lines are taken from extraction, not hardcoded in the renderer.

Ordinary/scoped scan details, `skout findings` and `skout review` show:

- Registered callable and all verified owning agents.
- Selected owner where applicable.
- Extracted condition, explicit rejection outcome and existing concern identity.
- Registration kinds/IDs and actual declaration/registration/rejection locations.
- A limitation distinguishing declaration from execution or eval verification.

These lines supplement the original coverage assessment, candidate evals,
missing dimensions, reasons and suggested scenario. No second coverage status is
introduced. A provenance record never makes an invocation, test name, wrong
condition, wrong exception, unrelated helper, JSONL exception description or
Pydantic Evals expected text sufficient to verify a failure.

The controlled corpus preserves an existing M8 difference: a conditional-branch
record can be `covered` where its equivalent `tool_failure` is still partial.
M10.2e does not reconcile those assessments or change the matcher. Consolidation
is explanation context, not a union of test evidence or a coverage promotion.

Scoped JSON adds context under existing assessment/finding structured explanations;
all old keys remain. Nested source excerpts are omitted by the existing serializer,
while relative references/IDs remain. Root discovery JSON and M9 JSON stay unchanged.
The metrics export also removes excerpts recursively from optional nested context;
its calculation and metric definitions do not change.
Unscoped `scan --json` remains unsupported without a baseline; no CLI options,
coverage enums or finding-count meanings change.

## Identity, lifecycle, M9 and scope invariants

No behavior ID, fingerprint, callable/registration identity, finding ID, threshold,
SQLite schema, classification, metric formula or lifecycle state changes.
Existing JSON finding payloads can store the optional context without migration.
Normal refresh updates or clears it as registrations change; unavailable evidence
never invents an owner or proves resolution. Historical records are not rewritten
until normal scans refresh their explanations.

Owner addition/removal, formatting and line movement preserve an unchanged
rejection's identity, assessment and M9 delta. Adding a new Agent declaration can
still create the ordinary pre-existing Agent invocation behavior; that is separate
from the unchanged rejection. Relevant eval additions/removals retain their normal
M9 interpretation. Provenance adds no change category and is not M9 evidence.
Scoped M9 remains explicitly unsupported.

Persistence tests compare enriched and raw scans with identical source edits,
scan times and feedback. Findings (apart from optional context), classifications,
metrics and history agree. A second scan legitimately changes repeat-scan cohorts;
that ordinary event is not a provenance-induced impact. The public Pydantic AI
solution still resolves the same finding with `covered` status, retains `add_eval`,
and never infers confirmed impact.

## Independent audit and limitations

The [source-first inventory](../tests/fixtures/rejection_audit/inventory.json)
pins all source files and independently declares expected owners, conditions,
outcomes and abstentions. Human review remains pending. Expectations were written
before running the enrichment audit, not copied from computed provenance.
The [structured report](rejection-provenance-audit.json) records:

| Measure | Result | Unit |
|---|---:|---|
| Eligible enrichment recall | 5/5 | Existing rejection concerns (10 equivalent behavior records) |
| Owner attribution precision | 6/6 | Reviewed resolved concern/owner associations |
| Owner attribution recall | 6/6 | Independently expected concern/owner associations |
| Equivalent-fact consolidation | 5/5 | One primary context per equivalent branch/failure group |
| Source-reference accuracy | 33/33 | Actual declaration, registration, callable and rejection reference occurrences |
| Abstention correctness | 3/3 | Unregistered same-name tool, unknown factory, ambiguous owner |
| Assessment preservation | 29/29 | All raw M8 assessments, excluding only added provenance |
| Finding preservation | 1/1 | Full selection payload comparison, excluding only added provenance |
| Historical snapshots | 20/20 | Complete inventories, fingerprints, M8, findings, scopes and same-snapshot M9 |
| Historical audit hashes | 8/8 | Seven current reports plus archived M10.2d report |

No computed enrichment records are unreviewed in this controlled fixture. Context
controls also retain registration-without-rejection and ambiguous internal adapter
cases without manufacturing behaviors. Separate regressions exercise complete
repositories with genuine actionable findings, shared-owner scoped views, normal
resolution, feedback, missing verification dimensions and source availability.

These numbers measure controlled provenance correctness, not production-wide
precision, behavioral recall, eval coverage, actionable-gap precision or runtime
reachability. Upstream extractor and matcher limitations remain. Existing
incomplete evidence may lower assessment confidence or withhold findings, exactly
as before; provenance cannot override that safeguard.

## Reproduction

```bash
python -m tools.behavior_audit.rejection_provenance --output docs/rejection-provenance-audit.json
pytest tests/test_rejection_provenance.py tests/test_scopes.py
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
```

Auditing performs read-only static analysis and pure finding selection. Isolation
checks prohibit network, subprocess and SQLite access. Audit identities and
ordering contain no timestamps, absolute roots or traversal-order dependency.
Earlier source/expectation inventories and audit reports are preserved.

## Validation and changed-file manifest

Pre-change baseline: **707 tests passed** with all required static checks.
Final suite: **770 tests passed**, including 63 new rejection-provenance cases.
Ruff lint and format checks (165 Python files), mypy for production (34 modules)
and audit tooling (13 modules), and `git diff --check` pass. Documentation fences
and relative links validate. All seven current audit reports regenerate to their
pre-change bytes; all eight saved report hashes, including the archived study,
match. Two new provenance-audit regenerations match the saved JSON exactly.

The installed CLI was manually exercised against a disposable copy of the public
Pydantic AI example, with no target code or tests executed:

| Stage | Finding ID | Coverage | Lifecycle |
|---|---|---|---|
| Initial scoped scan | `finding_f232f8c4fbb9aae3723cde30` | `potentially_uncovered` | `open` |
| Enable supplied eval and ordinary rescan | `finding_f232f8c4fbb9aae3723cde30` | `covered` | `resolved` |

Actual context identified `output_validator_callback`, owner
`agent.py#refund_agent`, condition `decision.refund_amount > 500` and outcome
`ModelRetry`. Confirmed impact remained false. Metrics JSON retained provenance
references without nested source excerpts. CLI regression tests also exercise
ordinary/scoped text, scoped JSON, findings and interactive review.

| Created or modified file | Purpose |
|---|---|
| [requirements.md](../requirements.md) | M10.2e acceptance contract. |
| [docs/rejection-provenance-enrichment.md](rejection-provenance-enrichment.md) | Design, compatibility, limits, results and manifest. |
| [docs/rejection-provenance-audit.json](rejection-provenance-audit.json) | Deterministic independent audit. |
| [docs/verification-obligation-integration-plan.md](verification-obligation-integration-plan.md) | Mark the narrow first integration implemented. |
| [docs/verification-obligation-mapping.md](verification-obligation-mapping.md) | Distinguish historical study from production enrichment. |
| [docs/verification-evidence.md](verification-evidence.md) | Additive explanation contract. |
| [docs/agent-scope-controls.md](agent-scope-controls.md) | Selected owner versus all owners and unchanged membership. |
| [src/agentguard/models.py](../src/agentguard/models.py) | Optional typed provenance; historical serialization compatibility. |
| [src/agentguard/rejection_provenance.py](../src/agentguard/rejection_provenance.py) | Pure joining/consolidation, explanation copies and rendering. |
| [src/agentguard/cli.py](../src/agentguard/cli.py) | Post-matcher enrichment and scan/findings/review context. |
| [src/agentguard/scopes.py](../src/agentguard/scopes.py) | Complete persistence and selected-owner presentation copies. |
| [src/agentguard/scope_reporting.py](../src/agentguard/scope_reporting.py) | Render selected finding context. |
| [src/agentguard/metrics/calculator.py](../src/agentguard/metrics/calculator.py) | Recursively remove new nested excerpts from export only; no formula changes. |
| [tests/test_rejection_provenance.py](../tests/test_rejection_provenance.py) | Provenance, matching, ID, M9, scope, lifecycle, CLI and audit regressions. |
| [tests/test_scopes.py](../tests/test_scopes.py) | Compare every raw M8 field while permitting only approved provenance additions. |
| [tests/fixtures/rejection_audit/agent.py](../tests/fixtures/rejection_audit/agent.py) | Tools, validator, shared owners and distinct rejection paths. |
| [tests/fixtures/rejection_audit/negative.py](../tests/fixtures/rejection_audit/negative.py) | Same-name, unregistered, unknown/ambiguous owner and adapter controls. |
| [tests/fixtures/rejection_audit/tests/evidence.py](../tests/fixtures/rejection_audit/tests/evidence.py) | Source-only pytest verification and negative controls. |
| [tests/fixtures/rejection_audit/evals/cases.py](../tests/fixtures/rejection_audit/evals/cases.py) | Pydantic Evals exception-text control. |
| [tests/fixtures/rejection_audit/evals/cases.jsonl](../tests/fixtures/rejection_audit/evals/cases.jsonl) | JSONL exception-text controls. |
| [tests/fixtures/rejection_audit/inventory.json](../tests/fixtures/rejection_audit/inventory.json) | Independent expected owners, source pins and pending human review. |
| [tests/fixtures/rejection_audit/compatibility_baseline.json](../tests/fixtures/rejection_audit/compatibility_baseline.json) | Pre-implementation raw snapshot/report hashes. |
| [tools/behavior_audit/rejection_provenance.py](../tools/behavior_audit/rejection_provenance.py) | Read-only deterministic audit and historical compatibility checks. |

No marketing copy, examples, extractor/matcher implementations, selection/lifecycle
code, SQLite schema, package dependencies, release metadata, version, CI workflows,
commits, pushes, tags or publication were changed by this milestone.
