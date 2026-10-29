"""Map existing extracted facts to audit-only obligations. No source parser or matcher."""

import hashlib
import json
from collections import defaultdict
from typing import Literal, TypedDict

from agentguard.models import (
    Behavior,
    BehaviorExtractionResult,
    BehaviorType,
    CoverageDimension,
    RegistrationRelationship,
    RegistrationResolution,
    ScanCompleteness,
    SourceEvidence,
)
from tools.behavior_audit.obligation_models import (
    Eligibility,
    EvidenceRequirement,
    MatcherContract,
    ObligationCandidate,
    ObligationMapping,
)


class _Common(TypedDict):
    candidate_id: str
    source_file: str
    subject: str
    relationship_kind: str
    originating_relationship_ids: tuple[str, ...]
    parent_identities: tuple[str, ...]
    parent_callable_ids: tuple[str, ...]
    target_callable_id: str | None
    target_symbol: str
    source_evidence: tuple[SourceEvidence, ...]
    dispatch_key: str | None
    exception_condition: str | None
    structural_conditions: tuple[str, ...]
    uncertainty: tuple[str, ...]


LIMITS = (
    "Eligibility is not coverage, runtime execution, production relevance, or finding confidence.",
    (
        "No child-guard composition, exception propagation, "
        "recovery success or state output is inferred."
    ),
)
DIMENSIONS = tuple(CoverageDimension)


