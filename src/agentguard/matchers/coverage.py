"""Deterministic, indexed behavior-to-eval matching."""

import ast
import json
import re
from collections import defaultdict
from dataclasses import dataclass

from agentguard.models import (
    AssessmentAvailability,
    Behavior,
    BehaviorCoverageAssessment,
    BehaviorEvalMatch,
    BehaviorExtractionResult,
    BehaviorType,
    ConfidenceLevel,
    CoverageStatus,
    EvalAssertionKind,
    EvalParseResult,
    EvalScenario,
    EvalSourceType,
    MatchEvidence,
    MatchingError,
    MatchingResult,
    MatchingWarning,
    ReferencedSymbol,
    ScanCompleteness,
)

MATCHER_NAME = "deterministic-v1"
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*|-?\d+(?:\.\d+)?")
WEAK_TERMS = {
    "action",
    "agent",
    "automatic",
    "branch",
    "call",
    "case",
    "error",
    "expected",
    "failure",
    "false",
    "graph",
    "input",
    "none",
    "result",
    "return",
    "route",
    "source",
    "status",
    "test",
    "true",
    "workflow",
}
_UNKNOWN = object()


def _normalize_name(value: str) -> str:
    return value.casefold().rsplit(".", maxsplit=1)[-1]


def _terms(value: object) -> set[str]:
    if value is None:
        return set()
    text = (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    terms: set[str] = set()
    for token in TOKEN_PATTERN.findall(text):
        normalized = token.casefold()
        terms.add(normalized)
        terms.update(part for part in normalized.split("_") if part)
    return terms


def _literal_values(value: object) -> set[str]:
    if isinstance(value, dict):
        values = {_normalize_name(str(key)) for key in value}
        for item in value.values():
            values.update(_literal_values(item))
        return values
    if isinstance(value, list | tuple):
        collected: set[str] = set()
        for item in value:
            collected.update(_literal_values(item))
        return collected
    if value is None:
        return {"null"}
    if isinstance(value, bool):
        return {str(value).casefold()}
    if isinstance(value, int | float):
        return {str(value)}
    return {_normalize_name(str(value))}


@dataclass(frozen=True)
class _EvalFeatures:
    scenario: EvalScenario
    symbols: frozenset[str]
    terms: frozenset[str]
    values: frozenset[str]
    expected_terms: frozenset[str]
    assertion_terms: frozenset[str]
    expected_exceptions: frozenset[str]
    has_assertion: bool
    has_normal_assertion: bool
    has_expected: bool


@dataclass
class _CandidateIndex:
    features: tuple[_EvalFeatures, ...]
    symbols: dict[str, set[int]]
    terms: dict[str, set[int]]
    exceptions: dict[str, set[int]]


def _scenario_features(scenario: EvalScenario) -> _EvalFeatures:
    symbols = {
        _normalize_name(name)
        for reference in scenario.referenced_symbols
        for name in (
            reference.name,
            reference.qualified_name,
            reference.normalized_tool_name,
            reference.normalized_subject_name,
        )
        if name is not None
    }
    assertion_text = " ".join(assertion.expression for assertion in scenario.assertions)
    expected_text_parts = [
        scenario.expected_outcome.description if scenario.expected_outcome else "",
        (
            json.dumps(scenario.expected_outcome.value, ensure_ascii=False, sort_keys=True)
            if scenario.expected_outcome and scenario.expected_outcome.value is not None
            else ""
        ),
    ]
    searchable = " ".join(
        part
        for part in (
            scenario.name,
            scenario.description or "",
            json.dumps(scenario.inputs, ensure_ascii=False, sort_keys=True),
            " ".join(expected_text_parts),
            assertion_text,
            json.dumps(scenario.metadata, ensure_ascii=False, sort_keys=True),
            " ".join(symbols),
        )
        if part
    )
    values = _literal_values(scenario.inputs)
    for reference in scenario.referenced_symbols:
        for argument in reference.literal_arguments:
            values.update(_literal_values(argument.value))
    if scenario.expected_outcome is not None:
        values.update(_literal_values(scenario.expected_outcome.value))
    expected_exceptions = {
        _normalize_name(assertion.expected_exception)
        for assertion in scenario.assertions
        if assertion.kind is EvalAssertionKind.EXPECTED_EXCEPTION
        and assertion.expected_exception is not None
    }
    return _EvalFeatures(
        scenario=scenario,
        symbols=frozenset(symbols),
        terms=frozenset(_terms(searchable)),
        values=frozenset(values),
        expected_terms=frozenset(_terms(" ".join(expected_text_parts))),
        assertion_terms=frozenset(_terms(assertion_text)),
        expected_exceptions=frozenset(expected_exceptions),
        has_assertion=bool(scenario.assertions),
        has_normal_assertion=any(
            assertion.kind is EvalAssertionKind.ASSERT for assertion in scenario.assertions
        ),
        has_expected=scenario.expected_outcome is not None,
    )


def _build_index(scenarios: tuple[EvalScenario, ...]) -> _CandidateIndex:
    features = tuple(_scenario_features(scenario) for scenario in scenarios)
    symbol_index: dict[str, set[int]] = defaultdict(set)
    term_index: dict[str, set[int]] = defaultdict(set)
    exception_index: dict[str, set[int]] = defaultdict(set)
    for index, feature in enumerate(features):
        for symbol in feature.symbols:
            symbol_index[symbol].add(index)
        for term in feature.terms:
            term_index[term].add(index)
        for exception in feature.expected_exceptions:
            exception_index[exception].add(index)
    return _CandidateIndex(
        features=features,
        symbols=dict(symbol_index),
        terms=dict(term_index),
        exceptions=dict(exception_index),
    )


def _behavior_identity_terms(behavior: Behavior) -> set[str]:
    values = [behavior.subject]
    if behavior.action is not None:
        if behavior.action.target:
            values.append(behavior.action.target)
        if behavior.action.kind == "raise" and behavior.action.outcome:
            values.append(behavior.action.outcome)
    return {
        normalized
        for value in values
        if (normalized := _normalize_name(value)) not in WEAK_TERMS
        and len(normalized) >= 5
        and TOKEN_PATTERN.fullmatch(normalized) is not None
    }


def _candidate_reasons(behavior: Behavior, index: _CandidateIndex) -> dict[int, set[str]]:
    candidates: dict[int, set[str]] = defaultdict(set)
    subject = _normalize_name(behavior.subject)
    for candidate in index.symbols.get(subject, set()):
        candidates[candidate].add("referenced_subject")

    if behavior.action is not None and behavior.action.target:
        target = _normalize_name(behavior.action.target)
        for candidate in index.symbols.get(target, set()):
            candidates[candidate].add("referenced_action_target")

    if behavior.behavior_type is BehaviorType.TOOL_FAILURE and behavior.action is not None:
        outcome = behavior.action.outcome
        if behavior.action.kind == "raise" and outcome:
            exception = _normalize_name(outcome)
            for candidate in index.exceptions.get(exception, set()):
                candidates[candidate].add("expected_exception")

    for term in sorted(_behavior_identity_terms(behavior)):
        for candidate in index.terms.get(term, set()):
            candidates[candidate].add(f"identity_term:{term}")
    return candidates


def _reference_for_subject(behavior: Behavior, feature: _EvalFeatures) -> ReferencedSymbol | None:
    subject = _normalize_name(behavior.subject)
    direct = next(
        (
            reference
            for reference in feature.scenario.referenced_symbols
            if _normalize_name(reference.name) == subject
            or _normalize_name(reference.qualified_name) == subject
        ),
        None,
    )
    if direct is not None:
        return direct
    return next(
        (
            reference
            for reference in feature.scenario.referenced_symbols
            if reference.normalized_tool_name is not None
            and _normalize_name(reference.normalized_tool_name) == subject
            or reference.normalized_subject_name is not None
            and _normalize_name(reference.normalized_subject_name) == subject
        ),
        None,
    )


def _argument_bindings(
    behavior: Behavior, reference: ReferencedSymbol | None, scenario: EvalScenario
) -> dict[str, object]:
    if scenario.source_type in {EvalSourceType.JSONL, EvalSourceType.PYDANTIC_EVAL} and isinstance(
        scenario.inputs, dict
    ):
        return {str(key): value for key, value in scenario.inputs.items()}
    if reference is None:
        return {}
    positional_names = [
        argument.name
        for argument in behavior.arguments
        if not argument.name.startswith(("*", "**"))
    ]
    bindings: dict[str, object] = {}
    for argument in reference.literal_arguments:
        if argument.keyword is not None:
            bindings[argument.keyword] = argument.value
        elif argument.position is not None and argument.position < len(positional_names):
            bindings[positional_names[argument.position]] = argument.value
    return bindings


def _compare(left: object, operator: ast.cmpop, right: object) -> object:
    try:
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.Lt):
            return left < right  # type: ignore[operator]
        if isinstance(operator, ast.LtE):
            return left <= right  # type: ignore[operator]
        if isinstance(operator, ast.Gt):
            return left > right  # type: ignore[operator]
        if isinstance(operator, ast.GtE):
            return left >= right  # type: ignore[operator]
        if isinstance(operator, ast.In):
            return left in right  # type: ignore[operator]
        if isinstance(operator, ast.NotIn):
            return left not in right  # type: ignore[operator]
        if isinstance(operator, ast.Is):
            return left is right
        if isinstance(operator, ast.IsNot):
            return left is not right
    except TypeError:
        return _UNKNOWN
    return _UNKNOWN


