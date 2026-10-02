"""Static extraction of pytest and JSONL eval scenarios."""

import ast
import hashlib
import json
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from agentguard.extractors.behaviors import extract_behaviors
from agentguard.models import (
    ArtifactType,
    BehaviorType,
    ConfidenceLevel,
    DiscoveredArtifact,
    EvalAssertion,
    EvalAssertionKind,
    EvalParseError,
    EvalParseResult,
    EvalParseWarning,
    EvalScenario,
    EvalSourceType,
    ExpectedOutcome,
    LiteralArgument,
    ReferencedSymbol,
    ScanCompleteness,
    ScanResult,
    SourceEvidence,
)

EVAL_ID_VERSION = "eval-v1"
FINGERPRINT_VERSION = "content-v1"
TOOL_INVOCATION_WRAPPERS = frozenset({"invoke", "ainvoke", "coroutine"})


def _canonical_json(value: JsonValue | dict[str, JsonValue]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _eval_id(source_type: EvalSourceType, source_file: str, identity: str) -> str:
    canonical_identity = _canonical_json(
        {
            "version": EVAL_ID_VERSION,
            "source_type": source_type.value,
            "source_file": source_file,
            "identity": identity,
        }
    )
    return _digest("eval", canonical_identity)


def _content_fingerprint(content: str) -> str:
    return _digest(FINGERPRINT_VERSION, content)


def _evidence(
    *,
    kind: str,
    source_file: str,
    source_symbol: str | None,
    source: str,
    node: ast.AST,
) -> SourceEvidence:
    return SourceEvidence(
        kind=kind,
        source_file=source_file,
        source_symbol=source_symbol,
        start_line=getattr(node, "lineno", None),
        end_line=getattr(node, "end_lineno", None),
        excerpt=ast.get_source_segment(source, node) or ast.unparse(node),
    )


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _as_json_value(value: Any) -> JsonValue:
    normalized: Any = json.loads(json.dumps(value, ensure_ascii=False))
    return cast(JsonValue, normalized)


def _literal_arguments(call: ast.Call) -> tuple[LiteralArgument, ...]:
    arguments: list[LiteralArgument] = []
    for position, argument in enumerate(call.args):
        try:
            value = _as_json_value(ast.literal_eval(argument))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        arguments.append(LiteralArgument(position=position, value=value))
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        try:
            value = _as_json_value(ast.literal_eval(keyword.value))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        arguments.append(LiteralArgument(keyword=keyword.arg, value=value))
    return tuple(arguments)


def _pytest_assertions(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    source_file: str,
    source_symbol: str,
    source: str,
) -> tuple[EvalAssertion, ...]:
    assertions: list[EvalAssertion] = []
    context_raise_calls: set[int] = set()

    for node in ast.walk(function):
        if isinstance(node, ast.Assert):
            assertions.append(
                EvalAssertion(
                    kind=EvalAssertionKind.ASSERT,
                    expression=ast.unparse(node.test),
                    evidence=_evidence(
                        kind="assert",
                        source_file=source_file,
                        source_symbol=source_symbol,
                        source=source,
                        node=node,
                    ),
                )
            )
        if isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                call = item.context_expr
                if not isinstance(call, ast.Call):
                    continue
                name = _qualified_name(call.func)
                if name not in {"pytest.raises", "raises"} or not call.args:
                    continue
                context_raise_calls.add(id(call))
                exception_name = ast.unparse(call.args[0])
                assertions.append(
                    EvalAssertion(
                        kind=EvalAssertionKind.EXPECTED_EXCEPTION,
                        expression=ast.unparse(call),
                        expected_exception=exception_name,
                        evidence=_evidence(
                            kind="expected_exception",
                            source_file=source_file,
                            source_symbol=source_symbol,
                            source=source,
                            node=call,
                        ),
                    )
                )

    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or id(node) in context_raise_calls:
            continue
        name = _qualified_name(node.func)
        if name not in {"pytest.raises", "raises"} or len(node.args) < 2:
            continue
        exception_name = ast.unparse(node.args[0])
        assertions.append(
            EvalAssertion(
                kind=EvalAssertionKind.EXPECTED_EXCEPTION,
                expression=ast.unparse(node),
                expected_exception=exception_name,
                evidence=_evidence(
                    kind="expected_exception",
                    source_file=source_file,
                    source_symbol=source_symbol,
                    source=source,
                    node=node,
                ),
            )
        )

    return tuple(
        sorted(
            assertions,
            key=lambda assertion: (
                assertion.evidence.start_line or 0,
                assertion.kind.value,
                assertion.expression,
            ),
        )
    )


def _pytest_references(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    source_file: str,
    source_symbol: str,
    source: str,
    known_tool_names: Collection[str],
) -> tuple[ReferencedSymbol, ...]:
    references: list[ReferencedSymbol] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        qualified_name = _qualified_name(node.func)
        if qualified_name is None:
            continue
        normalized_tool_name = None
        if isinstance(node.func, ast.Attribute) and node.func.attr in TOOL_INVOCATION_WRAPPERS:
            receiver_name = _qualified_name(node.func.value)
            if receiver_name in known_tool_names:
                normalized_tool_name = receiver_name
        references.append(
            ReferencedSymbol(
                name=qualified_name.rsplit(".", maxsplit=1)[-1],
                qualified_name=qualified_name,
                normalized_tool_name=normalized_tool_name,
                literal_arguments=_literal_arguments(node),
                evidence=_evidence(
                    kind="call",
                    source_file=source_file,
                    source_symbol=source_symbol,
                    source=source,
                    node=node,
                ),
            )
        )
    return tuple(
        sorted(
            references,
            key=lambda reference: (
                reference.evidence.start_line or 0,
                reference.qualified_name,
                reference.evidence.excerpt,
            ),
        )
    )


def _test_functions(
    tree: ast.Module,
) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test_"
        ):
            yield node, node.name
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(
                    child, ast.FunctionDef | ast.AsyncFunctionDef
                ) and child.name.startswith("test_"):
                    yield child, f"{node.name}.{child.name}"


