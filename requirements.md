# AgentGuard V0 Requirements

## 1. Product Objective

AgentGuard is a local-first developer tool that identifies potentially important AI-agent behaviors that are not adequately represented in the agent's existing eval or regression-test suite.

The primary V0 question is:

> What important behaviors in this agent appear insufficiently tested?

V0 exists to validate whether AgentGuard can find gaps that engineers consider useful enough to act on.

The core product hypothesis is:

> If AgentGuard identifies a credible missing eval, an engineer will add or modify a test because of that finding.

---

## 2. Target User

The primary V0 user is an AI or agent engineer responsible for an agent that already has an eval or regression-test suite.

The user may have:

- prompts
- tool definitions
- workflow definitions
- pytest tests
- JSONL eval datasets

The user should not need to create a new capability taxonomy, policy system, requirements database, or governance process before using AgentGuard.

---

## 3. Primary User Workflow

A user should eventually be able to run:

```bash
agentguard scan <repository-path>
```

AgentGuard should:

1. inspect the repository
2. discover supported agent artifacts
3. extract candidate agent behaviors
4. discover existing eval scenarios
5. map behaviors to existing evals
6. classify behaviors as:
   - covered
   - partially covered
   - potentially uncovered
7. explain why each finding was produced
8. suggest a missing eval scenario where appropriate
9. assign stable IDs to behaviors and findings
10. preserve user feedback across future scans
11. detect when a new or modified eval appears to resolve a previous finding

---

## 4. Supported V0 Inputs

V0 should support:

- Python source code
- prompt strings discoverable in supported Python source
- supported standalone prompt files
- agent tool definitions
- agent/workflow definitions
- LangGraph workflows where practical
- pytest-based tests/evals
- supported JSONL eval datasets
- optional AgentGuard configuration

V0 does not require:

- production traces
- cloud integrations
- Jira
- Confluence
- Slack
- governance systems
- policy repositories
- hosted storage

---

## 5. Initial Supported Prompt Formats

V0 should initially support prompt discovery from:

- Python string literals assigned to clearly identifiable prompt variables
- Python strings passed directly into supported agent/model constructors where statically discoverable
- `.txt` prompt files
- `.md` prompt files

Prompt extraction should remain static.

AgentGuard must not execute target repository code in order to discover prompts.

Unsupported or ambiguous prompt formats should be reported as unsupported rather than guessed.

Additional prompt formats may be added later.

---

## 6. Initial Supported JSONL Eval Format

V0 should support a minimal documented JSONL format.

Each line should be a valid JSON object.

AgentGuard should initially recognize these fields when present:

```json
{
  "input": "user input or scenario",
  "expected": "expected response or behavior",
  "metadata": {
    "name": "optional eval name",
    "tools": ["optional", "tool", "names"],
    "tags": ["optional", "tags"]
  }
}
```

Required:

- `input`

Optional:

- `expected`
- `metadata`
- `metadata.name`
- `metadata.tools`
- `metadata.tags`

If `expected` is absent, AgentGuard may still discover the scenario but must not assume the expected outcome has been verified.

Unknown fields should be preserved where practical but ignored for V0 matching unless explicitly supported.

Malformed JSONL records should produce a scan warning and should not crash the entire scan.

---

## 7. Behavior Representation

Each extracted behavior should contain at minimum:

- behavior ID
- human-readable description
- behavior type
- source file
- source symbol where available
- source evidence
- extractor that produced it

Potential behavior types may include:

- tool invocation
- tool failure
- conditional behavior
- workflow branch
- fallback behavior
- escalation
- prohibited action
- required action

Examples:

- a tool can be invoked
- a tool can fail with a specific exception
- a workflow can follow a conditional branch
- a prompt requires escalation above a threshold
- an agent must avoid taking an action if authentication fails

---

## 8. Eval Representation

Each discovered eval should contain at minimum:

- eval ID
- test/eval name
- source file
- source symbol where available
- scenario description where inferable
- assertions or expected outcomes where inferable
- tools or behaviors referenced where inferable

AgentGuard should distinguish between:

- an eval that merely mentions or invokes a behavior
- an eval that actually verifies the expected outcome

---

## 9. Coverage States

V0 supports three coverage states.

### Covered

A behavior may be marked `covered` only when AgentGuard has evidence that at least one existing eval:

1. materially exercises the behavior or relevant condition, and
2. verifies the expected outcome or invariant.

Examples of acceptable evidence may include:

- a pytest test invokes the relevant tool/branch and asserts the expected result
- a test explicitly verifies the expected exception/fallback/escalation
- a JSONL eval contains the relevant scenario and an expected outcome that corresponds to the behavior

Merely:

- mentioning the same tool
- referencing the same function
- exercising a neighboring branch
- using similar keywords

is not sufficient to mark a behavior as covered.

When evidence is ambiguous, prefer `partially_covered` or `potentially_uncovered`.

### Partially Covered

A behavior is `partially_covered` when an eval exercises the relevant functionality but does not fully verify an important condition, branch, failure mode, or expected outcome.

Example:

- the refund tool is tested successfully
- timeout behavior for the same tool is not tested