def _evaluate_expression(node: ast.AST, bindings: dict[str, object]) -> object:
    if isinstance(node, ast.Expression):
        return _evaluate_expression(node.body, bindings)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return bindings.get(node.id, _UNKNOWN)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        operand = _evaluate_expression(node.operand, bindings)
        return _UNKNOWN if operand is _UNKNOWN else not bool(operand)
    if isinstance(node, ast.BoolOp):
        values = [_evaluate_expression(value, bindings) for value in node.values]
        if any(value is _UNKNOWN for value in values):
            return _UNKNOWN
        if isinstance(node.op, ast.And):
            return all(bool(value) for value in values)
        if isinstance(node.op, ast.Or):
            return any(bool(value) for value in values)
    if isinstance(node, ast.Compare):
        left = _evaluate_expression(node.left, bindings)
        if left is _UNKNOWN:
            return _UNKNOWN
        for operator, comparator_node in zip(node.ops, node.comparators, strict=True):
            right = _evaluate_expression(comparator_node, bindings)
            if right is _UNKNOWN:
                return _UNKNOWN
            comparison = _compare(left, operator, right)
            if comparison is _UNKNOWN or not comparison:
                return comparison
            left = right
        return True
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        values = [_evaluate_expression(element, bindings) for element in node.elts]
        return _UNKNOWN if any(value is _UNKNOWN for value in values) else values
    return _UNKNOWN


