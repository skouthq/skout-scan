"""File-local, provenance-backed registration facts; never coverage evidence."""

import ast
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from agentguard.models import (
    CallableCapability,
    RegistrationRelationship,
    RegistrationResolution,
    SourceEvidence,
)

Function = ast.FunctionDef | ast.AsyncFunctionDef
CONSTRUCTORS = {
    "pydantic_ai.Agent": "Pydantic AI",
    "pydantic_ai.agent.Agent": "Pydantic AI",
    "crewai.Agent": "CrewAI",
    "crewai.agent.Agent": "CrewAI",
    "crewai.Task": "CrewAI",
    "crewai.task.Task": "CrewAI",
}
TOOL_DECORATORS = {
    "langchain_core.tools.tool",
    "langchain_core.tools.convert.tool",
    "langchain.tools.tool",
    "crewai.tools.tool",
    "crewai.tools.base_tool.tool",
    "agents.function_tool",
}


def qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _digest(prefix: str, payload: dict[str, str | None]) -> str:
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _evidence(path: str, source: str, node: ast.AST, symbol: str, kind: str) -> SourceEvidence:
    return SourceEvidence(
        source_file=path,
        source_symbol=symbol,
        kind=kind,
        start_line=getattr(node, "lineno", None),
        end_line=getattr(node, "end_lineno", None),
        excerpt=ast.get_source_segment(source, node) or ast.unparse(node),
    )