def _id(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "audit_obligation_" + hashlib.sha256(encoded.encode()).hexdigest()[:24]


def _proofs(refs: list[SourceEvidence]) -> tuple[SourceEvidence, ...]:
    unique = {r.model_dump_json(): r for r in refs}
    return tuple(
        sorted(
            unique.values(),
            key=lambda r: (
                r.source_file,
                r.start_line or 0,
                r.end_line or 0,
                r.kind,
                r.source_symbol or "",
                r.excerpt,
            ),
        )
    )


def _relationship_proofs(r: RegistrationRelationship) -> list[SourceEvidence]:
    return [
        ref
        for ref in (
            r.registration,
            r.definition,
            r.registry_evidence,
            r.handler_evidence,
            *r.parent_provenance,
            *r.context_evidence,
        )
        if ref is not None
    ]


def _requirement(functionality: str, condition: str, outcome: str) -> EvidenceRequirement:
    return EvidenceRequirement(
        dimensions=DIMENSIONS,
        functionality=functionality,
        condition=condition,
        expected_outcome=outcome,
        qualifying_categories=("automated_test", "eval_case"),
    )


def map_obligations(extraction: BehaviorExtractionResult) -> ObligationMapping:
    """Consume typed extraction only. Parent/child bodies and evidence text are never parsed."""
    caps = {c.callable_id: c for c in extraction.callable_capabilities}
    relations = sorted(
        {r.relationship_id: r for r in extraction.registration_relationships}.values(),
        key=lambda r: r.relationship_id,
    )
    candidates: list[ObligationCandidate] = []
    for r in relations:
        cap = caps.get(r.callable_id or "")
        target = cap.qualified_name if cap else r.referenced_symbol
        source = _proofs(_relationship_proofs(r))
        status = Eligibility.CONTEXT_ONLY
        reason = "registration_is_context"
        if r.kind == "one_hop_delegation":
            reason = "delegation_has_no_observable_parent_contract"
        elif r.kind == "task_agent_executor":
            reason = "task_assignment_does_not_verify_output"
        if extraction.completeness is ScanCompleteness.FAILED:
            status, reason = Eligibility.INSUFFICIENT, "upstream_failed"
        elif r.resolution is RegistrationResolution.AMBIGUOUS:
            status, reason = Eligibility.AMBIGUOUS, "ambiguous_relationship"
        elif r.resolution is not RegistrationResolution.RESOLVED:
            status = (
                Eligibility.UNSUPPORTED
                if r.reason == "unsupported_control_or_exception"
                else Eligibility.INSUFFICIENT
            )
            reason = (
                "unsupported_handler_or_control"
                if status is Eligibility.UNSUPPORTED
                else "unresolved_relationship"
            )
        common: _Common = dict(
            candidate_id=_id(["candidate-v1", r.relationship_id]),
            source_file=r.source_file,
            subject=r.owner_identity.split("#", 1)[-1],
            relationship_kind=r.kind,
            originating_relationship_ids=(r.relationship_id,),
            parent_identities=(r.owner_identity,),
            parent_callable_ids=(r.parent_callable_id,) if r.parent_callable_id else (),
            target_callable_id=r.callable_id,
            target_symbol=target,
            source_evidence=source,
            dispatch_key=r.dispatch_key,
            exception_condition=r.exception_condition,
            structural_conditions=r.conditions,
            uncertainty=(*LIMITS, *r.limitations),
        )
        eligible = status is Eligibility.CONTEXT_ONLY and r.kind in {
            "literal_dispatch",
            "exception_fallback",
        }
        if eligible and not (
            cap
            and r.parent_callable_id in caps
            and r.parent_provenance
            and r.definition
            and (
                r.registry_evidence
                if r.kind == "literal_dispatch"
                else r.handler_evidence and r.conditions
            )
        ):
            status, reason, eligible = Eligibility.INSUFFICIENT, "missing_typed_provenance", False
        if eligible:
            type_: Literal["literal_route_selection", "conditional_fallback_invocation"]
            if r.kind == "literal_dispatch" and r.dispatch_key is not None:
                type_ = "literal_route_selection"
                condition = "; ".join(
                    (
                        *r.conditions,
                        "at the recorded lookup site, registry key "
                        f"{json.dumps(r.dispatch_key, ensure_ascii=False)} is selected",
                    )
                )
                functionality = f"{common['subject']} selects a literal dispatch target"
                outcome = f"selects {target}; handler result is unspecified"
            elif r.kind == "exception_fallback" and r.exception_condition:
                type_ = "conditional_fallback_invocation"
                condition = "; ".join(r.conditions)
                functionality = f"{common['subject']} invokes its handler-local fallback"
                outcome = f"invokes {target}; result and recovery are unspecified"
            else:
                status, reason, eligible = (
                    Eligibility.INSUFFICIENT,
                    "missing_typed_condition",
                    False,
                )
        if eligible:
            candidates.append(
                ObligationCandidate(
                    **common,
                    obligation_id=_id(["prototype-obligation-v1", r.relationship_id]),
                    obligation_type=type_,
                    classification="new_obligation",
                    eligibility=Eligibility.ELIGIBLE,
                    reason_code="explicit_conditional_relationship",
                    functionality=functionality,
                    condition=condition,
                    expected_outcome=outcome,
                    evidence_requirement=_requirement(functionality, condition, outcome),
                    matcher_compatibility=MatcherContract.EXTENSION,
                    raw_eligible_mappings=1,
                )
            )
        else:
            candidates.append(
                ObligationCandidate(
                    **common,
                    eligibility=status,
                    reason_code=reason,
                    classification="structural_context"
                    if status is Eligibility.CONTEXT_ONLY
                    else "unsupported_or_uncertain",
                )
            )

    # Existing source-backed conditions/outcomes can be enriched, never re-extracted.
    groups: dict[tuple[str, ...], list[Behavior]] = defaultdict(list)
    for b in {b.behavior_id: b for b in extraction.behaviors}.values():
        if not b.condition or not b.action:
            continue
        rejection = (
            b.action.kind == "raise"
            and b.action.outcome
            and b.behavior_type
            in {
                BehaviorType.TOOL_FAILURE,
                BehaviorType.CONDITIONAL_BRANCH,
            }
        )
        routing = (
            b.action.kind == "transition"
            and b.action.target
            and b.behavior_type
            in {
                BehaviorType.CONDITIONAL_BRANCH,
                BehaviorType.ESCALATION,
            }
        )
        if rejection or routing:
            groups[
                (
                    b.source_file,
                    b.subject,
                    b.condition.normalized_expression,
                    b.action.kind,
                    b.action.target or "",
                    b.action.outcome or "",
                )
            ].append(b)
    for _key, behaviors in sorted(groups.items()):
        b = min(
            behaviors,
            key=lambda b: (b.behavior_type is not BehaviorType.TOOL_FAILURE, b.behavior_id),
        )
        assert b.condition and b.action
        routing = b.action.kind == "transition"
        origins = [
            r
            for r in relations
            if r.resolution is RegistrationResolution.RESOLVED
            and (
                r.kind in {"constructor_tool", "decorator_tool", "output_validator_callback"}
                and r.callable_id in caps
                and caps[r.callable_id].qualified_name == b.subject
                and r.source_file == b.source_file
                or routing
                and r.kind == "graph_node_callback"
                and r.owner_identity == f"{b.source_file}#{b.subject}"
            )
        ]
        if not origins:
            continue  # Legacy names alone cannot establish a new assessment root.
        available = extraction.completeness is not ScanCompleteness.FAILED and not any(
            x.behavior_id in extraction.unavailable_behavior_ids for x in behaviors
        )
        kind = min(r.kind for r in origins)
        condition = b.condition.normalized_expression
        outcome = (b.action.target if routing else b.action.outcome) or ""
        assert outcome
        functionality = (
            f"{b.subject}: {'conditional route selection' if routing else 'explicit rejection'}"
        )
        raw_count = len(behaviors) * len(origins)
        candidates.append(
            ObligationCandidate(
                candidate_id=_id(["existing-candidate-v1", b.behavior_id]),
                obligation_id=b.behavior_id if available else None,
                source_file=b.source_file,
                subject=b.subject,
                relationship_kind=kind,
                originating_relationship_ids=tuple(sorted(r.relationship_id for r in origins)),
                parent_identities=tuple(sorted({r.owner_identity for r in origins})),
                parent_callable_ids=tuple(
                    sorted({r.callable_id for r in origins if r.callable_id})
                ),
                target_callable_id=None if routing else origins[0].callable_id,
                target_symbol=b.action.target if routing else b.subject,
                obligation_type="conditional_route" if routing else "explicit_rejection",
                classification="existing_behavior_enrichment"
                if available
                else "unsupported_or_uncertain",
                eligibility=Eligibility.ELIGIBLE if available else Eligibility.INSUFFICIENT,
                reason_code="existing_explicit_source_behavior"
                if available
                else "behavior_unavailable",
                functionality=functionality,
                condition=condition,
                expected_outcome=outcome,
                existing_behavior_ids=tuple(sorted(x.behavior_id for x in behaviors)),
                source_evidence=_proofs(
                    [ref for x in behaviors for ref in x.evidence]
                    + [ref for r in origins for ref in _relationship_proofs(r)]
                ),
                evidence_requirement=_requirement(functionality, condition, outcome),
                matcher_compatibility=(
                    MatcherContract.EXTENSION if routing else MatcherContract.EXISTING
                )
                if available
                else MatcherContract.NONE,
                uncertainty=(
                    *LIMITS,
                    "Existing matcher sufficiency is bounded to tested evidence shapes.",
                )
                if not routing
                else (*LIMITS, "M8 does not require same graph identity for routing matches."),
                raw_eligible_mappings=raw_count if available else 0,
            )
        )
    eligible_count = sum(c.eligibility is Eligibility.ELIGIBLE for c in candidates)
    raw = sum(c.raw_eligible_mappings for c in candidates)
    return ObligationMapping(
        candidates=tuple(sorted(candidates, key=lambda c: c.candidate_id)),
        raw_eligible_mappings=raw,
        duplicates_removed=raw - eligible_count,
    )
