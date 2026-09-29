"""Command-line interface for Skout Scan."""

import json
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.feedback import (
    ALREADY_COVERED_REASONS,
    NOT_RELEVANT_REASONS,
    FindingNotFoundError,
    FindingStore,
    InvalidFeedbackReasonError,
    review_queue,
)
from agentguard.findings import update_findings
from agentguard.matchers import match_behaviors_to_evals
from agentguard.metrics import calculate_validation_summary, export_validation_data
from agentguard.models import (
    ArtifactType,
    AssessmentAvailability,
    BehaviorExtractionResult,
    BehaviorType,
    CoverageStatus,
    EvalParseResult,
    EvalSourceType,
    FeedbackReason,
    FindingDisposition,
    FindingStatus,
    FindingUpdateResult,
    MatchingResult,
    ScanCompleteness,
    ScanResult,
)
from agentguard.progress import ScanProgressReporter
from agentguard.scanners import scan_repository

PACKAGE_NAME = "skout-scan"

app = typer.Typer(
    help="Find potentially important AI-agent behaviors that lack adequate eval coverage.",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()
error_console = Console(stderr=True)


class BreakdownOption(StrEnum):
    """Finding attributes available for metrics breakdown output."""

    BEHAVIOR_TYPE = "behavior_type"
    SOURCE_FILE = "source_file"
    CONFIDENCE = "confidence"
    COVERAGE_STATUS = "coverage_status"
    REJECTION_REASON = "rejection_reason"
    ALL = "all"
    NONE = "none"


def get_version() -> str:
    """Return the version from the installed package metadata."""
    return version(PACKAGE_NAME)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(get_version())
        raise typer.Exit()


def _combined_completeness(
    result: ScanResult,
    eval_result: EvalParseResult | None,
    behavior_result: BehaviorExtractionResult | None,
    matching_result: MatchingResult | None,
) -> ScanCompleteness:
    statuses = [result.completeness]
    statuses.extend(
        extraction.completeness
        for extraction in (eval_result, behavior_result, matching_result)
        if extraction is not None
    )
    if ScanCompleteness.FAILED in statuses:
        return ScanCompleteness.FAILED
    if ScanCompleteness.INCOMPLETE in statuses:
        return ScanCompleteness.INCOMPLETE
    return ScanCompleteness.COMPLETE


def _progress_detail(
    count: int,
    noun: str,
    *,
    warnings: int = 0,
    errors: int = 0,
) -> str:
    """Format only counts already produced by a completed scan phase."""
    parts = [f"{count:,} {noun}"]
    if warnings:
        parts.append(f"{warnings:,} warning{'s' if warnings != 1 else ''}")
    if errors:
        parts.append(f"{errors:,} error{'s' if errors != 1 else ''}")
    return ", ".join(parts)


def _render_scan_result(
    result: ScanResult,
    eval_result: EvalParseResult | None = None,
    behavior_result: BehaviorExtractionResult | None = None,
    matching_result: MatchingResult | None = None,
    finding_result: FindingUpdateResult | None = None,
) -> None:
    completeness = _combined_completeness(result, eval_result, behavior_result, matching_result)
    output = error_console if completeness is ScanCompleteness.FAILED else console
    repository = result.repository.root or result.repository.requested_path
    output.print(f"Repository: {repository}", soft_wrap=True, markup=False)
    output.print(f"Status: {completeness.value}", markup=False)

    if result.completeness is not ScanCompleteness.FAILED:
        counts = {artifact_type: 0 for artifact_type in ArtifactType}
        for artifact in result.artifacts:
            counts[artifact.artifact_type] += 1

        table = Table(title="Discovered artifacts")
        table.add_column("Type")
        table.add_column("Count", justify="right")
        for artifact_type in ArtifactType:
            table.add_row(artifact_type.value, str(counts[artifact_type]))
        table.add_section()
        table.add_row("total", str(len(result.artifacts)))
        output.print(table)

        if eval_result is not None:
            eval_counts = {source_type: 0 for source_type in EvalSourceType}
            for scenario in eval_result.scenarios:
                eval_counts[scenario.source_type] += 1

            eval_table = Table(title="Discovered evals")
            eval_table.add_column("Source")
            eval_table.add_column("Count", justify="right")
            for source_type in EvalSourceType:
                eval_table.add_row(source_type.value, str(eval_counts[source_type]))
            eval_table.add_section()
            eval_table.add_row("total", str(len(eval_result.scenarios)))
            output.print(eval_table)
            output.print(f"Eval parse warnings: {len(eval_result.warnings)}", markup=False)

        if behavior_result is not None:
            behavior_counts = {behavior_type: 0 for behavior_type in BehaviorType}
            for behavior in behavior_result.behaviors:
                behavior_counts[behavior.behavior_type] += 1

            behavior_table = Table(title="Detected behaviors")
            behavior_table.add_column("Type")
            behavior_table.add_column("Count", justify="right")
            for behavior_type in BehaviorType:
                behavior_table.add_row(behavior_type.value, str(behavior_counts[behavior_type]))
            behavior_table.add_section()
            behavior_table.add_row("total", str(len(behavior_result.behaviors)))
            output.print(behavior_table)
            output.print(
                f"Behavior extraction warnings: {len(behavior_result.warnings)}",
                markup=False,
            )

        if matching_result is not None:
            coverage_counts = {status: 0 for status in CoverageStatus}
            unavailable = 0
            for assessment in matching_result.assessments:
                if assessment.availability is AssessmentAvailability.UNAVAILABLE:
                    unavailable += 1
                elif assessment.coverage_status is not None:
                    coverage_counts[assessment.coverage_status] += 1

            matching_table = Table(title="Coverage assessments")
            matching_table.add_column("Status")
            matching_table.add_column("Count", justify="right")
            for status in CoverageStatus:
                matching_table.add_row(status.value, str(coverage_counts[status]))
            matching_table.add_row("unavailable", str(unavailable))
            output.print(matching_table)
            output.print(
                f"Candidate pairs considered: {matching_result.candidate_pair_count}",
                markup=False,
            )

        if finding_result is not None:
            finding_table = Table(title="Actionable findings")
            finding_table.add_column("Lifecycle")
            finding_table.add_column("Count", justify="right")
            finding_table.add_row("new", str(finding_result.new_count))
            finding_table.add_row("existing", str(finding_result.existing_count))
            finding_table.add_row("resolved", str(finding_result.resolved_count))
            finding_table.add_row("reopened", str(finding_result.reopened_count))
            finding_table.add_row(
                "no_longer_observed", str(finding_result.no_longer_observed_count)
            )
            output.print(finding_table)
            visible = [
                finding
                for finding in finding_result.findings
                if finding.status is FindingStatus.OPEN
                and finding.current_disposition is not FindingDisposition.SUPPRESSED
            ][:5]
            if visible:
                output.print("Open findings:")
                for finding in visible:
                    output.print(
                        f"  {finding.finding_id}: {finding.title} [{finding.source_file}]",
                        markup=False,
                    )

        if result.skipped:
            output.print(f"Skipped paths: {len(result.skipped)}", markup=False)
            for skipped_path in result.skipped:
                output.print(f"  {skipped_path.path} ({skipped_path.reason.value})", markup=False)

    if result.warnings:
        output.print("Warnings:")
        for scan_warning in result.warnings:
            location = f" [{scan_warning.path}]" if scan_warning.path else ""
            output.print(f"  {scan_warning.message}{location}", markup=False)

    if result.errors:
        output.print("Errors:")
        for scan_error in result.errors:
            output.print(f"  {scan_error.message}", markup=False)

    if eval_result is not None and eval_result.warnings:
        output.print("Eval parse warnings:")
        for eval_warning in eval_result.warnings:
            location = (
                f"{eval_warning.source_file}:{eval_warning.line}"
                if eval_warning.line
                else eval_warning.source_file
            )
            output.print(f"  {eval_warning.message} [{location}]", markup=False)

    if eval_result is not None and eval_result.errors:
        output.print("Eval parse errors:")
        for eval_error in eval_result.errors:
            output.print(f"  {eval_error.message} [{eval_error.source_file}]", markup=False)

    if behavior_result is not None and behavior_result.warnings:
        output.print("Behavior extraction warnings:")
        for behavior_warning in behavior_result.warnings:
            location = (
                f"{behavior_warning.source_file}:{behavior_warning.line}"
                if behavior_warning.line
                else behavior_warning.source_file
            )
            output.print(f"  {behavior_warning.message} [{location}]", markup=False)

    if behavior_result is not None and behavior_result.errors:
        output.print("Behavior extraction errors:")
        for behavior_error in behavior_result.errors:
            output.print(f"  {behavior_error.message} [{behavior_error.source_file}]", markup=False)

    if matching_result is not None and matching_result.warnings:
        output.print("Matching warnings:")
        for matching_warning in matching_result.warnings:
            output.print(f"  {matching_warning.message}", markup=False)

    if matching_result is not None and matching_result.errors:
        output.print("Matching errors:")
        for matching_error in matching_result.errors:
            output.print(f"  {matching_error.message}", markup=False)


@app.callback(invoke_without_command=True)
def main(
    context: typer.Context,
    version_requested: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed Skout Scan version and exit.",
        ),
    ] = False,
) -> None:
    """Run Skout Scan."""
    del version_requested
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


