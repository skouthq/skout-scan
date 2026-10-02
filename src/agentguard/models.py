"""Typed domain models shared across AgentGuard."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ArtifactType(StrEnum):
    """Artifact categories supported by V0 discovery."""

    PYTHON = "python"
    PROMPT_TEXT = "prompt_text"
    PROMPT_MARKDOWN = "prompt_markdown"
    EVAL_JSONL = "eval_jsonl"


class ScanCompleteness(StrEnum):
    """Whether repository discovery examined everything required."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class ConfidenceLevel(StrEnum):
    """Qualitative confidence in a deterministic or inferred result."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvalSourceType(StrEnum):
    """Supported sources of eval scenarios."""

    PYTEST = "pytest"
    JSONL = "jsonl"


class EvalAssertionKind(StrEnum):
    """Static assertion patterns recognized in an eval."""

    ASSERT = "assert"
    EXPECTED_EXCEPTION = "expected_exception"


class BehaviorType(StrEnum):
    """Deterministic behavior categories supported by V0 extraction."""

    TOOL_INVOCATION = "tool_invocation"
    TOOL_FAILURE = "tool_failure"
    CONDITIONAL_BRANCH = "conditional_branch"
    WORKFLOW_TRANSITION = "workflow_transition"
    FALLBACK = "fallback"
    ESCALATION = "escalation"


class BehaviorSourceType(StrEnum):
    """Static source constructs that produce behaviors."""

    PYTHON_TOOL = "python_tool"
    LANGGRAPH_WORKFLOW = "langgraph_workflow"
    CREWAI_TOOL = "crewai_tool"
    CREWAI_WORKFLOW = "crewai_workflow"


class CoverageStatus(StrEnum):
    """Supported V0 behavior coverage classifications."""

    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    POTENTIALLY_UNCOVERED = "potentially_uncovered"


class AssessmentAvailability(StrEnum):
    """Whether available evidence supports a coverage classification."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class FindingStatus(StrEnum):
    """Lifecycle state of a persisted finding."""

    OPEN = "open"
    RESOLVED = "resolved"
    NO_LONGER_OBSERVED = "no_longer_observed"


class FindingDisposition(StrEnum):
    """Explicit user feedback supported by V0."""

    ADD_EVAL = "add_eval"
    VALID_LATER = "valid_later"
    ALREADY_COVERED = "already_covered"
    NOT_RELEVANT = "not_relevant"
    SUPPRESSED = "suppressed"


class FeedbackReason(StrEnum):
    """Structured reasons for already-covered or not-relevant feedback."""

    ALIAS_OR_WRAPPER = "alias_or_wrapper"
    FIXTURE_INDIRECTION = "fixture_indirection"
    PARAMETRIZED_TEST = "parametrized_test"
    UNSUPPORTED_FRAMEWORK_PATTERN = "unsupported_framework_pattern"
    MATCHER_MISSED_EXISTING_EVAL = "matcher_missed_existing_eval"
    BEHAVIOR_NOT_WORTH_TESTING = "behavior_not_worth_testing"
    DUPLICATE_CONCERN = "duplicate_concern"
    IMPLEMENTATION_DETAIL = "implementation_detail"
    INTENTIONALLY_UNCOVERED = "intentionally_uncovered"
    OTHER = "other"


class MetricName(StrEnum):
    """Feedback and outcome metrics used to validate V0."""

    VALID_GAP_RATE = "valid_gap_rate"
    INTENT_TO_ACT_RATE = "intent_to_act_rate"
    OBSERVED_RESOLUTION_RATE = "observed_resolution_rate"
    CONFIRMED_IMPACT_RATE = "confirmed_impact_rate"
    FALSE_POSITIVE_RATE = "false_positive_rate"
    RESOLVED_BY_TEST_RATE = "resolved_by_test_rate"


class ValidationCriterionStatus(StrEnum):
    """Progress state for one V0 validation criterion."""

    PASS = "pass"
    NOT_YET = "not_yet"
    NOT_ENOUGH_DATA = "not_enough_data"


