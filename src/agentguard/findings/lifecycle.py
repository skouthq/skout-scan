"""Finding lifecycle transitions driven by available deterministic assessments."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import JsonValue

from agentguard.feedback import FindingStore
from agentguard.findings.selection import select_findings
from agentguard.models import (
    AssessmentAvailability,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    CoverageStatus,
    Finding,
    FindingHistoryEvent,
    FindingHistoryEventType,
    FindingScanRecord,
    FindingSelectionResult,
    FindingStatus,
    FindingUpdateResult,
    MatchingResult,
    ResolutionEvidence,
    ScanCompleteness,
)


def _history_event(
    finding_id: str,
    event_type: FindingHistoryEventType,
    timestamp: datetime,
    **details: JsonValue,
) -> FindingHistoryEvent:
    return FindingHistoryEvent(
        event_id=f"history_{uuid4().hex}",
        finding_id=finding_id,
        event_type=event_type,
        occurred_at=timestamp,
        details=details,
    )


def _refresh_finding(existing: Finding, current: Finding, timestamp: datetime) -> Finding:
    return current.model_copy(
        update={
            "first_seen": existing.first_seen,
            "last_seen": timestamp,
            "current_disposition": existing.current_disposition,
            "current_feedback_reason": existing.current_feedback_reason,
            "confirmed_impact": existing.confirmed_impact,
            "assessment_available": True,
            "status": FindingStatus.OPEN,
            "observed_resolution": False,
            "resolution_evidence": None,
        }
    )


def _resolve_finding(
    finding: Finding,
    assessment: BehaviorCoverageAssessment,
    timestamp: datetime,
) -> Finding:
    return finding.model_copy(
        update={
            "last_seen": timestamp,
            "status": FindingStatus.RESOLVED,
            "observed_resolution": True,
            "resolution_evidence": ResolutionEvidence(
                resolved_at=timestamp,
                matched_eval_ids=assessment.matched_eval_ids,
                matcher=assessment.matcher,
                explanation=assessment.explanation,
            ),
            "matched_eval_ids": assessment.matched_eval_ids,
            "matched_eval_evidence": assessment.matches,
            "coverage_status": assessment.coverage_status,
            "current_confidence": assessment.confidence,
            "matcher": assessment.matcher,
            "assessment_available": True,
        }
    )


def update_findings(
    repository_root: str | Path,
    behavior_result: BehaviorExtractionResult,
    matching_result: MatchingResult,
    *,
    observed_at: datetime | None = None,
) -> FindingUpdateResult:
    """Select findings, apply lifecycle transitions, and persist one scan atomically."""
    timestamp = observed_at or datetime.now(UTC)
    store = FindingStore(repository_root)
    existing_findings = {finding.behavior_id: finding for finding in store.list_findings()}
    usable = (
        behavior_result.completeness is not ScanCompleteness.FAILED
        and matching_result.completeness is not ScanCompleteness.FAILED
    )
    selection = (
        select_findings(behavior_result, matching_result, observed_at=timestamp)
        if usable
        else FindingSelectionResult()
    )
    selected_by_behavior = {finding.behavior_id: finding for finding in selection.findings}
    assessments = {assessment.behavior_id: assessment for assessment in matching_result.assessments}
    observed_behaviors = {behavior.behavior_id for behavior in behavior_result.behaviors}
    updated: dict[str, Finding] = {}
    history: list[FindingHistoryEvent] = []
    new_count = 0
    existing_count = 0
    resolved_count = 0
    reopened_count = 0
    no_longer_observed_count = 0

    if usable:
        for behavior_id, candidate in selected_by_behavior.items():
            existing = existing_findings.get(behavior_id)
            if existing is None:
                updated[behavior_id] = candidate
                new_count += 1
                history.append(
                    _history_event(
                        candidate.finding_id,
                        FindingHistoryEventType.CREATED,
                        timestamp,
                        coverage_status=candidate.coverage_status.value,
                    )
                )
                continue
            refreshed = _refresh_finding(existing, candidate, timestamp)
            updated[behavior_id] = refreshed
            if existing.status is FindingStatus.OPEN:
                existing_count += 1
                event_type = FindingHistoryEventType.SEEN
            else:
                reopened_count += 1
                event_type = FindingHistoryEventType.REOPENED
            history.append(_history_event(existing.finding_id, event_type, timestamp))

        for behavior_id, existing in existing_findings.items():
            if behavior_id in updated:
                continue
            assessment = assessments.get(behavior_id)
            if (
                assessment is not None
                and assessment.availability is AssessmentAvailability.UNAVAILABLE
            ):
                updated[behavior_id] = existing.model_copy(
                    update={"last_seen": timestamp, "assessment_available": False}
                )
                history.append(
                    _history_event(
                        existing.finding_id,
                        FindingHistoryEventType.SCAN_INCOMPLETE,
                        timestamp,
                        completeness=matching_result.completeness.value,
                    )
                )
            elif assessment is not None and assessment.coverage_status is CoverageStatus.COVERED:
                if existing.status is FindingStatus.RESOLVED:
                    updated[behavior_id] = existing.model_copy(
                        update={
                            "last_seen": timestamp,
                            "coverage_status": assessment.coverage_status,
                            "current_confidence": assessment.confidence,
                            "matched_eval_ids": assessment.matched_eval_ids,
                            "matched_eval_evidence": assessment.matches,
                            "matcher": assessment.matcher,
                            "assessment_available": True,
                        }
                    )
                    continue
                resolved = _resolve_finding(existing, assessment, timestamp)
                updated[behavior_id] = resolved
                resolved_count += 1
                history.append(
                    _history_event(
                        existing.finding_id,
                        FindingHistoryEventType.RESOLVED,
                        timestamp,
                        matched_eval_ids=",".join(assessment.matched_eval_ids),
                    )
                )
            elif (
                behavior_id not in observed_behaviors
                and behavior_result.completeness is ScanCompleteness.COMPLETE
            ):
                if existing.status is FindingStatus.NO_LONGER_OBSERVED:
                    updated[behavior_id] = existing
                    continue
                missing = existing.model_copy(
                    update={
                        "status": FindingStatus.NO_LONGER_OBSERVED,
                        "assessment_available": True,
                    }
                )
                updated[behavior_id] = missing
                no_longer_observed_count += 1
                history.append(
                    _history_event(
                        existing.finding_id,
                        FindingHistoryEventType.NO_LONGER_OBSERVED,
                        timestamp,
                    )
                )
            elif behavior_id in observed_behaviors:
                is_gap = assessment is not None and assessment.coverage_status in {
                    CoverageStatus.PARTIALLY_COVERED,
                    CoverageStatus.POTENTIALLY_UNCOVERED,
                }
                if is_gap and assessment is not None and existing.status is not FindingStatus.OPEN:
                    updated[behavior_id] = existing.model_copy(
                        update={
                            "last_seen": timestamp,
                            "status": FindingStatus.OPEN,
                            "observed_resolution": False,
                            "resolution_evidence": None,
                            "coverage_status": assessment.coverage_status,
                            "current_confidence": assessment.confidence,
                            "assessment_available": True,
                        }
                    )
                    reopened_count += 1
                    history.append(
                        _history_event(
                            existing.finding_id,
                            FindingHistoryEventType.REOPENED,
                            timestamp,
                        )
                    )
                else:
                    updated[behavior_id] = existing.model_copy(
                        update={"last_seen": timestamp, "assessment_available": True}
                    )
                    history.append(
                        _history_event(
                            existing.finding_id,
                            FindingHistoryEventType.SEEN,
                            timestamp,
                        )
                    )
            else:
                updated[behavior_id] = existing.model_copy(update={"assessment_available": False})
                history.append(
                    _history_event(
                        existing.finding_id,
                        FindingHistoryEventType.SCAN_INCOMPLETE,
                        timestamp,
                        completeness=matching_result.completeness.value,
                    )
                )
    else:
        for behavior_id, existing in existing_findings.items():
            updated[behavior_id] = existing.model_copy(update={"assessment_available": False})
            history.append(
                _history_event(
                    existing.finding_id,
                    FindingHistoryEventType.SCAN_INCOMPLETE,
                    timestamp,
                    completeness=matching_result.completeness.value,
                )
            )

    result = FindingUpdateResult(
        findings=tuple(sorted(updated.values(), key=lambda finding: finding.finding_id)),
        eligible_assessment_count=selection.eligible_assessment_count,
        new_count=new_count,
        existing_count=existing_count,
        resolved_count=resolved_count,
        reopened_count=reopened_count,
        no_longer_observed_count=no_longer_observed_count,
    )
    scan_record = FindingScanRecord(
        scan_id=f"scan_{uuid4().hex}",
        occurred_at=timestamp,
        completeness=matching_result.completeness,
        behavior_count=len(behavior_result.behaviors),
        assessment_count=len(matching_result.assessments),
        eligible_assessment_count=result.eligible_assessment_count,
        new_count=result.new_count,
        existing_count=result.existing_count,
        resolved_count=result.resolved_count,
        reopened_count=result.reopened_count,
        no_longer_observed_count=result.no_longer_observed_count,
    )
    store.persist_scan(result.findings, tuple(history), scan_record)
    return result
