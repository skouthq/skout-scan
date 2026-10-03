"""Deterministic extraction tests for common CrewAI patterns."""

from pathlib import Path

from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    ArtifactType,
    BehaviorSourceType,
    BehaviorType,
    DiscoveredArtifact,
    RepositoryMetadata,
    ScanCompleteness,
    ScanResult,
)
from agentguard.scanners import scan_repository

runner = CliRunner()


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _extract(root: Path):
    return extract_behaviors(scan_repository(root))


def test_direct_agent_task_and_sequential_crew_extract_structural_behaviors(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Agent, Crew, Process, Task

researcher = Agent(
    role="Researcher",
    goal="Find facts",
    backstory="Metadata only",
    tools=[search_tool],
    allow_delegation=False,
)
research = Task(
    description="Research",
    expected_output="A report",
    agent=researcher,
    tools=[search_tool],
)
write = Task(
    description="Write",
    expected_output="An article",
    agent=researcher,
    context=[research],
)
content_crew = Crew(
    agents=[researcher],
    tasks=[research, write],
    process=Process.sequential,
)
""",
    )

    result = _extract(tmp_path)

    assert result.completeness is ScanCompleteness.COMPLETE
    summary = result.framework_summaries[0]
    assert summary.framework == "CrewAI"
    assert summary.construct_counts["agent"] == 1
    assert summary.construct_counts["task"] == 2
    assert summary.construct_counts["crew"] == 1
    agent = next(item for item in result.framework_constructs if item.kind == "agent")
    assert agent.metadata["role"] == "Researcher"
    assert agent.metadata["goal"] == "Find facts"
    assert agent.metadata["backstory"] == "Metadata only"
    assert not any("resolve customer" in item.description for item in result.behaviors)
    transitions = [
        item for item in result.behaviors if item.behavior_type is BehaviorType.WORKFLOW_TRANSITION
    ]
    assert {(item.subject, item.action.target) for item in transitions if item.action} == {
        ("research", "write")
    }
    assert any(
        item.behavior_type is BehaviorType.TOOL_INVOCATION and item.subject == "search_tool"
        for item in result.behaviors
    )


def test_hierarchical_crew_records_process_without_inventing_task_order(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Crew, Process

team = Crew(
    agents=[researcher, writer],
    tasks=[research, write],
    process=Process.hierarchical,
    manager_agent=manager,
)
""",
    )

    result = _extract(tmp_path)

    crew = next(item for item in result.framework_constructs if item.kind == "crew")
    assert crew.metadata["process"] == "Process.hierarchical"
    assert crew.metadata["manager_agent"] == "manager"
    assert not any(
        item.behavior_type is BehaviorType.WORKFLOW_TRANSITION for item in result.behaviors
    )


def test_crewbase_yaml_config_and_decorated_methods_are_linked_statically(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/project/crew.py",
        """
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, after_kickoff, agent, before_kickoff, crew, task

@CrewBase
class ContentCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @before_kickoff
    def prepare(self, inputs):
        return inputs

    @after_kickoff
    def finalize(self, output):
        return output

    @agent
    def researcher(self):
        return Agent(config=self.agents_config["researcher"])

    @task
    def research_task(self):
        return Task(config=self.tasks_config["research_task"])

    @task
    def writing_task(self):
        return Task(
            config=self.tasks_config["writing_task"],
            context=[self.research_task()],
        )

    @crew
    def content(self):
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential)
""",
    )
    _write(
        tmp_path,
        "src/project/config/agents.yaml",
        """
researcher:
  role: Researcher
  goal: Find facts
  backstory: Metadata only
  tools:
    - web_search
""",
    )
    _write(
        tmp_path,
        "src/project/config/tasks.yaml",
        """
research_task:
  description: Research a topic
  expected_output: Notes
  agent: researcher
writing_task:
  description: Write the result
  expected_output: Article
  agent: researcher
  context:
    - research_task
""",
    )

    result = _extract(tmp_path)

    assert result.completeness is ScanCompleteness.COMPLETE
    assert {item.kind for item in result.framework_constructs} >= {
        "crew_base",
        "agent",
        "task",
        "crew",
        "before_kickoff_hook",
        "after_kickoff_hook",
    }
    researcher = next(
        item
        for item in result.framework_constructs
        if item.kind == "agent" and item.source_file.endswith("crew.py")
    )
    assert researcher.metadata["config_reference"] == "researcher"
    assert researcher.metadata["role"] == "Researcher"
    transitions = {
        (item.subject, item.action.target)
        for item in result.behaviors
        if item.behavior_type is BehaviorType.WORKFLOW_TRANSITION and item.action
    }
    assert ("research_task", "writing_task") in transitions
    assert any(
        item.source_file.endswith("tasks.yaml")
        and item.subject == "research_task"
        and item.action is not None
        and item.action.target == "writing_task"
        for item in result.behaviors
    )
    assert any(item.subject == "web_search" for item in result.behaviors)
    summary = result.framework_summaries[0]
    assert summary.config_files_referenced == 2
    assert summary.config_files_parsed == 2
    assert summary.config_files_failed == 0
    assert summary.config_agents == 1
    assert summary.config_tasks == 2


