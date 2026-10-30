"""Explicit orchestration facts never substitute for execution or eval evidence."""

import ast
import hashlib
import json
import socket
import sqlite3
import subprocess
from pathlib import Path
from shutil import copy2, copytree
from typing import Any

import pytest

from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.extractors import extract_behaviors
from agentguard.extractors.delegation import DISCOVERY_FIELDS
from agentguard.extractors.orchestration import ORCHESTRATION_KINDS, extract_orchestration
from agentguard.models import ComparisonBaseline, RegistrationRelationship, RegistrationResolution
from agentguard.scanners import scan_repository
from tools.behavior_audit.orchestration import run_orchestration_audit
from tools.behavior_audit.runner import PROJECT_ROOT, load_corpus, serialize_report

FIXTURES = PROJECT_ROOT / "tests/fixtures/orchestration_audit"
GRAPH = """from langgraph.graph import StateGraph

def review(state):
    return state

graph = StateGraph(dict)
graph.add_node("review", review)
"""
VALIDATOR = """from pydantic_ai import Agent
agent = Agent("test")
@agent.output_validator
def validate(ctx, output):
    return output
"""
CREW = """from crewai import Agent, Task
worker = Agent(role="reader")
task = Task(description="read", agent=worker)
"""


def extract(source: str):
    return extract_orchestration("app.py", ast.parse(source), source)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize(
    "imports,constructor",
    [
        ("from langgraph.graph import StateGraph", "StateGraph"),
        ("from langgraph.graph import StateGraph as Builder", "Builder"),
        ("import langgraph.graph as lg", "lg.StateGraph"),
        ("import langgraph", "langgraph.graph.StateGraph"),
    ],
)
@pytest.mark.parametrize("async_prefix", ["", "async "])
def test_graph_provenance_and_async_callbacks(
    imports: str, constructor: str, async_prefix: str
) -> None:
    source = (
        f"{imports}\n{async_prefix}def callback(state): return state\n"
        f"graph={constructor}(dict)\ngraph.add_node('review', callback)"
    )
    result = extract(source)
    assert len(result.relationships) == len(result.capabilities) == 1
    relationship = result.relationships[0]
    assert relationship.kind == "graph_node_callback"
    assert relationship.owner_identity == "app.py#graph"
    assert relationship.registered_identity == "review"
    assert relationship.resolution is RegistrationResolution.RESOLVED
    assert relationship.registration.excerpt == "graph.add_node('review', callback)"
    assert relationship.definition.excerpt.startswith(f"{async_prefix}def callback")


def test_shared_callback_distinct_nodes_and_same_name_across_graphs() -> None:
    result = extract(
        GRAPH
        + """other = StateGraph(dict)
graph.add_node("copy", review)
other.add_node("review", review)
"""
    )
    assert len(result.relationships) == 3
    assert len(result.capabilities) == 1
    assert len({r.relationship_id for r in result.relationships}) == 3
    duplicate = extract(GRAPH + 'graph.add_node("review", review)\n')
    assert len(duplicate.relationships) == len(duplicate.capabilities) == 1


@pytest.mark.parametrize(
    "source",
    [
        GRAPH.replace("from langgraph.graph import StateGraph", "from unrelated import StateGraph"),
        GRAPH.replace("graph = StateGraph(dict)", "graph = factory()"),
        GRAPH.replace("graph = StateGraph(dict)", "graph = StateGraph(dict)\nalias=graph").replace(
            "graph.add_node", "alias.add_node"
        ),
        GRAPH.replace("graph = StateGraph(dict)", "StateGraph = other\ngraph = StateGraph(dict)"),
        GRAPH.replace(
            "graph = StateGraph(dict)", "class StateGraph: pass\ngraph = StateGraph(dict)"
        ),
        GRAPH.replace(
            'graph.add_node("review", review)', 'graph.add_node(node="review", action=review)'
        ),
    ],
)
def test_unknown_or_unsupported_graph_forms_do_not_gain_relationships(source: str) -> None:
    assert not extract(source).relationships


@pytest.mark.parametrize(
    "target", ["external", "lambda state: state", "factory()", "adapter.read", "alias"]
)
def test_unsupported_callback_keeps_actual_registration_without_definition(target: str) -> None:
    source = "from external import external\n" + GRAPH.replace(
        '"review", review)', f'"review", {target})'
    )
    result = extract(source)
    relationship = result.relationships[0]
    assert relationship.resolution is RegistrationResolution.UNRESOLVED
    assert relationship.referenced_symbol == target
    assert relationship.definition is None and relationship.callable_id is None
    assert not result.capabilities


