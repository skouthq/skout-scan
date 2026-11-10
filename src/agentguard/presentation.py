"""Terminal-only views over existing assessments; never feed these back to matching/state."""

from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Console

from agentguard.guidance import OWNER_REASONS, guidance_for_assessment, with_guidance
from agentguard.models import (
    AssessmentAvailability,
    BehaviorCoverageAssessment,
    ConfidenceLevel,
    CoverageDimension,
    CoverageExplanation,
    CoverageReason,
    CoverageStatus,
    Finding,
    FindingGuidance,
    FindingStatus,
    RegistrationResolution,
    SourceEvidence,
)

DIMENSIONS = {
    CoverageDimension.FUNCTIONALITY: "correct callable or graph",
    CoverageDimension.CONDITION: "required condition",
    CoverageDimension.EXPECTED_OUTCOME: "expected outcome",
}
COVERAGE = {
    CoverageStatus.POTENTIALLY_UNCOVERED: "Potential eval gap",
    CoverageStatus.PARTIALLY_COVERED: "Partial verification",
    CoverageStatus.COVERED: "Qualifying verification evidence",
}
REGISTRATIONS = {
    "constructor_tool": "Tool in agent declaration",
    "decorator_tool": "Tool decorator",
    "output_validator_callback": "Output validator",
}


@dataclass(frozen=True)
class FindingPresentation:
    """An internal terminal view, intentionally absent from JSON and SQLite."""

    title: str
    coverage: str
    source: str
    owners: tuple[str, ...]
    behavior: tuple[str, ...]
    evidence: tuple[str, ...]
    next_step: str
    guidance: FindingGuidance | None
    detail: CoverageExplanation | None
    status: CoverageStatus | None
    confidence: ConfidenceLevel


def location(ref: SourceEvidence, *, span: bool = False, ascii_only: bool = False) -> str:
    value = ref.source_file
    if ref.start_line is not None:
        value += f":{ref.start_line}"
        if span and ref.end_line is not None and ref.end_line != ref.start_line:
            value += ("-" if ascii_only else "–") + str(ref.end_line)
    return value


def display_ids(findings: Sequence[Finding]) -> dict[str, str]:
    """Shortest unique prefix (at least eight chars); never accepted as canonical IDs."""
    identities = {f.finding_id for f in findings}
    tokens = {identity: identity.removeprefix("finding_") for identity in identities}
    result = {}
    for identity, token in tokens.items():
        length = min(8, len(token))
        while length < len(token) and any(
            other != identity and value.startswith(token[:length])
            for other, value in tokens.items()
        ):
            length += 1
        short = token[:length]
        # A full short token can itself be the prefix of another ID.
        result[identity] = (
            identity
            if any(other != identity and value == short for other, value in tokens.items())
            else short
        )
    return result


ICONS = {"Behavior": "▸", "Evidence": "◇", "Next step": "→", "Additional details": "≡"}
ASCII_ICONS = {"Behavior": ">", "Evidence": "?", "Next step": "->", "Additional details": "+"}


def unicode_supported(output: Console) -> bool:
    if output.legacy_windows:
        return False
    try:
        "▸◇→≡–·".encode(output.encoding)
    except (UnicodeError, LookupError):
        return False
    return True


def print_text(
    output: Console,
    text: str = "",
    *,
    style: str | None = None,
    markup: bool = False,
    highlight: bool = False,
) -> None:
    """Let Rich wrap cell widths; escape unrepresentable source text without losing it."""
    if not unicode_supported(output):
        text = text.encode(output.encoding, errors="backslashreplace").decode(output.encoding)
    output.print(text, style=style, markup=markup, highlight=highlight)


def _identity(detail: CoverageExplanation | None) -> tuple[str, str] | None:
    if detail is None:
        return None
    context = detail.rejection_provenance
    if context:
        if context.resolution is not RegistrationResolution.RESOLVED:
            return None
        return (
            (context.source_file, context.source_symbol)
            if context.callable_id and context.source_symbol
            else None
        )
    behavior = detail.behavior
    return (behavior.source_file, behavior.source_symbol) if behavior.source_symbol else None


