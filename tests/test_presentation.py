"""Evidence-first terminal layout without changes to assessments, JSON or feedback."""

import json
import socket
import sqlite3
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from shutil import copytree, ignore_patterns

import pytest
from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.feedback import FindingStore
from agentguard.guidance import guidance_for_assessment
from agentguard.models import BehaviorAction, Finding, FindingDisposition
from agentguard.presentation import (
    display_ids,
    render_diagnostics,
    render_summary,
    view_for_assessment,
    view_for_finding,
)
from tools.behavior_audit.actionability_cases import load_cases
from tools.behavior_audit.presentation import BASELINE, capture, run_presentation_audit
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

CASES = load_cases()


def render(view, width=80, *, details=False, color=False):
    stream = StringIO()
    output = Console(
        file=stream,
        width=width,
        color_system="standard" if color else None,
        force_terminal=color,
        highlight=False,
    )
    render_summary(output, view)
    if details:
        render_diagnostics(output, view)
    return Text.from_ansi(stream.getvalue()).plain


@pytest.mark.parametrize("width", [60, 80, 100, 120])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.expectation["case_id"])
def test_primary_and_progressive_contexts(case, width):
    original = case.assessment.model_dump_json()
    view = view_for_assessment(case.assessment)
    expected_label = (
        "Inconclusive verification"
        if case.expectation["expected_uncertainty"]
        else {
            "potentially_uncovered": "Potential eval gap",
            "partially_covered": "Partial verification",
            "covered": "Qualifying verification evidence",
        }[case.assessment.coverage_status.value]
    )
    assert view.coverage == expected_label
    assert view.status == case.assessment.coverage_status
    assert view.confidence == case.assessment.confidence
    basic = render(view, width)
    detail = render(view, width, details=True)
    assert detail.startswith(basic)
    assert all(len(line) <= width for line in detail.splitlines())
    assert all(basic.count(section) == 1 for section in ["Behavior:", "Evidence:", "Next step:"])
    assert detail.count("Additional details") == 1
    assert detail.count("\nLimitations:\n") <= 1
    assert "Reasons:" not in detail
    assert "assessable_gap" not in basic and "potentially_uncovered" not in basic
    assert "Finding ID:" not in detail  # Assessment context is never a selected finding.
    assert case.assessment.model_dump_json() == original
    assert view.guidance == guidance_for_assessment(case.assessment)


def test_evidence_and_actions_are_the_original_closest_candidate_only():
    views = {c.expectation["case_id"]: view_for_assessment(c.assessment) for c in CASES}
    assert views["rejection_partial"].evidence[-1] == "Still missing: expected outcome"
    assert "condition" not in views["rejection_partial"].next_step
    assert "ValueError" in views["rejection_partial"].next_step
    assert "identity of this graph" in " ".join(views["graph_wrong_owner"].evidence)
    assert "ambiguous" in " ".join(views["graph_ambiguous"].evidence)
    assert "No qualifying" in views["no_candidates"].evidence[0]
    assert "Qualifying verification evidence was found" in views["rejection_covered"].evidence[0]
    assert "no missing verification step" in views["rejection_covered"].next_step
    for name in ["unsupported_dynamic", "incomplete_scan"]:
        assert views[name].coverage == "Inconclusive verification"
        assert "Review" in views[name].next_step
        assert "Target" not in views[name].next_step


@pytest.fixture
def example(tmp_path):
    root = tmp_path / "example"
    copytree(
        PROJECT_ROOT / "examples/pydantic-ai-agent",
        root,
        ignore=ignore_patterns(".agentguard", ".venv", "__pycache__"),
    )
    assert CliRunner().invoke(app, ["scan", str(root), "--no-progress"]).exit_code == 0
    return root


def test_single_cli_card_details_review_and_canonical_feedback(example):
    runner = CliRunner()
    store = FindingStore(example)
    finding = store.list_findings()[0]
    before = store.database_path.read_bytes()
    basic = runner.invoke(app, ["findings", "--repository", str(example)])
    detail = runner.invoke(app, ["findings", "--repository", str(example), "--details"])
    review = runner.invoke(app, ["review", "--repository", str(example)], input="skip\n")
    review_detail = runner.invoke(
        app, ["review", "--repository", str(example), "--details"], input="skip\n"
    )
    assert all(r.exit_code == 0 for r in [basic, detail, review, review_detail])
    assert "Finding ID      " not in basic.output
    assert "Finding: f232f8c4" in basic.output
    assert finding.finding_id not in basic.output
    assert finding.finding_id in detail.output
    primary = basic.output.split("Finding 1 of 1", 1)[1].split("Static evidence only.")[0]
    assert primary in detail.output and primary in review.output and primary in review_detail.output
    assert before == store.database_path.read_bytes()
    shortened = runner.invoke(
        app, ["feedback", "f232f8c4", "add_eval", "--repository", str(example)]
    )
    assert shortened.exit_code != 0
    classified = runner.invoke(
        app, ["feedback", finding.finding_id, "add_eval", "--repository", str(example)]
    )
    assert classified.exit_code == 0
    assert store.get_finding(finding.finding_id).current_disposition is FindingDisposition.ADD_EVAL


