"""Deterministic evidence-to-action presentation, downstream of finding selection."""

from collections.abc import Sequence
from typing import Literal

from rich.console import Console

from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorCoverageAssessment,
    BehaviorEvalMatch,
    BehaviorType,
    ConfidenceLevel,
    CoverageDimension,
    CoverageExplanation,
    CoverageReason,
    CoverageStatus,
    Finding,
    FindingGuidance,
    GuidanceGap,
    ScanCompleteness,
    SourceEvidence,
)

OWNER_REASONS = {
    CoverageReason.GRAPH_OWNER_NOT_VERIFIED,
    CoverageReason.GRAPH_OWNER_MISMATCH,
    CoverageReason.GRAPH_OWNER_AMBIGUOUS,
}


def _contract(behavior: Behavior) -> tuple[str, str, str] | None:
    action = behavior.action
    condition = behavior.condition.expression if behavior.condition else None
    if action and action.kind == "raise" and action.outcome and condition:
        claim = f"{behavior.subject} raises {action.outcome} when {condition}"
        return claim, f"Verify that {claim}.", f"Explicitly assert {action.outcome}."
    if action and action.kind == "transition" and action.target and condition:
        claim = f"{behavior.subject} selects {action.target} when {condition}"
        return (
            claim,
            f"Verify that {claim} for the correct graph.",
            (f"Assert the route target {action.target} for {behavior.subject}."),
        )
    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        return (
            f"{behavior.subject} has a declared invocation surface",
            f"Verify an invocation of {behavior.subject} and a meaningful result or invariant.",
            "Assert a meaningful result or invariant; no particular output is inferred.",
        )
    if action and action.kind in {"return", "call"}:
        outcome = action.outcome if action.kind == "return" else action.target
        if outcome:
            suffix = f" when {condition}" if condition else ""
            claim = f"{behavior.subject} declares {action.kind} {outcome}{suffix}"
            return (
                claim,
                f"Verify the explicit source action: {claim}.",
                (f"Verify the declared {action.kind} outcome {outcome}."),
            )
    return None


def _references(
    detail: CoverageExplanation, matches: Sequence[BehaviorEvalMatch]
) -> tuple[SourceEvidence, ...]:
    refs = list(detail.behavior.evidence)
    context = detail.rejection_provenance
    if context:
        refs.extend(context.source_evidence)
        for registration in context.registrations:
            refs.extend(
                (
                    *registration.owner_evidence,
                    registration.registration_evidence,
                    registration.callable_evidence,
                )
            )
    for match in matches:
        refs.extend(match.source_evidence)
    unique = {ref.model_dump_json(): ref for ref in refs}
    return tuple(
        sorted(
            unique.values(),
            key=lambda r: (
                r.source_file,
                r.start_line or 0,
                r.end_line or 0,
                r.kind,
                r.source_symbol or "",
                r.excerpt,
            ),
        )
    )


def build_guidance(
    detail: CoverageExplanation | None,
    matches: Sequence[BehaviorEvalMatch],
    status: CoverageStatus | None,
    confidence: ConfidenceLevel,
    *,
    available: bool = True,
    finding_id: str | None = None,
) -> FindingGuidance | None:
    """Read existing dimensions verbatim; never rank, union, or re-match evidence."""
    if detail is None:
        return None
    behavior = detail.behavior
    contract = _contract(behavior)
    if contract is None:
        return None
    summary, goal, outcome_action = contract
    uncertain = (
        not available
        or status is None
        or confidence is ConfidenceLevel.LOW
        or detail.scan_completeness is not ScanCompleteness.COMPLETE
        or CoverageReason.UNSUPPORTED_EVIDENCE_PATTERN in detail.reason_codes
    )
    level: Literal["assessable_gap", "partial_evidence", "covered_context", "analysis_uncertain"]
    level = (
        "analysis_uncertain"
        if uncertain
        else "covered_context"
        if status is CoverageStatus.COVERED
        else "partial_evidence"
        if status is CoverageStatus.PARTIALLY_COVERED
        else "assessable_gap"
    )
    gaps = []
    for dimension in detail.missing_dimensions if available else ():
        if dimension is CoverageDimension.FUNCTIONALITY:
            explanation = (
                "The recognized evidence does not establish the intended callable or graph."
            )
            action = f"Target {behavior.source_file}::{behavior.source_symbol or behavior.subject}."
            if behavior.action and behavior.action.kind == "transition":
                explanation = (
                    "The recognized evidence does not establish the required graph identity."
                    if OWNER_REASONS.intersection(detail.reason_codes)
                    else explanation
                )
                action += " Use a supported graph invocation or validated explicit owner binding."
        elif dimension is CoverageDimension.CONDITION:
            condition = behavior.condition.expression if behavior.condition else None
            explanation = (
                f"The recognized evidence does not establish condition {condition}."
                if condition
                else "No explicit condition is available to describe this gap."
            )
            action = (
                f"Exercise the explicit condition {condition}."
                if condition
                else ("Inspect the missing condition evidence; no concrete input is inferred.")
            )
        else:
            explanation = "The recognized evidence does not verify the required expected outcome."
            action = outcome_action
        gaps.append(
            GuidanceGap(
                dimension=dimension,
                explanation=explanation,
                suggested_action="" if uncertain or status is CoverageStatus.COVERED else action,
            )
        )
    if uncertain:
        next_step = (
            "Review the unavailable, incomplete or unsupported evidence before deciding "
            "whether to add a verification scenario."
        )
    elif status is CoverageStatus.COVERED:
        next_step = (
            "Inspect the matched evidence; this assessment indicates no missing verification step."
        )
    elif gaps:
        next_step = " ".join(gap.suggested_action for gap in gaps)
    else:
        next_step = (
            "Inspect the assessment and recognized evidence; "
            "no specific missing dimension is recorded."
        )
    return FindingGuidance(
        finding_id=finding_id,
        behavior_id=behavior.behavior_id,
        behavior_summary=summary,
        verification_goal=goal,
        interpretation=level,
        observed_evidence=tuple(matches),
        closest_eval_id=detail.closest_eval_id,
        missing_evidence=tuple(gaps),
        suggested_next_step=next_step,
        source_references=_references(detail, matches),
        limitations=(
            *detail.limitations,
            "Guidance describes verification, not runtime test results or business priority.",
        ),
        reason_codes=detail.reason_codes,
    )


def guidance_for_assessment(assessment: BehaviorCoverageAssessment) -> FindingGuidance | None:
    return build_guidance(
        assessment.structured_explanation,
        assessment.matches,
        assessment.coverage_status,
        assessment.confidence,
        available=assessment.availability is AssessmentAvailability.AVAILABLE,
    )


def with_guidance(finding: Finding) -> Finding:
    """Return a presentation copy. Callers must not feed it into persistence."""
    return finding.model_copy(
        update={
            "guidance": build_guidance(
                finding.structured_explanation,
                finding.matched_eval_evidence,
                finding.coverage_status,
                finding.current_confidence,
                available=finding.assessment_available,
                finding_id=finding.finding_id,
            )
        }
    )


def render_finding_guidance(output: Console, finding: Finding, *, compact: bool = False) -> bool:
    """Compatibility entry point for terminal rendering; guidance semantics stay unchanged."""
    from agentguard.presentation import render_finding, render_preview

    if with_guidance(finding).guidance is None:
        return False
    if compact:
        render_preview(output, finding)
    else:
        render_finding(output, finding)
    return True
