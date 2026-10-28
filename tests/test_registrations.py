"""Provenance facts enrich inventory without creating verification evidence."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from agentguard.comparison import analyze_snapshot
from agentguard.extractors import extract_behaviors
from agentguard.extractors.registrations import SourceIndex, extract_registrations
from agentguard.models import BehaviorExtractionResult, RegistrationResolution
from agentguard.scanners import scan_repository

ROOT = Path(__file__).parents[1]


def extract(source: str):
    return extract_registrations("app.py", ast.parse(source), source)


FUNCTION = "\ndef lookup(key: str):\n    return key\n"
BOUND = """
class Records:
    def read(self, key):
        return key
records = Records()
"""


@pytest.mark.parametrize(
    "statement,expression,expected",
    [
        ("from pydantic_ai import Agent", "Agent", "pydantic_ai.Agent"),
        ("from pydantic_ai import Agent as Assistant", "Assistant", "pydantic_ai.Agent"),
        ("import pydantic_ai as pai", "pai.Agent", "pydantic_ai.Agent"),
        ("import pydantic_ai", "pydantic_ai.Agent", "pydantic_ai.Agent"),
        ("from crewai import Agent as Worker", "Worker", "crewai.Agent"),
        ("from external import Agent", "Agent", "external.Agent"),
        ("from pydantic_ai import *", "Agent", None),
        ("from pydantic_ai import Agent\nAgent = other", "Agent", None),
        ("from pydantic_ai import Agent\nclass Agent: pass", "Agent", None),
        ("from pydantic_ai import Agent\ndef Agent(): pass", "Agent", None),
        ("if condition:\n    from pydantic_ai import Agent", "Agent", None),
        ("def helper():\n    from pydantic_ai import Agent", "Agent", None),
        ("from .pydantic_ai import Agent", "Agent", None),
        ("from pydantic_ai import Agent\nunused = (Agent := other)", "Agent", None),
    ],
)
def test_file_local_import_index(statement: str, expression: str, expected: str | None) -> None:
    index = SourceIndex(ast.parse(statement))
    assert index.resolve_import(ast.parse(expression, mode="eval").body) == expected


@pytest.mark.parametrize("container", ["[lookup]", "(lookup,)", "{lookup}"])
@pytest.mark.parametrize("framework", ["pydantic_ai", "crewai"])
def test_literal_registrations_have_real_provenance(container: str, framework: str) -> None:
    result = extract(f"from {framework} import Agent\n{FUNCTION}\na = Agent(tools={container})")
    assert len(result.capabilities) == len(result.relationships) == 1
    relationship = result.relationships[0]
    assert relationship.resolution is RegistrationResolution.RESOLVED
    assert relationship.owner_identity == "app.py#a"
    assert relationship.callable_id == result.capabilities[0].callable_id
    assert relationship.registration.excerpt == "lookup"
    assert relationship.definition.excerpt.startswith("def lookup")


def test_shared_callable_is_one_capability_with_two_owners() -> None:
    source = (
        f"from pydantic_ai import Agent\n{FUNCTION}\n"
        "a=Agent(tools=[lookup,lookup])\nb=Agent(tools=[lookup])"
    )
    result = extract(source)
    assert len(result.capabilities) == 1
    assert len(result.relationships) == 2
    assert {r.owner_identity for r in result.relationships} == {"app.py#a", "app.py#b"}
    assert len({r.relationship_id for r in result.relationships}) == 2


@pytest.mark.parametrize("decoration", ["tool", "tool_plain"])
def test_owned_decorator_and_unattached_framework_tool(decoration: str) -> None:
    source = f"""from pydantic_ai import Agent
