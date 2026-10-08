"""Read-only repository compatibility diagnostics for ``skout doctor``."""

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import (
    ArtifactType,
    AssessmentAvailability,
    BehaviorExtractionResult,
    BehaviorSourceType,
    BehaviorType,
    DoctorReport,
    EvalParseResult,
    EvalSourceType,
    MatchingResult,
    RepositoryReadiness,
    ScanCompleteness,
    ScanResult,
    SkipReason,
)
from agentguard.scanners import scan_repository

SUSPICIOUS_SCOPE_PARTS = frozenset(
    {"cache", "caches", "generated", "output", "outputs", "vendor", "vendored"}
)
LARGE_SCOPE_THRESHOLD = 20


def _artifact_counts(scan: ScanResult) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for artifact in scan.artifacts:
        key = (
            "jsonl"
            if artifact.artifact_type is ArtifactType.EVAL_JSONL
            else artifact.artifact_type.value
        )
        counts[key] += 1
    return dict(sorted(counts.items()))


def _excluded_categories(scan: ScanResult) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for skipped in scan.skipped:
        if skipped.reason is not SkipReason.EXCLUDED:
            continue
        parts = Path(skipped.path).parts
        counts[parts[0] if parts else skipped.path] += 1
    return dict(sorted(counts.items()))


def _skipped_counts(scan: ScanResult) -> dict[str, int]:
    return dict(sorted(Counter(item.reason.value for item in scan.skipped).items()))


def _suspicious_scope(scan: ScanResult) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for artifact in scan.artifacts:
        matching_part = next(
            (
                part
                for part in Path(artifact.path).parts[:-1]
                if part.casefold() in SUSPICIOUS_SCOPE_PARTS
            ),
            None,
        )
        if matching_part is not None:
            counts[matching_part] += 1
    return dict(sorted(counts.items()))


def _frameworks(behaviors: BehaviorExtractionResult) -> tuple[str, ...]:
    detected = {summary.framework for summary in behaviors.framework_summaries}
    if any(
        behavior.source_type is BehaviorSourceType.LANGGRAPH_WORKFLOW
        for behavior in behaviors.behaviors
    ):
        detected.add("LangGraph")
    if any(
        behavior.behavior_type is BehaviorType.TOOL_INVOCATION
        and behavior.source_type is BehaviorSourceType.PYTHON_TOOL
        for behavior in behaviors.behaviors
    ):
        detected.add("Python tool patterns")
    return tuple(sorted(detected))


def _readiness(
    behaviors: BehaviorExtractionResult,
    evals: EvalParseResult,
    matching: MatchingResult,
) -> RepositoryReadiness:
    available = sum(
        assessment.availability is AssessmentAvailability.AVAILABLE
        for assessment in matching.assessments
    )
    unavailable = len(matching.assessments) - available
    if not behaviors.behaviors or available == 0:
        return RepositoryReadiness.INCONCLUSIVE
    if (
        unavailable
        or behaviors.completeness is ScanCompleteness.INCOMPLETE
        or evals.completeness is ScanCompleteness.INCOMPLETE
        or matching.completeness is ScanCompleteness.INCOMPLETE
    ):
        return RepositoryReadiness.PARTIALLY_ASSESSABLE
    return RepositoryReadiness.READY