def callable_display_names(findings: Sequence[Finding]) -> dict[str, str | None]:
    """Disambiguate existing source identities in the supplied inventory, without new analysis."""
    identities = {f.finding_id: _identity(f.structured_explanation) for f in findings}
    by_short_name: dict[str, set[tuple[str, str]]] = {}
    for identity in identities.values():
        if identity:
            by_short_name.setdefault(identity[1].rsplit(".", 1)[-1], set()).add(identity)
    return {
        key: None
        if identity is None
        else (
            f"{identity[0]}::{identity[1]}"
            if len(by_short_name[identity[1].rsplit(".", 1)[-1]]) > 1
            else identity[1]
        )
        for key, identity in identities.items()
    }


def _view(
    detail: CoverageExplanation | None,
    guidance: FindingGuidance | None,
    status: CoverageStatus | None,
    confidence: ConfidenceLevel,
    *,
    available: bool,
    title: str,
    source: str,
    suggestion: str | None = None,
    display_name: str | None = None,
) -> FindingPresentation:
    uncertain = (
        not available
        or confidence is ConfidenceLevel.LOW
        or detail is not None
        and guidance is None
        or guidance is not None
        and guidance.interpretation == "analysis_uncertain"
    )
    behavior = detail.behavior if detail else None
    context = detail.rejection_provenance if detail else None
    owners = context.owner_identities if context else ()
    lines: tuple[str, ...] = (title,)
    if behavior:
        action = behavior.action
        condition = behavior.condition.expression if behavior.condition else None
        if action and action.kind == "raise" and action.outcome and condition:
            lines = (f"If {condition}", f"raises {action.outcome}")
            title = f"{behavior.subject} rejection"
        elif action and action.kind == "transition" and action.target and condition:
            lines = (f"If {condition}", f"selects {action.target}")
            title = f"{behavior.subject} route"
        elif guidance:
            lines = (guidance.behavior_summary,)
            title = f"{behavior.subject} verification"
        else:
            lines = (behavior.description,)
            title = f"{behavior.subject} verification context"
        if behavior.evidence:
            source = location(behavior.evidence[0])
    if status is not CoverageStatus.COVERED and not uncertain and guidance:
        title += " may lack verification"
    evidence = []
    candidate = (
        next((m for m in guidance.observed_evidence if m.eval_id == guidance.closest_eval_id), None)
        if guidance
        else None
    )
    if uncertain:
        evidence.append(
            "Verification is inconclusive because the available analysis is "
            "incomplete, unavailable or unsupported."
        )
    elif status is CoverageStatus.COVERED:
        evidence.append("Qualifying verification evidence was found.")
    elif detail and OWNER_REASONS.intersection(detail.reason_codes):
        evidence.append(
            "A related eval was found, but its graph identity is ambiguous."
            if CoverageReason.GRAPH_OWNER_AMBIGUOUS in detail.reason_codes
            else "A related eval was found, but it does not verify the identity of this graph."
        )
    elif guidance and not guidance.observed_evidence:
        evidence.append("No qualifying eval candidates discovered.")
    elif detail is None:
        evidence.append(
            "Historical record lacks structured verification evidence; inspect saved details."
        )
    elif guidance and not candidate:
        evidence.append("Eval candidates were considered; no closest candidate was recorded.")
    if candidate and not uncertain:
        if not evidence:
            evidence.append("The closest eval does not verify all required dimensions.")
        evidence.append(
            "Closest eval: "
            + ((candidate.source_file + "::") if candidate.source_file else "")
            + (candidate.source_symbol or candidate.name or candidate.eval_id)
        )
        # These dimensions are the existing closest M8 decision, not a union of matches.
        verified = [
            DIMENSIONS[d] for d in CoverageDimension if d not in candidate.missing_dimensions
        ]
        if candidate.coverage_status is not None and verified:
            evidence.append("Verified: " + ", ".join(verified))
        if candidate.missing_dimensions:
            evidence.append(
                "Still missing: " + ", ".join(DIMENSIONS[d] for d in candidate.missing_dimensions)
            )
    next_step = (
        guidance.suggested_next_step
        if guidance
        else (
            suggestion
            or "Inspect the saved assessment; no supported verification scenario is available."
        )
    )
    if uncertain and guidance is None:
        next_step = (
            "Review the unavailable or unsupported evidence before deciding whether to add a test."
        )
    elif status is CoverageStatus.COVERED and guidance is None:
        next_step = (
            "Inspect the matched evidence; this assessment indicates no missing verification step."
        )
    if guidance and behavior and guidance.interpretation in {"assessable_gap", "partial_evidence"}:
        identity = _identity(detail)
        name = display_name or (identity[1] if identity else None)
        target = f"Target {behavior.source_file}::{behavior.source_symbol or behavior.subject}."
        generic = (
            "Target this graph."
            if behavior.action and behavior.action.kind == "transition"
            else "Target this callable."
        )
        next_step = next_step.replace(target, f"Test {name}." if name else generic)
        if behavior.condition:
            next_step = next_step.replace(
                f"Exercise the explicit condition {behavior.condition.expression}.",
                "Exercise the condition above.",
            )
        dimensions = {gap.dimension for gap in guidance.missing_evidence if gap.suggested_action}
        if (
            name
            and dimensions == set(CoverageDimension)
            and behavior.condition
            and behavior.action
            and behavior.action.kind == "raise"
            and behavior.action.outcome
        ):
            next_step = (
                f"Test {name} with the condition above "
                f"and explicitly assert {behavior.action.outcome}."
            )
        elif name:
            # A name locates the existing recommendation; it does not add another
            # missing dimension when the callable has already been verified.
            route_subject = f" for {behavior.subject}."
            if next_step.startswith(f"Test {name}."):
                next_step = next_step.replace(route_subject, ".")
            elif route_subject in next_step:
                next_step = next_step.replace(route_subject, f" for {name}.")
            else:
                next_step = f"For {name}, " + next_step[0].lower() + next_step[1:]
    return FindingPresentation(
        title,
        "Inconclusive verification"
        if uncertain
        else COVERAGE[status]
        if status
        else "Verification context",
        source,
        owners,
        lines,
        tuple(evidence),
        next_step,
        guidance,
        detail,
        status,
        confidence,
    )