### Potentially Uncovered

A behavior is `potentially_uncovered` when AgentGuard finds no eval that appears to materially exercise and verify the behavior.

AgentGuard must avoid implying certainty.

Use language such as:

> Potentially uncovered

rather than:

> Definitely untested

unless a deterministic rule genuinely establishes that conclusion.

---

## 10. No Numeric Behavioral Coverage Percentage in V0

V0 must not present a numeric behavioral coverage percentage such as:

> 82% covered

The denominator for agent behavioral coverage is not yet trustworthy enough to support that claim.

V0 should instead present:

- identified behaviors
- matched evals
- partially covered behaviors
- potentially uncovered behaviors
- confidence and evidence

---

## 11. Findings

Each finding should contain:

- stable finding ID
- associated behavior ID
- coverage status
- confidence
- supporting evidence
- matched eval IDs
- explanation
- suggested missing scenario, if applicable

Every actionable finding should answer:

- what behavior was detected
- where it came from
- what existing evals were considered
- why AgentGuard believes coverage may be incomplete
- what additional scenario may close the gap

---

## 12. Static Analysis and Execution Safety

AgentGuard must not import or execute code from the target repository during scanning.

Scanning must be based on static analysis.

AgentGuard must not:

- import target repository modules
- execute target repository tests
- invoke target repository functions
- run arbitrary scripts from the target repository
- make network calls on behalf of scanned code
- access target application credentials by executing repository code

This requirement exists to avoid:

- side effects
- dependency conflicts
- unintended API calls
- credential exposure
- malicious code execution
- non-reproducible scanning behavior

AgentGuard may inspect source files, syntax trees, configuration files, and supported static metadata.

If a behavior cannot be determined without executing the target repository, V0 should report that limitation rather than execute the code.

---

## 13. Feedback Loop

Feedback and resolution tracking are mandatory V0 features.

Every actionable finding should support these dispositions:

- `add_eval`
- `valid_later`
- `already_covered`
- `not_relevant`
- `suppressed`

Feedback must persist locally across scans.

A future scan should attempt to determine whether a new or modified eval appears to resolve a previously open finding.

---

## 14. Feedback Meaning

### add_eval

The user indicates that the finding is valid and intends to add or modify an eval.

### valid_later

The user agrees the gap is valid but does not intend to address it immediately.

### already_covered

The user believes the behavior is already adequately tested and AgentGuard failed to detect the coverage correctly.

This should be treated as an important false-positive/matching-quality signal.

### not_relevant

The user believes the detected behavior does not require coverage or is not relevant to their testing strategy.

### suppressed

The user does not want AgentGuard to continue surfacing this finding.

Suppression does not necessarily mean the finding was incorrect.

---

## 15. Observed Resolution vs Confirmed Product Impact

AgentGuard must distinguish between two different concepts.

### Observed Test Resolution

AgentGuard detects that a new or modified eval now appears to adequately cover a previously open finding.

Example:

```text
Finding AG-123:
payment lookup timeout appears untested

Later scan:
tests/test_payment.py::test_payment_timeout now matches the behavior
```

This may be recorded as:

> Observed resolution

AgentGuard must not assume that the engineer created the test because of AgentGuard.

### User-Confirmed Impact

The user explicitly confirms that an AgentGuard finding caused them to add or modify an eval.

Examples:

- selecting `add_eval`
- accepting a suggested eval
- confirming after resolution that the finding caused the test change

This may be recorded as:

> Confirmed product impact

Observed resolution and confirmed impact must remain separate metrics.

---

## 16. Feedback Metric Definitions

V0 should support calculating the following metrics.

### Valid Gap Rate

Measures whether engineers agree that surfaced gaps are genuine.

Eligible reviewed findings:

- `add_eval`
- `valid_later`
- `already_covered`
- `not_relevant`

Suggested definition:

```text
add_eval + valid_later
----------------------
eligible reviewed findings
```

`suppressed` should not automatically be counted as valid or invalid unless the user also supplies a reason.

### Actionable Gap Rate

Measures whether findings cause engineers to act.

Primary confirmed version:

```text
findings explicitly confirmed as causing an eval change
--------------------------------------------------------
eligible high-confidence findings reviewed
```

A separate observed metric may track:

```text
findings followed by detected eval resolution
---------------------------------------------
eligible findings
```

These two metrics must not be conflated.

### False Positive Rate

Suggested definition:

```text
already_covered + clearly incorrect findings
---------------------------------------------
eligible reviewed findings
```

`not_relevant` should not automatically count as a false positive because the detected behavior may be real even if the user does not consider it worth testing.

### Resolved-by-Test Rate

Measures whether previously open findings later become covered.

```text
open findings later resolved by new/modified eval
-------------------------------------------------
eligible previously open findings
```

The product should preserve enough history to calculate these metrics consistently.

---

## 17. Stable Behavior IDs

Behavior IDs should remain stable across:

- whitespace changes
- formatting changes
- line-number movement
- non-semantic changes around the behavior

Line numbers must not be the primary basis for identity.

Behavior identity should instead use stable semantic or structural attributes where possible, such as:

