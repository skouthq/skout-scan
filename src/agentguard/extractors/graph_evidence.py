"""Bounded graph owner evidence, separate from behavior/relationship extraction."""

import ast
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agentguard.extractors.delegation import _locals
from agentguard.extractors.registrations import SourceIndex, _evidence, qualified_name
from agentguard.models import (
    ArtifactType,
    EvalScenario,
    EvalSourceType,
    LiteralArgument,
    ReferencedSymbol,
    ScanResult,
    SourceEvidence,
)

GRAPH_TYPES = {"langgraph.graph.StateGraph", "langgraph.graph.state.StateGraph"}
OWNER_INVOCATION = "graph_owner_invocation"
OWNER_ASSERTION = "graph_owner_assertion"
OWNER_AMBIGUOUS = "graph_owner_ambiguous"
OWNER_UNVERIFIED = "graph_owner_unverified"
OWNER_KINDS = {OWNER_INVOCATION, OWNER_ASSERTION, OWNER_AMBIGUOUS, OWNER_UNVERIFIED}


@dataclass(frozen=True)
class _Declaration:
    identity: str
    unique: bool
    evidence: SourceEvidence


def attach_graph_evidence(
    scan: ScanResult,
    scenarios: tuple[EvalScenario, ...],
    *,
    literal_arguments: Callable[[ast.Call], tuple[LiteralArgument, ...]],
) -> tuple[EvalScenario, ...]:
    """Resolve only scanned local graph declarations and direct import/invocation forms."""
    if scan.repository.root is None:
        return scenarios
    root = Path(scan.repository.root)
    trees: dict[str, tuple[str, ast.Module, SourceIndex]] = {}
    owners: dict[str, _Declaration] = {}
    modules: dict[str, list[str]] = {}
    for artifact in scan.artifacts:
        if artifact.artifact_type is not ArtifactType.PYTHON:
            continue
        try:
            source = (root / artifact.path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeError, SyntaxError):
            continue  # Existing eval/behavior parsing owns read/parse completeness warnings.
        index = SourceIndex(tree)
        trees[artifact.path] = source, tree, index
        parts = list(PurePosixPath(artifact.path).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        names = [".".join(parts)]
        if parts and parts[0] == "src":
            names.append(".".join(parts[1:]))
        for name in names:
            modules.setdefault(name, []).append(artifact.path)
        for node in tree.body:
            if not isinstance(node, ast.Assign | ast.AnnAssign) or not isinstance(
                node.value, ast.Call
            ):
                continue
            if index.resolve_import(node.value.func) not in GRAPH_TYPES:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                identity = f"{artifact.path}#{target.id}"
                owners[identity] = _Declaration(
                    identity,
                    index.unique(target.id) is node and target.id not in index.mutations,
                    _evidence(artifact.path, source, node, target.id, "graph_owner_definition"),
                )

    def reference(
        identity: str,
        declaration: _Declaration | None,
        evidence: SourceEvidence,
        *,
        assertion: bool = False,
        ambiguous: bool = False,
    ) -> ReferencedSymbol:
        kind = (
            OWNER_AMBIGUOUS
            if ambiguous or declaration is not None and not declaration.unique
            else OWNER_ASSERTION
            if assertion and declaration
            else OWNER_INVOCATION
            if declaration
            else OWNER_UNVERIFIED
        )
        return ReferencedSymbol(
            name=identity.rsplit("#", 1)[-1],
            qualified_name=identity,
            evidence=evidence.model_copy(update={"kind": kind}),
        )

    result = []
    for scenario in scenarios:
        added: list[ReferencedSymbol] = []
        proofs: list[SourceEvidence] = []
        if scenario.source_type in {EvalSourceType.JSONL, EvalSourceType.PYDANTIC_EVAL}:
            binding = scenario.metadata.get("graph_owner")
            if binding is not None:
                valid = (
                    isinstance(binding, dict)
                    and set(binding) == {"source_file", "symbol"}
                    and all(isinstance(v, str) and v for v in binding.values())
                )
                identity = (
                    f"{binding['source_file']}#{binding['symbol']}"
                    if valid and isinstance(binding, dict)
                    else "[invalid graph_owner]"
                )
                declaration = owners.get(identity)
                if scenario.evidence:
                    added.append(
                        reference(
                            identity,
                            declaration,
                            scenario.evidence[0],
                            assertion=True,
                            ambiguous=isinstance(binding, list),
                        )
                    )
                if declaration:
                    proofs.append(declaration.evidence)
        elif scenario.source_type is EvalSourceType.PYTEST and scenario.source_file in trees:
            source, tree, index = trees[scenario.source_file]
            name = scenario.source_symbol or ""
            parent: ast.AST = tree
            function = None
            for part in name.split("."):
                function = next(
                    (
                        node
                        for node in getattr(parent, "body", [])
                        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                        and node.name == part
                    ),
                    None,
                )
                if function is None:
                    break
                parent = function
            if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                shadows = _locals(function)

                # Nested callable bodies cannot establish invocation by the enclosing test.
                def calls(node: ast.AST) -> Iterator[ast.Call]:
                    for child in ast.iter_child_nodes(node):
                        if isinstance(
                            child,
                            ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda,
                        ):
                            continue
                        if isinstance(child, ast.Call):
                            yield child
                        yield from calls(child)

                for call in calls(function):
                    if not isinstance(call.func, ast.Attribute) or call.func.attr not in {
                        "invoke",
                        "ainvoke",
                    }:
                        continue
                    receiver = call.func.value
                    if (
                        isinstance(receiver, ast.Call)
                        and isinstance(receiver.func, ast.Attribute)
                        and receiver.func.attr == "compile"
                        and not receiver.args
                        and not receiver.keywords
                    ):
                        receiver = receiver.func.value
                    raw = qualified_name(receiver)
                    if raw is None or raw.split(".")[0] in shadows:
                        continue
                    identity = f"{scenario.source_file}#{raw}"
                    declaration = owners.get(identity)
                    ambiguous = False
                    if declaration is None:
                        imported = index.resolve_import(receiver)
                        if imported and "." in imported:
                            module, symbol = imported.rsplit(".", 1)
                            paths = modules.get(module, [])
                            ambiguous = len(paths) > 1
                            if len(paths) == 1:
                                identity = f"{paths[0]}#{symbol}"
                                declaration = owners.get(identity)
                    if declaration is None and not ambiguous:
                        continue
                    proof = _evidence(scenario.source_file, source, call, name, OWNER_INVOCATION)
                    added.append(
                        reference(identity, declaration, proof, ambiguous=ambiguous).model_copy(
                            update={"literal_arguments": literal_arguments(call)}
                        )
                    )
                    if declaration:
                        proofs.append(declaration.evidence)
        if added:
            result.append(
                scenario.model_copy(
                    update={
                        "referenced_symbols": (*scenario.referenced_symbols, *added),
                        "evidence": tuple(
                            dict.fromkeys(
                                (*scenario.evidence, *proofs, *(r.evidence for r in added))
                            )
                        ),
                    }
                )
            )
        else:
            result.append(scenario)
    return tuple(result)
