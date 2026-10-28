"""One-hop relationships from a frozen, proven parent set. No coverage inference."""

import ast
import json
from dataclasses import dataclass
from typing import Literal

from agentguard.extractors.registrations import (
    TOOL_DECORATORS,
    Function,
    RegistrationInventory,
    SourceIndex,
    _digest,
    _evidence,
    qualified_name,
    resolve_capability,
)
from agentguard.models import (
    CallableCapability,
    RegistrationRelationship,
    RegistrationResolution,
    SourceEvidence,
)

DELEGATION_KINDS = {"literal_dispatch", "one_hop_delegation", "exception_fallback"}
PARENT_KINDS = {
    "constructor_tool",
    "decorator_tool",
    "graph_node_callback",
    "output_validator_callback",
}
DISCOVERY_FIELDS = {
    "parent_callable_id",
    "parent_relationship_ids",
    "parent_provenance",
    "dispatch_key",
    "exception_condition",
    "conditions",
    "context_evidence",
    "registry_evidence",
    "handler_evidence",
    "target_role",
}
EXCEPTIONS = {
    "TimeoutError",
    "ConnectionError",
    "FileNotFoundError",
    "PermissionError",
    "OSError",
    "KeyError",
    "ValueError",
    "LookupError",
}
REFLECTION = {"eval", "exec", "globals", "locals", "vars", "__import__"}
BUILTIN_HELPERS = {
    "str",
    "int",
    "float",
    "bool",
    "len",
    "dict",
    "list",
    "tuple",
    "set",
    "print",
    "range",
    "isinstance",
    "super",
    "object",
}
STATIC_LIMIT = (
    "Possible structural call only; no execution, propagation, recovery, "
    "or eval coverage is established."
)
Kind = Literal["literal_dispatch", "one_hop_delegation", "exception_fallback"]


@dataclass(frozen=True)
class Parent:
    capability: CallableCapability
    function: Function
    proofs: tuple[SourceEvidence, ...]
    relationships: tuple[str, ...]
    framework: str | None


def _definition(index: SourceIndex, name: str) -> Function | None:
    head, *tail = name.split(".")
    node = index.unique(head)
    if isinstance(node, Function) and not tail:
        return node
    if isinstance(node, ast.ClassDef) and len(tail) == 1:
        methods = [m for m in node.body if isinstance(m, Function) and m.name == tail[0]]
        return methods[0] if len(methods) == 1 else None
    return None


def eligible_parents(
    path: str, source: str, index: SourceIndex, inventory: RegistrationInventory
) -> tuple[Parent, ...]:
    result = []
    for cap in inventory.capabilities:
        function = _definition(index, cap.qualified_name)
        if function is None:
            continue
        links = [
            r
            for r in inventory.relationships
            if r.kind in PARENT_KINDS
            and r.callable_id == cap.callable_id
            and r.resolution is RegistrationResolution.RESOLVED
        ]
        proofs = [r.registration for r in links]
        frameworks = {r.framework for r in links if r.framework}
        for decorator in function.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            symbol = index.resolve_import(target)
            if symbol in TOOL_DECORATORS:
                proofs.append(
                    _evidence(
                        path, source, decorator, cap.qualified_name, "framework_tool_declaration"
                    )
                )
                frameworks.add(
                    "CrewAI"
                    if symbol.startswith("crewai")
                    else "LangChain"
                    if symbol.startswith("langchain")
                    else "OpenAI Agents"
                )
        if proofs:
            result.append(
                Parent(
                    cap,
                    function,
                    tuple(proofs),
                    tuple(sorted(r.relationship_id for r in links)),
                    next(iter(frameworks)) if len(frameworks) == 1 else None,
                )
            )
    return tuple(sorted(result, key=lambda p: p.capability.callable_id))


