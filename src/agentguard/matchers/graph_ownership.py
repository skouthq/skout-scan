"""Typed sufficiency gate for existing conditional LangGraph routes only."""

from dataclasses import dataclass
from enum import StrEnum

from agentguard.extractors.graph_evidence import (
    OWNER_AMBIGUOUS,
    OWNER_ASSERTION,
    OWNER_INVOCATION,
    OWNER_UNVERIFIED,
)
from agentguard.models import Behavior, BehaviorSourceType, CoverageReason, EvalScenario


class OwnerStatus(StrEnum):
    VERIFIED = "verified_owner"
    UNVERIFIED = "unverified_owner"
    CONFLICTING = "conflicting_owner"
    AMBIGUOUS = "ambiguous_owner"


@dataclass(frozen=True)
class OwnerCheck:
    status: OwnerStatus
    expected: str
    observed: tuple[str, ...]
    modes: tuple[str, ...]

    @property
    def reason(self) -> CoverageReason | None:
        return {
            OwnerStatus.VERIFIED: None,
            OwnerStatus.UNVERIFIED: CoverageReason.GRAPH_OWNER_NOT_VERIFIED,
            OwnerStatus.CONFLICTING: CoverageReason.GRAPH_OWNER_MISMATCH,
            OwnerStatus.AMBIGUOUS: CoverageReason.GRAPH_OWNER_AMBIGUOUS,
        }[self.status]

    @property
    def detail(self) -> str:
        return (
            f"Graph owner {self.expected}: {self.status.value}; "
            f"supported subjects: {', '.join(self.observed) or 'none'}; "
            f"evidence: {', '.join(self.modes) or 'no verified binding'}. "
            "A metadata assertion declares an eval subject; it does not establish execution."
        )


def is_conditional_graph_route(behavior: Behavior) -> bool:
    return behavior.source_type is BehaviorSourceType.LANGGRAPH_WORKFLOW and any(
        e.kind == "conditional_workflow_edge" for e in behavior.evidence
    )


def check_graph_owner(behavior: Behavior, scenario: EvalScenario) -> OwnerCheck:
    expected = f"{behavior.source_file}#{behavior.subject}"
    claims = [
        r
        for r in scenario.referenced_symbols
        if r.evidence.kind in {OWNER_INVOCATION, OWNER_ASSERTION, OWNER_AMBIGUOUS, OWNER_UNVERIFIED}
    ]
    observed = tuple(
        sorted(
            {
                r.qualified_name
                for r in claims
                if r.evidence.kind in {OWNER_INVOCATION, OWNER_ASSERTION}
            }
        )
    )
    modes = tuple(sorted({r.evidence.kind for r in claims}))
    hints = scenario.metadata.get("tools")
    if any(r.evidence.kind == OWNER_AMBIGUOUS for r in claims):
        status = OwnerStatus.AMBIGUOUS
    elif len(observed) > 1 or observed and observed != (expected,):
        status = OwnerStatus.CONFLICTING
    elif any(r.evidence.kind == OWNER_UNVERIFIED for r in claims):
        status = OwnerStatus.UNVERIFIED
    elif observed == (expected,):
        status = OwnerStatus.VERIFIED
    elif isinstance(hints, list) and len(hints) > 1:
        status = OwnerStatus.AMBIGUOUS
    else:
        status = OwnerStatus.UNVERIFIED
    return OwnerCheck(status, expected, observed, modes)
