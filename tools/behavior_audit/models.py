"""Source-curated audit contracts, separate from production coverage models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agentguard.models import BehaviorType


class Role(StrEnum):
    AGENT_FACING = "agent_facing"
    ORCHESTRATED_INTERNAL = "orchestrated_internal"
    IMPLEMENTATION_DETAIL = "implementation_detail"
    UNKNOWN = "unknown"


class Discovery(StrEnum):
    CORRECT = "correctly_discovered"
    MISSED = "missed"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    UNEXPECTED = "unexpected"
    CORRECTLY_ABSENT = "correctly_absent"


class AuditModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Selector(AuditModel):
    subject: str
    source_symbol: str | None
    behavior_types: tuple[BehaviorType, ...]
    action_target: str | None = None
    action_outcome: str | None = None
    related_types: tuple[BehaviorType, ...] = ()


class ExpectedBehavior(AuditModel):
    repository: str
    expectation_id: str
    description: str
    source_file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    source_anchor: str
    category: str
    pattern: str
    registration_evidence: str
    role: Role
    operational_relevance: str
    support_status: str
    expected_discovery: str
    review_status: str
    supporting_evidence: tuple[str, ...]
    uncertainty_notes: str
    selector: Selector
    gap_category: str
    root_cause_hypothesis: str
    deterministic_feasibility: str
    false_positive_risk: str


class Repository(AuditModel):
    repository: str
    path: str
    architecture: str
    source_hashes: dict[str, str]


class Corpus(AuditModel):
    corpus_id: str
    provenance: str
    reviewer: str
    repositories: tuple[Repository, ...]
    expectations: tuple[ExpectedBehavior, ...]
