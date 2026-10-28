"""Ephemeral comparison of two full inventories from the existing scanner pipeline."""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.findings.selection import select_findings
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorChange,
    BehaviorChangeStatus,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorSourceType,
    BehaviorType,
    ComparisonBaseline,
    ConfidenceLevel,
    CoverageStatus,
    EvalEvidenceChange,
    EvalParseResult,
    MatchingResult,
    ScanCompleteness,
    ScanResult,
    ScanWarning,
    SnapshotInventorySummary,
    VerificationDelta,
    VerificationDeltaReport,
)
from agentguard.scanners import scan_repository
from agentguard.scanners.git_snapshot import (
    baseline_snapshot,
    current_git_limitations,
    resolve_git_context,
)

STATIC_LIMITATION = (
    "Static comparison covers extracted structure only, not arbitrary semantics, "
    "helper/import changes, or whether tests will pass. Target code is never executed."
)


@dataclass(frozen=True)
class VerificationInventory:
    discovery: ScanResult
    behaviors: BehaviorExtractionResult
    evals: EvalParseResult
    matching: MatchingResult
    finding_ids: dict[str, str]

    @property
    def completeness(self) -> ScanCompleteness:
        statuses = {
            self.discovery.completeness,
            self.behaviors.completeness,
            self.evals.completeness,
            self.matching.completeness,
        }
        return (
            ScanCompleteness.FAILED
            if ScanCompleteness.FAILED in statuses
            else ScanCompleteness.INCOMPLETE
            if ScanCompleteness.INCOMPLETE in statuses
            else ScanCompleteness.COMPLETE
        )

    def summary(self) -> SnapshotInventorySummary:
        return SnapshotInventorySummary(
            completeness=self.completeness,
            behavior_count=len(self.behaviors.behaviors),
            eval_count=len(self.evals.scenarios),
            candidate_pair_count=self.matching.candidate_pair_count,
            selected_finding_count=len(self.finding_ids),
        )

    def limitations(self, side: str) -> tuple[str, ...]:
        messages = {
            f"{side}: {item.code} "
            f"({getattr(item, 'source_file', None) or getattr(item, 'path', None) or 'repository'})"
            for result in (self.discovery, self.behaviors, self.evals, self.matching)
            for item in (*result.warnings, *result.errors)
        }
        return tuple(sorted(messages))


def analyze_snapshot(
    root: Path, excludes: Sequence[str] = (), *, limitations: Sequence[str] = ()
) -> VerificationInventory:
    """Run existing analysis and pure finding selection; never invoke persistence."""
    discovery = scan_repository(root, extra_excludes=excludes)
    if limitations and discovery.completeness is not ScanCompleteness.FAILED:
        discovery = discovery.model_copy(
            update={
                "completeness": ScanCompleteness.INCOMPLETE,
                "warnings": (
                    *discovery.warnings,
                    *(
                        ScanWarning(code="git_snapshot_incomplete", message=message)
                        for message in limitations
                    ),
                ),
            }
        )
    behaviors = extract_behaviors(discovery)
    evals = parse_eval_artifacts(
        discovery,
        known_tool_names={
            b.subject
            for b in behaviors.behaviors
            if (b.behavior_type is BehaviorType.TOOL_INVOCATION)
        },
        known_agent_names={
            b.subject
            for b in behaviors.behaviors
            if (b.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT)
        },
    )
    matching = match_behaviors_to_evals(behaviors, evals)
    findings = select_findings(behaviors, matching)
    return VerificationInventory(
        discovery,
        behaviors,
        evals,
        matching,
        {finding.behavior_id: finding.finding_id for finding in findings.findings},
    )


def _structure(behavior: Behavior) -> str:
    """Keep persisted IDs untouched; compare extractor-visible structure separately."""
    return json.dumps(
        {
            "fingerprint": behavior.content_fingerprint,
            "condition": behavior.condition.normalized_expression if behavior.condition else None,
            "action": behavior.action.model_dump() if behavior.action else None,
            "arguments": [argument.model_dump() for argument in behavior.arguments],
        },
        sort_keys=True,
    )


def _anchor(behavior: Behavior) -> tuple[str, ...]:
    return (
        behavior.source_file,
        behavior.source_type,
        behavior.source_symbol or "",
        behavior.subject,
        behavior.behavior_type,
    )


def _move_key(behavior: Behavior) -> tuple[str, ...]:
    return (*_anchor(behavior)[1:], _structure(behavior))