@app.command()
def scan(
    repository_path: Annotated[Path, typer.Argument(help="Repository directory to scan.")],
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable scan progress messages."),
    ] = False,
) -> None:
    """Discover artifacts and assess deterministic behavior coverage."""
    progress = ScanProgressReporter(console, enabled=not no_progress)
    progress.start(repository_path.expanduser().resolve())

    with progress.phase("Discovering repository artifacts", "Repository discovery"):
        result = scan_repository(repository_path)
    progress.complete(
        "Repository discovery",
        result.completeness,
        detail=_progress_detail(
            len(result.artifacts),
            "artifacts",
            warnings=len(result.warnings),
            errors=len(result.errors),
        ),
    )

    behavior_result: BehaviorExtractionResult | None = None
    eval_result: EvalParseResult | None = None
    matching_result: MatchingResult | None = None
    finding_result: FindingUpdateResult | None = None
    if result.completeness is not ScanCompleteness.FAILED:
        with progress.phase("Extracting agent behaviors", "Behavior extraction"):
            behavior_result = extract_behaviors(result)
        progress.complete(
            "Behavior extraction",
            behavior_result.completeness,
            detail=_progress_detail(
                len(behavior_result.behaviors),
                "behaviors",
                warnings=len(behavior_result.warnings),
                errors=len(behavior_result.errors),
            ),
        )

        with progress.phase("Parsing eval scenarios", "Eval extraction"):
            eval_result = parse_eval_artifacts(
                result,
                known_tool_names={
                    behavior.subject
                    for behavior in behavior_result.behaviors
                    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION
                },
            )
        progress.complete(
            "Eval extraction",
            eval_result.completeness,
            detail=_progress_detail(
                len(eval_result.scenarios),
                "scenarios",
                warnings=len(eval_result.warnings),
                errors=len(eval_result.errors),
            ),
        )

        with progress.phase("Matching behaviors to evals", "Behavior matching"):
            matching_result = match_behaviors_to_evals(behavior_result, eval_result)
        progress.complete(
            "Behavior matching",
            matching_result.completeness,
            detail=_progress_detail(
                matching_result.candidate_pair_count,
                "candidate pairs",
                warnings=len(matching_result.warnings),
                errors=len(matching_result.errors),
            ),
        )

        if result.repository.root is not None:
            with progress.phase("Updating findings", "Findings update"):
                finding_result = update_findings(
                    result.repository.root,
                    behavior_result,
                    matching_result,
                )
            open_count = sum(
                finding.status is FindingStatus.OPEN for finding in finding_result.findings
            )
            resolved_count = sum(
                finding.status is FindingStatus.RESOLVED for finding in finding_result.findings
            )
            progress.complete(
                "Findings update",
                _combined_completeness(result, eval_result, behavior_result, matching_result),
                detail=f"{open_count:,} open, {resolved_count:,} resolved",
            )
    _render_scan_result(
        result,
        eval_result,
        behavior_result,
        matching_result,
        finding_result,
    )
    if result.completeness is ScanCompleteness.FAILED:
        raise typer.Exit(code=1)