def test_module_level_literal_crewai_config_is_loaded(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Agent

agents_config = "config/agents.yaml"
researcher = Agent(config=agents_config["researcher"])
""",
    )
    _write(
        tmp_path,
        "config/agents.yaml",
        """
researcher:
  role: Researcher
  tools:
    - lookup
""",
    )

    result = _extract(tmp_path)

    assert result.completeness is ScanCompleteness.COMPLETE
    assert any(
        item.kind == "agent"
        and item.name == "researcher"
        and item.source_file == "config/agents.yaml"
        for item in result.framework_constructs
    )
    assert any(item.subject == "lookup" for item in result.behaviors)


def test_multiple_task_configs_are_counted_with_provenance(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/crews.py",
        """
from crewai.project import CrewBase

@CrewBase
class ArticleCrew:
    tasks_config = "config/article_tasks.yaml"

@CrewBase
class PodcastCrew:
    tasks_config = "config/podcast_tasks.yaml"
""",
    )
    _write(tmp_path, "src/config/article_tasks.yaml", "write_article:\n  description: Write\n")
    _write(tmp_path, "src/config/podcast_tasks.yaml", "record_show:\n  description: Record\n")

    result = _extract(tmp_path)
    summary = result.framework_summaries[0]

    assert summary.config_files_referenced == 2
    assert summary.config_files_parsed == 2
    assert summary.config_tasks == 2


def test_missing_and_malformed_crewai_configs_preserve_failed_provenance(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai.project import CrewBase

@CrewBase
class BrokenCrew:
    agents_config = "config/missing.yaml"
    tasks_config = "config/tasks.yaml"
""",
    )
    _write(tmp_path, "config/tasks.yaml", "task: [unterminated\n")

    result = _extract(tmp_path)
    summary = result.framework_summaries[0]

    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert summary.config_files_referenced == 2
    assert summary.config_files_parsed == 0
    assert summary.config_files_failed == 2
    assert {warning.code for warning in result.warnings} == {
        "crewai_config_unreadable",
        "crewai_no_supported_behaviors",
    }
    config_evidence = [
        construct for construct in result.framework_constructs if construct.kind == "config_file"
    ]
    assert all(construct.evidence[0].source_file == "crew.py" for construct in config_evidence)


def test_linked_instruction_is_evidence_without_invented_behavior(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/example_crew/crew.py",
        """
from crewai.project import CrewBase

@CrewBase
class ExampleCrew:
    tasks_config = "config/tasks.yaml"
""",
    )
    _write(
        tmp_path,
        "src/example_crew/config/tasks.yaml",
        """
fact_check:
  description: Check facts
  instructions_file: ../skills/fact-checking/instructions.md
""",
    )
    _write(
        tmp_path,
        "src/example_crew/skills/fact-checking/instructions.md",
        "Verify every source.",
    )
    _write(tmp_path, "docs/unrelated.md", "This is unrelated.")

    result = _extract(tmp_path)
    linked = [
        construct
        for construct in result.framework_constructs
        if construct.kind == "linked_instruction"
    ]

    assert [construct.name for construct in linked] == [
        "src/example_crew/skills/fact-checking/instructions.md"
    ]
    assert result.framework_summaries[0].linked_instruction_files == 1
    assert all("Verify every source" not in behavior.description for behavior in result.behaviors)


def test_crewai_tool_decorator_and_base_tool_subclass_are_recognized(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tools.py",
        """
from crewai.tools import BaseTool, tool

@tool
def lookup(query: str) -> str:
    return query

class TicketTool(BaseTool):
    name = "ticket"

    def _run(self, title: str) -> str:
        return title
""",
    )

    result = _extract(tmp_path)

    tools = {
        item.subject: item
        for item in result.behaviors
        if item.behavior_type is BehaviorType.TOOL_INVOCATION
    }
    assert {"lookup", "TicketTool"} <= tools.keys()
    assert tools["lookup"].source_type is BehaviorSourceType.PYTHON_TOOL
    assert tools["TicketTool"].source_type is BehaviorSourceType.CREWAI_TOOL
    assert tools["TicketTool"].arguments[0].name == "title"
    assert result.framework_summaries[0].construct_counts["tool"] == 2