class FindingHistoryEventType(StrEnum):
    """Append-only finding lifecycle event categories."""

    CREATED = "created"
    SEEN = "seen"
    FEEDBACK = "feedback"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    NO_LONGER_OBSERVED = "no_longer_observed"
    SCAN_INCOMPLETE = "scan_incomplete"
    IMPACT_CONFIRMED = "impact_confirmed"


class SkipReason(StrEnum):
    """Why a path was not included as a discovered artifact."""

    EXCLUDED = "excluded"
    UNREADABLE = "unreadable"
    UNSUPPORTED = "unsupported"


class DomainModel(BaseModel):
    """Immutable base for machine-readable AgentGuard domain models."""

    model_config = ConfigDict(frozen=True)


class RepositoryMetadata(DomainModel):
    """Repository and effective configuration used for discovery."""

    requested_path: str
    root: str | None = None
    config_path: str | None = None
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()


class DiscoveredArtifact(DomainModel):
    """A readable, supported artifact found in the repository."""

    path: str
    artifact_type: ArtifactType
    size_bytes: int


class SkippedPath(DomainModel):
    """A relevant path intentionally or necessarily skipped."""

    path: str
    reason: SkipReason
    is_directory: bool = False


class ScanWarning(DomainModel):
    """A non-fatal problem that limited repository discovery."""

    code: str
    message: str
    path: str | None = None


class ScanError(DomainModel):
    """A fatal problem that prevented repository discovery."""

    code: str
    message: str
    path: str | None = None


class ScanResult(DomainModel):
    """Deterministic manifest produced by repository discovery."""

    repository: RepositoryMetadata
    artifacts: tuple[DiscoveredArtifact, ...] = ()
    skipped: tuple[SkippedPath, ...] = ()
    warnings: tuple[ScanWarning, ...] = ()
    errors: tuple[ScanError, ...] = ()
    completeness: ScanCompleteness


class SourceEvidence(DomainModel):
    """Inspectible source evidence for an extracted static fact."""

    kind: str
    source_file: str
    source_symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    excerpt: str


class LiteralArgument(DomainModel):
    """A statically recoverable literal call argument."""

    position: int | None = None
    keyword: str | None = None
    value: JsonValue


class ReferencedSymbol(DomainModel):
    """A function, tool, or other callable referenced by an eval."""

    name: str
    qualified_name: str
    normalized_tool_name: str | None = None
    literal_arguments: tuple[LiteralArgument, ...] = ()
    evidence: SourceEvidence


class EvalAssertion(DomainModel):
    """An assertion or expected-exception construct found statically."""

    kind: EvalAssertionKind
    expression: str
    expected_exception: str | None = None
    evidence: SourceEvidence


class ExpectedOutcome(DomainModel):
    """An expected result explicitly stated by an eval artifact."""

    description: str
    value: JsonValue | None = None
    is_explicit: bool = True


