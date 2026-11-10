# Release readiness — M11.5

**Recommendation: conditionally ready.** Local wheel/sdist and regression checks
pass on Python 3.12 and 3.13. Release remains gated on green Python 3.14/3.15 CI
results for the exact release commit and maintainer verification of external
Trusted Publisher/environment protections. Configuring CI is not a passing CI run.

This milestone validates distribution readiness for completed M8–M11 capabilities.
It does not publish anything or add scanner functionality.

## Package identity and version

| Field | Validated value |
|---|---|
| Distribution | `skout-scan` |
| Authoritative version | `0.1.11`, from `pyproject.toml` |
| Console entry point | `skout = agentguard.cli:app` |
| Import package | `agentguard` |
| Python requirement | `>=3.12` (no declared upper bound) |
| Build backend | `hatchling.build`, `hatchling>=1.27.0,<1.32` |
| License | Apache-2.0; license file and SPDX expression checked |
| Runtime dependencies | Typer, Rich, Pydantic and PyYAML, with existing bounds |

The proposed next release is **0.1.12**, following the existing pre-alpha patch
release convention for additive compatible changes. No version was changed.
The inspected public PyPI 0.1.11 wheel already includes scopes, but lacks
rejection provenance, M11 guidance and `--details`. These source features must
not be advertised as already installed by `pip install skout-scan`.

## Acceptance inventory

| Area | Status | Evidence / release gate |
|---|---|---|
| Metadata | pass | Built name/version, CLI, Python requirement, SPDX license, URLs, UTF-8 README and dependency constraints match source. |
| Dependencies | pass | Four fresh wheel/sdist installations pass `pip check`; no dev extras or framework runtimes installed. |
| Wheel | pass | Every runtime source file and `py.typed` matches the checkout byte-for-byte; metadata and entry point present. |
| Sdist | pass | Independently builds/installs outside checkout; source, metadata, README and license present. |
| Build backend | pass | Default resolved backend and exact declared minimum build both artifacts with valid metadata. |
| Installed CLI | pass | Real console executable, help and version outside checkout; imports inside each noneditable environment. |
| Public examples | pass | Installed LangGraph, Pydantic AI and CrewAI walkthroughs, scopes, guidance, details and supplied-eval resolution. |
| SQLite | pass | Stable findings, feedback retention, resolution history/eval references and no automatic confirmed impact. |
| Documentation | pass | README distinguishes source from PyPI, provides wheel install, and uses PyPI-safe GitHub links. |
| Automation contract | pass | Static checks verify matrix, aggregate gate, tag-only release, pre-publish smoke and publish-only OIDC permission. |
| Regression compatibility | pass | 840 tests pass on both local versions; nine current audit reports remain byte-identical. |
| Python 3.12 / 3.13 | pass | Full source suite and both installed distribution types validated. |
| Python 3.14 / 3.15 | blocked | Interpreters unavailable locally; configured CI matrix must pass on the release commit. |
| External publishing protections | blocked | Maintainer must verify PyPI Trusted Publisher and GitHub `pypi` environment restrictions/approvals. |
| Publication | not-applicable | No upload, version bump, commit, push, tag or GitHub release performed. |

## Build and isolated installation evidence

[release-validation.json](release-validation.json) records artifact names, SHA-256
hashes, sizes, metadata, minimum-backend builds, dependency versions, per-install
smoke results and remaining gates. Two complete harness runs produce identical
structured reports with equivalent dependency resolution. Fixed `SOURCE_DATE_EPOCH`
removes archive timestamp variation; no temporary paths or wall-clock timestamps
are included. Future dependency/backend resolution can change hashes/results and
is recorded rather than hidden.

Both wheel and sdist pass Twine metadata checks. The default build uses isolation;
the additional minimum-backend check uses its dedicated environment with the exact
backend version. Each artifact is installed into separate fresh virtual environments
outside the checkout on Python 3.12 and 3.13. Module paths, noneditable provenance
and console entry points are checked. Neither install contains pytest, Pydantic AI,
LangGraph or CrewAI.

The wheel contains runtime package files and distribution metadata. The sdist
intentionally contains runtime source, packaging metadata, license, README and
release instructions. Examples, tests and audit tooling remain repository resources;
they are not required for installed scanning. Both archives are checked for state
databases, environments, secrets filenames, caches, Git history, unsafe archive
paths/links, recordings and checkout paths. No runtime resource was missing.

## Installed CLI and representative framework patterns

Every clean installation exercises real commands against disposable public examples:

- `doctor`, `scopes` and `scopes --json`: framework detection, deterministic selectors
  and no discovery-time state creation.
- `scan`, scoped `scan --json`, `findings`, `findings --details`, `review` and
  `review --details`: supported guidance/diagnostics, unchanged IDs, read-only
  review skip, and persistent `add_eval` feedback.
- `metrics` and `metrics --json`: existing export fields plus optional guidance,
  without nested source excerpts.
- Invalid selectors and scope/baseline conflicts: nonzero failure without changing
  SQLite state or silently falling back to a global scan.
- M9 baseline comparison against actual disposable Git commits: repeated JSON
  results match; source/Git hashes remain unchanged and no database is created.

