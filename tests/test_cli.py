"""Tests for the AgentGuard command-line foundation."""

import json
from importlib.metadata import version
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.feedback import FindingStore
from agentguard.models import (
    FeedbackReason,
    FindingDisposition,
    RepositoryMetadata,
    ScanCompleteness,
    ScanResult,
    ScanWarning,
    SkippedPath,
    SkipReason,
)
from agentguard.progress import ScanProgressReporter

runner = CliRunner()


def test_help_succeeds() -> None:
    result = runner.invoke(app, ["--help"])
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "Find potentially important AI-agent behaviors" in output
    assert "--version" in output


def test_review_help_describes_classification_and_repository_option() -> None:
    result = runner.invoke(app, ["review", "--help"])
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "Review and classify open findings that have not yet been classified." in output
    assert "--repository" in output

    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    assert "skout review --repository path/to/your-agent-repo" in readme
    assert "skout review ." not in readme

    feedback_help = Text.from_ansi(runner.invoke(app, ["feedback", "--help"]).output).plain
    assert "classification" in feedback_help
    assert "disposition" not in feedback_help


def test_bare_invocation_displays_help_and_succeeds() -> None:
    result = runner.invoke(app)
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "Usage:" in output
    assert "--help" in output


def test_version_matches_installed_package_metadata() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == version("skout-scan")


