"""Run with an installed artifact's Python -I, outside the checkout. No target execution."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from shutil import copy2, copytree

# Installed only in disposable validation environments, never in distribution artifacts.
GUARD = """import os
import sys
from pathlib import Path

if os.environ.get("SKOUT_RELEASE_OFFLINE") == "1":
    def _guard(event, args):
        blocked = event.startswith("socket.") or event == "urllib.Request"
        if event == "subprocess.Popen":
            command = args[1]
            blocked = not (isinstance(command, (list, tuple)) and command
                           and Path(str(command[0])).name == "git")
        if blocked:
            marker = os.environ.get("SKOUT_RELEASE_GUARD_LOG")
            if marker:
                with open(marker, "a", encoding="utf-8") as log:
                    log.write(event + "\\n")
            raise RuntimeError("Release smoke blocked network or unsupported subprocess")
    sys.addaudithook(_guard)
"""


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def plain_output(output: str) -> str:
    """Compare visible CLI content independently of CI's ANSI styling."""
    # Imported here so the build driver can import GUARD using only the stdlib.
    from rich.text import Text

    return Text.from_ansi(output).plain


def run_smoke(workspace: Path, expected_version: str) -> dict[str, object]:
    import agentguard
    from agentguard.feedback import FindingStore
    from agentguard.models import CoverageStatus, FindingDisposition, FindingStatus

    prefix = Path(sys.prefix).resolve()
    module = Path(agentguard.__file__).resolve()
    assert module.is_relative_to(prefix), "Editable/source import leakage"
    assert importlib.metadata.version("skout-scan") == expected_version
    direct_url = importlib.metadata.distribution("skout-scan").read_text("direct_url.json")
    assert direct_url is not None
    assert not json.loads(direct_url).get("dir_info", {}).get("editable", False)
    entry = next(
        e
        for e in importlib.metadata.distribution("skout-scan").entry_points
        if e.group == "console_scripts" and e.name == "skout"
    )
    assert entry.value == "agentguard.cli:app"
    for framework in ["pydantic_ai", "langgraph", "crewai", "pytest"]:
        assert importlib.util.find_spec(framework) is None, framework
    binary = prefix / ("Scripts/skout.exe" if os.name == "nt" else "bin/skout")
    assert binary.is_file()
    environment = dict(os.environ)
    for name in ["PYTHONPATH", "PYTHONHOME"]:
        environment.pop(name, None)
    environment.update(
        SKOUT_RELEASE_OFFLINE="1",
        SKOUT_RELEASE_GUARD_LOG=str(workspace / "guard.log"),
        NO_COLOR="1",
        COLUMNS="120",
    )

    def cli(root: Path, *args: str, input_text: str | None = None, expected_code: int = 0) -> str:
        result = subprocess.run(
            [str(binary), *args],
            cwd=root,
            env=environment,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if result.returncode != expected_code:
            raise AssertionError(
                f"CLI {args!r}: exit {result.returncode}: " + result.stdout + result.stderr
            )
        return plain_output(result.stdout)

    # Guard probes use their own log; actual runtime must produce no denied events.
    probe_environment = {**environment, "SKOUT_RELEASE_GUARD_LOG": str(workspace / "probe.log")}
    for probe in [
        "import socket; socket.socket()",
        'import subprocess,sys; subprocess.run([sys.executable,"-c","print(1)"])',
    ]:
        result = subprocess.run(
            [sys.executable, "-I", "-c", probe],
            cwd=workspace,
            env=probe_environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode != 0 and "Release smoke blocked" in result.stderr
    assert (workspace / "probe.log").is_file()

    assert cli(workspace, "--version").strip() == expected_version
    for command in [
        (),
        ("scopes",),
        ("scan",),
        ("findings",),
        ("review",),
        ("doctor",),
        ("metrics",),
    ]:
        assert "Usage:" in cli(workspace, *command, "--help")
    assert "--details" in cli(workspace, "findings", "--help")
    assert "--details" in cli(workspace, "review", "--help")
    configurations = [
        (
            "pydantic-ai-agent",
            "Pydantic AI",
            "agent.py#refund_agent",
            "validate_refund",
            "tests/solutions/test_retry.py.example",
            "tests/test_retry.py",
        ),
        (
            "langgraph-agent",
            "LangGraph",
            "workflow.py#review_graph",
            "review_graph",
            "evals/escalation_path.jsonl.example",
            "evals/escalation_path.jsonl",
        ),
        (
            "crewai-agent",
            "CrewAI",
            "crew.py#refund_analyst",
            "escalate_refund",
            "tests/solutions/test_escalation.py.example",
            "tests/test_escalation.py",
        ),
    ]
    results = {}
    for directory, framework, selector, subject, source, target in configurations:
        root = workspace / directory
        # Poison files prove these Python modules/tests are only statically inspected.
        (root / "execution_trap.py").write_text('raise RuntimeError("Target code executed")\n')
        (root / "conftest.py").write_text('raise RuntimeError("Target test suite executed")\n')
        (root / "generated").mkdir()
        (root / "generated/broken.py").write_text("not valid python!\n")
        (root / "agentguard.toml").write_text('exclude = ["generated/**"]\n')
        doctor = json.loads(cli(root, "doctor", "--json"))
        assert framework in doctor["frameworks_detected"]
        assert "generated/**" in doctor["effective_excludes"]
        roots_text = cli(root, "scopes", ".")
        roots = json.loads(cli(root, "scopes", ".", "--json"))
        assert roots == json.loads(cli(root, "scopes", ".", "--json"))
        assert selector in [r["selector"] for r in roots["roots"]]
        assert selector in roots_text
        assert not (root / ".agentguard").exists(), "Read-only discovery created state"
        output = cli(root, "scan", ".", "--no-progress")
        assert "Status: complete" in output and "Open findings:" in output
        store = FindingStore(root)
        initial = store.list_findings()
        intended = next(
            f for f in initial if f.behavior_subject == subject and f.status is FindingStatus.OPEN
        )
        assert intended.coverage_status is CoverageStatus.POTENTIALLY_UNCOVERED
        database = root / ".agentguard/agentguard.db"
        inode = database.stat().st_ino
        before_read = database.read_bytes()
        assert "Next step:" in cli(root, "findings")
        assert "Source evidence:" in cli(root, "findings", "--details")
        assert "recorded, 0 skipped" not in cli(root, "review", input_text="skip\n" * len(initial))
        cli(root, "review", "--details", input_text="skip\n" * len(initial))
        assert database.read_bytes() == before_read, "Read-only review/listing changed state"
        cli(root, "feedback", intended.finding_id, "add_eval")
        scoped = json.loads(cli(root, "scan", ".", "--scope", selector, "--json"))
        assert scoped["scope"]["root"]["selector"] == selector
        assert all(
            k in scoped["scope"]["behavior_counts"] for k in ["in_scope", "out_of_scope", "unknown"]
        )
        assert any(f["finding_id"] == intended.finding_id for f in scoped["findings"])
        assert '"excerpt"' not in json.dumps(scoped)
        current = store.get_finding(intended.finding_id)
        assert current.current_disposition is FindingDisposition.ADD_EVAL
        assert current.status is FindingStatus.OPEN
        exported = json.loads(cli(root, "metrics", "--json"))
        assert any(f.get("guidance") for f in exported["findings"])
        assert '"excerpt"' not in json.dumps(exported)
        cli(root, "metrics")
        before_invalid = database.read_bytes()
        invalid = json.loads(
            cli(root, "scan", ".", "--scope", "not_a_scope", "--json", expected_code=2)
        )
        assert invalid["error"]["code"] == "unknown_scope"
        conflict = json.loads(
            cli(
                root,
                "scan",
                ".",
                "--scope",
                selector,
                "--baseline",
                "HEAD",
                "--json",
                expected_code=2,
            )
        )
        assert conflict["error"]["code"] == "scoped_baseline_unsupported"
        assert database.read_bytes() == before_invalid
        checks = {
            "scope_discovery_read_only": "pass",
            "basic_scan": "pass",
            "scoped_scan": "pass",
            "guidance_and_details": "pass",
            "review": "pass",
            "metrics_reference_only": "pass",
            "configuration": "pass",
            "invalid_scope_safe": "pass",
            "scope_baseline_rejected": "pass",
        }
        if directory == "pydantic-ai-agent":
            assert current.structured_explanation is not None
            context = current.structured_explanation.rejection_provenance
            assert context is not None
            assert context.owner_identities == ("agent.py#refund_agent",)
            assert any(r.kind == "output_validator_callback" for r in context.registrations)
            assert current.structured_explanation.behavior.action is not None
            assert current.structured_explanation.behavior.action.outcome == "ModelRetry"
            checks["validator_rejection_provenance"] = "pass"
        elif directory == "langgraph-agent":
            outside = json.loads(
                cli(root, "scan", ".", "--scope", "workflow.py#refund_graph", "--json")
            )
            assert any(
                f["finding_id"] == intended.finding_id for f in outside["out_of_scope_findings"]
            )
            assert store.get_finding(intended.finding_id).status is FindingStatus.OPEN
            wrong = json.loads((root / source).read_text())
            wrong["metadata"]["graph_owner"]["symbol"] = "refund_graph"
            (root / "evals/wrong_owner.jsonl").write_text(json.dumps(wrong) + "\n")
            cli(root, "scan", ".", "--scope", selector)
            wrong_result = store.get_finding(intended.finding_id)
            assert wrong_result.coverage_status is not CoverageStatus.COVERED
            assert wrong_result.status is FindingStatus.OPEN
            assert wrong_result.structured_explanation is not None
            assert "graph_owner_mismatch" in wrong_result.structured_explanation.reason_codes
            checks.update(graph_owner_gate="pass", outside_findings_preserved="pass")
        else:
            assert any(
                r["source_symbol"] == "lookup_order" for r in scoped["capability_membership"]
            )
            assert any(
                "task" in r["item_kind"]
                or r["source_symbol"] in {"inspect_request", "decide_refund"}
                for r in scoped["relationship_membership"]
            )
            checks["tool_and_task_executor_surface"] = "pass"
        solution = root / target
        solution.parent.mkdir(parents=True, exist_ok=True)
        copy2(root / source, solution)
        cli(root, "scan", ".", "--no-progress")
        resolved = store.get_finding(intended.finding_id)
        assert resolved.status is FindingStatus.RESOLVED
        assert resolved.coverage_status is CoverageStatus.COVERED
        assert resolved.current_disposition is FindingDisposition.ADD_EVAL
        assert resolved.observed_resolution and not resolved.confirmed_impact
        assert resolved.resolution_evidence
        assert set(resolved.resolution_evidence.matched_eval_ids) == set(resolved.matched_eval_ids)
        assert any(
            m.source_file == target
            for m in resolved.matched_eval_evidence
            if m.eval_id in resolved.matched_eval_ids
        )
        assert database.stat().st_ino == inode
        checks.update(
            supplied_eval_resolution="pass",
            finding_identity_feedback="pass",
            same_database_reused="pass",
            confirmed_impact_not_inferred="pass",
        )
        results[framework] = {
            "checks": checks,
            "initial_finding_id": intended.finding_id,
            "initial_findings": len(initial),
            "selectors": [r["selector"] for r in roots["roots"]],
            "scope_behavior_counts": scoped["scope"]["behavior_counts"],
            "resolved_by": target,
        }
    git_root = workspace / "git-repository"
    before_git = tree_hash(git_root)
    comparison = json.loads(cli(git_root, "scan", ".", "--baseline", "before-eval", "--json"))
    repeated = json.loads(cli(git_root, "scan", ".", "--baseline", "before-eval", "--json"))
    assert comparison == repeated
    assert any(
        c["verification_delta"] == "coverage_improvement"
        and c["current_behavior"]["subject"] == "validate_refund"
        for c in comparison["changes"]
    )
    assert tree_hash(git_root) == before_git
    assert not (git_root / ".agentguard").exists()
    assert not (workspace / "guard.log").exists(), (
        "Offline runtime guard recorded a prohibited action"
    )
    return {
        "status": "pass",
        "import_inside_environment": True,
        "editable": False,
        "entry_point": entry.value,
        "version": expected_version,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "sqlite_version": sqlite3.sqlite_version,
        "framework_libraries_installed": [],
        "frameworks": results,
        "offline_runtime": "pass",
        "network_and_subprocess_guard_probes": "pass",
        "target_execution_traps": "pass",
        "m9_read_only_deterministic": "pass",
        "m9_summary": comparison["summary"],
        "dependencies": {
            d.metadata["Name"]: d.version
            for d in sorted(
                importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()
            )
            if d.metadata["Name"].lower() not in {"pip", "setuptools"}
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    # Prepare local Git history before runtime guards are activated in CLI children.
    root = args.workspace / "git-repository"
    copytree(args.workspace / "pydantic-ai-agent", root)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_DATE="2000-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2000-01-01T00:00:00+00:00",
    )

    def git(*parts: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-c",
                "user.name=Skout validation",
                "-c",
                "user.email=validation@example.invalid",
                "-C",
                str(root),
                *parts,
            ],
            check=True,
            capture_output=True,
            env=env,
        )

    git("init", "--quiet")
    git("add", ".")
    git("commit", "--quiet", "-m", "Before supplied eval")
    git("tag", "before-eval")
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    git("add", ".")
    git("commit", "--quiet", "-m", "Supplied eval enabled")
    result = run_smoke(args.workspace, args.version)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
