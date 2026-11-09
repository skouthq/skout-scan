"""Explicit structural scope discovery/projection. Never a coverage or lifecycle filter."""

import ast
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath

from agentguard.comparison import VerificationInventory, analyze_snapshot
from agentguard.extractors.orchestration import (
    CREW_AGENTS,
    GRAPH_CONSTRUCTORS,
    PYDANTIC_AGENTS,
    _owner,
)
from agentguard.extractors.registrations import SourceIndex, _digest, _evidence
from agentguard.findings import update_findings
from agentguard.guidance import with_guidance
from agentguard.models import (
    ArtifactType,
    BehaviorExtractionResult,
    BehaviorSourceType,
    Finding,
    FindingDisposition,
    FindingStatus,
    FindingUpdateResult,
    RegistrationRelationship,
    RegistrationResolution,
    ScanCompleteness,
    ScanResult,
    ScopedScanReport,
    ScopeInventory,
    ScopeItemMembership,
    ScopeMembership,
    ScopeRoot,
    ScopeSelection,
    SourceEvidence,
)
from agentguard.rejection_provenance import enrich_rejection_explanations

LIMITATION = (
    "Selected scope is a declared structural surface, not runtime reachability or deployment."
)
ROOT_TYPES = (
    (PYDANTIC_AGENTS, "Pydantic AI", "pydantic_ai_agent"),
    (CREW_AGENTS, "CrewAI", "crewai_agent"),
    (GRAPH_CONSTRUCTORS, "LangGraph", "langgraph"),
)


class ScopeSelectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def discover_scope_roots(scan: ScanResult, extraction: BehaviorExtractionResult) -> ScopeInventory:
    """Reuse file-local known-constructor provenance; never import a target module."""
    roots: list[ScopeRoot] = []
    limits = [
        LIMITATION,
        "Only unique module-level known Agent/StateGraph declarations are selectable; "
        "class factories and imported instances remain unsupported.",
    ]
    source_unavailable = False
    if scan.repository.root is not None:
        root = Path(scan.repository.root)
        for artifact in scan.artifacts:
            if artifact.artifact_type is not ArtifactType.PYTHON:
                continue
            try:
                source = (root / artifact.path).read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, UnicodeError, SyntaxError):
                source_unavailable = True
                limits.append(f"Source unavailable for scope discovery: {artifact.path}")
                continue
            index = SourceIndex(tree)
            for name in sorted(index.bindings):
                found = [
                    (types, framework, kind, _owner(index, name, types))
                    for types, framework, kind in ROOT_TYPES
                ]
                candidates = [
                    (framework, kind, value) for _, framework, kind, value in found if value
                ]
                for framework, kind, value in candidates:
                    assert value is not None
                    node, _, unique = value
                    direct = (
                        isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == name
                        or isinstance(node, ast.AnnAssign)
                        and isinstance(node.target, ast.Name)
                        and node.target.id == name
                    )
                    resolved = unique and direct and len(candidates) == 1
                    call = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
                    opaque = isinstance(call, ast.Call) and (
                        any(k.arg is None for k in call.keywords)
                        or any(isinstance(arg, ast.Starred) for arg in call.args)
                    )
                    selector = f"{artifact.path}#{name}"
                    roots.append(
                        ScopeRoot(
                            root_id=_digest(
                                "scope",
                                {
                                    "version": "scope-root-v1",
                                    "path": artifact.path,
                                    "symbol": name,
                                    "kind": kind,
                                },
                            ),
                            selector=selector,
                            framework=framework,
                            root_kind=kind,
                            display_name=name,
                            qualified_symbol=name,
                            source_file=artifact.path,
                            evidence=(
                                _evidence(
                                    artifact.path, source, node, name, "scope_root_declaration"
                                ),
                            ),
                            resolution=RegistrationResolution.RESOLVED
                            if resolved
                            else RegistrationResolution.AMBIGUOUS,
                            relationship_ids=tuple(
                                sorted(
                                    r.relationship_id
                                    for r in extraction.registration_relationships
                                    if r.owner_identity == selector
                                    or r.executor_identity == selector
                                )
                            ),
                            has_opaque_configuration=opaque,
                            limitations=(
                                (LIMITATION,)
                                + (
                                    ("Expanded constructor arguments may hide registrations.",)
                                    if opaque
                                    else ()
                                )
                            )
                            if resolved
                            else (
                                "Known owner is rebound, mutated, conditional, "
                                "unpacked or ambiguous.",
                            ),
                        )
                    )
    statuses = {scan.completeness, extraction.completeness}
    completeness = (
        ScanCompleteness.FAILED
        if ScanCompleteness.FAILED in statuses
        else ScanCompleteness.INCOMPLETE
        if ScanCompleteness.INCOMPLETE in statuses or source_unavailable
        else ScanCompleteness.COMPLETE
    )
    limits.extend(f"Discovery: {w.code} ({w.path or 'repository'})" for w in scan.warnings)
    limits.extend(f"Discovery error: {e.code}: {e.message}" for e in scan.errors)
    limits.extend(f"Extraction: {w.code} ({w.source_file})" for w in extraction.warnings)
    if completeness is not ScanCompleteness.COMPLETE:
        limits.append("Incomplete analysis cannot establish exclusion confidently.")
    return ScopeInventory(
        roots=tuple(
            sorted(
                (r for r in roots if r.resolution is RegistrationResolution.RESOLVED),
                key=lambda r: r.selector,
            )
        ),
        candidates=tuple(
            sorted(
                (r for r in roots if r.resolution is not RegistrationResolution.RESOLVED),
                key=lambda r: (r.selector, r.root_kind),
            )
        ),
        completeness=completeness,
        limitations=tuple(dict.fromkeys(limits)),
    )