def _function_parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    parameters = [
        argument.arg
        for argument in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        if argument.arg not in {"self", "cls"}
    ]
    if function.args.vararg is not None:
        parameters.append(f"*{function.args.vararg.arg}")
    if function.args.kwarg is not None:
        parameters.append(f"**{function.args.kwarg.arg}")
    return parameters


def _is_likely_pytest_path(source_file: str) -> bool:
    path = Path(source_file)
    return path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in path.parts


def _expected_from_assertions(
    assertions: tuple[EvalAssertion, ...],
) -> ExpectedOutcome | None:
    if not assertions:
        return None
    descriptions = [
        (
            f"raises {assertion.expected_exception}"
            if assertion.kind is EvalAssertionKind.EXPECTED_EXCEPTION
            else assertion.expression
        )
        for assertion in assertions
    ]
    return ExpectedOutcome(description="; ".join(descriptions))


def parse_pytest_artifact(
    root: Path,
    artifact: DiscoveredArtifact,
    *,
    known_tool_names: Collection[str] = (),
) -> EvalParseResult:
    """Parse pytest-style tests from one Python artifact using AST only."""
    artifact_path = root / artifact.path
    try:
        source = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return EvalParseResult(
            errors=(
                EvalParseError(
                    code="python_eval_unreadable",
                    message=f"Unable to read Python artifact: {error}",
                    source_file=artifact.path,
                ),
            ),
            completeness=ScanCompleteness.INCOMPLETE,
        )
    try:
        tree = ast.parse(source, filename=artifact.path)
    except SyntaxError as error:
        if not _is_likely_pytest_path(artifact.path):
            return EvalParseResult(completeness=ScanCompleteness.COMPLETE)
        return EvalParseResult(
            warnings=(
                EvalParseWarning(
                    code="python_syntax_error",
                    message=error.msg,
                    source_file=artifact.path,
                    line=error.lineno,
                ),
            ),
            completeness=ScanCompleteness.INCOMPLETE,
        )

    scenarios: list[EvalScenario] = []
    for function, symbol in _test_functions(tree):
        assertions = _pytest_assertions(function, artifact.path, symbol, source)
        references = _pytest_references(
            function,
            artifact.path,
            symbol,
            source,
            known_tool_names,
        )
        docstring = ast.get_docstring(function, clean=True)
        evidence = _evidence(
            kind="pytest_test",
            source_file=artifact.path,
            source_symbol=symbol,
            source=source,
            node=function,
        )
        normalized_ast = ast.dump(function, annotate_fields=True, include_attributes=False)
        scenarios.append(
            EvalScenario(
                eval_id=_eval_id(EvalSourceType.PYTEST, artifact.path, symbol),
                source_type=EvalSourceType.PYTEST,
                source_file=artifact.path,
                source_symbol=symbol,
                name=function.name,
                description=docstring or function.name.removeprefix("test_").replace("_", " "),
                inputs=cast(JsonValue, {"parameters": _function_parameters(function)}),
                expected_outcome=_expected_from_assertions(assertions),
                assertions=assertions,
                referenced_symbols=references,
                evidence=(evidence,),
                content_fingerprint=_content_fingerprint(normalized_ast),
                confidence=ConfidenceLevel.HIGH,
            )
        )
    return EvalParseResult(
        scenarios=tuple(sorted(scenarios, key=lambda scenario: scenario.eval_id)),
        completeness=ScanCompleteness.COMPLETE,
    )


