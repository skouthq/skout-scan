from pathlib import Path

from agentguard.diagnostics import diagnose_repository
from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    BehaviorSourceType,
    BehaviorType,
    CoverageStatus,
    EvalSourceType,
)
from agentguard.scanners import scan_repository

AGENT_SOURCE = """
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, Tool

class Deps: pass
class Result(BaseModel):
    answer: str

def constructor_tool(query: str) -> str:
    return query

wrapped_tool = Tool(constructor_tool)
support_agent = Agent(
    "test",
    deps_type=Deps,
    output_type=Result | None,
    instructions="Help the user.",
    tools=[wrapped_tool],
)

@support_agent.tool
async def lookup(ctx: RunContext[Deps], customer_id: int) -> str:
    return str(ctx.deps.customer_service)

@support_agent.tool_plain
def ping(value: str) -> str:
    return value

@support_agent.instructions
async def extra_instructions(ctx: RunContext[Deps]) -> str:
    return "Use the dependency."

@support_agent.output_validator
def validate_output(ctx: RunContext[Deps], score: float) -> float:
    if score < 0.8:
        raise ModelRetry("score too low")
    return score
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_extracts_common_pydantic_ai_constructs_without_execution(tmp_path: Path) -> None:
    _write(tmp_path / "agent.py", AGENT_SOURCE)
    result = extract_behaviors(scan_repository(tmp_path))

    pydantic_behaviors = [
        item for item in result.behaviors if item.source_type.value.startswith("pydantic_ai_")
    ]
    subjects = {item.subject for item in pydantic_behaviors}
    assert {"support_agent", "constructor_tool", "lookup", "ping", "validate_output"} <= subjects
    assert sum(item.subject == "lookup" for item in result.behaviors) == 1
    assert any(
        item.behavior_type is BehaviorType.TOOL_FAILURE
        and item.subject == "validate_output"
        and item.action
        and item.action.outcome == "ModelRetry"
        for item in pydantic_behaviors
    )

    constructs = {(item.kind, item.name): item for item in result.framework_constructs}
    assert constructs[("agent", "support_agent")].metadata["deps_type"] == "Deps"
    assert constructs[("structured_output", "support_agent.output_type")]
    assert constructs[("tool", "lookup")].metadata["run_context"] is True
    assert constructs[("tool", "lookup")].metadata["dependency_type"] == "Deps"
    assert (
        "ctx.deps.customer_service"
        in constructs[("tool", "lookup")].metadata["dependency_accesses"]
    )
    assert constructs[("tool_plain", "ping")]
    assert constructs[("instruction_function", "extra_instructions")]
    assert constructs[("output_validator", "validate_output")]


def test_unqualified_generic_agent_is_not_pydantic_ai(tmp_path: Path) -> None:
    _write(
        tmp_path / "generic.py",
        "class Agent: pass\nagent = Agent()\ndef tool(): pass\n",
    )
    result = extract_behaviors(scan_repository(tmp_path))
    assert not any(item.framework == "Pydantic AI" for item in result.framework_summaries)
    assert not any(
        item.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT for item in result.behaviors
    )


def test_agent_runs_and_override_are_conservative_pytest_evidence(tmp_path: Path) -> None:
    _write(tmp_path / "agent.py", AGENT_SOURCE)
    _write(
        tmp_path / "tests/test_agent.py",
        """
from agent import support_agent

def test_sync_run():
    result = support_agent.run_sync("hello")
    assert result is not None

async def test_async_run():
    result = await support_agent.run("hello")
    assert result is not None

def test_override_alone():
    with support_agent.override(deps=object()):
        assert True
""",
    )
    scan = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(scan)
    matching = match_behaviors_to_evals(behaviors, evals)

    agent = next(
        item
        for item in behaviors.behaviors
        if item.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT
    )
    assessment = next(
        item for item in matching.assessments if item.behavior_id == agent.behavior_id
    )
    assert assessment.coverage_status is CoverageStatus.COVERED
    assert assessment.candidate_count == 2
    override = next(item for item in evals.scenarios if item.name == "test_override_alone")
    assert not any(ref.normalized_subject_name for ref in override.referenced_symbols)


def test_extracts_pydantic_evals_and_associates_dataset_task(tmp_path: Path) -> None:
    _write(tmp_path / "agent.py", AGENT_SOURCE)
    _write(
        tmp_path / "evals.py",
        """
from pydantic_evals import Case, Dataset
from agent import support_agent

case = Case(
    name="answers greeting",
    inputs={"prompt": "hello"},
    expected_output={"answer": "hello"},
    metadata={"priority": "high"},
    evaluators=[lambda ctx: True],
)
dataset = Dataset(name="support", cases=[case], evaluators=[lambda ctx: True])

def run_support(inputs):
    return support_agent.run_sync(inputs["prompt"])

dataset.evaluate_sync(run_support)
""",
    )
    scan = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(scan)
    scenario = next(
        item for item in evals.scenarios if item.source_type is EvalSourceType.PYDANTIC_EVAL
    )
    assert scenario.name == "answers greeting"
    assert scenario.inputs == {"prompt": "hello"}
    assert scenario.expected_outcome and scenario.expected_outcome.value == {"answer": "hello"}
    assert scenario.metadata["priority"] == "high"
    assert scenario.metadata["associated_agents"] == ["support_agent"]

    matching = match_behaviors_to_evals(behaviors, evals)
    agent = next(
        item
        for item in behaviors.behaviors
        if item.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT
    )
    assessment = next(
        item for item in matching.assessments if item.behavior_id == agent.behavior_id
    )
    assert assessment.coverage_status is CoverageStatus.COVERED


def test_dynamic_tools_warn_without_hiding_static_agent(tmp_path: Path) -> None:
    _write(
        tmp_path / "agent.py",
        "from pydantic_ai import Agent\nagent = Agent('test', tools=make_tools())\n",
    )
    result = extract_behaviors(scan_repository(tmp_path))
    assert any(item.code == "pydantic_ai_dynamic_tools" for item in result.warnings)
    assert any(item.subject == "agent" for item in result.behaviors)


def test_nested_mixed_language_harness_is_scoped_to_python(tmp_path: Path) -> None:
    _write(tmp_path / "platform/cmd/server/main.go", "package main\n")
    _write(tmp_path / "harness/src/agent.py", AGENT_SOURCE)
    _write(
        tmp_path / "harness/tests/test_agent.py",
        "from agent import support_agent\n"
        "def test_run():\n    result = support_agent.run_sync('hi')\n    assert result\n",
    )
    report, scan = diagnose_repository(tmp_path)
    assert report is not None
    assert "Pydantic AI" in report.frameworks_detected
    assert report.mixed_language_repository is True
    assert report.unsupported_source_counts == {"Go": 1}
    assert report.candidate_pairs > 0
    assert not scan.warnings
