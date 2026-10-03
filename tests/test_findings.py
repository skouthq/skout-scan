"""Tests for finding selection, persistence, feedback, and lifecycle."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentguard.feedback import FindingStore
from agentguard.findings import select_findings, update_findings
from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorAction,
    BehaviorCondition,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorSourceType,
    BehaviorType,
    ConfidenceLevel,
    CoverageStatus,
    FindingDisposition,
    FindingHistoryEventType,
    FindingStatus,
    MatchingResult,
    ScanCompleteness,
    SourceEvidence,
)

FIRST_SCAN = datetime(2026, 1, 1, tzinfo=UTC)
SECOND_SCAN = FIRST_SCAN + timedelta(days=1)


def _behavior(
    *,
    behavior_id: str = "behavior_failure",
    behavior_type: BehaviorType = BehaviorType.TOOL_FAILURE,
) -> Behavior:
    return Behavior(
        behavior_id=behavior_id,
        description="lookup may fail when the provider times out",
        behavior_type=behavior_type,
        source_type=BehaviorSourceType.PYTHON_TOOL,
        source_file="agent.py",
        source_symbol="lookup",
        subject="lookup",
        condition=BehaviorCondition(
            expression="provider == 'timeout'",
            normalized_expression="(provider == 'timeout')",
        ),
        action=BehaviorAction(kind="raise", outcome="TimeoutError"),
        evidence=(
            SourceEvidence(
                kind="raise",
                source_file="agent.py",
                source_symbol="lookup",
                start_line=4,
                end_line=4,
                excerpt="raise TimeoutError()",
            ),
        ),
        confidence=ConfidenceLevel.HIGH,
        extractor="test",
        content_fingerprint="fingerprint",
    )


def _assessment(
    behavior: Behavior,
    *,
    status: CoverageStatus = CoverageStatus.POTENTIALLY_UNCOVERED,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    availability: AssessmentAvailability = AssessmentAvailability.AVAILABLE,
    matched_eval_ids: tuple[str, ...] = (),
) -> BehaviorCoverageAssessment:
    return BehaviorCoverageAssessment(
        behavior_id=behavior.behavior_id,
        availability=availability,
        coverage_status=status if availability is AssessmentAvailability.AVAILABLE else None,
        confidence=confidence,
        matched_eval_ids=matched_eval_ids,
        explanation="No eval verifies the timeout failure.",
        candidate_count=len(matched_eval_ids),
        matcher="test-matcher",
    )


def _results(
    behavior: Behavior,
    assessment: BehaviorCoverageAssessment,
    *,
    completeness: ScanCompleteness = ScanCompleteness.COMPLETE,
) -> tuple[BehaviorExtractionResult, MatchingResult]:
    return (
        BehaviorExtractionResult(behaviors=(behavior,), completeness=completeness),
        MatchingResult(
            assessments=(assessment,),
            completeness=completeness,
            behavior_count=1,
            eval_count=0,
            matcher="test-matcher",
        ),
    )


def _create_finding(root: Path) -> tuple[FindingStore, str]:
    behavior = _behavior()
    behavior_result, matching_result = _results(behavior, _assessment(behavior))
    update = update_findings(
        root,
        behavior_result,
        matching_result,
        observed_at=FIRST_SCAN,
    )
    return FindingStore(root), update.findings[0].finding_id


def test_high_confidence_uncovered_behavior_becomes_finding(tmp_path: Path) -> None:
    behavior = _behavior()
    selection = select_findings(*_results(behavior, _assessment(behavior)), observed_at=FIRST_SCAN)

    assert selection.eligible_assessment_count == 1
    assert len(selection.findings) == 1
    assert selection.findings[0].status is FindingStatus.OPEN
    assert selection.findings[0].suggested_scenario is not None


def test_high_confidence_actionable_partial_becomes_finding(tmp_path: Path) -> None:
    del tmp_path
    behavior = _behavior()
    assessment = _assessment(behavior, status=CoverageStatus.PARTIALLY_COVERED)

    selection = select_findings(*_results(behavior, assessment), observed_at=FIRST_SCAN)

    assert selection.findings[0].coverage_status is CoverageStatus.PARTIALLY_COVERED


def test_low_confidence_assessment_is_not_surfaced(tmp_path: Path) -> None:
    del tmp_path
    behavior = _behavior()
    assessment = _assessment(behavior, confidence=ConfidenceLevel.LOW)

    selection = select_findings(*_results(behavior, assessment), observed_at=FIRST_SCAN)

    assert selection.findings == ()


def test_ordinary_high_confidence_branch_is_not_surfaced_by_default(
    tmp_path: Path,
) -> None:
    del tmp_path
    behavior = _behavior(behavior_type=BehaviorType.CONDITIONAL_BRANCH).model_copy(
        update={"action": BehaviorAction(kind="return", target="process_record")}
    )
    assessment = _assessment(behavior)

    selection = select_findings(*_results(behavior, assessment), observed_at=FIRST_SCAN)

    assert selection.findings == ()


def test_duplicate_assessment_is_deduplicated(tmp_path: Path) -> None:
    del tmp_path
    behavior = _behavior()
    assessment = _assessment(behavior)
    behavior_result = BehaviorExtractionResult(
        behaviors=(behavior,), completeness=ScanCompleteness.COMPLETE
    )
    matching_result = MatchingResult(
        assessments=(assessment, assessment),
        completeness=ScanCompleteness.COMPLETE,
        matcher="test-matcher",
    )

    selection = select_findings(behavior_result, matching_result, observed_at=FIRST_SCAN)

    assert len(selection.findings) == 1
    assert selection.duplicate_count == 1


def test_repeated_scans_keep_stable_id_and_do_not_duplicate(tmp_path: Path) -> None:
    behavior = _behavior()
    behavior_result, matching_result = _results(behavior, _assessment(behavior))

    first = update_findings(tmp_path, behavior_result, matching_result, observed_at=FIRST_SCAN)
    second = update_findings(tmp_path, behavior_result, matching_result, observed_at=SECOND_SCAN)

    assert second.new_count == 0
    assert second.existing_count == 1
    assert second.findings[0].finding_id == first.findings[0].finding_id
    assert len(FindingStore(tmp_path).list_findings()) == 1


@pytest.mark.parametrize(
    "disposition",
    [
        FindingDisposition.ADD_EVAL,
        FindingDisposition.VALID_LATER,
        FindingDisposition.ALREADY_COVERED,
        FindingDisposition.NOT_RELEVANT,
        FindingDisposition.SUPPRESSED,
    ],
)
def test_feedback_dispositions_persist(tmp_path: Path, disposition: FindingDisposition) -> None:
    store, finding_id = _create_finding(tmp_path)

    updated = store.record_feedback(
        finding_id,
        disposition,
        reason="reviewed",
        occurred_at=SECOND_SCAN,
    )

    assert updated.current_disposition is disposition
    assert store.get_finding(finding_id).current_disposition is disposition
    assert store.feedback_events(finding_id)[0].disposition is disposition


def test_add_eval_is_intent_only_and_suppression_does_not_resolve(tmp_path: Path) -> None:
    store, finding_id = _create_finding(tmp_path)
    add_eval = store.record_feedback(
        finding_id, FindingDisposition.ADD_EVAL, occurred_at=SECOND_SCAN
    )
    suppressed = store.record_feedback(
        finding_id,
        FindingDisposition.SUPPRESSED,
        occurred_at=SECOND_SCAN + timedelta(hours=1),
    )

    assert add_eval.status is FindingStatus.OPEN
    assert not add_eval.confirmed_impact
    assert suppressed.status is FindingStatus.OPEN
    assert not suppressed.observed_resolution


def test_feedback_is_preserved_across_repeated_scans(tmp_path: Path) -> None:
    store, finding_id = _create_finding(tmp_path)
    store.record_feedback(finding_id, FindingDisposition.VALID_LATER, occurred_at=SECOND_SCAN)
    behavior = _behavior()
    behavior_result, matching_result = _results(behavior, _assessment(behavior))

    update = update_findings(
        tmp_path,
        behavior_result,
        matching_result,
        observed_at=SECOND_SCAN + timedelta(days=1),
    )

    assert update.findings[0].current_disposition is FindingDisposition.VALID_LATER


def test_matching_eval_resolves_with_observed_resolution_only(tmp_path: Path) -> None:
    store, finding_id = _create_finding(tmp_path)
    behavior = _behavior()
    covered = _assessment(
        behavior,
        status=CoverageStatus.COVERED,
        matched_eval_ids=("eval_timeout",),
    )
    behavior_result, matching_result = _results(behavior, covered)

    update = update_findings(tmp_path, behavior_result, matching_result, observed_at=SECOND_SCAN)
    finding = update.findings[0]

    assert update.resolved_count == 1
    assert finding.finding_id == finding_id
    assert finding.status is FindingStatus.RESOLVED
    assert finding.coverage_status is CoverageStatus.COVERED
    assert finding.observed_resolution
    assert finding.resolution_evidence is not None
    assert finding.resolution_evidence.matched_eval_ids == ("eval_timeout",)
    assert not finding.confirmed_impact
    assert FindingHistoryEventType.RESOLVED in {
        event.event_type for event in store.history(finding_id)
    }

    refreshed = _assessment(
        behavior,
        status=CoverageStatus.COVERED,
        matched_eval_ids=("eval_timeout_revised",),
    )
    refreshed_results = _results(behavior, refreshed)
    repeated = update_findings(
        tmp_path,
        *refreshed_results,
        observed_at=SECOND_SCAN + timedelta(hours=1),
    )
    repeated_finding = repeated.findings[0]

    assert repeated.resolved_count == 0
    assert repeated_finding.coverage_status is CoverageStatus.COVERED
    assert repeated_finding.matched_eval_ids == ("eval_timeout_revised",)
    assert repeated_finding.resolution_evidence == finding.resolution_evidence
    assert (
        sum(
            event.event_type is FindingHistoryEventType.RESOLVED
            for event in store.history(finding_id)
        )
        == 1
    )


def test_confirmed_impact_requires_explicit_event(tmp_path: Path) -> None:
    store, finding_id = _create_finding(tmp_path)

    updated = store.confirm_impact(
        finding_id, note="Added the timeout test", occurred_at=SECOND_SCAN
    )

    assert updated.confirmed_impact
    assert len(store.impact_events(finding_id)) == 1
    assert store.impact_events(finding_id)[0].note == "Added the timeout test"


def test_disappearing_behavior_is_no_longer_observed_not_resolved(tmp_path: Path) -> None:
    _, finding_id = _create_finding(tmp_path)
    update = update_findings(
        tmp_path,
        BehaviorExtractionResult(completeness=ScanCompleteness.COMPLETE),
        MatchingResult(completeness=ScanCompleteness.COMPLETE, matcher="test-matcher"),
        observed_at=SECOND_SCAN,
    )

    finding = update.findings[0]
    assert finding.finding_id == finding_id
    assert finding.status is FindingStatus.NO_LONGER_OBSERVED
    assert not finding.observed_resolution


def test_reopened_finding_retains_original_id(tmp_path: Path) -> None:
    _, finding_id = _create_finding(tmp_path)
    update_findings(
        tmp_path,
        BehaviorExtractionResult(completeness=ScanCompleteness.COMPLETE),
        MatchingResult(completeness=ScanCompleteness.COMPLETE, matcher="test-matcher"),
        observed_at=SECOND_SCAN,
    )
    behavior = _behavior()
    behavior_result, matching_result = _results(behavior, _assessment(behavior))

    reopened = update_findings(
        tmp_path,
        behavior_result,
        matching_result,
        observed_at=SECOND_SCAN + timedelta(days=1),
    )

    assert reopened.reopened_count == 1
    assert reopened.findings[0].finding_id == finding_id
    assert reopened.findings[0].status is FindingStatus.OPEN


def test_incomplete_scan_cannot_resolve_or_mark_missing(tmp_path: Path) -> None:
    store, finding_id = _create_finding(tmp_path)

    update = update_findings(
        tmp_path,
        BehaviorExtractionResult(completeness=ScanCompleteness.INCOMPLETE),
        MatchingResult(completeness=ScanCompleteness.INCOMPLETE, matcher="test-matcher"),
        observed_at=SECOND_SCAN,
    )

    finding = update.findings[0]
    assert finding.status is FindingStatus.OPEN
    assert not finding.observed_resolution
    assert FindingHistoryEventType.SCAN_INCOMPLETE in {
        event.event_type for event in store.history(finding_id)
    }


def test_incomplete_scan_can_create_finding_from_available_assessment(tmp_path: Path) -> None:
    behavior = _behavior()
    behavior_result, matching_result = _results(
        behavior,
        _assessment(behavior),
        completeness=ScanCompleteness.INCOMPLETE,
    )

    update = update_findings(
        tmp_path,
        behavior_result,
        matching_result,
        observed_at=FIRST_SCAN,
    )

    assert update.new_count == 1
    assert update.findings[0].assessment_available
    assert update.findings[0].status is FindingStatus.OPEN


def test_state_is_stored_under_scanned_repository_only(tmp_path: Path) -> None:
    tool_repository = tmp_path / "tool"
    target_repository = tmp_path / "target"
    tool_repository.mkdir()
    target_repository.mkdir()
    behavior = _behavior()
    behavior_result, matching_result = _results(behavior, _assessment(behavior))

    update_findings(
        target_repository,
        behavior_result,
        matching_result,
        observed_at=FIRST_SCAN,
    )

    assert (target_repository / ".agentguard" / "agentguard.db").is_file()
    assert not (tool_repository / ".agentguard").exists()
    assert len(FindingStore(target_repository).scan_records()) == 1