@pytest.mark.parametrize(
    "change",
    [
        "graph=StateGraph(dict)",
        "graph=other",
        "graph.add_node=other",
        "setattr(graph, 'add_node', other)",
    ],
)
def test_reassigned_or_mutated_graph_is_ambiguous(change: str) -> None:
    result = extract(GRAPH + change)
    assert result.relationships[0].resolution is RegistrationResolution.AMBIGUOUS
    assert result.relationships[0].definition is None
    assert not result.capabilities


def test_dynamic_node_and_ambiguous_callback_are_not_resolved() -> None:
    dynamic = extract(GRAPH.replace('"review", review)', "node_name, review)"))
    assert dynamic.relationships[0].registered_identity is None
    assert dynamic.relationships[0].resolution is RegistrationResolution.UNRESOLVED
    ambiguous = extract(GRAPH + "\ndef review(state): return other\n")
    assert ambiguous.relationships[0].resolution is RegistrationResolution.AMBIGUOUS
    conflict = extract(GRAPH + 'def other(state): return state\ngraph.add_node("review", other)\n')
    assert len(conflict.relationships) == 2
    assert all(r.resolution is RegistrationResolution.AMBIGUOUS for r in conflict.relationships)
    assert not conflict.capabilities


@pytest.mark.parametrize(
    "imports,agent,task",
    [
        ("from crewai import Agent, Task", "Agent", "Task"),
        ("from crewai import Agent as A, Task as T", "A", "T"),
        ("import crewai as crew", "crew.Agent", "crew.Task"),
    ],
)
def test_task_executor_provenance_and_multiple_tasks(imports: str, agent: str, task: str) -> None:
    result = extract(f"""{imports}
worker={agent}(role="reader")
first={task}(agent=worker)
second={task}(agent=worker, context=[first])
context_only={task}(context=[second])
""")
    assert len(result.relationships) == 2
    assert {r.owner_identity for r in result.relationships} == {"app.py#first", "app.py#second"}
    assert {r.executor_identity for r in result.relationships} == {"app.py#worker"}
    assert all(r.resolution is RegistrationResolution.RESOLVED for r in result.relationships)
    assert all(r.definition.source_symbol == "worker" for r in result.relationships)
    assert not result.capabilities  # Agent instances are not callable tool definitions.


@pytest.mark.parametrize(
    "modification",
    [
        "worker = imported_agent",
        "worker = make_agent()",
        "worker = Agent(role='other')",
    ],
)
def test_reassigned_executor_remains_ambiguous(modification: str) -> None:
    relationship = extract(CREW + modification).relationships[0]
    assert relationship.resolution is RegistrationResolution.AMBIGUOUS
    assert relationship.executor_identity is None and relationship.definition is None


@pytest.mark.parametrize("reference", ["imported_agent", "make_agent()", "agents[0]"])
def test_dynamic_or_imported_executor_is_unresolved(reference: str) -> None:
    relationship = extract(CREW.replace("agent=worker", f"agent={reference}")).relationships[0]
    assert relationship.resolution is RegistrationResolution.UNRESOLVED
    assert relationship.definition is None


@pytest.mark.parametrize(
    "source",
    [
        CREW.replace("from crewai import Agent, Task", "from unrelated import Agent, Task"),
        CREW.replace("task = Task", "Task = factory\ntask = Task"),
        CREW.replace("agent=worker", "context=[worker]"),
        CREW.replace("task = Task", "task = make_task"),
    ],
)
def test_noncrewai_task_or_absent_executor_does_not_gain_assignment(source: str) -> None:
    assert not extract(source).relationships


@pytest.mark.parametrize(
    "imports,constructor",
    [
        ("from pydantic_ai import Agent", "Agent"),
        ("from pydantic_ai import Agent as Assistant", "Assistant"),
        ("import pydantic_ai as pai", "pai.Agent"),
    ],
)
@pytest.mark.parametrize("async_prefix", ["", "async "])
def test_validator_provenance_and_async(imports: str, constructor: str, async_prefix: str) -> None:
    source = (
        VALIDATOR.replace("from pydantic_ai import Agent", imports)
        .replace('Agent("test")', f'{constructor}("test")')
        .replace("def validate", f"{async_prefix}def validate")
    )
    relationship = extract(source).relationships[0]
    assert relationship.kind == "output_validator_callback"
    assert relationship.resolution is RegistrationResolution.RESOLVED
    assert relationship.registered_identity == "app.py#validate"
    assert relationship.registration.excerpt == "agent.output_validator"
    assert relationship.definition.source_symbol == "validate"


