"""Ownership is an independent requirement for LangGraph conditional routes."""

from pathlib import Path

import pytest

from agentguard.comparison import analyze_snapshot
from agentguard.models import BehaviorSourceType
from tools.behavior_audit.obligation_audit import run_obligation_audit
from tools.behavior_audit.runner import PROJECT_ROOT

FIXTURES = PROJECT_ROOT / "tests/fixtures/graph_ownership"


def route(root: Path, name: str, owner: str = "review_graph"):
    inventory = analyze_snapshot(root)
    b = next(
        b
        for b in inventory.behaviors.behaviors
        if b.subject == owner
        and b.source_type is BehaviorSourceType.LANGGRAPH_WORKFLOW
        and b.action
        and b.action.target == "escalate"
        and b.condition
    )
    assessment = next(a for a in inventory.matching.assessments if a.behavior_id == b.behavior_id)
    return next(m for m in assessment.matches if m.name == name)


@pytest.mark.parametrize(
    "name", ["route_wrong_owner", "route_helper_only", "pydantic_route_wrong_owner"]
)
def test_original_wrong_owner_evidence_must_not_cover(name: str) -> None:
    report = run_obligation_audit()
    case = next(e for e in report["evidence_experiments"] if e["case"]["case_id"] == name)
    assert case["actual_covered"] is False


@pytest.mark.parametrize(
    "name", ["test_direct", "test_import_alias", "test_async", "jsonl_bound", "pydantic_bound"]
)
def test_source_bound_owner_condition_and_target_cover(name: str) -> None:
    assert route(FIXTURES, name).coverage_status.value == "covered"


@pytest.mark.parametrize(
    "name",
    [
        "test_wrong_graph",
        "test_conflicting_calls",
        "test_shadowed_import",
        "test_unresolved_alias",
        "jsonl_wrong",
        "jsonl_legacy",
        "jsonl_conflicting",
        "jsonl_missing",
        "pydantic_wrong",
    ],
)
def test_matching_route_terms_do_not_replace_ownership(name: str) -> None:
    assert route(FIXTURES, name).coverage_status.value != "covered"


@pytest.mark.parametrize("name", ["test_wrong_condition", "test_wrong_target", "test_no_outcome"])
def test_verified_identity_does_not_replace_condition_or_outcome(name: str) -> None:
    match = route(FIXTURES, name)
    assert match.coverage_status.value == "partially_covered"
    assert match.evidence.same_subject
    assert "verified_owner" in " ".join(match.evidence.details)


def test_wrong_graph_case_only_covers_its_own_owner() -> None:
    assert route(FIXTURES, "test_wrong_graph", "other_graph").coverage_status.value == "covered"
    assert route(FIXTURES, "jsonl_wrong", "other_graph").coverage_status.value == "covered"


def test_missing_owner_retains_matched_dimensions_and_conservative_explanation() -> None:
    from agentguard.models import CoverageDimension, CoverageReason

    match = route(FIXTURES, "jsonl_legacy")
    assert match.evidence.condition_matches and match.evidence.action_matches
    assert CoverageDimension.FUNCTIONALITY in match.missing_dimensions
    assert CoverageReason.GRAPH_OWNER_NOT_VERIFIED.value in match.evidence.candidate_reasons
    inventory = analyze_snapshot(FIXTURES)
    assessment = next(
        a
        for a in inventory.matching.assessments
        if a.behavior_id
        == next(
            b.behavior_id
            for b in inventory.behaviors.behaviors
            if b.subject == "review_graph" and b.action and b.action.target == "escalate"
        )
    )
    # This repository also has a genuinely verified positive; one bad eval cannot invalidate it.
    assert assessment.coverage_status.value == "covered"


def isolated(tmp_path: Path, source: str):
    from shutil import copy2

    (tmp_path / "tests").mkdir()
    copy2(FIXTURES / "workflow.py", tmp_path / "workflow.py")
    (tmp_path / "tests/evidence.py").write_text(source)
    return analyze_snapshot(tmp_path)