def _jsonl_warning(code: str, message: str, source_file: str, line: int) -> EvalParseWarning:
    return EvalParseWarning(code=code, message=message, source_file=source_file, line=line)


def parse_jsonl_artifact(root: Path, artifact: DiscoveredArtifact) -> EvalParseResult:
    """Parse independent eval scenarios from a supported JSONL artifact."""
    artifact_path = root / artifact.path
    try:
        source = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return EvalParseResult(
            errors=(
                EvalParseError(
                    code="jsonl_eval_unreadable",
                    message=f"Unable to read JSONL artifact: {error}",
                    source_file=artifact.path,
                ),
            ),
            completeness=ScanCompleteness.INCOMPLETE,
        )

    scenarios: list[EvalScenario] = []
    warnings: list[EvalParseWarning] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as error:
            warnings.append(
                _jsonl_warning("jsonl_malformed", error.msg, artifact.path, line_number)
            )
            continue
        if not isinstance(record, dict):
            warnings.append(
                _jsonl_warning(
                    "jsonl_record_not_object",
                    "JSONL eval record must be an object.",
                    artifact.path,
                    line_number,
                )
            )
            continue
        if "input" not in record:
            warnings.append(
                _jsonl_warning(
                    "jsonl_input_missing",
                    "JSONL eval record is missing required field 'input'.",
                    artifact.path,
                    line_number,
                )
            )
            continue

        metadata_value = record.get("metadata", {})
        metadata: dict[str, JsonValue]
        if isinstance(metadata_value, dict):
            metadata = metadata_value
        else:
            metadata = {}
            warnings.append(
                _jsonl_warning(
                    "jsonl_metadata_invalid",
                    "JSONL metadata must be an object when present.",
                    artifact.path,
                    line_number,
                )
            )

        metadata_name = metadata.get("name")
        name = metadata_name if isinstance(metadata_name, str) and metadata_name else None
        input_value: JsonValue = record["input"]
        identity = f"name:{name}" if name else f"input:{_canonical_json(input_value)}"
        eval_id = _eval_id(EvalSourceType.JSONL, artifact.path, identity)
        fingerprint = _content_fingerprint(_canonical_json(record))
        if eval_id in seen_ids:
            warnings.append(
                _jsonl_warning(
                    "jsonl_duplicate_identity",
                    "JSONL eval record duplicates a stable eval identity and was skipped.",
                    artifact.path,
                    line_number,
                )
            )
            continue
        seen_ids.add(eval_id)

        tools = metadata.get("tools", [])
        tool_names = (
            [tool for tool in tools if isinstance(tool, str)] if isinstance(tools, list) else []
        )
        tools_are_valid = isinstance(tools, list) and len(tool_names) == len(tools)
        if tools and not tools_are_valid:
            warnings.append(
                _jsonl_warning(
                    "jsonl_tools_invalid",
                    "JSONL metadata.tools must be a list of strings when present.",
                    artifact.path,
                    line_number,
                )
            )
        evidence = SourceEvidence(
            kind="jsonl_record",
            source_file=artifact.path,
            source_symbol=name,
            start_line=line_number,
            end_line=line_number,
            excerpt=raw_line,
        )
        references = tuple(
            ReferencedSymbol(
                name=tool_name,
                qualified_name=tool_name,
                evidence=SourceEvidence(
                    kind="metadata_tool",
                    source_file=artifact.path,
                    source_symbol=name,
                    start_line=line_number,
                    end_line=line_number,
                    excerpt=tool_name,
                ),
            )
            for tool_name in sorted(tool_names)
        )
        expected_outcome = (
            ExpectedOutcome(
                description="Expected outcome supplied by JSONL record.",
                value=record["expected"],
            )
            if "expected" in record
            else None
        )
        unknown_fields = {
            key: value
            for key, value in record.items()
            if key not in {"input", "expected", "metadata"}
        }
        description = name or (
            input_value[:160] if isinstance(input_value, str) else "JSONL eval scenario"
        )
        scenarios.append(
            EvalScenario(
                eval_id=eval_id,
                source_type=EvalSourceType.JSONL,
                source_file=artifact.path,
                source_symbol=name,
                name=name or f"line_{line_number}",
                description=description,
                inputs=input_value,
                expected_outcome=expected_outcome,
                referenced_symbols=references,
                evidence=(evidence,),
                metadata=metadata,
                unknown_fields=unknown_fields,
                content_fingerprint=fingerprint,
                confidence=ConfidenceLevel.HIGH,
            )
        )

    completeness = ScanCompleteness.INCOMPLETE if warnings else ScanCompleteness.COMPLETE
    return EvalParseResult(
        scenarios=tuple(sorted(scenarios, key=lambda scenario: scenario.eval_id)),
        warnings=tuple(
            sorted(
                warnings, key=lambda warning: (warning.source_file, warning.line or 0, warning.code)
            )
        ),
        completeness=completeness,
    )


