"""Development-only eligibility contracts; none are production coverage states."""

from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from agentguard.models import CoverageDimension, SourceEvidence
from tools.behavior_audit.models import AuditModel


class Eligibility(StrEnum):
    ELIGIBLE = "eligible"
    CONTEXT_ONLY = "context_only"
    INSUFFICIENT = "insufficient_evidence"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class MatcherContract(StrEnum):
    EXISTING = "existing_matcher_sufficient"
    EXTENSION = "matcher_extension_required"
    NONE = "not_assessable"


class EvidenceRequirement(AuditModel):
    dimensions: tuple[CoverageDimension, ...] = ()
    functionality: str | None = None
    condition: str | None = None
    expected_outcome: str | None = None
    qualifying_categories: tuple[str, ...] = ()


class ObligationCandidate(AuditModel):
    candidate_id: str
    obligation_id: str | None = None
    source_file: str
    subject: str
    relationship_kind: str
    originating_relationship_ids: tuple[str, ...]
    parent_identities: tuple[str, ...]
    parent_callable_ids: tuple[str, ...] = ()
    target_callable_id: str | None = None
    target_symbol: str | None = None
    obligation_type: Literal[
        "structural_context",
        "explicit_rejection",
        "conditional_route",
        "literal_route_selection",
        "conditional_fallback_invocation",
    ] = "structural_context"
    classification: Literal[
        "new_obligation",
        "existing_behavior_enrichment",
        "structural_context",
        "unsupported_or_uncertain",
    ]
    eligibility: Eligibility
    reason_code: str
    functionality: str | None = None
    condition: str | None = None
    expected_outcome: str | None = None
    dispatch_key: str | None = None
    exception_condition: str | None = None
    structural_conditions: tuple[str, ...] = ()
    existing_behavior_ids: tuple[str, ...] = ()
    source_evidence: tuple[SourceEvidence, ...]
    evidence_requirement: EvidenceRequirement = EvidenceRequirement()
    matcher_compatibility: MatcherContract = MatcherContract.NONE
    uncertainty: tuple[str, ...]
    raw_eligible_mappings: int = 0

    @model_validator(mode="after")
    def explicit_eligible_claim(self) -> "ObligationCandidate":
        if self.eligibility is Eligibility.ELIGIBLE:
            if not all(
                (
                    self.obligation_id,
                    self.functionality,
                    self.condition,
                    self.expected_outcome,
                    self.source_evidence,
                    self.originating_relationship_ids,
                    self.parent_identities,
                )
            ):
                raise ValueError("Eligible obligations require an explicit source-backed claim")
            if self.matcher_compatibility is MatcherContract.NONE:
                raise ValueError("Eligible claim must identify its evidence contract")
            if self.classification not in {"new_obligation", "existing_behavior_enrichment"}:
                raise ValueError("An eligible claim is distinct from structural context")
        elif self.obligation_id is not None:
            raise ValueError("Abstentions/context cannot create obligation identities")
        return self


class ObligationMapping(AuditModel):
    candidates: tuple[ObligationCandidate, ...]
    raw_eligible_mappings: int
    duplicates_removed: int


class ExpectedObligation(AuditModel):
    expectation_id: str
    repository: str
    source_file: str
    subject: str
    relationship_kind: str
    obligation_type: str
    dispatch_key: str | None
    exception_condition: str | None
    target_symbol: str | None
    eligibility: Eligibility
    matcher_compatibility: MatcherContract
    existing_behavior_subject: str | None
    minimum_origins: int
    reason: str
    required_dimensions: tuple[CoverageDimension, ...]
    anchor: str
    source_line: int
    review_status: Literal["confirmed", "uncertain", "unreviewed"]
    human_review_status: Literal["pending", "reviewed"] = "pending"
    uncertainty: str
    actionable_proxy: bool
    duplicate_notes: str


class ObligationRepository(AuditModel):
    repository: str
    path: str
    source_hashes: dict[str, str]


class AbsenceExpectation(AuditModel):
    repository: str
    source_file: str
    anchor: str
    reason: str


class EvidenceCase(AuditModel):
    case_id: str
    repository: str
    subject: str
    obligation_type: str
    target_symbol: str
    evidence_file: str
    scenario: str
    should_cover: bool
    review_status: Literal["confirmed", "uncertain", "unreviewed"]
    human_review_status: Literal["pending", "reviewed"] = "pending"
    reason: str


class ObligationCorpus(AuditModel):
    corpus_id: str
    provenance: str
    repositories: tuple[ObligationRepository, ...]
    expectations: tuple[ExpectedObligation, ...]
    absence_expectations: tuple[AbsenceExpectation, ...]
    evidence_root: str
    evidence_hashes: dict[str, str]
    evidence_cases: tuple[EvidenceCase, ...]