@pytest.mark.parametrize(
    "imports,receiver",
    [
        ("import workflow", "workflow.review_graph"),
        ("import workflow as flow", "flow.review_graph"),
        ("from workflow import review_graph as graph", "graph"),
    ],
)
def test_direct_import_forms_preserve_canonical_identity(
    tmp_path: Path, imports: str, receiver: str
) -> None:
    isolated(
        tmp_path,
        f"{imports}\ndef test_case():\n"
        f"    result = {receiver}.compile().invoke({{'choose': 'escalate'}})\n"
        "    assert result['route'] == 'escalate'\n",
    )
    assert route(tmp_path, "test_case").coverage_status.value == "covered"


@pytest.mark.parametrize(
    "change",
    [
        "review_graph = other_graph",
        "review_graph.invoke = other",
        "alias = review_graph",
    ],
)
def test_unresolved_rebound_and_mutated_subjects_do_not_verify(tmp_path: Path, change: str) -> None:
    source = (
        "from workflow import review_graph, other_graph\n"
        + change
        + "\ndef test_case():\n    result = "
        + ("alias" if change.startswith("alias") else "review_graph")
        + ".invoke({'choose': 'escalate'})\n    assert result['route'] == 'escalate'\n"
    )
    isolated(tmp_path, source)
    assert route(tmp_path, "test_case").coverage_status.value != "covered"


def test_ambiguous_module_paths_do_not_guess_import_resolution(tmp_path: Path) -> None:
    from shutil import copy2

    isolated(
        tmp_path,
        "from workflow import review_graph\ndef test_case():\n"
        "    result = review_graph.invoke({'choose':'escalate'})\n"
        "    assert result['route'] == 'escalate'\n",
    )
    (tmp_path / "src").mkdir()
    copy2(tmp_path / "workflow.py", tmp_path / "src/workflow.py")
    match = route(tmp_path, "test_case")
    assert match.coverage_status.value == "partially_covered"
    assert "graph_owner_ambiguous" in match.evidence.candidate_reasons


def test_nested_helper_call_is_not_invocation_evidence_for_test(tmp_path: Path) -> None:
    isolated(
        tmp_path,
        "from workflow import review_graph\ndef test_case():\n    def helper():\n"
        "        return review_graph.invoke({'choose':'escalate'})\n"
        "    assert 'escalate' == 'escalate'\n",
    )
    assert route(tmp_path, "test_case").coverage_status.value != "covered"


@pytest.mark.parametrize(
    "binding",
    [
        {"source_file": "../workflow.py", "symbol": "review_graph"},
        {"source_file": "workflow.py", "symbol": "unknown"},
        {"source_file": "workflow.py"},
        {"source_file": "workflow.py", "symbol": "review_graph", "extra": True},
        [
            {"source_file": "workflow.py", "symbol": "review_graph"},
            {"source_file": "workflow.py", "symbol": "other_graph"},
        ],
    ],
)
def test_invalid_or_ambiguous_asserted_subject_never_covers(tmp_path: Path, binding) -> None:
    import json

    isolated(tmp_path, "")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/case.jsonl").write_text(
        json.dumps(
            {
                "input": {"choose": "escalate"},
                "expected": {"route": "escalate"},
                "metadata": {"name": "case", "graph_owner": binding},
            }
        )
        + "\n"
    )
    assert route(tmp_path, "case").coverage_status.value != "covered"


@pytest.mark.parametrize("category", ["requirement", "runtime_guardrail", "quality_observation"])
def test_nonqualifying_category_cannot_use_verified_owner(category: str) -> None:
    from agentguard.matchers import match_behaviors_to_evals
    from agentguard.models import VerificationEvidenceType

    inventory = analyze_snapshot(FIXTURES)
    scenario = next(s for s in inventory.evals.scenarios if s.name == "jsonl_bound")
    scenario = scenario.model_copy(update={"evidence_type": VerificationEvidenceType(category)})
    result = match_behaviors_to_evals(
        inventory.behaviors, inventory.evals.model_copy(update={"scenarios": (scenario,)})
    )
    assert not any(
        a.coverage_status and a.coverage_status.value == "covered" for a in result.assessments
    )


