# Local change-aware eval coverage (M9)

Compare all supported behavior and eval evidence at a local Git revision with
all supported evidence in your current working tree:

```bash
skout scan . --baseline main
skout scan . --baseline HEAD
skout scan . --baseline HEAD~1 --json
skout scan . --baseline main --all-changes
```

Git must be installed and the baseline commit's objects must be available locally.
Branches, tags, and commit hashes are accepted. The revision is resolved once and
its full commit ID is included in the report. Skout does not fetch, pull, switch
branches, create commits, or execute repository hooks or filters.

Without `--baseline`, ordinary scanning, finding persistence, feedback, metrics,
and observed resolution retain their existing behavior. `--json` and
`--all-changes` on `scan` require a baseline; other commands' JSON flags are
unchanged.

## Two complete analysis inventories

The baseline is built from raw Git blobs in a temporary directory. The current
side reads the actual working tree, including tracked edits, staged edits as
represented on disk, deletions, and supported untracked files. It does not read
only `HEAD`, only the index, changed files, or diff lines. Git-ignored files remain
subject to Skout's existing include/exclude configuration, just as in ordinary
scans; Git ignore rules do not replace Skout scope rules.

Both sides call existing discovery, behavior extraction, eval extraction,
matching, and pure finding selection. Tests elsewhere in the repository are
therefore considered even when the agent source file did not change. No
alternative matcher, threshold, or framework extraction is introduced.

Scanning a subdirectory compares the same path beneath the actual Git root at
the baseline. Source references remain relative to the supplied scan directory.
If that directory did not exist at the baseline, its baseline inventory is empty.
Configuration is resolved separately from each snapshot's scan directory, as for
ordinary scans. The same `--exclude` arguments apply to both. A changed effective
include/exclude scope makes absence uncertain rather than a confirmed removal
or regression. Configurations outside the supplied directory are not inherited.

## Behavior identity and supported changes

1. Match existing stable behavior IDs exactly.
2. For remaining behaviors, pair only unique same-file, same-source-type,
   same-symbol/subject, same-behavior-type anchors. This handles supported
   condition/action edits that intentionally produce different stable IDs.
3. Recognize a move only with a unique matching symbol/subject, type, and exact
   extracted structural fingerprint, condition, action, and arguments across
   files. Both original IDs are retained in the comparison record.
4. Otherwise, compatible unmatched kinds on both sides remain separate
   `identity_uncertain` records. Do not invent a pairing for a rename, duplicate,
   or simultaneous removal/addition. This intentionally favors uncertainty.

`modified` means extractor-visible verification structure changed. For example,
a supported tool's `amount > 500` guard changed to `amount > 250` is modified,
even when its failure action and function name remain unchanged. Comments,
formatting, and line movement do not change normalized AST fingerprints.

`unchanged` means equivalent **under the supported extracted representation**.
It is not a claim of semantic equivalence. Changes in unmodeled helpers, imports,
dynamic calls, natural-language instructions, or a LangGraph routing function's
body may not be reflected in extracted behavior fingerprints. Existing LangGraph
edge/route declarations, CrewAI constructs, and Pydantic AI tool/validator
patterns retain their current scope. The report always states this static limit.

Stable persisted behavior/finding ID generation is not changed for M9.
Comparison anchors do not create a rename-tracking guarantee for ordinary scans.

## Verification deltas

Coverage is computed independently in each inventory using M8's qualifying
pytest (`automated_test`) and JSONL/Pydantic Evals (`eval_case`) evidence.
Functionality, condition/branch/failure, and expected-outcome dimensions remain
separate. A requirement, guardrail, observation, dataset presence, or unsupported
artifact cannot independently establish coverage.

| Delta | Meaning |
| --- | --- |
| `new_gap` | Added behavior has insufficient supported evidence, including partial coverage |
| `added_covered` | Added behavior already has sufficient evidence |
| `coverage_regression` | Previously covered behavior now has partial or potentially missing coverage |
| `coverage_improvement` | Previously partial/potentially uncovered behavior is now covered |
| `modified_covered` | Modified behavior retains sufficient evidence |
| `modified_gap` | Modified behavior still has insufficient evidence, without a prior covered state |
| `unchanged_gap` | Extractor-equivalent behavior still lacks sufficient evidence |
| `unchanged_covered` | Extractor-equivalent behavior retains sufficient evidence |
| `removed_behavior` | Behavior is absent under a sufficiently complete comparison |
| `uncertain` | Identity, scan completeness, scope, or unsupported Git structures limit comparison |

Regression/improvement takes precedence over a modified classification when
coverage crosses the sufficient-evidence boundary. Mere removal of a behavior
is never observed test resolution. A modified implementation does not by itself
make its old eval stale: an unchanged eval may still satisfy supported matching
dimensions, and static analysis cannot tell whether that eval will pass.