def _condition_matches(
    behavior: Behavior,
    feature: _EvalFeatures,
    reference: ReferencedSymbol | None,
) -> bool:
    if behavior.condition is None:
        return True
    bindings = _argument_bindings(behavior, reference, feature.scenario)
    try:
        expression = ast.parse(behavior.condition.normalized_expression, mode="eval")
    except SyntaxError:
        expression = None
    if expression is not None:
        evaluated = _evaluate_expression(expression, bindings)
        if evaluated is not _UNKNOWN:
            return bool(evaluated)

    constants: set[str] = set()
    if expression is not None:
        for node in ast.walk(expression):
            if isinstance(node, ast.Constant):
                constants.update(_literal_values(node.value))
    return bool(constants and constants <= feature.values)


def _action_terms(behavior: Behavior) -> set[str]:
    if behavior.action is None:
        return set()
    values = [item for item in (behavior.action.target, behavior.action.outcome) if item]
    terms = {term for value in values for term in _terms(value)}
    return {term for term in terms if term not in WEAK_TERMS and len(term) >= 3}


def _action_matches(behavior: Behavior, feature: _EvalFeatures) -> bool:
    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        return True
    if behavior.action is None:
        return False
    verified_terms = feature.expected_terms | feature.assertion_terms
    if behavior.action.target:
        target = _normalize_name(behavior.action.target)
        if target in verified_terms:
            return True
    terms = _action_terms(behavior)
    return bool(terms) and terms <= verified_terms


def _failure_matches(behavior: Behavior, feature: _EvalFeatures) -> bool:
    if behavior.action is None:
        return False
    if behavior.action.kind == "raise" and behavior.action.outcome:
        return _normalize_name(behavior.action.outcome) in feature.expected_exceptions
    return _action_matches(behavior, feature)


