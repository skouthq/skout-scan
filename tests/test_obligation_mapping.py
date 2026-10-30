"""Development-only obligations cannot affect production verification or persistence."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from pathlib import Path
from shutil import copy2, copytree

import pytest
from pydantic import ValidationError

from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    BehaviorExtractionResult,
    ComparisonBaseline,
    EvalParseResult,
    RegistrationResolution,
    ScanCompleteness,
    VerificationEvidenceType,
)
from agentguard.scanners import scan_repository
from tools.behavior_audit.delegation import run_delegation_audit
from tools.behavior_audit.obligation_audit import INVENTORY, run_obligation_audit
from tools.behavior_audit.obligation_models import Eligibility, MatcherContract, ObligationCandidate
from tools.behavior_audit.obligations import map_obligations
from tools.behavior_audit.orchestration import run_orchestration_audit
from tools.behavior_audit.registrations import run_report
from tools.behavior_audit.runner import PROJECT_ROOT, load_corpus, run_audit, serialize_report

FIXTURES = PROJECT_ROOT / "tests/fixtures/obligation_audit"
DELEGATION = PROJECT_ROOT / "tests/fixtures/delegation_audit"


def facts(root: Path) -> BehaviorExtractionResult:
    return extract_behaviors(scan_repository(root))


def eligible(root: Path):
    return [
        c for c in map_obligations(facts(root)).candidates if c.eligibility is Eligibility.ELIGIBLE
    ]


def test_independent_ground_truth_decisions_and_traceability() -> None:
    report = run_obligation_audit()
    m = report["metrics"]
    assert (
        m["eligibility_precision"]
        == m["eligibility_recall"]
        == {"numerator": 10, "denominator": 10}
    )
    assert m["reviewed_decisions"] == {"numerator": 55, "denominator": 55}
    assert m["abstention_correctness"] == {"numerator": 45, "denominator": 45}
    assert m["source_traceability"] == {"numerator": 55, "denominator": 55}
    assert m["source_references"] == {"numerator": 134, "denominator": 134}
    assert m["actionability_proxy"] == {"numerator": 10, "denominator": 10}
    assert m["pre_dedup_duplicate_rate"] == {"numerator": 9, "denominator": 64}
    assert m["residual_duplicate_rate"] == {"numerator": 0, "denominator": 55}
    assert m["unreviewed_candidates"] == 0
    assert all(
        row["correct"] for repo in report["repositories"] for row in repo["absence_expectations"]
    )
    assert set(m["statuses"]) == set(Eligibility)
    serialized = serialize_report(report)
    assert serialized == serialize_report(run_obligation_audit())
    assert serialized == (PROJECT_ROOT / "docs/verification-obligation-audit.json").read_text()
    assert '"excerpt"' not in serialized and str(PROJECT_ROOT) not in serialized


def test_shared_ownership_and_existing_branch_failure_are_enriched_once() -> None:
    source = facts(FIXTURES)
    mapping = map_obligations(source)
    current = [c for c in mapping.candidates if c.eligibility is Eligibility.ELIGIBLE]
    assert len(current) == 1
    c = current[0]
    assert c.classification == "existing_behavior_enrichment"
    assert len(c.originating_relationship_ids) == len(c.existing_behavior_ids) == 2
    assert c.raw_eligible_mappings == 4 and mapping.duplicates_removed == 3
    assert c.obligation_id in c.existing_behavior_ids
    assert c.obligation_id == next(
        b.behavior_id for b in source.behaviors if b.behavior_type.value == "tool_failure"
    )
    assert c.matcher_compatibility is MatcherContract.EXISTING
    assert all(
        c.obligation_id is None
        for c in mapping.candidates
        if c.eligibility is not Eligibility.ELIGIBLE
    )


def test_registration_no_contract_and_delegation_are_context() -> None:
    for root in [PROJECT_ROOT / "tests/fixtures/registration_audit", DELEGATION]:
        for c in map_obligations(facts(root)).candidates:
            if c.relationship_kind in {"constructor_tool", "decorator_tool", "one_hop_delegation"}:
                assert c.eligibility is not Eligibility.ELIGIBLE
    child = next(
        c
        for c in map_obligations(facts(DELEGATION)).candidates
        if c.target_symbol == "Storage.fetch"
    )
    assert child.eligibility is Eligibility.CONTEXT_ONLY
    assert (
        child.obligation_id is None
    )  # Its referenced body has a raise; propagation was never extracted.


def test_new_relations_have_testable_claims_but_require_new_verification_contracts() -> None:
    current = eligible(DELEGATION)
    assert len(current) == 5
    for c in current:
        assert c.classification == "new_obligation" and not c.existing_behavior_ids
        assert c.matcher_compatibility is MatcherContract.EXTENSION
        assert c.parent_callable_ids and c.target_callable_id and c.condition and c.expected_outcome
        assert c.obligation_id.startswith("audit_obligation_")
        assert len(c.evidence_requirement.dimensions) == 3
    routes = [c for c in current if c.dispatch_key]
    assert {c.dispatch_key for c in routes} == {"search", "retrieve", "lookup"}
    assert len({c.obligation_id for c in routes}) == 3
    fallbacks = [c for c in current if c.exception_condition]
    assert all("except" in c.condition and "recovery" in c.expected_outcome for c in fallbacks)


def test_nonagent_helpers_do_not_become_candidates() -> None:
    source = facts(PROJECT_ROOT / "tests/fixtures/behavior_audit/internal_helpers")
    assert not map_obligations(source).candidates
    assert not [
        c for c in map_obligations(facts(DELEGATION)).candidates if c.source_file == "negative.py"
    ]


def test_pure_mapping_is_order_independent_and_deduplicates_repeated_inputs() -> None:
    source = facts(FIXTURES)
    before = map_obligations(source)
    reordered = source.model_copy(
        update={
            "behaviors": tuple(reversed(source.behaviors)),
            "callable_capabilities": tuple(reversed(source.callable_capabilities)),
            "registration_relationships": tuple(reversed(source.registration_relationships)),
        }
    )
    assert map_obligations(reordered) == before
    repeated = source.model_copy(
        update={
            "behaviors": source.behaviors * 2,
            "registration_relationships": source.registration_relationships * 2,
        }
    )
    assert map_obligations(repeated) == before


def test_mapping_neither_reads_source_nor_interprets_excerpts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = facts(DELEGATION)
    before = map_obligations(source)

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure mapping attempted source access")

    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert map_obligations(source) == before
    source = source.model_copy(update={"behaviors": ()})
    # Definitions may contain raises; only existing Behavior facts can create rejection claims.
    assert not any(
        c.obligation_type == "explicit_rejection" for c in map_obligations(source).candidates
    )


@pytest.mark.parametrize(
    "status", [RegistrationResolution.UNRESOLVED, RegistrationResolution.AMBIGUOUS]
)
def test_unresolved_relationships_cannot_create_obligations(status: RegistrationResolution) -> None:
    source = facts(DELEGATION)
    changed = source.model_copy(
        update={
            "registration_relationships": tuple(
                r.model_copy(update={"resolution": status})
                for r in source.registration_relationships
            )
        }
    )
    mapped = map_obligations(changed)
    assert not any(c.eligibility is Eligibility.ELIGIBLE for c in mapped.candidates)
    assert all(c.obligation_id is None for c in mapped.candidates)


@pytest.mark.parametrize(
    "missing", ["parent_provenance", "parent_callable_id", "definition", "registry_evidence"]
)
def test_missing_dispatch_provenance_abstains(missing: str) -> None:
    source = facts(DELEGATION)
    row = next(
        r
        for r in source.registration_relationships
        if r.kind == "literal_dispatch" and r.resolution is RegistrationResolution.RESOLVED
    )
    updated = row.model_copy(update={missing: () if missing == "parent_provenance" else None})
    result = map_obligations(
        source.model_copy(update={"registration_relationships": (updated,), "behaviors": ()})
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].eligibility is Eligibility.INSUFFICIENT
    assert result.candidates[0].obligation_id is None


def test_missing_handler_context_and_failed_extraction_abstain() -> None:
    source = facts(DELEGATION)
    row = next(
        r
        for r in source.registration_relationships
        if r.kind == "exception_fallback" and r.resolution is RegistrationResolution.RESOLVED
    )
    result = map_obligations(
        source.model_copy(
            update={
                "registration_relationships": (row.model_copy(update={"conditions": ()}),),
                "behaviors": (),
            }
        )
    )
    assert result.candidates[0].eligibility is Eligibility.INSUFFICIENT
    assert not any(
        c.eligibility is Eligibility.ELIGIBLE
        for c in map_obligations(
            source.model_copy(update={"completeness": ScanCompleteness.FAILED})
        ).candidates
    )


def test_unavailable_existing_behavior_is_not_eligible() -> None:
    source = facts(FIXTURES)
    result = map_obligations(
        source.model_copy(
            update={"unavailable_behavior_ids": tuple(b.behavior_id for b in source.behaviors)}
        )
    )
    assert not any(c.eligibility is Eligibility.ELIGIBLE for c in result.candidates)


@pytest.mark.parametrize(
    "field,value",
    [
        ("condition", None),
        ("expected_outcome", None),
        ("source_evidence", ()),
        ("matcher_compatibility", "not_assessable"),
    ],
)
def test_eligible_model_requires_explicit_claim(field: str, value: object) -> None:
    payload = eligible(FIXTURES)[0].model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        ObligationCandidate.model_validate(payload)


def test_context_model_cannot_claim_obligation_identity() -> None:
    payload = next(
        c
        for c in map_obligations(facts(FIXTURES)).candidates
        if c.eligibility is Eligibility.CONTEXT_ONLY
    ).model_dump()
    payload["obligation_id"] = "invented"
    with pytest.raises(ValidationError):
        ObligationCandidate.model_validate(payload)


@pytest.mark.parametrize("prefix", ["", "\n\n# unrelated line movement\n"])
def test_existing_identity_survives_line_moves_and_owner_rename(
    tmp_path: Path, prefix: str
) -> None:
    (tmp_path / "agent.py").write_text((FIXTURES / "agent.py").read_text())
    before = eligible(tmp_path)[0]
    text = (tmp_path / "agent.py").read_text().replace("first", "renamed")
    (tmp_path / "agent.py").write_text(prefix + text)
    after = eligible(tmp_path)[0]
    assert before.obligation_id == after.obligation_id
    assert before.candidate_id == after.candidate_id
    assert before.originating_relationship_ids != after.originating_relationship_ids


def test_route_identity_changes_for_material_key_and_preserves_formatting(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.py"
    original = (DELEGATION / "dispatch.py").read_text()
    path.write_text(original)
    before = {c.obligation_id for c in eligible(tmp_path)}
    path.write_text("\n# comment\n" + original.replace("(key, query)", "( key, query )"))
    assert {c.obligation_id for c in eligible(tmp_path)} == before
    path.write_text(original.replace('"lookup": search', '"other": search'))
    assert {c.obligation_id for c in eligible(tmp_path)} != before


def test_observed_evidence_agreement_and_known_graph_ownership_gap() -> None:
    report = run_obligation_audit()
    rows = report["evidence_experiments"]
    assert report["metrics"]["m8_experiment_agreement"] == {"numerator": 20, "denominator": 21}
    disagree = [
        r["case"]["case_id"] for r in rows if r["agrees_with_required_sufficiency"] is False
    ]
    assert disagree == ["route_supported"]
    historical = json.loads(
        (PROJECT_ROOT / "docs/verification-obligation-audit-m10-2d.json").read_text()
    )
    assert historical["metrics"]["m8_experiment_agreement"] == {"numerator": 18, "denominator": 21}
    assert [r["case"] for r in rows] == [r["case"] for r in historical["evidence_experiments"]]
    for row in rows:
        if row["case"]["obligation_type"] == "explicit_rejection":
            assert row["agrees_with_required_sufficiency"] is True
        if row["case"]["obligation_type"] in {
            "literal_route_selection",
            "conditional_fallback_invocation",
        }:
            assert row["assessment"] is None and row["actual_covered"] is None
            assert row["agrees_with_required_sufficiency"] is None
    assert sum(r["assessment"] is None for r in rows) == 12


def test_public_solution_evidence_does_not_change_obligation_identity(tmp_path: Path) -> None:
    root = tmp_path / "public"
    copytree(PROJECT_ROOT / "examples/pydantic-ai-agent", root)
    before = analyze_snapshot(root)
    obligation_before = eligible(root)
    assert len(obligation_before) == 1
    copy2(root / "tests/solutions/test_retry.py.example", root / "tests/test_retry.py")
    after = analyze_snapshot(root)
    assert eligible(root) == obligation_before
    id_ = obligation_before[0].obligation_id
    assert (
        next(a for a in after.matching.assessments if a.behavior_id == id_).coverage_status.value
        == "covered"
    )
    baseline = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    unchanged = comparison_json(
        compare_inventories(before, after, baseline=baseline, repository="[audit]")
    )
    map_obligations(after.behaviors)
    assert (
        comparison_json(compare_inventories(before, after, baseline=baseline, repository="[audit]"))
        == unchanged
    )
    assert not (root / ".agentguard").exists()


def test_all_production_snapshots_and_existing_reports_remain_unchanged() -> None:
    baseline = json.loads((FIXTURES / "compatibility_baseline.json").read_text())

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    for path, expected in baseline.items():
        result = analyze_snapshot(PROJECT_ROOT / path)
        assert (
            digest([x.model_dump(mode="json") for x in result.behaviors.behaviors])
            == expected["behaviors"]
        )
        assert (
            digest([x.model_dump(mode="json") for x in result.behaviors.registration_relationships])
            == expected["relationships"]
        )
        assert (
            digest([x.model_dump(mode="json") for x in result.behaviors.callable_capabilities])
            == expected["capabilities"]
        )
        assert (
            digest([x.model_dump(mode="json") for x in result.matching.assessments])
            == expected["assessments"]
        )
        assert result.finding_ids == expected["finding_ids"]
    for name, run in [
        ("behavior-discovery", lambda: run_audit(load_corpus())),
        ("registration-relationships", run_report),
        ("orchestration-relationships", run_orchestration_audit),
        ("delegation-relationships", run_delegation_audit),
    ]:
        assert serialize_report(run()) == (PROJECT_ROOT / f"docs/{name}-audit.json").read_text()


def test_ground_truth_is_not_consulted_by_mapper(tmp_path: Path) -> None:
    truth = json.loads(INVENTORY.read_text())
    truth["expectations"][2]["eligibility"] = "context_only"
    catalog = tmp_path / "inventory.json"
    catalog.write_text(json.dumps(truth))
    original = run_obligation_audit()
    changed = run_obligation_audit(catalog)
    assert changed["metrics"]["reviewed_decisions"]["numerator"] == 54
    assert [r["candidates"] for r in original["repositories"]] == [
        r["candidates"] for r in changed["repositories"]
    ]


def test_audit_preserves_state_and_never_executes_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    target = project / "target"
    copytree(FIXTURES, target)
    truth = json.loads(INVENTORY.read_text())
    truth["repositories"] = [r for r in truth["repositories"] if r["repository"] == "controlled"]
    truth["expectations"] = [e for e in truth["expectations"] if e["repository"] == "controlled"]
    truth["absence_expectations"] = []
    truth["evidence_cases"] = [
        e for e in truth["evidence_cases"] if e["repository"] == "controlled"
    ]
    truth["repositories"][0]["path"] = truth["evidence_root"] = "target"
    source = target / "agent.py"
    source.write_text(source.read_text() + "\nraise AssertionError('target executed')\n")
    truth["repositories"][0]["source_hashes"]["agent.py"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    catalog = project / "inventory.json"
    catalog.write_text(json.dumps(truth))
    state = target / ".agentguard/agentguard.db"
    state.parent.mkdir()
    state.write_bytes(b"saved user feedback and history")
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Execution, network or persistence attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    run_obligation_audit(catalog, project=project)
    assert before == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    state.unlink()
    state.parent.rmdir()
    run_obligation_audit(catalog, project=project)
    assert not state.parent.exists()


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown_repository", "stale_hash", "outside_root", "wrong_anchor"]
)
def test_invalid_corpus_fails_clearly(tmp_path: Path, mutation: str) -> None:
    truth = json.loads(INVENTORY.read_text())
    if mutation == "duplicate":
        truth["expectations"].append(truth["expectations"][0])
    elif mutation == "unknown_repository":
        truth["expectations"][0]["repository"] = "unknown"
    elif mutation == "stale_hash":
        truth["repositories"][0]["source_hashes"]["agent.py"] = "0" * 64
    elif mutation == "outside_root":
        truth["repositories"][0]["path"] = "../outside"
    else:
        truth["expectations"][0]["anchor"] = "wrong anchor"
    catalog = tmp_path / "inventory.json"
    catalog.write_text(json.dumps(truth))
    with pytest.raises(ValueError):
        run_obligation_audit(catalog)


def test_dispatch_keeps_control_context_without_guaranteeing_parent_execution(
    tmp_path: Path,
) -> None:
    source = (DELEGATION / "dispatch.py").read_text()
    source = source.replace(
        "    return HANDLERS[key](query)", "    if query:\n        return HANDLERS[key](query)"
    )
    (tmp_path / "app.py").write_text(source)
    candidates = eligible(tmp_path)
    assert len(candidates) == 3
    assert all(
        "if query" in c.condition and c.structural_conditions == ("if query",) for c in candidates
    )
    assert all("recorded lookup site" in c.condition for c in candidates)


@pytest.mark.parametrize(
    "category",
    [
        VerificationEvidenceType.REQUIREMENT,
        VerificationEvidenceType.RUNTIME_GUARDRAIL,
        VerificationEvidenceType.QUALITY_OBSERVATION,
    ],
)
def test_non_verifying_categories_never_establish_obligation_coverage(category) -> None:
    source = facts(FIXTURES)
    b = next(b for b in source.behaviors if b.behavior_type.value == "tool_failure")
    parsed = parse_eval_artifacts(scan_repository(FIXTURES))
    scenario = next(s for s in parsed.scenarios if s.name == "test_failure_verified")
    scenario = scenario.model_copy(update={"evidence_type": category})
    matched = match_behaviors_to_evals(
        source.model_copy(update={"behaviors": (b,)}),
        EvalParseResult(scenarios=(scenario,), completeness=ScanCompleteness.COMPLETE),
    )
    assert matched.assessments[0].coverage_status.value == "potentially_uncovered"
