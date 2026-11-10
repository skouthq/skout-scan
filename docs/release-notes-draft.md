# Draft release notes — proposed 0.1.12

**Unreleased draft.** Source metadata remains `0.1.11`; no tag, upload or release
has been authorized. The latest inspected PyPI release is `0.1.11`. A new patch
version is proposed under the existing pre-alpha release convention; these
additions preserve existing identities, assessment semantics and persistence.

## New capabilities since published 0.1.11

- Source-backed rejection provenance for existing guarded tool and Pydantic AI
  validator failures: canonical callable, condition, exception, registrations,
  all verified owners and actual source locations.
- Deterministic finding guidance based on existing M8 evidence and missing
  dimensions, including scoped finding JSON and the local metrics export.
- `skout findings --details` and `skout review --details` retain full diagnostics
  alongside the new concise default views.

Agent scope discovery and selection already ship in `0.1.11`; they are not new
framework support in this draft.

## Correctness improvements

- Preserve the established Python 3.12 structural AST bytes on Python 3.13+,
  avoiding interpreter-driven fingerprint/relationship churn without changing
  extraction, matching or frozen source expectations.
- Require Hatchling 1.27.0 or newer for the existing PEP 639 license metadata;
  the old declared Hatchling 1.25 minimum rejects `project.license-files`.

- CLI help tests tolerate ANSI styling and terminal line wrapping across four widths.
- Nested provenance/guidance exports preserve existing source-excerpt boundaries.
- Shared rejection registrations consolidate explanation context without
  multiplying findings or changing their IDs.

## Developer experience and distribution validation

- Clearer behavior, evidence, missing verification and bounded next-step presentation.
- A reproducible wheel/sdist validation harness checks fresh installations outside
  the checkout, offline runtime, public examples, scopes, SQLite lifecycle and M9.
- CI requests Python 3.12–3.15 and validates installed artifacts. Publication remains
  a separate tag-triggered Trusted Publishing job after artifact validation.
- README distinguishes the published package from unreleased source features and
  uses GitHub links that remain usable when rendered on PyPI.

## Compatibility notes

- Python requirement remains `>=3.12`; package, CLI and import names remain
  `skout-scan`, `skout` and `agentguard`.
- Behavior/eval/finding IDs, fingerprints, M8 coverage rules, M9 comparisons,
  M10.3 scope membership, feedback/lifecycle and metric formulas are preserved.
  Canonical serialization is the established Python 3.12 form. Historical
  snapshots generated with the old Python 3.13 defaults can have different
  fingerprints/relationship IDs; the fix restores canonical output without
  rewriting their stored history.
- Guidance is optional presentation data, not new SQLite state. Existing JSON
  fields are retained; default human-readable finding output is more concise.
- `scan --scope` with `--baseline` remains unsupported. Standalone `scan --json`
  still requires a baseline or selected scope.

## Known limitations and release gates

- Static analysis does not run agents/tests or prove runtime behavior. Unsupported
  aliases, fixtures and data flow remain unsupported.
- Guidance correctness in controlled fixtures is not demonstrated engineer usefulness.
- Local artifact validation covers Python 3.12 and 3.13; the configured 3.14/3.15
  CI jobs must pass before release readiness is unconditional.
- Verify external PyPI Trusted Publisher and GitHub `pypi` environment protections.
- See [release readiness](release-readiness.md) for actual build/install results
  and remaining authorization steps. No release date is asserted here.