def select_scope(inventory: ScopeInventory, selector: str) -> ScopeRoot:
    if not selector or selector != selector.strip() or any(ord(c) < 32 for c in selector):
        raise ScopeSelectionError(
            "malformed_scope", "Use a scope selector printed by skout scopes ."
        )
    if "#" in selector:
        parts = selector.split("#")
        if (
            len(parts) != 2
            or not parts[1].isidentifier()
            or not parts[0]
            or PurePosixPath(parts[0]).is_absolute()
            or ".." in PurePosixPath(parts[0]).parts
        ):
            raise ScopeSelectionError(
                "malformed_scope", "Expected repository-relative file.py#symbol."
            )
    elif not selector.isidentifier() and not selector.startswith("scope_"):
        raise ScopeSelectionError(
            "malformed_scope", "Use a qualified file.py#symbol selector or unique root name."
        )
    matches = [
        r
        for r in (*inventory.roots, *inventory.candidates)
        if selector in {r.selector, r.root_id, r.qualified_symbol}
    ]
    options = (
        ", ".join(r.selector for r in inventory.roots)
        or "none; check source, exclusions and scan completeness"
    )
    if not matches:
        raise ScopeSelectionError(
            "unknown_scope",
            f"Unknown or unsupported scope {selector!r}; selectable roots: {options}. "
            "Run skout scopes .",
        )
    if len(matches) > 1:
        raise ScopeSelectionError(
            "ambiguous_scope",
            f"Ambiguous scope {selector!r}; use an exact selector: "
            + ", ".join(f"{r.selector} ({r.root_kind}, {r.resolution.value})" for r in matches),
        )
    selected = matches[0]
    if selected.resolution is not RegistrationResolution.RESOLVED:
        raise ScopeSelectionError(
            "unresolved_scope",
            f"Scope {selected.selector} is not selectable: " + " ".join(selected.limitations),
        )
    return selected


def _edge(r: RegistrationRelationship) -> tuple[str | None, str | None]:
    if r.kind == "task_agent_executor":
        return r.executor_identity, r.owner_identity
    if r.kind in {"literal_dispatch", "one_hop_delegation", "exception_fallback"}:
        return r.parent_callable_id, r.callable_id
    return r.owner_identity, r.callable_id


