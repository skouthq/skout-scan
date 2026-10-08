"""Regression tests for the public framework examples."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copy2, copytree

import pytest

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.findings import update_findings
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    BehaviorExtractionResult,
    BehaviorSourceType,
    BehaviorType,
    CoverageStatus,
    EvalParseResult,
    FindingStatus,
    MatchingResult,
    ScanResult,
)
from agentguard.scanners import scan_repository

REPOSITORY_ROOT = Path(__file__).parents[1]
EXAMPLES_ROOT = REPOSITORY_ROOT / "examples"
FIRST_SCAN = datetime(2026, 1, 1, tzinfo=UTC)
SECOND_SCAN = FIRST_SCAN + timedelta(days=1)


def _analyze(
    root: Path,
) -> tuple[ScanResult, BehaviorExtractionResult, EvalParseResult, MatchingResult]:
    scan = scan_repository(root)
    behaviors = extract_behaviors(scan)
    tools = {
        behavior.subject
        for behavior in behaviors.behaviors
        if behavior.behavior_type is BehaviorType.TOOL_INVOCATION
    }
    agents = {
        behavior.subject
        for behavior in behaviors.behaviors
        if behavior.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT
    }
    evals = parse_eval_artifacts(
        scan,
        known_tool_names=tools,
        known_agent_names=agents,
    )
    matching = match_behaviors_to_evals(behaviors, evals)
    return scan, behaviors, evals, matching


@pytest.mark.parametrize(
    ("directory", "framework", "subject", "solution_source", "solution_target"),
    [
        (
            "langgraph-agent",
            "LangGraph",
            "review_graph",
            "evals/escalation_path.jsonl.example",
            "evals/escalation_path.jsonl",
        ),
        (
            "crewai-agent",
            "CrewAI",
            "escalate_refund",
            "tests/solutions/test_escalation.py.example",
            "tests/test_escalation.py",
        ),
        (
            "pydantic-ai-agent",
            "Pydantic AI",
            "validate_refund",
            "tests/solutions/test_retry.py.example",
            "tests/test_retry.py",
        ),
    ],
)
def test_public_example_detects_and_resolves_intentional_gap(
    tmp_path: Path,
    directory: str,
    framework: str,
    subject: str,
    solution_source: str,
    solution_target: str,
) -> None:
    root = tmp_path / directory
    copytree(EXAMPLES_ROOT / directory, root)

    scan, behaviors, evals, matching = _analyze(root)
    assert not scan.errors
    assert len(behaviors.behaviors) > 0
    assert len(evals.scenarios) > 0
    assert matching.candidate_pair_count > 0
    if framework == "LangGraph":
        assert any(
            behavior.source_type is BehaviorSourceType.LANGGRAPH_WORKFLOW
            for behavior in behaviors.behaviors
        )
    else:
        assert framework in {summary.framework for summary in behaviors.framework_summaries}

    first = update_findings(root, behaviors, matching, observed_at=FIRST_SCAN)
    intended = next(
        finding
        for finding in first.findings
        if finding.behavior_subject == subject and finding.status is FindingStatus.OPEN
    )

    target = root / solution_target
    target.parent.mkdir(parents=True, exist_ok=True)
    copy2(root / solution_source, target)
    _, next_behaviors, next_evals, next_matching = _analyze(root)
    second = update_findings(
        root,
        next_behaviors,
        next_matching,
        observed_at=SECOND_SCAN,
    )
    resolved = next(
        finding for finding in second.findings if finding.finding_id == intended.finding_id
    )

    assert resolved.status is FindingStatus.RESOLVED
    assert resolved.coverage_status is CoverageStatus.COVERED
    assert resolved.observed_resolution is True
    assert resolved.resolution_evidence is not None
    assert resolved.resolution_evidence.matched_eval_ids
    assert any(
        scenario.eval_id in resolved.resolution_evidence.matched_eval_ids
        and scenario.source_file == solution_target
        for scenario in next_evals.scenarios
    )
