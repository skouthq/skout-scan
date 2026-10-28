"""Bounded structural links never substitute for verified behavior/eval evidence."""

import ast
import hashlib
import json
import socket
import sqlite3
import subprocess
from pathlib import Path
from shutil import copytree

import pytest

from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.extractors import extract_behaviors
from agentguard.extractors.delegation import DELEGATION_KINDS, DISCOVERY_FIELDS, extract_delegations
from agentguard.extractors.orchestration import extract_orchestration
from agentguard.extractors.registrations import RegistrationInventory, extract_registrations
from agentguard.models import ComparisonBaseline, RegistrationRelationship, RegistrationResolution
from agentguard.scanners import scan_repository
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

FIXTURES = PROJECT_ROOT / "tests/fixtures/delegation_audit"
PREFIX = "from langchain_core.tools import tool\n"
DISPATCH = (
    PREFIX
    + """
def first(value): return value
def second(value): return value
HANDLERS = {"first": first, "second": second}
@tool
def dispatch(key, value):
    return HANDLERS[key](value)
"""
)
ADAPTER = (
    PREFIX
    + """
def deep(value): return value
class Adapter:
    def execute(self, value): return deep(value)
class Other:
    def execute(self, value): return value
adapter = Adapter()
other = Other()
@tool
def run(value):
    return adapter.execute(value)
"""
)
FALLBACK = (
    PREFIX
    + """
def primary(value): return value
def cached(value): return value
def alternate(value): return value
@tool
def run(value):
    try:
        return primary(value)
    except TimeoutError:
        return cached(value)
    except (ConnectionError, FileNotFoundError):
        return alternate(value)
"""
)


def extract(source: str):
    tree = ast.parse(source)
    a = extract_registrations("app.py", tree, source)
    b = extract_orchestration("app.py", tree, source)
    return extract_delegations(
        "app.py",
        tree,
        source,
        RegistrationInventory(a.capabilities + b.capabilities, a.relationships + b.relationships),
    )


def resolved(source: str):
    return [
        r for r in extract(source).relationships if r.resolution is RegistrationResolution.RESOLVED
    ]


def identity(source: str):
    return {(r.relationship_id, r.content_fingerprint) for r in extract(source).relationships}