- normalized behavior type
- symbol identity
- tool/workflow identity
- normalized condition
- normalized expected action/outcome

---

## 18. Rename and Move Limitations

V0 should make a best-effort attempt to preserve stable IDs when code is moved or renamed.

However, V0 does not guarantee identity preservation across:

- file renames
- symbol renames
- function moves between modules
- major workflow restructuring
- substantial prompt rewrites

If AgentGuard cannot confidently determine that a moved or renamed behavior is the same logical behavior, it may:

- create a new behavior ID
- mark the previous finding as no longer observed
- avoid claiming that the previous issue has been resolved

This limitation should be documented.

A later version may support stronger rename/move tracking using repository history.

---

## 19. Stable Finding IDs

Finding IDs should derive from the underlying behavior and finding type rather than:

- line number
- scan timestamp
- arbitrary ordering

A finding should normally retain the same ID across repeated scans when the underlying behavior and coverage concern are materially unchanged.

A materially changed behavior may generate a new finding ID.

---

## 20. Incomplete Scan Handling

AgentGuard must distinguish between:

- a successful complete scan
- a successful but incomplete scan
- a failed scan

A scan may be incomplete because:

- files could not be parsed
- unsupported syntax was encountered
- an extractor failed
- an expected artifact format was unsupported
- part of the repository was inaccessible
- scan limits were reached

When a scan is incomplete:

1. AgentGuard must surface warnings describing what was not analyzed.
2. AgentGuard must not silently treat missing analysis as proof of missing eval coverage.
3. Findings dependent on unavailable evidence should be:
   - withheld, or
   - marked inconclusive/low-confidence.
4. Previously known findings must not automatically be marked resolved merely because the behavior was not observed in an incomplete scan.
5. Historical state should be preserved.
6. Metrics should exclude findings whose status cannot be confidently determined because of scan incompleteness.

The product should prefer:

> Unable to determine coverage because part of the repository could not be analyzed.

over:

> Potentially uncovered

when the required evidence was unavailable.

---

## 21. Explainability Requirements

For every partially covered or potentially uncovered behavior, AgentGuard should show:

- what behavior was detected
- the source artifact
- the relevant file and symbol
- relevant source evidence
- what existing evals were considered
- why those evals were insufficient
- the confidence level
- what additional eval scenario may be useful

AgentGuard should favor evidence over opaque scores.

---

## 22. Confidence

V0 may use qualitative confidence levels:

- high
- medium
- low

Confidence should represent confidence in the finding or match, not a probability that the agent is safe or correct.

Examples:

### High confidence

A deterministic tool failure exists and no discovered eval references or verifies that failure mode.

### Medium confidence

A semantic match suggests neighboring behavior is tested but the exact condition may not be.

### Low confidence

The behavior was inferred from ambiguous natural-language prompt text.

Low-confidence findings should not dominate the default output.

---

## 23. Local Persistence

V0 should store local AgentGuard state under:

```text
.agentguard/
```

Persistence may initially use:

- JSON, or
- SQLite

The persistence layer should support at minimum:

- finding history
- feedback dispositions
- first-seen timestamp
- last-seen timestamp
- open/resolved state
- observed resolution
- user-confirmed impact where available

No hosted backend is required.

---

## 24. CLI Requirements

At minimum, V0 should eventually support:

```bash
agentguard scan <path>
agentguard findings
agentguard feedback <finding-id> <disposition>
```

The exact syntax may evolve during implementation.

Commands should return clear errors for:

- nonexistent paths
- unsupported repositories
- malformed configuration
- malformed JSONL
- incomplete scans

---

## 25. Quality Requirements

The scanner should prioritize precision over recall.

It is better to surface:

> 5 findings that engineers agree are useful

than:

> 50 speculative findings

Every major capability must have automated tests.

Important test cases include:

1. behavior with matching eval
2. behavior with no matching eval
3. partially covered behavior
4. multiple evals matching one behavior
5. one eval covering multiple behaviors
6. suppressed finding
7. finding marked already covered
8. stable ID across whitespace changes
9. stable ID across line movement
10. new eval resolving a prior finding
11. incomplete scan does not falsely resolve findings
12. unsupported file does not crash the scan
13. repository code is never imported or executed during scan
14. JSONL scenario without expected output does not count as verified coverage
15. user-confirmed impact remains separate from observed resolution

---

## 26. V0 Validation Criteria

Before progressing to V1, we want evidence that:

- at least 20 real users or repositories have been evaluated
- at least 70% of reviewed high-confidence findings are considered valid
- at least 30% of eligible high-confidence findings cause an eval to be added or modified
- false-positive rate is below approximately 20–25%
- users perform repeat scans
- there are concrete examples of:

```text
finding
→ engineer agrees it is valid
→ eval added or modified
→ finding later resolved
```

The strongest validation signal is:

> An engineer added or changed an eval because AgentGuard found a gap they did not already know about.

GitHub stars, installs, and downloads are useful secondary metrics but are not sufficient V0 validation.

---

## 27. Out of Scope for V0

Do not build:

- cloud dashboard
- production trace ingestion
- production monitoring
- GitHub Actions integration
- GitHub PR comments
- release gating
- agent certification
- enterprise governance workflows
- policy-management platform
- Jira integration
- Confluence integration
- Slack integration
- SSO
- RBAC
- multi-tenant SaaS backend
- enterprise audit platform
- enterprise agent inventory
- VPC deployment
- numeric behavioral coverage score

Planned progression:

- GitHub Actions / CI integration: V1
- local change-aware coverage: M9; hosted and CI integration remain deferred
- production-informed coverage: V2
- credible coverage intelligence: V2.5
- release assurance: V3
- requirements/policy traceability: V4
- enterprise agent assurance: V5

---

## 28. V0 Product Principles

### Precision over recall

Do not maximize the number of findings.

Maximize the number of findings engineers consider genuinely useful.

### Evidence over scoring

Every important conclusion should have inspectable evidence.

### Static and safe by default

Scanning must not execute untrusted repository code.

### Local first

The core V0 experience should work locally without a hosted backend.

### Developer workflow first

AgentGuard should feel like an engineering tool, not a compliance platform.

### Low setup

Users should receive useful results from artifacts already present in their repository.

### No false assurance

AgentGuard identifies potential missing eval coverage.

It does not certify that an agent is:

- safe
- correct
- compliant
- production-ready
- fully tested

### Product impact must be measurable

AgentGuard should distinguish between:

- finding something
- a user agreeing it is valid
- a test later appearing
- the user confirming AgentGuard caused the test change

Those are different signals and should remain separate.

## Metric and Impact Clarifications

### add_eval

`add_eval` represents user intent to add or modify an eval.

It does not by itself count as confirmed product impact.

### observed_resolution

`observed_resolution` is recorded when a later scan detects that a new or
modified eval now appears to cover the finding.

Observed resolution does not prove AgentGuard caused the change.

### confirmed_impact

`confirmed_impact` requires explicit user confirmation that the AgentGuard
finding caused or materially influenced the eval change.

### Finding Counting

Metrics count unique stable finding IDs, not repeated scan appearances.

### Review Eligibility

A finding is considered reviewed when the user selects:

- add_eval
- valid_later
- already_covered
- not_relevant

Suppression alone is not a reviewed outcome unless a reason is also recorded.

### Confidence Cohort

Metric eligibility uses the finding confidence at the time of first review.

### Reopened Findings

A reopened finding retains its original finding ID and is not counted as a new
finding. Reopen events should be tracked separately.

### Revised Feedback

The latest user disposition is the current state, but all prior feedback events
must remain in history.

### False Positive Signal

`already_covered` is the primary V0 false-positive signal.

`not_relevant` does not automatically count as a false positive.

## Metric Definitions

Metrics are calculated over unique stable `finding_id` values, not scan appearances.

A finding is considered `reviewed` when the latest explicit user disposition is one of:

- `add_eval`
- `valid_later`
- `already_covered`
- `not_relevant`

A `suppressed` finding is excluded from reviewed cohorts unless it also has an explicit review reason.

Findings whose assessment was unavailable because of an incomplete or failed scan are excluded from metric denominators until they become assessable.

Confidence eligibility is determined using the finding confidence at the time of first review.

Reopened findings retain the same finding ID and are not counted as new findings.

### Valid Gap Rate

Measures whether reviewed findings are considered genuine gaps by users.

Numerator:

- `add_eval`
- `valid_later`

Denominator:

- all eligible reviewed findings

Formula:

Valid Gap Rate =
(`add_eval` + `valid_later`) / eligible reviewed findings

### Intent-to-Act Rate

Measures whether users intend to change their eval suite because of a finding.

Numerator:

- findings with current disposition `add_eval`

Denominator:

- eligible reviewed findings

Formula:

Intent-to-Act Rate =
`add_eval` / eligible reviewed findings

`add_eval` represents intent only and must not be interpreted as confirmed product impact.

### Observed Resolution Rate

Measures whether previously open findings later appear to become covered by a new or modified eval.

Numerator:

- eligible findings with `observed_resolution = true`

Denominator:

- eligible previously open findings that have had at least one subsequent complete scan

Formula:

Observed Resolution Rate =
observed resolutions / eligible previously open findings with follow-up scans

Observed resolution does not establish that AgentGuard caused the eval change.

### Confirmed Impact Rate

Measures whether users explicitly confirm that AgentGuard caused or materially influenced an eval addition or modification.

Numerator:

- eligible findings with explicit `confirmed_impact = true`

Denominator:

- eligible reviewed high-confidence findings

Formula:

Confirmed Impact Rate =
confirmed-impact findings / eligible reviewed high-confidence findings

Confirmed impact must require an explicit user confirmation event.

### False Positive Rate

Measures findings where the user indicates that adequate coverage already existed and AgentGuard failed to identify it.

Numerator:

- findings whose current disposition is `already_covered`

Denominator:

- eligible reviewed findings

Formula:

False Positive Rate =
`already_covered` / eligible reviewed findings

`not_relevant` must not automatically count as a false positive.

### Resolved-by-Test Rate

Measures whether open findings later become covered by a new or modified eval.

Numerator:

- findings with observed test resolution

Denominator:

- eligible findings that were previously open and have had at least one subsequent complete scan

Formula:

Resolved-by-Test Rate =
findings resolved by test / eligible previously open findings with follow-up scans

## M8 — Verification Evidence Foundation

Extend the existing eval, match, assessment, and finding models additively;
do not introduce a parallel evidence registry or change stable IDs/fingerprints.

- Evidence categories are `automated_test`, `eval_case`, `runtime_guardrail`,
  `quality_observation`, and `requirement`. Only supported pytest tests and
  JSONL/Pydantic Evals cases are automatically classified in M8. The other
  categories are model-only; no new extraction heuristics are introduced.
- Only supported test/case source-category pairs qualify for matching. A
  requirement, guardrail, observation, or mere artifact presence cannot
  independently establish coverage, test passage, or observed resolution.
- Preserve existing functionality, condition/branch/failure, outcome verification,
  partial coverage, exact tool/wrapper identity, and incomplete-scan safeguards.
  Do not change matching thresholds, selection, or metrics formulas.
- Structured finding explanations retain the normalized behavior, actual source
  references, candidate evidence types and matching dimensions, qualitative
  confidence, reason codes, missing dimensions, and scan limitations. Unknown
  source locations must remain unknown. Absence is scoped to supported evidence,
  never asserted as proof that no tests exist or that tests passed at runtime.
- Missing dimensions describe the closest single supported candidate, with
  deterministic eval-ID tie breaking; evidence from separate candidates is not
  combined to establish sufficient coverage. Unavailable assessments must not
  claim known missing dimensions.
- Stable reason codes include `sufficient_matching_evidence`,
  `no_qualifying_evidence`, `functionality_not_matched`, `condition_not_matched`,
  `expected_outcome_not_matched`, `partial_dimension_match`,
  `unsupported_evidence_pattern`, and `scan_incomplete`. These explain existing
  decisions rather than introducing new inference from unsupported artifacts.
- Preserve existing commands/flags and JSON keys. Enhance `findings` details and
  add excerpt-free structured evidence to the existing metrics JSON export;
  retain its omission of source contents. Full evidence remains local.
- Existing SQLite payloads must load with backward-compatible defaults, without
  state resets or discarded feedback. New scans refresh explanations while
  retaining finding identity, dispositions, and resolution/impact distinctions.

See [Verification evidence](docs/verification-evidence.md) for the field contract,
reason-code meanings, and supported scope. Static inspection does not certify
correctness, guarantee complete coverage, or recognize every eval implementation.

## M9 — Local Change-Aware Eval Coverage

- `skout scan <path> --baseline <local-ref>` independently analyzes a Git commit
  snapshot and the current working tree through the existing discovery,
  extraction, matching, and pure finding-selection functions. Do not analyze
  only changed lines/files or build a second matcher. Without a baseline,
  ordinary scanning retains its existing persistence and output contracts.
- Resolve local branches, tags, and commit IDs once. Identify the actual Git root
  and compare the supplied scan directory at the same relative scope. Include
  supported tracked edits, deletions, and untracked working-tree files.
- Resolve configuration within each snapshot's scan root and apply the same
  CLI exclusions to both. Changed scope configuration makes absence uncertain.
- Snapshot Git blobs without checkout, hooks, filters, code execution, network
  retrieval, or writes to the target repository. Use temporary storage with
  cleanup and explicit size/time limits; reject partial/promisor clones.
- Keep change classification separate from coverage: `added`, `modified`,
  `unchanged`, `removed`, and `identity_uncertain`. Use exact stable IDs, unique
  same-symbol anchors, and unique exact structural moves. Never change existing
  behavior/finding IDs to achieve a comparison match or guess ambiguous renames.
- Compare existing fingerprints, normalized conditions/actions, and arguments.
  Supported branch-threshold edits must be modified, while comments, whitespace,
  and line shifts do not imply modification. Equivalence is limited to extracted
  structure; unmodeled helper/import/runtime semantics must remain an explicit
  limitation rather than a semantic-equivalence claim.
- Independently assess M8 qualifying pytest, JSONL, and Pydantic Evals evidence.
  Retain partial coverage and condition/outcome dimensions. Requirements,
  guardrails, and observations cannot independently establish coverage. Do not
  infer stale or passing tests simply because implementation changed.
- Report `new_gap`, `coverage_regression`, `coverage_improvement`,
  `modified_covered`, `unchanged_gap`, `removed_behavior`, and `uncertain`.
  Additional explicit results are `added_covered`, `unchanged_covered`, and
  `modified_gap`. Compare changed qualifying eval identities/fingerprints too.
- Preserve uncertainty if either snapshot is incomplete, identity is ambiguous,
  or Git/scope limitations prevent a sufficient comparison. Removed behavior
  must never be equated with observed test resolution.
- Provide deterministic human and `--baseline <ref> --json` reports, with IDs,
  source locations, typed evidence, M8 reasons/dimensions, confidence, and limits.
  Omit source excerpts from JSON. Default output prioritizes changed concerns;
  `--all-changes` includes unrelated unchanged behaviors. Counts are of behaviors,
  distinct from actionable finding selection.