def test_all_prechange_source_identities_and_nongraph_assessments_are_unchanged() -> None:
    import hashlib
    import json

    from agentguard.comparison import compare_inventories, comparison_json
    from agentguard.matchers.graph_ownership import is_conditional_graph_route
    from agentguard.models import ComparisonBaseline

    baseline = json.loads((FIXTURES / "compatibility_baseline.json").read_text())

    def digest(x):
        return hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest()

    for path, expected in baseline.items():
        now = analyze_snapshot(PROJECT_ROOT / path)
        assert (
            digest([b.model_dump(mode="json") for b in now.behaviors.behaviors])
            == expected["behaviors"]
        )
        assert (
            digest([r.model_dump(mode="json") for r in now.behaviors.registration_relationships])
            == expected["relationships"]
        )
        assert now.finding_ids == expected["finding_ids"]
        conditional = {
            b.behavior_id for b in now.behaviors.behaviors if is_conditional_graph_route(b)
        }
        assert [
            a.model_dump(mode="json")
            for a in now.matching.assessments
            if a.behavior_id not in conditional
        ] == [a for a in expected["assessments"] if a["behavior_id"] not in conditional]
        b = ComparisonBaseline(
            requested_ref="audit",
            resolved_commit="0" * 40,
            repository_root="[audit]",
            scan_path=".",
        )
        same = comparison_json(compare_inventories(now, now, baseline=b, repository="[audit]"))
        assert same == comparison_json(
            compare_inventories(
                analyze_snapshot(PROJECT_ROOT / path), now, baseline=b, repository="[audit]"
            )
        )


def test_m9_owner_evidence_add_remove_and_unrelated_eval(tmp_path: Path) -> None:
    import json

    from agentguard.comparison import compare_inventories
    from agentguard.models import ComparisonBaseline

    isolated(tmp_path, "")
    (tmp_path / "evals").mkdir()
    path = tmp_path / "evals/case.jsonl"
    record = {
        "input": {"choose": "escalate"},
        "expected": {"route": "escalate"},
        "metadata": {"name": "case", "tools": ["unrelated_graph"]},
    }
    path.write_text(json.dumps(record) + "\n")
    wrong = analyze_snapshot(tmp_path)
    b = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    record["metadata"]["graph_owner"] = {"source_file": "workflow.py", "symbol": "review_graph"}
    path.write_text(json.dumps(record) + "\n")
    valid = analyze_snapshot(tmp_path)
    assert (
        compare_inventories(wrong, valid, baseline=b, repository="[audit]").summary[
            "coverage_improvements"
        ]
        >= 1
    )
    assert (
        compare_inventories(valid, wrong, baseline=b, repository="[audit]").summary[
            "coverage_regressions"
        ]
        >= 1
    )
    path.write_text(
        json.dumps(
            {
                "input": {"choose": "escalate"},
                "expected": {"route": "escalate"},
                "metadata": {"name": "helper", "tools": ["choose"]},
            }
        )
        + "\n"
    )
    helper = analyze_snapshot(tmp_path)
    assert (
        compare_inventories(wrong, helper, baseline=b, repository="[audit]").summary[
            "coverage_improvements"
        ]
        == 0
    )
    assert {x.behavior_id for x in wrong.behaviors.behaviors} == {
        x.behavior_id for x in valid.behaviors.behaviors
    }
    assert not (tmp_path / ".agentguard").exists()