def scope_membership(
    inventory: ScopeInventory, extraction: BehaviorExtractionResult, selected: ScopeRoot
) -> tuple[
    tuple[ScopeItemMembership, ...],
    tuple[ScopeItemMembership, ...],
    tuple[ScopeItemMembership, ...],
    bool,
]:
    """Follow existing directed links only. Unresolved links never become confirmed paths."""
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    uncertain: set[str] = set()
    for r in extraction.registration_relationships:
        parent, child = _edge(r)
        if (
            parent is not None
            and child is not None
            and r.resolution is RegistrationResolution.RESOLVED
        ):
            adjacency[parent].append((child, r.relationship_id))
        elif parent is not None:
            uncertain.add(parent)
    unanchored = any(
        _edge(r)[0] is None and r.resolution is not RegistrationResolution.RESOLVED
        for r in extraction.registration_relationships
    )
    paths: dict[str, dict[str, tuple[str, ...]]] = {}
    closed: dict[str, bool] = {}
    for root in inventory.roots:
        reached: dict[str, tuple[str, ...]] = {root.selector: ()}
        queue = deque([root.selector])
        while queue:
            parent = queue.popleft()
            for child, link in sorted(adjacency[parent]):
                if child not in reached:
                    reached[child] = (*reached[parent], link)
                    queue.append(child)
        paths[root.selector] = reached
        closed[root.selector] = (
            not root.has_opaque_configuration
            and not unanchored
            and not uncertain.intersection(reached)
            and inventory.completeness is ScanCompleteness.COMPLETE
        )
    known_nodes = {node for reached in paths.values() for node in reached}
    if uncertain - known_nodes:
        closed = {selector: False for selector in closed}
    chosen = paths[selected.selector]

    def record(
        item_id: str,
        kind: str,
        file: str,
        symbol: str | None,
        nodes: set[str],
        refs: tuple[SourceEvidence, ...],
        *,
        uncertain_item: bool = False,
    ) -> ScopeItemMembership:
        owners = tuple(
            sorted(root for root, reached in paths.items() if nodes.intersection(reached))
        )
        inside = sorted(nodes.intersection(chosen))
        if inside and not uncertain_item:
            status, reason = ScopeMembership.IN_SCOPE, "resolved_selected_path"
            links = chosen[inside[0]]
        elif owners and closed[selected.selector] and not uncertain_item:
            status, reason = ScopeMembership.OUT_OF_SCOPE, "resolved_distinct_component"
            other = owners[0]
            node = sorted(nodes.intersection(paths[other]))[0]
            links = paths[other][node]
        else:
            status = ScopeMembership.UNKNOWN
            reason = (
                "unresolved_or_unavailable_item"
                if uncertain_item
                else "selected_surface_incomplete"
                if not closed[selected.selector]
                else "no_proven_component_membership"
            )
            links = ()
        if kind == "relationship" and status is not ScopeMembership.UNKNOWN:
            links = tuple(dict.fromkeys((*links, item_id)))
        return ScopeItemMembership(
            item_id=item_id,
            item_kind=kind,
            source_file=file,
            source_symbol=symbol,
            membership=status,
            reason=reason,
            relationship_ids=links,
            known_roots=owners,
            evidence=refs,
        )

    capabilities = {(c.source_file, c.qualified_name): c for c in extraction.callable_capabilities}
    roots = {r.selector: r for r in inventory.roots}
    task_nodes = {
        r.owner_identity
        for r in extraction.registration_relationships
        if r.kind == "task_agent_executor" and r.resolution is RegistrationResolution.RESOLVED
    }
    behavior_rows = []
    for b in extraction.behaviors:
        nodes: set[str] = set()
        owner = f"{b.source_file}#{b.subject}"
        if b.source_type is BehaviorSourceType.LANGGRAPH_WORKFLOW:
            if owner in roots and roots[owner].root_kind == "langgraph":
                nodes.add(owner)
        elif b.source_type is BehaviorSourceType.PYDANTIC_AI_AGENT:
            if owner in roots and roots[owner].root_kind == "pydantic_ai_agent":
                nodes.add(owner)
        elif b.source_type is BehaviorSourceType.CREWAI_WORKFLOW:
            if owner in task_nodes:
                nodes.add(owner)
        else:
            cap = capabilities.get((b.source_file, b.source_symbol or b.subject))
            if cap:
                nodes.add(cap.callable_id)
            else:
                # Constructor-specific tool behaviors keep their actual registration owner.
                cap = capabilities.get((b.source_file, b.subject))
                if cap:
                    nodes.update(
                        r.owner_identity
                        for r in extraction.registration_relationships
                        if r.callable_id == cap.callable_id
                        and r.owner_identity == f"{b.source_file}#{b.source_symbol}"
                        and r.resolution is RegistrationResolution.RESOLVED
                    )
        behavior_rows.append(
            record(
                b.behavior_id,
                "behavior",
                b.source_file,
                b.source_symbol,
                nodes,
                b.evidence,
                uncertain_item=b.behavior_id in extraction.unavailable_behavior_ids,
            )
        )
    relationship_rows = []
    for r in extraction.registration_relationships:
        parent, _ = _edge(r)
        relationship_rows.append(
            record(
                r.relationship_id,
                "relationship",
                r.source_file,
                r.registration.source_symbol,
                {parent} if parent else set(),
                tuple(
                    ref
                    for ref in (
                        r.registration,
                        r.definition,
                        r.registry_evidence,
                        r.handler_evidence,
                        *r.parent_provenance,
                        *r.context_evidence,
                    )
                    if ref
                ),
                uncertain_item=r.resolution is not RegistrationResolution.RESOLVED,
            )
        )
    capability_rows = [
        record(
            c.callable_id,
            "capability",
            c.source_file,
            c.qualified_name,
            {c.callable_id},
            (c.definition,),
        )
        for c in extraction.callable_capabilities
    ]

    def ordered(rows: list[ScopeItemMembership]) -> tuple[ScopeItemMembership, ...]:
        return tuple(sorted(rows, key=lambda r: r.item_id))

    return (
        ordered(behavior_rows),
        ordered(relationship_rows),
        ordered(capability_rows),
        closed[selected.selector],
    )