class EvalScenario(DomainModel):
    """A normalized pytest test or JSONL eval scenario."""

    eval_id: str
    source_type: EvalSourceType
    source_file: str
    source_symbol: str | None = None
    name: str
    description: str | None = None
    inputs: JsonValue | None = None
    expected_outcome: ExpectedOutcome | None = None
    assertions: tuple[EvalAssertion, ...] = ()
    referenced_symbols: tuple[ReferencedSymbol, ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    unknown_fields: dict[str, JsonValue] = Field(default_factory=dict)
    content_fingerprint: str
    confidence: ConfidenceLevel


class EvalParseWarning(DomainModel):
    """A non-fatal limitation encountered while parsing eval artifacts."""

    code: str
    message: str
    source_file: str
    line: int | None = None


class EvalParseError(DomainModel):
    """An artifact-level failure encountered while parsing evals."""

    code: str
    message: str
    source_file: str


class EvalParseResult(DomainModel):
    """Typed result of parsing discovered artifacts for eval scenarios."""

    scenarios: tuple[EvalScenario, ...] = ()
    warnings: tuple[EvalParseWarning, ...] = ()
    errors: tuple[EvalParseError, ...] = ()
    completeness: ScanCompleteness


class BehaviorCondition(DomainModel):
    """A statically recoverable condition governing a behavior."""

    expression: str
    normalized_expression: str


class BehaviorAction(DomainModel):
    """The explicit action or outcome associated with a behavior."""

    kind: str
    target: str | None = None
    outcome: str | None = None


class ToolArgument(DomainModel):
    """A statically declared tool argument."""

    name: str
    required: bool
    annotation: str | None = None
    default: str | None = None


class Behavior(DomainModel):
    """A normalized deterministic behavior extracted from repository source."""

    behavior_id: str
    description: str
    behavior_type: BehaviorType
    source_type: BehaviorSourceType
    source_file: str
    source_symbol: str | None = None
    subject: str
    condition: BehaviorCondition | None = None
    action: BehaviorAction | None = None
    arguments: tuple[ToolArgument, ...] = ()
    evidence: tuple[SourceEvidence, ...] = ()
    confidence: ConfidenceLevel
    extractor: str
    content_fingerprint: str


class BehaviorExtractionWarning(DomainModel):
    """A non-fatal limitation encountered while extracting behaviors."""

    code: str
    message: str
    source_file: str
    line: int | None = None


class BehaviorExtractionError(DomainModel):
    """An artifact-level behavior extraction failure."""

    code: str
    message: str
    source_file: str


class FrameworkConstruct(DomainModel):
    """A statically identified framework construct retained as structured evidence."""

    framework: str
    kind: str
    name: str
    source_file: str
    source_symbol: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    evidence: tuple[SourceEvidence, ...] = ()


class FrameworkSummary(DomainModel):
    """Deterministic framework detection and construct counts for scan reporting."""

    framework: str
    construct_counts: dict[str, int] = Field(default_factory=dict)


class BehaviorExtractionResult(DomainModel):
    """Typed result of deterministic behavior extraction."""

    behaviors: tuple[Behavior, ...] = ()
    warnings: tuple[BehaviorExtractionWarning, ...] = ()
    errors: tuple[BehaviorExtractionError, ...] = ()
    framework_constructs: tuple[FrameworkConstruct, ...] = ()
    framework_summaries: tuple[FrameworkSummary, ...] = ()
    completeness: ScanCompleteness


class MatchEvidence(DomainModel):
    """Decomposed deterministic evidence for one behavior/eval candidate pair."""

    candidate_reasons: tuple[str, ...] = ()
    same_subject: bool = False
    condition_matches: bool = False
    branch_matches: bool = False
    failure_matches: bool = False
    action_matches: bool = False
    explicit_assertion: bool = False
    expected_outcome_present: bool = False
    details: tuple[str, ...] = ()


class BehaviorEvalMatch(DomainModel):
    """The deterministic relationship between a behavior and candidate eval."""

    eval_id: str
    coverage_status: CoverageStatus | None = None
    confidence: ConfidenceLevel
    evidence: MatchEvidence


class BehaviorCoverageAssessment(DomainModel):
    """Coverage assessment for one extracted behavior."""

    behavior_id: str
    availability: AssessmentAvailability
    coverage_status: CoverageStatus | None = None
    confidence: ConfidenceLevel
    matched_eval_ids: tuple[str, ...] = ()
    matches: tuple[BehaviorEvalMatch, ...] = ()
    explanation: str
    candidate_count: int
    matcher: str


class MatchingWarning(DomainModel):
    """A non-fatal limitation encountered during matching."""

    code: str
    message: str
    behavior_id: str | None = None


class MatchingError(DomainModel):
    """A fatal or behavior-level matching failure."""

    code: str
    message: str
    behavior_id: str | None = None


class MatchingResult(DomainModel):
    """Deterministic behavior-to-eval matching output."""

    assessments: tuple[BehaviorCoverageAssessment, ...] = ()
    warnings: tuple[MatchingWarning, ...] = ()
    errors: tuple[MatchingError, ...] = ()
    completeness: ScanCompleteness
    behavior_count: int = 0
    eval_count: int = 0
    candidate_pair_count: int = 0
    matcher: str


class ResolutionEvidence(DomainModel):
    """Evidence that a later eval appears to resolve a finding."""

    resolved_at: datetime
    matched_eval_ids: tuple[str, ...]
    matcher: str
    explanation: str


class Finding(DomainModel):
    """A persisted actionable behavior coverage concern."""

    finding_id: str
    behavior_id: str
    behavior_type: BehaviorType
    behavior_subject: str
    coverage_status: CoverageStatus
    confidence_at_creation: ConfidenceLevel
    current_confidence: ConfidenceLevel
    title: str
    explanation: str
    source_file: str
    source_symbol: str | None = None
    source_evidence: tuple[SourceEvidence, ...] = ()
    matched_eval_ids: tuple[str, ...] = ()
    matched_eval_evidence: tuple[BehaviorEvalMatch, ...] = ()
    suggested_scenario: str | None = None
    first_seen: datetime
    last_seen: datetime
    status: FindingStatus
    current_disposition: FindingDisposition | None = None
    current_feedback_reason: FeedbackReason | None = None
    assessment_available: bool = True
    observed_resolution: bool = False
    resolution_evidence: ResolutionEvidence | None = None
    confirmed_impact: bool = False
    matcher: str


class FeedbackEvent(DomainModel):
    """An append-only user disposition event."""

    event_id: str
    finding_id: str
    disposition: FindingDisposition
    occurred_at: datetime
    reason: str | None = None
    feedback_reason: FeedbackReason | None = None
    confidence_at_feedback: ConfidenceLevel


class ImpactConfirmationEvent(DomainModel):
    """Explicit confirmation that AgentGuard influenced an eval change."""

    event_id: str
    finding_id: str
    occurred_at: datetime
    note: str | None = None


class FindingHistoryEvent(DomainModel):
    """An append-only finding lifecycle record."""

    event_id: str
    finding_id: str
    event_type: FindingHistoryEventType
    occurred_at: datetime
    details: dict[str, JsonValue] = Field(default_factory=dict)


class FindingSelectionResult(DomainModel):
    """Actionable findings selected from matching assessments."""

    findings: tuple[Finding, ...] = ()
    eligible_assessment_count: int = 0
    duplicate_count: int = 0


class FindingUpdateResult(DomainModel):
    """Summary of lifecycle changes applied for one scan."""

    findings: tuple[Finding, ...] = ()
    eligible_assessment_count: int = 0
    new_count: int = 0
    existing_count: int = 0
    resolved_count: int = 0
    reopened_count: int = 0
    no_longer_observed_count: int = 0


class FindingScanRecord(DomainModel):
    """Persisted scan metadata needed for lifecycle and later metrics."""

    scan_id: str
    occurred_at: datetime
    completeness: ScanCompleteness
    behavior_count: int
    assessment_count: int
    eligible_assessment_count: int
    new_count: int
    existing_count: int
    resolved_count: int
    reopened_count: int
    no_longer_observed_count: int


class MetricCohort(DomainModel):
    """Inspectable denominator used for one metric."""

    description: str
    eligible_finding_ids: tuple[str, ...] = ()
    excluded_finding_count: int = 0


class MetricResult(DomainModel):
    """One named V0 metric with an explicit numerator and denominator."""

    name: MetricName
    numerator: int
    denominator: int
    rate: float | None
    cohort: MetricCohort
    explanation: str


class FindingBreakdown(DomainModel):
    """Quality counts grouped by a deterministic finding attribute."""

    dimension: str
    value: str
    total: int
    reviewed: int
    valid_gap: int
    add_eval: int
    already_covered: int
    not_relevant: int
    suppressed: int
    observed_resolution: int
    confirmed_impact: int


class ValidationCriterion(DomainModel):
    """Progress toward one requirement-defined V0 validation target."""

    name: str
    current: str
    target: str
    status: ValidationCriterionStatus
    explanation: str


class ValidationSummary(DomainModel):
    """Repository-local metrics, quality breakdowns, and V0 progress."""

    repository: str
    finding_count: int
    reviewed_finding_count: int
    scan_count: int
    metrics: tuple[MetricResult, ...]
    breakdowns: tuple[FindingBreakdown, ...]
    criteria: tuple[ValidationCriterion, ...]