def test_upgrade_reopens_same_finding_and_preserves_feedback(tmp_path: Path) -> None:
    import json
    from shutil import copytree

    from agentguard.feedback import FindingStore
    from agentguard.findings import update_findings
    from agentguard.models import BehaviorCoverageAssessment, FindingDisposition, FindingStatus

    root = tmp_path / "example"
    copytree(PROJECT_ROOT / "examples/langgraph-agent", root)
    initial = analyze_snapshot(root)
    saved = json.loads((FIXTURES / "compatibility_baseline.json").read_text())
    legacy_initial = initial.matching.model_copy(
        update={
            "assessments": tuple(
                BehaviorCoverageAssessment.model_validate(a)
                for a in saved["examples/langgraph-agent"]["assessments"]
            )
        }
    )
    first = update_findings(root, initial.behaviors, legacy_initial)
    finding = next(f for f in first.findings if f.behavior_subject == "review_graph")
    store = FindingStore(root)
    store.record_feedback(finding.finding_id, FindingDisposition.ADD_EVAL)
    old = json.loads((PROJECT_ROOT / "docs/verification-obligation-audit-m10-2d.json").read_text())

    def restore_references(value):
        if isinstance(value, dict):
            if value.get("start_line") and value.get("end_line") and "excerpt" not in value:
                for base in (root, PROJECT_ROOT / "tests/fixtures/obligation_audit"):
                    path = base / value["source_file"]
                    if path.is_file():
                        value["excerpt"] = "\n".join(
                            path.read_text().splitlines()[
                                value["start_line"] - 1 : value["end_line"]
                            ]
                        )
                        break
            for child in value.values():
                restore_references(child)
        elif isinstance(value, list):
            for child in value:
                restore_references(child)

    restore_references(old)
    old_assessment = BehaviorCoverageAssessment.model_validate(
        next(
            e["assessment"]
            for e in old["evidence_experiments"]
            if e["case"]["case_id"] == "route_wrong_owner"
        )
    )
    legacy = initial.matching.model_copy(
        update={
            "assessments": tuple(
                old_assessment if a.behavior_id == old_assessment.behavior_id else a
                for a in initial.matching.assessments
            )
        }
    )
    resolved = update_findings(root, initial.behaviors, legacy)
    assert (
        next(f for f in resolved.findings if f.finding_id == finding.finding_id).status
        is FindingStatus.RESOLVED
    )
    history_before = store.history(finding.finding_id)
    feedback_before = store.feedback_events(finding.finding_id)
    (root / "evals/legacy_case.jsonl").write_text(
        json.dumps(
            {
                "input": {"select_review_route": "escalate"},
                "expected": {"path": ["escalate_refund"]},
                "metadata": {"tools": ["unrelated_graph"]},
            }
        )
        + "\n"
    )
    current = analyze_snapshot(root)
    reopened = update_findings(root, current.behaviors, current.matching)
    result = next(f for f in reopened.findings if f.finding_id == finding.finding_id)
    assert result.status is FindingStatus.OPEN
    assert result.current_disposition is FindingDisposition.ADD_EVAL
    assert not result.confirmed_impact and not result.observed_resolution
    assert store.feedback_events(finding.finding_id) == feedback_before
    assert store.history(finding.finding_id)[: len(history_before)] == history_before
    assert result.structured_explanation is not None
    assert "graph_owner_not_verified" in result.structured_explanation.reason_codes


def test_line_changes_preserve_ids_fingerprints_and_ownership(tmp_path: Path) -> None:
    first = isolated(
        tmp_path,
        "from workflow import review_graph\ndef test_case():\n"
        "    result = review_graph.compile().invoke({'choose':'escalate'})\n"
        "    assert result['route'] == 'escalate'\n",
    )
    for path in [tmp_path / "workflow.py", tmp_path / "tests/evidence.py"]:
        path.write_text("\n# unrelated line shift\n" + path.read_text())
    second = analyze_snapshot(tmp_path)
    assert {(b.behavior_id, b.content_fingerprint) for b in first.behaviors.behaviors} == {
        (b.behavior_id, b.content_fingerprint) for b in second.behaviors.behaviors
    }
    assert {(s.eval_id, s.content_fingerprint) for s in first.evals.scenarios} == {
        (s.eval_id, s.content_fingerprint) for s in second.evals.scenarios
    }
    assert route(tmp_path, "test_case").coverage_status.value == "covered"