def test_crewai_flow_start_listen_router_and_literal_targets(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "flow.py",
        """
from crewai.flow.flow import Flow, listen, router, start

class PublishingFlow(Flow):
    @start()
    def begin(self):
        return "draft"

    @listen(begin)
    def write(self):
        return "written"

    @router(write)
    def choose(self):
        if self.ready:
            return "publish"
        return "revise"

    @listen("publish")
    def finish(self):
        return "done"
""",
    )

    result = _extract(tmp_path)

    transitions = {
        (item.subject, item.action.target)
        for item in result.behaviors
        if item.behavior_type is BehaviorType.WORKFLOW_TRANSITION and item.action
    }
    assert {
        ("begin", "write"),
        ("write", "choose"),
        ("choose", "publish"),
        ("choose", "revise"),
        ("publish", "finish"),
    } <= transitions
    assert result.framework_summaries[0].construct_counts["flow"] == 1


def test_plain_json_config_is_supported_and_jsonc_is_explicitly_unsupported(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "json_crew.py",
        """
from crewai.project import CrewBase

@CrewBase
class JsonCrew:
    agents_config = "config/agents.json"
    tasks_config = "config/tasks.jsonc"
""",
    )
    _write(
        tmp_path,
        "config/agents.json",
        '{"researcher":{"role":"Researcher","tools":["lookup"]}}',
    )
    _write(tmp_path, "config/tasks.jsonc", '{"task": {/* comment */ "description":"x"}}')

    result = _extract(tmp_path)

    assert any(item.name == "researcher" for item in result.framework_constructs)
    assert any(item.subject == "lookup" for item in result.behaviors)
    assert {warning.code for warning in result.warnings} == {"crewai_jsonc_unsupported"}
    assert result.completeness is ScanCompleteness.INCOMPLETE


def test_dynamic_crewai_structures_warn_instead_of_inventing_behaviors(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "dynamic.py",
        """
from crewai import Agent, Crew, Process
from crewai.project import CrewBase
from crewai.tools import BaseTool

class StableTool(BaseTool):
    def _run(self):
        return "ok"

@CrewBase
class DynamicCrew:
    agents_config = config_path()

agent = Agent(role="Researcher", tools=load_tools())
crew = Crew(tasks=build_tasks(), agents=build_agents(), process=Process.sequential)
""",
    )

    result = _extract(tmp_path)

    codes = {warning.code for warning in result.warnings}
    assert {
        "crewai_dynamic_config_path_unsupported",
        "crewai_dynamic_tools_unsupported",
        "crewai_dynamic_task_order_unsupported",
    } <= codes
    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert not any(
        item.behavior_type is BehaviorType.WORKFLOW_TRANSITION for item in result.behaviors
    )
    matched = match_behaviors_to_evals(
        result,
        parse_eval_artifacts(scan_repository(tmp_path), known_tool_names={"StableTool"}),
    )
    stable_assessment = next(
        assessment
        for assessment in matched.assessments
        if assessment.behavior_id
        == next(item.behavior_id for item in result.behaviors if item.subject == "StableTool")
    )
    assert stable_assessment.availability.value == "available"
    assert stable_assessment.coverage_status is not None
    assert stable_assessment.coverage_status.value == "potentially_uncovered"


def test_arbitrary_framework_symbols_are_not_treated_as_crewai(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "other.py",
        """
class Agent:
    pass

class Flow:
    pass

agent = Agent()
""",
    )

    result = _extract(tmp_path)

    assert result.framework_summaries == ()
    assert result.framework_constructs == ()
    assert result.behaviors == ()


def test_zero_behavior_crewai_repo_is_incomplete_and_cli_is_inconclusive(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "agent.py",
        """
from crewai import Agent

support = Agent(role="Support", goal="Help customers")
""",
    )

    extracted = _extract(tmp_path)
    cli_result = runner.invoke(app, ["scan", str(tmp_path), "--no-progress"])

    assert extracted.behaviors == ()
    assert extracted.completeness is ScanCompleteness.INCOMPLETE
    assert extracted.warnings[0].code == "crewai_no_supported_behaviors"
    assert cli_result.exit_code == 0
    assert "Status: incomplete" in cli_result.output
    assert "No coverage assessment could be performed." in cli_result.output
    assert "CrewAI detected" in cli_result.output
    assert "Do not interpret this result as complete eval coverage." in cli_result.output


