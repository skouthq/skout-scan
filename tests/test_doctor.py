"""Tests for read-only repository compatibility diagnostics."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.cli import app

runner = CliRunner()


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _doctor_json(root: Path, *arguments: str) -> dict[str, object]:
    result = runner.invoke(
        app,
        ["doctor", "--repository", str(root), "--json", *arguments],
    )
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output
    assert "\r" not in result.output
    return json.loads(result.output)


def test_doctor_defaults_to_current_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Repository:" in result.output
    assert tmp_path.name in result.output
    assert not (tmp_path / ".agentguard").exists()


def test_doctor_reports_healthy_supported_repository_without_writing_state(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(
        tmp_path,
        "tests/test_agent.py",
        "def test_lookup():\n    result = lookup('key')\n    assert result == 'key'\n",
    )

    result = runner.invoke(app, ["doctor", "--repository", str(tmp_path)])

    assert result.exit_code == 0
    assert "Skout repository diagnostics" in result.output
    assert "Python tool patterns" in result.output
    assert "Pytest scenarios: 1" in result.output
    assert "Total behaviors: 1" in result.output
    assert "Candidate pairs: 1" in result.output
    assert "Ready for coverage assessment" in result.output
    assert not (tmp_path / ".agentguard").exists()


def test_doctor_json_is_machine_readable_and_reports_configuration(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agentguard.toml", 'exclude = ["vendor/**"]\n')
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(tmp_path, "vendor/ignored.py", "value = 1\n")
    _write(tmp_path, "output/ignored.py", "value = 1\n")

    report = _doctor_json(tmp_path, "--exclude", "output/**")

    assert report["config_excludes"] == ["vendor/**"]
    assert report["cli_excludes"] == ["output/**"]
    assert report["artifact_total"] == 1
    assert report["excluded_path_count"] == 2
    assert report["skipped_counts"] == {"excluded": 2}
    assert report["readiness"] == "ready"
    assert not (tmp_path / ".agentguard").exists()


def test_doctor_is_inconclusive_for_ordinary_python_without_supported_behaviors(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "application.py", "def add(left, right):\n    return left + right\n")

    report = _doctor_json(tmp_path)

    assert report["behavior_total"] == 0
    assert report["readiness"] == "inconclusive"
    assert any(
        "no supported agent behaviors" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_recommends_eval_discovery_when_behaviors_have_no_evals(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")

    report = _doctor_json(tmp_path)

    assert report["behavior_total"] == 1
    assert report["pytest_scenarios"] == 0
    assert any(
        "no supported eval scenarios" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_reports_evals_without_deterministic_candidate_pairs(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(
        tmp_path,
        "tests/test_unrelated.py",
        "def test_unrelated():\n    result = calculate_total()\n    assert result == 3\n",
    )

    report = _doctor_json(tmp_path)

    assert report["pytest_scenarios"] == 1
    assert report["candidate_pairs"] == 0
    assert any(
        "no deterministic candidate pairs" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_explains_unavailable_assessments_with_evidence_category(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    _write(
        tmp_path,
        "evals/cases.jsonl",
        'not json\n{"input":"lookup key","metadata":{"tools":["lookup"]}}\n',
    )

    report = _doctor_json(tmp_path)

    assert report["unavailable_assessments"] == 1
    assert report["readiness"] == "inconclusive"
    assert any(
        "1 eval source file(s) have uncertain evidence" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_marks_dynamic_crewai_repository_partially_assessable(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "crew.py",
        """
from crewai import Agent
from crewai.tools import tool

@tool
def lookup(query):
    return query

agent = Agent(role="Researcher", tools=load_tools())
""",
    )

    report = _doctor_json(tmp_path)

    assert "CrewAI" in report["frameworks_detected"]
    assert report["behavior_total"] >= 1
    assert report["behavior_warning_count"] >= 1
    assert report["readiness"] == "partially_assessable"
    assert any(
        "dynamic construct warning" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_suggests_excluding_large_generated_scope(tmp_path: Path) -> None:
    _write(tmp_path, "agent.py", "@tool\ndef lookup(key):\n    return key\n")
    for index in range(20):
        _write(tmp_path, f"output/generated_{index}.py", "value = 1\n")

    report = _doctor_json(tmp_path)

    assert report["suspicious_in_scope"] == {"output": 20}
    assert any(
        "Large generated, output, cache, or vendor paths" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_reports_jsonl_classification_and_linked_instruction_evidence(
    tmp_path: Path,
) -> None:
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
        "fact_check:\n"
        "  description: Check facts\n"
        "  instructions_file: ../skills/fact-checking/instructions.md\n",
    )
    _write(
        tmp_path,
        "src/example_crew/skills/fact-checking/instructions.md",
        "Verify every source.\n",
    )
    _write(tmp_path, "knowledge/memory.jsonl", '{"memory":"fact"}\n')
    _write(
        tmp_path,
        "data/mixed.jsonl",
        '{"input":"looks like an eval"}\n{"memory":"application data"}\n',
    )

    report = _doctor_json(tmp_path)

    assert report["crewai_config_files_referenced"] == 1
    assert report["crewai_config_files_parsed"] == 1
    assert report["linked_instruction_files"] == 1
    assert report["jsonl_non_eval_files"] == 1
    assert report["jsonl_ambiguous_files"] == 1
    assert any(
        "natural-language requirements" in recommendation
        for recommendation in report["recommendations"]
    )


def test_doctor_rejects_nonexistent_repository(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor", "--repository", str(tmp_path / "missing")],
    )

    assert result.exit_code != 0
    assert "Repository path does not exist" in result.output