def _pair_behaviors(
    baseline: tuple[Behavior, ...],
    current: tuple[Behavior, ...],
) -> list[tuple[Behavior | None, Behavior | None, BehaviorChangeStatus]]:
    old = {b.behavior_id: b for b in baseline}
    new = {b.behavior_id: b for b in current}
    pairs: list[tuple[Behavior | None, Behavior | None, BehaviorChangeStatus]] = []

    def pair(old_id: str, new_id: str) -> None:
        before, after = old.pop(old_id), new.pop(new_id)
        status = (
            BehaviorChangeStatus.UNCHANGED
            if _structure(before) == _structure(after)
            else BehaviorChangeStatus.MODIFIED
        )
        pairs.append((before, after, status))

    for identity in sorted(old.keys() & new.keys()):
        pair(identity, identity)
    # Unique anchors allow supported condition/outcome edits whose stable IDs
    # intentionally change. Multiple branches sharing an anchor are not guessed.
    for key_function in (_anchor, _move_key):
        old_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
        new_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for identity, behavior in old.items():
            old_groups[key_function(behavior)].append(identity)
        for identity, behavior in new.items():
            new_groups[key_function(behavior)].append(identity)
        for key in sorted(old_groups.keys() & new_groups.keys()):
            if len(old_groups[key]) == len(new_groups[key]) == 1:
                pair(old_groups[key][0], new_groups[key][0])

    # A removed and added compatible kind may be a rename/move/rewrite. Report
    # each separately as uncertain, without inventing a cross-snapshot pairing.
    old_kinds = {(b.source_type, b.behavior_type) for b in old.values()}
    new_kinds = {(b.source_type, b.behavior_type) for b in new.values()}
    for before in sorted(old.values(), key=lambda b: b.behavior_id):
        status = (
            BehaviorChangeStatus.IDENTITY_UNCERTAIN
            if (before.source_type, before.behavior_type) in new_kinds
            else BehaviorChangeStatus.REMOVED
        )
        pairs.append((before, None, status))
    for after in sorted(new.values(), key=lambda b: b.behavior_id):
        status = (
            BehaviorChangeStatus.IDENTITY_UNCERTAIN
            if (after.source_type, after.behavior_type) in old_kinds
            else BehaviorChangeStatus.ADDED
        )
        pairs.append((None, after, status))
    return pairs


def _delta(
    status: BehaviorChangeStatus,
    before: BehaviorCoverageAssessment | None,
    after: BehaviorCoverageAssessment | None,
    complete: bool,
) -> VerificationDelta:
    if (
        not complete
        or status is BehaviorChangeStatus.IDENTITY_UNCERTAIN
        or any(a.availability is AssessmentAvailability.UNAVAILABLE for a in (before, after) if a)
    ):
        return VerificationDelta.UNCERTAIN
    if status is BehaviorChangeStatus.REMOVED:
        return VerificationDelta.REMOVED_BEHAVIOR
    covered = after is not None and after.coverage_status is CoverageStatus.COVERED
    was_covered = before is not None and before.coverage_status is CoverageStatus.COVERED
    if status is BehaviorChangeStatus.ADDED:
        return VerificationDelta.ADDED_COVERED if covered else VerificationDelta.NEW_GAP
    if was_covered and not covered:
        return VerificationDelta.COVERAGE_REGRESSION
    if covered and not was_covered:
        return VerificationDelta.COVERAGE_IMPROVEMENT
    if status is BehaviorChangeStatus.MODIFIED:
        return VerificationDelta.MODIFIED_COVERED if covered else VerificationDelta.MODIFIED_GAP
    return VerificationDelta.UNCHANGED_COVERED if covered else VerificationDelta.UNCHANGED_GAP


def _eval_changes(
    before: EvalParseResult, after: EvalParseResult
) -> tuple[EvalEvidenceChange, ...]:
    old = {s.eval_id: s for s in before.scenarios if s.qualifies_for_matching}
    new = {s.eval_id: s for s in after.scenarios if s.qualifies_for_matching}
    result: list[EvalEvidenceChange] = []
    for identity in sorted(old.keys() | new.keys()):
        if identity not in old:
            status = BehaviorChangeStatus.ADDED
        elif identity not in new:
            status = BehaviorChangeStatus.REMOVED
        elif old[identity].content_fingerprint != new[identity].content_fingerprint:
            status = BehaviorChangeStatus.MODIFIED
        else:
            continue
        scenario = new.get(identity) or old[identity]
        result.append(
            EvalEvidenceChange(
                eval_id=identity,
                evidence_type=scenario.evidence_type,
                source_type=scenario.source_type,
                source_file=scenario.source_file,
                source_symbol=scenario.source_symbol,
                change_status=status,
            )
        )
    return tuple(result)


