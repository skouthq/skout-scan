"""M11 explains existing decisions without changing selection, evidence or state."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from io import StringIO
from shutil import copy2, copytree, ignore_patterns

import pytest
from rich.console import Console
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.comparison import analyze_snapshot
from agentguard.feedback import FindingStore
from agentguard.findings import select_findings
from agentguard.guidance import (
    build_guidance,
    guidance_for_assessment,
    render_finding_guidance,
    with_guidance,
)
from agentguard.metrics import calculate_validation_summary
from agentguard.models import (
    AssessmentAvailability,
    BehaviorAction,
    ConfidenceLevel,
    CoverageStatus,
    Finding,
    FindingDisposition,
    FindingStatus,
    ScanCompleteness,
)
from agentguard.scopes import scan_selected_scope
from tools.behavior_audit.actionability import run_actionability_audit
from tools.behavior_audit.actionability_cases import INVENTORY, load_cases
from tools.behavior_audit.rejection_provenance import compatibility_snapshot
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

CASES = load_cases()


@pytest.fixture
def example(tmp_path):
    root = tmp_path / "example"
    copytree(
        PROJECT_ROOT / "examples/pydantic-ai-agent",
        root,
        ignore=ignore_patterns(".agentguard", "__pycache__", ".venv"),
    )
    return root


def test_independent_guidance_audit_and_reproducibility():
    report = run_actionability_audit()
    for name, metric in report["metrics"].items():
        assert metric["denominator"] > 0
        assert metric["numerator"] == (
            0 if name == "unsupported_claim_rate" else metric["denominator"]
        )
    assert report["human_usefulness"] == "not_yet_validated"
    assert report["human_review"] == "pending"
    data = serialize_report(report)
    assert data == serialize_report(run_actionability_audit())
    assert data == (PROJECT_ROOT / "docs/finding-actionability-audit.json").read_text()
    assert str(PROJECT_ROOT) not in data and '"excerpt"' not in data


def test_baseline_precedes_presentation_and_captures_real_old_contracts():
    baseline = json.loads((PROJECT_ROOT / INVENTORY.parent / "baseline.json").read_text())
    assert len(baseline["cases"]) == 19
    assert all("guidance" not in c["assessment"] for c in baseline["cases"])
    assert all("Next step:" not in c["cli"]["findings"] for c in baseline["cases"])
    for path, digest in baseline["technical_snapshots"].items():
        assert compatibility_snapshot(PROJECT_ROOT / path) == digest
    for name, digest in baseline["prior_reports"].items():
        assert hashlib.sha256((PROJECT_ROOT / "docs" / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.expectation["case_id"])
def test_guidance_preserves_each_assessment_and_its_exact_evidence(case):
    original = case.assessment.model_dump(mode="json")
    guidance = guidance_for_assessment(case.assessment)
    assert guidance is not None
    assert guidance.behavior_id == case.assessment.behavior_id
    assert guidance.observed_evidence == case.assessment.matches
    assert guidance.closest_eval_id == case.assessment.structured_explanation.closest_eval_id
    assert [g.dimension for g in guidance.missing_evidence] == list(
        case.assessment.structured_explanation.missing_dimensions
    )
    assert guidance == guidance_for_assessment(case.assessment)
    assert case.assessment.model_dump(mode="json") == original
    assert guidance.source_references
    assert [g.dimension.value for g in guidance.missing_evidence if g.suggested_action] == (
        case.expectation["allowed_actions"]
    )


def test_guidance_never_unions_or_reranks_candidates():
    case = next(c for c in CASES if c.expectation["case_id"] == "wrong_condition")
    other = next(c for c in CASES if c.expectation["case_id"] == "wrong_exception")
    original = case.assessment
    # Reordering supplied existing candidates cannot change the closest-candidate
    # decision or its missing dimensions, which belong to M8, not this renderer.
    assessment = original.model_copy(
        update={"matches": (*other.assessment.matches, *original.matches)}
    )
    g = guidance_for_assessment(assessment)
    assert g.closest_eval_id == original.structured_explanation.closest_eval_id
    assert g.observed_evidence == assessment.matches
    assert [x.dimension.value for x in g.missing_evidence] == ["condition"]
    assert "Assert" not in g.suggested_next_step


@pytest.mark.parametrize("reason", ["unavailable", "low_confidence", "incomplete", "failed"])
def test_uncertainty_never_becomes_a_strong_missing_test_claim(reason):
    case = next(c for c in CASES if c.expectation["case_id"] == "rejection_missing")
    a = case.assessment
    if reason == "unavailable":
        a = a.model_copy(update={"availability": AssessmentAvailability.UNAVAILABLE})
    elif reason == "low_confidence":
        a = a.model_copy(update={"confidence": ConfidenceLevel.LOW})
    else:
        detail = a.structured_explanation.model_copy(
            update={"scan_completeness": ScanCompleteness(reason)}
        )
        a = a.model_copy(update={"structured_explanation": detail})
    guidance = guidance_for_assessment(a)
    assert guidance.interpretation == "analysis_uncertain"
    assert "Review" in guidance.suggested_next_step
    assert not any(gap.suggested_action for gap in guidance.missing_evidence)
    if reason == "unavailable":
        assert guidance.missing_evidence == ()


def test_covered_assessment_is_context_not_an_instruction_to_add_tests():
    case = next(c for c in CASES if c.expectation["case_id"] == "rejection_covered")
    guidance = guidance_for_assessment(case.assessment)
    assert guidance.interpretation == "covered_context"
    assert guidance.missing_evidence == ()
    assert "no missing verification step" in guidance.suggested_next_step


@pytest.mark.parametrize(
    "case_id,reason",
    [
        ("graph_wrong_owner", "graph_owner_mismatch"),
        ("graph_ambiguous", "graph_owner_ambiguous"),
    ],
)
def test_graph_identity_actions_follow_original_owner_reason(case_id, reason):
    case = next(c for c in CASES if c.expectation["case_id"] == case_id)
    guidance = guidance_for_assessment(case.assessment)
    assert reason in guidance.reason_codes
    assert "validated explicit owner binding" in guidance.suggested_next_step
    assert [g.dimension.value for g in guidance.missing_evidence] == ["functionality"]
    assert "Assert the route" not in guidance.suggested_next_step
    assert ".invoke(" not in guidance.suggested_next_step


def test_unknown_or_historical_contract_abstains_instead_of_inventing_scenarios():
    assert build_guidance(None, (), None, "high") is None
    a = CASES[0].assessment
    behavior = a.structured_explanation.behavior.model_copy(
        update={"action": BehaviorAction(kind="unsupported")}
    )
    detail = a.structured_explanation.model_copy(update={"behavior": behavior})
    assert build_guidance(detail, a.matches, a.coverage_status, a.confidence) is None


def test_guidance_uses_declared_values_without_inventing_concrete_inputs():
    a = CASES[0].assessment
    guidance = guidance_for_assessment(a)
    assert "decision.refund_amount > 500" in guidance.suggested_next_step
    assert "ModelRetry" in guidance.suggested_next_step
    for invented in ["501", "refund(-1)", "pytest.fixture", "TestModel(", "api_key"]:
        assert invented not in guidance.suggested_next_step


def test_optional_guidance_never_changes_historical_payload_or_selection(example):
    full = analyze_snapshot(example)
    selected = select_findings(full.behaviors, full.matching)
    original = [f.model_dump(mode="json") for f in selected.findings]
    for finding in selected.findings:
        assert "guidance" not in finding.model_dump(mode="json")
        assert Finding.model_validate_json(finding.model_dump_json()) == finding
        presented = with_guidance(finding)
        assert presented.guidance is not None
        assert presented.model_dump(mode="json", exclude={"guidance"}) == finding.model_dump(
            mode="json"
        )
        assert Finding.model_validate_json(presented.model_dump_json()) == presented
    assert [f.model_dump(mode="json") for f in selected.findings] == original


def test_scoped_shared_guidance_is_identical_and_unknown_membership_stays_diagnostic(tmp_path):
    root = tmp_path / "shared"
    copytree(PROJECT_ROOT / "tests/fixtures/scope_audit/agents", root)
    first = scan_selected_scope(root, "alpha")
    second = scan_selected_scope(root, "beta")
    a = next(
        f
        for f in first.findings
        if f.behavior_subject == "shared" and f.behavior_type.value == "tool_failure"
    )
    b = next(f for f in second.findings if f.behavior_id == a.behavior_id)
    assert a.finding_id == b.finding_id and a.guidance == b.guidance
    assert a.structured_explanation.rejection_provenance.selected_owner_identity == "app.py#alpha"
    assert b.structured_explanation.rejection_provenance.selected_owner_identity == "app.py#beta"
    assert any(f.behavior_subject == "unregistered" for f in first.unknown_findings)
    assert not any(f.behavior_subject == "unregistered" for f in first.findings)
    assert all(f.guidance is None for f in FindingStore(root).list_findings())


def test_default_and_details_views_and_review_do_not_modify_database_or_metrics(example):
    runner = CliRunner()
    assert runner.invoke(app, ["scan", str(example), "--no-progress"]).exit_code == 0
    store = FindingStore(example)
    before_findings = store.list_findings()
    before_metrics = calculate_validation_summary(store)
    database = example / ".agentguard/agentguard.db"
    before_bytes = database.read_bytes()
    default = runner.invoke(app, ["findings", "--repository", str(example)])
    detailed = runner.invoke(app, ["findings", "--repository", str(example), "--details"])
    assert default.exit_code == detailed.exit_code == 0
    assert "Next step:" in default.output and "ModelRetry" in default.output
    assert "Source evidence:" not in default.output
    assert (
        "Source evidence:" in detailed.output
        and "Additional details" in detailed.output
        and "raises ModelRetry" in detailed.output
    )
    review = runner.invoke(app, ["review", "--repository", str(example)], input="skip\n" * 20)
    assert review.exit_code == 0 and "Next step:" in review.output
    assert "add_eval" in review.output and "suppressed" in review.output
    assert store.list_findings() == before_findings
    assert calculate_validation_summary(store) == before_metrics
    assert database.read_bytes() == before_bytes


def test_scoped_json_is_additive_and_reference_only(example):
    runner = CliRunner()
    result = runner.invoke(app, ["scan", str(example), "--scope", "refund_agent", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    finding = next(f for f in report["findings"] if f["behavior_subject"] == "validate_refund")
    g = finding["guidance"]
    assert g["finding_id"] == finding["finding_id"]
    assert g["behavior_id"] == finding["behavior_id"]
    assert '"excerpt"' not in result.output
    exported = runner.invoke(app, ["metrics", "--repository", str(example), "--json"])
    assert exported.exit_code == 0
    assert "guidance" in json.loads(exported.output)["findings"][0]
    assert '"excerpt"' not in exported.output
    assert (
        '"guidance"'
        not in FindingStore(example).get_finding(finding["finding_id"]).model_dump_json()
    )
    assert runner.invoke(app, ["scan", str(example), "--json"]).exit_code != 0
    assert (
        runner.invoke(
            app, ["scan", str(example), "--scope", "refund_agent", "--baseline", "HEAD"]
        ).exit_code
        != 0
    )


def test_guidance_and_review_preserve_resolution_feedback_and_explicit_impact(example):
    runner = CliRunner()
    first = scan_selected_scope(example, "refund_agent")
    finding = next(f for f in first.findings if f.behavior_subject == "validate_refund")
    store = FindingStore(example)
    store.record_feedback(finding.finding_id, FindingDisposition.ADD_EVAL)
    history = store.history(finding.finding_id)
    assert runner.invoke(app, ["findings", "--repository", str(example)]).exit_code == 0
    copy2(example / "tests/solutions/test_retry.py.example", example / "tests/test_retry.py")
    scan_selected_scope(example, "refund_agent")
    after = store.get_finding(finding.finding_id)
    assert (
        after.status is FindingStatus.RESOLVED and after.coverage_status is CoverageStatus.COVERED
    )
    assert after.current_disposition is FindingDisposition.ADD_EVAL
    assert after.observed_resolution and not after.confirmed_impact
    assert all(event in store.history(finding.finding_id) for event in history)
    assert with_guidance(after).guidance.interpretation == "covered_context"


def test_narrow_terminal_keeps_behavior_evidence_action_and_identity(example):
    view = scan_selected_scope(example, "refund_agent")
    finding = next(f for f in view.findings if f.behavior_subject == "validate_refund")
    stream = StringIO()
    output = Console(file=stream, width=50, color_system=None)
    output.print(finding.finding_id, markup=False)
    assert render_finding_guidance(output, finding)
    text = stream.getvalue()
    assert finding.finding_id in text
    assert "validate_refund" in text and "ModelRetry" in text
    assert "Evidence:" in text and "Next step:" in text
    assert "agent.py:" in text and "…" not in text


def test_audit_never_uses_network_subprocess_or_sqlite(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network, target execution or state access permitted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert run_actionability_audit()["metrics"]["unsupported_claim_rate"]["numerator"] == 0


def test_audit_checks_claims_against_source_not_only_expected_text(monkeypatch):
    original = json.loads

    def wrong_expectation(text, *args, **kwargs):
        parsed = original(text, *args, **kwargs)
        if isinstance(parsed, dict) and parsed.get("audit") == "finding-actionability-v1":
            parsed["cases"][0]["expected_facts"]["outcome"] = "InventedException"
        return parsed

    monkeypatch.setattr(json, "loads", wrong_expectation)
    result = run_actionability_audit()
    assert result["metrics"]["unsupported_claim_rate"]["numerator"] > 0
    assert (
        result["metrics"]["factual_correctness"]["numerator"]
        < result["metrics"]["factual_correctness"]["denominator"]
    )


def test_source_fact_order_does_not_change_guidance_or_input(case=CASES[0]):
    a = case.assessment
    detail = a.structured_explanation
    reversed_refs = detail.behavior.model_copy(
        update={"evidence": tuple(reversed(detail.behavior.evidence))}
    )
    equivalent = a.model_copy(
        update={"structured_explanation": detail.model_copy(update={"behavior": reversed_refs})}
    )
    assert guidance_for_assessment(equivalent) == guidance_for_assessment(a)