Pydantic AI validates the refund agent, registered validator/tool ownership and
source-backed `ModelRetry` rejection context. Its supplied retry eval resolves the
original validator finding. LangGraph validates conditional routes and graph
ownership: wrong-owner evidence does not cover the route; the correct supplied
JSONL solution does. Scanning a different graph does not resolve an out-of-scope
finding. CrewAI validates the existing tool and Task executor relationship and
supplied escalation test. These are representative structural contracts, not
exhaustive framework support.

All examples reuse the same SQLite database across scans. The same finding ID
becomes resolved/covered, `add_eval` survives, new eval references appear in
resolution history, and confirmed impact remains false. No automatic
`confirm-impact` command is issued.

## Demonstrated compatibility fixes

1. **Python 3.13 structural serialization:** changed `ast.dump` defaults omitted
   empty fields, causing 20 fingerprint/audit failures in the full suite despite
   passing CLI smoke tests. `stable_ast_dump` restores the established Python 3.12
   representation on 3.13+. Seven extractors use it at existing serialization
   points. Frozen expectations and baselines are unchanged; no parsing, matching,
   selection or identity scheme was redesigned.
   Historical snapshots generated with the old Python 3.13 defaults can differ
   in fingerprints/relationship IDs from the restored canonical representation;
   stored history is not rewritten. The frozen Python 3.12 contract is preserved.
2. **Build-backend minimum:** the old Hatchling 1.25.0 minimum rejects
   `project.license-files`. Hatchling 1.26.3 builds but lacks the required SPDX
   `License-Expression`. Verified Hatchling 1.27.0 builds both distributions with
   correct metadata, so only the build dependency lower bound changes. Runtime
   dependency constraints are unchanged.

The clean baseline had **813 passing tests**, rather than the historical 810
quoted in the prompt (three terminal-width regression cases). The final suite has
**840 passing tests** on each locally tested interpreter. Ruff lint/format,
production mypy, audit/tooling mypy and `git diff --check` pass. All nine current
audit reports regenerate byte-for-byte unchanged: discovery, registrations,
orchestration, delegation, verification obligations, graph ownership, scopes,
rejection provenance and actionability. Historical files and frozen fixtures were
not rewritten.

## Security and publishing boundaries

Dependency downloads may require network access during setup. Installed CLI smoke
tests use a temporary environment-only audit hook blocking socket/network requests
and non-Git subprocesses. Positive probes verify the guard is active. Target
Python/conftest execution traps never run; scanning needs no provider API key,
framework import or eval execution. Actual runtime checks record no denied
network/subprocess attempts. This is controlled privacy/static-execution
validation, not a malicious-repository security audit.

The harness copies an explicit public example file list and cleans up only its
own temporary directories. It never changes tracked examples or developer state.
No telemetry or source upload is introduced.

CI requests 3.12–3.15 and keeps `test-and-build` as an aggregate requiring the
full matrix. Release remains `v*` tag-only, checks tag/version agreement, builds
and validates installed artifacts before the separate publishing job. Only that
job requests `id-token: write`, using the existing `pypi` environment. Ordinary
branch/PR checks cannot publish. The release workflow does not independently
prove its tag commit passed full CI: the maintainer must verify this before
authorizing a tag. External Trusted Publisher settings and environment approvals
cannot be established from repository files; they remain explicit release gates.

## Changed-file manifest

| Files | Change |
|---|---|
| `.github/workflows/ci.yml` | Python matrix, validation checks, installed smoke, reports, stable aggregate gate. |
| `.github/workflows/release.yml` | Bounded existing build tools and pre-publish installed validation. |
| `.gitignore` | Ignore generated root validation reports. |
| `pyproject.toml` | Correct build-backend minimum; version unchanged. |
| `README.md` | Published/source distinction, source wheel installation, PyPI-safe links. |
| `docs/releasing.md` | Repeatable artifact checks and CI/publisher gates. |
| `docs/release-readiness.md` | This inventory and final assessment. |
| `docs/release-validation.json` | Deterministic actual artifact/install evidence. |
| `docs/release-notes-draft.md` | Unreleased summary and compatibility/remaining gates. |
| `tools/release_validation.py` | Build, archive inspection, isolated install and workflow driver. |
| `tools/release_smoke.py` | Installed console walkthroughs, offline probes and lifecycle checks. |
| `tests/test_release_validation.py` | Metadata, archive, guard, copying and workflow regressions. |
| `tests/test_ast_compat.py` | Frozen Python 3.12 canonical AST cases. |
| `src/agentguard/ast_compat.py` | Preserve structural AST serialization across interpreters. |
| `src/agentguard/extractors/behaviors.py`, `crewai.py`, `delegation.py`, `evals.py`, `orchestration.py`, `pydantic_ai.py`, `registrations.py` | Route existing AST serialization through compatibility helper only. |

## Publication actions requiring explicit authorization

After the remaining CI/publisher gates are verified:

1. Select release version and bump authoritative metadata.
2. Commit reviewed changes and push the release commit.
3. Create/push the matching version tag after that exact commit passes CI.
4. Approve PyPI publication through the existing protected workflow.
5. Create a GitHub release if desired.

None of these actions was performed by this milestone.