def compare_inventories(
    before: VerificationInventory,
    after: VerificationInventory,
    *,
    baseline: ComparisonBaseline,
    repository: str,
    limitations: Sequence[str] = (),
) -> VerificationDeltaReport:
    """Compare independent coverage decisions, never infer stale tests from code changes."""
    limits = (
        set(limitations) | set(before.limitations("baseline")) | set(after.limitations("current"))
    )
    for skipped in after.discovery.skipped:
        if skipped.path.endswith("/.git"):
            limits.add(f"Nested Git repository is unsupported in comparison scope: {skipped.path}")
    if set(before.discovery.repository.include_patterns) != set(
        after.discovery.repository.include_patterns
    ) or set(before.discovery.repository.exclude_patterns) != set(
        after.discovery.repository.exclude_patterns
    ):
        limits.add(
            "Scan scope configuration differs across snapshots; absence may reflect exclusions."
        )
    complete = (
        before.completeness is ScanCompleteness.COMPLETE
        and after.completeness is ScanCompleteness.COMPLETE
        and not limits
    )
    old_assessments = {a.behavior_id: a for a in before.matching.assessments}
    new_assessments = {a.behavior_id: a for a in after.matching.assessments}
    changes: list[BehaviorChange] = []
    for old, new, status in _pair_behaviors(before.behaviors.behaviors, after.behaviors.behaviors):
        old_assessment = old_assessments.get(old.behavior_id) if old else None
        new_assessment = new_assessments.get(new.behavior_id) if new else None
        if not complete and status in {BehaviorChangeStatus.ADDED, BehaviorChangeStatus.REMOVED}:
            status = BehaviorChangeStatus.IDENTITY_UNCERTAIN
        delta = _delta(status, old_assessment, new_assessment, complete)
        local_limits: tuple[str, ...] = ()
        if status is BehaviorChangeStatus.IDENTITY_UNCERTAIN:
            local_limits = ("No unique supported cross-snapshot identity was established.",)
        if delta is VerificationDelta.UNCERTAIN:
            local_limits += (
                "Insufficient comparison evidence; no regression or improvement asserted.",
            )
        changes.append(
            BehaviorChange(
                change_status=status,
                verification_delta=delta,
                baseline_behavior=old,
                current_behavior=new,
                baseline_assessment=old_assessment,
                current_assessment=new_assessment,
                current_finding_id=after.finding_ids.get(new.behavior_id) if new else None,
                confidence=(
                    ConfidenceLevel.LOW
                    if delta is VerificationDelta.UNCERTAIN
                    else min(
                        (a.confidence for a in (old_assessment, new_assessment) if a),
                        key=lambda c: {
                            ConfidenceLevel.LOW: 0,
                            ConfidenceLevel.MEDIUM: 1,
                            ConfidenceLevel.HIGH: 2,
                        }[c],
                        default=ConfidenceLevel.HIGH,
                    )
                ),
                limitations=local_limits,
            )
        )
    changes.sort(
        key=lambda c: (
            (c.current_behavior or c.baseline_behavior).source_file,  # type: ignore[union-attr]
            (c.current_behavior or c.baseline_behavior).behavior_id,  # type: ignore[union-attr]
            c.change_status,
        )
    )
    counts = Counter(c.verification_delta.value for c in changes)
    statuses = Counter(c.change_status.value for c in changes)
    summary = {
        f"{status.value}_behaviors": statuses[status.value] for status in BehaviorChangeStatus
    }
    summary.update(
        {
            "new_gaps": counts[VerificationDelta.NEW_GAP],
            "coverage_regressions": counts[VerificationDelta.COVERAGE_REGRESSION],
            "coverage_improvements": counts[VerificationDelta.COVERAGE_IMPROVEMENT],
            "uncertain_comparisons": counts[VerificationDelta.UNCERTAIN],
            "added_covered": counts[VerificationDelta.ADDED_COVERED],
            "modified_covered": counts[VerificationDelta.MODIFIED_COVERED],
            "modified_gaps": counts[VerificationDelta.MODIFIED_GAP],
            "unchanged_gaps": counts[VerificationDelta.UNCHANGED_GAP],
            "unchanged_covered": counts[VerificationDelta.UNCHANGED_COVERED],
        }
    )
    return VerificationDeltaReport(
        repository=repository,
        baseline=baseline,
        baseline_inventory=before.summary(),
        current_inventory=after.summary(),
        changes=tuple(changes),
        eval_changes=_eval_changes(before.evals, after.evals),
        summary=summary,
        limitations=(*sorted(limits), STATIC_LIMITATION),
    )


def compare_repository(
    repository: Path,
    revision: str,
    *,
    extra_excludes: Sequence[str] = (),
) -> VerificationDeltaReport:
    context = resolve_git_context(repository, revision)
    current_limits = current_git_limitations(context, extra_excludes)
    with baseline_snapshot(context, extra_excludes) as snapshot:
        before = analyze_snapshot(snapshot.root, extra_excludes, limitations=snapshot.limitations)
        after = analyze_snapshot(context.current, extra_excludes, limitations=current_limits)
        report = compare_inventories(
            before,
            after,
            baseline=ComparisonBaseline(
                requested_ref=revision,
                resolved_commit=context.commit,
                repository_root=str(context.root),
                scan_path=context.scope or ".",
            ),
            repository=str(context.current),
            limitations=(*snapshot.limitations, *current_limits),
        )
        # Errors can mention disposable absolute paths. Do not leak them or make
        # repeated comparisons nondeterministic.
        temporary_path = json.dumps(str(snapshot.root), ensure_ascii=False)[1:-1]
        serialized = report.model_dump_json().replace(temporary_path, "[baseline]")
        return VerificationDeltaReport.model_validate_json(serialized)


def comparison_json(report: VerificationDeltaReport) -> JsonValue:
    """Keep M8 models/source locations, excluding source-code excerpts throughout."""

    def clean(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key != "excerpt"}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(cast(JsonValue, report.model_dump(mode="json")))
