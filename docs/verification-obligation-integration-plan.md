# Future verification-obligation integration contract

This is a proposed follow-up plan, not production functionality implemented by
M10.2d. The [mapping study](verification-obligation-mapping.md) and
[structured audit](verification-obligation-audit.json) are the measured basis.
All proposed matcher/extraction changes need separately approved scope.

## Recommended first integration: enrich existing explicit rejections

Start with existing guarded rejection behaviors on resolved registered tools and
Pydantic AI output validators. This is the smallest credible precision benefit:
retain explicit conditions/outcomes, consolidate shared registration provenance,
and avoid duplicate concerns. It does not promise new uncovered findings or
pretend that relationships already improve behavioral recall.

| Contract element | Required behavior |
|---|---|
| Recognition | An existing available `Behavior` has an explicit condition and `raise` outcome, and resolved tool/validator registration identifies exactly the same file-local canonical callable. |
| Source facts | Existing condition/action/arguments/evidence, canonical callable, registration and definition references. Missing or ambiguous provenance abstains. No callback-body reparsing or propagation inference. |
| Representation | Enrich the existing behavior/assessment explanation with relationship provenance; do not create another invocation/failure or public coverage category. |
| Evidence | Reuse M8 matching for tested direct pytest calls, condition inputs and expected exceptions. Expected fields, helper calls, wrappers or names alone cannot prove the failure path. No assumption that JSONL/Pydantic Evals exception text is an assertion. |
| Deduplication | One existing concern per canonical callable + condition + action; prefer the existing failure behavior identity. Merge owner links and equivalent branch evidence. Owner-specific obligations require independently explicit owner behavior. |
| Stable identity | Preserve behavior ID, finding ID, fingerprint conventions and saved feedback. Registration-owner edits change provenance, not an otherwise unchanged existing failure identity. Source renames retain existing product limitations. |
| Finding eligibility | Existing selection only: available assessment, high assessment confidence, actionable coverage/type rules and concern deduplication. Eligibility itself confers no finding confidence. No new finding per registration. |
| Missing facts/removal | Mark enrichment unavailable or omit context, without inferring resolution. If a behavior disappears, use existing lifecycle semantics; missing extraction does not mean newly covered. Preserve history; no deletion/migration or new states. |
| M8/M9 | M8 condition/outcome semantics and M9 behavior comparisons remain unchanged. Provenance-only edits must not create coverage deltas. |
| Acceptance | Public validator resolution loop and IDs stay unchanged; shared owners yield one concern; wrong subject/condition/helper/name/guardrail controls do not cover; all old audit and lifecycle snapshots remain identical. |

Do not broaden this step to all bound-method bodies. M10.2a proves callable
identity, not an extracted parent rejection contract. `Storage.fetch`'s internal
raise does not currently have source-backed propagation or argument composition.

## Priority 2: a narrowly defined literal-route selection contract

Three curated routes are testable, but current M8 has no key-to-target selection
representation. A separate implementation proposal should add only this contract
before broader adapter or semantic behavior expansion.

- Recognition must retain the established parent, exact registry/call site,
  literal key, canonical target, all guards and selector binding. If the current
  extraction lacks a typed selector-to-input binding, add that small fact under
  an approved contract; do not recover it by loosely interpreting evidence text.
- Model the obligation as **selection at a specific lookup site**, rather than
  handler success or generic tool invocation. Do not coerce it into an existing
  `tool_invocation` or a free-text condition that existing matching might overclaim.
- Sufficient evidence must bind invocation of that exact dispatcher, the correct
  literal route and required guards, and an assertion of the selected target.
  A supported bounded spy/mock assertion pattern could qualify only after its
  call provenance is explicit. The audit's spy artifact is a prospective example,
  not proof of currently supported instrumentation/data-flow analysis.
- Same outputs from adjacent handlers, a directly called handler, an expected
  field, or a test named after the key must not suffice. An unverified selection
  remains partial/inconclusive under the future approved model.
- Deduplicate by repository-local canonical parent, relative lookup site/context,
  key and target. Shared owners merge provenance; different keys and relevant
  contexts remain distinct. Use a separately versioned future obligation identity
  derived from the existing stable relationship identity. Do not reuse prototype
  IDs as persisted production finding IDs or alter historical IDs.
- Surface findings only after independent evidence negatives, source availability,
  assessment confidence and selection usefulness have been validated. Eligible
  does not imply high-confidence or actionable by default.
