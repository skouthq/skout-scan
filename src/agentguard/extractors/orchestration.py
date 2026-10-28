"""Explicit orchestration facts using the existing registration inventory contract."""

import ast
from typing import Literal

from agentguard.extractors.registrations import (
    Function,
    RegistrationInventory,
    SourceIndex,
    _digest,
    _evidence,
    resolve_capability,
)
from agentguard.models import (
    CallableCapability,
    RegistrationRelationship,
    RegistrationResolution,
    SourceEvidence,
)

GRAPH_CONSTRUCTORS = {"langgraph.graph.StateGraph", "langgraph.graph.state.StateGraph"}
CREW_AGENTS = {"crewai.Agent", "crewai.agent.Agent"}
CREW_TASKS = {"crewai.Task", "crewai.task.Task"}
PYDANTIC_AGENTS = {"pydantic_ai.Agent", "pydantic_ai.agent.Agent"}
ORCHESTRATION_KINDS = {"graph_node_callback", "task_agent_executor", "output_validator_callback"}
Kind = Literal["graph_node_callback", "task_agent_executor", "output_validator_callback"]
STATIC_LIMIT = (
    "Registration or assignment does not establish execution, reachability, or eval coverage."
)


def _owner(
    index: SourceIndex, name: str, constructors: set[str]
) -> tuple[ast.AST, str, bool] | None:
    """Retain known-constructor evidence under rebinding without resolving the current owner."""
    candidates = [
        (node, index.resolve_import(node.value.func))
        for node in index.bindings.get(name, [])
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Call)
        and index.resolve_import(node.value.func) in constructors
    ]
    if not candidates:
        return None
    node, symbol = candidates[0]
    assert symbol is not None
    valid = index.unique(name) is node and name not in index.mutations
    return node, symbol, valid


