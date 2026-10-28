"""Audit infrastructure correctness; discovery gaps are results, not test failures."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from shutil import copytree
from typing import Any

import pytest

from agentguard.extractors import extract_behaviors
from agentguard.models import BehaviorType
from agentguard.scanners import scan_repository
from tools.behavior_audit.models import Corpus, ExpectedBehavior
from tools.behavior_audit.runner import (
    DEFAULT_INVENTORY,
    PROJECT_ROOT,
    calculate_metrics,
    classify_repository,
    load_corpus,
    run_audit,
    serialize_report,
)


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return load_corpus()


@pytest.fixture(scope="module")
def report(corpus: Corpus) -> dict[str, Any]:
    return run_audit(corpus)


def _simple(corpus: Corpus) -> tuple[Path, ExpectedBehavior, Any]:
    repository = next(r for r in corpus.repositories if r.repository == "plain_registration")
    root = PROJECT_ROOT / repository.path
    expected = next(e for e in corpus.expectations if e.repository == repository.repository)
    behavior = extract_behaviors(scan_repository(root)).behaviors[0]
    return root, expected, behavior


def test_inventory_is_source_curated_and_covers_required_architectures(corpus: Corpus) -> None:
    assert len(corpus.repositories) == 14
    assert len(corpus.expectations) == 58
    assert len({r.path for r in corpus.repositories}) == 14
    assert {r.repository for r in corpus.repositories if r.architecture == "public_example"} == {
        "public-langgraph-agent",
        "public-crewai-agent",
        "public-pydantic-ai-agent",
    }
    assert all(e.registration_evidence and e.supporting_evidence for e in corpus.expectations)
    assert "behavior_id" not in DEFAULT_INVENTORY.read_text()
    assert all(
        not Path(r.path).is_absolute() and ".." not in Path(r.path).parts
        for r in corpus.repositories
    )


@pytest.mark.parametrize("damage", ["hash", "span", "anchor", "duplicate", "escape", "unknown"])
def test_inventory_rejects_stale_or_invalid_ground_truth(tmp_path: Path, damage: str) -> None:
    data = json.loads(DEFAULT_INVENTORY.read_text())
    if damage == "hash":
        hashes = data["repositories"][0]["source_hashes"]
        hashes[next(iter(hashes))] = "invalid"
    elif damage == "span":
        data["expectations"][0]["end_line"] = 99999
    elif damage == "anchor":
        data["expectations"][0]["source_anchor"] = "not present"
    elif damage == "duplicate":
        data["expectations"].append(data["expectations"][0])
    elif damage == "escape":
        data["repositories"][0]["path"] = "../outside"
    else:
        data["expectations"][0]["repository"] = "absent"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_corpus(path)


def test_exact_missing_negative_and_uncertain_classification(corpus: Corpus) -> None:
    root, expected, behavior = _simple(corpus)

    def classify(e: ExpectedBehavior, actual: tuple = (), *, complete: bool = True) -> str:
        return classify_repository(root, (e,), actual, complete=complete)[0][0]["classification"]

    assert classify(expected, (behavior,)) == "correctly_discovered"
    assert classify(expected) == "missed"
    assert classify(expected, complete=False) == "ambiguous"
    negative = expected.model_copy(update={"expected_discovery": "not_discovered"})
    assert classify(negative) == "correctly_absent"
    assert classify(negative, (behavior,)) == "unexpected"
    assert classify(negative, complete=False) == "ambiguous"
    uncertain = expected.model_copy(update={"review_status": "uncertain"})
    assert classify(uncertain, (behavior,)) == "ambiguous"


@pytest.mark.parametrize("damage", ["path", "line", "text", "missing", "span"])
def test_source_reference_errors_never_count_as_full_discovery(corpus: Corpus, damage: str) -> None:
    root, expected, behavior = _simple(corpus)
    evidence = behavior.evidence[0]
    if damage == "missing":
        behavior = behavior.model_copy(update={"evidence": ()})
    elif damage == "span":
        expected = expected.model_copy(update={"start_line": 999, "end_line": 1000})
    else:
        updates = {
            "path": {"source_file": "../outside.py"},
            "line": {"start_line": 999, "end_line": 1000},
            "text": {"excerpt": "invented source"},
        }[damage]
        behavior = behavior.model_copy(update={"evidence": (evidence.model_copy(update=updates),)})
    rows, actual = classify_repository(root, (expected,), (behavior,), complete=True)
    assert rows[0]["classification"] == "partial"
    assert rows[0]["gap_category"] == "incorrect_source_reference"
    assert actual[0]["review_status"] == "unreviewed"


def test_partial_container_and_identity_ambiguity_are_not_full_discovery(corpus: Corpus) -> None:
    root, expected, behavior = _simple(corpus)
    selector = expected.selector.model_copy(
        update={
            "behavior_types": (BehaviorType.FALLBACK,),
            "related_types": (BehaviorType.TOOL_INVOCATION,),
        }
    )
    partial = expected.model_copy(update={"selector": selector})
    rows, _ = classify_repository(root, (partial,), (behavior,), complete=True)
    assert rows[0]["classification"] == "partial"
    duplicate = behavior.model_copy(update={"behavior_id": "different-id"})
    rows, _ = classify_repository(root, (expected,), (behavior, duplicate), complete=True)
    assert rows[0]["classification"] == "ambiguous"
    duplicate_expected = expected.model_copy(update={"expectation_id": "different-expectation"})
    rows, _ = classify_repository(root, (expected, duplicate_expected), (behavior,), complete=True)
    assert {r["classification"] for r in rows} == {"ambiguous"}


def test_unreviewed_extras_and_unknown_relevance_are_explicit(corpus: Corpus) -> None:
    root, expected, behavior = _simple(corpus)
    _, actual = classify_repository(root, (), (behavior,), complete=True)
    assert actual[0]["classification"] == "unexpected_unreviewed"
    assert actual[0]["role"] == "unknown"
    metrics = calculate_metrics([{"actual": actual, "expectations": []}])
    assert metrics["structural_discovery_precision"]["denominator"] == 0
    assert metrics["excluded_unreviewed_extractions"] == 1
    unknown = expected.model_copy(update={"operational_relevance": "unknown"})
    rows, actual = classify_repository(root, (unknown,), (behavior,), complete=True)
    assert rows[0]["classification"] == "correctly_discovered"
    assert actual[0]["structurally_valid"] is True
    assert actual[0]["operational_relevance"] == "unknown"


def test_metrics_have_honest_denominators_and_preserve_discovery_gaps(report: dict) -> None:
    metrics = report["metrics"]
    assert metrics["discovery_recall"] == {"numerator": 30, "denominator": 50, "rate": 0.6}
    assert metrics["supported_pattern_recall"]["numerator"] == 30
    assert metrics["supported_pattern_recall"]["denominator"] == 30
    assert metrics["structural_discovery_precision"] == {
        "numerator": 30,
        "denominator": 30,
        "rate": 1.0,
    }
    counts = Counter(e["classification"] for r in report["repositories"] for e in r["expectations"])
    assert counts == {
        "correctly_discovered": 30,
        "missed": 13,
        "partial": 5,
        "ambiguous": 3,
        "correctly_absent": 7,
    }
    assert metrics["source_accuracy"]["correct_locations"] == 30
    assert metrics["excluded_uncertain_expectations"] == 1
    assert metrics["roles"] == {
        "agent_facing": 16,
        "orchestrated_internal": 14,
        "implementation_detail": 0,
        "unknown": 0,
    }
    assert metrics["operational_relevance"]["unknown"] == 1
    assert metrics["by_architecture"]["public_example"]["discovery_recall"]["denominator"] == 23


CONTROLLED = [
    "decorated_tool",
    "plain_registration",
    "adapter_delegation",
    "shared_tools",
    "skill_dispatch",
    "graph_routing",
    "failure_fallback",
    "internal_helpers",
    "multiple_entries",
    "dynamic_registration",
    "negative_controls",
]


@pytest.mark.parametrize("fixture", CONTROLLED)
@pytest.mark.parametrize("directory", ["module", "v1", "v2", "legacy"])
def test_equivalent_structures_are_independent_of_directory_names(
    corpus: Corpus,
    report: dict,
    tmp_path: Path,
    fixture: str,
    directory: str,
) -> None:
    repository = next(r for r in corpus.repositories if r.repository == fixture)
    root = tmp_path / directory
    copytree(PROJECT_ROOT / repository.path, root)
    expected = tuple(
        e.model_copy(update={"source_file": f"{directory}/{e.source_file}"})
        for e in corpus.expectations
        if e.repository == fixture
    )
    scan = scan_repository(tmp_path)
    extraction = extract_behaviors(scan)
    rows, actual = classify_repository(
        tmp_path,
        expected,
        extraction.behaviors,
        complete=extraction.completeness.value == "complete",
    )
    original = next(r for r in report["repositories"] if r["repository"] == fixture)
    assert {r["expectation"]["expectation_id"]: r["classification"] for r in rows} == {
        r["expectation"]["expectation_id"]: r["classification"] for r in original["expectations"]
    }
    assert Counter(
        (r["behavior_type"], r["subject"], r["source_symbol"]) for r in actual
    ) == Counter((r["behavior_type"], r["subject"], r["source_symbol"]) for r in original["actual"])


def test_audit_is_read_only_and_never_executes_targets(
    corpus: Corpus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = next(r for r in corpus.repositories if r.repository == "plain_registration")
    root = tmp_path / "target"
    copytree(PROJECT_ROOT / repository.path, root)
    (root / ".agentguard").mkdir()
    state = root / ".agentguard/agentguard.db"
    state.write_bytes(b"existing state must remain untouched")
    marker = tmp_path / "executed"
    with (root / "app.py").open("a") as file:
        file.write(f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    target = repository.model_copy(update={"path": "target"})
    isolated = corpus.model_copy(
        update={
            "repositories": (target,),
            "expectations": tuple(
                e for e in corpus.expectations if e.repository == repository.repository
            ),
        }
    )
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Audit attempted network, execution, or persistence")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    first = serialize_report(run_audit(isolated, project=tmp_path))
    assert first == serialize_report(run_audit(isolated, project=tmp_path))
    assert not marker.exists()
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    state.unlink()
    state.parent.rmdir()
    run_audit(isolated, project=tmp_path)
    assert not state.parent.exists()


def test_report_is_reproducible_and_golden_artifact_matches(corpus: Corpus, report: dict) -> None:
    rendered = serialize_report(report)
    assert rendered == serialize_report(run_audit(corpus))
    assert rendered == (PROJECT_ROOT / "docs/behavior-discovery-audit.json").read_text()
    assert str(PROJECT_ROOT) not in rendered
    assert '"excerpt"' not in rendered
    for repository in corpus.repositories:
        for file, digest in repository.source_hashes.items():
            assert (
                hashlib.sha256((PROJECT_ROOT / repository.path / file).read_bytes()).hexdigest()
                == digest
            )


@pytest.mark.parametrize("destination", ["inventory", "source", "state"])
def test_development_command_rejects_writes_to_audited_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destination: str,
) -> None:
    from tools.behavior_audit.__main__ import main

    targets = {
        "inventory": DEFAULT_INVENTORY,
        "source": PROJECT_ROOT / "tests/fixtures/behavior_audit/plain_registration/app.py",
        "state": tmp_path / ".agentguard/agentguard.db",
    }
    target = targets[destination]
    before = target.read_bytes() if target.exists() else None
    monkeypatch.setattr("sys.argv", ["behavior_audit", "--output", str(target)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert (target.read_bytes() if target.exists() else None) == before
    assert not (tmp_path / ".agentguard").exists()


def test_run_boundary_rejects_unscoped_repository(corpus: Corpus, tmp_path: Path) -> None:
    repository = corpus.repositories[0].model_copy(update={"path": "../outside"})
    outside = corpus.model_copy(update={"repositories": (repository,)})
    with pytest.raises(ValueError, match="explicitly curated"):
        run_audit(outside, project=tmp_path)