def _has_verification(feature: _EvalFeatures, *, exception: bool = False) -> bool:
    if feature.scenario.source_type in {EvalSourceType.JSONL, EvalSourceType.PYDANTIC_EVAL}:
        return feature.has_expected
    return feature.has_assertion if exception else feature.has_normal_assertion


def _classify_candidate(
    behavior: Behavior,
    feature: _EvalFeatures,
    reasons: set[str],
) -> BehaviorEvalMatch:
    reference = _reference_for_subject(behavior, feature)
    subject = _normalize_name(behavior.subject)
    same_subject = reference is not None or (
        feature.scenario.source_type is EvalSourceType.JSONL and subject in feature.terms
    )
    wrapper_invocation = reference is not None and reference.normalized_tool_name is not None
    invocation_only = (
        wrapper_invocation and behavior.behavior_type is not BehaviorType.TOOL_INVOCATION
    )
    condition_matches = (
        False if invocation_only else _condition_matches(behavior, feature, reference)
    )
    action_matches = False if invocation_only else _action_matches(behavior, feature)
    failure_matches = False if invocation_only else _failure_matches(behavior, feature)
    branch_matches = condition_matches and action_matches
    status: CoverageStatus | None = None
    details: list[str] = []

    if same_subject:
        details.append("Eval exercises the behavior subject.")
    if wrapper_invocation:
        details.append("A statically known tool is invoked through its supported wrapper method.")
    if condition_matches and behavior.condition is not None:
        details.append("Literal inputs satisfy or explicitly identify the behavior condition.")
    if action_matches:
        details.append("The expected or asserted outcome identifies the behavior action.")
    if failure_matches:
        details.append("The eval verifies the behavior's explicit failure outcome.")

    if behavior.behavior_type is BehaviorType.TOOL_INVOCATION:
        if same_subject and _has_verification(feature):
            status = CoverageStatus.COVERED
        elif same_subject:
            status = CoverageStatus.PARTIALLY_COVERED
    elif behavior.behavior_type is BehaviorType.TOOL_FAILURE:
        exception = behavior.action is not None and behavior.action.kind == "raise"
        if (
            same_subject
            and condition_matches
            and failure_matches
            and _has_verification(feature, exception=exception)
        ):
            status = CoverageStatus.COVERED
        elif same_subject:
            status = CoverageStatus.PARTIALLY_COVERED
    elif behavior.behavior_type is BehaviorType.CONDITIONAL_BRANCH:
        exception = behavior.action is not None and behavior.action.kind == "raise"
        if same_subject and branch_matches and _has_verification(feature, exception=exception):
            status = CoverageStatus.COVERED
        elif same_subject:
            status = CoverageStatus.PARTIALLY_COVERED
    else:
        if branch_matches and _has_verification(feature):
            status = CoverageStatus.COVERED
        elif condition_matches or action_matches:
            status = CoverageStatus.PARTIALLY_COVERED

    confidence = (
        ConfidenceLevel.HIGH if status is CoverageStatus.COVERED else ConfidenceLevel.MEDIUM
    )
    if status is None:
        confidence = ConfidenceLevel.LOW
    return BehaviorEvalMatch(
        eval_id=feature.scenario.eval_id,
        coverage_status=status,
        confidence=confidence,
        evidence=MatchEvidence(
            candidate_reasons=tuple(sorted(reasons)),
            same_subject=same_subject,
            condition_matches=condition_matches,
            branch_matches=branch_matches,
            failure_matches=failure_matches,
            action_matches=action_matches,
            explicit_assertion=feature.has_assertion,
            expected_outcome_present=feature.has_expected,
            details=tuple(details),
        ),
    )