def _locals(function: Function) -> set[str]:
    """Exclude lexical shadows; do not mistake nested callable bodies for this parent's body."""
    names = {
        a.arg for a in [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    }
    names.update(a.arg for a in (function.args.vararg, function.args.kwarg) if a)

    def visit(node: ast.AST) -> None:
        if isinstance(node, Function | ast.ClassDef):
            names.add(node.name)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            names.add(node.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            names.update(node.names)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in function.body:
        visit(statement)
    return names


def _registry(index: SourceIndex, name: str) -> tuple[ast.Dict | None, str]:
    declaration = index.unique(name)
    value = index.values.get(name)
    if not isinstance(declaration, ast.Assign | ast.AnnAssign) or not isinstance(value, ast.Dict):
        return None, "registry_not_unique_literal"
    if name in index.mutations:
        return None, "registry_mutated"
    parents = {child: node for node in ast.walk(index.tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(index.tree):
        if isinstance(node, ast.Attribute) and node.attr in {"__globals__", "__dict__"}:
            return None, "registry_reflection_or_unknown_mutation"
        if isinstance(node, ast.Call):
            raw = qualified_name(node.func) or ""
            imported = index.resolve_import(node.func) or ""
            if raw in REFLECTION or imported in {f"builtins.{name}" for name in REFLECTION}:
                return None, "registry_reflection_or_unknown_mutation"
        if not isinstance(node, ast.Name) or node.id != name:
            continue
        parent = parents.get(node)
        if parent is declaration and isinstance(node.ctx, ast.Store):
            continue
        call_parent = parents.get(parent) if parent is not None else None
        # The only supported read is as the callee of REGISTRY[key](...).
        if (
            isinstance(parent, ast.Subscript)
            and parent.value is node
            and isinstance(parent.ctx, ast.Load)
            and isinstance(call_parent, ast.Call)
            and call_parent.func is parent
        ):
            continue
        return None, "registry_escaped_aliased_or_mutated"
    keys: set[str] = set()
    for key, target in zip(value.keys, value.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return None, "computed_registry_key"
        if key.value in keys:
            return None, "duplicate_registry_key"
        keys.add(key.value)
        if not isinstance(target, ast.Name) or not isinstance(index.unique(target.id), Function):
            return None, "computed_or_external_registry_target"
        if index.callable_definition(target)[1] is None:
            return None, "unresolved_registry_target"
    return value, "literal_registry"


def _exception(node: ast.expr | None, index: SourceIndex, shadows: set[str]) -> bool:
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_exception(e, index, shadows) for e in node.elts)
    if (
        isinstance(node, ast.Name)
        and node.id in EXCEPTIONS
        and node.id not in shadows
        and node.id not in index.bindings
        and node.id not in index.mutations
        and not index.star_import
    ):
        return True
    if node is not None and (qualified_name(node) or "").split(".")[0] in shadows:
        return False
    symbol = index.resolve_import(node) if node is not None else None
    return symbol in {f"builtins.{name}" for name in EXCEPTIONS}


def extract_delegations(
    path: str,
    tree: ast.Module,
    source: str,
    inventory: RegistrationInventory,
    *,
    index: SourceIndex | None = None,
) -> RegistrationInventory:
    index = index if index is not None else SourceIndex(tree)
    capabilities: dict[str, CallableCapability] = {}
    relationships: dict[str, RegistrationRelationship] = {}
    # Freeze roots before adding any internal target. Never recurse through new capabilities.
    parents = eligible_parents(path, source, index, inventory)
    registries: dict[str, tuple[ast.Dict | None, str]] = {}

    def analyze_parent(parent: Parent) -> None:
        shadows = _locals(parent.function)
        symbol = parent.capability.qualified_name

        def add(
            kind: Kind,
            expression: ast.expr,
            call: ast.Call,
            contexts: tuple[str, ...],
            context_keys: tuple[str, ...],
            evidence: tuple[SourceEvidence, ...],
            *,
            target: ast.expr | None = None,
            dispatch_key: str | None = None,
            registry: ast.Dict | None = None,
            handler: ast.ExceptHandler | None = None,
            supported: bool = True,
            reason: str = "unique_local_target",
        ) -> None:
            target = call.func if target is None else target
            if supported and not isinstance(target, ast.Name | ast.Attribute):
                supported, reason = False, "unsupported_callable_expression"
            head = (qualified_name(target) or "").split(".")[0]
            blocked = head in shadows
            cap = (
                resolve_capability(path, source, index, target)
                if supported and not blocked
                else None
            )
            status = RegistrationResolution.RESOLVED if cap else RegistrationResolution.UNRESOLVED
            if blocked:
                reason = "local_binding_shadows_target"
            elif supported and cap is None:
                _, _, reason = index.callable_definition(target)
                if "rebound" in reason:
                    status = RegistrationResolution.AMBIGUOUS
            if cap:
                capabilities[cap.callable_id] = cap
            condition = (
                ast.unparse(handler.type)
                if handler is not None and handler.type is not None
                else None
            )
            normalized = ast.dump(expression, include_attributes=False)
            payload = {
                "version": "delegation-v1",
                "path": path,
                "parent": parent.capability.callable_id,
                "kind": kind,
                "target": cap.callable_id if cap else ast.dump(target, include_attributes=False),
                "key": dispatch_key,
                "exception": condition,
                "context": json.dumps(context_keys),
                "call": normalized,
            }
            identity = _digest("registration", payload)
            relationships[identity] = RegistrationRelationship(
                relationship_id=identity,
                kind=kind,
                source_file=path,
                owner_identity=f"{path}#{symbol}",
                parent_callable_id=parent.capability.callable_id,
                parent_relationship_ids=parent.relationships,
                parent_provenance=parent.proofs,
                callable_id=cap.callable_id if cap else None,
                referenced_symbol=ast.unparse(target),
                registration=_evidence(path, source, expression, symbol, "relationship_call_site"),
                definition=cap.definition if cap else None,
                framework=parent.framework,
                resolution=status,
                reason=reason if cap is None else "source_backed_one_hop",
                dispatch_key=dispatch_key,
                exception_condition=condition,
                conditions=contexts,
                context_evidence=evidence,
                registry_evidence=_evidence(path, source, registry, symbol, "literal_registry")
                if registry
                else None,
                handler_evidence=_evidence(path, source, handler, symbol, "exception_handler")
                if handler
                else None,
                target_role="orchestrated_internal" if cap else None,
                limitations=(
                    STATIC_LIMIT,
                    "Delegated condition/failure propagation is not inferred.",
                ),
                content_fingerprint=_digest("delegation-content-v1", payload),
            )

        def call_site(
            expression: ast.expr | None,
            contexts: tuple[str, ...],
            keys: tuple[str, ...],
            evidence: tuple[SourceEvidence, ...],
            handler: ast.ExceptHandler | None,
            supported: bool,
        ) -> None:
            original = expression
            if isinstance(expression, ast.Await):
                expression = expression.value
            if not isinstance(expression, ast.Call) or original is None:
                return
            call = expression
            fallback = handler is not None
            if (
                isinstance(call.func, ast.Subscript)
                and isinstance(call.func.value, ast.Name)
                and not fallback
            ):
                name = call.func.value.id
                if name not in registries:
                    registries[name] = _registry(index, name)
                registry, reason = registries[name]
                if name in shadows:
                    registry, reason = None, "local_binding_shadows_registry"
                if not (
                    isinstance(call.func.slice, ast.Name)
                    or isinstance(call.func.slice, ast.Constant)
                    and isinstance(call.func.slice.value, str)
                ):
                    registry, reason = None, "computed_dispatch_selector"
                if registry is None or not supported:
                    add(
                        "literal_dispatch",
                        original,
                        call,
                        contexts,
                        keys,
                        evidence,
                        supported=False,
                        reason=reason if supported else "unsupported_control_context",
                    )
                    return
                for key, target in zip(registry.keys, registry.values, strict=True):
                    assert isinstance(key, ast.Constant) and isinstance(key.value, str)
                    if (
                        isinstance(call.func.slice, ast.Constant)
                        and call.func.slice.value != key.value
                    ):
                        continue
                    add(
                        "literal_dispatch",
                        original,
                        call,
                        contexts,
                        keys,
                        evidence,
                        target=target,
                        dispatch_key=key.value,
                        registry=registry,
                    )
                return
            if (
                isinstance(call.func, ast.Name)
                and call.func.id in BUILTIN_HELPERS
                and call.func.id not in shadows
                and call.func.id not in index.bindings
            ):
                return
            valid_handler = handler is None or _exception(handler.type, index, shadows)
            add(
                "exception_fallback" if fallback else "one_hop_delegation",
                original,
                call,
                contexts,
                keys,
                evidence,
                handler=handler,
                supported=supported and valid_handler,
                reason="unsupported_control_or_exception"
                if not supported or not valid_handler
                else "unique_local_target",
            )

        def visit(
            statements: list[ast.stmt],
            contexts: tuple[str, ...] = (),
            keys: tuple[str, ...] = (),
            evidence: tuple[SourceEvidence, ...] = (),
            handler: ast.ExceptHandler | None = None,
            try_depth: int = 0,
            supported: bool = True,
        ) -> None:
            for statement in statements:
                if isinstance(statement, ast.If):
                    guard = ast.unparse(statement.test)
                    proof = _evidence(path, source, statement.test, symbol, "branch_condition")
                    visit(
                        statement.body,
                        (*contexts, f"if {guard}"),
                        (*keys, f"if {guard}"),
                        (*evidence, proof),
                        handler,
                        try_depth,
                        supported,
                    )
                    visit(
                        statement.orelse,
                        (*contexts, f"else of {guard}"),
                        (*keys, f"else {guard}"),
                        (*evidence, proof),
                        handler,
                        try_depth,
                        supported,
                    )
                elif isinstance(statement, ast.Try):
                    body = ast.dump(
                        ast.Module(body=statement.body, type_ignores=[]), include_attributes=False
                    )
                    scope = _digest("try-context", {"body": body})
                    valid = supported and try_depth == 0
                    visit(
                        statement.body,
                        (*contexts, "try body"),
                        (*keys, scope, "try"),
                        evidence,
                        handler,
                        try_depth + 1,
                        valid,
                    )
                    for caught in statement.handlers:
                        label = ast.unparse(caught.type) if caught.type else "bare except"
                        visit(
                            caught.body,
                            (*contexts, f"except {label}"),
                            (*keys, scope, f"except {label}"),
                            evidence,
                            caught,
                            try_depth + 1,
                            valid,
                        )
                    visit(
                        statement.orelse,
                        (*contexts, "try else"),
                        (*keys, scope, "else"),
                        evidence,
                        handler,
                        try_depth + 1,
                        valid,
                    )
                    visit(
                        statement.finalbody,
                        (*contexts, "finally"),
                        (*keys, scope, "finally"),
                        evidence,
                        handler,
                        try_depth + 1,
                        valid,
                    )
                elif isinstance(statement, ast.Return | ast.Expr | ast.Assign | ast.AnnAssign):
                    call_site(statement.value, contexts, keys, evidence, handler, supported)
                elif isinstance(statement, Function | ast.ClassDef):
                    continue
                elif isinstance(
                    statement,
                    ast.For | ast.AsyncFor | ast.While | ast.With | ast.AsyncWith | ast.TryStar,
                ):
                    for field in ("body", "orelse", "finalbody"):
                        visit(
                            getattr(statement, field, []),
                            (*contexts, f"unsupported {type(statement).__name__}"),
                            (*keys, ast.dump(statement, include_attributes=False)),
                            evidence,
                            handler,
                            try_depth,
                            False,
                        )

        visit(parent.function.body)

    for parent in parents:
        analyze_parent(parent)
    return RegistrationInventory(
        tuple(capabilities[k] for k in sorted(capabilities)),
        tuple(relationships[k] for k in sorted(relationships)),
    )