class SourceIndex:
    """Unique module bindings only; conditional/nested bindings cannot establish provenance."""

    def __init__(self, tree: ast.Module) -> None:
        self.bindings: dict[str, list[ast.AST]] = defaultdict(list)
        self.imports: dict[str, str] = {}
        self.values: dict[str, ast.expr] = {}
        self.direct = set(tree.body)
        self.star_import = False
        self.mutations: set[str] = set()
        self.tree = tree
        self._index(tree)
        # Attribute writes and explicit reflection invalidate a receiver/class resolution.
        for node in ast.walk(tree):
            if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                self.mutations.add(node.target.id)
            if isinstance(node, ast.Global):
                self.mutations.update(node.names)
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store | ast.Del):
                name = qualified_name(node.value)
                if name and name.endswith(".__dict__"):
                    self.mutations.add(name.split(".")[0])
                if (
                    isinstance(node.value, ast.Call)
                    and qualified_name(node.value.func) == "vars"
                    and node.value.args
                    and isinstance(node.value.args[0], ast.Name)
                ):
                    self.mutations.add(node.value.args[0].id)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store | ast.Del):
                name = qualified_name(node)
                if name:
                    self.mutations.add(name.split(".")[0])
            if (
                isinstance(node, ast.Call)
                and qualified_name(node.func) in {"setattr", "delattr"}
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                self.mutations.add(node.args[0].id)

    def _bind(self, name: str, node: ast.AST) -> None:
        self.bindings[name].append(node)

    def _index(self, node: ast.AST) -> None:
        # Do not mistake function/class-local imports or assignments for module bindings.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import | ast.ImportFrom):
                if isinstance(child, ast.ImportFrom) and any(a.name == "*" for a in child.names):
                    self.star_import = True
                for alias in child.names:
                    name = alias.asname or alias.name.split(".")[0]
                    self._bind(name, child)
                    if isinstance(child, ast.Import):
                        self.imports[name] = alias.name if alias.asname else name
                    elif child.level == 0 and child.module and alias.name != "*":
                        self.imports[name] = f"{child.module}.{alias.name}"
            elif isinstance(child, ast.ExceptHandler):
                if child.name:
                    self._bind(child.name, child)
                self._index(child)
            elif isinstance(child, Function | ast.ClassDef):
                self._bind(child.name, child)
            elif isinstance(child, ast.Assign | ast.AnnAssign):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    for leaf in ast.walk(target):
                        if isinstance(leaf, ast.Name) and isinstance(leaf.ctx, ast.Store):
                            self._bind(leaf.id, child)
                            if isinstance(target, ast.Name) and child.value is not None:
                                self.values[target.id] = child.value
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store | ast.Del):
                self._bind(child.id, child)
            else:
                self._index(child)

    def unique(self, name: str) -> ast.AST | None:
        nodes = self.bindings.get(name, [])
        if len(nodes) != 1 or nodes[0] not in self.direct:
            return None
        if isinstance(nodes[0], ast.Assign) and len(nodes[0].targets) != 1:
            return None
        return nodes[0]

    def resolve_import(self, node: ast.AST) -> str | None:
        name = qualified_name(node)
        if not name or self.star_import:
            return None
        head, *tail = name.split(".")
        declaration = self.unique(head)
        if not isinstance(declaration, ast.Import | ast.ImportFrom) or head in self.mutations:
            return None
        mapped = self.imports.get(head)
        return ".".join((mapped, *tail)) if mapped else None

    def known_non_agent(self, node: ast.AST) -> bool:
        """Only proven local declarations tighten historical generic discovery."""
        target = node.func if isinstance(node, ast.Call) else node
        if not isinstance(target, ast.Name):
            return False
        declaration = self.unique(target.id)
        if not isinstance(declaration, Function | ast.ClassDef):
            return False
        if declaration.decorator_list:
            return False
        if isinstance(declaration, Function):
            # A local identity decorator is demonstrably not a framework decorator.
            args = [*declaration.args.posonlyargs, *declaration.args.args]
            return (
                len(args) == 1
                and len(declaration.body) == 1
                and isinstance(declaration.body[0], ast.Return)
                and isinstance(declaration.body[0].value, ast.Name)
                and declaration.body[0].value.id == args[0].arg
            )
        if declaration.bases or declaration.keywords:
            return False
        # Limit compatibility tightening to passive storage-only constructors.
        # Unknown local factories/custom dispatch classes remain unknown, not non-agent.
        if len(declaration.body) != 1:
            return False
        init = declaration.body[0]
        return (
            isinstance(init, Function)
            and init.name == "__init__"
            and bool(init.body)
            and not init.decorator_list
            and all(
                isinstance(item, ast.Assign)
                and isinstance(item.value, ast.Name)
                and all(
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                    for t in item.targets
                )
                for item in init.body
            )
        )

    def callable_definition(self, node: ast.AST) -> tuple[str, Function | None, str]:
        raw = ast.unparse(node)
        if (
            isinstance(node, ast.Call)
            and self.resolve_import(node.func) == "pydantic_ai.Tool"
            and len(node.args) == 1
        ):
            return self.callable_definition(node.args[0])
        if isinstance(node, ast.Name):
            definition = self.unique(node.id)
            if isinstance(definition, Function) and node.id not in self.mutations:
                for decorator in definition.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if self.resolve_import(target) in TOOL_DECORATORS:
                        continue
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        value = self.values.get(target.value.id)
                        if (
                            target.attr in {"tool", "tool_plain"}
                            and self.unique(target.value.id) is not None
                            and isinstance(value, ast.Call)
                            and self.resolve_import(value.func)
                            in {"pydantic_ai.Agent", "pydantic_ai.agent.Agent"}
                        ):
                            continue
                    return raw, None, "unsupported_callable_decorator"
                return node.id, definition, "unique_local_function"
            if isinstance(definition, ast.Assign | ast.AnnAssign):
                value = self.values.get(node.id)
                if (
                    isinstance(value, ast.Call)
                    and self.resolve_import(value.func) == "pydantic_ai.Tool"
                    and len(value.args) == 1
                    and isinstance(value.args[0], ast.Name)
                    and isinstance(self.unique(value.args[0].id), Function)
                ):
                    return self.callable_definition(value.args[0])
            return raw, None, "callable_not_unique_or_local"
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            return raw, None, "unsupported_callable_expression"
        receiver = node.value.id
        value = self.values.get(receiver)
        if self.unique(receiver) is None or receiver in self.mutations:
            return raw, None, "receiver_rebound_or_mutated"
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
            return raw, None, "receiver_not_direct_local_construction"
        definition = self.unique(value.func.id)
        if (
            not isinstance(definition, ast.ClassDef)
            or definition.bases
            or definition.keywords
            or definition.decorator_list
            or definition.name in self.mutations
        ):
            return raw, None, "unsupported_class_or_inheritance"
        members = [m for m in definition.body if isinstance(m, Function) and m.name == node.attr]
        if len(members) != 1 or members[0].decorator_list:
            return raw, None, "ambiguous_method_or_descriptor"
        # Overrides/descriptors installed in the class or constructor are unsupported.
        for member in ast.walk(definition):
            if isinstance(member, Function) and member.name in {
                "__getattr__",
                "__getattribute__",
                "__setattr__",
                "__new__",
            }:
                return raw, None, "dynamic_class_attributes"
            if (
                isinstance(member, ast.Name)
                and isinstance(member.ctx, ast.Store)
                and member.id == node.attr
            ):
                return raw, None, "method_overwritten"
            if (
                isinstance(member, ast.Attribute)
                and isinstance(member.ctx, ast.Store | ast.Del)
                and member.attr in {node.attr, "__dict__"}
            ):
                return raw, None, "method_overwritten"
            if isinstance(member, ast.Call) and qualified_name(member.func) in {
                "setattr",
                "delattr",
            }:
                return raw, None, "dynamic_class_attributes"
        return f"{definition.name}.{node.attr}", members[0], "unique_local_bound_method"


