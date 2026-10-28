"""Change-aware full-snapshot comparison, Git isolation, and CLI contracts."""

import json
import os
import subprocess
from pathlib import Path
from shutil import copy2, copytree
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.comparison import compare_repository, comparison_json
from agentguard.feedback import FindingStore
from agentguard.models import (
    BehaviorChangeStatus as Change,
)
from agentguard.models import (
    BehaviorType,
    CoverageStatus,
    FindingDisposition,
)
from agentguard.models import (
    VerificationDelta as Delta,
)
from agentguard.scanners.git_snapshot import (
    GitComparisonError,
    baseline_snapshot,
    resolve_git_context,
)

EXAMPLES = Path(__file__).parents[1] / "examples"
TOOL = "@tool\ndef lookup(key):\n    return key\n"
TEST = "def test_lookup():\n    assert lookup('a') == 'a'\n"


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("GIT_"):
            del env[name]
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Skout Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _write(tmp_path, "README.md", "Static test fixture.\n")
    _commit(tmp_path)
    return tmp_path


def _invocation(report):
    return next(
        c
        for c in report.changes
        if (
            (c.current_behavior or c.baseline_behavior).behavior_type
            is BehaviorType.TOOL_INVOCATION
        )
    )


def test_new_untracked_behavior_is_gap_and_baseline_is_empty(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    report = compare_repository(repo, "main")
    change = _invocation(report)
    assert change.change_status is Change.ADDED
    assert change.verification_delta is Delta.NEW_GAP
    assert change.current_assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert report.baseline_inventory.behavior_count == 0
    assert report.current_inventory.behavior_count == 1
    assert report.current_inventory.selected_finding_count == 1
    assert not (repo / ".agentguard").exists()


def test_new_behavior_with_new_eval_is_covered(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _write(repo, "tests/test_tool.py", TEST)
    change = _invocation(compare_repository(repo, "HEAD"))
    assert change.change_status is Change.ADDED
    assert change.verification_delta is Delta.ADDED_COVERED
    assert change.current_assessment.coverage_status is CoverageStatus.COVERED
    assert change.current_finding_id is None


def test_partial_new_evidence_retains_missing_outcome_dimension(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _write(repo, "tests/test_tool.py", "def test_lookup():\n    lookup('a')\n")
    change = _invocation(compare_repository(repo, "HEAD"))
    assert change.verification_delta is Delta.NEW_GAP
    assert change.current_assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert change.current_assessment.structured_explanation.missing_dimensions == (
        "expected_outcome",
    )


def test_eval_removed_regresses_unchanged_behavior(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _write(repo, "tests/test_tool.py", TEST)
    _commit(repo)
    (repo / "tests/test_tool.py").unlink()
    report = compare_repository(repo, "HEAD")
    change = _invocation(report)
    assert change.change_status is Change.UNCHANGED
    assert change.verification_delta is Delta.COVERAGE_REGRESSION
    assert change.baseline_assessment.coverage_status is CoverageStatus.COVERED
    assert change.current_assessment.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    assert report.eval_changes[0].change_status is Change.REMOVED


def test_eval_added_improves_unchanged_behavior(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    _write(repo, "tests/test_tool.py", TEST)
    report = compare_repository(repo, "HEAD")
    change = _invocation(report)
    assert change.change_status is Change.UNCHANGED
    assert change.verification_delta is Delta.COVERAGE_IMPROVEMENT
    assert report.eval_changes[0].change_status is Change.ADDED
    assert report.eval_changes[0].evidence_type.value == "automated_test"


@pytest.mark.parametrize(
    "new_threshold,update_eval,expected",
    [
        (250, False, Delta.MODIFIED_COVERED),
        (1000, False, Delta.COVERAGE_REGRESSION),
        (1000, True, Delta.MODIFIED_COVERED),
    ],
)
def test_threshold_edits_use_comparison_identity_and_actual_matching(
    repo: Path,
    new_threshold: int,
    update_eval: bool,
    expected: Delta,
) -> None:
    source = """@tool
def lookup(amount):
    if amount > 500:
        raise ValueError()
    return amount
"""
    tests = """def test_success():
    assert lookup(1) == 1
def test_failure():
    with pytest.raises(ValueError):
        lookup(700)
"""
    _write(repo, "agent.py", source)
    _write(repo, "tests/test_tool.py", tests)
    _commit(repo)
    _write(repo, "agent.py", source.replace("> 500", f"> {new_threshold}"))
    if update_eval:
        _write(repo, "tests/test_tool.py", tests.replace("700", "1700"))
    report = compare_repository(repo, "HEAD")
    failure = next(
        c
        for c in report.changes
        if c.current_behavior and (c.current_behavior.behavior_type is BehaviorType.TOOL_FAILURE)
    )
    assert failure.change_status is Change.MODIFIED
    assert failure.baseline_behavior.behavior_id != failure.current_behavior.behavior_id
    assert failure.verification_delta is expected
    assert failure.current_assessment.coverage_status is (
        CoverageStatus.PARTIALLY_COVERED
        if expected is Delta.COVERAGE_REGRESSION
        else CoverageStatus.COVERED
    )


@pytest.mark.parametrize(
    "changed_source",
    [
        "\n\n" + TOOL,
        "# unrelated comment\n" + TOOL,
        "@tool\ndef lookup(key):\n\n    # same result\n    return  key\n",
    ],
)
def test_whitespace_comments_and_line_shifts_do_not_modify(repo: Path, changed_source: str):
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    _write(repo, "agent.py", changed_source)
    change = _invocation(compare_repository(repo, "HEAD"))
    assert change.change_status is Change.UNCHANGED
    assert change.verification_delta is Delta.UNCHANGED_GAP
    assert change.baseline_behavior.behavior_id == change.current_behavior.behavior_id


def test_exact_unique_structural_move_is_not_a_new_gap(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    (repo / "agent.py").rename(repo / "moved.py")
    change = _invocation(compare_repository(repo, "HEAD"))
    assert change.change_status is Change.UNCHANGED
    assert change.verification_delta is Delta.UNCHANGED_GAP
    assert change.baseline_behavior.source_file == "agent.py"
    assert change.current_behavior.source_file == "moved.py"
    assert change.baseline_behavior.behavior_id != change.current_behavior.behavior_id


def test_rename_and_duplicate_move_candidates_are_uncertain(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    (repo / "agent.py").unlink()
    _write(repo, "one.py", TOOL)
    _write(repo, "two.py", TOOL)
    report = compare_repository(repo, "HEAD")
    assert len(report.changes) == 3
    assert all(c.change_status is Change.IDENTITY_UNCERTAIN for c in report.changes)
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert report.summary["new_gaps"] == 0
    (repo / "two.py").unlink()
    _write(repo, "one.py", TOOL.replace("lookup", "renamed_lookup"))
    report = compare_repository(repo, "HEAD")
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)


def test_deleted_behavior_is_removed_not_resolved(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    (repo / "agent.py").unlink()
    change = _invocation(compare_repository(repo, "HEAD"))
    assert change.change_status is Change.REMOVED
    assert change.verification_delta is Delta.REMOVED_BEHAVIOR
    assert change.current_assessment is None


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_incomplete_snapshot_prevents_coverage_regression_claims(repo: Path, side: str):
    _write(repo, "agent.py", TOOL)
    _write(repo, "tests/test_tool.py", TEST if side == "current" else "def test_broken(:\n")
    _commit(repo)
    _write(repo, "tests/test_tool.py", "def test_broken(:\n" if side == "current" else TEST)
    report = compare_repository(repo, "HEAD")
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert report.summary["coverage_regressions"] == report.summary["coverage_improvements"] == 0
    assert any("python_syntax_error" in limit for limit in report.limitations)


@pytest.mark.parametrize(
    "name,content",
    [
        ("requirements.md", "lookup must work.\n"),
        ("guardrail.py", "def enforce(value):\n    return bool(value)\n"),
        ("quality.jsonl", '{"score": 1, "passed": true}\n'),
    ],
)
def test_nonqualifying_artifacts_do_not_improve_coverage(repo: Path, name: str, content: str):
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    _write(repo, name, content)
    report = compare_repository(repo, "HEAD")
    assert _invocation(report).verification_delta is Delta.UNCHANGED_GAP
    assert report.eval_changes == ()


def test_unsupported_helper_semantics_are_explicitly_limited(repo: Path) -> None:
    source = "@tool\ndef lookup(key):\n    return helper(key)\ndef helper(key):\n    return key\n"
    _write(repo, "agent.py", source)
    _commit(repo)
    _write(repo, "agent.py", source.replace("return key", "return None"))
    report = compare_repository(repo, "HEAD")
    assert _invocation(report).change_status is Change.UNCHANGED
    assert any("helper/import changes" in limit for limit in report.limitations)


def test_revision_forms_and_nested_scan_path(repo: Path) -> None:
    _write(repo, "nested/agent.py", TOOL)
    commit = _commit(repo)
    _git(repo, "tag", "baseline-fixture")
    for revision in ("main", "HEAD", commit, "baseline-fixture"):
        report = compare_repository(repo / "nested", revision)
        assert report.baseline.resolved_commit == commit
        assert report.baseline.scan_path == "nested"
        assert _invocation(report).baseline_behavior.source_file == "agent.py"
    assert compare_repository(repo / "nested", "HEAD~1").summary["added_behaviors"] == 1


@pytest.mark.parametrize("revision", ["does-not-exist", "--help", "HEAD:README.md", "HEAD\nHEAD"])
def test_invalid_revision_has_clear_nonzero_cli_error(repo: Path, revision: str):
    result = CliRunner().invoke(app, ["scan", str(repo), "--baseline", revision, "--json"])
    assert result.exit_code != 0
    assert json.loads(result.stdout)["error"]["code"] == "baseline_unavailable"
    assert not (repo / ".agentguard").exists()


def test_non_git_missing_and_file_paths_are_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "file.py", TOOL)
    for root in (tmp_path, tmp_path / "missing", tmp_path / "file.py"):
        with pytest.raises(GitComparisonError):
            compare_repository(root, "HEAD")


def test_config_excludes_cli_excludes_and_includes_apply_to_both_snapshots(repo: Path) -> None:
    _write(repo, "agentguard.toml", 'include = ["src/**/*.py"]\nexclude = ["src/vendor/**"]\n')
    for path in ("src/agent.py", "src/vendor/ignored.py", "src/temporary/ignored.py", "other.py"):
        _write(repo, path, TOOL)
    _commit(repo)
    report = compare_repository(repo, "HEAD", extra_excludes=("src/temporary/**",))
    assert report.baseline_inventory.behavior_count == report.current_inventory.behavior_count == 1
    assert _invocation(report).change_status is Change.UNCHANGED


def test_changed_scope_configuration_marks_absence_uncertain(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    _write(repo, "agentguard.toml", 'exclude = ["agent.py"]\n')
    report = compare_repository(repo, "HEAD")
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert any("configuration differs" in limit for limit in report.limitations)


def test_snapshots_cleanup_even_when_analysis_raises(repo: Path) -> None:
    context = resolve_git_context(repo, "HEAD")
    with pytest.raises(RuntimeError), baseline_snapshot(context) as snapshot:
        directory = snapshot.root
        assert directory.is_dir()
        raise RuntimeError("test cleanup")
    assert not directory.exists()


def test_no_hooks_filters_network_or_target_execution_and_no_source_writes(repo: Path):
    marker = repo.parent / f"{repo.name}-unexpected-execution"
    _write(repo, "agent.py", TOOL + f"\nopen({str(marker)!r}, 'w').write('BAD')\n")
    _write(repo, ".gitattributes", "*.py filter=evil\n")
    _commit(repo)
    hook = repo.parent / f"{repo.name}-hook.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(hook))
    _git(repo, "config", "filter.evil.smudge", str(hook))
    before = {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    commands = []
    original = subprocess.run

    def observe(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    with patch("agentguard.scanners.git_snapshot.subprocess.run", side_effect=observe):
        compare_repository(repo, "HEAD")
    assert commands
    for command in commands:
        assert command[command.index("-C") + 2] in {
            "rev-parse",
            "ls-tree",
            "cat-file",
            "ls-files",
            "config",
        }
        assert "core.fsmonitor=false" in command
    assert not marker.exists()
    assert before == {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()}


def test_existing_sqlite_feedback_history_and_metrics_are_untouched(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    runner = CliRunner()
    assert runner.invoke(app, ["scan", str(repo), "--no-progress"]).exit_code == 0
    store = FindingStore(repo)
    original = store.list_findings()[0]
    store.record_feedback(original.finding_id, FindingDisposition.ADD_EVAL)
    state = {p.name: p.read_bytes() for p in (repo / ".agentguard").iterdir() if p.is_file()}
    _write(repo, "tests/test_tool.py", TEST)
    first = compare_repository(repo, "HEAD")
    assert first == compare_repository(repo, "HEAD")
    assert _invocation(first).verification_delta is Delta.COVERAGE_IMPROVEMENT
    assert state == {
        p.name: p.read_bytes() for p in (repo / ".agentguard").iterdir() if p.is_file()
    }
    assert store.get_finding(original.finding_id).status.value == "open"
    assert runner.invoke(app, ["scan", str(repo), "--no-progress"]).exit_code == 0
    resolved = store.get_finding(original.finding_id)
    assert resolved.status.value == "resolved"
    assert resolved.current_disposition is FindingDisposition.ADD_EVAL
    state = store.database_path.read_bytes()
    compare_repository(repo, "HEAD")
    assert store.database_path.read_bytes() == state


def test_json_is_deterministic_excerpt_free_and_ordinary_flags_remain_separate(repo: Path):
    _write(repo, "agent.py", TOOL)
    runner = CliRunner()
    args = ["scan", str(repo), "--baseline", "HEAD", "--json"]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert first.output == runner.invoke(app, args).output
    data = json.loads(first.output)
    assert data["current_source"] == "working_tree"
    assert data["summary"]["new_gaps"] == 1
    assert '"excerpt"' not in first.output
    assert data["changes"][0]["current_behavior"]["evidence"][0]["start_line"] == 2
    assert data == comparison_json(compare_repository(repo, "HEAD"))
    assert runner.invoke(app, ["scan", str(repo), "--json"]).exit_code != 0
    assert not (repo / ".agentguard").exists()


@pytest.mark.parametrize(
    "directory,solution,target",
    [
        ("langgraph-agent", "evals/escalation_path.jsonl.example", "evals/escalation_path.jsonl"),
        ("crewai-agent", "tests/solutions/test_escalation.py.example", "tests/test_escalation.py"),
        ("pydantic-ai-agent", "tests/solutions/test_retry.py.example", "tests/test_retry.py"),
    ],
)
def test_framework_examples_improvement_and_genuine_added_tool_gap(
    repo: Path,
    directory: str,
    solution: str,
    target: str,
) -> None:
    root = repo / "example"
    copytree(EXAMPLES / directory, root)
    _commit(repo)
    initial = compare_repository(root, "HEAD")
    assert initial.summary["coverage_improvements"] == 0
    copy2(root / solution, root / target)
    improved = compare_repository(root, "HEAD")
    assert improved.summary["coverage_improvements"] >= 1
    source_file = {
        "langgraph-agent": "workflow.py",
        "crewai-agent": "crew.py",
        "pydantic-ai-agent": "agent.py",
    }[directory]
    decorator = "@refund_agent.tool_plain" if directory == "pydantic-ai-agent" else "@tool"
    addition = "\n\n"
    if directory == "langgraph-agent":
        addition += "from langchain_core.tools import tool\n\n"
    addition += (
        f"{decorator}\ndef escalate_unverified(case_id: str) -> str:\n"
        '    """Return the case selected for escalation."""\n    return case_id\n'
    )
    _write(root, source_file, (root / source_file).read_text() + addition)
    changed = compare_repository(root, "HEAD")
    added = next(
        c
        for c in changed.changes
        if c.current_behavior and (c.current_behavior.subject == "escalate_unverified")
    )
    assert added.verification_delta is Delta.NEW_GAP
    assert added.current_finding_id is not None
    assert not (root / ".agentguard").exists()


def test_jsonl_expected_removed_is_evidence_modification_and_partial_regression(repo: Path):
    _write(repo, "agent.py", TOOL)
    record = {"input": {"key": "a"}, "expected": "a", "metadata": {"tools": ["lookup"]}}
    _write(repo, "evals/check.jsonl", json.dumps(record) + "\n")
    _commit(repo)
    del record["expected"]
    _write(repo, "evals/check.jsonl", json.dumps(record) + "\n")
    report = compare_repository(repo, "HEAD")
    change = _invocation(report)
    assert change.verification_delta is Delta.COVERAGE_REGRESSION
    assert change.current_assessment.coverage_status is CoverageStatus.PARTIALLY_COVERED
    assert report.eval_changes[0].change_status is Change.MODIFIED
    assert report.eval_changes[0].evidence_type.value == "eval_case"


def test_supported_wrapper_matching_is_reused_without_failure_inference(repo: Path):
    _write(repo, "agent.py", TOOL)
    _write(
        repo, "tests/test_tool.py", "def test_lookup():\n    assert lookup.ainvoke('a') == 'a'\n"
    )
    report = compare_repository(repo, "HEAD")
    assert _invocation(report).verification_delta is Delta.ADDED_COVERED


def test_clean_snapshot_equality_and_removed_details_are_not_hidden_from_json(repo: Path):
    _write(repo, "agent.py", TOOL)
    _write(repo, "tests/test_tool.py", TEST)
    _commit(repo)
    report = compare_repository(repo, "HEAD")
    assert _invocation(report).verification_delta is Delta.UNCHANGED_COVERED
    assert report.eval_changes == ()
    assert report.summary["new_gaps"] == report.summary["modified_behaviors"] == 0
    human = CliRunner().invoke(app, ["scan", str(repo), "--baseline", "HEAD"])
    assert human.exit_code == 0
    assert "unchanged_covered:" not in human.output
    detailed = CliRunner().invoke(app, ["scan", str(repo), "--baseline", "HEAD", "--all-changes"])
    assert "unchanged_covered: lookup" in detailed.output


def test_oversized_snapshot_reports_uncertainty_and_cleans_up(repo: Path, monkeypatch):
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    monkeypatch.setattr("agentguard.scanners.git_snapshot.MAX_FILE_BYTES", 10)
    report = compare_repository(repo, "HEAD")
    assert report.summary["new_gaps"] == 0
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert any("size limit" in limit for limit in report.limitations)


def test_symlink_is_not_followed_or_recreated_and_exclusions_suppress_it(repo: Path):
    _write(repo, "agent.py", TOOL)
    (repo / "link.py").symlink_to(repo / "agent.py")
    _commit(repo)
    context = resolve_git_context(repo, "HEAD")
    with baseline_snapshot(context) as snapshot:
        assert not (snapshot.root / "link.py").exists()
        assert snapshot.limitations
    report = compare_repository(repo, "HEAD")
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    excluded = compare_repository(repo, "HEAD", extra_excludes=("link.py",))
    assert _invocation(excluded).verification_delta is Delta.UNCHANGED_GAP


def test_gitlink_submodule_is_explicitly_unsupported(repo: Path):
    _write(repo, "agent.py", TOOL)
    commit = _commit(repo)
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{commit},submodule")
    _git(repo, "commit", "-m", "gitlink fixture")
    report = compare_repository(repo, "HEAD")
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert any("160000" in limit for limit in report.limitations)
    assert any("submodule" in limit for limit in report.limitations)
    excluded = compare_repository(repo, "HEAD", extra_excludes=("submodule/**",))
    assert _invocation(excluded).verification_delta is Delta.UNCHANGED_GAP


def test_untracked_nested_git_repository_is_not_confidently_new_behavior(repo: Path):
    _write(repo, "nested/agent.py", TOOL)
    _git(repo / "nested", "init", "-b", "main")
    _commit(repo / "nested")
    report = compare_repository(repo, "HEAD")
    assert report.summary["new_gaps"] == 0
    assert all(c.verification_delta is Delta.UNCERTAIN for c in report.changes)
    assert any("Nested Git" in limit for limit in report.limitations)


def test_failed_configuration_is_reported_as_uncertain_and_cli_nonzero(repo: Path):
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    _write(repo, "agentguard.toml", "this isn't TOML")
    result = CliRunner().invoke(app, ["scan", str(repo), "--baseline", "HEAD", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["current_inventory"]["completeness"] == "failed"
    assert data["changes"][0]["verification_delta"] == "uncertain"
    assert not (repo / ".agentguard").exists()


@pytest.mark.parametrize(
    "directory,source",
    [
        ("langgraph-agent", "workflow.py"),
        ("crewai-agent", "crew.py"),
        ("pydantic-ai-agent", "agent.py"),
    ],
)
def test_framework_comment_changes_do_not_modify_behaviors(repo: Path, directory: str, source: str):
    root = repo / "example"
    copytree(EXAMPLES / directory, root)
    _commit(repo)
    path = root / source
    path.write_text("# a new comment\n\n" + path.read_text(), encoding="utf-8")
    report = compare_repository(root, "HEAD")
    assert report.changes
    assert all(c.change_status is Change.UNCHANGED for c in report.changes)


def test_binary_and_default_excluded_artifacts_follow_existing_discovery(repo: Path):
    _write(repo, "agent.py", TOOL)
    _write(repo, ".venv/ignored.py", TOOL)
    (repo / "binary.bin").write_bytes(bytes(range(256)))
    _commit(repo)
    report = compare_repository(repo, "HEAD")
    assert report.baseline_inventory.behavior_count == report.current_inventory.behavior_count == 1
    assert _invocation(report).verification_delta is Delta.UNCHANGED_GAP


def test_unborn_repository_has_no_available_baseline(tmp_path: Path):
    _git(tmp_path, "init", "-b", "main")
    with pytest.raises(GitComparisonError, match="baseline"):
        compare_repository(tmp_path, "HEAD")


def test_partial_clone_is_rejected_without_lazy_fetch(repo: Path) -> None:
    _git(repo, "config", "remote.origin.promisor", "true")
    _git(repo, "config", "remote.origin.url", "https://invalid.example/no-network")
    with pytest.raises(GitComparisonError, match="No fetch"):
        compare_repository(repo, "HEAD")


@pytest.mark.parametrize("operation", ["add", "remove_expected", "modify_expected"])
def test_pydantic_evals_evidence_deltas_use_supported_case_identity(repo: Path, operation: str):
    root = repo / "example"
    copytree(EXAMPLES / "pydantic-ai-agent", root)
    source = (root / "evals.py").read_text()
    if operation == "add":
        (root / "evals.py").unlink()
    _commit(repo)
    if operation == "remove_expected":
        source = source.replace(
            '    expected_output={"approved": True, "refund_amount": 125},\n', ""
        )
    elif operation == "modify_expected":
        source = source.replace('"approved": True', '"approved": False')
    _write(root, "evals.py", source)
    report = compare_repository(root, "HEAD")
    agent = next(
        c
        for c in report.changes
        if c.current_behavior and (c.current_behavior.source_type.value == "pydantic_ai_agent")
    )
    expected = {
        "add": Delta.COVERAGE_IMPROVEMENT,
        "remove_expected": Delta.COVERAGE_REGRESSION,
        "modify_expected": Delta.UNCHANGED_COVERED,
    }
    assert agent.verification_delta is expected[operation]
    case = next(c for c in report.eval_changes if c.source_type.value == "pydantic_eval")
    assert case.evidence_type.value == "eval_case"
    assert case.change_status is (Change.ADDED if operation == "add" else Change.MODIFIED)


def test_unmerged_index_entries_limit_comparison_without_modifying_the_index(repo: Path):
    _write(repo, "agent.py", TOOL)
    _commit(repo)
    blob = _git(repo, "rev-parse", "HEAD:agent.py")
    index_data = f"0 {'0' * len(blob)}\tagent.py\n" + "".join(
        f"100644 {blob} {stage}\tagent.py\n" for stage in (1, 2, 3)
    )
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--index-info"],
        input=index_data,
        capture_output=True,
        text=True,
        check=True,
    )
    index = (repo / ".git/index").read_bytes()
    report = compare_repository(repo, "HEAD")
    assert _invocation(report).verification_delta is Delta.UNCERTAIN
    assert any("Unmerged index" in limit for limit in report.limitations)
    assert index == (repo / ".git/index").read_bytes()


def test_reordered_scope_rules_do_not_create_uncertainty(repo: Path) -> None:
    _write(repo, "agent.py", TOOL)
    _write(repo, "agentguard.toml", 'include = ["**/*.py", "**/*.md"]\n')
    _commit(repo)
    _write(repo, "agentguard.toml", 'include = ["**/*.md", "**/*.py"]\n')
    assert _invocation(compare_repository(repo, "HEAD")).verification_delta is Delta.UNCHANGED_GAP