@pytest.mark.parametrize(
    "source",
    [
        VALIDATOR.replace("from pydantic_ai import Agent", "from unrelated import Agent"),
        VALIDATOR.replace('agent = Agent("test")', "agent = make_agent()"),
        VALIDATOR.replace("@agent.output_validator", "@agent.output_validator()"),
        VALIDATOR.replace('agent = Agent("test")', "Agent = unknown\nagent = Agent('test')"),
    ],
)
def test_unknown_or_dynamic_validator_forms_do_not_gain_relationships(source: str) -> None:
    assert not extract(source).relationships


def test_validator_rebinding_and_decorator_ambiguity_remain_uncertain() -> None:
    for source in [VALIDATOR + "agent = other\n", VALIDATOR + "validate = other\n"]:
        relationship = extract(source).relationships[0]
        assert relationship.resolution is RegistrationResolution.AMBIGUOUS
        assert relationship.definition is None
    decorated = extract(
        VALIDATOR.replace("@agent.output_validator", "@unknown\n@agent.output_validator")
    )
    assert decorated.relationships[0].resolution is RegistrationResolution.UNRESOLVED


@pytest.mark.parametrize("source", [GRAPH, CREW, VALIDATOR])
def test_ids_ignore_formatting_and_unrelated_line_moves(source: str) -> None:
    before = extract(source)
    after = extract("# comment\n\nunused = 1\n" + source.replace("= ", "=  "))
    assert [r.relationship_id for r in before.relationships] == [
        r.relationship_id for r in after.relationships
    ]
    assert [r.content_fingerprint for r in before.relationships] == [
        r.content_fingerprint for r in after.relationships
    ]


@pytest.mark.parametrize(
    "changed",
    [
        GRAPH.replace('"review"', '"changed"'),
        GRAPH.replace("graph =", "builder =").replace("graph.add_node", "builder.add_node"),
        GRAPH.replace("def review", "def inspect").replace(", review)", ", inspect)"),
    ],
)
def test_material_graph_changes_change_identity(changed: str) -> None:
    assert (
        extract(GRAPH).relationships[0].relationship_id
        != extract(changed).relationships[0].relationship_id
    )


def test_task_context_is_not_executor_identity_or_fingerprint() -> None:
    first = extract(CREW).relationships[0]
    second = extract(
        CREW.replace('description="read",', 'description="changed", context=[other],')
    ).relationships[0]
    assert first.relationship_id == second.relationship_id
    assert first.content_fingerprint == second.content_fingerprint
    assert (
        first.relationship_id
        != extract(CREW.replace("task =", "other =")).relationships[0].relationship_id
    )
    assert (
        first.relationship_id
        != extract(CREW.replace("worker", "writer")).relationships[0].relationship_id
    )


def test_old_relationship_payload_loads_with_empty_additive_fields() -> None:
    path = PROJECT_ROOT / "docs/registration-relationships-audit.json"
    row = json.loads(path.read_text())["actual"][0]
    row = {
        k: v
        for k, v in row.items()
        if k not in {"registered_identity", "executor_identity", "limitations"}
    }
    row["registration"]["excerpt"] = "lookup"
    if row["definition"] is not None:
        row["definition"]["excerpt"] = "def lookup(): pass"
    restored = RegistrationRelationship.model_validate(row)
    assert restored.registered_identity is None and restored.executor_identity is None
    assert restored.limitations == ()


def test_original_m10_2a_registration_ids_fingerprints_and_fields_are_preserved() -> None:
    baseline = json.loads((FIXTURES / "compatibility_baseline.json").read_text())["legacy"]
    for repository in load_corpus().repositories:
        result = extract_behaviors(scan_repository(PROJECT_ROOT / repository.path))
        old = [
            r.model_dump(
                mode="json",
                exclude={"registered_identity", "executor_identity", "limitations"}
                | DISCOVERY_FIELDS,
            )
            for r in result.registration_relationships
            if r.kind in {"constructor_tool", "decorator_tool"}
        ]
        assert digest(old) == baseline[repository.repository]["relationship_sha256"]
        assert set(baseline[repository.repository]["capability_ids"]) <= {
            c.callable_id for c in result.callable_capabilities
        }


