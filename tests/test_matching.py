"""Tests for deterministic behavior-to-eval matching."""

from pathlib import Path

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorType,
    CoverageStatus,
    EvalParseResult,
    ScanCompleteness,
)
from agentguard.scanners import scan_repository


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _analyze(
    root: Path,
) -> tuple[tuple[Behavior, ...], tuple[BehaviorCoverageAssessment, ...]]:
    scan_result = scan_repository(root)
    behaviors = extract_behaviors(scan_result)
    evals = parse_eval_artifacts(scan_result)
    matching = match_behaviors_to_evals(behaviors, evals)
    return behaviors.behaviors, matching.assessments


def _assessment_for(
    behaviors: tuple[Behavior, ...],
    assessments: tuple[BehaviorCoverageAssessment, ...],
    behavior_type: BehaviorType,
    *,
    action_target: str | None = None,
) -> BehaviorCoverageAssessment:
    behavior = next(
        item
        for item in behaviors
        if item.behavior_type is behavior_type
        and (action_target is None or (item.action and item.action.target == action_target))
    )
    return next(item for item in assessments if item.behavior_id == behavior.behavior_id)


def test_exact_tool_success_behavior_is_covered(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n    result = lookup('a')\n    assert result == 'found'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.confidence.value == "high"
    assert assessment.matches[0].evidence.same_subject
    assert assessment.matches[0].evidence.explicit_assertion


def test_tool_called_without_asserted_outcome_is_partial(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(tmp_path, "tests/test_agent.py", "def test_lookup():\n    lookup('a')\n")

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED


def test_tool_failure_is_covered_by_matching_pytest_raises(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        "@tool\ndef lookup(key):\n    if not key:\n        raise ValueError('key required')\n",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_missing_key():\n    with pytest.raises(ValueError):\n        lookup('')\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_FAILURE)

    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.matches[0].evidence.failure_matches
    assert assessment.matches[0].evidence.condition_matches
    branch = _assessment_for(behaviors, assessments, BehaviorType.CONDITIONAL_BRANCH)
    assert branch.coverage_status is CoverageStatus.COVERED


def test_success_test_does_not_cover_timeout_failure(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        """@tool
def lookup(payment_id):
    if payment_id == "timeout":
        return {"error": "provider timeout"}
    return {"status": "found"}
""",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n"
        "    result = lookup('payment-1')\n"
        "    assert result['status'] == 'found'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_FAILURE)

    assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert all(not match.evidence.failure_matches for match in assessment.matches)


def test_conditional_branch_with_matching_literal_and_action_is_covered(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "agent.py",
        """@tool
def refund(amount):
    if amount > 500:
        return manual_review(amount)
    return process_refund(amount)
""",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_large_refund():\n"
        "    result = refund(900)\n"
        "    assert result.route == 'manual_review'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(
        behaviors,
        assessments,
        BehaviorType.CONDITIONAL_BRANCH,
        action_target="manual_review",
    )

    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.matches[0].evidence.branch_matches


def test_neighboring_branch_is_only_partial(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        """@tool
def refund(amount):
    if amount > 500:
        return manual_review(amount)
    return process_refund(amount)
""",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_small_refund():\n"
        "    result = refund(25)\n"
        "    assert result.route == 'process_refund'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(
        behaviors,
        assessments,
        BehaviorType.CONDITIONAL_BRANCH,
        action_target="manual_review",
    )

    assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert all(not match.evidence.condition_matches for match in assessment.matches)


def test_escalation_action_is_covered_when_verified(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        """@tool
def refund(amount):
    if amount > 500:
        return handoff_to_human(amount)
    return process_refund(amount)
""",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_handoff():\n"
        "    result = refund(900)\n"
        "    assert result.route == 'handoff_to_human'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(
        behaviors,
        assessments,
        BehaviorType.ESCALATION,
        action_target="handoff_to_human",
    )

    assert assessment.coverage_status is CoverageStatus.COVERED


def test_jsonl_input_and_expected_can_cover_tool_invocation(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "cases.jsonl",
        '{"input":{"key":"a"},"expected":{"status":"found"},"metadata":{"tools":["lookup"]}}\n',
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.matches[0].evidence.expected_outcome_present


def test_input_only_jsonl_cannot_establish_covered_status(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "cases.jsonl",
        '{"input":{"key":"a"},"metadata":{"tools":["lookup"]}}\n',
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED


def test_same_keywords_on_unrelated_symbol_do_not_match(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef issue_refund(amount):\n    return amount\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_refund_label():\n"
        "    result = format_refund_label('refund')\n"
        "    assert result == 'refund'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert assessment.matched_eval_ids == ()


def test_no_candidate_is_potentially_uncovered(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef archive_record(key):\n    return key\n")

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert assessment.candidate_count == 0


def test_unrelated_incomplete_behavior_source_does_not_block_assessment(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(tmp_path, "broken.py", "def broken(:\n")
    scan_result = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan_result)
    evals = parse_eval_artifacts(scan_result)

    result = match_behaviors_to_evals(behaviors, evals)

    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert result.assessments[0].availability is AssessmentAvailability.AVAILABLE
    assert result.assessments[0].coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED


def test_non_eval_jsonl_does_not_make_matching_unavailable(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(tmp_path, "knowledge/memory.jsonl", '{"memory":"cached"}\n')
    scan_result = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan_result)
    evals = parse_eval_artifacts(scan_result)

    result = match_behaviors_to_evals(behaviors, evals)

    assert evals.completeness is ScanCompleteness.COMPLETE
    assert result.assessments[0].availability is AssessmentAvailability.AVAILABLE
    assert result.assessments[0].coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED


def test_incomplete_eval_source_only_blocks_assessments_without_verified_coverage(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "agent.py",
        "@tool\ndef lookup(key):\n    return key\n\n@tool\ndef archive(key):\n    return key\n",
    )
    _write(
        tmp_path,
        "evals/cases.jsonl",
        '{"input":"lookup","expected":"found","metadata":{"tools":["lookup"]}}\nnot json\n',
    )
    scan_result = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan_result)
    evals = parse_eval_artifacts(scan_result)

    result = match_behaviors_to_evals(behaviors, evals)
    by_id = {assessment.behavior_id: assessment for assessment in result.assessments}
    by_subject = {behavior.subject: by_id[behavior.behavior_id] for behavior in behaviors.behaviors}

    assert by_subject["lookup"].availability is AssessmentAvailability.AVAILABLE
    assert by_subject["lookup"].coverage_status is CoverageStatus.COVERED
    assert by_subject["archive"].availability is AssessmentAvailability.UNAVAILABLE
    assert by_subject["archive"].coverage_status is None


def test_behavior_uncertainty_is_scoped_to_named_behavior_ids(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        "@tool\ndef first():\n    return 1\n\n@tool\ndef second():\n    return 2\n",
    )
    extracted = extract_behaviors(scan_repository(tmp_path))
    uncertain = next(item for item in extracted.behaviors if item.subject == "second")
    scoped = extracted.model_copy(
        update={
            "unavailable_behavior_ids": (uncertain.behavior_id,),
            "completeness": ScanCompleteness.INCOMPLETE,
        }
    )

    result = match_behaviors_to_evals(
        scoped, EvalParseResult(completeness=ScanCompleteness.COMPLETE)
    )
    by_id = {assessment.behavior_id: assessment for assessment in result.assessments}

    assert by_id[uncertain.behavior_id].availability is AssessmentAvailability.UNAVAILABLE
    available_id = next(
        behavior.behavior_id for behavior in extracted.behaviors if behavior.subject == "first"
    )
    assert by_id[available_id].availability is AssessmentAvailability.AVAILABLE


def test_candidate_selection_records_reasons_and_avoids_cartesian_product(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    unrelated = "".join(
        f"def test_unrelated_{index}():\n    assert helper_{index}()\n\n" for index in range(100)
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        unrelated + "def test_lookup():\n    assert lookup('a') == 'a'\n",
    )
    scan_result = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan_result)
    evals = parse_eval_artifacts(scan_result)

    result = match_behaviors_to_evals(behaviors, evals)

    assert result.candidate_pair_count < result.behavior_count * result.eval_count
    assert result.candidate_pair_count >= 1
    reasons = result.assessments[0].matches[0].evidence.candidate_reasons
    assert "referenced_subject" in reasons


def test_matching_output_order_is_deterministic(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        "@tool\ndef zed():\n    return 1\n\n@tool\ndef alpha():\n    return 2\n",
    )
    scan_result = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan_result)
    evals = EvalParseResult(completeness=ScanCompleteness.COMPLETE)

    first = match_behaviors_to_evals(behaviors, evals)
    second = match_behaviors_to_evals(behaviors, evals)

    assert first == second
    assert [item.behavior_id for item in first.assessments] == sorted(
        item.behavior_id for item in first.assessments
    )
    assert not (tmp_path / ".agentguard").exists()


def test_failed_upstream_returns_explicit_matching_error() -> None:
    result = match_behaviors_to_evals(
        BehaviorExtractionResult(completeness=ScanCompleteness.FAILED),
        EvalParseResult(completeness=ScanCompleteness.FAILED),
    )

    assert result.completeness is ScanCompleteness.FAILED
    assert result.errors[0].code == "upstream_failed"


def test_tool_wrapper_invocation_with_assertion_can_cover_invocation(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n"
        "    result = lookup.ainvoke({'key': 'a'})\n"
        "    assert result == 'found'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.matches[0].evidence.same_subject


def test_tool_wrapper_invocation_without_verification_is_partial(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n    lookup.invoke({'key': 'a'})\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED


def test_tool_wrapper_success_does_not_cover_failure_behavior(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.py",
        "@tool\n"
        "def lookup(key):\n"
        "    if not key:\n"
        "        raise ValueError('key required')\n"
        "    return key\n",
    )
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n"
        "    result = lookup.coroutine({'key': 'a'})\n"
        "    assert result == 'a'\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    failure = _assessment_for(behaviors, assessments, BehaviorType.TOOL_FAILURE)

    assert failure.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert all(not match.evidence.failure_matches for match in failure.matches)


def test_non_tool_wrapper_receivers_do_not_match_known_tool(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return find(key)\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_clients():\n"
        "    first = unrelated_object.ainvoke({'key': 'a'})\n"
        "    second = lookup_client.ainvoke({'key': 'a'})\n"
        "    assert first and second\n",
    )

    behaviors, assessments = _analyze(tmp_path)
    assessment = _assessment_for(behaviors, assessments, BehaviorType.TOOL_INVOCATION)

    assert assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert assessment.matched_eval_ids == ()