- Comparison results are ephemeral. Never create/update `.agentguard/`, saved
  classifications, lifecycle events, metrics, or confirmed impact in this mode.
  Ordinary subsequent scans continue to update the existing lifecycle.
- No new frameworks, dependencies, GitHub integration, CI gates, LLM analysis,
  runtime tracing, test generation, telemetry, or coverage percentages are added.

See [Change-aware coverage](docs/change-aware-coverage.md) for the complete M9
report contract, Git limitations, and validated CLI examples.

## M10.1 — Agent Behavior Discovery Audit

- Provide development-only tooling that reuses repository discovery and behavior
  extraction. Do not create another behavior extractor or public CLI command.
- Define meaningful behaviors as externally observable or explicitly orchestrated
  agent operations, decisions, conditions, transitions, and failure paths. Require
  structural registration/wiring/dispatch evidence; ordinary helpers do not
  automatically qualify. Separate structural correctness from operational value.
- Independently curate source-first expected inventories for the public LangGraph,
  CrewAI, and Pydantic AI examples and architecture-neutral controlled fixtures.
  Include decorated/plain tools, adapter delegation, shared tools, skill dispatch,
  routing, failure/fallback, helpers, multiple entries, dynamic registration, and
  negative controls. Pin sources and record evidence, roles, support status,
  uncertainty, and review status. Do not derive ground truth from scanner output.
- Classify exact, missed, partial, ambiguous, and unexpected discoveries. Parent
  records cannot substitute for missing child contracts. Incomplete/uncertain
  evidence must remain uncertain. Validate source paths, locations, and text.
- Report overall and supported-pattern recall with denominators; reviewed
  structural precision with excluded cases; pattern/architecture results; source
  accuracy; role and operational-relevance distinctions. These are internal
  discovery audit measurements, not public behavioral coverage percentages or new
  `skout metrics` definitions.
- Record gap taxonomy, confirmed observations separately from hypotheses,
  deterministic feasibility, false-positive risk, and downstream implications for
  inventory, matching, selection, M8 explanations, and M9 comparison. A missing
  extraction is not an observed matcher failure or an immediate missing-eval finding.
- Verify equivalent structures under neutral and version/legacy-looking directory
  names without path heuristics, active-code inference, or a legacy-code dependency.
- Treat unavailable current Easentic results solely as unverified qualitative
  feedback. Never inspect/scan the outdated checkout, calibrate against it,
  reconstruct its structures, or claim reproduction of its reported findings.
- Keep the audit read-only for target sources/state. Do not execute/import target
  code, access network services, change feedback/SQLite/lifecycle, or create
  persistent findings. No production extractor, matcher, ID, M8/M9 contract,
  public JSON, metrics, scope filter, release metadata, or CLI behavior changes.
- Deliver deterministic `docs/behavior-discovery-audit.json`, methodology/results
  in `docs/behavior-discovery-audit.md`, and two or three scored, source-backed
  generalized proposals in `docs/m10-2-extraction-plan.md`. Specify AST recognition,
  provenance, exclusions, model/identity/source contracts, risks, regression cases,
  and acceptance criteria without implementing M10.2/M10.3.
- Done means the baseline and full regression suite are recorded, the harness
  correctness tests and determinism/isolation checks pass, all three examples and
  all controlled fixtures are audited, denominators/unknowns are explicit, and
  `pytest`, `ruff check .`, `ruff format --check .`, `mypy src/agentguard`, and
  `git diff --check` pass. Discovery expectations may remain missed/partial;
  do not weaken expectations to make unsupported patterns pass.

## M10.2a — Provenance-backed registration and bound callables

- Add a conservative file-local source index for imports/aliases, declarations,
  assignments, uniqueness, shadowing, rebinding, and explicit mutation. Do not
  import/execute target code or resolve arbitrary cross-module flows.
- Recognize supported framework provenance for literal list/tuple/set tool
  registrations and supported owned tool decorators. Names such as `tool` or
  `tools=` alone never establish verified ownership. Preserve unknown external
  and custom-factory provenance as unknown.
- Keep callable capabilities separate from owner-to-callable relationships.
  Shared callables have one canonical definition and separate owner links.
  Relationships retain versioned stable identity, kind, owner, raw reference,
  optional resolved callable, actual registration and definition evidence,
  framework provenance, status/reason, and structural fingerprint.
- Resolve bound methods only for unique direct local receiver construction,
  unique local classes/methods, and no unsupported inheritance, descriptors,
  rebinding, dynamic attributes, metaclasses, or explicit monkey-patching.
  Ambiguous/unknown targets must not receive invented definition references.
- Add default-empty capability/relationship tuples to the extraction result.
  New relationships are internal inventory facts, not executable behaviors or
  qualifying M8 evidence. Existing coverage, finding, feedback, SQLite, metrics,
  CLI JSON, and M9 delta consumers remain unchanged. Existing IDs/fingerprints
  remain unchanged where the represented behavior is unchanged.
- Bound-method capability discovery does not automatically add behavior
  assessments/findings; retain explicit unsupported assessment warnings.
  Correct generic name-only false promotions only for source-demonstrated
  passive local constructors/identity decorators. Retain generic plain-function
  compatibility for unknown custom factories and document every output change.