def test_unknown_command_is_a_usage_error() -> None:
    result = runner.invoke(app, ["unknown-command"])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_unknown_option_is_a_usage_error() -> None:
    result = runner.invoke(app, ["--unknown-option"])

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_scan_command_summarizes_valid_repository(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "def test_answer():\n    assert answer() == 42\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert f"Repository: {tmp_path}" in result.output
    assert "Status: complete" in result.output
    assert "python" in result.output
    assert "total" in result.output
    assert "Discovered evals" in result.output
    assert "pytest" in result.output
    assert "Eval parse warnings: 0" in result.output
    assert "Detected behaviors" in result.output
    assert "Behavior extraction warnings: 0" in result.output
    assert "Coverage assessments" in result.output
    assert "Candidate pairs considered:" in result.output


def test_scan_summary_breaks_down_open_findings_by_classification(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )

    unclassified = runner.invoke(app, ["scan", str(tmp_path)])

    assert unclassified.exit_code == 0
    assert "Open findings: 1" in unclassified.output
    assert "Awaiting classification: 1" in unclassified.output
    assert "Previously classified, unresolved: 0" in unclassified.output

    store = FindingStore(tmp_path)
    finding_id = store.list_findings()[0].finding_id
    store.record_feedback(finding_id, FindingDisposition.ADD_EVAL)

    classified = runner.invoke(app, ["scan", str(tmp_path)])

    assert classified.exit_code == 0
    assert "Open findings: 1" in classified.output
    assert "Awaiting classification: 0" in classified.output
    assert "Previously classified, unresolved: 1" in classified.output

    (tmp_path / "test_agent.py").write_text(
        "def test_archive_record():\n"
        "    result = archive_record('key')\n"
        "    assert result == 'key'\n",
        encoding="utf-8",
    )

    resolved = runner.invoke(app, ["scan", str(tmp_path)])

    assert resolved.exit_code == 0
    assert "Open findings: 0" in resolved.output
    assert "Awaiting classification: 0" in resolved.output
    assert "Previously classified, unresolved: 0" in resolved.output
    assert store.get_finding(finding_id).status.value == "resolved"


def test_scan_command_reports_all_major_progress_phases(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("@tool\ndef answer():\n    return 42\n", encoding="utf-8")

    result = runner.invoke(app, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert f"Scanning {tmp_path}" in result.output
    assert "Repository discovery complete" in result.output
    assert "Behavior extraction complete" in result.output
    assert "Eval extraction complete" in result.output
    assert "Behavior matching complete" in result.output
    assert "Findings update complete" in result.output


def test_scan_no_progress_suppresses_progress_but_keeps_summary(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("value = 1\n", encoding="utf-8")

    result = runner.invoke(app, ["scan", str(tmp_path), "--no-progress"])

    assert result.exit_code == 0
    assert "Scanning " not in result.output
    assert "Repository discovery complete" not in result.output
    assert f"Repository: {tmp_path}" in result.output
    assert "Status: complete" in result.output


def test_scan_repeatable_exclude_is_applied_without_mutating_config(tmp_path: Path) -> None:
    config_path = tmp_path / "agentguard.toml"
    config_path.write_text('exclude = ["vendor/**"]\n', encoding="utf-8")
    (tmp_path / "kept.py").write_text("value = 1\n", encoding="utf-8")
    for directory in ("vendor", "output", "generated"):
        path = tmp_path / directory
        path.mkdir()
        (path / "ignored.py").write_text("value = 1\n", encoding="utf-8")
    original = config_path.read_text(encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "scan",
            str(tmp_path),
            "--exclude",
            "output/**",
            "--exclude",
            "generated/**",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert "total" in result.output
    assert "1" in result.output
    assert config_path.read_text(encoding="utf-8") == original


def test_scan_and_doctor_help_expose_repeatable_exclude() -> None:
    scan_help = runner.invoke(app, ["scan", "--help"])
    doctor_help = runner.invoke(app, ["doctor", "--help"])

    assert scan_help.exit_code == 0
    assert doctor_help.exit_code == 0
    assert "--exclude" in scan_help.output
    assert "--exclude" in doctor_help.output
    assert "Repeat to exclude multiple paths" in scan_help.output


def test_non_tty_progress_is_plain_text_without_control_sequences(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text("value = 1\n", encoding="utf-8")

    result = runner.invoke(app, ["scan", str(tmp_path)])

    assert result.exit_code == 0
    assert "Discovering repository artifacts..." in result.output
    assert "\x1b[" not in result.output
    assert "\r" not in result.output


def test_interactive_progress_reports_start_and_completed_phase(tmp_path: Path) -> None:
    output = StringIO()
    progress = ScanProgressReporter(
        Console(file=output, force_terminal=True, color_system=None),
    )

    progress.start(tmp_path)
    with progress.phase("Discovering repository artifacts", "Repository discovery"):
        pass
    progress.complete(
        "Repository discovery",
        ScanCompleteness.COMPLETE,
        detail="3 artifacts",
    )

    rendered = output.getvalue()
    assert f"Scanning {tmp_path}" in rendered
    assert "Repository discovery complete — 3 artifacts" in rendered


def test_progress_phase_failure_stops_status_and_reports_failure() -> None:
    output = StringIO()
    progress = ScanProgressReporter(
        Console(file=output, force_terminal=True, color_system=None),
    )

    with (
        pytest.raises(RuntimeError, match="phase failed"),
        progress.phase("Parsing eval scenarios", "Eval extraction"),
    ):
        raise RuntimeError("phase failed")
    progress.console.print("after failure")

    rendered = output.getvalue()
    assert "Eval extraction failed" in rendered
    assert "after failure" in rendered


def test_scan_command_rejects_nonexistent_repository(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    result = runner.invoke(app, ["scan", str(missing_path)])

    assert result.exit_code != 0
    assert "Repository path does not exist" in result.output
    assert "Repository discovery failed" in result.output
    assert "Status: failed" in result.output


def test_scan_command_rejects_file_path(tmp_path: Path) -> None:
    file_path = tmp_path / "file.py"
    file_path.touch()

    result = runner.invoke(app, ["scan", str(file_path)])

    assert result.exit_code != 0
    assert "Repository path is not a directory" in result.output
    assert "Status: failed" in result.output


def test_scan_command_displays_warning_path_literally(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scan_result = ScanResult(
        repository=RepositoryMetadata(requested_path="repository", root=str(tmp_path)),
        skipped=(SkippedPath(path="nested/link.py", reason=SkipReason.UNSUPPORTED),),
        warnings=(
            ScanWarning(
                code="symlink_unsupported",
                message="Symbolic links are not followed during repository discovery.",
                path="nested/link.py",
            ),
        ),
        completeness=ScanCompleteness.INCOMPLETE,
    )
    monkeypatch.setattr("agentguard.cli.scan_repository", lambda _, **__: scan_result)

    result = runner.invoke(app, ["scan", "repository"])

    assert result.exit_code == 0
    assert "[nested/link.py]" in result.output
    assert "Repository discovery incomplete" in result.output
    assert "Repository discovery complete" not in result.output


def test_findings_feedback_and_confirm_impact_commands(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )
    scan_result = runner.invoke(app, ["scan", str(tmp_path)])
    assert scan_result.exit_code == 0

    findings_result = runner.invoke(app, ["findings", "--repository", str(tmp_path)])
    assert findings_result.exit_code == 0
    store = FindingStore(tmp_path)
    finding_id = store.list_findings()[0].finding_id
    assert finding_id in findings_result.output
    assert "Suggested scenario:" in findings_result.output

    feedback_result = runner.invoke(
        app,
        ["feedback", finding_id, "add_eval", "--repository", str(tmp_path)],
    )
    impact_result = runner.invoke(
        app,
        ["confirm-impact", finding_id, "--repository", str(tmp_path)],
    )

    assert feedback_result.exit_code == 0
    assert "Recorded add_eval" in feedback_result.output
    assert impact_result.exit_code == 0
    assert "Confirmed impact" in impact_result.output
    assert store.get_finding(finding_id).confirmed_impact


def test_cross_repository_scan_writes_only_target_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_repository = tmp_path / "tool"
    target_repository = tmp_path / "target"
    tool_repository.mkdir()
    target_repository.mkdir()
    sentinel = target_repository / "executed"
    (target_repository / "agent.py").write_text(
        f"Path({str(sentinel)!r}).touch()\n\n@tool\ndef archive_record(key):\n    return key\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tool_repository)

    result = runner.invoke(app, ["scan", str(target_repository)])

    assert result.exit_code == 0
    assert (target_repository / ".agentguard" / "agentguard.db").is_file()
    assert not (tool_repository / ".agentguard").exists()
    assert not sentinel.exists()


def test_scan_explains_zero_candidate_pairs(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef lookup(key):\n    return key\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_unrelated.py").write_text(
        "def test_unrelated():\n    assert unrelated()\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["scan", str(tmp_path), "--no-progress"])

    assert result.exit_code == 0
    assert "Candidate pairs considered: 0" in result.output
    assert "No deterministic behavior-to-eval candidate pairs were found." in result.output
    assert "Do not interpret zero candidate pairs as complete coverage." in result.output


def test_review_command_persists_interactive_disposition_and_reason(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["scan", str(tmp_path)]).exit_code == 0

    result = runner.invoke(
        app,
        ["review", "--repository", str(tmp_path)],
        input="already_covered\nfixture_indirection\n",
    )

    assert result.exit_code == 0
    assert "Source evidence:" in result.output
    assert "Suggested eval:" in result.output
    assert "Review complete: 1 recorded, 0 skipped." in result.output
    finding = FindingStore(tmp_path).list_findings()[0]
    assert finding.current_disposition is FindingDisposition.ALREADY_COVERED
    assert finding.current_feedback_reason is FeedbackReason.FIXTURE_INDIRECTION


def test_review_command_can_skip_without_persisting_feedback(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["scan", str(tmp_path)]).exit_code == 0

    result = runner.invoke(
        app,
        ["review", "--repository", str(tmp_path)],
        input="skip\n",
    )

    assert result.exit_code == 0
    assert "Review complete: 0 recorded, 1 skipped." in result.output
    assert FindingStore(tmp_path).list_findings()[0].current_disposition is None


def test_review_empty_state_uses_unclassified_terminology(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["scan", str(tmp_path)]).exit_code == 0
    store = FindingStore(tmp_path)
    store.record_feedback(store.list_findings()[0].finding_id, FindingDisposition.ADD_EVAL)

    result = runner.invoke(app, ["review", "--repository", str(tmp_path)])

    assert result.exit_code == 0
    assert "No open, unclassified findings to review." in result.output


def test_metrics_command_human_and_json_output(tmp_path: Path) -> None:
    (tmp_path / "agent.py").write_text(
        "@tool\ndef archive_record(key):\n    return key\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["scan", str(tmp_path)]).exit_code == 0
    store = FindingStore(tmp_path)
    finding_id = store.list_findings()[0].finding_id
    store.record_feedback(finding_id, FindingDisposition.ADD_EVAL)

    human = runner.invoke(app, ["metrics", "--repository", str(tmp_path)])
    machine = runner.invoke(app, ["metrics", "--repository", str(tmp_path), "--json"])

    assert human.exit_code == 0
    assert "valid_gap_rate" in human.output
    assert "100.0%" in human.output
    assert "Observed resolution does not establish" in human.output
    assert machine.exit_code == 0
    payload = json.loads(machine.output)
    assert payload["summary"]["reviewed_finding_count"] == 1
    assert "source_evidence" not in payload["findings"][0]