def _recommendations(
    scan: ScanResult,
    behaviors: BehaviorExtractionResult,
    evals: EvalParseResult,
    matching: MatchingResult,
    suspicious: dict[str, int],
    linked_instruction_files: int,
) -> tuple[str, ...]:
    recommendations: list[str] = []
    python_files = sum(artifact.artifact_type is ArtifactType.PYTHON for artifact in scan.artifacts)
    if not behaviors.behaviors and python_files:
        recommendations.append(
            "Skout found Python code but no supported agent behaviors. Check for an unsupported "
            "framework, dynamic construction, or patterns Skout does not yet recognize."
        )
    if behaviors.behaviors and not evals.scenarios:
        recommendations.append(
            "Skout found agent behaviors but no supported eval scenarios. Verify that evals use "
            "pytest or recognized JSONL, or identify an unsupported eval framework."
        )
    if behaviors.behaviors and evals.scenarios and matching.candidate_pair_count == 0:
        recommendations.append(
            "Skout found behaviors and evals but no deterministic candidate pairs. Tests may "
            "exercise behavior indirectly, use unsupported wrappers, or lack matching symbol "
            "evidence."
        )
    unavailable = sum(
        assessment.availability is AssessmentAvailability.UNAVAILABLE
        for assessment in matching.assessments
    )
    if unavailable:
        causes: list[str] = []
        if behaviors.unavailable_behavior_ids:
            causes.append(
                f"{len(behaviors.unavailable_behavior_ids)} behavior(s) depend on incomplete "
                "extraction evidence"
            )
        if evals.uncertain_source_files:
            causes.append(
                f"{len(evals.uncertain_source_files)} eval source file(s) have uncertain evidence"
            )
        if matching.warnings or matching.errors:
            causes.append(
                f"{len(matching.warnings) + len(matching.errors)} matching diagnostic(s) were "
                "reported"
            )
        cause_text = "; ".join(causes) or "the extraction or matching phase was incomplete"
        recommendations.append(
            f"{unavailable} assessment(s) lack sufficient evidence because {cause_text}. Review "
            "the corresponding warnings before interpreting missing coverage."
        )
    unreadable_paths = sum(item.reason is SkipReason.UNREADABLE for item in scan.skipped)
    if unreadable_paths:
        recommendations.append(
            f"Skout could not read {unreadable_paths} path(s). Adjust repository permissions or "
            "exclude irrelevant unreadable paths before relying on the assessment."
        )
    large_paths = {
        path: count for path, count in suspicious.items() if count >= LARGE_SCOPE_THRESHOLD
    }
    if large_paths:
        names = ", ".join(f"{path}/ ({count} artifacts)" for path, count in large_paths.items())
        recommendations.append(
            "Large generated, output, cache, or vendor paths are in scope: "
            f"{names}. Add persistent "
            "agentguard.toml exclusions or temporary --exclude values if these artifacts are not "
            "relevant."
        )
    if evals.jsonl_ambiguous_files:
        recommendations.append(
            f"{evals.jsonl_ambiguous_files} ambiguous JSONL file(s) were skipped. Move intended "
            "evals under an eval-oriented path or use the supported input/expected schema."
        )
    dynamic_crewai = sum(
        warning.code.startswith("crewai_dynamic_") for warning in behaviors.warnings
    )
    if dynamic_crewai:
        recommendations.append(
            f"CrewAI extraction encountered {dynamic_crewai} dynamic construct warning(s). Static "
            "results are partial; runtime task, tool, or context relationships were not guessed."
        )
    dynamic_pydantic = sum(
        warning.code.startswith("pydantic_ai_dynamic_") for warning in behaviors.warnings
    )
    if dynamic_pydantic:
        recommendations.append(
            f"Pydantic AI extraction encountered {dynamic_pydantic} dynamic construct "
            "warning(s). Static tools, toolsets, or instructions were not guessed."
        )
    pydantic_cases = sum(
        scenario.source_type is EvalSourceType.PYDANTIC_EVAL for scenario in evals.scenarios
    )
    if pydantic_cases and not any(
        scenario.referenced_symbols
        for scenario in evals.scenarios
        if scenario.source_type is EvalSourceType.PYDANTIC_EVAL
    ):
        recommendations.append(
            "Pydantic Evals cases were found, but no deterministic agent/task association was "
            "found, so they are not used as coverage proof."
        )
    if scan.repository.unsupported_source_counts and any(
        summary.framework == "Pydantic AI" for summary in behaviors.framework_summaries
    ):
        recommendations.append(
            "Skout found supported Python agent/eval evidence in a mixed-language repository. "
            "Coverage assessment applies only to the supported Python surface; unsupported "
            "source languages are not analyzed."
        )
    if linked_instruction_files:
        recommendations.append(
            f"Skout linked {linked_instruction_files} instruction file(s) as evidence. Their "
            "natural-language requirements are not converted into coverage obligations in V0."
        )
    return tuple(recommendations)


