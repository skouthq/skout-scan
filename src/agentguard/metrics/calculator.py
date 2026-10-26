"""Deterministic calculation of repository-local feedback and outcome metrics."""

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from agentguard.feedback import FindingStore
from agentguard.models import (
    ConfidenceLevel,
    FeedbackEvent,
    Finding,
    FindingBreakdown,
    FindingDisposition,
    FindingHistoryEventType,
    MetricCohort,
    MetricName,
    MetricResult,
    ScanCompleteness,
    ValidationCriterion,
    ValidationCriterionStatus,
    ValidationSummary,
)

REVIEWED_DISPOSITIONS = frozenset(
    {
        FindingDisposition.ADD_EVAL,
        FindingDisposition.VALID_LATER,
        FindingDisposition.ALREADY_COVERED,
        FindingDisposition.NOT_RELEVANT,
    }
)


def _latest_feedback(events: tuple[FeedbackEvent, ...]) -> FeedbackEvent | None:
    return events[-1] if events else None


def _is_review_event(event: FeedbackEvent) -> bool:
    return event.disposition in REVIEWED_DISPOSITIONS or (
        event.disposition is FindingDisposition.SUPPRESSED
        and (event.reason is not None or event.feedback_reason is not None)
    )


def _is_reviewed(finding: Finding, latest: FeedbackEvent | None) -> bool:
    if not finding.assessment_available:
        return False
    if finding.current_disposition in REVIEWED_DISPOSITIONS:
        return True
    return (
        finding.current_disposition is FindingDisposition.SUPPRESSED
        and latest is not None
        and (latest.reason is not None or latest.feedback_reason is not None)
    )


def _metric(
    name: MetricName,
    numerator_ids: set[str],
    denominator_ids: set[str],
    description: str,
    explanation: str,
    total_findings: int,
) -> MetricResult:
    numerator = len(numerator_ids & denominator_ids)
    denominator = len(denominator_ids)
    return MetricResult(
        name=name,
        numerator=numerator,
        denominator=denominator,
        rate=numerator / denominator if denominator else None,
        cohort=MetricCohort(
            description=description,
            eligible_finding_ids=tuple(sorted(denominator_ids)),
            excluded_finding_count=total_findings - denominator,
        ),
        explanation=explanation,
    )


def _breakdowns(
    findings: tuple[Finding, ...],
    reviewed_ids: set[str],
    resolved_ids: set[str],
    first_review_confidence: dict[str, ConfidenceLevel],
) -> tuple[FindingBreakdown, ...]:
    dimensions: dict[str, Callable[[Finding], str]] = {
        "behavior_type": lambda finding: finding.behavior_type.value,
        "source_file": lambda finding: finding.source_file,
        "confidence": lambda finding: (
            first_review_confidence.get(finding.finding_id, finding.current_confidence).value
        ),
        "coverage_status": lambda finding: finding.coverage_status.value,
        "rejection_reason": lambda finding: (
            finding.current_feedback_reason.value if finding.current_feedback_reason else "none"
        ),
    }
    groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for finding in findings:
        for dimension, value_for in dimensions.items():
            groups[(dimension, value_for(finding))].append(finding)

    results: list[FindingBreakdown] = []
    for (dimension, value), members in sorted(groups.items()):
        results.append(
            FindingBreakdown(
                dimension=dimension,
                value=value,
                total=len(members),
                reviewed=sum(f.finding_id in reviewed_ids for f in members),
                valid_gap=sum(
                    f.finding_id in reviewed_ids
                    and f.current_disposition
                    in {FindingDisposition.ADD_EVAL, FindingDisposition.VALID_LATER}
                    for f in members
                ),
                add_eval=sum(
                    f.finding_id in reviewed_ids
                    and f.current_disposition is FindingDisposition.ADD_EVAL
                    for f in members
                ),
                already_covered=sum(
                    f.finding_id in reviewed_ids
                    and f.current_disposition is FindingDisposition.ALREADY_COVERED
                    for f in members
                ),
                not_relevant=sum(
                    f.finding_id in reviewed_ids
                    and f.current_disposition is FindingDisposition.NOT_RELEVANT
                    for f in members
                ),
                suppressed=sum(
                    f.current_disposition is FindingDisposition.SUPPRESSED for f in members
                ),
                observed_resolution=sum(f.finding_id in resolved_ids for f in members),
                confirmed_impact=sum(f.confirmed_impact for f in members),
            )
        )
    return tuple(results)