def view_for_finding(finding: Finding, *, display_name: str | None = None) -> FindingPresentation:
    return _view(
        finding.structured_explanation,
        with_guidance(finding).guidance,
        finding.coverage_status,
        finding.current_confidence,
        available=finding.assessment_available,
        title=finding.title,
        source=location(finding.source_evidence[0])
        if finding.source_evidence
        else finding.source_file,
        suggestion=finding.suggested_scenario,
        display_name=display_name,
    )


def view_for_assessment(assessment: BehaviorCoverageAssessment) -> FindingPresentation:
    """Render assessment context without inventing a finding or persisting anything."""
    return _view(
        assessment.structured_explanation,
        guidance_for_assessment(assessment),
        assessment.coverage_status,
        assessment.confidence,
        available=assessment.availability is AssessmentAvailability.AVAILABLE,
        title="Assessment context",
        source="Source unavailable",
    )


def _section(output: Console, heading: str, lines: Sequence[str]) -> None:
    if not lines:
        return
    if heading in {"Evidence", "Next step"}:
        print_text(output)
    icon = (ICONS if unicode_supported(output) else ASCII_ICONS).get(heading)
    label = f"{icon} {heading}:" if icon else heading + ":"
    subdued = heading in {"Identifiers", "Provenance identifiers"}
    print_text(output, label, style="dim" if subdued else "bold")
    if heading == "Behavior" and len(lines) == 2:
        arrow = " → " if unicode_supported(output) else " -> "
        lines = (arrow.join(lines),)
    for line in lines:
        print_text(output, "  " + line, style="dim" if subdued else None)


def limitation_lines(view: FindingPresentation) -> tuple[str, ...]:
    registration = (
        "Registration declares a callable surface; it does not prove execution or eval coverage."
    )
    guidance_limit = (
        "Guidance describes verification, not runtime test results or business priority."
    )
    aliases = {
        (
            "Static evidence only; target code and tests were not executed. "
            "Unsupported test/eval implementations may not be recognized."
        ): (
            "Static analysis only; Skout does not execute agents or tests. "
            "Unsupported eval patterns may not be recognized."
        ),
        registration: "Registration does not prove runtime execution or eval coverage.",
        guidance_limit: "Guidance is not a runtime result or business priority assessment.",
    }
    detail = view.detail
    records = list(detail.limitations if detail else ())
    if detail and detail.rejection_provenance:
        records.extend(detail.rejection_provenance.limitations)
    if view.guidance:
        records.extend(view.guidance.limitations)
    return tuple(dict.fromkeys(aliases.get(record, record) for record in records)) or (
        "Static analysis may not recognize unsupported eval patterns.",
    )


def render_summary(output: Console, view: FindingPresentation) -> None:
    print_text(output, view.title, style="bold", markup=False, highlight=False)
    separator = " · " if unicode_supported(output) else " | "
    metadata = view.source + (
        separator + "Registered by " + ", ".join(view.owners) if view.owners else ""
    )
    print_text(output, metadata, style="dim")
    print_text(output)
    _section(output, "Behavior", view.behavior)
    _section(output, "Evidence", view.evidence)
    _section(output, "Next step", (view.next_step,))


