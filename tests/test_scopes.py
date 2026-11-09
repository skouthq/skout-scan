"""Explicit scopes preserve full repository matching, persistence and history."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from shutil import copy2, copytree

import pytest
from rich.console import Console
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.feedback import FindingStore
from agentguard.findings import update_findings
from agentguard.metrics import calculate_validation_summary
from agentguard.models import ComparisonBaseline, FindingDisposition, FindingStatus, ScopeMembership
from agentguard.scope_reporting import render_scope_inventory
from agentguard.scopes import (
    ScopeSelectionError,
    discover_scope_roots,
    scan_selected_scope,
    scope_membership,
    select_scope,
)
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report
from tools.behavior_audit.scopes import INVENTORY, run_scope_audit

FIXTURES = PROJECT_ROOT / "tests/fixtures/scope_audit"
FIRST = datetime(2026, 1, 1, tzinfo=UTC)
SECOND = FIRST + timedelta(days=1)
runner = CliRunner()


def test_discovery_selectors_remain_copyable_on_narrow_terminals() -> None:
    _, inventory = roots(PROJECT_ROOT / "examples/pydantic-ai-agent")
    stream = StringIO()
    render_scope_inventory(Console(file=stream, width=50, color_system=None), inventory)
    assert "--scope 'agent.py#refund_agent'" in stream.getvalue()


def roots(root: Path):
    full = analyze_snapshot(root)
    return full, discover_scope_roots(full.discovery, full.behaviors)


def test_source_first_scope_audit_and_determinism() -> None:
    report = run_scope_audit()
    assert report["metrics"]["membership_precision"] == {"numerator": 54, "denominator": 54}
    assert report["metrics"]["membership_recall"] == {"numerator": 54, "denominator": 54}
    assert report["metrics"]["exclusion_precision"] == {"numerator": 12, "denominator": 12}
    assert report["metrics"]["unknown_correctness"] == {"numerator": 16, "denominator": 16}
    assert report["metrics"]["source_accuracy"] == {"numerator": 182, "denominator": 182}
    assert report["metrics"]["relevant_findings_retained"] == {"numerator": 4, "denominator": 4}
    assert report["metrics"]["known_outside_findings_excluded"] == {
        "numerator": 2,
        "denominator": 2,
    }
    assert report["metrics"]["unknown_findings_preserved_as_diagnostics"] == {
        "numerator": 2,
        "denominator": 2,
    }
    assert serialize_report(report) == serialize_report(run_scope_audit())
    assert serialize_report(report) == (PROJECT_ROOT / "docs/agent-scope-audit.json").read_text()
    assert '"excerpt"' not in serialize_report(report) and str(
        PROJECT_ROOT
    ) not in serialize_report(report)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("agents", ["app.py#alpha", "app.py#beta"]),
        ("chains", ["app.py#other", "app.py#selected"]),
        ("unknown", ["app.py#dynamic", "app.py#external", "app.py#selected"]),
    ],
)
def test_known_unique_roots_only(name: str, expected: list[str]) -> None:
    _, inventory = roots(FIXTURES / name)
    assert [r.selector for r in inventory.roots] == expected
    for root in inventory.roots:
        assert select_scope(inventory, root.selector) == select_scope(inventory, root.root_id)
        assert select_scope(inventory, root.qualified_symbol) == root
    assert not (FIXTURES / name / ".agentguard").exists()


def test_ambiguous_candidate_is_not_selectable() -> None:
    _, inventory = roots(FIXTURES / "unknown")
    assert [r.selector for r in inventory.candidates] == ["app.py#rebound"]
    with pytest.raises(ScopeSelectionError, match="not selectable"):
        select_scope(inventory, "rebound")
    with pytest.raises(ScopeSelectionError, match="unsupported"):
        select_scope(inventory, "custom")


@pytest.mark.parametrize(
    "selector",
    [
        "",
        " ",
        "/absolute.py#alpha",
        "../outside.py#alpha",
        "app.py#bad#name",
        "app.py#",
        "crewai:alpha",
        "x\n",
    ],
)
def test_malformed_selectors_fail_without_fallback(selector: str) -> None:
    _, inventory = roots(FIXTURES / "agents")
    with pytest.raises(ScopeSelectionError) as e:
        select_scope(inventory, selector)
    assert e.value.code == "malformed_scope"


def test_duplicate_short_names_require_qualified_selector(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "one")
    copytree(FIXTURES / "agents", tmp_path / "two")
    _, inventory = roots(tmp_path)
    with pytest.raises(ScopeSelectionError, match="one/app.py#alpha.*two/app.py#alpha"):
        select_scope(inventory, "alpha")
    assert select_scope(inventory, "two/app.py#alpha").source_file == "two/app.py"


def test_quoted_selector_can_contain_a_source_path_space(tmp_path: Path) -> None:
    copy2(FIXTURES / "agents/app.py", tmp_path / "some file.py")
    _, inventory = roots(tmp_path)
    assert select_scope(inventory, "some file.py#alpha").display_name == "alpha"


@pytest.mark.parametrize("directory", ["agent", "v1", "v2", "legacy", "module"])
def test_directory_labels_never_determine_membership(tmp_path: Path, directory: str) -> None:
    copytree(FIXTURES / "agents", tmp_path / directory)
    before, old = roots(FIXTURES / "agents")
    after, new = roots(tmp_path)

    def signature(full, inventory, selector):
        rows, _, _, _ = scope_membership(
            inventory, full.behaviors, select_scope(inventory, selector)
        )
        by_id = {b.behavior_id: b for b in full.behaviors.behaviors}
        return sorted(
            (by_id[r.item_id].subject, by_id[r.item_id].behavior_type.value, r.membership.value)
            for r in rows
        )

    assert signature(before, old, "app.py#alpha") == signature(
        after, new, f"{directory}/app.py#alpha"
    )


def test_shared_behavior_and_finding_ids_survive_selected_views(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    root = tmp_path / "repo"
    alpha = scan_selected_scope(root, "alpha", observed_at=FIRST)
    beta = scan_selected_scope(root, "beta", observed_at=SECOND)
    alpha_shared = {f.finding_id for f in alpha.findings if f.behavior_subject == "shared"}
    beta_shared = {f.finding_id for f in beta.findings if f.behavior_subject == "shared"}
    assert alpha_shared and alpha_shared == beta_shared
    assert {b.behavior_id for b in alpha.behaviors if b.subject == "shared"} == {
        b.behavior_id for b in beta.behaviors if b.subject == "shared"
    }
    assert not any(f.behavior_subject == "only_beta" for f in alpha.findings)
    assert any(f.behavior_subject == "only_beta" for f in alpha.out_of_scope_findings)
    assert any(f.behavior_subject == "unregistered" for f in alpha.unknown_findings)
    assert alpha.scope.finding_counts == {"in_scope": 5, "out_of_scope": 3, "unknown": 2}


def test_scoped_and_full_persistence_commute_and_metrics_match(tmp_path: Path) -> None:
    left, right = tmp_path / "scoped", tmp_path / "ordinary"
    copytree(FIXTURES / "agents", left)
    copytree(FIXTURES / "agents", right)
    selected = scan_selected_scope(left, "alpha", observed_at=FIRST)
    full = analyze_snapshot(right)
    update_findings(right, full.behaviors, full.matching, observed_at=FIRST)
    stores = [FindingStore(left), FindingStore(right)]
    outside = next(f for f in selected.out_of_scope_findings if f.behavior_subject == "only_beta")
    for store in stores:
        store.record_feedback(
            outside.finding_id, FindingDisposition.ADD_EVAL, occurred_at=FIRST + timedelta(hours=1)
        )
    for root in [left, right]:
        full = analyze_snapshot(root)
        update_findings(root, full.behaviors, full.matching, observed_at=SECOND)
    assert stores[0].list_findings() == stores[1].list_findings()
    assert all(f.status is FindingStatus.OPEN for f in stores[0].list_findings())
    assert calculate_validation_summary(stores[0]).model_dump(
        exclude={"repository"}
    ) == calculate_validation_summary(stores[1]).model_dump(exclude={"repository"})
    for f in stores[0].list_findings():
        assert [e.model_dump(exclude={"event_id"}) for e in stores[0].history(f.finding_id)] == [
            e.model_dump(exclude={"event_id"}) for e in stores[1].history(f.finding_id)
        ]
        assert [
            e.model_dump(exclude={"event_id"}) for e in stores[0].feedback_events(f.finding_id)
        ] == [e.model_dump(exclude={"event_id"}) for e in stores[1].feedback_events(f.finding_id)]


def test_scoped_matching_is_exact_full_matching_and_keeps_all_evidence(tmp_path: Path) -> None:
    copytree(PROJECT_ROOT / "examples/pydantic-ai-agent", tmp_path / "repo")
    root = tmp_path / "repo"
    full = analyze_snapshot(root)
    selected = scan_selected_scope(root, "refund_agent", observed_at=FIRST)
    # M10.2e adds explanation context only; every M8 decision/evidence field stays exact.
    assert [
        a.model_dump(exclude={"structured_explanation": {"rejection_provenance"}})
        for a in selected.assessments
    ] == [a.model_dump() for a in full.matching.assessments]
    assert selected.behaviors == full.behaviors.behaviors
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    after = scan_selected_scope(root, "refund_agent", observed_at=SECOND)
    assert after.repository_summary["resolved"] >= 1
    assert not any(f.behavior_subject == "validate_refund" for f in after.findings)


def test_uncertain_links_and_incomplete_sources_do_not_prove_exclusion(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    root = tmp_path / "repo"
    (root / "broken.py").write_text("def broken(:\n")
    full, inventory = roots(root)
    rows, _, _, closed = scope_membership(
        inventory, full.behaviors, select_scope(inventory, "alpha")
    )
    assert not closed
    by_id = {b.behavior_id: b for b in full.behaviors.behaviors}
    assert all(
        r.membership is ScopeMembership.UNKNOWN
        for r in rows
        if by_id[r.item_id].subject == "only_beta"
    )
    assert any(r.membership is ScopeMembership.IN_SCOPE for r in rows)


def test_resolved_context_traversal_never_creates_coverage_behaviors() -> None:
    full, inventory = roots(FIXTURES / "chains")
    before = full.behaviors.model_dump_json()
    b, r, c, _ = scope_membership(inventory, full.behaviors, select_scope(inventory, "selected"))
    assert full.behaviors.model_dump_json() == before
    assert {row.source_symbol for row in c if row.membership is ScopeMembership.IN_SCOPE} >= {
        "search",
        "retrieve",
        "Storage.fetch",
        "cached",
    }
    assert not any(
        behavior.subject in {"search", "retrieve", "Storage.fetch", "cached"}
        for behavior in full.behaviors.behaviors
    )
    assert all(row.relationship_ids for row in r if row.membership is ScopeMembership.IN_SCOPE)


def test_root_and_membership_ids_ignore_formatting_and_order(tmp_path: Path) -> None:
    copy2(FIXTURES / "agents/app.py", tmp_path / "app.py")
    before, old = roots(tmp_path)
    old_ids = {r.root_id for r in old.roots}
    path = tmp_path / "app.py"
    path.write_text("\n# line shift\n" + path.read_text())
    after, new = roots(tmp_path)
    assert {r.root_id for r in new.roots} == old_ids
    assert {b.behavior_id for b in before.behaviors.behaviors} == {
        b.behavior_id for b in after.behaviors.behaviors
    }
    reordered = after.behaviors.model_copy(
        update={
            "registration_relationships": tuple(
                reversed(after.behaviors.registration_relationships)
            ),
            "behaviors": tuple(reversed(after.behaviors.behaviors)),
        }
    )
    selected = select_scope(new, "alpha")
    assert scope_membership(new, reordered, selected) == scope_membership(
        new, after.behaviors, selected
    )


def test_scope_listing_is_read_only_and_json_is_reference_only(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    result = runner.invoke(app, ["scopes", str(tmp_path / "repo"), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [r["selector"] for r in payload["roots"]] == ["app.py#alpha", "app.py#beta"]
    assert '"excerpt"' not in result.output
    assert not (tmp_path / "repo/.agentguard").exists()
    text = runner.invoke(app, ["scopes", str(tmp_path / "repo")])
    assert text.exit_code == 0 and "app.py#alpha" in text.output and "Pydantic AI" in text.output


@pytest.mark.parametrize("json_output", [False, True])
def test_scoped_cli_reports_only_selected_findings_and_diagnostics(
    tmp_path: Path, json_output: bool
) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    args = ["scan", str(tmp_path / "repo"), "--scope", "alpha", "--no-progress"]
    if json_output:
        args.append("--json")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    if json_output:
        payload = json.loads(result.output)
        assert payload["scope"]["root"]["selector"] == "app.py#alpha"
        assert payload["scope"]["behavior_counts"] == {
            "in_scope": 7,
            "out_of_scope": 4,
            "unknown": 3,
        }
        assert all(f["behavior_subject"] != "only_beta" for f in payload["findings"])
        assert payload["out_of_scope_findings"] and payload["unknown_findings"]
        assert '"excerpt"' not in result.output
    else:
        assert "Scoped open findings: 5" in result.output
        assert "out_of_scope" in result.output and "unknown" in result.output
        assert "not runtime reachability" in " ".join(result.output.split())
    assert len(FindingStore(tmp_path / "repo").list_findings()) == 10


@pytest.mark.parametrize("selector", ["absent", "app.py#missing", "wrong_kind:agent", "rebound"])
def test_invalid_selection_has_no_state_side_effects(tmp_path: Path, selector: str) -> None:
    copytree(FIXTURES / "unknown", tmp_path / "repo")
    result = runner.invoke(app, ["scan", str(tmp_path / "repo"), "--scope", selector, "--json"])
    assert result.exit_code == 2 and "error" in json.loads(result.output)
    assert not (tmp_path / "repo/.agentguard").exists()


@pytest.mark.parametrize(
    "selector",
    ["alpha", "old_name", "new_name", "moved/file.py#root", "baseline_only", "current_only"],
)
def test_scoped_m9_is_rejected_before_any_snapshot_or_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selector: str
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Analysis ran for unsupported flag combination")

    monkeypatch.setattr("agentguard.cli.scan_selected_scope", forbidden)
    monkeypatch.setattr("agentguard.cli.compare_repository", forbidden)
    result = runner.invoke(
        app, ["scan", str(tmp_path), "--scope", selector, "--baseline", "HEAD", "--json"]
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "scoped_baseline_unsupported"
    assert not (tmp_path / ".agentguard").exists()


def test_exclusions_and_configuration_are_relative_to_supplied_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    copy2(FIXTURES / "agents/app.py", root / "kept.py")
    copy2(FIXTURES / "agents/app.py", root / "excluded.py")
    (root / "agentguard.toml").write_text('include=["*.py"]\nexclude=["excluded.py"]\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["scopes", "repo", "--json"])
    assert [r["selector"] for r in json.loads(result.output)["roots"]] == [
        "kept.py#alpha",
        "kept.py#beta",
    ]
    run = runner.invoke(app, ["scan", "repo", "--scope", "kept.py#alpha", "--json"])
    assert run.exit_code == 0, run.output
    assert (root / ".agentguard/agentguard.db").exists() and not (tmp_path / ".agentguard").exists()
    excluded = runner.invoke(
        app, ["scan", "repo", "--scope", "kept.py#alpha", "--exclude", "kept.py", "--json"]
    )
    assert excluded.exit_code == 2


def test_missing_path_and_file_path_fail_clearly(tmp_path: Path) -> None:
    file = tmp_path / "file.py"
    file.write_text("x=1\n")
    for root in [tmp_path / "missing", file]:
        result = runner.invoke(app, ["scan", str(root), "--scope", "alpha", "--json"])
        assert result.exit_code == 1
        assert json.loads(result.output)["error"]["code"] == "scope_scan_failed"


def test_baselines_and_all_prior_reports_are_identical() -> None:
    baseline = json.loads((FIXTURES / "compatibility_baseline.json").read_text())

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    context = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    for path, expected in baseline["repositories"].items():
        r = analyze_snapshot(PROJECT_ROOT / path)
        assert (
            digest([x.model_dump(mode="json") for x in r.behaviors.behaviors])
            == expected["behaviors"]
        )
        assert (
            digest([x.model_dump(mode="json") for x in r.behaviors.registration_relationships])
            == expected["relationships"]
        )
        assert (
            digest([x.model_dump(mode="json") for x in r.matching.assessments])
            == expected["assessments"]
        )
        assert digest([x.model_dump(mode="json") for x in r.evals.scenarios]) == expected["evals"]
        assert r.finding_ids == expected["finding_ids"]
        assert (
            digest(
                comparison_json(compare_inventories(r, r, baseline=context, repository="[audit]"))
            )
            == expected["m9_same"]
        )
    for name, expected in baseline["reports"].items():
        assert (
            hashlib.sha256((PROJECT_ROOT / f"docs/{name}-audit.json").read_bytes()).hexdigest()
            == expected
        )


def test_pure_audit_no_execution_network_or_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    target = project / "target"
    copytree(FIXTURES / "agents", target)
    source = target / "app.py"
    source.write_text(source.read_text() + "\nraise AssertionError('executed target')\n")
    truth = json.loads(INVENTORY.read_text())
    truth["repositories"] = [r for r in truth["repositories"] if r["repository"] == "agents"]
    truth["repositories"][0]["path"] = "target"
    truth["repositories"][0]["source_hashes"]["app.py"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    truth["expectations"] = [e for e in truth["expectations"] if e["repository"] == "agents"]
    truth["root_expectations"] = [
        e for e in truth["root_expectations"] if e["repository"] == "agents"
    ]
    inventory = project / "inventory.json"
    inventory.write_text(json.dumps(truth))
    state = target / ".agentguard/agentguard.db"
    state.parent.mkdir()
    state.write_bytes(b"existing feedback")
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Network/execution/SQLite attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    report = run_scope_audit(inventory, project=project)
    assert (
        report["metrics"]["reviewed_membership"]["numerator"]
        == report["metrics"]["reviewed_membership"]["denominator"]
    )
    assert before == {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    }
    state.unlink()
    state.parent.rmdir()
    run_scope_audit(inventory, project=project)
    assert not state.parent.exists()


def test_expected_decisions_do_not_control_membership(tmp_path: Path) -> None:
    original = run_scope_audit()
    truth = json.loads(INVENTORY.read_text())
    truth["expectations"][0]["membership"] = "out_of_scope"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(truth))
    altered = run_scope_audit(path)
    assert (
        altered["metrics"]["reviewed_membership"]["numerator"]
        < altered["metrics"]["reviewed_membership"]["denominator"]
    )
    assert [r["selections"][0]["behavior_membership"] for r in original["repositories"]] == [
        r["selections"][0]["behavior_membership"] for r in altered["repositories"]
    ]


def test_invalid_selection_preserves_existing_database_bytes(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    root = tmp_path / "repo"
    scan_selected_scope(root, "alpha", observed_at=FIRST)
    state = root / ".agentguard/agentguard.db"
    before = state.read_bytes()
    result = runner.invoke(app, ["scan", str(root), "--scope", "removed.py#old_agent", "--json"])
    assert result.exit_code == 2
    assert state.read_bytes() == before


def test_actual_eval_change_can_resolve_an_outside_finding(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    root = tmp_path / "repo"
    before = scan_selected_scope(root, "alpha", observed_at=FIRST)
    outside = next(
        f
        for f in before.out_of_scope_findings
        if f.behavior_subject == "only_beta" and f.behavior_type.value == "tool_failure"
    )
    store = FindingStore(root)
    store.record_feedback(
        outside.finding_id, FindingDisposition.ADD_EVAL, occurred_at=FIRST + timedelta(hours=1)
    )
    (root / "tests").mkdir()
    (root / "tests/evidence.py").write_text(
        "import pytest\nfrom app import only_beta\n"
        "def test_beta():\n    with pytest.raises(TypeError):\n        only_beta('')\n"
    )
    after = scan_selected_scope(root, "alpha", observed_at=SECOND)
    resolved = store.get_finding(outside.finding_id)
    assert (
        resolved.status is FindingStatus.RESOLVED
        and resolved.current_disposition is FindingDisposition.ADD_EVAL
    )
    assert not resolved.confirmed_impact
    assert after.repository_summary["resolved"] >= 1
    assert not any(f.finding_id == outside.finding_id for f in after.findings)


def test_suppressed_outside_feedback_is_not_rewritten(tmp_path: Path) -> None:
    copytree(FIXTURES / "agents", tmp_path / "repo")
    root = tmp_path / "repo"
    before = scan_selected_scope(root, "alpha", observed_at=FIRST)
    store = FindingStore(root)
    finding = before.out_of_scope_findings[0]
    store.record_feedback(
        finding.finding_id, FindingDisposition.SUPPRESSED, occurred_at=FIRST + timedelta(hours=1)
    )
    feedback = store.feedback_events(finding.finding_id)
    after = scan_selected_scope(root, "alpha", observed_at=SECOND)
    assert (
        store.get_finding(finding.finding_id).current_disposition is FindingDisposition.SUPPRESSED
    )
    assert store.get_finding(finding.finding_id).status is FindingStatus.OPEN
    assert store.feedback_events(finding.finding_id) == feedback
    assert finding.finding_id not in {
        f.finding_id for f in (*after.findings, *after.out_of_scope_findings)
    }


def test_existing_edge_cycles_and_multiple_links_do_not_expand_source_analysis(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text("""from langchain_core.tools import tool
from pydantic_ai import Agent