def _repository_store(repository: Path) -> FindingStore:
    supplied = repository.expanduser()
    if not supplied.exists():
        raise typer.BadParameter(f"Repository path does not exist: {repository}")
    if not supplied.is_dir():
        raise typer.BadParameter(f"Repository path is not a directory: {repository}")
    return FindingStore(supplied)


@app.command("findings")
def findings_command(
    repository: Annotated[
        Path,
        typer.Option("--repository", "-r", help="Repository containing Skout Scan state."),
    ] = Path("."),
) -> None:
    """Show persisted findings for a repository."""
    store = _repository_store(repository)
    findings = store.list_findings()
    if not findings:
        console.print("No persisted findings for this repository.")
        return

    table = Table(title="Skout Scan findings")
    table.add_column("Finding ID")
    table.add_column("Status")
    table.add_column("Coverage")
    table.add_column("Disposition")
    table.add_column("Title")
    for finding in findings:
        table.add_row(
            finding.finding_id,
            finding.status.value,
            finding.coverage_status.value,
            finding.current_disposition.value if finding.current_disposition else "-",
            finding.title,
        )
    console.print(table)
    for finding in findings:
        console.print(f"\n{finding.finding_id}", markup=False)
        console.print(f"  Source: {finding.source_file}", markup=False)
        if finding.source_evidence:
            console.print(f"  Source evidence: {finding.source_evidence[0].excerpt}", markup=False)
        console.print(f"  Explanation: {finding.explanation}", markup=False)
        candidate_eval_ids = tuple(match.eval_id for match in finding.matched_eval_evidence)
        if candidate_eval_ids:
            console.print(
                f"  Candidate evals considered: {', '.join(candidate_eval_ids)}",
                markup=False,
            )
        if finding.matched_eval_ids:
            console.print(f"  Matched evals: {', '.join(finding.matched_eval_ids)}", markup=False)
        if finding.suggested_scenario:
            console.print(f"  Suggested scenario: {finding.suggested_scenario}", markup=False)
        console.print(
            f"  Observed resolution: {'yes' if finding.observed_resolution else 'no'}",
            markup=False,
        )
        console.print(
            f"  Confirmed impact: {'yes' if finding.confirmed_impact else 'no'}",
            markup=False,
        )