def test_rebound_source_declaration_is_ambiguous_not_verified(tmp_path: Path) -> None:
    isolated(
        tmp_path,
        "from workflow import review_graph\ndef test_case():\n"
        "    result = review_graph.invoke({'choose':'escalate'})\n"
        "    assert result['route'] == 'escalate'\n",
    )
    path = tmp_path / "workflow.py"
    path.write_text(path.read_text() + "\nreview_graph = other_graph\n")
    match = route(tmp_path, "test_case")
    assert match.coverage_status.value == "partially_covered"
    assert "graph_owner_ambiguous" in match.evidence.candidate_reasons


def test_historical_and_postfix_audits_are_deterministic_and_keep_expectations() -> None:
    import hashlib
    import json

    from tools.behavior_audit.graph_ownership import run_graph_ownership_audit
    from tools.behavior_audit.runner import serialize_report

    report = run_graph_ownership_audit()
    assert report["metrics"]["post_fix_original_agreement"] == {"numerator": 20, "denominator": 21}
    assert report["metrics"]["three_original_false_coverage_corrected"] == {
        "numerator": 3,
        "denominator": 3,
    }
    assert report["metrics"]["control_agreement"] == {"numerator": 17, "denominator": 17}
    assert report["metrics"]["control_source_accuracy"] == {"numerator": 17, "denominator": 17}
    assert report["metrics"]["obligation_eligibility"] == {"numerator": 55, "denominator": 55}
    assert serialize_report(report) == serialize_report(run_graph_ownership_audit())
    assert (
        serialize_report(report)
        == (PROJECT_ROOT / "docs/graph-route-ownership-audit.json").read_text()
    )
    assert all(
        row["behaviors_unchanged"]
        and row["relationships_unchanged"]
        and row["finding_ids_unchanged"]
        for row in report["compatibility"]
    )
    assert all(
        change["conditional_graph_route"]
        for row in report["compatibility"]
        for change in row["assessment_changes"]
    )
    original = PROJECT_ROOT / "docs/verification-obligation-audit-m10-2d.json"
    inventory = json.loads((FIXTURES / "inventory.json").read_text())
    assert (
        hashlib.sha256(original.read_bytes()).hexdigest() == inventory["historical_report_sha256"]
    )


def test_graph_audit_never_executes_sources_or_mutates_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import json
    import socket
    import sqlite3
    import subprocess
    from shutil import copy2, copytree, ignore_patterns

    from tools.behavior_audit.graph_ownership import run_graph_ownership_audit

    project = tmp_path / "project"
    paths = list(json.loads((FIXTURES / "compatibility_baseline.json").read_text()))
    paths.append("tests/fixtures/graph_ownership")
    for path in paths:
        copytree(
            PROJECT_ROOT / path,
            project / path,
            dirs_exist_ok=True,
            ignore=ignore_patterns(".agentguard", ".venv", "__pycache__"),
        )
    (project / "docs").mkdir()
    copy2(PROJECT_ROOT / "docs/verification-obligation-audit-m10-2d.json", project / "docs")
    target = project / "tests/fixtures/graph_ownership"
    source = target / "workflow.py"
    source.write_text(source.read_text() + "\nraise AssertionError('target executed')\n")
    path = target / "inventory.json"
    truth = json.loads(path.read_text())
    truth["sources"]["workflow.py"] = hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_text(json.dumps(truth))
    state = target / ".agentguard/agentguard.db"
    state.parent.mkdir()
    state.write_bytes(b"existing user feedback")
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Network, execution or SQLite access attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    run_graph_ownership_audit(project=project)
    assert before == {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    }
    assert list(project.rglob(".agentguard")) == [state.parent]