def render_diagnostics(
    output: Console, view: FindingPresentation, finding: Finding | None = None
) -> None:
    print_text(output)
    icon = (ICONS if unicode_supported(output) else ASCII_ICONS)["Additional details"]
    print_text(output, f"{icon} Additional details", style="bold")
    print_text(output)
    detail = view.detail
    context = detail.rejection_provenance if detail else None
    references: dict[tuple[str, int, int], tuple[SourceEvidence, set[str]]] = {}

    def reference(purpose: str, ref: SourceEvidence) -> None:
        if ref.kind == "callable_definition":
            purpose = "Callable definition"
        elif purpose == "Behavior source":
            if context and ref.kind in {"raise", "model_retry", "conditional_branch"}:
                purpose = "Rejection"
            elif ref.kind == "conditional_workflow_edge":
                purpose = "Route"
        elif purpose == "Eval evidence":
            purpose = {
                "graph_owner_definition": "Graph declaration",
                "graph_owner_invocation": "Graph invocation",
                "pytest_test": "Eval test",
            }.get(ref.kind, purpose)
        if location(ref, span=True) != view.source:
            key = (ref.source_file, ref.start_line or 0, ref.end_line or ref.start_line or 0)
            references.setdefault(key, (ref, set()))[1].add(purpose)

    if context:
        _section(
            output,
            "Provenance",
            (
                f"Callable: {context.source_file}::{context.source_symbol}",
                "Registered as: "
                + ", ".join(dict.fromkeys(REGISTRATIONS[r.kind] for r in context.registrations)),
                *(
                    (f"Selected owner: {context.selected_owner_identity}",)
                    if context.selected_owner_identity
                    else ()
                ),
            ),
        )
        for r in context.registrations:
            reference("Registration", r.registration_evidence)
            reference("Callable definition", r.callable_evidence)
            for ref in r.owner_evidence:
                reference("Agent declaration", ref)
        for ref in context.source_evidence:
            reference("Behavior source", ref)
    if detail:
        for ref in detail.behavior.evidence:
            reference("Behavior source", ref)
    matches = (
        view.guidance.observed_evidence
        if view.guidance
        else finding.matched_eval_evidence
        if finding
        else ()
    )
    if matches:
        print_text(output, "Verification evidence:", style="bold")
        for match in matches:
            candidate_source = match.source_file or "Source unavailable"
            label = match.source_symbol or match.name or match.eval_id
            print_text(output, f"  {label} — {candidate_source}", markup=False, highlight=False)
            if match.source_evidence:
                for evidence in match.source_evidence:
                    reference("Eval evidence", evidence)
            print_text(
                output,
                "    Evidence type: "
                + (
                    match.evidence_type.value.replace("_", " ")
                    if match.evidence_type
                    else "unavailable"
                )
                + f"; confidence: {match.confidence.value}",
                markup=False,
            )
            print_text(
                output, f"    Eval ID: {match.eval_id}", style="dim", markup=False, highlight=False
            )
            print_text(
                output,
                "    Verification: "
                + (
                    COVERAGE[match.coverage_status]
                    if match.coverage_status
                    else "Insufficient verification"
                ),
                markup=False,
            )
            for explanation in dict.fromkeys(match.evidence.details):
                print_text(output, f"    {explanation}", markup=False, highlight=False)
            if (
                match.eval_id != (view.guidance.closest_eval_id if view.guidance else None)
                and match.missing_dimensions
            ):
                print_text(
                    output,
                    "    Missing: " + ", ".join(DIMENSIONS[d] for d in match.missing_dimensions),
                    markup=False,
                )
    if references:
        order = {
            role: i
            for i, role in enumerate(
                (
                    "Agent declaration",
                    "Registration",
                    "Callable definition",
                    "Rejection",
                    "Route",
                    "Graph declaration",
                    "Graph invocation",
                    "Eval test",
                    "Eval evidence",
                    "Behavior source",
                )
            )
        }
        rows = []
        for key, (ref, roles) in references.items():
            # Remove only redundant rejection anchors contained by an existing
            # same-symbol rejection span. Never invent or union a broader span.
            if roles == {"Rejection"} and any(
                other != key
                and other[0] == key[0]
                and other[1] <= key[1]
                and other[2] >= key[2]
                and labels == roles
                and parent.source_symbol == ref.source_symbol
                for other, (parent, labels) in references.items()
            ):
                continue
            labels = sorted(roles, key=lambda role: (order[role], role))
            rows.append((min(order[role] for role in roles), key, ", ".join(labels), ref))
        _section(
            output,
            "Source references",
            tuple(
                f"{labels}: {location(ref, span=True, ascii_only=not unicode_supported(output))}"
                for _, _, labels, ref in sorted(rows)
            ),
        )
    if (
        detail
        and detail.missing_dimensions
        and (
            not (view.guidance and view.guidance.closest_eval_id)
            or view.guidance.interpretation == "analysis_uncertain"
        )
    ):
        _section(
            output,
            "Last available missing verification (not a current assessment)"
            if finding and not finding.assessment_available
            else "Missing verification",
            tuple(DIMENSIONS[d].capitalize() for d in detail.missing_dimensions),
        )
    source = detail.behavior.evidence if detail else finding.source_evidence if finding else ()
    if source:
        _section(
            output,
            "Source evidence",
            tuple(dict.fromkeys(ref.excerpt for ref in source if ref.excerpt)),
        )
    _section(output, "Limitations", limitation_lines(view))
    _section(
        output,
        "Assessment",
        (
            f"Coverage: {view.status.value if view.status else 'unavailable'}",
            f"Confidence: {view.confidence.value}",
        ),
    )
    if finding:
        _section(
            output,
            "Lifecycle",
            (
                f"State: {finding.status.value}",
                "Classification: "
                + (
                    finding.current_disposition.value
                    if finding.current_disposition
                    else "not classified"
                ),
                f"Observed resolution: {'yes' if finding.observed_resolution else 'no'}",
                f"Confirmed impact: {'yes' if finding.confirmed_impact else 'no'}",
            ),
        )
        if finding.resolution_evidence:
            _section(
                output,
                "Resolution evidence",
                (
                    "Eval IDs: " + ", ".join(finding.resolution_evidence.matched_eval_ids),
                    finding.resolution_evidence.explanation,
                ),
            )
        if detail is None:
            _section(output, "Saved explanation", (finding.explanation,))
    if finding:
        _section(
            output,
            "Identifiers",
            (
                f"Finding ID: {finding.finding_id}",
                f"Behavior ID: {finding.behavior_id}",
            ),
        )
    if context:
        _section(
            output,
            "Provenance identifiers",
            (
                f"Callable ID: {context.callable_id}",
                *(f"Registration ID: {r.relationship_id}" for r in context.registrations),
                *(
                    f"Related behavior ID: {b}"
                    for b in context.related_behavior_ids
                    if not finding or b != finding.behavior_id
                ),
            ),
        )