def parse_eval_artifacts(
    scan_result: ScanResult,
    *,
    known_tool_names: Collection[str] | None = None,
) -> EvalParseResult:
    """Parse eval scenarios from a repository discovery manifest."""
    if scan_result.completeness is ScanCompleteness.FAILED or scan_result.repository.root is None:
        return EvalParseResult(
            errors=(
                EvalParseError(
                    code="discovery_failed",
                    message="Eval parsing could not start because repository discovery failed.",
                    source_file=scan_result.repository.requested_path,
                ),
            ),
            completeness=ScanCompleteness.FAILED,
        )

    root = Path(scan_result.repository.root)
    if known_tool_names is None:
        behavior_result = extract_behaviors(scan_result)
        known_tool_names = {
            behavior.subject
            for behavior in behavior_result.behaviors
            if behavior.behavior_type is BehaviorType.TOOL_INVOCATION
        }
    scenarios: list[EvalScenario] = []
    warnings: list[EvalParseWarning] = []
    errors: list[EvalParseError] = []
    for artifact in scan_result.artifacts:
        if artifact.artifact_type is ArtifactType.PYTHON:
            parsed = parse_pytest_artifact(
                root,
                artifact,
                known_tool_names=known_tool_names,
            )
        elif artifact.artifact_type is ArtifactType.EVAL_JSONL:
            parsed = parse_jsonl_artifact(root, artifact)
        else:
            continue
        scenarios.extend(parsed.scenarios)
        warnings.extend(parsed.warnings)
        errors.extend(parsed.errors)

    unique_warnings = {
        (warning.source_file, warning.line, warning.code, warning.message): warning
        for warning in warnings
    }
    incomplete = (
        scan_result.completeness is ScanCompleteness.INCOMPLETE
        or bool(unique_warnings)
        or bool(errors)
    )
    return EvalParseResult(
        scenarios=tuple(
            sorted(
                scenarios,
                key=lambda scenario: (
                    scenario.source_file,
                    scenario.source_symbol or "",
                    scenario.eval_id,
                ),
            )
        ),
        warnings=tuple(
            sorted(
                unique_warnings.values(),
                key=lambda warning: (
                    warning.source_file,
                    warning.line or 0,
                    warning.code,
                    warning.message,
                ),
            )
        ),
        errors=tuple(sorted(errors, key=lambda error: (error.source_file, error.code))),
        completeness=ScanCompleteness.INCOMPLETE if incomplete else ScanCompleteness.COMPLETE,
    )