def _assessment(
    behavior: Behavior,
    matches: tuple[BehaviorEvalMatch, ...],
    *,
    behavior_evidence_complete: bool,
    eval_evidence_complete: bool,
) -> BehaviorCoverageAssessment:
    covered = [match for match in matches if match.coverage_status is CoverageStatus.COVERED]
    partial = [
        match for match in matches if match.coverage_status is CoverageStatus.PARTIALLY_COVERED
    ]
    matched = [*covered, *partial]
    if not behavior_evidence_complete:
        return BehaviorCoverageAssessment(
            behavior_id=behavior.behavior_id,
            availability=AssessmentAvailability.UNAVAILABLE,
            confidence=ConfidenceLevel.LOW,
            matched_eval_ids=tuple(match.eval_id for match in [*covered, *partial]),
            matches=matches,
            explanation=(
                "Coverage is unavailable because extraction evidence for this behavior is "
                "incomplete."
            ),
            candidate_count=len(matches),
            matcher=MATCHER_NAME,
        )
    if covered:
        status = CoverageStatus.COVERED
        confidence = ConfidenceLevel.HIGH
        explanation = "At least one eval exercises the behavior and verifies its expected outcome."
    elif not eval_evidence_complete:
        return BehaviorCoverageAssessment(
            behavior_id=behavior.behavior_id,
            availability=AssessmentAvailability.UNAVAILABLE,
            confidence=ConfidenceLevel.LOW,
            matched_eval_ids=tuple(match.eval_id for match in partial),
            matches=matches,
            explanation=(
                "Coverage is unavailable because a recognized eval source is incomplete; "
                "missing evidence cannot be treated as absent coverage."
            ),
            candidate_count=len(matches),
            matcher=MATCHER_NAME,
        )
    elif partial:
        status = CoverageStatus.PARTIALLY_COVERED
        confidence = ConfidenceLevel.MEDIUM
        explanation = (
            "Existing evals exercise the same functionality but do not deterministically verify "
            "this exact condition and expected outcome."
        )
    else:
        status = CoverageStatus.POTENTIALLY_UNCOVERED
        confidence = ConfidenceLevel.HIGH if not matches else ConfidenceLevel.MEDIUM
        explanation = (
            "No discovered eval both exercises this behavior and verifies its expected outcome."
        )
    return BehaviorCoverageAssessment(
        behavior_id=behavior.behavior_id,
        availability=AssessmentAvailability.AVAILABLE,
        coverage_status=status,
        confidence=confidence,
        matched_eval_ids=tuple(sorted(match.eval_id for match in matched)),
        matches=matches,
        explanation=explanation,
        candidate_count=len(matches),
        matcher=MATCHER_NAME,
    )


def match_behaviors_to_evals(
    behavior_result: BehaviorExtractionResult,
    eval_result: EvalParseResult,
) -> MatchingResult:
    """Match extracted behaviors to evals using indexed deterministic evidence."""
    index = _build_index(eval_result.scenarios)
    failed = (
        behavior_result.completeness is ScanCompleteness.FAILED
        or eval_result.completeness is ScanCompleteness.FAILED
    )
    assessments: list[BehaviorCoverageAssessment] = []
    candidate_pair_count = 0
    for behavior in behavior_result.behaviors:
        candidate_map = _candidate_reasons(behavior, index)
        candidate_pair_count += len(candidate_map)
        matches = tuple(
            sorted(
                (
                    _classify_candidate(behavior, index.features[candidate], reasons)
                    for candidate, reasons in candidate_map.items()
                ),
                key=lambda match: match.eval_id,
            )
        )
        assessments.append(
            _assessment(
                behavior,
                matches,
                behavior_evidence_complete=(
                    behavior.behavior_id not in behavior_result.unavailable_behavior_ids
                ),
                eval_evidence_complete=not eval_result.uncertain_source_files,
            )
        )

    warnings: tuple[MatchingWarning, ...] = ()
    errors: tuple[MatchingError, ...] = ()
    if failed:
        errors = (
            MatchingError(
                code="upstream_failed",
                message="Matching evidence is unavailable because an upstream stage failed.",
            ),
        )
        completeness = ScanCompleteness.FAILED
    elif (
        behavior_result.completeness is ScanCompleteness.INCOMPLETE
        or eval_result.completeness is ScanCompleteness.INCOMPLETE
    ):
        warnings = (
            MatchingWarning(
                code="upstream_incomplete",
                message="Some coverage assessments are unavailable due to incomplete evidence.",
            ),
        )
        completeness = ScanCompleteness.INCOMPLETE
    else:
        completeness = ScanCompleteness.COMPLETE

    return MatchingResult(
        assessments=tuple(sorted(assessments, key=lambda item: item.behavior_id)),
        warnings=warnings,
        errors=errors,
        completeness=completeness,
        behavior_count=len(behavior_result.behaviors),
        eval_count=len(eval_result.scenarios),
        candidate_pair_count=candidate_pair_count,
        matcher=MATCHER_NAME,
    )
