# Finding presentation refinement — M11.1

This milestone changes terminal presentation only. The default uses a structured,
evidence-first summary; `--details` adds progressive diagnostics after that exact
summary. It does not change extraction, matching, confidence, missing dimensions,
selection, guidance calculations, stable identities, JSON, metrics or persistence.
Controlled layout correctness is **not demonstrated engineer comprehension**.

The source baseline is commit `ce7fc12` (M11.5 merge), version `0.1.12`.
[PyPI 0.1.12](https://pypi.org/project/skout-scan/0.1.12/) was confirmed published
before this work. This presentation is unreleased source work for a future
release. Package metadata and dependencies are unchanged; no release actions occur.

## Baseline and real before/after output

The first working-tree run had 842 passing tests and three failures caused by
public-example copies inheriting pre-existing `.agentguard` state. That state was
preserved. A disposable copy of tracked source, with the installed CLI on PATH,
passed all **845 baseline tests**. Baseline Ruff, formatting, production/audit
mypy and the existing release harness also passed (wheel and sdist installs).
The affected tests now ignore local state/environments/caches when copying examples.

[The frozen pre-change capture](../tests/fixtures/presentation_audit/baseline.json)
contains actual CLI output, raw existing M11 assessment contexts, exact guidance
objects and normalized compatibility data. Commands ran only on disposable copies;
no target agent or test was executed. Only temporary paths, timestamps and random
scan/event identifiers are normalized in compatibility captures. CLI paths shown
as `[workspace]` replace the actual temporary repository path.

The original graph audit fixture has no selected findings. An additional public
LangGraph trace was therefore captured through the untouched pre-change checkout.
Partial/covered evidence experiments remain explicitly labelled **assessment
contexts**, not invented selected findings. The prior M11 source-pinned cases and
all historical audit baselines remain unchanged.

Actual validator commands on a copied `examples/pydantic-ai-agent`:

```bash
skout scan [workspace] --no-progress
skout findings --repository [workspace]
skout findings --repository [workspace] --details
```

Before, at 100 columns:

```text
                                        Skout Scan findings
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Finding ID             ┃ Status ┃ Coverage              ┃ Classification ┃ Title                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│ finding_f232f8c4fbb9a… │ open   │ potentially_uncovered │ -              │ validate_refund       │
│                        │        │                       │                │ failure behavior is   │
│                        │        │                       │                │ potentially uncovered │
└────────────────────────┴────────┴───────────────────────┴────────────────┴───────────────────────┘

finding_f232f8c4fbb9aae3723cde30
  Behavior: validate_refund raises ModelRetry when decision.refund_amount > 500
  Registered by agent: agent.py#refund_agent
  Registered callable: agent.py::validate_refund
  Verification goal: verify the declared condition and outcome together.
  Verification: potentially_uncovered; assessable_gap
  Evidence: No qualifying eval candidates discovered in the supported scan.
  Missing dimensions:
    functionality: The recognized evidence does not establish the intended callable or graph.
    condition: The recognized evidence does not establish condition decision.refund_amount > 500.
    expected_outcome: The recognized evidence does not verify the required expected outcome.
  Source: agent.py:38
  Reasons: no_qualifying_evidence, functionality_not_matched, condition_not_matched,
expected_outcome_not_matched
  Next step: Target agent.py::validate_refund. Exercise the explicit condition
decision.refund_amount > 500. Explicitly assert ModelRetry.
  Observed resolution: no; Confirmed impact: no
Static evidence only; use skout findings --details for full diagnostics.
```

After, at the same width:

```text
Skout Scan — Findings
Repository: [workspace]
1 finding; 1 open
────────────────────────────────────────────────────────────────────────────────────────────────────
Finding 1 of 1 · Potential eval gap

validate_refund rejection may lack verification
agent.py:38
Registered by: agent.py#refund_agent

Behavior:
  If decision.refund_amount > 500
  raises ModelRetry
Evidence:
  No qualifying eval candidates discovered.
Next step:
  Target this callable. Exercise the condition above. Explicitly assert ModelRetry.
Finding: f232f8c4
Static evidence only. Display IDs are abbreviations; copy full IDs with skout findings --details.
```

The complete default, detailed, review and scan traces for all six repository
views are in [the presentation audit](finding-presentation-audit.json), under
`captures`. That includes the public validator, partial-tool fixture repository,
conditional LangGraph route, shared-owner scoped view and multiple findings.
`observations` additionally records actual renderer output for all 19 existing
M11 assessment contexts, including partial rejection, graph owner mismatch,
ambiguous ownership, covered context and incomplete/unsupported evidence.

## Information hierarchy and evidence wording

Each finding has a progress heading and readable coverage interpretation, one
primary source, verified registered owners where available, then **Behavior**,
**Evidence**, **Next step** and a compact display ID. A single finding has no
summary table. Multiple findings are separated cards with `Finding i of n`;
all selected findings remain displayed. Existing scan previews remain bounded
at five findings, with full IDs for copying; scoped reports retain their previous
membership counts, diagnostics and preview limits.

| Existing evidence state | Primary presentation |
|---|---|
| No supported candidate | No qualifying eval candidates discovered. |
| Closest partial candidate | Identifies that original candidate, its verified dimensions and exactly what remains missing. |
| Wrong/unverified graph owner | Related evidence does not verify this graph's identity. |
| Ambiguous graph owner | Related evidence has ambiguous graph identity. |
| Incomplete/unsupported/unavailable/low-confidence analysis | Inconclusive; review evidence before deciding on a test. |
| Covered context | Qualifying verification evidence found; no recommendation for another test. |
| Historical record without structured explanation | Explicit historical-evidence fallback; saved explanation remains in details. |

Verified dimensions are taken only from the original closest M8 candidate's
recorded decision. Evidence is not ranked or combined across candidates. Partial
and covered contexts are never promoted into findings by this renderer.
Recommendations come from unchanged M11 guidance. Terminal text can refer to
"this callable" or "the condition above" instead of repeating its full identity
or expression. The actual source facts remain immediately above the action.
Unsupported/unavailable contexts do not gain concrete test instructions.

## Progressive diagnostics and deduplication

`--details` starts with the identical card, then adds provenance, candidate
verification evidence, grouped source references, verbatim source proof,
limitations, the original assessment, full identifiers and lifecycle metadata.
Registration declares ownership; it does not prove execution or test coverage.
The selected owner remains distinct from the full verified owner set.

A source location is grouped by its real recorded span and purpose. References
sharing the same span have combined purpose labels; no adjacent spans are invented.
The primary location is not repeated as an identical reference. Full callable,
registration, eval, behavior and finding IDs remain available for investigating
false positives. Original reason codes remain unchanged in existing metrics and
scoped JSON exports rather than being printed as raw arrays.

Behavior, evidence and action sections occur once. The standalone verification
goal and old generic suggested-scenario repetition are removed from supported
finding cards. Missing dimensions for a closest candidate are not repeated in a
second list. Verbatim source proof or a candidate-specific diagnostic can repeat
a literal for a different purpose; this is not a universal zero-repetition claim.

## IDs, review and terminal widths

Display IDs are unique prefixes of the existing canonical IDs, initially eight
characters and extended when necessary to disambiguate collisions. They are never
stored or accepted as aliases. Both findings and review provide a hint to copy
full IDs using `skout findings --details`. Feedback and impact commands still
require the full canonical ID. Full IDs are printed without ellipsis in details.

Findings and review use the same renderer and wording. Feedback choices, reason
prompts, queue ordering, skip behavior, progress and persistence are unchanged.
Both default and detailed read-only views preserve database bytes and metrics.
Observed resolution and explicit confirmed impact remain distinct.

Rich wraps actual text at 60/80/100/120 columns. There is no wide finding table
or diagnostic truncation. Restrained warning/coverage emphasis supplements the
text; no-color and ANSI modes retain the same content. Long identifiers/paths
may wrap naturally; structured exports retain their complete values.

## Independent controlled audit

The new [presentation inventory](../tests/fixtures/presentation_audit/inventory.json)
records expected evidence states and layout requirements over existing M11 cases.
Existing independent M11 facts/actions, real source locations and frozen technical
snapshots are reused. Two new audit runs must produce identical JSON.

| Check | Passed/checked |
|---|---|
| action preservation | 19/19 |
| deterministic rendering | 19/19 |
| primary section uniqueness | 19/19 |
| evidence statement correctness | 19/19 |
| full id accessibility | 31/31 |
| json compatibility | 37/37 |
| narrow terminal layout | 76/76 |
| required content completeness | 95/95 |
| source reference accuracy | 91/91 |

For the one actual validator detail trace, repeated occurrences after the first
of three pinned facts (condition expression, canonical callable, registered owner)
fell from **8 to 0 per finding**. This metric deliberately names its three facts
and denominator of one finding; it is not a broad usability or precision score.
Source proofs are included in the counting rule. No primary Behavior/Evidence/
Next-step section is duplicated across the 19 controlled contexts.

## Compatibility and validation

- Before/after raw assessments and guidance objects are identical for all 19 cases.
- Six repository views have identical normalized metrics, root JSON, scoped JSON,
  technical snapshots, finding IDs and read-only state checks (37 checks total).
- All nine M10.1–M11 audit reports regenerate byte-for-byte unchanged. Behavior,
  eval/finding IDs and fingerprints, M8/M9 decisions, M10.3 membership, feedback,
  lifecycle and metrics retain their existing regression contracts.
- The final suite contains **932 tests**. Required Ruff, formatting, production/audit
  mypy and diff checks are run. Python 3.12–3.15 source and installed-artifact checks
  are recorded in the completion report; configuring CI alone is not a passing run.
- The existing release harness builds/inspects wheel and sdist, checks metadata
  and declared-minimum backend, installs outside the checkout and tests actual
  console commands. Dependency setup may download packages; runtime checks block
  network/non-Git subprocesses and include target-execution traps.

Reproduce:

```bash
pytest
ruff check .
ruff format --check .
mypy src/agentguard
mypy tools/behavior_audit
git diff --check
python -m tools.behavior_audit.presentation --output docs/finding-presentation-audit.json
python -m tools.release_validation --report release-validation.json
```

## Changed-file manifest

| File(s) | Purpose |
|---|---|
| `src/agentguard/presentation.py` | Internal terminal view, unique display IDs, shared cards, diagnostics and previews. |
| `src/agentguard/cli.py` | Wire findings/review and bounded normal-scan previews to the common renderer. |
| `src/agentguard/scope_reporting.py` | Same finding vocabulary in scoped previews; membership/JSON untouched. |
| `src/agentguard/guidance.py` | Delegate the existing rendering hook; guidance calculations unchanged. |
| `tests/test_presentation.py` | Widths, evidence states, IDs/collisions, historical payloads, multiple findings, shared scope, feedback, read-only and compatibility checks. |
| `tests/test_cli.py`, `test_guidance.py`, `test_rejection_provenance.py`, `test_verification_evidence.py`, `test_demo.py` | Update intended terminal assertions; retain semantic/JSON/lifecycle checks and request details when full IDs are required. |
| `tests/test_comparison.py`, `test_obligation_mapping.py`, `test_orchestration.py` | Prevent example copies inheriting developer scan state or virtual environments. |
| `tools/behavior_audit/presentation.py` | Deterministic source-backed terminal/compatibility audit and real CLI capture. |
| `tests/fixtures/presentation_audit/inventory.json` | Explicit presentation expectations. |
| `tests/fixtures/presentation_audit/baseline.json` | Frozen actual pre-change CLI and technical data; not regenerated. |
| `docs/finding-presentation-audit.json` | Measured checks, actual before/after traces and assessment-context renders. |
| `docs/finding-presentation-refinement.md` | This design, evidence, validation and limitations report. |
| `docs/finding-quality-actionability.md` | Link M11 guidance semantics to the new terminal layout. |
| `requirements.md` | Presentation-only requirements and invariants. |
| `README.md` | Actual source presentation, canonical-ID usage and published/source distinction. |

## Limitations

No independent engineer study has measured comprehension or usefulness. Static
analysis still cannot recognize every alias, fixture, wrapper or dynamic pattern.
Historical records without structured evidence cannot support detailed verified
claims. Display prefixes can lengthen when another finding shares their prefix;
canonical IDs do not change. Existing structured exports retain raw diagnostics
when terminal interpretation alone is insufficient. This milestone adds no
framework support, matching logic, API key, telemetry or target execution and
performs no version bump, commit, push, tag or publication.

## Final installed-artifact results

The final source wheel and sdist passed the existing release harness with GitHub
color settings enabled. Wheel and sdist were each installed on Python 3.12, 3.13,
3.14 and 3.15: **8/8 clean installations passed**, including `pip check`, isolated
imports and the real CLI. The full source suite passed 932 tests per version.
Ruff lint/format, production/audit mypy, Markdown links/fences and diff checks pass.
No historical release-validation or technical audit report was overwritten.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `skout_scan-0.1.12-py3-none-any.whl` | 135713 | `9ceed5cf682f17785e2c7af7f725dcb484472c577de96308da4fdf8f6f8428d8` |
| `skout_scan-0.1.12.tar.gz` | 116816 | `1adea9501854b7cb213522dbeb8a22adc5fb30abc75356928d059887ffd57748` |

These are unpublished development artifacts retaining the existing source version,
not replacements for the published PyPI files. Their metadata and every runtime
module were inspected; Twine checks and the exact minimum-backend builds passed.
Public Pydantic AI, LangGraph and CrewAI workflows resolved their original finding
IDs using supplied evals, preserved feedback and did not infer confirmed impact.
Runtime guards passed without network/unsupported subprocess attempts or target
execution. The validation environments contained no agent-framework runtimes.


## Final M11.1 UI polish

The following captures show the same Pydantic AI validator finding at 100
columns. The audit substitutes `[workspace]` for its temporary repository path.

### Before

```text
Skout Scan — Findings
Repository: [workspace]
1 finding; 1 open
────────────────────────────────────────────────────────────────────────────────────────────────────
Finding 1 of 1 · Potential eval gap

validate_refund rejection may lack verification
agent.py:38
Registered by: agent.py#refund_agent

Behavior:
  If decision.refund_amount > 500
  raises ModelRetry
Evidence:
  No qualifying eval candidates discovered.
Next step:
  Target this callable. Exercise the condition above. Explicitly assert ModelRetry.
Finding: f232f8c4
Static evidence only. Display IDs are abbreviations; copy full IDs with skout findings --details.
```

### After

```text
Skout Scan — Findings
Repository: [workspace]
1 finding · 1 open
────────────────────────────────────────────────────────────────────────────────────────────────────
Finding 1 of 1 · Potential eval gap

validate_refund rejection may lack verification
agent.py:38 · Registered by agent.py#refund_agent

▸ Behavior:
  If decision.refund_amount > 500 → raises ModelRetry

◇ Evidence:
  No qualifying eval candidates discovered.

→ Next step:
  Test validate_refund with the condition above and explicitly assert ModelRetry.

Finding: f232f8c4

≡ Additional details

Provenance:
  Callable: agent.py::validate_refund
  Registered as: Output validator
Source references:
  Agent declaration: agent.py:20–25
  Registration: agent.py:33
  Callable definition: agent.py:34–39
  Rejection: agent.py:37–38
Missing verification:
  Correct callable or graph
  Required condition
  Expected outcome
Source evidence:
  raise ModelRetry("High-value refunds require human review")
Limitations:
  Static analysis only; Skout does not execute agents or tests. Unsupported eval patterns may not be
recognized.
  Registration does not prove runtime execution or eval coverage.
  Guidance is not a runtime result or business priority assessment.
Assessment:
  Coverage: potentially_uncovered
  Confidence: high
Lifecycle:
  State: open
  Classification: not classified
  Observed resolution: no
  Confirmed impact: no
Identifiers:
  Finding ID: finding_f232f8c4fbb9aae3723cde30
  Behavior ID: behavior_036ed8c2b01e2a0c881658fd
Provenance identifiers:
  Callable ID: callable_f22429716325a23510bef18f
  Registration ID: registration_fe4d1ee2e828b4787a4c1715
  Related behavior ID: behavior_f110ef2808c1dcf7da7132c2
```

The title is prominent, with the source location and owner on a subdued line.
The renderer joins the existing condition and outcome with an arrow and names
the canonical callable in the suggested action. When the displayed inventory
contains distinct callables with the same short name, the action qualifies
them as `file::symbol`. Unresolved identities use a generic reference.
Unconditional behaviors keep their original statements.

Behavior, Evidence, Next step and Additional details use the single-column
symbols `▸`, `◇`, `→` and `≡`. Restricted encodings use `>`, `?`, `->` and
`+`. The text labels carry the meaning in either mode. Rich wraps at the
terminal's cell width. The layout has one blank line before Behavior, Evidence,
Next step and Additional details, and omits empty optional sections. Findings,
review and bounded scan previews share the summary wording and ordering.
Plain redirected output omits ANSI styling by default. Glyph availability
still depends on the terminal font.

The validator's detailed view has four source roles across four recorded
locations. It uses **Callable definition** for the former
**Behavior source, Callable definition** row and **Rejection** for the guarded
raise. Exact locations with genuinely different roles share one row. An
existing rejection span can represent a nested anchor for the same symbol and
role. The primary location stays under the title, and distinct evidence and
source spans are preserved. The Limitations section consolidates equivalent
display text while retaining all structured records.

The compact reference `f232f8c4` stays in the summary. Full finding and behavior
IDs sit near the bottom of `--details`, followed by a dim provenance identifier
group. The short reference can lengthen to avoid a collision. Review and
feedback continue to use the canonical finding ID.

[Presentation audit](finding-presentation-audit.json) records actual CLI
transcripts for the validator, partial rejection, public LangGraph route,
shared scoped finding and multiple findings. The audit verifies 76/76
rendered layouts at 60, 80, 100 and 120 columns, 76/76 section icons,
57/57 spacing checks, 19/19 strict ASCII renders, 91/91 source reference
checks, 31/31 full-ID accessibility checks and 37/37 normalized compatibility
checks. Plain, redirected, and `NO_COLOR` output are also exercised by the
terminal tests. The nine historical technical audits reproduced byte-for-byte.

The full source suite passed **944 tests per interpreter** on Python 3.12,
3.13, 3.14 and 3.15. Ruff lint and format, production and audit mypy, and
`git diff --check` passed. The presentation audit regenerated byte-for-byte.
The example state databases retained their original hashes.

The M11.5 release harness passed **8/8 clean wheel and sdist installations**
across those four interpreters, including metadata checks, the minimum-backend
build, `pip check`, and installed console workflows. This pass produced the
following unpublished validation artifacts at the existing version.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `skout_scan-0.1.12-py3-none-any.whl` | 137928 | `23cf9c10c9687e55213fd55705e3169f044723ba1f1914c26ac3c1727b0d87c8` |
| `skout_scan-0.1.12.tar.gz` | 118962 | `656c08b9675c97516ffacb9156122ed301be618fa8c3b74e42824702b3ea02f8` |

### Polish changed-file manifest

| File | Change |
|---|---|
| `src/agentguard/presentation.py` | Callable display identity, connected statements, headings, spacing, source roles, limitations and ID styling. |
| `src/agentguard/cli.py` | Shared card and preview names and compact references in findings, review and normal scans. |
| `src/agentguard/scope_reporting.py` | Shared compact presentation for scoped previews. |
| `tests/test_presentation_polish.py` | Twelve terminal regression cases, including width, fallback and command consistency. |
| `tests/test_rejection_provenance.py` | Align two terminal assertions with the owner line. |
| `tools/behavior_audit/presentation.py` | Verify the layout and capture the real CLI views. |
| `tests/fixtures/presentation_audit/inventory.json` | Record independent presentation expectations. |
| `tests/fixtures/presentation_audit/pre_polish.json` | Archive the original M11.1 terminal captures and results. |
| `docs/finding-presentation-audit.json` | Store current terminal captures, checks and pre-polish results. |
| `docs/finding-presentation-refinement.md` | Record the final design, captured output and validation. |