- Relationship identity excludes line numbers, whitespace, comments, absolute
  roots, timestamps, and scan order. Material owner/target/registration changes
  change identity; path moves may too. Duplicate equivalent links collapse.
- Preserve M10.1 ground truth. Separately audit behavior recall/precision and
  registration recall/precision, bound-method resolution, shared ownership,
  incorrect promotions, source accuracy, and unknown cases. Pin public-example
  behavior IDs/fingerprints, finding IDs, and assessment compatibility before
  implementation. Retain source-first independent registration expectations.
- Validate alias/qualified imports, shadowing, plain functions, bound methods,
  receiver ambiguity, descriptors/inheritance, custom/external factories, shared
  ownership, duplicate links, source references, formatting/line moves, directory
  independence, old payload defaults, M8/M9, and persisted feedback lifecycle.
- Do not implement M10.2b/M10.2c callbacks/executors, skill dispatch, delegation,
  matching changes, scope heuristics, runtime reachability, network/LLM analysis,
  new finding categories, CLI flags, or release changes. Done requires the full
  pytest suite, Ruff checks/formatting, mypy, audit regeneration/determinism, and
  `git diff --check`, with explicit compatibility and limitation reporting.

## M10.2b — Explicit orchestration callbacks and executors

- Extend M10.2a's source index, canonical capabilities, relationship model and
  inventory tuple; do not create another relationship system or behavior engine.
- Add distinct `graph_node_callback`, `task_agent_executor`, and
  `output_validator_callback` kinds, with additive defaulted registered/executor
  identities and limitations. Retain framework, owner, resolved target, actual
  registration/definition references, status/reason, stable ID and fingerprint.
- Resolve direct module-level LangGraph `StateGraph` owners and literal
  `add_node("name", local_function)` callbacks, including async functions. Keep
  owner/node associations distinct; share canonical callbacks; retain conflicts
  and dynamic/unresolved targets as uncertain without guessing graph execution.
- Resolve explicit CrewAI `Task(..., agent=known_local_agent)` assignments through
  known framework imports/aliases. Context, ordering, crew membership, and process
  do not imply executors. Several tasks can reference one unique agent identity.
- Resolve bare Pydantic AI `@agent.output_validator` registrations for uniquely
  bound local sync/async functions and known agent receivers. Preserve existing
  validator conditions, ModelRetry outcomes, and failure behavior separately.
- Require source provenance and uniqueness. Do not infer known framework owners
  from method names, filenames, annotations, unknown factories, or arbitrary
  aliases. Rebinding, mutation, dynamic identifiers, imported callbacks, ambiguous
  definitions, and unsupported decorators must not gain confident resolution.
- Relationship identities exclude physical lines, comments, whitespace, absolute
  paths, scan order, and timestamps. Owner, literal node, and callback/executor
  changes are material; shared targets retain distinct registration links. Path
  moves/renames may change identity; existing behavior/tool IDs remain unchanged.
- Relationships remain structural inventory facts only. Do not infer execution,
  reachability, deployment, eval exercise, covered/uncovered status, or new
  high-confidence findings. Keep behavior categories, matching thresholds, M8
  evidence, M9 deltas, SQLite/feedback/lifecycle, metrics, CLI and public JSON intact.
- Preserve existing independent audit ground truth and public-example results.
  Separately audit new orchestration relationships, framework-level recall,
  reviewed precision, source accuracy, unknown cases, and incorrect ownership.
  Capture pre-implementation tool relationship and public behavior/assessment/
  finding/M9 comparison baselines. Do not count relationships as executable
  behavioral recall or combine denominators into coverage percentages.
- Add deterministic source-first controlled fixtures for shared/multiple owners,
  async callbacks, import aliases, graph transitions, task context/order, retries,
  dynamic/imported/ambiguous targets, negative APIs, source/identity stability,
  directory independence, old payload defaults, and read-only isolation.
- Done requires full pytest, Ruff lint/format, production and audit-tooling mypy,
  `git diff --check`, all three deterministic audit reports, unchanged M10.2a
  scores and pre/post compatibility, documentation, and explicit limitations.
  No target execution, network, state reset, M10.2c dispatch/delegation, broad
  call graphs, active-code heuristics, guardrail analysis, or release actions.

## M10.2c — Bounded literal dispatch and one-hop delegation

- Extend the existing canonical capabilities, source index, relationship tuple
  and defaulted model with `literal_dispatch`, `one_hop_delegation`, and
  `exception_fallback`. Keep real call sites separate from parent registration
  provenance, target definitions, registry evidence, handler/guard evidence,
  resolution status, limitations and contextual `orchestrated_internal` role.
- Freeze eligible parents before extraction: unique resolved tool registrations,
  orchestration callbacks, or existing supported framework tool declarations.
  A known imported tool decorator establishes a declared tool interface without
  proving deployment or validating an unknown custom owner. Unknown factories,
  helper names, `tools`, `execute`, directory/version/legacy names never suffice.