Qualifying eval changes are listed separately using existing eval IDs and
fingerprints: added, removed, or modified pytest, JSONL, and Pydantic Evals cases.
An eval rename/move may appear as removal plus addition; coverage is still
recomputed from the full inventories rather than inferred from that label.

## Reports and uncertainty

The human report prioritizes new gaps, regressions, modified gaps, improvements,
and uncertain comparisons. Existing finding-selection IDs prioritize actionable
concerns within those groups. Summary counts describe **behaviors**, not unique
persisted actionable findings; related behaviors can share a testing concern.
Unrelated unchanged behaviors are hidden by default, with existing gap counts
retained. Use `--all-changes` to inspect every behavior, including covered additions
and removals. JSON always includes the complete comparison.

The JSON report contains:

- `repository`, `baseline` (requested ref, resolved commit, Git root, scoped path),
  and `current_source: "working_tree"`.
- `baseline_inventory` / `current_inventory`: completeness and behavior, eval,
  candidate-pair, and selected-finding counts.
- `summary`: added/modified/removed/unchanged/identity-uncertain behavior counts;
  new gaps, regressions, improvements, modified/added covered counts, existing
  gaps, and uncertain comparisons.
- `changes`: behavior change and verification delta, baseline/current existing
  `Behavior` and M8 assessment models, actual source locations, evidence types,
  match dimensions, reason codes, missing dimensions, confidence, and limitations.
  `current_finding_id` is populated only when existing pure finding selection
  selects the current behavior. It does not imply a persisted finding.
- `eval_changes`: changed qualifying scenario IDs, types, sources, and change labels.
- `limitations`: snapshot issues and the scope of static comparison.

Source excerpts are omitted from CLI JSON throughout. Source paths, line numbers,
conditions, and expected actions remain available. Ordering is deterministic;
there are no scan timestamps or temporary baseline directory names in the report.
Ambiguous correspondences are not collapsed into guessed pairs, so an uncertain
rename can produce separate baseline-only and current-only records.

If either inventory is incomplete, or comparison scope/Git limitations affect
analysis, deltas are conservatively `uncertain`; no regression, improvement, or
new-gap claim is made. Available snapshot coverage facts remain visible with
limitations. This M9 policy is more conservative than ordinary per-behavior
assessment; it does not change ordinary coverage semantics. Invalid paths,
non-Git/bare repositories, unavailable revisions, and unsupported partial clones
return clear nonzero errors. A failed discovery/configuration also returns a
nonzero status with its structured uncertainty report; incomplete comparisons
can return successfully with explicit uncertainty.

## Persistence and Git limitations

Comparison never calls finding lifecycle updates or writes SQLite. It neither
creates `.agentguard/` nor revises existing feedback, resolution history, metrics,
or confirmed impact. Use a subsequent ordinary scan to update persisted findings:

```bash
skout scan .
skout review
```

Baseline temporary directories are cleaned up on success or error. Symbolic links
are not recreated or followed. In-scope Git submodules, nested repositories,
unmerged index entries, or skipped unsupported Git entries limit comparison.
Partial/promisor clones are rejected to avoid implicit network retrieval.

Baseline materialization is bounded to 32 MiB per file and 256 MiB total;
exceeding a limit marks the baseline incomplete. Default/configured exclusions
are applied before these limits. Binary/unsupported files are never interpreted
as tests; if a large in-scope blob prevents snapshot materialization, the limit
is explicit. Git operations have a 60-second timeout. Current working-tree reads
are live rather than an atomic filesystem snapshot; avoid editing during a scan.

Skout does not execute tests or agent code, infer arbitrary semantics, guarantee
complete coverage, certify correctness, upload sources, or introduce CI gates.

## Validated examples

Temporary Git copies of all three public examples were checked with their
supplied solution evals. Enabling the solution produces coverage improvement;
adding a supported tool without a matching eval produces a new gap. Published
example source files are unchanged.

Separate temporary CLI fixtures produced these actual output excerpts:

```text
new_gap: lookup
  Change: added; confidence: high
  Coverage: not present → potentially_uncovered

added_covered: lookup
  Change: added; confidence: high
  Coverage: not present → covered

coverage_regression: lookup
  Change: unchanged; confidence: high
  Coverage: covered → potentially_uncovered

coverage_improvement: lookup
  Change: unchanged; confidence: high
  Coverage: potentially_uncovered → covered

uncertain: renamed_lookup
  Change: identity_uncertain; confidence: low
```

These were run with `skout scan <temporary-repository> --baseline HEAD
--all-changes`; accompanying JSON reports were checked against the expected
deltas. They demonstrate static evidence transitions, not test execution results.
