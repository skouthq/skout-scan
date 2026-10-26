"""M8 evidence categories, explanations, and backward-compatible lifecycle contracts."""

import json
import sqlite3
from pathlib import Path
from shutil import copy2, copytree

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.feedback import FindingStore
from agentguard.findings import select_findings, update_findings
from agentguard.matchers import match_behaviors_to_evals
from agentguard.metrics import export_validation_data
from agentguard.models import (
    AssessmentAvailability,
    BehaviorCoverageAssessment,
    BehaviorExtractionResult,
    BehaviorType,
    ConfidenceLevel,
    CoverageDimension,
    CoverageReason,
    CoverageStatus,
    EvalParseResult,
    EvalScenario,
    EvalSourceType,
    Finding,
    FindingDisposition,
    FindingStatus,
    MatchingResult,
    ScanCompleteness,
    VerificationEvidence,
    VerificationEvidenceType,
)
from agentguard.scanners import scan_repository

EXAMPLES = Path(__file__).parents[1] / "examples"
TOOL = """@tool
def lookup(key):
    if not key:
        raise ValueError('key required')
    return key
"""


def _write(root: Path, path: str, source: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _analyze(
    root: Path,
) -> tuple[BehaviorExtractionResult, EvalParseResult, MatchingResult]:
    scan = scan_repository(root)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(scan)
    return behaviors, evals, match_behaviors_to_evals(behaviors, evals)


def _invocation(matching: MatchingResult) -> BehaviorCoverageAssessment:
    return next(
        assessment
        for assessment in matching.assessments
        if assessment.structured_explanation is not None
        and assessment.structured_explanation.behavior.behavior_type is BehaviorType.TOOL_INVOCATION
    )


def test_supported_sources_are_typed_and_legacy_scenarios_infer_category(tmp_path: Path) -> None:
    copytree(EXAMPLES / "pydantic-ai-agent", tmp_path / "example")
    root = tmp_path / "example"
    _write(root, "evals/case.jsonl", '{"input": "refund", "expected": "accepted"}\n')
    _, evals, _ = _analyze(root)
    assert {s.source_type for s in evals.scenarios} == set(EvalSourceType)
    for scenario in evals.scenarios:
        expected = (
            VerificationEvidenceType.AUTOMATED_TEST
            if scenario.source_type is EvalSourceType.PYTEST
            else VerificationEvidenceType.EVAL_CASE
        )
        assert scenario.evidence_type is expected
        assert scenario.qualifies_for_matching
        legacy = scenario.model_dump(mode="json", exclude={"evidence_type"})
        restored = EvalScenario.model_validate(legacy)
        assert restored == scenario
    assert _analyze(root)[1] == evals


@pytest.mark.parametrize(
    "category",
    [
        VerificationEvidenceType.RUNTIME_GUARDRAIL,
        VerificationEvidenceType.QUALITY_OBSERVATION,
        VerificationEvidenceType.REQUIREMENT,
    ],
)
def test_nonqualifying_categories_cannot_cover_or_resolve(
    tmp_path: Path, category: VerificationEvidenceType
) -> None:
    _write(tmp_path, "agent.py", TOOL)
    behaviors, _, initial = _analyze(tmp_path)
    first = update_findings(tmp_path, behaviors, initial)
    _write(tmp_path, "tests/test_tool.py", "def test_lookup():\n    assert lookup('a') == 'a'\n")
    _, evals, supported = _analyze(tmp_path)
    assert _invocation(supported).coverage_status is CoverageStatus.COVERED
    # Construct future category fixtures; no extractor for these is being claimed.
    typed_evidence = evals.model_copy(
        update={
            "scenarios": tuple(
                s.model_copy(update={"evidence_type": category}) for s in evals.scenarios
            )
        }
    )
    matching = match_behaviors_to_evals(behaviors, typed_evidence)
    assessment = _invocation(matching)
    assert assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert assessment.candidate_count == 0
    assert not assessment.structured_explanation.qualifying_evidence_found
    assert CoverageReason.NO_QUALIFYING_EVIDENCE in assessment.structured_explanation.reason_codes
    second = update_findings(tmp_path, behaviors, matching)
    assert {f.finding_id for f in second.findings} == {f.finding_id for f in first.findings}
    assert all(
        f.status is FindingStatus.OPEN and not f.observed_resolution for f in second.findings
    )


@pytest.mark.parametrize(
    "record",
    [
        '{"input": {"key": "a"}, "metadata": {"tools": ["lookup"]}}',
        '{"input": {"key": "a"}, "expected": "a", "metadata": {"tools": ["lookup"]}}',
    ],
)
def test_jsonl_category_does_not_replace_outcome_requirement(tmp_path: Path, record: str) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(tmp_path, "evals/cases.jsonl", record + "\n")
    _, evals, matching = _analyze(tmp_path)
    assert evals.scenarios[0].evidence_type is VerificationEvidenceType.EVAL_CASE
    assessment = _invocation(matching)
    if '"expected"' in record:
        assert assessment.coverage_status is CoverageStatus.COVERED
        assert assessment.structured_explanation.missing_dimensions == ()
    else:
        assert assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
        assert assessment.structured_explanation.missing_dimensions == (
            CoverageDimension.EXPECTED_OUTCOME,
        )
        assert CoverageReason.EXPECTED_OUTCOME_NOT_MATCHED in (
            assessment.structured_explanation.reason_codes
        )


def test_unsupported_and_malformed_artifacts_are_not_guessed(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(tmp_path, "requirements.md", "lookup must work; all tests passed")
    _write(tmp_path, "guardrail.py", "def enforce(): return True\n")
    _write(tmp_path, "quality.jsonl", '{"score": 1, "passed": true}\n')
    _, evals, _ = _analyze(tmp_path)
    assert evals.scenarios == ()
    _write(tmp_path, "evals/broken.jsonl", '{"input": "a"}\n{not json}\n')
    _, evals, matching = _analyze(tmp_path)
    assert len(evals.scenarios) == 1
    assert any(w.code == "jsonl_malformed" for w in evals.warnings)
    assert evals.completeness is ScanCompleteness.INCOMPLETE
    assessment = _invocation(matching)
    assert assessment.availability is AssessmentAvailability.UNAVAILABLE
    detail = assessment.structured_explanation
    assert detail.reason_codes == (CoverageReason.SCAN_INCOMPLETE,)
    assert detail.missing_dimensions == ()
    assert detail.scan_completeness is ScanCompleteness.INCOMPLETE
    assert "evals/broken.jsonl" in " ".join(detail.limitations)


def test_ambiguous_jsonl_retains_explicit_unsupported_limitation(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(tmp_path, "unknown.jsonl", '{"input": "a"}\n{"result": "unknown"}\n')
    _, evals, matching = _analyze(tmp_path)
    assert evals.scenarios == ()
    assert any(w.code == "jsonl_unrecognized" for w in evals.warnings)
    detail = _invocation(matching).structured_explanation
    assert CoverageReason.UNSUPPORTED_EVIDENCE_PATTERN in detail.reason_codes
    assert "unknown.jsonl" in " ".join(detail.limitations)


def test_source_backed_explanations_and_closest_candidate_dimensions(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(tmp_path, "tests/test_tool.py", "def test_lookup():\n    assert lookup('a') == 'a'\n")
    behaviors, evals, matching = _analyze(tmp_path)
    failure = next(
        a
        for a in matching.assessments
        if (a.structured_explanation.behavior.behavior_type is BehaviorType.TOOL_FAILURE)
    )
    detail = failure.structured_explanation
    assert failure.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert set(detail.missing_dimensions) == {
        CoverageDimension.CONDITION,
        CoverageDimension.EXPECTED_OUTCOME,
    }
    assert set(detail.reason_codes) == {
        CoverageReason.PARTIAL_DIMENSION_MATCH,
        CoverageReason.CONDITION_NOT_MATCHED,
        CoverageReason.EXPECTED_OUTCOME_NOT_MATCHED,
    }
    assert detail.behavior in behaviors.behaviors
    assert detail.closest_eval_id == evals.scenarios[0].eval_id
    match = failure.matches[0]
    assert match.source_file == evals.scenarios[0].source_file
    assert match.source_symbol == "test_lookup"
    assert match.source_evidence == evals.scenarios[0].evidence
    for evidence in (*detail.behavior.evidence, *match.source_evidence):
        lines = (tmp_path / evidence.source_file).read_text().splitlines()
        assert 1 <= evidence.start_line <= len(lines)
        assert evidence.excerpt in "\n".join(lines[evidence.start_line - 1 : evidence.end_line])
    assert "were not executed" in " ".join(detail.limitations)
    assert _analyze(tmp_path)[2] == matching


def test_no_candidate_finding_has_behavior_context_and_supported_absence_language(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agent.py", TOOL)
    behaviors, _, matching = _analyze(tmp_path)
    findings = select_findings(behaviors, matching).findings
    assert findings
    for finding in findings:
        detail = finding.structured_explanation
        assert detail.behavior.behavior_id == finding.behavior_id
        assert detail.behavior.source_file == "agent.py"
        assert detail.behavior.evidence
        assert CoverageReason.NO_QUALIFYING_EVIDENCE in detail.reason_codes
        assert not detail.qualifying_evidence_found
        assert finding.explanation == (
            "No sufficient matching eval evidence was discovered in the supported scan."
        )


def test_dimensions_from_separate_candidates_do_not_imply_full_coverage(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(
        tmp_path,
        "tests/test_tool.py",
        """def test_condition():
    lookup('')

def test_other_condition():
    with pytest.raises(ValueError):
        lookup('a')
""",
    )
    _, _, matching = _analyze(tmp_path)
    failure = next(
        a
        for a in matching.assessments
        if (a.structured_explanation.behavior.behavior_type is BehaviorType.TOOL_FAILURE)
    )
    assert failure.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert failure.structured_explanation.missing_dimensions
    assert all(match.missing_dimensions for match in failure.matches)
    assert failure.structured_explanation.closest_eval_id in {m.eval_id for m in failure.matches}


def test_findings_cli_and_excerpt_free_json_export(tmp_path: Path) -> None:
    copytree(EXAMPLES / "pydantic-ai-agent", tmp_path / "example")
    root = tmp_path / "example"
    runner = CliRunner()
    assert runner.invoke(app, ["scan", str(root)]).exit_code == 0
    result = runner.invoke(app, ["findings", "--repository", str(root)])
    assert result.exit_code == 0
    assert "no_qualifying_evidence" in result.output
    assert "Missing dimensions" in result.output
    assert "validate_refund" in result.output
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    assert runner.invoke(app, ["scan", str(root)]).exit_code == 0
    result = runner.invoke(app, ["findings", "--repository", str(root)])
    assert "automated_test" in result.output
    assert "tests/test_retry.py" in result.output
    assert "sufficient_matching_evidence" in result.output
    exported = runner.invoke(app, ["metrics", "--repository", str(root), "--json"])
    assert exported.exit_code == 0
    finding = json.loads(exported.output)["findings"][0]
    assert finding["coverage_status"] == "covered"
    assert finding["structured_explanation"]["reason_codes"] == ["sufficient_matching_evidence"]
    assert finding["verification_evidence"][0]["evidence_type"] == "automated_test"
    assert '"excerpt":' not in exported.output
    assert "raise ModelRetry" not in exported.output


def test_legacy_sqlite_feedback_survives_resolution_with_additive_explanations(
    tmp_path: Path,
) -> None:
    copytree(EXAMPLES / "pydantic-ai-agent", tmp_path / "example")
    root = tmp_path / "example"
    behaviors, _, matching = _analyze(root)
    finding = update_findings(root, behaviors, matching).findings[0]
    store = FindingStore(root)
    store.record_feedback(finding.finding_id, FindingDisposition.ADD_EVAL)
    # Emulate the pre-M8 payload, in a real SQLite database with existing events.
    legacy = store.get_finding(finding.finding_id).model_dump(mode="json")
    del legacy["structured_explanation"]
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("UPDATE findings SET payload = ?", (json.dumps(legacy),))
        schema_before = connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert store.get_finding(finding.finding_id).structured_explanation is None
    assert Finding.model_validate(legacy).finding_id == finding.finding_id
    history_before = store.history(finding.finding_id)
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    behaviors, _, matching = _analyze(root)
    update_findings(root, behaviors, matching)
    resolved = store.get_finding(finding.finding_id)
    assert resolved.status is FindingStatus.RESOLVED
    assert resolved.coverage_status is CoverageStatus.COVERED
    assert resolved.current_disposition is FindingDisposition.ADD_EVAL
    assert resolved.observed_resolution and not resolved.confirmed_impact
    assert resolved.structured_explanation.reason_codes == (
        CoverageReason.SUFFICIENT_MATCHING_EVIDENCE,
    )
    assert any(m.source_file == "tests/test_retry.py" for m in resolved.matched_eval_evidence)
    assert resolved.resolution_evidence.matched_eval_ids == resolved.matched_eval_ids
    assert store.feedback_events(finding.finding_id)[0].disposition is FindingDisposition.ADD_EVAL
    assert all(event in store.history(finding.finding_id) for event in history_before)
    assert export_validation_data(store)["findings"][0]["structured_explanation"]
    with sqlite3.connect(store.database_path) as connection:
        assert (
            connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
            == schema_before
        )


def test_legacy_match_payloads_keep_ids_and_unknown_locations(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    _write(tmp_path, "tests/test_tool.py", "def test_lookup():\n    assert lookup('a') == 'a'\n")
    _, evals, matching = _analyze(tmp_path)
    current = _invocation(matching)
    legacy = current.model_dump(mode="json", exclude={"structured_explanation"})
    additive_match_fields = {
        "evidence_type",
        "source_file",
        "source_symbol",
        "name",
        "source_evidence",
        "missing_dimensions",
    }
    for match in legacy["matches"]:
        for key in additive_match_fields:
            match.pop(key)
    restored = type(current).model_validate(legacy)
    assert restored.behavior_id == current.behavior_id
    assert restored.matched_eval_ids == (evals.scenarios[0].eval_id,)
    assert restored.matches[0].source_file is None
    assert restored.matches[0].evidence_type is None
    assert restored.structured_explanation is None


def test_incomplete_rescan_preserves_open_finding_and_feedback(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", TOOL)
    behaviors, _, matching = _analyze(tmp_path)
    initial = update_findings(tmp_path, behaviors, matching)
    store = FindingStore(tmp_path)
    for finding in initial.findings:
        store.record_feedback(finding.finding_id, FindingDisposition.ADD_EVAL)
    _write(tmp_path, "tests/test_broken.py", "def test_lookup(:\n    assert lookup('a')\n")
    behaviors, _, matching = _analyze(tmp_path)
    later = update_findings(tmp_path, behaviors, matching)
    assert later.resolved_count == 0
    for finding in later.findings:
        assert not finding.assessment_available
        assert finding.status is FindingStatus.OPEN
        assert finding.current_disposition is FindingDisposition.ADD_EVAL
        assert not finding.observed_resolution
        assert finding.structured_explanation.missing_dimensions == ()
        assert finding.structured_explanation.reason_codes == (CoverageReason.SCAN_INCOMPLETE,)


def test_repeated_and_reopened_findings_refresh_explanation_without_new_identity(
    tmp_path: Path,
) -> None:
    copytree(EXAMPLES / "pydantic-ai-agent", tmp_path / "example")
    root = tmp_path / "example"
    behaviors, _, matching = _analyze(root)
    first = update_findings(root, behaviors, matching).findings[0]
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    behaviors, _, matching = _analyze(root)
    second = update_findings(root, behaviors, matching).findings[0]
    third = update_findings(root, behaviors, matching).findings[0]
    assert third.structured_explanation == second.structured_explanation
    assert third.resolution_evidence == second.resolution_evidence
    (root / "tests/test_retry.py").unlink()
    behaviors, _, matching = _analyze(root)
    reopened = update_findings(root, behaviors, matching).findings[0]
    assert reopened.finding_id == first.finding_id
    assert reopened.status is FindingStatus.OPEN
    assert reopened.structured_explanation == first.structured_explanation
    assert reopened.matched_eval_evidence == ()


@pytest.mark.parametrize(
    "category",
    [
        VerificationEvidenceType.RUNTIME_GUARDRAIL,
        VerificationEvidenceType.QUALITY_OBSERVATION,
        VerificationEvidenceType.REQUIREMENT,
    ],
)
def test_future_evidence_needs_no_fictional_eval_source_and_is_not_an_eval(
    category: VerificationEvidenceType,
) -> None:
    evidence = VerificationEvidence(
        evidence_type=category,
        source_file="artifact.txt",
        name="Explicitly constructed future evidence",
        confidence=ConfidenceLevel.HIGH,
    )
    assert VerificationEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    # The generic record cannot enter the supported eval collection. Even an
    # eval-shaped record explicitly reclassified to this category is filtered
    # from matching (tested separately above).
    with pytest.raises(ValidationError):
        EvalParseResult.model_validate(
            {
                "scenarios": [evidence.model_dump()],
                "completeness": "complete",
            }
        )