def render_finding(
    output: Console,
    finding: Finding,
    *,
    index: int = 1,
    total: int = 1,
    details: bool = False,
    token: str | None = None,
    display_name: str | None = None,
) -> None:
    view = view_for_finding(finding, display_name=display_name)
    output.rule(characters="─" if unicode_supported(output) else "-", style="dim")
    separator = " · " if unicode_supported(output) else " | "
    state = "Resolved" + separator if finding.status is FindingStatus.RESOLVED else ""
    print_text(
        output,
        f"Finding {index} of {total}{separator}{state}{view.coverage}",
        style="green" if view.status is CoverageStatus.COVERED else "yellow",
        markup=False,
    )
    print_text(output)
    render_summary(output, view)
    print_text(output)
    print_text(
        output,
        f"Finding: {token or display_ids((finding,))[finding.finding_id]}",
        style="dim",
        markup=False,
        highlight=False,
    )
    if details:
        render_diagnostics(output, view, finding)


def render_preview(
    output: Console, finding: Finding, *, token: str | None = None, display_name: str | None = None
) -> None:
    view = view_for_finding(finding, display_name=display_name)
    print_text(output, f"  {view.coverage}: {view.title}", style="bold")
    separator = " · " if unicode_supported(output) else " | "
    metadata = view.source + (
        separator + "Registered by " + ", ".join(view.owners) if view.owners else ""
    )
    print_text(output, "  " + metadata, style="dim")
    print_text(output)
    _section(output, "Behavior", view.behavior)
    _section(output, "Evidence", view.evidence)
    _section(output, "Next step", (view.next_step,))
    print_text(output)
    print_text(
        output, f"Finding: {token or display_ids((finding,))[finding.finding_id]}", style="dim"
    )
