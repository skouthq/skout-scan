"""Read-only source-curated audit of bounded dispatch/delegation/fallback links."""

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from agentguard.extractors import extract_behaviors
from agentguard.extractors.delegation import DELEGATION_KINDS
from agentguard.models import RegistrationRelationship, RegistrationResolution, SourceEvidence
from agentguard.scanners import scan_repository
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report

INVENTORY = PROJECT_ROOT / "tests/fixtures/delegation_audit/inventory.json"


def source_references(r: RegistrationRelationship) -> tuple[SourceEvidence, ...]:
    return tuple(
        ref
        for ref in (
            r.registration,
            r.definition,
            r.registry_evidence,
            r.handler_evidence,
            *r.parent_provenance,
            *r.context_evidence,
        )
        if ref is not None
    )


def run_delegation_audit(
    inventory: Path = INVENTORY, *, project: Path = PROJECT_ROOT
) -> dict[str, Any]:
    truth = json.loads(inventory.read_text())
    ids = [r["repository"] for r in truth["repositories"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate delegation repository")
    seen = set()
    for e in truth["expectations"]:
        key = (
            e["repository"],
            e["source_file"],
            e["parent"],
            e["kind"],
            e["target"],
            e["dispatch_key"],
            e["exception_condition"],
            e["call_line"],
        )
        if (
            key in seen
            or e["repository"] not in ids
            or e["kind"] not in DELEGATION_KINDS
            or e["resolution"] not in {"resolved", "unresolved", "ambiguous"}
        ):
            raise ValueError("Invalid or duplicate delegation expectation")
        seen.add(key)
    repositories = []
    reviewed = []
    refs: list[bool] = []
    promotions = 0
    for repo in sorted(truth["repositories"], key=lambda r: r["repository"]):
        root = (project / repo["path"]).resolve()
        if not root.is_relative_to(project.resolve()) or not root.is_dir():
            raise ValueError("Delegation repository must be within the project")
        for name, digest in repo["sources"].items():
            path = (root / name).resolve()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("Delegation source inventory is stale or outside its root")
        scan = scan_repository(root)
        extraction = extract_behaviors(scan)
        actual = [r for r in extraction.registration_relationships if r.kind in DELEGATION_KINDS]
        caps = {c.callable_id: c for c in extraction.callable_capabilities}
        rows = []
        claimed = set()
        for e in (e for e in truth["expectations"] if e["repository"] == repo["repository"]):
            if e["source_file"] not in repo["sources"]:
                raise ValueError("Delegation expectation must pin its source")
            source = (root / e["source_file"]).read_text()
            functions = [
                n
                for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == e["parent"]
            ]
            if (
                len(functions) != 1
                or not functions[0].lineno <= e["call_line"] <= functions[0].end_lineno
                or e["anchor"] not in source.splitlines()[e["call_line"] - 1]
            ):
                raise ValueError("Delegation curated parent/anchor moved")
            matches = [
                r
                for r in actual
                if (
                    r.source_file == e["source_file"]
                    and r.owner_identity == f"{e['source_file']}#{e['parent']}"
                    and r.kind == e["kind"]
                    and r.referenced_symbol == e["target"]
                    and r.dispatch_key == e["dispatch_key"]
                    and r.exception_condition == e["exception_condition"]
                    and r.registration.start_line == e["call_line"]
                )
            ]
            correct = False
            if len(matches) == 1:
                r = matches[0]
                claimed.add(r.relationship_id)
                cap = caps.get(r.callable_id or "")
                parent = caps.get(r.parent_callable_id or "")
                positive = e["resolution"] == "resolved"
                target_correct = (
                    cap is not None
                    and cap.qualified_name == e["definition"]
                    and r.target_role == "orchestrated_internal"
                    and r.definition == cap.definition
                    if positive
                    else cap is None and r.definition is None and r.target_role is None
                )
                correct = bool(
                    r.resolution.value == e["resolution"]
                    and target_correct
                    and parent
                    and parent.qualified_name == e["parent"]
                    and r.parent_provenance
                    and all(reference_valid(root, ref) for ref in source_references(r))
                    and (r.kind != "literal_dispatch" or not positive or r.registry_evidence)
                    and (r.kind != "exception_fallback" or (r.handler_evidence and r.conditions))
                    and r.limitations
                )
                reviewed.append(
                    {
                        "kind": r.kind,
                        "resolved": r.resolution is RegistrationResolution.RESOLVED,
                        "expected_positive": positive,
                        "correct": correct,
                    }
                )
            rows.append(
                {
                    "expectation": e,
                    "correct": correct,
                    "actual_ids": sorted(r.relationship_id for r in matches),
                }
            )
        refs.extend(reference_valid(root, ref) for r in actual for ref in source_references(r))
        negative_sources = truth["negative_sources"].get(repo["repository"], [])
        promotions += sum(
            r.resolution is RegistrationResolution.RESOLVED
            and (
                r.source_file in negative_sources
                or not r.parent_provenance
                or r.target_role != "orchestrated_internal"
            )
            for r in actual
        )
        repositories.append(
            {
                **repo,
                "expectations": rows,
                "actual": [excerpt_free(r.model_dump(mode="json")) for r in actual],
                "scan_completeness": scan.completeness.value,
                "extraction_completeness": extraction.completeness.value,
                "unexpected_ids": sorted(
                    r.relationship_id for r in actual if r.relationship_id not in claimed
                ),
                "unexpected_resolved_ids": sorted(
                    r.relationship_id
                    for r in actual
                    if r.relationship_id not in claimed
                    and r.resolution is RegistrationResolution.RESOLVED
                ),
            }
        )
    rows = [r for repo in repositories for r in repo["expectations"]]
    positives = [r for r in rows if r["expectation"]["resolution"] == "resolved"]
    resolved_reviewed = [r for r in reviewed if r["resolved"]]
    return {
        "corpus": "delegation-audit-v1",
        "provenance": truth["provenance"],
        "repositories": repositories,
        "metrics": {
            "relationship_recall": {
                "numerator": sum(r["correct"] for r in positives),
                "denominator": len(positives),
            },
            "reviewed_resolved_precision": {
                "numerator": sum(r["correct"] for r in resolved_reviewed),
                "denominator": len(resolved_reviewed),
            },
            "resolution_outcomes": {
                "numerator": sum(r["correct"] for r in rows),
                "denominator": len(rows),
            },
            "by_kind": {
                kind: {
                    "numerator": sum(
                        r["correct"] for r in positives if r["expectation"]["kind"] == kind
                    ),
                    "denominator": sum(r["expectation"]["kind"] == kind for r in positives),
                }
                for kind in sorted(DELEGATION_KINDS)
            },
            "source_accuracy": {"correct": sum(refs), "denominator": len(refs)},
            "incorrect_promotions": promotions
            + sum(r["resolved"] and not r["expected_positive"] for r in reviewed),
            "unexpected_resolved": sum(len(r["unexpected_resolved_ids"]) for r in repositories),
            "unreviewed_extractions": sum(len(r["unexpected_ids"]) for r in repositories),
            "statuses": dict(
                sorted(
                    Counter(
                        r["resolution"] for repo in repositories for r in repo["actual"]
                    ).items()
                )
            ),
        },
        "limitations": truth["limitations"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_delegation_audit()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Delegation report must be a JSON file under docs/.")
        output.write_text(serialize_report(report))
    else:
        print(serialize_report(report), end="")


if __name__ == "__main__":
    main()
