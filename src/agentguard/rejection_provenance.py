"""Optional explanation context over existing facts, strictly after M8 matching."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal, cast

from rich.console import Console

from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorExtractionResult,
    BehaviorType,
    CallableCapability,
    CoverageExplanation,
    MatchingResult,
    RegistrationResolution,
    RejectionProvenance,
    RejectionRegistration,
    ScanCompleteness,
    ScopeInventory,
    SourceEvidence,
)

KINDS = {"constructor_tool", "decorator_tool", "output_validator_callback"}
LIMIT = "Registration declares a callable surface; it does not prove execution or eval coverage."


def _references(refs: Sequence[SourceEvidence]) -> tuple[SourceEvidence, ...]:
    unique = {ref.model_dump_json(): ref for ref in refs}
    return tuple(
        sorted(
            unique.values(),
            key=lambda ref: (
                ref.source_file,
                ref.start_line or 0,
                ref.end_line or 0,
                ref.source_symbol or "",
                ref.kind,
                ref.excerpt,
            ),
        )
    )


def _located(ref: SourceEvidence, file: str) -> bool:
    return bool(
        ref.source_file == file
        and ref.excerpt
        and ref.start_line
        and ref.end_line
        and ref.end_line >= ref.start_line
    )


def rejection_provenance(
    extraction: BehaviorExtractionResult,
    inventory: ScopeInventory,
) -> tuple[RejectionProvenance, ...]:
    """Join exact local callable identities and resolved direct Agent registrations only.

    Consumes typed facts only; never reparses rejection bodies, follows delegation,
    changes the source inventory, or uses eval/name similarity to establish ownership.
    """
    if extraction.completeness is ScanCompleteness.FAILED:
        return ()
    caps: dict[tuple[str, str], list[CallableCapability]] = defaultdict(list)
    for cap in extraction.callable_capabilities:
        caps[cap.source_file, cap.qualified_name].append(cap)
    roots = {
        r.selector: r
        for r in inventory.roots
        if r.root_kind in {"pydantic_ai_agent", "crewai_agent"}
    }
    groups: dict[tuple[str, str, str, str, str], list[Behavior]] = defaultdict(list)
    for behavior in extraction.behaviors:
        if (
            behavior.behavior_id in extraction.unavailable_behavior_ids
            or behavior.behavior_type
            not in {BehaviorType.TOOL_FAILURE, BehaviorType.CONDITIONAL_BRANCH}
            or not behavior.condition
            or not behavior.action
            or behavior.action.kind != "raise"
            or not behavior.action.outcome
            or not behavior.source_symbol
            or not behavior.evidence
        ):
            continue
        candidates = caps.get((behavior.source_file, behavior.source_symbol), [])
        if len(candidates) != 1:
            continue
        cap = candidates[0]
        if not _located(cap.definition, behavior.source_file) or not all(
            _located(ref, cap.source_file)
            and cast(int, cap.definition.start_line) <= cast(int, ref.start_line)
            and cast(int, ref.end_line) <= cast(int, cap.definition.end_line)
            for ref in behavior.evidence
        ):
            continue
        key = (
            cap.callable_id,
            behavior.condition.normalized_expression,
            behavior.action.kind,
            behavior.action.target or "",
            behavior.action.outcome,
        )
        groups[key].append(behavior)
    result = []
    for key, facts in sorted(groups.items()):
        primary = min(
            facts, key=lambda b: (b.behavior_type is not BehaviorType.TOOL_FAILURE, b.behavior_id)
        )
        cap = caps[primary.source_file, cast(str, primary.source_symbol)][0]
        registrations: dict[str, RejectionRegistration] = {}
        uncertain = False
        for relation in extraction.registration_relationships:
            if relation.kind not in KINDS or relation.callable_id != cap.callable_id:
                continue
            root = roots.get(relation.owner_identity)
            if (
                relation.resolution is not RegistrationResolution.RESOLVED
                or not root
                or root.source_file != cap.source_file
                or relation.source_file != cap.source_file
                or relation.definition != cap.definition
                or not _located(relation.registration, cap.source_file)
                or not root.evidence
                or not all(_located(ref, cap.source_file) for ref in root.evidence)
            ):
                uncertain = True
                continue
            registrations[relation.relationship_id] = RejectionRegistration(
                relationship_id=relation.relationship_id,
                kind=cast(
                    Literal["constructor_tool", "decorator_tool", "output_validator_callback"],
                    relation.kind,
                ),
                owner_identity=root.selector,
                owner_evidence=root.evidence,
                registration_evidence=relation.registration,
                callable_evidence=cap.definition,
            )
        if not registrations:
            continue
        assert primary.condition and primary.action
        result.append(
            RejectionProvenance(
                primary_behavior_id=primary.behavior_id,
                related_behavior_ids=tuple(sorted(b.behavior_id for b in facts)),
                callable_id=key[0],
                source_file=cap.source_file,
                source_symbol=cap.qualified_name,
                condition=primary.condition,
                outcome=primary.action,
                registrations=tuple(registrations[k] for k in sorted(registrations)),
                owner_identities=tuple(sorted({r.owner_identity for r in registrations.values()})),
                source_evidence=_references(
                    [cap.definition, *(ref for b in facts for ref in b.evidence)]
                ),
                limitations=(LIMIT,)
                + (("Additional unverified registrations were omitted.",) if uncertain else ()),
            )
        )
    return tuple(sorted(result, key=lambda r: r.primary_behavior_id))


def enrich_rejection_explanations(
    extraction: BehaviorExtractionResult,
    matching: MatchingResult,
    inventory: ScopeInventory,
    *,
    selected_owner: str | None = None,
) -> MatchingResult:
    """Return a copy with optional provenance only; M8 results are never recomputed."""
    contexts = {
        bid: context
        for context in rejection_provenance(extraction, inventory)
        for bid in context.related_behavior_ids
    }
    assessments = []
    for assessment in matching.assessments:
        detail = assessment.structured_explanation
        if detail is not None:
            context = contexts.get(assessment.behavior_id)
            if assessment.availability is not AssessmentAvailability.AVAILABLE:
                context = None
            if context and selected_owner in context.owner_identities:
                context = context.model_copy(update={"selected_owner_identity": selected_owner})
            detail = detail.model_copy(update={"rejection_provenance": context})
            assessment = assessment.model_copy(update={"structured_explanation": detail})
        assessments.append(assessment)
    return matching.model_copy(update={"assessments": tuple(assessments)})


def render_rejection_context(output: Console, detail: CoverageExplanation | None) -> None:
    """Render existing condition/outcome and declaration references, never coverage claims."""
    context = detail.rejection_provenance if detail else None
    if context is None:
        return
    output.print(
        f"  Registered callable: {context.source_file}::{context.source_symbol}", markup=False
    )
    output.print("  Registered by agent: " + ", ".join(context.owner_identities), markup=False)
    if context.selected_owner_identity:
        output.print(f"  Selected owner: {context.selected_owner_identity}", markup=False)
    output.print(f"  Rejection condition: {context.condition.expression}", markup=False)
    output.print(f"  Explicit rejection outcome: {context.outcome.outcome}", markup=False)
    output.print(f"  Existing rejection concern: {context.primary_behavior_id}", markup=False)
    for registration in context.registrations:
        ref = registration.registration_evidence
        output.print(
            f"  Registration: {registration.kind} {registration.relationship_id} "
            f"[{ref.source_file}:{ref.start_line}]",
            markup=False,
        )
        for owner in registration.owner_evidence:
            output.print(
                f"    Agent declaration: {owner.source_file}:{owner.start_line}", markup=False
            )
    for ref in context.source_evidence:
        output.print(
            f"  Rejection source: {ref.source_file}:{ref.start_line} ({ref.kind})", markup=False
        )
    for limitation in context.limitations:
        output.print(f"  Provenance limitation: {limitation}", markup=False)