@app.command("feedback")
def feedback_command(
    finding_id: Annotated[str, typer.Argument(help="Stable finding ID.")],
    disposition: Annotated[FindingDisposition, typer.Argument(help="Feedback disposition.")],
    repository: Annotated[
        Path,
        typer.Option("--repository", "-r", help="Repository containing Skout Scan state."),
    ] = Path("."),
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Optional explanation for this disposition."),
    ] = None,
    feedback_reason: Annotated[
        FeedbackReason | None,
        typer.Option(
            "--feedback-reason",
            help="Optional structured reason for already_covered or not_relevant.",
        ),
    ] = None,
) -> None:
    """Persist a user disposition for one finding."""
    store = _repository_store(repository)
    try:
        finding = store.record_feedback(
            finding_id,
            disposition,
            reason=reason,
            feedback_reason=feedback_reason,
        )
    except (FindingNotFoundError, InvalidFeedbackReasonError) as error:
        error_console.print(str(error), markup=False)
        raise typer.Exit(code=1) from error
    console.print(
        f"Recorded {disposition.value} for {finding.finding_id}.",
        markup=False,
    )


@app.command("confirm-impact")
def confirm_impact_command(
    finding_id: Annotated[str, typer.Argument(help="Stable finding ID.")],
    repository: Annotated[
        Path,
        typer.Option("--repository", "-r", help="Repository containing Skout Scan state."),
    ] = Path("."),
    note: Annotated[
        str | None,
        typer.Option("--note", help="Optional impact confirmation note."),
    ] = None,
) -> None:
    """Explicitly confirm that a finding influenced an eval change."""
    store = _repository_store(repository)
    try:
        finding = store.confirm_impact(finding_id, note=note)
    except FindingNotFoundError as error:
        error_console.print(str(error), markup=False)
        raise typer.Exit(code=1) from error
    console.print(f"Confirmed impact for {finding.finding_id}.", markup=False)


def _format_rate(rate: float | None) -> str:
    return "not enough data" if rate is None else f"{rate:.1%}"


@app.command("metrics")
def metrics_command(
    repository: Annotated[
        Path,
        typer.Option("--repository", "-r", help="Repository containing Skout Scan state."),
    ] = Path("."),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable local JSON export."),
    ] = False,
    breakdown: Annotated[
        BreakdownOption,
        typer.Option("--breakdown", help="Quality breakdown to display."),
    ] = BreakdownOption.BEHAVIOR_TYPE,
) -> None:
    """Show repository-local feedback, resolution, and V0 validation metrics."""
    store = _repository_store(repository)
    if json_output:
        typer.echo(json.dumps(export_validation_data(store), indent=2, sort_keys=True))
        return

    summary = calculate_validation_summary(store)
    console.print("Skout Scan Validation Summary", style="bold")
    console.print(f"Repository: {summary.repository}", markup=False)
    console.print(
        f"Findings: {summary.finding_count} ({summary.reviewed_finding_count} reviewed)",
        markup=False,
    )
    metric_table = Table(title="V0 feedback and outcome metrics")
    metric_table.add_column("Metric")
    metric_table.add_column("Result")
    metric_table.add_column("Count")
    for metric in summary.metrics:
        metric_table.add_row(
            metric.name.value,
            _format_rate(metric.rate),
            f"{metric.numerator}/{metric.denominator}",
        )
    console.print(metric_table)
    console.print("Observed resolution does not establish Skout Scan-caused impact.")

    if breakdown is not BreakdownOption.NONE:
        selected = summary.breakdowns
        if breakdown is not BreakdownOption.ALL:
            selected = tuple(item for item in selected if item.dimension == breakdown.value)
        breakdown_table = Table(title="Finding quality breakdown")
        breakdown_table.add_column("Dimension")
        breakdown_table.add_column("Value")
        breakdown_table.add_column("Total", justify="right")
        breakdown_table.add_column("Reviewed", justify="right")
        breakdown_table.add_column("Valid", justify="right")
        breakdown_table.add_column("False positive", justify="right")
        for item in selected:
            breakdown_table.add_row(
                item.dimension,
                item.value,
                str(item.total),
                str(item.reviewed),
                str(item.valid_gap),
                str(item.already_covered),
            )
        console.print(breakdown_table)

    progress_table = Table(title="V0 validation progress (repository-local)")
    progress_table.add_column("Criterion")
    progress_table.add_column("Current")
    progress_table.add_column("Target")
    progress_table.add_column("Status")
    for criterion in summary.criteria:
        progress_table.add_row(
            criterion.name,
            criterion.current,
            criterion.target,
            criterion.status.value,
        )
    console.print(progress_table)