def diagnose_repository(
    repository: str | Path,
    *,
    extra_excludes: Sequence[str] = (),
) -> tuple[DoctorReport | None, ScanResult]:
    """Run the read-only analysis pipeline and derive a diagnostic report."""
    scan = scan_repository(repository, extra_excludes=extra_excludes)
    if scan.completeness is ScanCompleteness.FAILED or scan.repository.root is None:
        return None, scan

    behaviors = extract_behaviors(scan)
    known_tools = {
        behavior.subject
        for behavior in behaviors.behaviors
        if behavior.behavior_type is BehaviorType.TOOL_INVOCATION
    }
    known_agents = {
        behavior.subject
        for behavior in behaviors.behaviors
        if behavior.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT
    }
    evals = parse_eval_artifacts(scan, known_tool_names=known_tools, known_agent_names=known_agents)
    matching = match_behaviors_to_evals(behaviors, evals)
    artifact_counts = _artifact_counts(scan)
    behavior_counts = dict(
        sorted(Counter(behavior.behavior_type.value for behavior in behaviors.behaviors).items())
    )
    eval_counts = Counter(scenario.source_type for scenario in evals.scenarios)
    available = sum(
        assessment.availability is AssessmentAvailability.AVAILABLE
        for assessment in matching.assessments
    )
    unavailable = len(matching.assessments) - available
    suspicious = _suspicious_scope(scan)
    crewai = next(
        (summary for summary in behaviors.framework_summaries if summary.framework == "CrewAI"),
        None,
    )
    linked_instruction_files = crewai.linked_instruction_files if crewai else 0
    report = DoctorReport(
        repository=scan.repository.root,
        config_path=scan.repository.config_path,
        include_patterns=scan.repository.include_patterns,
        default_excludes=scan.repository.default_exclude_patterns,
        config_excludes=scan.repository.config_exclude_patterns,
        cli_excludes=scan.repository.cli_exclude_patterns,
        effective_excludes=scan.repository.exclude_patterns,
        artifact_counts=artifact_counts,
        artifact_total=len(scan.artifacts),
        scan_warning_count=len(scan.warnings),
        skipped_counts=_skipped_counts(scan),
        excluded_path_count=sum(skipped.reason is SkipReason.EXCLUDED for skipped in scan.skipped),
        excluded_categories=_excluded_categories(scan),
        suspicious_in_scope=suspicious,
        frameworks_detected=_frameworks(behaviors),
        framework_construct_counts={
            summary.framework: summary.construct_counts for summary in behaviors.framework_summaries
        },
        pytest_scenarios=eval_counts[EvalSourceType.PYTEST],
        jsonl_scenarios=eval_counts[EvalSourceType.JSONL],
        jsonl_eval_files=evals.jsonl_eval_files,
        jsonl_non_eval_files=evals.jsonl_non_eval_files,
        jsonl_ambiguous_files=evals.jsonl_ambiguous_files,
        pydantic_eval_scenarios=eval_counts[EvalSourceType.PYDANTIC_EVAL],
        eval_warning_count=sum(warning.occurrences for warning in evals.warnings),
        behavior_counts=behavior_counts,
        behavior_total=len(behaviors.behaviors),
        behavior_warning_count=len(behaviors.warnings),
        available_assessments=available,
        unavailable_assessments=unavailable,
        candidate_pairs=matching.candidate_pair_count,
        markdown_artifacts=artifact_counts.get(ArtifactType.PROMPT_MARKDOWN.value, 0),
        text_artifacts=artifact_counts.get(ArtifactType.PROMPT_TEXT.value, 0),
        crewai_config_files_referenced=crewai.config_files_referenced if crewai else 0,
        crewai_config_files_parsed=crewai.config_files_parsed if crewai else 0,
        crewai_config_files_failed=crewai.config_files_failed if crewai else 0,
        crewai_config_agents=crewai.config_agents if crewai else 0,
        crewai_config_tasks=crewai.config_tasks if crewai else 0,
        linked_instruction_files=linked_instruction_files,
        unsupported_source_counts=scan.repository.unsupported_source_counts,
        mixed_language_repository=bool(scan.repository.unsupported_source_counts),
        recommendations=_recommendations(
            scan,
            behaviors,
            evals,
            matching,
            suspicious,
            linked_instruction_files,
        ),
        readiness=_readiness(behaviors, evals, matching),
    )
    return report, scan
