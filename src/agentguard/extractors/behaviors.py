"""Deterministic behavior extraction from static Python source."""

import ast
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from agentguard.extractors.crewai import ConfigCache, extract_crewai_from_tree
from agentguard.extractors.pydantic_ai import extract_pydantic_ai_from_tree
from agentguard.models import (
    ArtifactType,
    Behavior,
    BehaviorAction,
    BehaviorCondition,
    BehaviorExtractionError,
    BehaviorExtractionResult,
    BehaviorExtractionWarning,
    BehaviorSourceType,
    BehaviorType,
    ConfidenceLevel,
    DiscoveredArtifact,
    FrameworkConstruct,
    FrameworkSummary,
    ScanCompleteness,
    ScanResult,
    SourceEvidence,
    ToolArgument,
)

BEHAVIOR_ID_VERSION = "behavior-v1"
FINGERPRINT_VERSION = "behavior-content-v1"
EXTRACTOR_NAME = "python_ast_v1"
TOOL_DECORATORS = {"tool", "function_tool"}
ESCALATION_PREFIXES = ("escalate", "handoff")


def _canonical_json(value: dict[str, str | None]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _behavior_id(
    *,
    source_type: BehaviorSourceType,
    source_file: str,
    subject: str,
    behavior_type: BehaviorType,
    condition: str | None,
    action: str | None,
) -> str:
    identity = _canonical_json(
        {
            "version": BEHAVIOR_ID_VERSION,
            "source_type": source_type.value,
            "source_file": source_file,
            "subject": subject,
            "behavior_type": behavior_type.value,
            "condition": condition,
            "action": action,
        }
    )
    return _digest("behavior", identity)


def _fingerprint(node: ast.AST) -> str:
    normalized = ast.dump(node, annotate_fields=True, include_attributes=False)
    return _digest(FINGERPRINT_VERSION, normalized)


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _source_evidence(
    *, source_file: str, source_symbol: str | None, source: str, node: ast.AST, kind: str
) -> SourceEvidence:
    return SourceEvidence(
        kind=kind,
        source_file=source_file,
        source_symbol=source_symbol,
        start_line=getattr(node, "lineno", None),
        end_line=getattr(node, "end_lineno", None),
        excerpt=ast.get_source_segment(source, node) or ast.unparse(node),
    )


def _condition(expressions: tuple[str, ...]) -> BehaviorCondition | None:
    if not expressions:
        return None
    expression = " and ".join(f"({item})" for item in expressions)
    return BehaviorCondition(expression=expression, normalized_expression=expression)


def _is_test_path(source_file: str) -> bool:
    path = Path(source_file)
    return path.name.startswith("test_") or path.name.endswith("_test.py") or "tests" in path.parts


def _decorator_name(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        return _qualified_name(decorator.func)
    return _qualified_name(decorator)


def _is_tool_decorator(decorator: ast.expr) -> bool:
    name = _decorator_name(decorator)
    if name is None:
        return False
    final_name = name.rsplit(".", maxsplit=1)[-1]
    return final_name in TOOL_DECORATORS


def _collection_names(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.List | ast.Tuple | ast.Set):
        return set()
    return {element.id for element in node.elts if isinstance(element, ast.Name)}


def _registered_tool_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            target_names = [target.id for target in targets if isinstance(target, ast.Name)]
            if value is not None and any(
                target == "tools" or target.endswith("_tools") for target in target_names
            ):
                names.update(_collection_names(value))
        if not isinstance(node, ast.Call):
            continue
        call_name = _qualified_name(node.func)
        if call_name is not None and call_name.endswith(".bind_tools") and node.args:
            names.update(_collection_names(node.args[0]))
        for keyword in node.keywords:
            if keyword.arg == "tools":
                names.update(_collection_names(keyword.value))
    return names


def _tool_functions(
    tree: ast.Module,
    excluded_names: set[str] | frozenset[str] = frozenset(),
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    registered_names = _registered_tool_names(tree)
    return tuple(
        function
        for name, function in functions.items()
        if name not in excluded_names
        if name in registered_names
        or any(_is_tool_decorator(item) for item in function.decorator_list)
    )


def _tool_arguments(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ToolArgument, ...]:
    positional = [*function.args.posonlyargs, *function.args.args]
    default_offset = len(positional) - len(function.args.defaults)
    arguments: list[ToolArgument] = []
    for index, argument in enumerate(positional):
        if argument.arg in {"self", "cls"}:
            continue
        default_node = (
            function.args.defaults[index - default_offset] if index >= default_offset else None
        )
        arguments.append(
            ToolArgument(
                name=argument.arg,
                required=default_node is None,
                annotation=ast.unparse(argument.annotation) if argument.annotation else None,
                default=ast.unparse(default_node) if default_node else None,
            )
        )
    for argument, default_node in zip(
        function.args.kwonlyargs, function.args.kw_defaults, strict=True
    ):
        arguments.append(
            ToolArgument(
                name=argument.arg,
                required=default_node is None,
                annotation=ast.unparse(argument.annotation) if argument.annotation else None,
                default=ast.unparse(default_node) if default_node else None,
            )
        )
    if function.args.vararg is not None:
        arguments.append(ToolArgument(name=f"*{function.args.vararg.arg}", required=False))
    if function.args.kwarg is not None:
        arguments.append(ToolArgument(name=f"**{function.args.kwarg.arg}", required=False))
    return tuple(arguments)


def _exception_name(raise_node: ast.Raise) -> str:
    if raise_node.exc is None:
        return "exception"
    if isinstance(raise_node.exc, ast.Call):
        return _qualified_name(raise_node.exc.func) or ast.unparse(raise_node.exc.func)
    return ast.unparse(raise_node.exc)


def _failure_return(return_node: ast.Return) -> str | None:
    value = return_node.value
    if isinstance(value, ast.Constant) and value.value is False:
        return ast.unparse(value)
    if isinstance(value, ast.Dict):
        entries: dict[str, ast.expr] = {}
        for key, item in zip(value.keys, value.values, strict=True):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                entries[key.value] = item
        if "error" in entries or "errors" in entries:
            return ast.unparse(value)
        success = entries.get("success")
        if isinstance(success, ast.Constant) and success.value is False:
            return ast.unparse(value)
        status = entries.get("status")
        if isinstance(status, ast.Constant) and status.value in {"error", "failed", "failure"}:
            return ast.unparse(value)
    return None


def _escalation_calls(node: ast.AST) -> tuple[ast.Call, ...]:
    calls: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _qualified_name(child.func)
        final_name = name.rsplit(".", maxsplit=1)[-1] if name else ""
        if final_name.startswith(ESCALATION_PREFIXES):
            calls.append(child)
    return tuple(calls)


def _branch_action(statements: list[ast.stmt]) -> tuple[BehaviorAction, ast.AST] | None:
    for statement in statements:
        if isinstance(statement, ast.Raise):
            exception = _exception_name(statement)
            return BehaviorAction(kind="raise", outcome=exception), statement
        if isinstance(statement, ast.Return):
            expression = ast.unparse(statement.value) if statement.value else "None"
            target = (
                _qualified_name(statement.value.func)
                if isinstance(statement.value, ast.Call)
                else None
            )
            return BehaviorAction(kind="return", target=target, outcome=expression), statement
        calls = _escalation_calls(statement)
        if calls:
            name = _qualified_name(calls[0].func)
            return BehaviorAction(kind="call", target=name), calls[0]
    return None


def _make_behavior(
    *,
    behavior_type: BehaviorType,
    source_type: BehaviorSourceType,
    source_file: str,
    source_symbol: str | None,
    subject: str,
    description: str,
    source: str,
    node: ast.AST,
    evidence_kind: str,
    condition_expressions: tuple[str, ...] = (),
    action: BehaviorAction | None = None,
    arguments: tuple[ToolArgument, ...] = (),
) -> Behavior:
    condition = _condition(condition_expressions)
    action_identity = None
    if action is not None:
        action_identity = ":".join(
            part for part in (action.kind, action.target, action.outcome) if part is not None
        )
    return Behavior(
        behavior_id=_behavior_id(
            source_type=source_type,
            source_file=source_file,
            subject=subject,
            behavior_type=behavior_type,
            condition=condition.normalized_expression if condition else None,
            action=action_identity,
        ),
        description=description,
        behavior_type=behavior_type,
        source_type=source_type,
        source_file=source_file,
        source_symbol=source_symbol,
        subject=subject,
        condition=condition,
        action=action,
        arguments=arguments,
        evidence=(
            _source_evidence(
                source_file=source_file,
                source_symbol=source_symbol,
                source=source,
                node=node,
                kind=evidence_kind,
            ),
        ),
        confidence=ConfidenceLevel.HIGH,
        extractor=EXTRACTOR_NAME,
        content_fingerprint=_fingerprint(node),
    )


def _tool_body_behaviors(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    source_file: str,
    source: str,
    arguments: tuple[ToolArgument, ...],
    source_type: BehaviorSourceType = BehaviorSourceType.PYTHON_TOOL,
) -> list[Behavior]:
    behaviors: list[Behavior] = []
    subject = function.name

    def visit(statements: list[ast.stmt], conditions: tuple[str, ...] = ()) -> None:
        for statement in statements:
            if isinstance(statement, ast.If):
                expression = ast.unparse(statement.test)
                branch = _branch_action(statement.body)
                if branch is not None:
                    action, _ = branch
                    behaviors.append(
                        _make_behavior(
                            behavior_type=BehaviorType.CONDITIONAL_BRANCH,
                            source_type=source_type,
                            source_file=source_file,
                            source_symbol=function.name,
                            subject=subject,
                            description=f"{subject} follows {action.kind} when {expression}",
                            source=source,
                            node=statement,
                            evidence_kind="conditional_branch",
                            condition_expressions=(*conditions, expression),
                            action=action,
                            arguments=arguments,
                        )
                    )
                visit(statement.body, (*conditions, expression))
                if statement.orelse:
                    visit(statement.orelse, (*conditions, f"not ({expression})"))
                continue
            if isinstance(statement, ast.Raise):
                exception = _exception_name(statement)
                behaviors.append(
                    _make_behavior(
                        behavior_type=BehaviorType.TOOL_FAILURE,
                        source_type=source_type,
                        source_file=source_file,
                        source_symbol=function.name,
                        subject=subject,
                        description=f"{subject} may raise {exception}",
                        source=source,
                        node=statement,
                        evidence_kind="raise",
                        condition_expressions=conditions,
                        action=BehaviorAction(kind="raise", outcome=exception),
                        arguments=arguments,
                    )
                )
            if isinstance(statement, ast.Return):
                failure = _failure_return(statement)
                if failure is not None:
                    behaviors.append(
                        _make_behavior(
                            behavior_type=BehaviorType.TOOL_FAILURE,
                            source_type=source_type,
                            source_file=source_file,
                            source_symbol=function.name,
                            subject=subject,
                            description=f"{subject} may return failure outcome {failure}",
                            source=source,
                            node=statement,
                            evidence_kind="failure_return",
                            condition_expressions=conditions,
                            action=BehaviorAction(kind="return", outcome=failure),
                            arguments=arguments,
                        )
                    )
            direct_call_statement = isinstance(
                statement,
                ast.Expr | ast.Assign | ast.AnnAssign | ast.AugAssign | ast.Return,
            )
            for call in _escalation_calls(statement) if direct_call_statement else ():
                name = _qualified_name(call.func) or ast.unparse(call.func)
                behaviors.append(
                    _make_behavior(
                        behavior_type=BehaviorType.ESCALATION,
                        source_type=source_type,
                        source_file=source_file,
                        source_symbol=function.name,
                        subject=subject,
                        description=f"{subject} may call {name}",
                        source=source,
                        node=call,
                        evidence_kind="escalation_call",
                        condition_expressions=conditions,
                        action=BehaviorAction(kind="call", target=name),
                        arguments=arguments,
                    )
                )
            nested_groups: list[list[ast.stmt]] = []
            if isinstance(statement, ast.For | ast.AsyncFor | ast.While):
                nested_groups.extend([statement.body, statement.orelse])
            elif isinstance(statement, ast.With | ast.AsyncWith):
                nested_groups.append(statement.body)
            elif isinstance(statement, ast.Try | ast.TryStar):
                nested_groups.extend([statement.body, statement.orelse, statement.finalbody])
                nested_groups.extend(handler.body for handler in statement.handlers)
            for group in nested_groups:
                visit(group, conditions)

    visit(function.body)
    return behaviors


def _langgraph_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        constructor = _qualified_name(node.value.func)
        if constructor is None or constructor.rsplit(".", maxsplit=1)[-1] != "StateGraph":
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(name for target in targets if (name := _qualified_name(target)) is not None)
    return names


def _workflow_behaviors(tree: ast.Module, source_file: str, source: str) -> list[Behavior]:
    behaviors: list[Behavior] = []
    graph_names = _langgraph_names(tree)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        call_name = _qualified_name(call.func)
        if call_name is None:
            continue
        method_name = call_name.rsplit(".", maxsplit=1)[-1]
        graph_subject = call_name.rsplit(".", maxsplit=1)[0] if "." in call_name else "workflow"
        if graph_subject not in graph_names:
            continue
        if method_name == "add_edge" and len(call.args) >= 2:
            source_node = call.args[0]
            destination_node = call.args[1]
            if not (
                isinstance(source_node, ast.Constant)
                and isinstance(source_node.value, str)
                and isinstance(destination_node, ast.Constant)
                and isinstance(destination_node.value, str)
            ):
                continue
            action = BehaviorAction(kind="transition", target=destination_node.value)
            behaviors.append(
                _make_behavior(
                    behavior_type=BehaviorType.WORKFLOW_TRANSITION,
                    source_type=BehaviorSourceType.LANGGRAPH_WORKFLOW,
                    source_file=source_file,
                    source_symbol=None,
                    subject=graph_subject,
                    description=(
                        f"{graph_subject} transitions from {source_node.value} "
                        f"to {destination_node.value}"
                    ),
                    source=source,
                    node=call,
                    evidence_kind="workflow_edge",
                    condition_expressions=(f"source == {source_node.value!r}",),
                    action=action,
                )
            )
        if method_name != "add_conditional_edges" or len(call.args) < 2:
            continue
        source_node = call.args[0]
        route_node = call.args[1]
        route_map: ast.AST | None = call.args[2] if len(call.args) >= 3 else None
        if route_map is None:
            route_map = next(
                (keyword.value for keyword in call.keywords if keyword.arg == "path_map"), None
            )
        if not (
            isinstance(source_node, ast.Constant)
            and isinstance(source_node.value, str)
            and isinstance(route_map, ast.Dict)
        ):
            continue
        route_name = _qualified_name(route_node) or ast.unparse(route_node)
        for key, value in zip(route_map.keys, route_map.values, strict=True):
            if not (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                continue
            normalized = f"{route_name} == {key.value!r}"
            combined = f"{key.value} {value.value}".lower()
            behavior_type = BehaviorType.CONDITIONAL_BRANCH
            if "fallback" in combined:
                behavior_type = BehaviorType.FALLBACK
            elif any(term in combined for term in ("escalat", "handoff", "human")):
                behavior_type = BehaviorType.ESCALATION
            behaviors.append(
                _make_behavior(
                    behavior_type=behavior_type,
                    source_type=BehaviorSourceType.LANGGRAPH_WORKFLOW,
                    source_file=source_file,
                    source_symbol=None,
                    subject=graph_subject,
                    description=(
                        f"{graph_subject} routes {source_node.value} to {value.value} "
                        f"when {normalized}"
                    ),
                    source=source,
                    node=call,
                    evidence_kind="conditional_workflow_edge",
                    condition_expressions=(normalized,),
                    action=BehaviorAction(kind="transition", target=value.value),
                )
            )
    return behaviors


def extract_python_behaviors(
    root: Path,
    artifact: DiscoveredArtifact,
    *,
    crewai_config_cache: ConfigCache | None = None,
) -> BehaviorExtractionResult:
    """Extract deterministic tool and workflow behaviors from one Python artifact."""
    if _is_test_path(artifact.path):
        return BehaviorExtractionResult(completeness=ScanCompleteness.COMPLETE)
    artifact_path = root / artifact.path
    try:
        source = artifact_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return BehaviorExtractionResult(
            errors=(
                BehaviorExtractionError(
                    code="behavior_source_unreadable",
                    message=f"Unable to read Python artifact: {error}",
                    source_file=artifact.path,
                ),
            ),
            completeness=ScanCompleteness.INCOMPLETE,
        )
    try:
        tree = ast.parse(source, filename=artifact.path)
    except SyntaxError as error:
        return BehaviorExtractionResult(
            warnings=(
                BehaviorExtractionWarning(
                    code="behavior_python_syntax_error",
                    message=error.msg,
                    source_file=artifact.path,
                    line=error.lineno,
                ),
            ),
            completeness=ScanCompleteness.INCOMPLETE,
        )

    pydantic_result = extract_pydantic_ai_from_tree(artifact.path, tree, source)
    behaviors = [*_workflow_behaviors(tree, artifact.path, source), *pydantic_result.behaviors]
    pydantic_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for name in sorted(pydantic_result.claimed_tool_names):
        function = pydantic_functions.get(name)
        if function is not None:
            behaviors.extend(
                _tool_body_behaviors(
                    function,
                    artifact.path,
                    source,
                    _tool_arguments(function),
                    BehaviorSourceType.PYDANTIC_AI_TOOL,
                )
            )
    for function in _tool_functions(tree, pydantic_result.claimed_tool_names):
        arguments = _tool_arguments(function)
        behaviors.append(
            _make_behavior(
                behavior_type=BehaviorType.TOOL_INVOCATION,
                source_type=BehaviorSourceType.PYTHON_TOOL,
                source_file=artifact.path,
                source_symbol=function.name,
                subject=function.name,
                description=f"Tool {function.name} can be invoked",
                source=source,
                node=function,
                evidence_kind="tool_definition",
                action=BehaviorAction(kind="invoke", target=function.name),
                arguments=arguments,
            )
        )
        behaviors.extend(_tool_body_behaviors(function, artifact.path, source, arguments))

    crewai_result = extract_crewai_from_tree(
        root,
        artifact,
        tree,
        source,
        crewai_config_cache if crewai_config_cache is not None else {},
    )
    behaviors.extend(crewai_result.behaviors)
    summaries = tuple(
        FrameworkSummary(framework=name)
        for name, detected in (
            ("CrewAI", crewai_result.detected),
            ("Pydantic AI", pydantic_result.detected),
        )
        if detected
    )
    return BehaviorExtractionResult(
        behaviors=tuple(sorted(behaviors, key=lambda behavior: behavior.behavior_id)),
        warnings=(*crewai_result.warnings, *pydantic_result.warnings),
        errors=crewai_result.errors,
        framework_constructs=(*crewai_result.constructs, *pydantic_result.constructs),
        framework_summaries=summaries,
        completeness=(
            ScanCompleteness.INCOMPLETE
            if crewai_result.warnings or crewai_result.errors or pydantic_result.warnings
            else ScanCompleteness.COMPLETE
        ),
    )


def extract_behaviors(scan_result: ScanResult) -> BehaviorExtractionResult:
    """Extract deterministic behaviors from a repository discovery manifest."""
    if scan_result.completeness is ScanCompleteness.FAILED or scan_result.repository.root is None:
        return BehaviorExtractionResult(
            errors=(
                BehaviorExtractionError(
                    code="discovery_failed",
                    message=(
                        "Behavior extraction could not start because repository discovery failed."
                    ),
                    source_file=scan_result.repository.requested_path,
                ),
            ),
            completeness=ScanCompleteness.FAILED,
        )

    root = Path(scan_result.repository.root)
    behaviors: list[Behavior] = []
    warnings: list[BehaviorExtractionWarning] = []
    errors: list[BehaviorExtractionError] = []
    unavailable_behavior_ids: set[str] = set()
    framework_constructs: list[FrameworkConstruct] = []
    detected_frameworks: set[str] = set()
    crewai_config_cache: ConfigCache = {}
    for artifact in scan_result.artifacts:
        if artifact.artifact_type is not ArtifactType.PYTHON:
            continue
        extracted = extract_python_behaviors(
            root,
            artifact,
            crewai_config_cache=crewai_config_cache,
        )
        behaviors.extend(extracted.behaviors)
        warnings.extend(extracted.warnings)
        errors.extend(extracted.errors)
        unavailable_behavior_ids.update(extracted.unavailable_behavior_ids)
        framework_constructs.extend(extracted.framework_constructs)
        detected_frameworks.update(item.framework for item in extracted.framework_summaries)

    if "CrewAI" in detected_frameworks and not behaviors:
        warnings.append(
            BehaviorExtractionWarning(
                code="crewai_no_supported_behaviors",
                message=(
                    "CrewAI was detected, but no supported CrewAI behaviors could be extracted "
                    "statically."
                ),
                source_file=(
                    framework_constructs[0].source_file
                    if framework_constructs
                    else scan_result.repository.requested_path
                ),
            )
        )

    if "Pydantic AI" in detected_frameworks and not any(
        behavior.source_type
        in {
            BehaviorSourceType.PYDANTIC_AI_AGENT,
            BehaviorSourceType.PYDANTIC_AI_TOOL,
            BehaviorSourceType.PYDANTIC_AI_VALIDATOR,
        }
        for behavior in behaviors
    ):
        warnings.append(
            BehaviorExtractionWarning(
                code="pydantic_ai_no_supported_behaviors",
                message=(
                    "Pydantic AI was detected, but no supported Pydantic AI behaviors could be "
                    "extracted statically."
                ),
                source_file=next(
                    (
                        item.source_file
                        for item in framework_constructs
                        if item.framework == "Pydantic AI"
                    ),
                    scan_result.repository.requested_path,
                ),
            )
        )

    unique_warnings = {
        (warning.source_file, warning.line, warning.code, warning.message): warning
        for warning in warnings
    }
    unique_constructs = {
        (
            construct.framework,
            construct.kind,
            construct.name,
            construct.source_file,
            construct.source_symbol,
        ): construct
        for construct in framework_constructs
    }
    counts: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for construct in unique_constructs.values():
        counts[construct.framework][construct.kind].add(construct.name)
    framework_summaries = tuple(
        FrameworkSummary(
            framework=framework,
            construct_counts={kind: len(names) for kind, names in sorted(kind_counts.items())},
            config_files_referenced=sum(
                construct.framework == framework and construct.kind == "config_file"
                for construct in unique_constructs.values()
            ),
            config_files_parsed=sum(
                construct.framework == framework
                and construct.kind == "config_file"
                and construct.metadata.get("status") == "parsed"
                for construct in unique_constructs.values()
            ),
            config_files_failed=sum(
                construct.framework == framework
                and construct.kind == "config_file"
                and construct.metadata.get("status") == "failed"
                for construct in unique_constructs.values()
            ),
            config_agents=sum(
                construct.framework == framework
                and construct.kind == "agent"
                and construct.metadata.get("configuration_origin") is True
                for construct in unique_constructs.values()
            ),
            config_tasks=sum(
                construct.framework == framework
                and construct.kind == "task"
                and construct.metadata.get("configuration_origin") is True
                for construct in unique_constructs.values()
            ),
            linked_instruction_files=sum(
                construct.framework == framework and construct.kind == "linked_instruction"
                for construct in unique_constructs.values()
            ),
        )
        for framework, kind_counts in sorted(counts.items())
    )
    for framework in sorted(detected_frameworks - counts.keys()):
        framework_summaries += (FrameworkSummary(framework=framework),)

    incomplete = (
        scan_result.completeness is ScanCompleteness.INCOMPLETE
        or bool(unique_warnings)
        or bool(errors)
    )
    return BehaviorExtractionResult(
        behaviors=tuple(
            sorted(
                behaviors,
                key=lambda behavior: (
                    behavior.source_file,
                    behavior.source_symbol or "",
                    behavior.behavior_type.value,
                    behavior.behavior_id,
                ),
            )
        ),
        warnings=tuple(
            sorted(
                unique_warnings.values(),
                key=lambda warning: (warning.source_file, warning.line or 0, warning.code),
            )
        ),
        errors=tuple(sorted(errors, key=lambda error: (error.source_file, error.code))),
        framework_constructs=tuple(
            sorted(
                unique_constructs.values(),
                key=lambda construct: (
                    construct.source_file,
                    construct.kind,
                    construct.name,
                ),
            )
        ),
        framework_summaries=framework_summaries,
        unavailable_behavior_ids=tuple(sorted(unavailable_behavior_ids)),
        completeness=ScanCompleteness.INCOMPLETE if incomplete else ScanCompleteness.COMPLETE,
    )
