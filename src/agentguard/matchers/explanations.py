"""Structured explanations derived solely from existing static match decisions."""

from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorType,
    CoverageDimension,
    CoverageExplanation,
    CoverageReason,
    CoverageStatus,
    EvalParseResult,
    ScanCompleteness,
)

STATIC_LIMITATION = (
    "Static evidence only; target code and tests were not executed. "
    "Unsupported test/eval implementations may not be recognized."
)


def explain_assessment(
    behavior: Behavior,
    assessment: BehaviorCoverageAssessment,
    behaviors: BehaviorExtractionResult,
    evals: EvalParseResult,
) -> CoverageExplanation:
    """Keep source references on matches, and explain the closest single candidate.

    Dimensions from separate evals are never combined to imply a sufficient match.
    Unknown assessments intentionally omit missing dimensions: absence is not known.
    """
    reasons: list[CoverageReason] = []
    closest = min(
        assessment.matches,
        key=lambda match: (len(match.missing_dimensions), match.eval_id),
        default=None,
    )
    missing: tuple[CoverageDimension, ...] = ()
    unavailable = assessment.availability is AssessmentAvailability.UNAVAILABLE
    if not unavailable:
        if assessment.coverage_status is CoverageStatus.COVERED:
            reasons.append(CoverageReason.SUFFICIENT_MATCHING_EVIDENCE)
        else:
            if closest is None:
                reasons.append(CoverageReason.NO_QUALIFYING_EVIDENCE)
                missing = (CoverageDimension.FUNCTIONALITY, CoverageDimension.EXPECTED_OUTCOME)
                if behavior.condition is not None and (
                    behavior.behavior_type is not BehaviorType.TOOL_INVOCATION
                ):
                    missing = (*missing[:1], CoverageDimension.CONDITION, *missing[1:])
            else:
                missing = closest.missing_dimensions
            if assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED:
                reasons.append(CoverageReason.PARTIAL_DIMENSION_MATCH)
            reason_for_dimension = {
                CoverageDimension.FUNCTIONALITY: CoverageReason.FUNCTIONALITY_NOT_MATCHED,
                CoverageDimension.CONDITION: CoverageReason.CONDITION_NOT_MATCHED,
                CoverageDimension.EXPECTED_OUTCOME: CoverageReason.EXPECTED_OUTCOME_NOT_MATCHED,
            }
            reasons.extend(reason_for_dimension[dimension] for dimension in missing)

    completeness = (
        ScanCompleteness.FAILED
        if ScanCompleteness.FAILED in {behaviors.completeness, evals.completeness}
        else ScanCompleteness.INCOMPLETE
        if ScanCompleteness.INCOMPLETE in {behaviors.completeness, evals.completeness}
        else ScanCompleteness.COMPLETE
    )
    limitations = [STATIC_LIMITATION]
    if completeness is not ScanCompleteness.COMPLETE or unavailable:
        reasons.append(CoverageReason.SCAN_INCOMPLETE)
        limitations.append(
            assessment.explanation
            if unavailable
            else (
                "The scan is incomplete; this assessment uses only the available "
                "supported evidence."
            )
        )
    if evals.uncertain_source_files:
        limitations.append("Unavailable eval sources: " + ", ".join(evals.uncertain_source_files))
    unsupported = sorted(
        {warning.source_file for warning in evals.warnings if warning.code == "jsonl_unrecognized"}
    )
    if unsupported:
        reasons.append(CoverageReason.UNSUPPORTED_EVIDENCE_PATTERN)
        limitations.append("Unrecognized JSONL skipped: " + ", ".join(unsupported))
    return CoverageExplanation(
        behavior=behavior,
        qualifying_evidence_found=bool(assessment.matches),
        reason_codes=tuple(reasons),
        missing_dimensions=missing,
        closest_eval_id=closest.eval_id if closest is not None else None,
        scan_completeness=completeness,
        limitations=tuple(limitations),
    )
