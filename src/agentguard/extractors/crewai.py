"""Deterministic static extraction for common CrewAI project patterns."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import JsonValue

from agentguard.models import (
    Behavior,
    BehaviorAction,
    BehaviorExtractionError,
    BehaviorExtractionWarning,
    BehaviorSourceType,
    BehaviorType,
    ConfidenceLevel,
    DiscoveredArtifact,
    FrameworkConstruct,
    SourceEvidence,
    ToolArgument,
)

EXTRACTOR_NAME = "crewai_ast_v1"
BEHAVIOR_ID_VERSION = "crewai-behavior-v1"
CREWAI_FRAMEWORK = "CrewAI"
CREWAI_CONSTRUCT_NAMES = {"Agent", "Task", "Crew"}
CREWAI_PROJECT_DECORATORS = {
    "CrewBase",
    "agent",
    "task",
    "crew",
    "before_kickoff",
    "after_kickoff",
}
CREWAI_FLOW_DECORATORS = {"start", "listen", "router"}
AGENT_METADATA_FIELDS = {
    "role",
    "goal",
    "backstory",
    "allow_delegation",
    "verbose",
    "memory",
    "max_iter",
    "max_rpm",
    "reasoning",
}
TASK_METADATA_FIELDS = {
    "description",
    "expected_output",
    "agent",
    "context",
    "tools",
    "async_execution",
    "human_input",
    "output_file",
    "output_json",
    "output_pydantic",
}
CREW_METADATA_FIELDS = {
    "agents",
    "tasks",
    "process",
    "manager_agent",
    "manager_llm",
    "planning",
    "memory",
    "verbose",
}

ConfigData = dict[str, JsonValue]
ConfigCache = dict[Path, tuple[ConfigData | None, BehaviorExtractionWarning | None]]


@dataclass(frozen=True)
class CrewAIArtifactResult:
    """CrewAI evidence extracted from one already-parsed Python artifact."""

    detected: bool = False
    behaviors: tuple[Behavior, ...] = ()
    constructs: tuple[FrameworkConstruct, ...] = ()
    warnings: tuple[BehaviorExtractionWarning, ...] = ()
    errors: tuple[BehaviorExtractionError, ...] = ()


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _import_map(tree: ast.Module) -> tuple[dict[str, str], bool]:
    imports: dict[str, str] = {}
    detected = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "crewai" or alias.name.startswith("crewai."):
                    detected = True
                    local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                    imports[local_name] = alias.name if alias.asname else local_name
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == "crewai" or node.module.startswith("crewai."))
        ):
            detected = True
            for alias in node.names:
                if alias.name == "*":
                    continue
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return imports, detected


def _resolved_name(node: ast.AST, imports: dict[str, str]) -> str | None:
    name = _qualified_name(node)
    if name is None:
        return None
    first, *remaining = name.split(".")
    mapped = imports.get(first)
    if mapped is None:
        return name
    return ".".join((mapped, *remaining))


def _is_crewai_name(name: str | None, final_name: str) -> bool:
    return bool(
        name and name.startswith("crewai.") and name.rsplit(".", maxsplit=1)[-1] == final_name
    )


def _decorator_name(node: ast.expr, imports: dict[str, str]) -> str | None:
    target = node.func if isinstance(node, ast.Call) else node
    return _resolved_name(target, imports)


def _has_decorator(decorators: list[ast.expr], imports: dict[str, str], expected: str) -> bool:
    return any(_is_crewai_name(_decorator_name(item, imports), expected) for item in decorators)


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


def _json_value(value: Any) -> JsonValue:
    normalized: Any = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return cast(JsonValue, normalized)


def _static_value(node: ast.AST) -> JsonValue:
    try:
        return _json_value(ast.literal_eval(node))
    except (ValueError, TypeError):
        if isinstance(node, ast.List | ast.Tuple | ast.Set):
            return [_static_value(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            values: dict[str, JsonValue] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    values[key.value] = _static_value(value)
            return values
        return ast.unparse(node)


def _keyword_map(call: ast.Call) -> dict[str, ast.expr]:
    return {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None}


def _metadata(call: ast.Call, fields: set[str]) -> dict[str, JsonValue]:
    keywords = _keyword_map(call)
    return {field: _static_value(keywords[field]) for field in sorted(fields & keywords.keys())}


def _reference(node: ast.AST) -> str | None:
    target = node.func if isinstance(node, ast.Call) else node
    name = _qualified_name(target)
    if name is None:
        return None
    return name.removeprefix("self.").rsplit(".", maxsplit=1)[-1]


def _reference_list(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, ast.List | ast.Tuple | ast.Set):
        return None
    references: list[str] = []
    for item in node.elts:
        name = _reference(item)
        if name is None:
            return None
        references.append(name)
    return tuple(references)


def _config_reference(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    container = _qualified_name(node.value)
    if container not in {
        "self.agents_config",
        "self.tasks_config",
        "agents_config",
        "tasks_config",
    }:
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value
    return None


def _digest(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _make_behavior(
    *,
    behavior_type: BehaviorType,
    source_type: BehaviorSourceType,
    source_file: str,
    source_symbol: str | None,
    subject: str,
    description: str,
    action: BehaviorAction,
    evidence: SourceEvidence,
    fingerprint_node: ast.AST | None = None,
    arguments: tuple[ToolArgument, ...] = (),
) -> Behavior:
    identity = json.dumps(
        {
            "version": BEHAVIOR_ID_VERSION,
            "source_type": source_type.value,
            "source_file": source_file,
            "source_symbol": source_symbol,
            "subject": subject,
            "behavior_type": behavior_type.value,
            "action": action.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    fingerprint_source = (
        ast.dump(fingerprint_node, annotate_fields=True, include_attributes=False)
        if fingerprint_node is not None
        else evidence.excerpt
    )
    return Behavior(
        behavior_id=_digest("behavior", identity),
        description=description,
        behavior_type=behavior_type,
        source_type=source_type,
        source_file=source_file,
        source_symbol=source_symbol,
        subject=subject,
        action=action,
        arguments=arguments,
        evidence=(evidence,),
        confidence=ConfidenceLevel.HIGH,
        extractor=EXTRACTOR_NAME,
        content_fingerprint=_digest("crewai-content-v1", fingerprint_source),
    )


def _tool_arguments(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ToolArgument, ...]:
    positional = [*function.args.posonlyargs, *function.args.args]
    defaults_at = len(positional) - len(function.args.defaults)
    arguments: list[ToolArgument] = []
    for index, argument in enumerate(positional):
        if argument.arg in {"self", "cls"}:
            continue
        default_node = function.args.defaults[index - defaults_at] if index >= defaults_at else None
        arguments.append(
            ToolArgument(
                name=argument.arg,
                required=default_node is None,
                annotation=ast.unparse(argument.annotation) if argument.annotation else None,
                default=ast.unparse(default_node) if default_node else None,
            )
        )
    return tuple(arguments)


def _construct(
    *,
    kind: str,
    name: str,
    source_file: str,
    source_symbol: str | None,
    metadata: dict[str, JsonValue],
    evidence: SourceEvidence,
) -> FrameworkConstruct:
    return FrameworkConstruct(
        framework=CREWAI_FRAMEWORK,
        kind=kind,
        name=name,
        source_file=source_file,
        source_symbol=source_symbol,
        metadata=metadata,
        evidence=(evidence,),
    )


def _load_config(
    root: Path,
    source_file: str,
    relative_config: str,
    cache: ConfigCache,
) -> tuple[ConfigData | None, BehaviorExtractionWarning | None]:
    config_path = (root / Path(source_file).parent / relative_config).resolve()
    try:
        config_path.relative_to(root.resolve())
    except ValueError:
        return None, BehaviorExtractionWarning(
            code="crewai_config_outside_repository",
            message="CrewAI config path resolves outside the scanned repository.",
            source_file=source_file,
        )
    if config_path in cache:
        return cache[config_path]

    config_relative = config_path.relative_to(root.resolve()).as_posix()
    if config_path.suffix.lower() == ".jsonc":
        result = (
            None,
            BehaviorExtractionWarning(
                code="crewai_jsonc_unsupported",
                message="Statically linked CrewAI JSONC configuration is not supported.",
                source_file=config_relative,
            ),
        )
        cache[config_path] = result
        return result
    if config_path.suffix.lower() not in {".yaml", ".yml", ".json"}:
        result = (
            None,
            BehaviorExtractionWarning(
                code="crewai_config_format_unsupported",
                message="Statically linked CrewAI config must be YAML or plain JSON.",
                source_file=config_relative,
            ),
        )
        cache[config_path] = result
        return result
    try:
        raw = config_path.read_text(encoding="utf-8")
        parsed: Any = (
            json.loads(raw) if config_path.suffix.lower() == ".json" else yaml.safe_load(raw)
        )
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as error:
        result = (
            None,
            BehaviorExtractionWarning(
                code="crewai_config_unreadable",
                message=f"Unable to parse statically linked CrewAI config: {error}",
                source_file=config_relative,
            ),
        )
        cache[config_path] = result
        return result
    if not isinstance(parsed, dict):
        result = (
            None,
            BehaviorExtractionWarning(
                code="crewai_config_invalid",
                message="CrewAI config must contain a top-level object mapping names to config.",
                source_file=config_relative,
            ),
        )
        cache[config_path] = result
        return result
    data = cast(ConfigData, _json_value(parsed))
    success_result: tuple[ConfigData | None, BehaviorExtractionWarning | None] = (data, None)
    cache[config_path] = success_result
    return success_result


def _config_constructs(
    *,
    root: Path,
    source_file: str,
    config_kind: str,
    relative_config: str,
    cache: ConfigCache,
) -> tuple[list[FrameworkConstruct], list[Behavior], list[BehaviorExtractionWarning]]:
    data, warning = _load_config(root, source_file, relative_config, cache)
    if warning is not None:
        return [], [], [warning]
    if data is None:
        return [], [], []
    config_path = (root / Path(source_file).parent / relative_config).resolve()
    config_relative = config_path.relative_to(root.resolve()).as_posix()
    values = data.get(f"{config_kind}s")
    entries = values if isinstance(values, dict) else data
    constructs: list[FrameworkConstruct] = []
    behaviors: list[Behavior] = []
    for name, raw_metadata in sorted(entries.items()):
        if not isinstance(raw_metadata, dict):
            continue
        metadata = raw_metadata
        evidence = SourceEvidence(
            kind=f"crewai_{config_kind}_config",
            source_file=config_relative,
            source_symbol=name,
            excerpt=f"{name}: {json.dumps(metadata, ensure_ascii=False, sort_keys=True)}",
        )
        constructs.append(
            _construct(
                kind=config_kind,
                name=name,
                source_file=config_relative,
                source_symbol=name,
                metadata=metadata,
                evidence=evidence,
            )
        )
        tools = metadata.get("tools")
        if isinstance(tools, list) and all(isinstance(item, str) for item in tools):
            for tool_name in sorted(cast(list[str], tools)):
                behaviors.append(
                    _make_behavior(
                        behavior_type=BehaviorType.TOOL_INVOCATION,
                        source_type=BehaviorSourceType.CREWAI_TOOL,
                        source_file=config_relative,
                        source_symbol=name,
                        subject=tool_name,
                        description=f"CrewAI {config_kind} {name} can invoke tool {tool_name}",
                        action=BehaviorAction(kind="invoke", target=tool_name),
                        evidence=evidence,
                    )
                )
        context = metadata.get("context")
        if (
            config_kind == "task"
            and isinstance(context, list)
            and all(isinstance(item, str) for item in context)
        ):
            for dependency in sorted(cast(list[str], context)):
                behaviors.append(
                    _make_behavior(
                        behavior_type=BehaviorType.WORKFLOW_TRANSITION,
                        source_type=BehaviorSourceType.CREWAI_WORKFLOW,
                        source_file=config_relative,
                        source_symbol=name,
                        subject=dependency,
                        description=f"CrewAI task {name} depends on {dependency}",
                        action=BehaviorAction(kind="transition", target=name),
                        evidence=evidence,
                    )
                )
    return constructs, behaviors, []


def _linked_config(statement: ast.stmt) -> tuple[str, ast.expr] | None:
    if not isinstance(statement, ast.Assign | ast.AnnAssign):
        return None
    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
    value = statement.value
    if value is None:
        return None
    target_names = [_qualified_name(target) for target in targets]
    if "agents_config" in target_names:
        return "agent", value
    if "tasks_config" in target_names:
        return "task", value
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _enclosing_function(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
            return current
        current = parents.get(current)
    return None


def _enclosing_class(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.ClassDef | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.ClassDef):
            return current
        current = parents.get(current)
    return None


def _call_symbol(call: ast.Call, parents: dict[ast.AST, ast.AST], kind: str) -> str:
    parent = parents.get(call)
    if isinstance(parent, ast.Assign) and parent.value is call:
        target = _qualified_name(parent.targets[0])
        if target:
            return target.removeprefix("self.")
    if isinstance(parent, ast.AnnAssign) and parent.value is call:
        target = _qualified_name(parent.target)
        if target:
            return target.removeprefix("self.")
    function = _enclosing_function(call, parents)
    if function is not None:
        return function.name
    return f"{kind}_line_{call.lineno}"


def _decorated_methods(
    crew_class: ast.ClassDef, imports: dict[str, str], decorator: str
) -> tuple[str, ...]:
    return tuple(
        child.name
        for child in crew_class.body
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        and _has_decorator(child.decorator_list, imports, decorator)
    )


def _attached_tools(
    *,
    owner_kind: str,
    owner_name: str,
    call: ast.Call,
    source_file: str,
    source: str,
) -> tuple[list[Behavior], list[BehaviorExtractionWarning]]:
    tool_node = _keyword_map(call).get("tools")
    if tool_node is None:
        return [], []
    tools = _reference_list(tool_node)
    if tools is None:
        return [], [
            BehaviorExtractionWarning(
                code="crewai_dynamic_tools_unsupported",
                message=(
                    f"Dynamic tools attached to CrewAI {owner_kind} {owner_name} were not inferred."
                ),
                source_file=source_file,
                line=getattr(tool_node, "lineno", None),
            )
        ]
    evidence = _evidence(
        kind=f"crewai_{owner_kind}_tools",
        source_file=source_file,
        source_symbol=owner_name,
        source=source,
        node=tool_node,
    )
    return [
        _make_behavior(
            behavior_type=BehaviorType.TOOL_INVOCATION,
            source_type=BehaviorSourceType.CREWAI_TOOL,
            source_file=source_file,
            source_symbol=owner_name,
            subject=tool,
            description=f"CrewAI {owner_kind} {owner_name} can invoke tool {tool}",
            action=BehaviorAction(kind="invoke", target=tool),
            evidence=evidence,
            fingerprint_node=tool_node,
        )
        for tool in tools
    ], []


def _task_context_behaviors(
    *,
    task_name: str,
    call: ast.Call,
    source_file: str,
    source: str,
) -> tuple[list[Behavior], list[BehaviorExtractionWarning]]:
    context_node = _keyword_map(call).get("context")
    if context_node is None:
        return [], []
    dependencies = _reference_list(context_node)
    if dependencies is None:
        return [], [
            BehaviorExtractionWarning(
                code="crewai_dynamic_task_context_unsupported",
                message=f"Dynamic context for CrewAI task {task_name} was not inferred.",
                source_file=source_file,
                line=getattr(context_node, "lineno", None),
            )
        ]
    evidence = _evidence(
        kind="crewai_task_context",
        source_file=source_file,
        source_symbol=task_name,
        source=source,
        node=context_node,
    )
    return [
        _make_behavior(
            behavior_type=BehaviorType.WORKFLOW_TRANSITION,
            source_type=BehaviorSourceType.CREWAI_WORKFLOW,
            source_file=source_file,
            source_symbol=task_name,
            subject=dependency,
            description=f"CrewAI task {task_name} depends on {dependency}",
            action=BehaviorAction(kind="transition", target=task_name),
            evidence=evidence,
            fingerprint_node=context_node,
        )
        for dependency in dependencies
    ], []


def _crew_task_order(
    *,
    crew_name: str,
    call: ast.Call,
    crew_class: ast.ClassDef | None,
    imports: dict[str, str],
    source_file: str,
    source: str,
) -> tuple[list[Behavior], list[BehaviorExtractionWarning]]:
    keywords = _keyword_map(call)
    process_node = keywords.get("process")
    process = _resolved_name(process_node, imports) if process_node is not None else None
    if not process or not process.endswith("Process.sequential"):
        return [], []
    tasks_node = keywords.get("tasks")
    tasks = _reference_list(tasks_node) if tasks_node is not None else None
    if (
        tasks is None
        and crew_class is not None
        and tasks_node is not None
        and _qualified_name(tasks_node) == "self.tasks"
    ):
        tasks = _decorated_methods(crew_class, imports, "task")
    if tasks is None:
        return [], [
            BehaviorExtractionWarning(
                code="crewai_dynamic_task_order_unsupported",
                message=f"Sequential CrewAI crew {crew_name} uses a dynamic task list.",
                source_file=source_file,
                line=getattr(tasks_node or call, "lineno", None),
            )
        ]
    evidence = _evidence(
        kind="crewai_sequential_tasks",
        source_file=source_file,
        source_symbol=crew_name,
        source=source,
        node=tasks_node or call,
    )
    return [
        _make_behavior(
            behavior_type=BehaviorType.WORKFLOW_TRANSITION,
            source_type=BehaviorSourceType.CREWAI_WORKFLOW,
            source_file=source_file,
            source_symbol=crew_name,
            subject=source_task,
            description=f"CrewAI crew {crew_name} runs {target_task} after {source_task}",
            action=BehaviorAction(kind="transition", target=target_task),
            evidence=evidence,
            fingerprint_node=tasks_node or call,
        )
        for source_task, target_task in zip(tasks, tasks[1:], strict=False)
    ], []


def _flow_constructs(
    *,
    tree: ast.Module,
    imports: dict[str, str],
    source_file: str,
    source: str,
) -> tuple[list[FrameworkConstruct], list[Behavior], list[BehaviorExtractionWarning]]:
    constructs: list[FrameworkConstruct] = []
    behaviors: list[Behavior] = []
    warnings: list[BehaviorExtractionWarning] = []
    for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        if not any(
            _is_crewai_name(_resolved_name(base, imports), "Flow") for base in class_node.bases
        ):
            continue
        class_evidence = _evidence(
            kind="crewai_flow",
            source_file=source_file,
            source_symbol=class_node.name,
            source=source,
            node=class_node,
        )
        constructs.append(
            _construct(
                kind="flow",
                name=class_node.name,
                source_file=source_file,
                source_symbol=class_node.name,
                metadata={},
                evidence=class_evidence,
            )
        )
        for method in (
            item
            for item in class_node.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        ):
            for decorator in method.decorator_list:
                decorator_name = _decorator_name(decorator, imports)
                final = decorator_name.rsplit(".", maxsplit=1)[-1] if decorator_name else ""
                if not decorator_name or not decorator_name.startswith("crewai."):
                    continue
                if final not in CREWAI_FLOW_DECORATORS:
                    continue
                metadata: dict[str, JsonValue] = {"decorator": final}
                construct_evidence = _evidence(
                    kind=f"crewai_flow_{final}",
                    source_file=source_file,
                    source_symbol=method.name,
                    source=source,
                    node=decorator,
                )
                constructs.append(
                    _construct(
                        kind=f"flow_{final}",
                        name=method.name,
                        source_file=source_file,
                        source_symbol=method.name,
                        metadata=metadata,
                        evidence=construct_evidence,
                    )
                )
                if final == "start" and (not isinstance(decorator, ast.Call) or not decorator.args):
                    continue
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    warnings.append(
                        BehaviorExtractionWarning(
                            code="crewai_dynamic_flow_route_unsupported",
                            message=f"CrewAI flow decorator @{final} has no static source.",
                            source_file=source_file,
                            line=getattr(decorator, "lineno", None),
                        )
                    )
                    continue
                source_step = _reference(decorator.args[0])
                if source_step is None and isinstance(decorator.args[0], ast.Constant):
                    value = decorator.args[0].value
                    source_step = value if isinstance(value, str) else None
                if source_step is None:
                    warnings.append(
                        BehaviorExtractionWarning(
                            code="crewai_dynamic_flow_route_unsupported",
                            message=(
                                f"CrewAI flow @{final} source could not be resolved statically."
                            ),
                            source_file=source_file,
                            line=getattr(decorator, "lineno", None),
                        )
                    )
                    continue
                behaviors.append(
                    _make_behavior(
                        behavior_type=BehaviorType.WORKFLOW_TRANSITION,
                        source_type=BehaviorSourceType.CREWAI_WORKFLOW,
                        source_file=source_file,
                        source_symbol=class_node.name,
                        subject=source_step,
                        description=(
                            f"CrewAI flow {class_node.name} routes {source_step} to {method.name}"
                        ),
                        action=BehaviorAction(kind="transition", target=method.name),
                        evidence=construct_evidence,
                        fingerprint_node=decorator,
                    )
                )
                if final == "router":
                    for return_node in (
                        node for node in ast.walk(method) if isinstance(node, ast.Return)
                    ):
                        if isinstance(return_node.value, ast.Constant) and isinstance(
                            return_node.value.value, str
                        ):
                            target = return_node.value.value
                            return_evidence = _evidence(
                                kind="crewai_flow_router_target",
                                source_file=source_file,
                                source_symbol=method.name,
                                source=source,
                                node=return_node,
                            )
                            behaviors.append(
                                _make_behavior(
                                    behavior_type=BehaviorType.WORKFLOW_TRANSITION,
                                    source_type=BehaviorSourceType.CREWAI_WORKFLOW,
                                    source_file=source_file,
                                    source_symbol=class_node.name,
                                    subject=method.name,
                                    description=(
                                        f"CrewAI flow router {method.name} can route to {target}"
                                    ),
                                    action=BehaviorAction(kind="transition", target=target),
                                    evidence=return_evidence,
                                    fingerprint_node=return_node,
                                )
                            )
    return constructs, behaviors, warnings


def extract_crewai_from_tree(
    root: Path,
    artifact: DiscoveredArtifact,
    tree: ast.Module,
    source: str,
    config_cache: ConfigCache,
) -> CrewAIArtifactResult:
    """Extract common CrewAI constructs without importing or executing target code."""
    imports, detected = _import_map(tree)
    if not detected:
        return CrewAIArtifactResult()

    source_file = artifact.path
    parents = _parent_map(tree)
    constructs: list[FrameworkConstruct] = []
    behaviors: list[Behavior] = []
    warnings: list[BehaviorExtractionWarning] = []

    crew_base_classes = {
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and _has_decorator(node.decorator_list, imports, "CrewBase")
    }
    linked_config_statements = list(tree.body)
    for class_node in crew_base_classes:
        linked_config_statements.extend(class_node.body)
    for statement in linked_config_statements:
        linked_config = _linked_config(statement)
        if linked_config is None:
            continue
        config_kind, value = linked_config
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            warnings.append(
                BehaviorExtractionWarning(
                    code="crewai_dynamic_config_path_unsupported",
                    message=f"CrewAI {config_kind} config path is not a string literal.",
                    source_file=source_file,
                    line=getattr(value, "lineno", None),
                )
            )
            continue
        config_constructs, config_behaviors, config_warnings = _config_constructs(
            root=root,
            source_file=source_file,
            config_kind=config_kind,
            relative_config=value.value,
            cache=config_cache,
        )
        constructs.extend(config_constructs)
        behaviors.extend(config_behaviors)
        warnings.extend(config_warnings)

    for class_node in sorted(crew_base_classes, key=lambda item: item.name):
        constructs.append(
            _construct(
                kind="crew_base",
                name=class_node.name,
                source_file=source_file,
                source_symbol=class_node.name,
                metadata={},
                evidence=_evidence(
                    kind="crewai_crew_base",
                    source_file=source_file,
                    source_symbol=class_node.name,
                    source=source,
                    node=class_node,
                ),
            )
        )
        for method in (
            item
            for item in class_node.body
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
        ):
            for decorator in CREWAI_PROJECT_DECORATORS - {"CrewBase"}:
                if _has_decorator(method.decorator_list, imports, decorator):
                    constructs.append(
                        _construct(
                            kind=f"{decorator}_hook"
                            if decorator.endswith("kickoff")
                            else decorator,
                            name=method.name,
                            source_file=source_file,
                            source_symbol=method.name,
                            metadata={"decorator": decorator},
                            evidence=_evidence(
                                kind=f"crewai_{decorator}",
                                source_file=source_file,
                                source_symbol=method.name,
                                source=source,
                                node=method,
                            ),
                        )
                    )

    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        if not any(
            _is_crewai_name(_resolved_name(base, imports), "BaseTool") for base in class_node.bases
        ):
            continue
        run_method = next(
            (
                item
                for item in class_node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                and item.name in {"_run", "run"}
            ),
            None,
        )
        evidence = _evidence(
            kind="crewai_base_tool",
            source_file=source_file,
            source_symbol=class_node.name,
            source=source,
            node=class_node,
        )
        constructs.append(
            _construct(
                kind="tool",
                name=class_node.name,
                source_file=source_file,
                source_symbol=class_node.name,
                metadata={"style": "BaseTool"},
                evidence=evidence,
            )
        )
        behaviors.append(
            _make_behavior(
                behavior_type=BehaviorType.TOOL_INVOCATION,
                source_type=BehaviorSourceType.CREWAI_TOOL,
                source_file=source_file,
                source_symbol=class_node.name,
                subject=class_node.name,
                description=f"CrewAI tool {class_node.name} can be invoked",
                action=BehaviorAction(kind="invoke", target=class_node.name),
                evidence=evidence,
                fingerprint_node=class_node,
                arguments=_tool_arguments(run_method) if run_method is not None else (),
            )
        )

    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ):
        if not _has_decorator(function.decorator_list, imports, "tool"):
            continue
        constructs.append(
            _construct(
                kind="tool",
                name=function.name,
                source_file=source_file,
                source_symbol=function.name,
                metadata={"style": "decorator"},
                evidence=_evidence(
                    kind="crewai_tool_decorator",
                    source_file=source_file,
                    source_symbol=function.name,
                    source=source,
                    node=function,
                ),
            )
        )

    config_entries: dict[str, dict[str, JsonValue]] = {}
    for construct in constructs:
        if construct.kind in {"agent", "task"}:
            config_entries.setdefault(construct.name, construct.metadata)

    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        resolved = _resolved_name(call.func, imports)
        final = resolved.rsplit(".", maxsplit=1)[-1] if resolved else ""
        if (
            not resolved
            or not resolved.startswith("crewai.")
            or final not in CREWAI_CONSTRUCT_NAMES
        ):
            continue
        kind = final.casefold()
        name = _call_symbol(call, parents, kind)
        fields = (
            AGENT_METADATA_FIELDS
            if final == "Agent"
            else TASK_METADATA_FIELDS
            if final == "Task"
            else CREW_METADATA_FIELDS
        )
        metadata = _metadata(call, fields)
        config_node = _keyword_map(call).get("config")
        if config_node is not None:
            reference = _config_reference(config_node)
            if reference is not None:
                metadata["config_reference"] = reference
                metadata.update(config_entries.get(reference, {}))
            else:
                metadata["config"] = _static_value(config_node)
        evidence = _evidence(
            kind=f"crewai_{kind}",
            source_file=source_file,
            source_symbol=name,
            source=source,
            node=call,
        )
        constructs.append(
            _construct(
                kind=kind,
                name=name,
                source_file=source_file,
                source_symbol=name,
                metadata=metadata,
                evidence=evidence,
            )
        )
        attached, attached_warnings = _attached_tools(
            owner_kind=kind,
            owner_name=name,
            call=call,
            source_file=source_file,
            source=source,
        )
        behaviors.extend(attached)
        warnings.extend(attached_warnings)
        if final == "Task":
            context_behaviors, context_warnings = _task_context_behaviors(
                task_name=name,
                call=call,
                source_file=source_file,
                source=source,
            )
            behaviors.extend(context_behaviors)
            warnings.extend(context_warnings)
        elif final == "Crew":
            order_behaviors, order_warnings = _crew_task_order(
                crew_name=name,
                call=call,
                crew_class=_enclosing_class(call, parents),
                imports=imports,
                source_file=source_file,
                source=source,
            )
            behaviors.extend(order_behaviors)
            warnings.extend(order_warnings)

    flow_constructs, flow_behaviors, flow_warnings = _flow_constructs(
        tree=tree,
        imports=imports,
        source_file=source_file,
        source=source,
    )
    constructs.extend(flow_constructs)
    behaviors.extend(flow_behaviors)
    warnings.extend(flow_warnings)

    unique_constructs = {
        (item.kind, item.name, item.source_file, item.source_symbol): item for item in constructs
    }
    unique_behaviors = {item.behavior_id: item for item in behaviors}
    unique_warnings = {
        (item.source_file, item.line, item.code, item.message): item for item in warnings
    }
    return CrewAIArtifactResult(
        detected=True,
        behaviors=tuple(sorted(unique_behaviors.values(), key=lambda item: item.behavior_id)),
        constructs=tuple(
            sorted(
                unique_constructs.values(),
                key=lambda item: (item.source_file, item.kind, item.name),
            )
        ),
        warnings=tuple(
            sorted(
                unique_warnings.values(),
                key=lambda item: (item.source_file, item.line or 0, item.code, item.message),
            )
        ),
    )