- Resolve only module-local unique literal string-to-local-function dictionaries
  used directly as `REGISTRY[key](...)`. Preserve each possible key/target edge;
  shared targets have one canonical callable. Reject computed entries, mutation,
  reassignment, aliases, escapes, reflection and imported implementations.
- Reuse M10.2a's local-instance resolver for direct method delegation; support
  unique local function calls and direct awaited calls. Respect local shadows,
  rebinding, inherited/dynamic methods, descriptors and ambiguous receivers.
  Never recursively follow newly discovered children or create call graphs.
- Preserve explicit exception-handler conditions on direct fallback calls.
  Recognize unshadowed allowlisted builtin exceptions/tuples and explicit builtin
  import aliases. Bare, generic, dynamic, nested or unresolved cases remain
  uncertain; never infer primary failure, handler execution, recovery, or outcome.
- Retain direct if/else and single-try structural context. Unsupported control
  forms must not gain confident target relationships. No silent count truncation
  is added; existing scanner resource limits/completeness remain in force.
- Identity/fingerprint uses parent, kind, relative path, key/handler, canonical
  target and normalized call/context AST. Exclude lines, whitespace, comments,
  traversal order, temporary roots and time. Preserve distinct parents/contexts
  and keys; deduplicate exact structural repeats. Preserve all historical IDs.
- Child condition/failure composition is deferred where propagation/guard
  semantics would require guessing. No new Behavior or eval findings arise from
  these links. M8 evidence/matching, M9 coverage deltas, findings/lifecycle,
  SQLite/feedback/metrics, public CLI/JSON and version remain unchanged.
- Keep original ground truth immutable. Separately measure new source-pinned
  relationships, precision, resolution outcomes, references, uncertainty and
  incorrect promotions. Do not combine relationship and behavior denominators.
- Require registry/method/fallback positive/negative controls, frozen depth,
  identity/source accuracy, read-only isolation, full pre-change compatibility,
  public-example M9 checks, all four audit reports and byte determinism, full
  pytest, Ruff lint/format, production/audit mypy, and `git diff --check`.
  See `docs/delegation-relationships.md` for exact syntax and limitations.

## M10.2d — Verification obligation mapping (development only)

- Distinguish structural source relationships, concrete testable verification
  obligations, and qualifying M8 verification evidence. Eligibility is not
  covered/uncovered status, runtime execution, finding confidence or usefulness.
- Keep typed prototype models and deterministic mapping under development audit
  tooling. Consume existing extracted behaviors, capabilities, relationships,
  conditions/actions and source references only; no parallel AST/body scanner.
- Distinguish eligible, context-only, insufficient-evidence, unsupported and
  ambiguous decisions, with reason codes, source proofs, uncertainty, required
  functionality/condition/outcome, existing behavior correspondence and matcher
  compatibility. Context/abstentions cannot create obligation IDs.
- Registration, node callbacks, task assignments and delegation alone stay
  context-only. Existing guarded rejections may be enriched through resolved
  registration provenance. Never infer child propagation, callback state output,
  task results, handler success or production relevance from wiring or names.
- Resolved literal key-to-target selection and explicit handler-to-fallback
  invocation may be audit-eligible conditional claims while requiring new matcher
  contracts. Retain all extracted guards; do not synthesize production Behaviors
  or use generic invocation coverage to assess these relationships.
- Consolidate equivalent existing branch/failure concerns and shared-owner
  provenance. Preserve existing behavior identities, retain all origin links,
  keep distinct literal keys/contexts, and measure raw duplicate mappings and
  residual duplication separately. New audit identities remain unpersisted.
- Maintain independently curated source-pinned positive/negative decisions for
  all M10.2a–c kinds and public examples, explicit review status, reason, source
  anchors, expected dimensions and uncertainty. Original audit ground truth is
  immutable; report unreviewed extractions separately. Do not use Easentic.
- Test actual unmodified M8 with exact existing Behavior/EvalScenario objects:
  verified versus unverified calls, wrong condition/callable, helper-only,
  similar-name and adjacent-route controls, including supported evidence source
  categories. Report matcher disagreements and unassessable new contracts;
  requirements/guardrails/quality observations cannot establish coverage.
- Report explicit counts for eligibility precision/recall, per-kind decisions,
  duplicate mappings, source traceability, abstention and a testability/actionability
  proxy. Do not equate the proxy with engineer intent, combine structural and
  obligation denominators, or claim production-wide accuracy/coverage scores.
- Deliver `docs/verification-obligation-mapping.md`, a deterministic structured
  report, the independent inventory and
  `docs/verification-obligation-integration-plan.md`. Specify recognition, model,
  evidence, deduplication, identity, finding confidence and M8/M9/lifecycle
  requirements for future integration without implementing them.
- No production behavior, matcher, finding threshold/category, persistence/schema,
  feedback, lifecycle, metrics, M9 comparison, CLI/JSON, package name or version
  changes. No target execution, network, LLM, state deletion or release actions.
- Done requires the full pytest suite, Ruff lint/format, production/audit mypy,
  `git diff --check`, byte-identical regeneration of all four prior audits plus
  the obligation report, source/identity and M8/M9 compatibility snapshots,
  read-only/no-state isolation, and an actual before/after validation report.