def test_attached_crewai_tool_reuses_deterministic_matching(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Agent

researcher = Agent(role="Researcher", tools=[search_tool])
""",
    )
    _write(
        tmp_path,
        "tests/test_crew.py",
        """
def test_search_tool():
    result = search_tool("topic")
    assert result == "facts"
""",
    )
    scan = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(
        scan,
        known_tool_names={
            item.subject
            for item in behaviors.behaviors
            if item.behavior_type is BehaviorType.TOOL_INVOCATION
        },
    )

    matched = match_behaviors_to_evals(behaviors, evals)

    tool_behavior = next(item for item in behaviors.behaviors if item.subject == "search_tool")
    assessment = next(
        item for item in matched.assessments if item.behavior_id == tool_behavior.behavior_id
    )
    assert assessment.coverage_status is not None
    assert assessment.coverage_status.value == "covered"


def test_attached_crewai_tool_without_verification_remains_partial(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Agent

researcher = Agent(role="Researcher", tools=[search_tool])
""",
    )
    _write(
        tmp_path,
        "tests/test_crew.py",
        """
def test_search_tool():
    search_tool("topic")
""",
    )
    scan = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(scan, known_tool_names={"search_tool"})

    matched = match_behaviors_to_evals(behaviors, evals)

    tool_behavior = next(item for item in behaviors.behaviors if item.subject == "search_tool")
    assessment = next(
        item for item in matched.assessments if item.behavior_id == tool_behavior.behavior_id
    )
    assert assessment.coverage_status is not None
    assert assessment.coverage_status.value == "partially_covered"


def test_eval_warning_deduplication_uses_stable_warning_identity(tmp_path: Path) -> None:
    _write(tmp_path, "tests/test_broken.py", "def broken(:\n")
    artifact = DiscoveredArtifact(
        path="tests/test_broken.py",
        artifact_type=ArtifactType.PYTHON,
        size_bytes=12,
    )
    duplicate_manifest = ScanResult(
        repository=RepositoryMetadata(requested_path=str(tmp_path), root=str(tmp_path)),
        artifacts=(artifact, artifact),
        completeness=ScanCompleteness.COMPLETE,
    )

    result = parse_eval_artifacts(duplicate_manifest, known_tool_names=set())

    assert len(result.warnings) == 1
    assert result.warnings[0].code == "python_syntax_error"


def test_cli_bounds_warning_details_and_keeps_category_count(tmp_path: Path) -> None:
    for index in range(30):
        _write(tmp_path, f"tests/test_broken_{index}.py", "def broken(:\n")

    result = runner.invoke(app, ["scan", str(tmp_path), "--no-progress"])

    assert result.exit_code == 0
    assert "Eval parse warnings: 30" in result.output
    assert "5 additional warning details not shown." in result.output
    assert "python_syntax_error: 30" in result.output


def test_real_world_shaped_crewai_repository_keeps_application_jsonl_out_of_evals(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "src/example_crew/crew.py",
        """
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class ExampleCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/article_tasks.yaml"

    @agent
    def researcher(self):
        return Agent(config=self.agents_config["researcher"])

    @task
    def article(self):
        return Task(config=self.tasks_config["article"])

    @crew
    def build(self):
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential)
""",
    )
    _write(
        tmp_path,
        "src/example_crew/config/agents.yaml",
        "researcher:\n  role: Researcher\n  tools:\n    - web_search\n",
    )
    _write(
        tmp_path,
        "src/example_crew/config/article_tasks.yaml",
        "article:\n"
        "  description: Write article\n"
        "  instructions_file: ../skills/article-writing/instructions.md\n",
    )
    _write(
        tmp_path,
        "src/example_crew/config/podcast_tasks.yaml",
        "podcast:\n  description: Record podcast\n",
    )
    _write(
        tmp_path,
        "src/example_crew/skills/article-writing/instructions.md",
        "Cite sources.",
    )
    _write(
        tmp_path,
        "src/example_crew/skills/fact-checking/instructions.md",
        "Check facts.",
    )
    _write(
        tmp_path,
        "knowledge/quality_memory/feedback_lessons.jsonl",
        '{"lesson":"verify claims","score":1}\n',
    )
    _write(
        tmp_path,
        "output/caches/research/cache_index.jsonl",
        '{"cache_key":"article-1"}\n',
    )
    _write(
        tmp_path,
        "tests/test_search.py",
        "def test_web_search():\n    result = web_search('topic')\n    assert result\n",
    )

    scan = scan_repository(tmp_path)
    behaviors = extract_behaviors(scan)
    evals = parse_eval_artifacts(scan, known_tool_names={"web_search"})
    matched = match_behaviors_to_evals(behaviors, evals)
    cli_result = runner.invoke(app, ["scan", str(tmp_path), "--no-progress"])

    assert len(behaviors.behaviors) > 0
    assert len(evals.scenarios) == 1
    assert evals.jsonl_non_eval_files == 2
    assert evals.warnings == ()
    assert matched.candidate_pair_count > 0
    assert all(assessment.availability.value == "available" for assessment in matched.assessments)
    assert cli_result.exit_code == 0
    assert "Config files referenced: 2" in cli_result.output
    assert "Successfully parsed: 2" in cli_result.output
    assert "Linked instruction files: 1" in cli_result.output
    assert "JSONL classification: 0 eval, 2 non-eval, 0 ambiguous" in cli_result.output