def test_two_dispatch_routes_shared_targets_and_real_source(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(DISPATCH)
    result = extract(DISPATCH)
    assert {(r.dispatch_key, r.referenced_symbol) for r in result.relationships} == {
        ("first", "first"),
        ("second", "second"),
    }
    assert all(r.kind == "literal_dispatch" for r in result.relationships)
    assert all(r.parent_callable_id and r.parent_provenance for r in result.relationships)
    for r in result.relationships:
        assert r.target_role == "orchestrated_internal"
        for ref in (r.registration, r.definition, r.registry_evidence, *r.parent_provenance):
            assert ref and reference_valid(tmp_path, ref)
    shared = extract(DISPATCH.replace('"second": second', '"second": first'))
    assert len(shared.relationships) == 2 and len(shared.capabilities) == 1


@pytest.mark.parametrize(
    "change",
    [
        "HANDLERS = {}",
        "HANDLERS.update({})",
        "HANDLERS.setdefault('x', first)",
        "HANDLERS['x'] = first",
        "HANDLERS[key] = first",
        "alias = HANDLERS",
        "register(HANDLERS)",
        "def escape(): return HANDLERS",
        "globals()",
        "setattr(HANDLERS, 'x', first)",
    ],
)
def test_mutated_escaped_or_reflected_registry_is_uncertain(change: str) -> None:
    rows = extract(DISPATCH + "\n" + change).relationships
    assert rows and all(r.resolution is not RegistrationResolution.RESOLVED for r in rows)
    assert all(r.callable_id is None and r.target_role is None for r in rows)


@pytest.mark.parametrize(
    "old,new",
    [
        ('"first": first', "key: first"),
        ('"first": first', '"first": factory()'),
        ('"first": first', '"first": external'),
        ('{"first": first, "second": second}', "{key: first for key in keys}"),
        ("HANDLERS[key]", "EXTERNAL[key]"),
        ("HANDLERS[key]", "HANDLERS[compute()]"),
        ("HANDLERS[key]", "HANDLERS[1]"),
        ("def dispatch(key, value):", "def dispatch(key, value, HANDLERS):"),
    ],
)
def test_dynamic_dispatch_never_resolves(old: str, new: str) -> None:
    assert not resolved(DISPATCH.replace(old, new))


def test_literal_selector_only_records_its_possible_route() -> None:
    # A known constant does not permit claiming a different key was selected.
    rows = resolved(DISPATCH.replace("HANDLERS[key]", 'HANDLERS["first"]'))
    assert {r.dispatch_key for r in rows} == {"first"}


@pytest.mark.parametrize("directory", ["agent", "v1", "v2", "legacy", "module"])
def test_no_naming_based_parent_promotion(tmp_path: Path, directory: str) -> None:
    root = tmp_path / directory
    root.mkdir()
    source = DISPATCH.replace("@tool\n", "") + ADAPTER.replace(PREFIX, "").replace("@tool\n", "")
    (root / "agent_v2_legacy.py").write_text(source)
    result = extract_behaviors(scan_repository(root))
    assert not [r for r in result.registration_relationships if r.kind in DELEGATION_KINDS]
    assert not extract(DISPATCH.replace(PREFIX, "from unrelated import tool\n")).relationships


def test_adapter_one_hop_and_two_distinct_receivers() -> None:
    rows = resolved(ADAPTER)
    assert len(rows) == 1 and rows[0].definition.source_symbol == "Adapter.execute"
    assert rows[0].parent_provenance and rows[0].parent_callable_id
    assert {c.qualified_name for c in extract(ADAPTER).capabilities} == {"Adapter.execute"}
    changed = resolved(
        ADAPTER.replace("return adapter.execute(value)", "return other.execute(value)")
    )
    assert changed[0].definition.source_symbol == "Other.execute"
    assert changed[0].relationship_id != rows[0].relationship_id


@pytest.mark.parametrize(
    "change",
    [
        "adapter = Other()",
        "adapter = external",
        "adapter.execute = replacement",
        "setattr(adapter, 'execute', replacement)",
    ],
)
def test_ambiguous_receiver_is_not_resolved(change: str) -> None:
    assert not resolved(ADAPTER + "\n" + change)


@pytest.mark.parametrize(
    "old,new",
    [
        ("class Adapter:", "class Adapter(Base):"),
        ("class Adapter:", "class Adapter(metaclass=Meta):"),
        ("adapter = Adapter()", "adapter = imported_instance"),
        ("adapter.execute(value)", "getattr(adapter, 'execute')(value)"),
        ("adapter.execute(value)", "factory().execute(value)"),
        ("def run(value):", "def run(value, adapter):"),
        ("adapter = Adapter()", "adapter = Adapter()\nalias = adapter"),
    ],
)
def test_unsupported_method_resolution_is_uncertain(old: str, new: str) -> None:
    assert not resolved(
        ADAPTER.replace(old, new).replace("return adapter.execute", "return alias.execute")
        if "alias = adapter" in new
        else ADAPTER.replace(old, new)
    )


def test_shared_child_different_parents_and_distinct_conditions() -> None:
    source = (
        ADAPTER
        + """
@tool
def another(value): return adapter.execute(value)
"""
    )
    rows = resolved(source)
    assert len(rows) == 2 and len({r.callable_id for r in rows}) == 1
    assert len({r.parent_callable_id for r in rows}) == 2
    conditional = ADAPTER.replace(
        "    return adapter.execute(value)",
        "    if value:\n        return adapter.execute(value)\n"
        "    else:\n        return adapter.execute(value)",
    )
    rows = resolved(conditional)
    assert len(rows) == len({r.relationship_id for r in rows}) == 2
    assert len({r.conditions for r in rows}) == 2
    duplicate = ADAPTER.replace(
        "    return adapter.execute(value)",
        "    adapter.execute(value)\n    adapter.execute(value)",
    )
    assert len(resolved(duplicate)) == 1


def test_callback_and_registered_plain_function_roots_and_async_calls() -> None:
    source = """from langgraph.graph import StateGraph
async def helper(value): return value
async def callback(state): return await helper(state)
graph = StateGraph(dict)
graph.add_node("run", callback)
"""
    rows = resolved(source)
    assert len(rows) == 1 and rows[0].parent_relationship_ids
    assert rows[0].registration.excerpt == "await helper(state)"
    source = "from pydantic_ai import Agent\n" + ADAPTER.replace(PREFIX, "").replace("@tool\n", "")
    source += '\nagent = Agent("test", tools=[run])\n'
    assert len(resolved(source)) == 1


def test_fallback_handler_condition_and_separation_from_ordinary_calls() -> None:
    rows = resolved(FALLBACK)
    fallbacks = [r for r in rows if r.kind == "exception_fallback"]
    assert {(r.exception_condition, r.referenced_symbol) for r in fallbacks} == {
        ("TimeoutError", "cached"),
        ("(ConnectionError, FileNotFoundError)", "alternate"),
    }
    assert all(r.handler_evidence and r.conditions and r.context_evidence == () for r in fallbacks)
    assert all("except" in " ".join(r.conditions) for r in fallbacks)
    assert all("no execution" in r.limitations[0] for r in rows)
    outside = resolved(FALLBACK + "\n@tool\ndef outside(value): return cached(value)\n")
    assert any(r.referenced_symbol == "cached" and r.kind == "one_hop_delegation" for r in outside)
    assert not any(
        r.kind == "one_hop_delegation" and r.referenced_symbol == "alternate" for r in rows
    )


@pytest.mark.parametrize(
    "exception",
    ["", "Exception", "BaseException", "Dynamic", "factory()", "(TimeoutError, Dynamic)"],
)
def test_unsupported_handlers_stay_uncertain(exception: str) -> None:
    source = FALLBACK.replace(
        "except TimeoutError:", f"except {exception}:" if exception else "except:"
    )
    # Syntax-only analysis must also handle a bare catch-all conservatively.
    rows = [r for r in extract(source).relationships if r.referenced_symbol == "cached"]
    assert len(rows) == 1 and rows[0].resolution is RegistrationResolution.UNRESOLVED
    assert rows[0].callable_id is None and rows[0].handler_evidence


@pytest.mark.parametrize(
    "prefix,exception",
    [
        ("from builtins import TimeoutError as Timeout\n", "Timeout"),
        ("from builtins import TimeoutError\n", "TimeoutError"),
        ("import builtins as errors\n", "errors.TimeoutError"),
    ],
)
def test_recognized_exception_aliases(prefix: str, exception: str) -> None:
    rows = resolved(prefix + FALLBACK.replace("except TimeoutError:", f"except {exception}:"))
    assert any(r.referenced_symbol == "cached" and r.exception_condition == exception for r in rows)


def test_shadowed_exception_and_unresolved_fallback_do_not_resolve() -> None:
    for source in [
        FALLBACK + "\nTimeoutError = external\n",
        FALLBACK.replace("def run(value):", "def run(value, TimeoutError):"),
        "import builtins\n"
        + FALLBACK.replace("def run(value):", "def run(value, builtins):").replace(
            "except TimeoutError:", "except builtins.TimeoutError:"
        ),
        FALLBACK.replace("return cached(value)", "return external(value)"),
    ]:
        assert not any(
            r.kind == "exception_fallback" and r.referenced_symbol != "alternate"
            for r in resolved(source)
        )


def test_unsupported_control_and_nested_propagation_remain_uncertain() -> None:
    source = FALLBACK.replace(
        "        return cached(value)",
        "        try:\n            return cached(value)\n"
        "        except ValueError:\n            return alternate(value)",
    )
    assert not any(r.referenced_symbol == "cached" for r in resolved(source))
    for control in ["for item in value:", "while value:", "with resource:"]:
        source = ADAPTER.replace(
            "    return adapter.execute(value)",
            f"    {control}\n        return adapter.execute(value)",
        )
        assert not resolved(source)


@pytest.mark.parametrize("source", [DISPATCH, ADAPTER, FALLBACK])
def test_ids_and_fingerprints_survive_formatting_lines_and_repetition(source: str) -> None:
    assert identity(source) == identity(source)
    assert identity(source) == identity(
        "\n# unrelated\n\n" + source.replace("(value)", "( value )")
    )


def test_material_key_target_parent_and_handler_changes() -> None:
    baseline = identity(DISPATCH)
    for changed in [
        DISPATCH.replace('"first": first', '"renamed": first'),
        DISPATCH.replace('"first": first', '"first": second'),
        DISPATCH.replace("def dispatch(", "def renamed("),
    ]:
        assert baseline != identity(changed)
    assert identity(FALLBACK) != identity(
        FALLBACK.replace("except TimeoutError:", "except OSError:")
    )


def test_callback_relationships_do_not_create_behaviors_findings_or_state(tmp_path: Path) -> None:
    source = ADAPTER.replace(PREFIX, "from langgraph.graph import StateGraph\n").replace(
        "@tool\n", ""
    )
    source += '\ngraph = StateGraph(dict)\ngraph.add_node("run", run)\n'
    (tmp_path / "app.py").write_text(source)
    result = analyze_snapshot(tmp_path)
    assert any(r.kind in DELEGATION_KINDS for r in result.behaviors.registration_relationships)
    assert (
        not result.behaviors.behaviors
        and not result.matching.assessments
        and not result.finding_ids
    )
    assert not (tmp_path / ".agentguard").exists()


def test_old_payload_defaults() -> None:
    row = extract(ADAPTER).relationships[0].model_dump(mode="json", exclude=DISCOVERY_FIELDS)
    restored = RegistrationRelationship.model_validate(row)
    assert restored.parent_provenance == () and restored.parent_callable_id is None
    assert restored.target_role is None


def test_all_pre_m10_2c_inventory_and_assessment_snapshots() -> None:
    baseline = json.loads((FIXTURES / "compatibility_baseline.json").read_text())

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    for path, expected in baseline.items():
        result = analyze_snapshot(PROJECT_ROOT / path)
        extraction = result.behaviors
        assert (
            digest([b.model_dump(mode="json") for b in extraction.behaviors])
            == expected["behavior_sha256"]
        )
        assert (
            digest([a.model_dump(mode="json") for a in result.matching.assessments])
            == expected["assessment_sha256"]
        )
        assert result.finding_ids == expected["finding_ids"]
        assert (
            digest(
                [
                    r.model_dump(mode="json", exclude=DISCOVERY_FIELDS)
                    for r in extraction.registration_relationships
                    if r.kind not in DELEGATION_KINDS
                ]
            )
            == expected["relationship_sha256"]
        )
        assert set(expected["capability_ids"]) <= {
            c.callable_id for c in extraction.callable_capabilities
        }


def test_curated_audit_and_read_only_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.behavior_audit.delegation import run_delegation_audit

    report = run_delegation_audit()
    assert all(row["correct"] for repo in report["repositories"] for row in repo["expectations"])
    assert report["metrics"]["unexpected_resolved"] == 0
    assert report["metrics"]["incorrect_promotions"] == 0
    assert (
        report["metrics"]["source_accuracy"]["correct"]
        == report["metrics"]["source_accuracy"]["denominator"]
    )
    assert serialize_report(report) == serialize_report(run_delegation_audit())
    assert (
        serialize_report(report)
        == (PROJECT_ROOT / "docs/delegation-relationships-audit.json").read_text()
    )
    assert '"excerpt"' not in serialize_report(report)
    project = tmp_path / "project"
    target = project / "target"
    copytree(FIXTURES, target)
    truth = json.loads((FIXTURES / "inventory.json").read_text())
    truth["repositories"] = [r for r in truth["repositories"] if r["repository"] == "controlled"]
    truth["expectations"] = [e for e in truth["expectations"] if e["repository"] == "controlled"]
    truth["repositories"][0]["path"] = "target"
    source = target / "negative.py"
    source.write_text(source.read_text() + "\nraise AssertionError('executed target')\n")
    truth["repositories"][0]["sources"]["negative.py"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    catalog = project / "inventory.json"
    catalog.write_text(json.dumps(truth))
    state = target / ".agentguard/agentguard.db"
    state.parent.mkdir()
    state.write_bytes(b"saved feedback and history")
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Network, execution, or persistence attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    run_delegation_audit(catalog, project=project)
    assert before == {
        p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()
    }
    state.unlink()
    state.parent.rmdir()
    run_delegation_audit(catalog, project=project)
    assert not state.parent.exists()


@pytest.mark.parametrize(
    "change",
    [
        "import builtins; builtins.globals()",
        "from builtins import globals as g; g()",
        "dispatch.__globals__['HANDLERS']['first'] = second",
        "HANDLERS.__dict__",
    ],
)
def test_registry_reflective_access_does_not_establish_literal_contract(change: str) -> None:
    assert not resolved(DISPATCH + "\n" + change)


def test_unknown_registration_owner_does_not_seed_parent_analysis() -> None:
    source = ADAPTER.replace(PREFIX, "from arbitrary_factory import create_agent\n")
    source = source.replace("@tool\n", "") + "\nagent = create_agent(tools=[run])\n"
    assert not extract(source).relationships


def test_nested_callable_bodies_and_call_arguments_are_not_traversed() -> None:
    source = ADAPTER.replace(
        "    return adapter.execute(value)",
        "    def nested():\n        return other.execute(value)\n"
        "    print(other.execute(value))\n    return adapter.execute(value)",
    )
    rows = resolved(source)
    assert len(rows) == 1 and rows[0].referenced_symbol == "adapter.execute"


def test_ambiguous_receiver_status_retains_call_without_definition() -> None:
    row = extract(ADAPTER + "\nadapter = Other()\n").relationships[0]
    assert row.resolution is RegistrationResolution.AMBIGUOUS
    assert row.definition is None and row.callable_id is None


def test_pydantic_validator_is_eligible_but_does_not_promote_its_child() -> None:
    source = """from pydantic_ai import Agent
agent = Agent("test")
def helper(output): return output
@agent.output_validator
def validate(ctx, output): return helper(output)
"""
    rows = resolved(source)
    assert len(rows) == 1 and rows[0].parent_relationship_ids
    assert rows[0].definition.source_symbol == "helper"


def test_relationship_retargeting_alone_does_not_create_m9_coverage_delta(tmp_path: Path) -> None:
    source = """from langgraph.graph import StateGraph
def first(state): return state
def second(state): return state
def callback(state): return first(state)
graph = StateGraph(dict)
graph.add_node("run", callback)
"""
    path = tmp_path / "graph.py"
    path.write_text(source)
    before = analyze_snapshot(tmp_path)
    path.write_text(source.replace("return first(state)", "return second(state)"))
    after = analyze_snapshot(tmp_path)
    before_ids = {
        r.relationship_id
        for r in before.behaviors.registration_relationships
        if r.kind in DELEGATION_KINDS
    }
    after_ids = {
        r.relationship_id
        for r in after.behaviors.registration_relationships
        if r.kind in DELEGATION_KINDS
    }
    assert before_ids and after_ids and before_ids != after_ids
    baseline = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    unchanged = compare_inventories(before, before, baseline=baseline, repository="[audit]")
    changed = compare_inventories(before, after, baseline=baseline, repository="[audit]")
    assert comparison_json(unchanged) == comparison_json(changed)
    assert not (tmp_path / ".agentguard").exists()


def test_existing_child_edges_cannot_seed_further_roots_on_reanalysis() -> None:
    tree = ast.parse(ADAPTER)
    a = extract_registrations("app.py", tree, ADAPTER)
    c = extract_delegations("app.py", tree, ADAPTER, a)
    again = extract_delegations(
        "app.py",
        tree,
        ADAPTER,
        RegistrationInventory(a.capabilities + c.capabilities, a.relationships + c.relationships),
    )
    assert again == c
    assert not any(r.referenced_symbol == "deep" for r in again.relationships)


def test_callable_return_values_are_not_unwrapped_as_direct_delegation() -> None:
    source = "from pydantic_ai import Tool\n" + ADAPTER.replace(
        "return adapter.execute(value)", "return Tool(deep)(value)"
    )
    row = extract(source).relationships[0]
    assert row.resolution is RegistrationResolution.UNRESOLVED
    assert row.callable_id is None and row.definition is None
