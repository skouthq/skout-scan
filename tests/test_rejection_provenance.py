"""Provenance is optional declaration context, never a new verification decision."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from io import StringIO
from shutil import copy2, copytree

import pytest
from rich.console import Console
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.feedback import FindingStore
from agentguard.findings import select_findings, update_findings
from agentguard.metrics import calculate_validation_summary
from agentguard.models import (
    AssessmentAvailability,
    BehaviorType,
    ComparisonBaseline,
    CoverageExplanation,
    CoverageStatus,
    FindingDisposition,
    FindingStatus,
    RegistrationResolution,
    ScanCompleteness,
)
from agentguard.rejection_provenance import (
    enrich_rejection_explanations,
    rejection_provenance,
    render_rejection_context,
)
from agentguard.scopes import discover_scope_roots, project_scope, scan_selected_scope, select_scope
from tools.behavior_audit.rejection_provenance import (
    FIXTURE,
    compatibility_snapshot,
    run_rejection_audit,
)
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

FIRST = datetime(2026, 1, 1, tzinfo=UTC)
SECOND = FIRST + timedelta(days=1)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    copytree(PROJECT_ROOT / FIXTURE, root)
    return root


@pytest.fixture
def operational_repository(repository):
    # Keep negative/incomplete-source controls in the audit corpus, but use a
    # complete, genuinely missing-eval surface for high-confidence lifecycle tests.
    (repository / "negative.py").unlink()
    for path in [
        repository / "tests/evidence.py",
        repository / "evals/cases.py",
        repository / "evals/cases.jsonl",
    ]:
        path.unlink()
    return repository


def analysis(root):
    full = analyze_snapshot(root)
    inventory = discover_scope_roots(full.discovery, full.behaviors)
    enriched = enrich_rejection_explanations(full.behaviors, full.matching, inventory)
    return full, inventory, enriched


def without_context(value):
    if isinstance(value, dict):
        return {k: without_context(v) for k, v in value.items() if k != "rejection_provenance"}
    if isinstance(value, list):
        return [without_context(v) for v in value]
    if isinstance(value, tuple):
        return tuple(without_context(v) for v in value)
    return value


def test_independent_source_first_audit_is_deterministic_and_correct():
    first = run_rejection_audit()
    assert all(m["numerator"] == m["denominator"] > 0 for m in first["metrics"].values())
    assert first["metrics"]["eligible_enrichment_recall"] == {"numerator": 5, "denominator": 5}
    assert first["metrics"]["owner_attribution_precision"] == {"numerator": 6, "denominator": 6}
    assert first["human_review"] == "pending"
    assert first["unreviewed_enrichment_count"] == 0
    encoded = serialize_report(first)
    assert encoded == serialize_report(run_rejection_audit())
    assert encoded == (PROJECT_ROOT / "docs/rejection-provenance-audit.json").read_text()
    assert '"excerpt"' not in encoded and str(PROJECT_ROOT) not in encoded


def test_all_historical_inventory_and_audit_snapshots_remain_exact():
    baseline = json.loads((PROJECT_ROOT / FIXTURE / "compatibility_baseline.json").read_text())
    for name, digest in baseline["repositories"].items():
        assert compatibility_snapshot(PROJECT_ROOT / name) == digest, name
    for name, digest in baseline["reports"].items():
        assert hashlib.sha256((PROJECT_ROOT / "docs" / name).read_bytes()).hexdigest() == digest


def test_matching_fields_findings_and_behavior_inventory_are_unchanged(repository):
    full, inventory, enriched = analysis(repository)
    original = full.matching.model_dump(mode="json")
    assert without_context(enriched.model_dump(mode="json")) == original
    before = select_findings(full.behaviors, full.matching, observed_at=FIRST)
    after = select_findings(full.behaviors, enriched, observed_at=FIRST)
    assert without_context(after.model_dump(mode="json")) == before.model_dump(mode="json")
    assert full.matching.model_dump(mode="json") == original
    assert enrich_rejection_explanations(full.behaviors, enriched, inventory) == enriched
    assert len(rejection_provenance(full.behaviors, inventory)) == 5


@pytest.mark.parametrize(
    "symbol,count", [("refund", 2), ("shared", 1), ("partial", 1), ("validate_refund", 1)]
)
def test_existing_rejections_consolidate_equivalent_facts_only(repository, symbol, count):
    full, inventory, _ = analysis(repository)
    contexts = [
        c for c in rejection_provenance(full.behaviors, inventory) if c.source_symbol == symbol
    ]
    assert len(contexts) == count
    for context in contexts:
        assert len(context.related_behavior_ids) == 2
        primary = next(
            b for b in full.behaviors.behaviors if b.behavior_id == context.primary_behavior_id
        )
        assert primary.behavior_type is BehaviorType.TOOL_FAILURE
        assert context.resolution is RegistrationResolution.RESOLVED
        assert context.callable_id in {c.callable_id for c in full.behaviors.callable_capabilities}
        assert context.condition == primary.condition and context.outcome == primary.action
        assert context.source_evidence


def test_shared_callable_has_two_registrations_without_fanout(operational_repository):
    repository = operational_repository
    full, inventory, enriched = analysis(repository)
    context = next(
        c for c in rejection_provenance(full.behaviors, inventory) if c.source_symbol == "shared"
    )
    assert context.owner_identities == ("agent.py#first", "agent.py#second")
    assert len(context.registrations) == 2
    assert len({r.relationship_id for r in context.registrations}) == 2
    findings = select_findings(full.behaviors, enriched, observed_at=FIRST).findings
    assert len([f for f in findings if f.behavior_id in context.related_behavior_ids]) == 1


@pytest.mark.parametrize("symbol", ["refund", "unknown", "uncertain", "Storage.read", "plain"])
def test_negative_controls_do_not_inherit_ownership(repository, symbol):
    full, inventory, _ = analysis(repository)
    file = "agent.py" if symbol == "plain" else "negative.py"
    assert not any(
        c.source_file == file and c.source_symbol == symbol
        for c in rejection_provenance(full.behaviors, inventory)
    )


@pytest.mark.parametrize(
    "mutation",
    ["failed", "unavailable", "condition", "action", "no_refs", "wrong_symbol", "wrong_file"],
)
def test_missing_rejection_facts_abstain_without_changing_inventory(repository, mutation):
    full, inventory, _ = analysis(repository)
    original = full.behaviors
    changes = {}
    if mutation == "failed":
        changes["completeness"] = ScanCompleteness.FAILED
    elif mutation == "unavailable":
        changes["unavailable_behavior_ids"] = tuple(b.behavior_id for b in original.behaviors)
    else:
        field, value = {
            "condition": ("condition", None),
            "action": ("action", None),
            "no_refs": ("evidence", ()),
            "wrong_symbol": ("source_symbol", "missing"),
            "wrong_file": ("source_file", "other.py"),
        }[mutation]
        changes["behaviors"] = tuple(
            b.model_copy(update={field: value}) for b in original.behaviors
        )
    altered = original.model_copy(update=changes)
    assert rejection_provenance(altered, inventory) == ()
    assert original == full.behaviors


@pytest.mark.parametrize(
    "mutation",
    [
        "unresolved",
        "ambiguous",
        "missing_definition",
        "wrong_definition",
        "missing_registration",
        "wrong_owner",
        "wrong_callable",
        "graph_callback",
    ],
)
def test_bad_registration_links_abstain(repository, mutation):
    full, inventory, _ = analysis(repository)
    updates = {
        "unresolved": {"resolution": RegistrationResolution.UNRESOLVED},
        "ambiguous": {"resolution": RegistrationResolution.AMBIGUOUS},
        "missing_definition": {"definition": None},
        "wrong_definition": {
            "definition": full.behaviors.callable_capabilities[0].definition.model_copy(
                update={"source_file": "other.py"}
            )
        },
        "missing_registration": {
            "registration": full.behaviors.registration_relationships[0].registration.model_copy(
                update={"start_line": None}
            )
        },
        "wrong_owner": {"owner_identity": "negative.py#refund"},
        "wrong_callable": {"callable_id": "missing"},
        "graph_callback": {"kind": "graph_node_callback"},
    }[mutation]
    altered = full.behaviors.model_copy(
        update={
            "registration_relationships": tuple(
                r.model_copy(update=updates) for r in full.behaviors.registration_relationships
            )
        }
    )
    assert rejection_provenance(altered, inventory) == ()


def test_conflicting_capability_identity_abstains(repository):
    full, inventory, _ = analysis(repository)
    altered = full.behaviors.model_copy(
        update={
            "callable_capabilities": tuple(
                item
                for c in full.behaviors.callable_capabilities
                for item in (c, c.model_copy(update={"callable_id": "conflict-" + c.callable_id}))
            )
        }
    )
    assert rejection_provenance(altered, inventory) == ()


def test_unavailable_assessment_never_receives_context(repository):
    full, inventory, _ = analysis(repository)
    unavailable = full.matching.model_copy(
        update={
            "assessments": tuple(
                a.model_copy(update={"availability": AssessmentAvailability.UNAVAILABLE})
                for a in full.matching.assessments
            )
        }
    )
    result = enrich_rejection_explanations(full.behaviors, unavailable, inventory)
    assert all(
        a.structured_explanation.rejection_provenance is None
        for a in result.assessments
        if a.structured_explanation
    )


def test_partial_and_covered_results_are_not_promoted_by_context(repository):
    full, _, enriched = analysis(repository)
    failures = {
        b.behavior_id: b
        for b in full.behaviors.behaviors
        if b.behavior_type is BehaviorType.TOOL_FAILURE and b.source_file == "agent.py"
    }
    observed = {}
    for assessment in enriched.assessments:
        if assessment.behavior_id in failures:
            b = failures[assessment.behavior_id]
            observed[b.subject, b.action.outcome] = assessment.coverage_status
    assert observed["refund", "ValueError"] is CoverageStatus.COVERED
    assert observed["refund", "RuntimeError"] is CoverageStatus.PARTIALLY_COVERED
    assert observed["validate_refund", "ModelRetry"] is CoverageStatus.PARTIALLY_COVERED
    assert observed["partial", "ValueError"] is CoverageStatus.PARTIALLY_COVERED


def test_historical_explanations_parse_and_serialize_without_required_context(repository):
    full, _, enriched = analysis(repository)
    for original in full.matching.assessments:
        detail = original.structured_explanation
        if detail:
            payload = detail.model_dump(mode="json")
            assert "rejection_provenance" not in payload
            assert CoverageExplanation.model_validate(payload).model_dump(mode="json") == payload
    for assessment in enriched.assessments:
        detail = assessment.structured_explanation
        if detail and detail.rejection_provenance:
            assert CoverageExplanation.model_validate_json(detail.model_dump_json()) == detail


def test_scoped_shared_views_preserve_ids_complete_owners_and_global_state(operational_repository):
    repository = operational_repository
    first = scan_selected_scope(repository, "first", observed_at=FIRST)
    second = scan_selected_scope(repository, "second", observed_at=SECOND)
    views = []
    for view, selected in [(first, "agent.py#first"), (second, "agent.py#second")]:
        finding = next(f for f in view.findings if f.behavior_subject == "shared")
        context = finding.structured_explanation.rejection_provenance
        assert context.selected_owner_identity == selected
        assert context.owner_identities == ("agent.py#first", "agent.py#second")
        assert set(r.relationship_id for r in context.registrations)
        views.append((finding.finding_id, finding.behavior_id))
    assert views[0] == views[1]
    stored = FindingStore(repository).get_finding(views[0][0])
    assert stored.structured_explanation.rejection_provenance.selected_owner_identity is None
    full, inventory, enriched = analysis(repository)
    raw = project_scope(
        full,
        inventory,
        select_scope(inventory, "first"),
        update_findings(repository, full.behaviors, enriched, observed_at=SECOND),
    )
    assert raw.behavior_membership == first.behavior_membership


def test_provenance_owner_removal_preserves_open_finding_feedback_and_metrics(
    operational_repository,
):
    repository = operational_repository
    control = repository.parent / "raw_control"
    copytree(repository, control)
    full, _, enriched = analysis(repository)
    initial = update_findings(repository, full.behaviors, enriched, observed_at=FIRST)
    raw = analyze_snapshot(control)
    update_findings(control, raw.behaviors, raw.matching, observed_at=FIRST)
    finding = next(f for f in initial.findings if f.behavior_subject == "shared")
    store = FindingStore(repository)
    store.record_feedback(
        finding.finding_id, FindingDisposition.ADD_EVAL, occurred_at=FIRST + timedelta(hours=1)
    )
    control_store = FindingStore(control)
    control_store.record_feedback(
        finding.finding_id,
        FindingDisposition.ADD_EVAL,
        occurred_at=FIRST + timedelta(hours=1),
    )
    history_before = store.history(finding.finding_id)
    source = repository / "agent.py"
    text = source.read_text().replace(
        'second = Agent("test:model", tools=[shared])', 'second = Agent("test:model")'
    )
    source.write_text(text)
    (control / "agent.py").write_text(text)
    raw = analyze_snapshot(control)
    update_findings(control, raw.behaviors, raw.matching, observed_at=SECOND)
    full, _, enriched = analysis(repository)
    update_findings(repository, full.behaviors, enriched, observed_at=SECOND)
    after = store.get_finding(finding.finding_id)
    assert after.status is FindingStatus.OPEN and not after.observed_resolution
    assert after.current_disposition is FindingDisposition.ADD_EVAL
    assert not after.confirmed_impact
    assert after.structured_explanation.rejection_provenance.owner_identities == ("agent.py#first",)
    assert all(event in store.history(finding.finding_id) for event in history_before)
    # Removing only the optional context cannot itself change metric eligibility/results.
    assert calculate_validation_summary(store).model_dump(exclude={"repository"}) == (
        calculate_validation_summary(control_store).model_dump(exclude={"repository"})
    )
    assert (
        without_context(after.model_dump())
        == control_store.get_finding(finding.finding_id).model_dump()
    )


def test_registration_loss_clears_context_without_claiming_resolution(operational_repository):
    repository = operational_repository
    full, inventory, enriched = analysis(repository)
    initial = update_findings(repository, full.behaviors, enriched, observed_at=FIRST)
    context = next(
        c for c in rejection_provenance(full.behaviors, inventory) if c.source_symbol == "shared"
    )
    finding = next(f for f in initial.findings if f.behavior_id == context.primary_behavior_id)
    removed = full.behaviors.model_copy(update={"registration_relationships": ()})
    cleared = enrich_rejection_explanations(removed, enriched, inventory)
    update_findings(repository, removed, cleared, observed_at=SECOND)
    after = FindingStore(repository).get_finding(finding.finding_id)
    assert after.status is FindingStatus.OPEN and not after.observed_resolution
    assert after.structured_explanation.rejection_provenance is None


@pytest.mark.parametrize(
    "edit",
    [
        "same",
        "add_owner",
        "remove_owner",
        "whitespace",
        "lines",
        "unrelated_registration",
        "eval_added",
        "eval_removed",
    ],
)
def test_m9_rejection_semantics_identity_and_fingerprints_remain_unchanged(
    operational_repository, edit
):
    repository = operational_repository
    source = repository / "agent.py"
    if edit == "eval_removed":
        (repository / "tests/new.py").write_text(
            "import pytest\nfrom agent import shared\ndef test_reject():\n"
            "    with pytest.raises(ValueError):\n        shared(-1)\n"
        )
    before = analyze_snapshot(repository)
    original = source.read_text()
    if edit == "add_owner":
        source.write_text(original + '\nthird = Agent("test:model", tools=[shared])\n')
    elif edit == "remove_owner":
        source.write_text(
            original.replace(
                'second = Agent("test:model", tools=[shared])', 'second = Agent("test:model")'
            )
        )
    elif edit == "whitespace":
        source.write_text(original.replace("if amount < 0:", "if  amount  <  0 :"))
    elif edit == "lines":
        source.write_text("\n\n# shifted source\n" + original)
    elif edit == "unrelated_registration":
        source.write_text(original + '\nunrelated = Agent("test:model", tools=[plain])\n')
    elif edit == "eval_added":
        (repository / "tests/new.py").write_text(
            "import pytest\nfrom agent import shared\ndef test_reject():\n"
            "    with pytest.raises(ValueError):\n        shared(-1)\n"
        )
    elif edit == "eval_removed":
        (repository / "tests/new.py").unlink()
    after = analyze_snapshot(repository)
    failures = {
        b.behavior_id: b.content_fingerprint
        for b in before.behaviors.behaviors
        if b.behavior_type is BehaviorType.TOOL_FAILURE and b.condition
    }
    assert failures == {
        b.behavior_id: b.content_fingerprint
        for b in after.behaviors.behaviors
        if b.behavior_type is BehaviorType.TOOL_FAILURE and b.condition
    }
    raw = compare_inventories(
        before,
        after,
        baseline=ComparisonBaseline(
            requested_ref="audit",
            resolved_commit="0" * 40,
            repository_root="[audit]",
            scan_path=".",
        ),
        repository="[audit]",
    )
    if edit not in {"eval_added", "eval_removed"}:
        for change in raw.changes:
            behavior = change.current_behavior or change.baseline_behavior
            if behavior.behavior_id in failures:
                assert change.verification_delta.value == "unchanged_gap"
    else:
        shared_changes = [
            change
            for change in raw.changes
            if change.current_behavior.subject == "shared"
            and change.current_behavior.behavior_type is BehaviorType.TOOL_FAILURE
        ]
        assert len(shared_changes) == 1
        assert shared_changes[0].verification_delta.value == (
            "coverage_improvement" if edit == "eval_added" else "coverage_regression"
        )
    # Explanation generation cannot mutate M9's input snapshots or serialized result.
    snapshot = comparison_json(raw)
    for f in [before, after]:
        enrich_rejection_explanations(
            f.behaviors, f.matching, discover_scope_roots(f.discovery, f.behaviors)
        )
    assert comparison_json(raw) == snapshot


def test_public_validator_solution_still_resolves_same_id_and_feedback(tmp_path):
    root = tmp_path / "example"
    copytree(PROJECT_ROOT / "examples/pydantic-ai-agent", root)
    first = scan_selected_scope(root, "refund_agent", observed_at=FIRST)
    finding = next(f for f in first.findings if f.behavior_subject == "validate_refund")
    store = FindingStore(root)
    store.record_feedback(
        finding.finding_id, FindingDisposition.ADD_EVAL, occurred_at=FIRST + timedelta(hours=1)
    )
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    scan_selected_scope(root, "refund_agent", observed_at=SECOND)
    resolved = store.get_finding(finding.finding_id)
    assert resolved.status is FindingStatus.RESOLVED
    assert resolved.coverage_status is CoverageStatus.COVERED
    assert resolved.current_disposition is FindingDisposition.ADD_EVAL
    assert resolved.structured_explanation.rejection_provenance.owner_identities == (
        "agent.py#refund_agent",
    )
    assert resolved.observed_resolution and not resolved.confirmed_impact


def test_cli_scan_findings_review_scoped_text_and_json(operational_repository):
    repository = operational_repository
    runner = CliRunner()
    scanned = runner.invoke(app, ["scan", str(repository), "--no-progress"])
    assert scanned.exit_code == 0, scanned.output
    assert "Registered by agent:" in scanned.output
    # M11 keeps the original full provenance diagnostics behind --details.
    findings = runner.invoke(app, ["findings", "--repository", str(repository), "--details"])
    assert findings.exit_code == 0 and "Explicit rejection outcome:" in findings.output
    reviewed = runner.invoke(app, ["review", "--repository", str(repository)], input="skip\n" * 30)
    assert reviewed.exit_code == 0 and "Registered callable:" in reviewed.output
    scoped = runner.invoke(app, ["scan", str(repository), "--scope", "first", "--json"])
    assert scoped.exit_code == 0, scoped.output
    payload = json.loads(scoped.output)
    context = next(
        f["structured_explanation"]["rejection_provenance"]
        for f in payload["findings"]
        if f["behavior_subject"] == "shared"
    )
    assert context["selected_owner_identity"] == "agent.py#first"
    assert context["owner_identities"] == ["agent.py#first", "agent.py#second"]
    assert '"excerpt"' not in scoped.output
    scoped_text = runner.invoke(app, ["scan", str(repository), "--scope", "first", "--no-progress"])
    assert scoped_text.exit_code == 0 and "Selected owner: agent.py#first" in scoped_text.output


def test_renderer_separates_declarations_conditions_and_existing_assessment(repository):
    _, _, explained = analysis(repository)
    detail = next(
        a.structured_explanation
        for a in explained.assessments
        if a.structured_explanation and a.structured_explanation.rejection_provenance
    )
    stream = StringIO()
    render_rejection_context(Console(file=stream, width=140), detail)
    text = stream.getvalue()
    assert "Registered by agent:" in text and "Agent declaration:" in text
    assert "Rejection condition:" in text and "Explicit rejection outcome:" in text
    assert "does not prove execution or eval coverage" in text
    assert "Executed by" not in text


def test_audit_never_executes_target_network_subprocess_or_sqlite(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No execution, network, or persistence allowed")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    report = run_rejection_audit()
    assert report["metrics"]["assessment_preservation"]["numerator"] > 0
    assert not (PROJECT_ROOT / FIXTURE / ".agentguard").exists()


def test_source_pin_changes_fail_audit(tmp_path):
    root = tmp_path / FIXTURE
    root.parent.mkdir(parents=True)
    copytree(PROJECT_ROOT / FIXTURE, root)
    (root / "agent.py").write_text('raise RuntimeError("must never execute")\n')
    with pytest.raises(ValueError, match="Pinned"):
        run_rejection_audit(project=tmp_path)


@pytest.mark.parametrize(
    "declaration",
    [
        'from pydantic_ai import Agent\nagent = Agent("test", tools=[reject])',
        'import pydantic_ai as ai\nagent = ai.Agent("test", tools=[reject])',
        'from pydantic_ai.agent import Agent as A\nagent = A("test", tools=[reject])',
        "from crewai import Agent\nagent = Agent(tools=[reject])",
        "from crewai.agent import Agent as A\nagent = A(tools=[reject])",
    ],
)
def test_supported_direct_constructor_registrations(tmp_path, declaration):
    source = (
        "def reject(amount):\n    if amount < 0:\n"
        '        raise ValueError("negative")\n    return amount\n\n' + declaration + "\n"
    )
    (tmp_path / "app.py").write_text(source)
    full, inventory, _ = analysis(tmp_path)
    contexts = rejection_provenance(full.behaviors, inventory)
    assert len(contexts) == 1
    assert contexts[0].owner_identities == ("app.py#agent",)
    assert contexts[0].registrations[0].kind == "constructor_tool"


@pytest.mark.parametrize("method", ["tool", "tool_plain", "output_validator"])
def test_supported_decorator_registrations(tmp_path, method):
    (tmp_path / "app.py").write_text(
        'from pydantic_ai import Agent, ModelRetry\nagent = Agent("test")\n'
        f"@agent.{method}\ndef reject(amount):\n"
        '    if amount < 0:\n        raise ModelRetry("negative")\n    return amount\n'
    )
    full, inventory, _ = analysis(tmp_path)
    contexts = rejection_provenance(full.behaviors, inventory)
    assert len(contexts) == 1
    assert contexts[0].registrations[0].kind == (
        "output_validator_callback" if method == "output_validator" else "decorator_tool"
    )


@pytest.mark.parametrize(
    "evidence,covered",
    [
        ("def test_reject():\n    with pytest.raises(ValueError):\n        reject(-1)\n", True),
        ("def test_reject():\n    reject(-1)\n", False),
        ("def test_reject():\n    with pytest.raises(ValueError):\n        reject(1)\n", False),
        ("def test_reject():\n    with pytest.raises(TypeError):\n        reject(-1)\n", False),
        ("def test_reject_ValueError():\n    assert True\n", False),
        ("def test_reject():\n    with pytest.raises(ValueError):\n        helper(-1)\n", False),
    ],
)
def test_enrichment_never_supplies_missing_pytest_verification(tmp_path, evidence, covered):
    (tmp_path / "app.py").write_text(
        'from pydantic_ai import Agent\nagent = Agent("test")\n'
        "@agent.tool_plain\ndef reject(amount):\n"
        '    if amount < 0:\n        raise ValueError("negative")\n    return amount\n'
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "evidence.py").write_text("import pytest\nfrom app import reject\n" + evidence)
    full, _, enriched = analysis(tmp_path)
    behavior = next(
        b for b in full.behaviors.behaviors if b.behavior_type is BehaviorType.TOOL_FAILURE
    )
    result = next(a for a in enriched.assessments if a.behavior_id == behavior.behavior_id)
    assert (result.coverage_status is CoverageStatus.COVERED) is covered
    assert without_context(enriched.model_dump()) == full.matching.model_dump()


def test_reversed_fact_traversal_produces_identical_contexts(repository):
    full, inventory, _ = analysis(repository)
    expected = rejection_provenance(full.behaviors, inventory)
    reversed_facts = full.behaviors.model_copy(
        update={
            "behaviors": tuple(reversed(full.behaviors.behaviors)),
            "callable_capabilities": tuple(reversed(full.behaviors.callable_capabilities)),
            "registration_relationships": tuple(
                reversed(full.behaviors.registration_relationships)
            ),
        }
    )
    assert (
        rejection_provenance(
            reversed_facts, inventory.model_copy(update={"roots": tuple(reversed(inventory.roots))})
        )
        == expected
    )