def extract_orchestration(
    path: str, tree: ast.Module, source: str, *, index: SourceIndex | None = None
) -> RegistrationInventory:
    index = index if index is not None else SourceIndex(tree)
    capabilities: dict[str, CallableCapability] = {}
    relationships: dict[str, RegistrationRelationship] = {}

    def add(
        *,
        kind: Kind,
        owner: str,
        framework: str,
        framework_symbol: str,
        registered: str | None,
        entry: ast.expr,
        registration: ast.AST,
        reason: str,
        status: RegistrationResolution,
        capability: CallableCapability | None = None,
        executor: str | None = None,
        definition: SourceEvidence | None = None,
    ) -> None:
        form = (
            ast.keyword(arg="agent", value=entry) if kind == "task_agent_executor" else registration
        )
        normalized = ast.dump(form, include_attributes=False)
        identity = _digest(
            "registration",
            {
                "version": "orchestration-v1",
                "path": path,
                "kind": kind,
                "framework": framework_symbol,
                "owner": owner,
                "registered": registered,
                "callable": capability.callable_id if capability else None,
                "executor": executor,
                # Keep uncertain expressions distinct; resolved identity ignores layout.
                "reference": ast.dump(entry, include_attributes=False),
                "uncertain_structure": normalized
                if status is not RegistrationResolution.RESOLVED
                else None,
            },
        )
        if capability:
            capabilities[capability.callable_id] = capability
        relationships[identity] = RegistrationRelationship(
            relationship_id=identity,
            kind=kind,
            source_file=path,
            owner_identity=f"{path}#{owner}",
            registered_identity=registered,
            callable_id=capability.callable_id if capability else None,
            executor_identity=executor,
            referenced_symbol=ast.unparse(entry),
            registration=_evidence(path, source, registration, owner, "orchestration_registration"),
            definition=capability.definition if capability else definition,
            framework=framework,
            framework_symbol=framework_symbol,
            resolution=status,
            reason=reason,
            limitations=(STATIC_LIMIT,)
            if status is RegistrationResolution.RESOLVED
            else (STATIC_LIMIT, reason),
            content_fingerprint=_digest(
                "orchestration-content-v1",
                {
                    "structure": normalized,
                    "reference": ast.dump(entry, include_attributes=False),
                },
            ),
        )

    graph_calls: list[tuple[str, ast.Call, ast.expr, ast.expr, str, bool]] = []
    for statement in tree.body:
        if not isinstance(statement, ast.Expr | ast.Assign | ast.AnnAssign):
            continue
        call = statement.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "add_node"
            and isinstance(call.func.value, ast.Name)
        ):
            continue
        owner = call.func.value.id
        provenance = _owner(index, owner, GRAPH_CONSTRUCTORS)
        if provenance is None or len(call.args) != 2 or call.keywords:
            continue
        _, symbol, valid_owner = provenance
        graph_calls.append((owner, call, call.args[0], call.args[1], symbol, valid_owner))

    # A conflicting mapping has no unique graph-node association; do not guess last-wins semantics.
    targets: dict[tuple[str, str], set[str]] = {}
    for owner, _, node, entry, _, _ in graph_calls:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            targets.setdefault((owner, node.value), set()).add(
                ast.dump(entry, include_attributes=False)
            )
    for owner, call, node, entry, symbol, valid_owner in graph_calls:
        name = (
            node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None
        )
        capability = None
        status = RegistrationResolution.UNRESOLVED
        reason = "unsupported_graph_callback"
        if not valid_owner:
            status, reason = RegistrationResolution.AMBIGUOUS, "owner_rebound_or_mutated"
        elif name is None:
            reason = "dynamic_node_identifier"
        elif len(targets[(owner, name)]) > 1:
            status, reason = RegistrationResolution.AMBIGUOUS, "conflicting_node_registrations"
        elif isinstance(entry, ast.Name):
            definition = index.unique(entry.id)
            if isinstance(definition, Function):
                capability = resolve_capability(path, source, index, entry)
            if capability:
                status, reason = RegistrationResolution.RESOLVED, "unique_local_node_callback"
            elif len(index.bindings.get(entry.id, [])) > 1:
                status, reason = RegistrationResolution.AMBIGUOUS, "callback_rebound_or_ambiguous"
            else:
                reason = "callback_not_unique_local_function"
        add(
            kind="graph_node_callback",
            owner=owner,
            framework="LangGraph",
            framework_symbol=symbol,
            registered=name,
            entry=entry,
            registration=call,
            status=status,
            reason=reason,
            capability=capability,
        )

    for statement in tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign) or not isinstance(
            statement.value, ast.Call
        ):
            continue
        call = statement.value
        task_symbol = index.resolve_import(call.func)
        if task_symbol is None or task_symbol not in CREW_TASKS:
            continue
        task_entry = next((kw.value for kw in call.keywords if kw.arg == "agent"), None)
        if task_entry is None:
            continue
        owners = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in owners:
            if not isinstance(target, ast.Name):
                continue
            owner = target.id
            status, reason = RegistrationResolution.UNRESOLVED, "executor_not_known_local_agent"
            executor, agent_definition = None, None
            if index.unique(owner) is not statement or owner in index.mutations:
                status, reason = RegistrationResolution.AMBIGUOUS, "task_rebound_or_mutated"
            elif isinstance(task_entry, ast.Name):
                agent = _owner(index, task_entry.id, CREW_AGENTS)
                if agent is not None and agent[2]:
                    status, reason = RegistrationResolution.RESOLVED, "unique_local_agent_executor"
                    executor = f"{path}#{task_entry.id}"
                    agent_definition = _evidence(
                        path, source, agent[0], task_entry.id, "agent_definition"
                    )
                elif agent is not None:
                    status, reason = RegistrationResolution.AMBIGUOUS, "executor_rebound_or_mutated"
            add(
                kind="task_agent_executor",
                owner=owner,
                framework="CrewAI",
                framework_symbol=task_symbol,
                registered=f"{path}#{owner}",
                entry=task_entry,
                registration=call,
                status=status,
                reason=reason,
                executor=executor,
                definition=agent_definition,
            )

    for function in tree.body:
        if not isinstance(function, Function):
            continue
        for decorator in function.decorator_list:
            if not (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "output_validator"
                and isinstance(decorator.value, ast.Name)
            ):
                continue
            owner = decorator.value.id
            provenance = _owner(index, owner, PYDANTIC_AGENTS)
            if provenance is None:
                continue
            _, symbol, valid_owner = provenance
            entry = ast.Name(id=function.name, ctx=ast.Load())
            capability = None
            status, reason = RegistrationResolution.UNRESOLVED, "unsupported_callback_decorators"
            if not valid_owner:
                status, reason = RegistrationResolution.AMBIGUOUS, "owner_rebound_or_mutated"
            elif index.unique(function.name) is not function or function.name in index.mutations:
                status, reason = RegistrationResolution.AMBIGUOUS, "callback_rebound_or_ambiguous"
            elif len(function.decorator_list) == 1:
                capability = resolve_capability(
                    path, source, index, entry, registration_decorator=decorator
                )
                if capability:
                    status, reason = (
                        RegistrationResolution.RESOLVED,
                        "unique_local_output_validator",
                    )
            add(
                kind="output_validator_callback",
                owner=owner,
                framework="Pydantic AI",
                framework_symbol=symbol,
                registered=f"{path}#{function.name}",
                entry=entry,
                registration=decorator,
                status=status,
                reason=reason,
                capability=capability,
            )

    return RegistrationInventory(
        tuple(capabilities[key] for key in sorted(capabilities)),
        tuple(relationships[key] for key in sorted(relationships)),
    )