def test_short_ids_disambiguate_collisions(example):
    f = FindingStore(example).list_findings()[0]
    items = [
        f.model_copy(update={"finding_id": identity})
        for identity in [
            "finding_aaaaaaaa11111111",
            "finding_aaaaaaaa22222222",
            "finding_bbbbbbbb11111111",
        ]
    ]
    tokens = display_ids(items)
    assert len(set(tokens.values())) == 3
    assert tokens[items[0].finding_id] == "aaaaaaaa1"
    assert tokens[items[1].finding_id] == "aaaaaaaa2"
    assert tokens[items[2].finding_id] == "bbbbbbbb"


def test_legacy_persisted_payload_without_guidance(example):
    store = FindingStore(example)
    f = store.list_findings()[0]
    payload = f.model_dump_json(exclude={"structured_explanation", "guidance"})
    # Simulate an actual older saved record in this disposable database only.
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE findings SET payload=? WHERE finding_id=?", (payload, f.finding_id)
        )
    before = store.database_path.read_bytes()
    result = CliRunner().invoke(app, ["findings", "--repository", str(example), "--details"])
    assert result.exit_code == 0 and "Historical record" in result.output
    assert f.finding_id in result.output and "Saved explanation:" in result.output
    assert store.database_path.read_bytes() == before
    assert Finding.model_validate_json(payload).guidance is None


def test_unsupported_context_and_ansi_do_not_invent_rejection():
    assessment = CASES[0].assessment
    behavior = assessment.structured_explanation.behavior.model_copy(
        update={"action": BehaviorAction(kind="unsupported")}
    )
    changed = assessment.model_copy(
        update={
            "structured_explanation": assessment.structured_explanation.model_copy(
                update={"behavior": behavior}
            )
        }
    )
    view = view_for_assessment(changed)
    assert view.guidance is None and view.coverage == "Inconclusive verification"
    assert "rejection" not in view.title
    assert "Target" not in view.next_step
    assert render(view, color=True) == render(view)


def test_read_only_renderer_needs_no_network_subprocess_or_sqlite(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Renderer may not inspect repositories or execute code")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    assert render(view_for_assessment(CASES[0].assessment))


def test_before_after_json_and_guidance_are_exact():
    before = json.loads(BASELINE.read_text())
    after = capture()
    assert before["assessment_contexts"] == after["assessment_contexts"]
    for name, row in after["repositories"].items():
        for key in [
            "metrics",
            "scopes",
            "scoped_json",
            "technical_snapshot",
            "finding_ids",
            "read_only_views",
        ]:
            assert row[key] == before["repositories"][name][key], (name, key)
        assert row["read_only_views"]


def test_independent_presentation_audit_is_reproducible(tmp_path, monkeypatch):
    report = run_presentation_audit()
    assert all(row["numerator"] == row["denominator"] > 0 for row in report["metrics"].values())
    assert (
        serialize_report(report)
        == (PROJECT_ROOT / "docs/finding-presentation-audit.json").read_text()
    )
    temp_alias = tmp_path / "temp-alias"
    temp_alias.symlink_to(Path(tempfile.gettempdir()).resolve(), target_is_directory=True)
    monkeypatch.setattr(tempfile, "tempdir", str(temp_alias))
    assert serialize_report(report) == serialize_report(run_presentation_audit())
    assert report["human_comprehension"] == "not_evaluated"


def test_multiple_findings_are_all_reachable_and_shared_scope_stays_distinct():
    captured = capture()
    row = captured["repositories"]["multiple"]
    count = len(row["finding_ids"])
    assert count > 1
    text = row["commands"]["findings"]
    for index in range(1, count + 1):
        assert f"Finding {index} of {count}" in text
    assert text.count("Behavior:") == count
    scoped = captured["repositories"]["shared_scoped"]
    assert "Selected scope: app.py#alpha" in scoped["commands"]["scan"]
    assert "unknown open findings (not presented as in-scope)" in scoped["commands"]["scan"]
    assert "out_of_scope open findings (not presented as in-scope)" in scoped["commands"]["scan"]
    assert "unregistered" in scoped["commands"]["scan"]


@pytest.mark.parametrize("change", [{"assessment_available": False}, {"current_confidence": "low"}])
def test_historical_uncertainty_withholds_stale_test_action(example, change):
    stored = FindingStore(example).list_findings()[0]
    payload = stored.model_dump(mode="json")
    payload.pop("structured_explanation", None)
    payload.pop("guidance", None)
    payload.update(change)
    view = view_for_finding(Finding.model_validate(payload))
    assert view.coverage == "Inconclusive verification"
    assert view.next_step.startswith("Review")
    assert "Explicitly assert" not in view.next_step
