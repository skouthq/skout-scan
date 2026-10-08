"""Static extraction for common, documented Pydantic AI constructs."""

import ast
import hashlib
import json
from dataclasses import dataclass
from typing import cast

from pydantic import JsonValue

from agentguard.models import (
    Behavior,
    BehaviorAction,
    BehaviorCondition,
    BehaviorExtractionWarning,
    BehaviorSourceType,
    BehaviorType,
    ConfidenceLevel,
    FrameworkConstruct,
    SourceEvidence,
    ToolArgument,
)


@dataclass(frozen=True)
class PydanticAiExtraction:
    behaviors: tuple[Behavior, ...]
    constructs: tuple[FrameworkConstruct, ...]
    warnings: tuple[BehaviorExtractionWarning, ...]
    claimed_tool_names: frozenset[str]
    agent_names: frozenset[str]
    detected: bool


def _qname(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qname(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _imports(tree: ast.Module) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in {"pydantic_ai", "pydantic_evals", "pydantic_graph"}:
                    names[item.asname or item.name] = item.name
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(("pydantic_ai", "pydantic_evals", "pydantic_graph"))
        ):
            for item in node.names:
                names[item.asname or item.name] = f"{node.module}.{item.name}"
    return names


def _resolve(node: ast.AST, imports: dict[str, str]) -> str | None:
    name = _qname(node)
    if not name:
        return None
    head, *tail = name.split(".")
    base = imports.get(head)
    return ".".join((base, *tail)) if base else None


def _evidence(
    path: str, symbol: str | None, source: str, node: ast.AST, kind: str
) -> SourceEvidence:
    return SourceEvidence(
        kind=kind,
        source_file=path,
        source_symbol=symbol,
        start_line=getattr(node, "lineno", None),
        end_line=getattr(node, "end_lineno", None),
        excerpt=ast.get_source_segment(source, node) or ast.unparse(node),
    )


def _json_literal(node: ast.AST) -> JsonValue | None:
    try:
        value = ast.literal_eval(node)
        return json.loads(json.dumps(value))  # type: ignore[no-any-return]
    except (ValueError, TypeError):
        return None


def _metadata(call: ast.Call) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    if call.args:
        result["model"] = _json_literal(call.args[0]) or ast.unparse(call.args[0])
    for keyword in call.keywords:
        if keyword.arg in {
            "deps_type",
            "output_type",
            "instructions",
            "tools",
            "toolsets",
            "retries",
            "model_settings",
        }:
            result[keyword.arg] = _json_literal(keyword.value) or ast.unparse(keyword.value)
    return result


def _arguments(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ToolArgument, ...]:
    args = [*function.args.posonlyargs, *function.args.args]
    offset = len(args) - len(function.args.defaults)
    result: list[ToolArgument] = []
    for index, argument in enumerate(args):
        default = function.args.defaults[index - offset] if index >= offset else None
        result.append(
            ToolArgument(
                name=argument.arg,
                required=default is None,
                annotation=ast.unparse(argument.annotation) if argument.annotation else None,
                default=ast.unparse(default) if default else None,
            )
        )
    return tuple(result)


def _run_context_type(arguments: list[ast.arg]) -> str | None:
    for argument in arguments:
        annotation = argument.annotation
        if not isinstance(annotation, ast.Subscript):
            continue
        name = _qname(annotation.value)
        if name and name.rsplit(".", 1)[-1] == "RunContext":
            return ast.unparse(annotation.slice)
    return None


def _digest(prefix: str, payload: dict[str, str | None]) -> str:
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _behavior(
    *,
    path: str,
    source: str,
    node: ast.AST,
    source_type: BehaviorSourceType,
    behavior_type: BehaviorType,
    symbol: str,
    subject: str,
    description: str,
    action: BehaviorAction,
    condition: str | None = None,
    arguments: tuple[ToolArgument, ...] = (),
    kind: str,
) -> Behavior:
    condition_model = (
        BehaviorCondition(expression=condition, normalized_expression=condition)
        if condition
        else None
    )
    action_id = ":".join(x for x in (action.kind, action.target, action.outcome) if x)
    identity = {
        "version": "behavior-v1",
        "source_type": source_type.value,
        "source_file": path,
        "subject": subject,
        "behavior_type": behavior_type.value,
        "condition": condition,
        "action": action_id,
    }
    return Behavior(
        behavior_id=_digest("behavior", identity),
        description=description,
        behavior_type=behavior_type,
        source_type=source_type,
        source_file=path,
        source_symbol=symbol,
        subject=subject,
        condition=condition_model,
        action=action,
        arguments=arguments,
        evidence=(_evidence(path, symbol, source, node, kind),),
        confidence=ConfidenceLevel.HIGH,
        extractor="pydantic_ai_ast_v1",
        content_fingerprint=_digest(
            "behavior-content-v1", {"ast": ast.dump(node, include_attributes=False)}
        ),
    )


def _assigned_calls(tree: ast.Module) -> list[tuple[str, ast.Call, ast.AST]]:
    result: list[tuple[str, ast.Call, ast.AST]] = []
    for node in tree.body:
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        if not isinstance(value, ast.Call):
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                result.append((target.id, value, node))
    return result


def extract_pydantic_ai_from_tree(path: str, tree: ast.Module, source: str) -> PydanticAiExtraction:
    """Extract Pydantic AI evidence without importing the target module."""
    imports = _imports(tree)
    detected = any(value.startswith("pydantic_ai") for value in imports.values())
    constructs: list[FrameworkConstruct] = []
    warnings: list[BehaviorExtractionWarning] = []
    behaviors: list[Behavior] = []
    agents: dict[str, ast.Call] = {}
    tool_instances: dict[str, str] = {}
    assigned = _assigned_calls(tree)
    for name, call, node in assigned:
        resolved = _resolve(call.func, imports)
        if resolved == "pydantic_ai.Agent":
            agents[name] = call
            metadata = _metadata(call)
            constructs.append(
                FrameworkConstruct(
                    framework="Pydantic AI",
                    kind="agent",
                    name=name,
                    source_file=path,
                    source_symbol=name,
                    metadata=metadata,
                    evidence=(_evidence(path, name, source, node, "agent"),),
                )
            )
            behaviors.append(
                _behavior(
                    path=path,
                    source=source,
                    node=node,
                    source_type=BehaviorSourceType.PYDANTIC_AI_AGENT,
                    behavior_type=BehaviorType.TOOL_INVOCATION,
                    symbol=name,
                    subject=name,
                    description=f"Pydantic AI agent {name} can be invoked",
                    action=BehaviorAction(kind="invoke", target=name),
                    kind="agent_definition",
                )
            )
            if "output_type" in metadata:
                constructs.append(
                    FrameworkConstruct(
                        framework="Pydantic AI",
                        kind="structured_output",
                        name=f"{name}.output_type",
                        source_file=path,
                        source_symbol=name,
                        metadata={"output_type": metadata["output_type"]},
                        evidence=(_evidence(path, name, source, call, "structured_output"),),
                    )
                )
            if "instructions" in metadata:
                constructs.append(
                    FrameworkConstruct(
                        framework="Pydantic AI",
                        kind="instructions",
                        name=f"{name}.instructions",
                        source_file=path,
                        source_symbol=name,
                        metadata={"value": metadata["instructions"]},
                        evidence=(_evidence(path, name, source, call, "instructions"),),
                    )
                )
            toolsets_keyword = next((kw for kw in call.keywords if kw.arg == "toolsets"), None)
            if toolsets_keyword and isinstance(
                toolsets_keyword.value, (ast.Name, ast.List, ast.Tuple)
            ):
                constructs.append(
                    FrameworkConstruct(
                        framework="Pydantic AI",
                        kind="toolset_reference",
                        name=f"{name}.toolsets",
                        source_file=path,
                        source_symbol=name,
                        metadata={"value": ast.unparse(toolsets_keyword.value)},
                        evidence=(
                            _evidence(
                                path,
                                name,
                                source,
                                toolsets_keyword.value,
                                "toolset_reference",
                            ),
                        ),
                    )
                )
            for key in ("instructions", "toolsets"):
                keyword = next((kw for kw in call.keywords if kw.arg == key), None)
                if keyword and not isinstance(
                    keyword.value, (ast.Constant, ast.Name, ast.List, ast.Tuple)
                ):
                    warnings.append(
                        BehaviorExtractionWarning(
                            code=f"pydantic_ai_dynamic_{key}",
                            message=f"Pydantic AI {key} could not be resolved statically.",
                            source_file=path,
                            line=getattr(keyword.value, "lineno", None),
                        )
                    )
        elif resolved == "pydantic_ai.Tool" and call.args and isinstance(call.args[0], ast.Name):
            tool_instances[name] = call.args[0].id
        elif resolved in {"pydantic_evals.Case", "pydantic_evals.Dataset"}:
            kind = "case" if resolved.endswith(".Case") else "dataset"
            constructs.append(
                FrameworkConstruct(
                    framework="Pydantic Evals",
                    kind=kind,
                    name=name,
                    source_file=path,
                    source_symbol=name,
                    evidence=(_evidence(path, name, source, node, f"pydantic_eval_{kind}"),),
                )
            )
            evaluators = next((kw.value for kw in call.keywords if kw.arg == "evaluators"), None)
            if isinstance(evaluators, (ast.List, ast.Tuple)):
                for index, evaluator in enumerate(evaluators.elts):
                    constructs.append(
                        FrameworkConstruct(
                            framework="Pydantic Evals",
                            kind="evaluator",
                            name=_qname(evaluator) or f"{name}.evaluator[{index}]",
                            source_file=path,
                            source_symbol=name,
                            evidence=(
                                _evidence(path, name, source, evaluator, "pydantic_evaluator"),
                            ),
                        )
                    )

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    claimed: set[str] = set()
    registered: list[tuple[str, str, str, ast.AST]] = []
    for function in functions.values():
        for decorator in function.decorator_list:
            decorator_name = _qname(
                decorator.func if isinstance(decorator, ast.Call) else decorator
            )
            if decorator_name and "." in decorator_name:
                receiver, method = decorator_name.rsplit(".", 1)
                if receiver in agents and method in {"tool", "tool_plain"}:
                    registered.append((function.name, receiver, method, function))
                elif receiver in agents and method in {"instructions", "output_validator"}:
                    callback_arguments = [
                        *function.args.posonlyargs,
                        *function.args.args,
                    ]
                    constructs.append(
                        FrameworkConstruct(
                            framework="Pydantic AI",
                            kind="instruction_function"
                            if method == "instructions"
                            else "output_validator",
                            name=function.name,
                            source_file=path,
                            source_symbol=function.name,
                            metadata={
                                "agent": receiver,
                                "async": isinstance(function, ast.AsyncFunctionDef),
                                "dependency_type": _run_context_type(callback_arguments),
                                "dependency_accesses": cast(
                                    JsonValue,
                                    sorted(
                                        {
                                            _qname(item) or ""
                                            for item in ast.walk(function)
                                            if isinstance(item, ast.Attribute)
                                            and (_qname(item) or "").startswith("ctx.deps")
                                        }
                                    ),
                                ),
                                "returns": cast(
                                    JsonValue,
                                    [
                                        ast.unparse(item.value)
                                        for item in ast.walk(function)
                                        if isinstance(item, ast.Return) and item.value is not None
                                    ],
                                ),
                            },
                            evidence=(_evidence(path, function.name, source, function, method),),
                        )
                    )
                    if method == "output_validator":
                        for branch in (
                            item for item in ast.walk(function) if isinstance(item, ast.If)
                        ):
                            for raised in (
                                item
                                for item in ast.walk(ast.Module(body=branch.body, type_ignores=[]))
                                if isinstance(item, ast.Raise) and item.exc is not None
                            ):
                                exc = (
                                    raised.exc.func
                                    if isinstance(raised.exc, ast.Call)
                                    else raised.exc
                                )
                                if (
                                    exc is not None
                                    and _resolve(exc, imports) == "pydantic_ai.ModelRetry"
                                ):
                                    condition = ast.unparse(branch.test)
                                    action = BehaviorAction(kind="raise", outcome="ModelRetry")
                                    for behavior_type in (
                                        BehaviorType.CONDITIONAL_BRANCH,
                                        BehaviorType.TOOL_FAILURE,
                                    ):
                                        behaviors.append(
                                            _behavior(
                                                path=path,
                                                source=source,
                                                node=branch
                                                if behavior_type is BehaviorType.CONDITIONAL_BRANCH
                                                else raised,
                                                source_type=BehaviorSourceType.PYDANTIC_AI_VALIDATOR,
                                                behavior_type=behavior_type,
                                                symbol=function.name,
                                                subject=function.name,
                                                description=f"{function.name} raises ModelRetry",
                                                action=action,
                                                condition=condition,
                                                arguments=_arguments(function),
                                                kind="model_retry",
                                            )
                                        )

    for agent_name, call in agents.items():
        tools_kw = next((kw.value for kw in call.keywords if kw.arg == "tools"), None)
        if tools_kw is None:
            continue
        if not isinstance(tools_kw, (ast.List, ast.Tuple)):
            warnings.append(
                BehaviorExtractionWarning(
                    code="pydantic_ai_dynamic_tools",
                    message="Pydantic AI tools collection could not be resolved statically.",
                    source_file=path,
                    line=getattr(tools_kw, "lineno", None),
                )
            )
            continue
        for item in tools_kw.elts:
            if isinstance(item, ast.Name):
                tool_name = tool_instances.get(item.id, item.id)
            elif (
                isinstance(item, ast.Call)
                and _resolve(item.func, imports) == "pydantic_ai.Tool"
                and item.args
                and isinstance(item.args[0], ast.Name)
            ):
                tool_name = item.args[0].id
            else:
                warnings.append(
                    BehaviorExtractionWarning(
                        code="pydantic_ai_dynamic_tool",
                        message="A Pydantic AI tool entry could not be resolved statically.",
                        source_file=path,
                        line=getattr(item, "lineno", None),
                    )
                )
                continue
            registered.append((tool_name, agent_name, "constructor", item))

    for tool_name, agent_name, registration, node in registered:
        if tool_name in claimed:
            continue
        claimed.add(tool_name)
        registered_function = functions.get(tool_name)
        evidence_node = registered_function or node
        function_arguments = (
            [*registered_function.args.posonlyargs, *registered_function.args.args]
            if registered_function is not None
            else []
        )
        function_nodes = ast.walk(registered_function) if registered_function is not None else ()
        constructs.append(
            FrameworkConstruct(
                framework="Pydantic AI",
                kind="tool_plain" if registration == "tool_plain" else "tool",
                name=tool_name,
                source_file=path,
                source_symbol=tool_name,
                metadata={
                    "agent": agent_name,
                    "registration": registration,
                    "registered_symbol": ast.unparse(node),
                    "normalized_symbol": tool_name,
                    "run_context": any(
                        arg.annotation and "RunContext" in ast.unparse(arg.annotation)
                        for arg in function_arguments
                    ),
                    "dependency_type": _run_context_type(function_arguments),
                    "dependency_accesses": cast(
                        JsonValue,
                        sorted(
                            {
                                _qname(item) or ""
                                for item in function_nodes
                                if isinstance(item, ast.Attribute)
                                and (_qname(item) or "").startswith("ctx.deps")
                            }
                        ),
                    ),
                },
                evidence=(_evidence(path, tool_name, source, node, "tool_registration"),),
            )
        )
        behaviors.append(
            _behavior(
                path=path,
                source=source,
                node=evidence_node,
                source_type=BehaviorSourceType.PYDANTIC_AI_TOOL,
                behavior_type=BehaviorType.TOOL_INVOCATION,
                symbol=tool_name,
                subject=tool_name,
                description=f"Pydantic AI tool {tool_name} can be invoked by {agent_name}",
                action=BehaviorAction(kind="invoke", target=tool_name),
                arguments=_arguments(registered_function) if registered_function else (),
                kind="tool_definition",
            )
        )

    if any(value.startswith("pydantic_graph") for value in imports.values()):
        constructs.append(
            FrameworkConstruct(
                framework="Pydantic Graph", kind="detected", name="pydantic_graph", source_file=path
            )
        )
    return PydanticAiExtraction(
        tuple(behaviors),
        tuple(constructs),
        tuple(warnings),
        frozenset(claimed),
        frozenset(agents),
        detected,
    )
