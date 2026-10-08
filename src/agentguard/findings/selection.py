"""Deterministic selection of actionable coverage findings."""

import hashlib
import json
from datetime import UTC, datetime

from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorSourceType,
    BehaviorType,
    ConfidenceLevel,
    CoverageStatus,
    Finding,
    FindingSelectionResult,
    FindingStatus,
    MatchingResult,
)

FINDING_ID_VERSION = "finding-v1"
TYPE_PRIORITY = {
    BehaviorType.TOOL_FAILURE: 0,
    BehaviorType.ESCALATION: 1,
    BehaviorType.FALLBACK: 2,
    BehaviorType.CONDITIONAL_BRANCH: 3,
    BehaviorType.TOOL_INVOCATION: 4,
    BehaviorType.WORKFLOW_TRANSITION: 5,
}


def _finding_id(behavior_id: str) -> str:
    identity = json.dumps(
        {"version": FINDING_ID_VERSION, "behavior_id": behavior_id},
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"finding_{digest[:24]}"


def _is_actionable(behavior: Behavior, assessment: BehaviorCoverageAssessment) -> bool:
    if assessment.availability is not AssessmentAvailability.AVAILABLE:
        return False
    if assessment.coverage_status not in {
        CoverageStatus.PARTIALLY_COVERED,
        CoverageStatus.POTENTIALLY_UNCOVERED,
    }:
        return False
    if assessment.confidence is not ConfidenceLevel.HIGH:
        return False
    if behavior.behavior_type in {
        BehaviorType.TOOL_FAILURE,
        BehaviorType.FALLBACK,
        BehaviorType.ESCALATION,
    }:
        return True
    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        return assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    if behavior.behavior_type is BehaviorType.CONDITIONAL_BRANCH:
        if behavior.action is None:
            return False
        target = (behavior.action.target or "").casefold()
        return behavior.action.kind in {"raise", "call"} or any(
            term in target for term in ("escalat", "handoff", "human", "fallback")
        )
    return False


def _concern_key(behavior: Behavior) -> tuple[str, str, str, str]:
    condition = behavior.condition.normalized_expression if behavior.condition else ""
    action = ""
    if behavior.action is not None:
        action = ":".join(
            item
            for item in (
                behavior.action.kind,
                behavior.action.target,
                behavior.action.outcome,
            )
            if item
        )
    return behavior.source_file, behavior.subject, condition, action


def _title(behavior: Behavior, assessment: BehaviorCoverageAssessment) -> str:
    status = (
        "partially covered"
        if assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
        else "potentially uncovered"
    )
    if behavior.behavior_type is BehaviorType.TOOL_FAILURE:
        return f"{behavior.subject} failure behavior is {status}"
    if behavior.behavior_type is BehaviorType.ESCALATION:
        return f"{behavior.subject} escalation is {status}"
    if behavior.behavior_type is BehaviorType.FALLBACK:
        return f"{behavior.subject} fallback is {status}"
    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        if behavior.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT:
            return f"{behavior.subject} agent invocation is {status}"
        return f"{behavior.subject} tool invocation is {status}"
    return f"{behavior.subject} conditional behavior is {status}"


def _suggested_scenario(behavior: Behavior) -> str:
    condition = behavior.condition.expression if behavior.condition else None
    action = behavior.action
    if behavior.behavior_type is BehaviorType.TOOL_FAILURE:
        outcome = action.outcome if action and action.outcome else "the expected failure outcome"
        if condition:
            return (
                f"Test {behavior.subject} when {condition} and verify {outcome} or the "
                "documented fallback behavior."
            )
        return f"Test {behavior.subject} and verify the explicit failure outcome {outcome}."
    if behavior.behavior_type is BehaviorType.ESCALATION:
        context = f" when {condition}" if condition else ""
        return f"Test {behavior.subject}{context} and verify escalation or handoff occurs."
    if behavior.behavior_type is BehaviorType.FALLBACK:
        context = f" when {condition}" if condition else ""
        return f"Test {behavior.subject}{context} and verify the fallback path is selected."
    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        if behavior.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT:
            return (
                f"Run {behavior.subject} with a representative input and assert a meaningful "
                "result or invariant."
            )
        required = [argument.name for argument in behavior.arguments if argument.required]
        argument_text = f" with required inputs {', '.join(required)}" if required else ""
        return (
            f"Invoke {behavior.subject}{argument_text} and assert a meaningful result or invariant."
        )
    target = action.target if action and action.target else "the expected branch action"
    context = f" for {condition}" if condition else ""
    return f"Test {behavior.subject}{context} and verify {target}."


def _new_finding(
    behavior: Behavior,
    assessment: BehaviorCoverageAssessment,
    observed_at: datetime,
) -> Finding:
    coverage_status = assessment.coverage_status
    if coverage_status is None:
        raise ValueError("An actionable assessment must have a coverage status.")
    return Finding(
        finding_id=_finding_id(behavior.behavior_id),
        behavior_id=behavior.behavior_id,
        behavior_type=behavior.behavior_type,
        behavior_subject=behavior.subject,
        coverage_status=coverage_status,
        confidence_at_creation=assessment.confidence,
        current_confidence=assessment.confidence,
        title=_title(behavior, assessment),
        explanation=assessment.explanation,
        source_file=behavior.source_file,
        source_symbol=behavior.source_symbol,
        source_evidence=behavior.evidence,
        matched_eval_ids=assessment.matched_eval_ids,
        matched_eval_evidence=assessment.matches,
        suggested_scenario=_suggested_scenario(behavior),
        first_seen=observed_at,
        last_seen=observed_at,
        status=FindingStatus.OPEN,
        matcher=assessment.matcher,
    )


def select_findings(
    behavior_result: BehaviorExtractionResult,
    matching_result: MatchingResult,
    *,
    observed_at: datetime | None = None,
) -> FindingSelectionResult:
    """Select and conservatively deduplicate actionable assessments."""
    timestamp = observed_at or datetime.now(UTC)
    behaviors = {behavior.behavior_id: behavior for behavior in behavior_result.behaviors}
    eligible: list[tuple[Behavior, BehaviorCoverageAssessment]] = []
    for assessment in matching_result.assessments:
        behavior = behaviors.get(assessment.behavior_id)
        if behavior is not None and _is_actionable(behavior, assessment):
            eligible.append((behavior, assessment))

    selected: dict[tuple[str, str, str, str], tuple[Behavior, BehaviorCoverageAssessment]] = {}
    for behavior, assessment in sorted(
        eligible,
        key=lambda item: (
            TYPE_PRIORITY[item[0].behavior_type],
            item[0].behavior_id,
        ),
    ):
        selected.setdefault(_concern_key(behavior), (behavior, assessment))

    findings = tuple(
        sorted(
            (
                _new_finding(behavior, assessment, timestamp)
                for behavior, assessment in selected.values()
            ),
            key=lambda finding: finding.finding_id,
        )
    )
    return FindingSelectionResult(
        findings=findings,
        eligible_assessment_count=len(eligible),
        duplicate_count=len(eligible) - len(findings),
    )