- Keep M9 integration off initially. A later approved comparison contract must
  distinguish material key/target/guard edits, extraction loss and verified test
  changes. Do not report improvements from added tests without sufficient evidence.

Acceptance requires two routes, shared targets, wrong/adjacent keys, unresolved
selectors, mutation/aliases, guarded sites, verified/unverified calls, direct
helper tests, formatting/line stability, shared owners, same-state resolution,
feedback retention and no unrelated finding churn. No general instrumentation,
mock tracing or interprocedural inference is justified by this study.

## Existing graph routes: tighten ownership before extending obligations

The audit found three false sufficiency judgments from a wrong graph or helper
while route literals and expected targets matched. Existing graph callbacks remain
context-only. A narrow future matcher change must require an explicit binding to
the correct graph/route context as well as the condition and expected target.
Do not interpret node registration, an edge, callback name or returned dictionary
as proof that a callback ran or produced a state transformation.

Keep existing route behavior IDs and history. Separately approve any changes to
coverage assessments caused by this ownership fix; do not bundle them into the
initial rejection-provenance integration. Regression fixtures must pair correct
and incorrect graph identities, shared callback names, direct helper calls,
adjacent routes, missing outcomes, JSONL cases and Pydantic Evals cases. Ordinary
M9 baseline/solution reports must be explicitly reviewed if the matcher changes.

## Exception fallback: retain eligibility, defer production assessment

Two source-explicit handler invocations are meaningful claims, but handler entry,
exception occurrence and target invocation need a new evidence link. The current
M8 matcher cannot bind a controlled parent failure to a specific handler-local
fallback assertion. Direct fallback tests or observing `TimeoutError` alone must
not establish that relationship.

A future contract must retain canonical parent/target, actual handler/guard,
exception tuple, call site and all typed conditions. It must support one explicit
bounded handler level, identify controlled exception evidence at the correct parent
operation and verify fallback selection. Bare/generic/dynamic handlers, unresolved
targets, helper-only tests and nested propagation abstain. No fallback return,
recovery success or primary exception reachability is inferred.

Use a separate versioned identity based on the existing relationship context;
handler/type/target changes are material. M9 and lifecycle integration need
separate regression approval. Required fixtures include separate handlers, tuples,
wrong exception/target, no verification, parent-to-handler linkage, guarded calls,
stable IDs and retained feedback. Do not implement generic mock/data-flow tracing
to make the existing spy artifact assessable.

## Context-only and unsupported cases

Keep registration-only tools, simple graph callbacks, task executors, shared
callable registrations and one-hop adapters as structural context. Task prose,
`expected_output` configuration, arbitrary callback dictionaries and internal helper
branches do not supply an independent supported behavioral contract. Never invent
outcomes from `execute`, `fallback`, `validate`, directory or framework names.

Unresolved/ambiguous targets and unsupported exception propagation stay outside
eligible obligations. Missing typed facts should lead to a narrowly justified
future extraction proposal or continued abstention, not a parallel AST scanner,
semantic guess, global call graph or LLM inference.

## Identity and lifecycle safeguards across any later integration

1. Existing behavior/finding IDs and local feedback must survive provenance,
   owner, formatting and line-only changes when their existing identity is intact.
2. New categories require their own approved versioned representation and stable
   identity. Parent/key/handler/target/context are structural inputs; absolute
   roots, scan order, physical lines and time are excluded.
3. Shared owners do not multiply obligations. An owner-specific condition needs
   explicit source facts and an independent regression case.
4. Removal, unsupported edits or incomplete scans never prove covered status.
   Preserve old state and apply existing inconclusive/no-longer-observed handling
   only when its current rules permit. Do not erase history or fabricate resolution.
5. An eval addition can resolve a finding only after a complete supported assessment
   verifies the same obligation. Confirmed impact still requires explicit engineer
   feedback; it cannot be inferred from resolution.
6. Keep SQLite schema, lifecycle states, metrics formulas and ordinary M9 semantics
   unchanged unless an additional, independently tested contract is approved.

M10.3 relevance/scope selection, agent deployment inference, traces, semantic
requirements, arbitrary aliases, cross-module data flow, recursive discovery,
LLMs, eval generation, release gates and production coverage scores remain out
of scope. None of the controlled metrics validate production-wide actionability.