@dataclass(frozen=True)
class RegistrationInventory:
    capabilities: tuple[CallableCapability, ...]
    relationships: tuple[RegistrationRelationship, ...]


def extract_registrations(path: str, tree: ast.Module, source: str) -> RegistrationInventory:
    index = SourceIndex(tree)
    capabilities: dict[str, CallableCapability] = {}
    relationships: dict[str, RegistrationRelationship] = {}
    owners: dict[str, tuple[str, str]] = {}

    def capability(node: ast.AST) -> CallableCapability | None:
        name, definition, _ = index.callable_definition(node)
        if definition is None:
            return None
        identity = _digest("callable", {"version": "callable-v1", "path": path, "symbol": name})
        result = CallableCapability(
            callable_id=identity,
            source_file=path,
            qualified_name=name,
            definition=_evidence(path, source, definition, name, "callable_definition"),
        )
        capabilities[identity] = result
        return result

    def relationship(
        owner: str,
        entry: ast.AST,
        framework: str | None,
        symbol: str | None,
        kind: Literal["constructor_tool", "decorator_tool"],
        *,
        literal: bool = True,
        form: ast.AST | None = None,
    ) -> None:
        _, definition, reason = index.callable_definition(entry)
        owner_unique = index.unique(owner) is not None and owner not in index.mutations
        cap = capability(entry) if framework and literal and owner_unique else None
        status = RegistrationResolution.RESOLVED if cap else RegistrationResolution.UNRESOLVED
        if not framework:
            reason = "unverified_framework_provenance"
        elif not literal:
            reason = "unsupported_callable_collection"
        elif index.unique(owner) is None or owner in index.mutations:
            status = RegistrationResolution.AMBIGUOUS
            reason = "owner_rebound_or_mutated"
            cap = None
        elif definition is None and "rebound" in reason:
            status = RegistrationResolution.AMBIGUOUS
        normalized = ast.dump(form if form is not None else entry, include_attributes=False)
        payload = {
            "version": "registration-v1",
            "path": path,
            "owner": owner,
            "callable": cap.callable_id if cap else None,
            "expression": normalized,
            "kind": kind,
            "framework": symbol,
        }
        identity = _digest("registration", payload)
        relationships[identity] = RegistrationRelationship(
            relationship_id=identity,
            kind=kind,
            owner_identity=f"{path}#{owner}",
            callable_id=cap.callable_id if cap else None,
            referenced_symbol=ast.unparse(entry),
            source_file=path,
            registration=_evidence(path, source, entry, owner, "tool_registration"),
            definition=cap.definition if cap else None,
            framework=framework,
            framework_symbol=symbol,
            resolution=status,
            reason=reason,
            content_fingerprint=_digest("registration-content-v1", {"expression": normalized}),
        )

    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        call = statement.value
        if not isinstance(call, ast.Call):
            continue
        symbol = index.resolve_import(call.func)
        framework = CONSTRUCTORS.get(symbol or "")
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            owner = target.id
            if framework and symbol:
                owners[owner] = framework, symbol
            tools = next((k.value for k in call.keywords if k.arg == "tools"), None)
            if tools is None:
                continue
            if index.known_non_agent(call.func):
                continue
            entries = tools.elts if isinstance(tools, ast.List | ast.Tuple | ast.Set) else [tools]
            for entry in entries:
                relationship(
                    owner,
                    entry,
                    framework,
                    symbol,
                    "constructor_tool",
                    literal=isinstance(tools, ast.List | ast.Tuple | ast.Set),
                )

    for function in tree.body:
        if not isinstance(function, Function):
            continue
        for decorator in function.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if index.resolve_import(target) in TOOL_DECORATORS:
                capability(ast.Name(id=function.name, ctx=ast.Load()))
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                owner = target.value.id
                if (
                    owner in owners
                    and owners[owner][0] == "Pydantic AI"
                    and target.attr in {"tool", "tool_plain"}
                ):
                    # Resolve through the definition but retain the actual decorator as evidence.
                    entry = ast.Name(id=function.name, ctx=ast.Load())
                    ast.copy_location(entry, decorator)
                    framework, symbol = owners[owner]
                    relationship(owner, entry, framework, symbol, "decorator_tool", form=decorator)
                    key = next(reversed(relationships))
                    relationships[key] = relationships[key].model_copy(
                        update={
                            "registration": _evidence(
                                path, source, decorator, owner, "tool_registration"
                            ),
                            "referenced_symbol": function.name,
                        }
                    )
    return RegistrationInventory(
        tuple(capabilities[key] for key in sorted(capabilities)),
        tuple(relationships[key] for key in sorted(relationships)),
    )