from langchain_core.tools import tool as exposed
a = Agent("test")
@a.{decoration}
def attached(): return 1
@exposed
def unattached(): return 2
"""
    result = extract(source)
    assert {c.qualified_name for c in result.capabilities} == {"attached", "unattached"}
    assert len(result.relationships) == 1
    assert result.relationships[0].registration.excerpt == f"a.{decoration}"
    assert result.relationships[0].referenced_symbol == "attached"


def test_bound_method_resolution_has_class_qualified_identity() -> None:
    source = f"from pydantic_ai import Agent\n{BOUND}\na=Agent(tools=[records.read])"
    result = extract(source)
    assert result.relationships[0].resolution is RegistrationResolution.RESOLVED
    assert result.capabilities[0].qualified_name == "Records.read"
    assert result.capabilities[0].behavior_id is None
    assert "def read" in result.relationships[0].definition.excerpt
    assert result.relationships[0].registration.excerpt == "records.read"


@pytest.mark.parametrize(
    "alteration",
    [
        "records = Records()",
        "records = other",
        "records.read = replacement",
        "Records.read = replacement",
        "setattr(records, 'read', replacement)",
        "del records.read",
        "records.__dict__['read'] = replacement",
        "vars(records)['read'] = replacement",
        "unused = (records := other)",
        "def mutate():\n    global records\n    records = other",
    ],
)
def test_rebound_or_mutated_receiver_never_resolves(alteration: str) -> None:
    result = extract(
        f"from pydantic_ai import Agent\n{BOUND}\n{alteration}\na=Agent(tools=[records.read])"
    )
    assert result.relationships[0].resolution is not RegistrationResolution.RESOLVED
    assert result.relationships[0].definition is None


@pytest.mark.parametrize(
    "class_source",
    [
        "class Records(Base):\n    def read(self): pass",
        "class Records(metaclass=Meta):\n    def read(self): pass",
        "class Records:\n    @property\n    def read(self): pass",
        "class Records:\n    @staticmethod\n    def read(): pass",
        "class Records:\n    def read(self): pass\n    def read(self): pass",
        "class Records:\n    def read(self): pass\n    def __getattr__(self, name): pass",
        "class Records:\n    def read(self): pass\n    def __init__(self): self.read = other",
        "class Records:\n    def read(self): pass\n    def __new__(cls): return other",
        "from external import Records",
    ],
)
def test_unsupported_classes_remain_unresolved(class_source: str) -> None:
    result = extract(
        f"from pydantic_ai import Agent\n{class_source}\n"
        "records=Records()\na=Agent(tools=[records.read])"
    )
    assert result.relationships[0].resolution is not RegistrationResolution.RESOLVED
    assert not result.capabilities
    assert result.relationships[0].definition is None


@pytest.mark.parametrize(
    "target", ["getattr(records, 'read')", "registry[key]", "alias.read", "external.read"]
)
def test_dynamic_or_unknown_receiver_expressions_remain_unknown(target: str) -> None:
    source = f"from pydantic_ai import Agent\n{BOUND}\nalias=records\na=Agent(tools=[{target}])"
    assert extract(source).relationships[0].resolution is not RegistrationResolution.RESOLVED


@pytest.mark.parametrize("tools", ["load_plugins()", "lookup", "tools", "[x for x in plugins]"])
def test_nonliteral_collections_do_not_create_resolved_registration(tools: str) -> None:
    result = extract(f"from pydantic_ai import Agent\n{FUNCTION}\na=Agent(tools={tools})")
    assert result.relationships[0].resolution is RegistrationResolution.UNRESOLVED
    assert not result.capabilities


def test_two_classes_with_same_method_have_distinct_capabilities() -> None:
    result = extract(f"""from pydantic_ai import Agent
{BOUND}
class Archive:
    def read(self, key): return key