def helper(value): return value
@tool
def first(value): return second(value)
@tool
def second(value):
    first(value)
    return helper(value)
selected = Agent("test", tools=[first])
""")
    full, inventory = roots(tmp_path)
    rows, relations, caps, closed = scope_membership(
        inventory, full.behaviors, select_scope(inventory, "selected")
    )
    assert {r.source_symbol for r in caps if r.membership is ScopeMembership.IN_SCOPE} == {
        "first",
        "second",
        "helper",
    }
    assert len({r.item_id for r in rows}) == len(rows)
    assert len({r.item_id for r in relations}) == len(relations)
    assert not any(b.subject == "helper" for b in full.behaviors.behaviors)
    assert closed


@pytest.mark.parametrize(
    "source",
    [
        "def agent(): return object()\nworkflow=object()\n",
        "from external import create_agent\nagent=create_agent()\n",
        "from external import agent\n",
        "from pydantic_ai import Agent\ndef create_agent(): return Agent('test')\n",
        "from crewai import Agent\nclass Crew:\n    def agent(self): return Agent(role='reader')\n",
    ],
)
def test_unsupported_entrypoints_never_gain_roots(tmp_path: Path, source: str) -> None:
    (tmp_path / "agent_v2_legacy.py").write_text(source)
    _, inventory = roots(tmp_path)
    assert not inventory.roots
    result = runner.invoke(app, ["scan", str(tmp_path), "--scope", "agent", "--json"])
    assert result.exit_code == 2
    assert not (tmp_path / ".agentguard").exists()


def test_removed_source_never_falls_back_to_another_root(tmp_path: Path) -> None:
    copy2(FIXTURES / "agents/app.py", tmp_path / "old.py")
    before, _ = roots(tmp_path)
    copy2(FIXTURES / "agents/app.py", tmp_path / "current.py")
    (tmp_path / "old.py").unlink()
    result = runner.invoke(app, ["scan", str(tmp_path), "--scope", "old.py#alpha", "--json"])
    assert result.exit_code == 2 and "unknown_scope" in result.output
    assert not (tmp_path / ".agentguard").exists()


def test_root_listing_respects_symlink_boundary(tmp_path: Path) -> None:
    external = tmp_path / "external.py"
    external.write_text("from pydantic_ai import Agent\nagent=Agent('test')\n")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "linked.py").symlink_to(external)
    result = runner.invoke(app, ["scopes", str(root), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["roots"] == []
    assert not (root / ".agentguard").exists()


@pytest.mark.parametrize("mutation", ["stale_hash", "outside_root", "duplicate", "wrong_expected"])
def test_invalid_ground_truth_is_rejected_or_scored_as_a_miss(
    tmp_path: Path, mutation: str
) -> None:
    truth = json.loads(INVENTORY.read_text())
    if mutation == "stale_hash":
        truth["repositories"][0]["source_hashes"]["app.py"] = "0" * 64
    elif mutation == "outside_root":
        truth["repositories"][0]["path"] = "../outside"
    elif mutation == "duplicate":
        truth["expectations"].append(truth["expectations"][0])
    else:
        truth["expectations"][0]["symbol"] = "not_a_source_symbol"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(truth))
    if mutation == "wrong_expected":
        report = run_scope_audit(path)
        assert (
            report["metrics"]["membership_recall"]["numerator"]
            < report["metrics"]["membership_recall"]["denominator"]
        )
    else:
        with pytest.raises(ValueError):
            run_scope_audit(path)


def test_unreadable_source_is_diagnostic_and_never_selects_another_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy2(FIXTURES / "agents/app.py", tmp_path / "app.py")
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == tmp_path / "app.py":
            raise PermissionError("not readable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    listing = runner.invoke(app, ["scopes", str(tmp_path), "--json"])
    payload = json.loads(listing.output)
    assert payload["completeness"] == "incomplete" and payload["roots"] == []
    assert any("unavailable" in text for text in payload["limitations"])
    result = runner.invoke(app, ["scan", str(tmp_path), "--scope", "app.py#alpha", "--json"])
    assert result.exit_code == 2
    assert not (tmp_path / ".agentguard").exists()


def test_graph_owner_rules_are_identical_in_selected_scan(tmp_path: Path) -> None:
    copytree(PROJECT_ROOT / "examples/langgraph-agent", tmp_path / "repo")
    root = tmp_path / "repo"
    (root / "evals/wrong.jsonl").write_text(
        json.dumps(
            {
                "input": {"select_review_route": "escalate"},
                "expected": {"path": ["escalate_refund"]},
                "metadata": {"name": "wrong owner", "tools": ["unrelated_graph"]},
            }
        )
        + "\n"
    )
    full = analyze_snapshot(root)
    view = scan_selected_scope(root, "review_graph", observed_at=FIRST)
    ids = {b.behavior_id for b in view.behaviors}
    assert view.assessments == tuple(a for a in full.matching.assessments if a.behavior_id in ids)
    assert any(
        m.name == "wrong owner" and m.coverage_status.value == "partially_covered"
        for a in view.assessments
        for m in a.matches
    )
    assert any(s.name == "wrong owner" for s in view.considered_evidence)


def test_destructured_constructor_result_is_not_a_proven_agent_instance(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "from pydantic_ai import Agent\nfirst, second = Agent('test')\n"
    )
    _, inventory = roots(tmp_path)
    assert not inventory.roots
    assert {r.qualified_symbol for r in inventory.candidates} == {"first", "second"}
    with pytest.raises(ScopeSelectionError):
        select_scope(inventory, "first")


@pytest.mark.parametrize("expansion", ["**settings", "*settings"])
def test_opaque_constructor_cannot_prove_other_components_excluded(
    tmp_path: Path, expansion: str
) -> None:
    (tmp_path / "app.py").write_text(
        f"from pydantic_ai import Agent\nselected = Agent({expansion})\nother = Agent('test')\n"
    )
    full, inventory = roots(tmp_path)
    selected = select_scope(inventory, "selected")
    assert selected.has_opaque_configuration
    rows, _, _, closed = scope_membership(inventory, full.behaviors, selected)
    assert not closed
    by_id = {b.behavior_id: b for b in full.behaviors.behaviors}
    assert all(
        r.membership is ScopeMembership.UNKNOWN for r in rows if by_id[r.item_id].subject == "other"
    )