def _prompt_feedback_reason(disposition: FindingDisposition) -> FeedbackReason | None:
    if disposition is FindingDisposition.ALREADY_COVERED:
        allowed = ALREADY_COVERED_REASONS
    elif disposition is FindingDisposition.NOT_RELEVANT:
        allowed = NOT_RELEVANT_REASONS
    else:
        return None
    choices = ", ".join(sorted(reason.value for reason in allowed))
    while True:
        value = typer.prompt(
            f"Optional reason ({choices}; Enter to omit)", default="", show_default=False
        ).strip()
        if not value:
            return None
        try:
            reason = FeedbackReason(value)
        except ValueError:
            console.print(f"Unknown reason: {value}", markup=False)
            continue
        if reason in allowed:
            return reason
        console.print(f"Reason {value} is not valid for {disposition.value}.", markup=False)


@app.command("review")
def review_command(
    repository: Annotated[
        Path,
        typer.Option("--repository", "-r", help="Repository containing Skout Scan state."),
    ] = Path("."),
) -> None:
    """Interactively review open findings that have no disposition."""
    store = _repository_store(repository)
    queue = review_queue(store.list_findings())
    if not queue:
        console.print("No open, undispositioned findings to review.")
        return

    choices: dict[str, FindingDisposition | None] = {
        disposition.value: disposition for disposition in FindingDisposition
    }
    choices["skip"] = None
    reviewed = 0
    skipped = 0
    for index, finding in enumerate(queue, start=1):
        console.rule(f"Finding {index}/{len(queue)}")
        console.print(f"{finding.finding_id}: {finding.title}", markup=False)
        console.print(
            f"Source: {finding.source_file}"
            + (f"::{finding.source_symbol}" if finding.source_symbol else ""),
            markup=False,
        )
        console.print(
            f"Coverage: {finding.coverage_status.value}; confidence: "
            f"{finding.current_confidence.value}",
            markup=False,
        )
        for evidence in finding.source_evidence:
            console.print(f"Source evidence: {evidence.excerpt}", markup=False)
        console.print(f"Why flagged: {finding.explanation}", markup=False)
        candidate_ids = tuple(match.eval_id for match in finding.matched_eval_evidence)
        console.print(
            "Evals considered: " + (", ".join(candidate_ids) if candidate_ids else "none"),
            markup=False,
        )
        for match in finding.matched_eval_evidence:
            status = match.coverage_status.value if match.coverage_status else "insufficient"
            console.print(
                f"  {match.eval_id}: {status}, confidence {match.confidence.value}",
                markup=False,
            )
            for detail in match.evidence.details:
                console.print(f"    Evidence: {detail}", markup=False)
        if finding.suggested_scenario:
            console.print(f"Suggested eval: {finding.suggested_scenario}", markup=False)
        while True:
            value = typer.prompt(
                "Disposition (add_eval, valid_later, already_covered, not_relevant, "
                "suppressed, skip)"
            ).strip()
            if value in choices:
                break
            console.print(f"Unknown disposition: {value}", markup=False)
        disposition = choices[value]
        if disposition is None:
            skipped += 1
            continue
        feedback_reason = _prompt_feedback_reason(disposition)
        store.record_feedback(
            finding.finding_id,
            disposition,
            feedback_reason=feedback_reason,
        )
        reviewed += 1
    console.print(f"Review complete: {reviewed} recorded, {skipped} skipped.", markup=False)