def calculate_validation_summary(store: FindingStore) -> ValidationSummary:
    """Calculate all V0 metrics from current findings and append-only history."""
    findings = store.list_findings()
    scans = store.scan_records()
    feedback = {
        finding.finding_id: store.feedback_events(finding.finding_id) for finding in findings
    }
    latest_feedback = {
        finding_id: _latest_feedback(events) for finding_id, events in feedback.items()
    }
    reviewed_ids = {
        finding.finding_id
        for finding in findings
        if _is_reviewed(finding, latest_feedback[finding.finding_id])
    }
    first_review_confidence = {}
    for finding_id, events in feedback.items():
        first_review = next((event for event in events if _is_review_event(event)), None)
        if first_review is not None:
            first_review_confidence[finding_id] = first_review.confidence_at_feedback
    high_confidence_reviewed_ids = {
        finding_id
        for finding_id in reviewed_ids
        if first_review_confidence.get(finding_id) is ConfidenceLevel.HIGH
    }
    complete_scan_times = tuple(
        scan.occurred_at for scan in scans if scan.completeness is ScanCompleteness.COMPLETE
    )
    follow_up_ids = {
        finding.finding_id
        for finding in findings
        if finding.assessment_available
        and any(scan_time > finding.first_seen for scan_time in complete_scan_times)
    }
    resolved_ids = {
        finding.finding_id
        for finding in findings
        if any(
            event.event_type is FindingHistoryEventType.RESOLVED
            for event in store.history(finding.finding_id)
        )
    }
    valid_ids = {
        finding.finding_id
        for finding in findings
        if finding.current_disposition
        in {FindingDisposition.ADD_EVAL, FindingDisposition.VALID_LATER}
    }
    add_eval_ids = {
        finding.finding_id
        for finding in findings
        if finding.current_disposition is FindingDisposition.ADD_EVAL
    }
    false_positive_ids = {
        finding.finding_id
        for finding in findings
        if finding.current_disposition is FindingDisposition.ALREADY_COVERED
    }
    confirmed_ids = {finding.finding_id for finding in findings if finding.confirmed_impact}
    total = len(findings)
    reviewed_description = (
        "Unique assessable findings with a current review disposition; reasoned suppression is "
        "eligible."
    )
    resolution_description = (
        "Unique assessable findings that were open and had a later complete scan."
    )
    metrics = (
        _metric(
            MetricName.VALID_GAP_RATE,
            valid_ids,
            reviewed_ids,
            reviewed_description,
            "Current add_eval and valid_later dispositions among eligible reviewed findings.",
            total,
        ),
        _metric(
            MetricName.INTENT_TO_ACT_RATE,
            add_eval_ids,
            reviewed_ids,
            reviewed_description,
            "Current add_eval dispositions; this records intent, not confirmed impact.",
            total,
        ),
        _metric(
            MetricName.OBSERVED_RESOLUTION_RATE,
            resolved_ids,
            follow_up_ids,
            resolution_description,
            "Findings with an observed resolution event after becoming eligible for follow-up.",
            total,
        ),
        _metric(
            MetricName.CONFIRMED_IMPACT_RATE,
            confirmed_ids,
            high_confidence_reviewed_ids,
            "Eligible reviewed findings whose confidence at first review was high.",
            "Explicit impact confirmations among reviewed high-confidence findings.",
            total,
        ),
        _metric(
            MetricName.FALSE_POSITIVE_RATE,
            false_positive_ids,
            reviewed_ids,
            reviewed_description,
            "Current already_covered dispositions among eligible reviewed findings.",
            total,
        ),
        _metric(
            MetricName.RESOLVED_BY_TEST_RATE,
            resolved_ids,
            follow_up_ids,
            resolution_description,
            "Observed test resolutions among eligible findings with a later complete scan.",
            total,
        ),
    )
    metric_by_name = {metric.name: metric for metric in metrics}
    high_valid = len(valid_ids & high_confidence_reviewed_ids)
    high_reviewed = len(high_confidence_reviewed_ids)
    high_valid_rate = high_valid / high_reviewed if high_reviewed else None
    confirmed = metric_by_name[MetricName.CONFIRMED_IMPACT_RATE]
    false_positive = metric_by_name[MetricName.FALSE_POSITIVE_RATE]
    impact_examples = len(resolved_ids & confirmed_ids)
    repository_count = 1 if scans else 0
    criteria = (
        ValidationCriterion(
            name="repositories_evaluated",
            current=str(repository_count),
            target=">=20",
            status=(
                ValidationCriterionStatus.PASS
                if repository_count >= 20
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation=(
                "Repository-local state only; aggregate repository counts require combining "
                "exports from separate repositories."
            ),
        ),
        ValidationCriterion(
            name="valid_high_confidence_findings",
            current=(
                f"{high_valid_rate:.1%}" if high_valid_rate is not None else "not enough data"
            ),
            target=">=70%",
            status=(
                ValidationCriterionStatus.NOT_ENOUGH_DATA
                if high_valid_rate is None
                else ValidationCriterionStatus.PASS
                if high_valid_rate >= 0.70
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation="Validity uses confidence frozen at the first review.",
        ),
        ValidationCriterion(
            name="confirmed_impact",
            current=(f"{confirmed.rate:.1%}" if confirmed.rate is not None else "not enough data"),
            target=">=30%",
            status=(
                ValidationCriterionStatus.NOT_ENOUGH_DATA
                if confirmed.rate is None
                else ValidationCriterionStatus.PASS
                if confirmed.rate >= 0.30
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation="Requires an explicit user confirmation event.",
        ),
        ValidationCriterion(
            name="false_positive_rate",
            current=(
                f"{false_positive.rate:.1%}"
                if false_positive.rate is not None
                else "not enough data"
            ),
            target="<25%",
            status=(
                ValidationCriterionStatus.NOT_ENOUGH_DATA
                if false_positive.rate is None
                else ValidationCriterionStatus.PASS
                if false_positive.rate < 0.25
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation="Uses the upper bound of the specified approximate 20–25% target.",
        ),
        ValidationCriterion(
            name="repeat_scan_evidence",
            current=str(len(scans)),
            target=">=2 scans",
            status=(
                ValidationCriterionStatus.PASS
                if len(scans) >= 2
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation=(
                "Counts complete and incomplete persisted scan attempts in this repository."
            ),
        ),
        ValidationCriterion(
            name="resolution_impact_examples",
            current=str(impact_examples),
            target=">=1",
            status=(
                ValidationCriterionStatus.PASS
                if impact_examples >= 1
                else ValidationCriterionStatus.NOT_YET
            ),
            explanation="A finding must have both observed resolution and confirmed impact.",
        ),
    )
    return ValidationSummary(
        repository=str(store.repository_root),
        finding_count=total,
        reviewed_finding_count=len(reviewed_ids),
        scan_count=len(scans),
        metrics=metrics,
        breakdowns=_breakdowns(findings, reviewed_ids, resolved_ids, first_review_confidence),
        criteria=criteria,
    )


def export_validation_data(store: FindingStore) -> dict[str, Any]:
    """Build a local export without source excerpts or repository contents."""
    summary = calculate_validation_summary(store)
    findings = []
    for finding in store.list_findings():
        findings.append(
            {
                "finding_id": finding.finding_id,
                "behavior_id": finding.behavior_id,
                "behavior_type": finding.behavior_type.value,
                "source_file": finding.source_file,
                "coverage_status": finding.coverage_status.value,
                "confidence": finding.current_confidence.value,
                "disposition": (
                    finding.current_disposition.value if finding.current_disposition else None
                ),
                "feedback_reason": (
                    finding.current_feedback_reason.value
                    if finding.current_feedback_reason
                    else None
                ),
                "status": finding.status.value,
                "assessment_available": finding.assessment_available,
                "observed_resolution": finding.observed_resolution,
                "confirmed_impact": finding.confirmed_impact,
                "first_seen": finding.first_seen.isoformat(),
                "last_seen": finding.last_seen.isoformat(),
                "verification_evidence": [
                    {
                        **match.model_dump(mode="json", exclude={"source_evidence", "evidence"}),
                        "match_dimensions": match.evidence.model_dump(
                            mode="json", exclude={"details"}
                        ),
                        "source_locations": [
                            evidence.model_dump(mode="json", exclude={"excerpt"})
                            for evidence in match.source_evidence
                        ],
                    }
                    for match in finding.matched_eval_evidence
                ],
                "structured_explanation": (
                    finding.structured_explanation.model_dump(mode="json", exclude={"behavior"})
                    if finding.structured_explanation is not None
                    else None
                ),
            }
        )
    return {"summary": summary.model_dump(mode="json"), "findings": findings}