@pytest.mark.parametrize("source_type", ["jsonl", "pydantic"])
@pytest.mark.parametrize(
    "condition,target,expected",
    [
        ("escalate", "escalate", "covered"),
        ("reject", "escalate", "partially_covered"),
        ("escalate", "reject", "partially_covered"),
        ("escalate", None, "partially_covered"),
    ],
)
def test_bound_case_sources_still_require_condition_and_expected_target(
    tmp_path: Path, source_type: str, condition: str, target: str | None, expected: str
) -> None:
    import json

    isolated(tmp_path, "")
    (tmp_path / "evals").mkdir()
    metadata = {
        "name": "case",
        "graph_owner": {"source_file": "workflow.py", "symbol": "review_graph"},
    }
    if source_type == "jsonl":
        record = {"input": {"choose": condition}, "metadata": metadata}
        if target:
            record["expected"] = {"route": target}
        (tmp_path / "evals/case.jsonl").write_text(json.dumps(record) + "\n")
    else:
        outcome = f", expected_output={{'route':{target!r}}}" if target else ""
        (tmp_path / "evals/case.py").write_text(
            "from pydantic_evals import Case\n"
            + f"case = Case(name='case', inputs={{'choose':{condition!r}}}, "
            + f"metadata={metadata!r}{outcome})\n"
        )
    assert route(tmp_path, "case").coverage_status.value == expected


@pytest.mark.parametrize("source_type", ["pytest", "jsonl"])
def test_equal_symbols_in_different_files_do_not_share_ownership(
    tmp_path: Path, source_type: str
) -> None:
    import json
    from shutil import copy2

    isolated(tmp_path, "")
    copy2(tmp_path / "workflow.py", tmp_path / "alternate.py")
    if source_type == "pytest":
        (tmp_path / "tests/evidence.py").write_text(
            "from alternate import review_graph\ndef test_case():\n"
            "    result = review_graph.compile().invoke({'choose':'escalate'})\n"
            "    assert result['route'] == 'escalate'\n"
        )
        name = "test_case"
    else:
        (tmp_path / "evals").mkdir()
        (tmp_path / "evals/case.jsonl").write_text(
            json.dumps(
                {
                    "input": {"choose": "escalate"},
                    "expected": {"route": "escalate"},
                    "metadata": {
                        "name": "case",
                        "graph_owner": {"source_file": "alternate.py", "symbol": "review_graph"},
                    },
                }
            )
            + "\n"
        )
        name = "case"
    inventory = analyze_snapshot(tmp_path)
    for file, expected in [("workflow.py", "partially_covered"), ("alternate.py", "covered")]:
        b = next(
            b
            for b in inventory.behaviors.behaviors
            if b.source_file == file
            and b.subject == "review_graph"
            and b.action
            and b.action.target == "escalate"
        )
        a = next(a for a in inventory.matching.assessments if a.behavior_id == b.behavior_id)
        assert next(m for m in a.matches if m.name == name).coverage_status.value == expected


def test_added_graph_facts_do_not_change_other_matcher_paths(tmp_path: Path) -> None:
    from agentguard.extractors.graph_evidence import OWNER_KINDS
    from agentguard.matchers import match_behaviors_to_evals
    from agentguard.models import BehaviorSourceType

    isolated(
        tmp_path,
        "import pytest\nfrom workflow import review_graph\nfrom agent import lookup\n"
        "def test_case():\n    review_graph.compile().invoke({'choose':'escalate'})\n"
        "    with pytest.raises(ValueError):\n        lookup(-1)\n",
    )
    (tmp_path / "agent.py").write_text(
        "from langchain_core.tools import tool\n@tool\n"
        "def lookup(amount):\n    if amount < 0:\n"
        "        raise ValueError('negative')\n    return amount\n"
    )
    inventory = analyze_snapshot(tmp_path)
    nongraph = inventory.behaviors.model_copy(
        update={
            "behaviors": tuple(
                b
                for b in inventory.behaviors.behaviors
                if b.source_type is not BehaviorSourceType.LANGGRAPH_WORKFLOW
            )
        }
    )
    stripped = inventory.evals.model_copy(
        update={
            "scenarios": tuple(
                s.model_copy(
                    update={
                        "referenced_symbols": tuple(
                            r for r in s.referenced_symbols if r.evidence.kind not in OWNER_KINDS
                        ),
                        "evidence": tuple(
                            e
                            for e in s.evidence
                            if e.kind not in {*OWNER_KINDS, "graph_owner_definition"}
                        ),
                    }
                )
                for s in inventory.evals.scenarios
            )
        }
    )
    assert match_behaviors_to_evals(nongraph, inventory.evals) == match_behaviors_to_evals(
        nongraph, stripped
    )
