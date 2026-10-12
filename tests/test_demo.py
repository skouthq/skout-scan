"""Exercise the public demo scripts through the real installed CLI."""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentguard.extractors import parse_eval_artifacts
from agentguard.feedback import FindingStore
from agentguard.models import CoverageStatus, FindingDisposition, FindingStatus
from agentguard.scanners import scan_repository

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "demo" / "scripts"
EXAMPLE = ROOT / "examples" / "pydantic-ai-agent"


def _run(
    *args: str, cwd: Path = ROOT, check: bool = True, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("skout") or str(ROOT / ".venv" / "bin" / "skout")
    environment = {
        **os.environ,
        "PATH": f"{Path(executable).parent}{os.pathsep}{os.environ['PATH']}",
    }
    return subprocess.run(
        args,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=check,
        input=input_text,
    )


@pytest.fixture
def workspace() -> Iterator[Path]:
    prepared = _run("sh", str(SCRIPTS / "prepare_demo.sh"))
    root = Path(prepared.stdout.strip())
    assert root.name.startswith("skout-demo.")
    assert (root / ".skout-demo-owned").read_text().strip() == "skout-public-demo-v1"
    try:
        yield root
    finally:
        # This directory was freshly created by this test, never supplied by a user.
        shutil.rmtree(root)


def test_demo_real_cli_resolution_and_reset(workspace: Path) -> None:
    source_before = {p: p.read_bytes() for p in EXAMPLE.rglob("*") if p.is_file()}
    assert not (workspace / ".agentguard").exists()
    assert not (workspace / "tests/test_retry.py").exists()
    doctor = json.loads(_run("skout", "doctor", "--json", cwd=workspace).stdout)
    assert "Pydantic AI" in doctor["frameworks_detected"]
    assert not (workspace / ".agentguard").exists()
    first_output = _run("skout", "scan", ".", "--no-progress", cwd=workspace).stdout
    assert "Open findings: 1" in first_output
    first = FindingStore(workspace).list_findings()
    finding = next(
        f
        for f in first
        if f.behavior_subject == "validate_refund"
        and f.source_file == "agent.py"
        and any("ModelRetry" in evidence.excerpt for evidence in f.source_evidence)
    )
    assert finding.status is FindingStatus.OPEN
    assert finding.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
    database = workspace / ".agentguard/agentguard.db"
    database_inode = database.stat().st_ino
    review = _run("skout", "review", cwd=workspace, input_text="add_eval\n")
    assert "1 recorded, 0 skipped" in review.stdout
    classified = next(
        f for f in FindingStore(workspace).list_findings() if f.finding_id == finding.finding_id
    )
    assert classified.current_disposition is FindingDisposition.ADD_EVAL
    assert classified.status is FindingStatus.OPEN
    assert not classified.observed_resolution
    assert not (workspace / "tests/test_retry.py").exists()
    for _ in range(2):
        _run("sh", str(SCRIPTS / "enable_solution.sh"), str(workspace))
    assert (workspace / "tests/test_retry.py").read_bytes() == (
        EXAMPLE / "tests/solutions/test_retry.py.example"
    ).read_bytes()
    assert database.stat().st_ino == database_inode
    second_output = _run("skout", "scan", ".", "--no-progress", cwd=workspace).stdout
    assert "Open findings: 0" in second_output
    second = FindingStore(workspace).list_findings()
    assert {f.finding_id for f in second} == {f.finding_id for f in first}
    resolved = next(f for f in second if f.finding_id == finding.finding_id)
    assert resolved.status is FindingStatus.RESOLVED
    assert resolved.coverage_status is CoverageStatus.COVERED
    assert resolved.current_disposition is FindingDisposition.ADD_EVAL
    assert resolved.observed_resolution
    assert not resolved.confirmed_impact
    assert resolved.resolution_evidence is not None
    assert resolved.resolution_evidence.matched_eval_ids
    evals = parse_eval_artifacts(
        scan_repository(workspace),
        known_tool_names={"lookup_order"},
        known_agent_names={"refund_agent"},
    )
    assert any(
        scenario.source_file == "tests/test_retry.py"
        and scenario.eval_id in resolved.resolution_evidence.matched_eval_ids
        for scenario in evals.scenarios
    )
    evidence = _run(sys.executable, str(SCRIPTS / "show_resolution.py"), cwd=workspace).stdout
    assert finding.finding_id in evidence
    assert "Matched eval: tests/test_retry.py" in evidence
    details = _run("skout", "findings", cwd=workspace).stdout
    assert finding.finding_id in details
    assert "Observed resolution: yes" in details
    for _ in range(2):
        _run("sh", str(SCRIPTS / "reset_demo.sh"), str(workspace))
    assert not database.exists()
    assert not (workspace / "tests/test_retry.py").exists()
    assert (workspace / "agent.py").read_bytes() == (EXAMPLE / "agent.py").read_bytes()
    assert source_before == {p: p.read_bytes() for p in EXAMPLE.rglob("*") if p.is_file()}


def test_demo_scripts_refuse_unowned_paths_and_changed_tests(workspace: Path) -> None:
    for name in ("enable_solution.sh", "reset_demo.sh"):
        result = _run("sh", str(SCRIPTS / name), str(EXAMPLE), check=False)
        assert result.returncode != 0
        assert "Refusing a path" in result.stderr
    _run("sh", str(SCRIPTS / "enable_solution.sh"), str(workspace))
    target = workspace / "tests/test_retry.py"
    target.write_text("# User edits must be preserved\n")
    state = workspace / ".agentguard"
    state.mkdir()
    sentinel = state / "keep.txt"
    sentinel.write_text("preserve history on failed reset")
    for name in ("enable_solution.sh", "reset_demo.sh"):
        result = _run("sh", str(SCRIPTS / name), str(workspace), check=False)
        assert result.returncode != 0
    assert target.read_text() == "# User edits must be preserved\n"
    assert sentinel.exists()


def test_demo_reset_refuses_linked_state(workspace: Path, tmp_path: Path) -> None:
    (workspace / ".agentguard").symlink_to(tmp_path, target_is_directory=True)
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("unrelated")
    result = _run("sh", str(SCRIPTS / "reset_demo.sh"), str(workspace), check=False)
    assert result.returncode != 0
    assert "Refusing linked scan state" in result.stderr
    assert sentinel.read_text() == "unrelated"