@pytest.mark.parametrize(
    "name,solution,target",
    [
        ("langgraph-agent", "evals/escalation_path.jsonl.example", "evals/escalation_path.jsonl"),
        ("crewai-agent", "tests/solutions/test_escalation.py.example", "tests/test_escalation.py"),
        ("pydantic-ai-agent", "tests/solutions/test_retry.py.example", "tests/test_retry.py"),
    ],
)
def test_public_behavior_assessment_finding_and_m9_results_match_preimplementation(
    tmp_path: Path,
    name: str,
    solution: str,
    target: str,
) -> None:
    expected = json.loads((FIXTURES / "compatibility_baseline.json").read_text())["public"][name]
    root = tmp_path / name
    copytree(PROJECT_ROOT / "examples" / name, root)
    before = analyze_snapshot(root)
    assert (
        digest([b.model_dump(mode="json") for b in before.behaviors.behaviors])
        == expected["behavior_sha256"]
    )
    assert (
        digest([a.model_dump(mode="json") for a in before.matching.assessments])
        == expected["assessments_sha256"]
    )
    assert before.finding_ids == expected["finding_ids"]
    baseline = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    unchanged = compare_inventories(before, before, baseline=baseline, repository="[audit]")
    assert digest(comparison_json(unchanged)) == expected["m9_unchanged_sha256"]
    copy2(root / solution, root / target)
    after = analyze_snapshot(root)
    improved = compare_inventories(before, after, baseline=baseline, repository="[audit]")
    if name == "langgraph-agent":
        # M10.2f migrates the supplied eval to an explicit graph binding.
        # The historical hash is preserved; graph/M9 changes are audited separately.
        assert improved.summary["coverage_improvements"] >= 1
    else:
        assert digest(comparison_json(improved)) == expected["m9_solution_sha256"]
    assert after.finding_ids == expected["solution_finding_ids"]
    assert not (root / ".agentguard").exists()


def test_callback_inventory_alone_does_not_create_assessments_or_findings(tmp_path: Path) -> None:
    (tmp_path / "graph.py").write_text(GRAPH)
    inventory = analyze_snapshot(tmp_path)
    assert inventory.behaviors.registration_relationships
    assert not inventory.behaviors.behaviors
    assert not inventory.matching.assessments and not inventory.finding_ids


@pytest.mark.parametrize("directory", ["module", "v1", "v2", "legacy"])
def test_orchestration_recognition_is_independent_of_directory_names(
    tmp_path: Path, directory: str
) -> None:
    copytree(FIXTURES, tmp_path / directory)
    before = extract_behaviors(scan_repository(FIXTURES))
    after = extract_behaviors(scan_repository(tmp_path))

    def signature(result):
        return sorted(
            (r.kind, r.owner_identity.split("#")[-1], r.referenced_symbol, r.resolution.value)
            for r in result.registration_relationships
            if r.kind in ORCHESTRATION_KINDS
        )

    assert signature(before) == signature(after)


def test_independent_orchestration_audit_and_reference_accuracy() -> None:
    report = run_orchestration_audit()
    assert all(row["correct"] for repo in report["repositories"] for row in repo["expectations"])
    assert report["metrics"]["orchestration_recall"] == {"numerator": 20, "denominator": 20}
    assert report["metrics"]["reviewed_resolved_precision"] == {"numerator": 20, "denominator": 20}
    assert report["metrics"]["source_accuracy"] == {"correct": 48, "denominator": 48}
    assert report["metrics"]["expected_unknown_or_ambiguous"] == 8
    assert report["metrics"]["incorrect_ownership_promotions"] == 0
    assert (
        serialize_report(report)
        == (PROJECT_ROOT / "docs/orchestration-relationships-audit.json").read_text()
    )
    assert serialize_report(report) == serialize_report(run_orchestration_audit())