def project_scope(
    full: VerificationInventory,
    inventory: ScopeInventory,
    root: ScopeRoot,
    findings: FindingUpdateResult,
) -> ScopedScanReport:
    explained = enrich_rejection_explanations(
        full.behaviors, full.matching, inventory, selected_owner=root.selector
    )
    details = {a.behavior_id: a.structured_explanation for a in explained.assessments}
    b_rows, r_rows, c_rows, closed = scope_membership(inventory, full.behaviors, root)
    membership = {row.item_id: row.membership for row in b_rows}
    inside = {key for key, value in membership.items() if value is ScopeMembership.IN_SCOPE}
    assessments = tuple(a for a in explained.assessments if a.behavior_id in inside)
    evidence_ids = {m.eval_id for a in assessments for m in a.matches}
    visible: dict[ScopeMembership, list[Finding]] = {status: [] for status in ScopeMembership}
    for f in findings.findings:
        if (
            f.status is FindingStatus.OPEN
            and f.current_disposition is not FindingDisposition.SUPPRESSED
        ):
            visible[membership.get(f.behavior_id, ScopeMembership.UNKNOWN)].append(
                with_guidance(
                    f.model_copy(update={"structured_explanation": details[f.behavior_id]})
                    if f.behavior_id in details
                    else f
                )
            )

    def counts(rows: tuple[ScopeItemMembership, ...]) -> dict[str, int]:
        found = Counter(row.membership.value for row in rows)
        return {status.value: found[status.value] for status in ScopeMembership}

    b_counts, r_counts = counts(b_rows), counts(r_rows)
    scope_complete = (
        closed
        and not b_counts[ScopeMembership.UNKNOWN]
        and not r_counts[ScopeMembership.UNKNOWN]
        and not any(row.membership is ScopeMembership.UNKNOWN for row in c_rows)
    )
    limits = tuple(
        dict.fromkeys(
            (
                *inventory.limitations,
                *root.limitations,
                "All repository behaviors/evals were matched before presentation filtering.",
                "Outside and unknown findings remain in repository-level state; "
                "they are not resolved by filtering.",
            )
        )
    )
    return ScopedScanReport(
        repository=full.discovery.repository.root or full.discovery.repository.requested_path,
        completeness=full.completeness,
        scope=ScopeSelection(
            root=root,
            behavior_counts=b_counts,
            relationship_counts=r_counts,
            finding_counts={status.value: len(visible[status]) for status in ScopeMembership},
            completeness=ScanCompleteness.COMPLETE
            if scope_complete
            else ScanCompleteness.INCOMPLETE,
            limitations=limits,
        ),
        behavior_membership=b_rows,
        relationship_membership=r_rows,
        capability_membership=c_rows,
        behaviors=tuple(b for b in full.behaviors.behaviors if b.behavior_id in inside),
        assessments=assessments,
        considered_evidence=tuple(s for s in full.evals.scenarios if s.eval_id in evidence_ids),
        findings=tuple(visible[ScopeMembership.IN_SCOPE]),
        out_of_scope_findings=tuple(visible[ScopeMembership.OUT_OF_SCOPE]),
        unknown_findings=tuple(visible[ScopeMembership.UNKNOWN]),
        repository_summary={
            "behaviors": len(full.behaviors.behaviors),
            "evals": len(full.evals.scenarios),
            "stored_findings": len(findings.findings),
            "open_findings": sum(f.status is FindingStatus.OPEN for f in findings.findings),
            "new": findings.new_count,
            "existing": findings.existing_count,
            "resolved": findings.resolved_count,
            "reopened": findings.reopened_count,
            "no_longer_observed": findings.no_longer_observed_count,
        },
        limitations=limits,
    )


def scan_selected_scope(
    repository: Path,
    selector: str,
    *,
    excludes: Sequence[str] = (),
    observed_at: datetime | None = None,
) -> ScopedScanReport:
    full = analyze_snapshot(repository, excludes)
    if full.completeness is ScanCompleteness.FAILED:
        errors = "; ".join(e.message for e in full.discovery.errors)
        raise ScopeSelectionError(
            "scope_scan_failed", errors or "Repository analysis failed; no scope was selected."
        )
    inventory = discover_scope_roots(full.discovery, full.behaviors)
    selected = select_scope(inventory, selector)
    explained = enrich_rejection_explanations(full.behaviors, full.matching, inventory)
    # Deliberately persist the complete inventory. Filtering never reaches lifecycle code.
    findings = update_findings(
        full.discovery.repository.root or repository,
        full.behaviors,
        explained,
        observed_at=observed_at,
    )
    return project_scope(full, inventory, selected, findings)