archive = Archive()
a=Agent(tools=[records.read])
b=Agent(tools=[archive.read])
""")
    assert {c.qualified_name for c in result.capabilities} == {"Records.read", "Archive.read"}
    assert len({c.callable_id for c in result.capabilities}) == 2


@pytest.mark.parametrize("prefix", ["", "# comment\n\n", "unrelated = 1\n"])
def test_relationship_identity_ignores_lines_and_formatting(prefix: str) -> None:
    base = f"from pydantic_ai import Agent\n{FUNCTION}\na=Agent(tools=[lookup])"
    original = extract(base)
    formatted = extract(
        prefix + base.replace("a=Agent(tools=[lookup])", "a = Agent(\n tools = [lookup],\n)")
    )
    assert original.relationships[0].relationship_id == formatted.relationships[0].relationship_id
    assert (
        original.relationships[0].content_fingerprint
        == formatted.relationships[0].content_fingerprint
    )
    assert original.capabilities[0].callable_id == formatted.capabilities[0].callable_id
    assert (
        original.relationships[0].relationship_id
        != extract(base.replace("a=", "b=")).relationships[0].relationship_id
    )
    changed = base.replace("lookup", "search")
    assert (
        original.relationships[0].relationship_id
        != extract(changed).relationships[0].relationship_id
    )


def test_unknown_custom_factory_preserves_generic_compatibility(tmp_path: Path) -> None:
    source = f"from external import create_agent\n{FUNCTION}\na=create_agent(tools=[lookup])"
    (tmp_path / "app.py").write_text(source)
    result = extract_behaviors(scan_repository(tmp_path))
    assert any(b.subject == "lookup" for b in result.behaviors)
    assert result.registration_relationships[0].framework is None
    assert result.registration_relationships[0].resolution is RegistrationResolution.UNRESOLVED
    # Local custom factories are not automatically proven non-agent either.
    (tmp_path / "app.py").write_text(
        "def create_agent(*, tools):\n    return Runtime(tools)\n"
        + FUNCTION
        + "\na=create_agent(tools=[lookup])"
    )
    result = extract_behaviors(scan_repository(tmp_path))
    assert any(b.subject == "lookup" for b in result.behaviors)
    assert result.registration_relationships[0].resolution is RegistrationResolution.UNRESOLVED


def test_bound_capability_and_shared_relationships_never_become_assessments(tmp_path: Path) -> None:
    source = (
        f"from pydantic_ai import Agent\n{BOUND}\n"
        "a=Agent(tools=[records.read])\nb=Agent(tools=[records.read])"
    )
    (tmp_path / "app.py").write_text(source)
    inventory = analyze_snapshot(tmp_path)
    assert len(inventory.behaviors.callable_capabilities) == 1
    assert len(inventory.behaviors.registration_relationships) == 2
    assert all(b.source_symbol != "Records.read" for b in inventory.behaviors.behaviors)
    ids = {r.relationship_id for r in inventory.behaviors.registration_relationships}
    assert not ids.intersection(inventory.finding_ids)
    assert not ids.intersection(a.behavior_id for a in inventory.matching.assessments)
    assert not (tmp_path / ".agentguard").exists()


def test_old_extraction_payload_has_additive_defaults() -> None:
    result = BehaviorExtractionResult.model_validate({"completeness": "complete"})
    assert not result.callable_capabilities and not result.registration_relationships


def test_public_example_behavior_finding_and_assessment_baselines_are_unchanged() -> None:
    baseline = json.loads(
        (ROOT / "tests/fixtures/registration_audit/public_baseline.json").read_text()
    )
    for directory, before in baseline.items():
        inventory = analyze_snapshot(ROOT / "examples" / directory)
        assert before["behaviors"] == {
            b.behavior_id: b.content_fingerprint for b in inventory.behaviors.behaviors
        }
        assert before["finding_ids"] == inventory.finding_ids
        assessments = [a.model_dump(mode="json") for a in inventory.matching.assessments]
        assert (
            before["assessments_sha256"]
            == hashlib.sha256(json.dumps(assessments, sort_keys=True).encode()).hexdigest()
        )


@pytest.mark.parametrize("expression", ["Tool(lookup)", "wrapped"])
def test_supported_pydantic_tool_wrapper_is_explicit_not_generic_tracing(expression: str) -> None:
    source = (
        f"from pydantic_ai import Agent, Tool\n{FUNCTION}\n"
        f"wrapped=Tool(lookup)\na=Agent(tools=[{expression}])"
    )
    result = extract(source)
    assert len(result.capabilities) == 1
    assert result.relationships[0].resolution is RegistrationResolution.RESOLVED
    assert result.capabilities[0].qualified_name == "lookup"


def test_decorator_registration_form_participates_in_identity() -> None:
    source = "from pydantic_ai import Agent\na=Agent('test')\n@a.tool\ndef lookup(): pass"
    first = extract(source).relationships[0]
    second = extract(source.replace("@a.tool", "@a.tool_plain")).relationships[0]
    assert first.relationship_id != second.relationship_id
    assert first.content_fingerprint != second.content_fingerprint


def test_chained_assignment_and_unknown_replacing_decorator_are_not_resolved() -> None:
    chained = extract(f"from pydantic_ai import Agent\n{BOUND}\na=b=Agent(tools=[records.read])")
    assert all(r.resolution is not RegistrationResolution.RESOLVED for r in chained.relationships)
    decorated = extract(
        "from pydantic_ai import Agent\n@replace\ndef lookup(): pass\na=Agent(tools=[lookup])"
    )
    assert decorated.relationships[0].definition is None
    assert not decorated.capabilities


def test_independent_registration_audit_is_reproducible_and_source_accurate() -> None:
    from tools.behavior_audit.registrations import run_registration_audit, run_report
    from tools.behavior_audit.runner import serialize_report

    report = run_registration_audit()
    assert all(e["correct"] for e in report["expectations"])
    assert report["metrics"]["registration_recall"] == {"numerator": 8, "denominator": 8}
    assert report["metrics"]["bound_method_resolution"] == {"numerator": 2, "denominator": 2}
    assert report["metrics"]["source_accuracy"] == {"correct": 21, "denominator": 21}
    assert report["metrics"]["incorrect_ownership_promotions"] == 0
    assert report["metrics"]["unknown_or_ambiguous"] == 5
    assert (
        serialize_report(run_report())
        == (ROOT / "docs/registration-relationships-audit.json").read_text()
    )


@pytest.mark.parametrize("directory", ["module", "v1", "v2", "legacy"])
def test_registration_recognition_is_independent_of_directory_names(
    tmp_path: Path, directory: str
) -> None:
    from shutil import copytree

    root = ROOT / "tests/fixtures/registration_audit"
    copytree(root, tmp_path / directory)
    before = extract_behaviors(scan_repository(root))
    after = extract_behaviors(scan_repository(tmp_path))

    def identities(result: BehaviorExtractionResult):
        return sorted(
            (
                r.owner_identity.split("#")[-1],
                r.referenced_symbol,
                r.resolution.value,
                r.framework or "",
            )
            for r in result.registration_relationships
        )

    assert identities(before) == identities(after)


def test_known_nonagent_controls_have_no_selected_findings_or_verified_owners() -> None:
    inventory = analyze_snapshot(ROOT / "tests/fixtures/behavior_audit/negative_controls")
    assert not inventory.behaviors.behaviors
    assert not inventory.finding_ids
    assert not inventory.behaviors.registration_relationships


def test_integration_keeps_assessment_limit_explicit_after_bound_resolution(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        f"from pydantic_ai import Agent\n{BOUND}\na=Agent(tools=[records.read])"
    )
    result = extract_behaviors(scan_repository(tmp_path))
    assert result.registration_relationships[0].resolution is RegistrationResolution.RESOLVED
    assert any(w.code == "registration_only_callable" for w in result.warnings)
    assert not any(w.code == "pydantic_ai_dynamic_tool" for w in result.warnings)
    assert result.completeness.value == "incomplete"