def test_orchestration_audit_does_not_execute_sources_or_modify_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    truth = json.loads((FIXTURES / "inventory.json").read_text())
    truth["repositories"] = [r for r in truth["repositories"] if r["repository"] == "controlled"]
    truth["expectations"] = [e for e in truth["expectations"] if e["repository"] == "controlled"]
    truth["repositories"][0]["path"] = "target"
    target = project / "target"
    copytree(FIXTURES, target)
    source = target / "negative.py"
    source.write_text(source.read_text() + "\nraise AssertionError('target executed')\n")
    truth["repositories"][0]["sources"]["negative.py"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    catalog = project / "inventory.json"
    catalog.write_text(json.dumps(truth))
    state = target / ".agentguard/agentguard.db"
    state.parent.mkdir()
    state.write_bytes(b"existing user state")
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Network, target execution, or persistence attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    report = run_orchestration_audit(catalog, project=project)
    assert all(row["correct"] for repo in report["repositories"] for row in repo["expectations"])
    assert before == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    state.unlink()
    state.parent.rmdir()
    run_orchestration_audit(catalog, project=project)
    assert not state.parent.exists()


def test_validator_owner_and_callback_changes_are_material() -> None:
    before = extract(VALIDATOR).relationships[0]
    for source in [
        VALIDATOR.replace("agent =", "assistant =").replace("@agent.", "@assistant."),
        VALIDATOR.replace("def validate", "def verify"),
    ]:
        after = extract(source).relationships[0]
        assert before.relationship_id != after.relationship_id
        assert before.content_fingerprint != after.content_fingerprint


def test_generated_function_and_bound_graph_method_remain_unsupported() -> None:
    source = GRAPH.replace(
        'graph.add_node("review", review)',
        'generated = factory()\ngraph.add_node("review", generated)',
    )
    assert extract(source).relationships[0].resolution is RegistrationResolution.UNRESOLVED
    source = (
        GRAPH
        + """
class Adapter:
    def read(self, state): return state
adapter = Adapter()
graph.add_node("bound", adapter.read)
"""
    )
    bound = next(r for r in extract(source).relationships if r.registered_identity == "bound")
    assert bound.resolution is RegistrationResolution.UNRESOLVED
    assert bound.definition is None


def test_shared_tool_and_graph_callback_have_one_canonical_capability(tmp_path: Path) -> None:
    source = "from langchain_core.tools import tool\n" + GRAPH.replace(
        "def review", "@tool\ndef review"
    )
    (tmp_path / "agent.py").write_text(source)
    result = extract_behaviors(scan_repository(tmp_path))
    assert len(result.callable_capabilities) == 1
    assert result.callable_capabilities[0].behavior_id is not None
    assert len({c.callable_id for c in result.callable_capabilities}) == 1


def test_distinct_unknown_node_expressions_do_not_collapse() -> None:
    source = GRAPH.replace(
        'graph.add_node("review", review)',
        "graph.add_node(first_name, review)\ngraph.add_node(second_name, review)",
    )
    result = extract(source)
    assert len(result.relationships) == 2
    assert len({r.relationship_id for r in result.relationships}) == 2
    assert all(r.resolution is RegistrationResolution.UNRESOLVED for r in result.relationships)


def test_callback_retargeting_alone_does_not_create_m9_coverage_deltas(tmp_path: Path) -> None:
    source = GRAPH + '\ndef alternate(state): return state\ngraph.add_edge("review", "end")\n'
    path = tmp_path / "app.py"
    path.write_text(source)
    before = analyze_snapshot(tmp_path)
    path.write_text(source.replace('"review", review)', '"review", alternate)'))
    after = analyze_snapshot(tmp_path)
    assert (
        before.behaviors.registration_relationships[0].relationship_id
        != after.behaviors.registration_relationships[0].relationship_id
    )
    assert before.behaviors.behaviors == after.behaviors.behaviors
    assert before.matching.assessments == after.matching.assessments
    assert before.finding_ids == after.finding_ids
    report = compare_inventories(
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
    assert len(report.changes) == len(before.behaviors.behaviors)
    assert all(change.change_status.value == "unchanged" for change in report.changes)
    assert not (tmp_path / ".agentguard").exists()


@pytest.mark.parametrize("damage", ["duplicate", "outside", "stale", "span"])
def test_orchestration_inventory_rejects_invalid_ground_truth(tmp_path: Path, damage: str) -> None:
    truth = json.loads((FIXTURES / "inventory.json").read_text())
    if damage == "duplicate":
        truth["expectations"].append(truth["expectations"][0])
    elif damage == "outside":
        truth["expectations"][0]["source_file"] = "../outside.py"
    elif damage == "stale":
        repository = truth["repositories"][0]
        first = next(iter(repository["sources"]))
        repository["sources"][first] = "invalid"
    else:
        truth["expectations"][0]["registration_line"] = 0
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(truth))
    with pytest.raises(ValueError):
        run_orchestration_audit(path)
