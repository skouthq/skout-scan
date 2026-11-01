"""Independent controlled audit of explicit structural scope membership, without persistence."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agentguard.comparison import analyze_snapshot
from agentguard.findings import select_findings
from agentguard.models import FindingUpdateResult, ScopeMembership
from agentguard.scopes import discover_scope_roots, project_scope, select_scope
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report

INVENTORY = PROJECT_ROOT / "tests/fixtures/scope_audit/inventory.json"


def run_scope_audit(inventory: Path = INVENTORY, *, project: Path = PROJECT_ROOT) -> dict[str, Any]:
    truth = json.loads(inventory.read_text())
    repos = {r["repository"]: r for r in truth["repositories"]}
    if len(repos) != len(truth["repositories"]):
        raise ValueError("Duplicate scope repository")
    expectation_ids = [e["expectation_id"] for e in truth["expectations"]]
    if len(expectation_ids) != len(set(expectation_ids)) or any(
        e["repository"] not in repos for e in truth["expectations"]
    ):
        raise ValueError("Duplicate or unknown scope expectation")
    results = []
    evaluated: list[dict[str, Any]] = []
    finding_rows: list[dict[str, Any]] = []
    ref_valid: list[bool] = []
    for name, repo in sorted(repos.items()):
        root = (project / repo["path"]).resolve()
        if not root.is_relative_to(project.resolve()) or not root.is_dir():
            raise ValueError("Scope corpus must be within the project")
        for file, digest in repo["source_hashes"].items():
            path = (root / file).resolve()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("Scope source inventory is stale or outside its root")
        full = analyze_snapshot(root)
        roots = discover_scope_roots(full.discovery, full.behaviors)
        expected_roots = next(
            e["selectors"] for e in truth["root_expectations"] if e["repository"] == name
        )
        root_correct = sorted(r.selector for r in roots.roots) == sorted(expected_roots)
        refs = [e for r in (*roots.roots, *roots.candidates) for e in r.evidence]
        ref_valid.extend(reference_valid(root, ref) for ref in refs)
        selections = []
        expectations = [e for e in truth["expectations"] if e["repository"] == name]
        for selector in sorted({e["selector"] for e in expectations}):
            selected = select_scope(roots, selector)
            # Pure finding selection only; no FindingStore or lifecycle update.
            findings = FindingUpdateResult(
                findings=select_findings(full.behaviors, full.matching).findings
            )
            view = project_scope(full, roots, selected, findings)
            rows = []
            for e in (e for e in expectations if e["selector"] == selector):
                if e["source_file"] not in repo["source_hashes"]:
                    raise ValueError("Scope expectation must pin its source")
                if e["item_kind"] == "behavior":
                    ids = {
                        b.behavior_id
                        for b in full.behaviors.behaviors
                        if b.source_file == e["source_file"] and b.subject == e["symbol"]
                    }
                    matches = [r for r in view.behavior_membership if r.item_id in ids]
                elif e["item_kind"] == "capability":
                    matches = [
                        r
                        for r in view.capability_membership
                        if r.source_file == e["source_file"] and r.source_symbol == e["symbol"]
                    ]
                elif e["item_kind"] == "relationship":
                    ids = {
                        r.relationship_id
                        for r in full.behaviors.registration_relationships
                        if r.source_file == e["source_file"]
                        and r.kind == e["relationship_kind"]
                        and r.owner_identity == f"{e['source_file']}#{e['owner']}"
                        and r.referenced_symbol == e["target"]
                    }
                    matches = [r for r in view.relationship_membership if r.item_id in ids]
                else:
                    raise ValueError("Unsupported scope expectation kind")
                correct = bool(matches) and all(
                    r.membership.value == e["membership"] for r in matches
                )
                rows.append(
                    {
                        "expectation": e,
                        "correct": correct,
                        "actual_ids": [r.item_id for r in matches],
                    }
                )
                for r in matches:
                    evaluated.append(
                        {
                            "selector": selector,
                            "expected": e["membership"],
                            "actual": r.membership.value,
                            "correct": r.membership.value == e["membership"],
                            "item_id": r.item_id,
                            "repository": name,
                        }
                    )
                if not matches:
                    evaluated.append(
                        {
                            "selector": selector,
                            "expected": e["membership"],
                            "actual": None,
                            "correct": False,
                            "item_id": e["expectation_id"],
                            "repository": name,
                        }
                    )
            for e in (
                e
                for e in truth["finding_expectations"]
                if e["repository"] == name and e["selector"] == selector
            ):
                actual = {
                    status.value: getattr(view, attr)
                    for status, attr in (
                        (ScopeMembership.IN_SCOPE, "findings"),
                        (ScopeMembership.OUT_OF_SCOPE, "out_of_scope_findings"),
                        (ScopeMembership.UNKNOWN, "unknown_findings"),
                    )
                }
                expected_findings = [
                    f for f in findings.findings if f.behavior_subject == e["subject"]
                ]
                for f in expected_findings:
                    found = next(
                        (
                            status
                            for status, values in actual.items()
                            if any(v.finding_id == f.finding_id for v in values)
                        ),
                        None,
                    )
                    finding_rows.append(
                        {
                            "expectation": e,
                            "finding_id": f.finding_id,
                            "actual": found,
                            "correct": found == e["membership"],
                        }
                    )
            refs = [
                ref
                for r in (
                    *view.behavior_membership,
                    *view.relationship_membership,
                    *view.capability_membership,
                )
                for ref in r.evidence
            ]
            ref_valid.extend(reference_valid(root, ref) for ref in refs)
            selections.append(
                {
                    "selector": selector,
                    "scope": view.scope.model_dump(mode="json"),
                    "expectations": rows,
                    "behavior_membership": [
                        r.model_dump(mode="json") for r in view.behavior_membership
                    ],
                    "relationship_membership": [
                        r.model_dump(mode="json") for r in view.relationship_membership
                    ],
                    "capability_membership": [
                        r.model_dump(mode="json") for r in view.capability_membership
                    ],
                }
            )
        results.append(
            {
                "repository": name,
                "source_hashes": repo["source_hashes"],
                "roots": roots.model_dump(mode="json"),
                "root_inventory_correct": root_correct,
                "selections": selections,
            }
        )
    # Count each (repository, scope, item) once, even if curated groups overlap.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for reviewed_row in evaluated:
        key = (reviewed_row["repository"], reviewed_row["selector"], reviewed_row["item_id"])
        if key in unique and unique[key]["expected"] != reviewed_row["expected"]:
            raise ValueError("Conflicting source-curated scope expectations")
        unique[key] = reviewed_row
    reviewed = list(unique.values())
    all_item_count = sum(
        len(s["behavior_membership"])
        + len(s["relationship_membership"])
        + len(s["capability_membership"])
        for r in results
        for s in r["selections"]
    )

    def quality(actual: str | None = None, expected: str | None = None) -> dict[str, int]:
        rows = [
            r
            for r in reviewed
            if (actual is None or r["actual"] == actual)
            and (expected is None or r["expected"] == expected)
        ]
        return {"numerator": sum(r["correct"] for r in rows), "denominator": len(rows)}

    def findings_quality(status: str) -> dict[str, int]:
        rows = [r for r in finding_rows if r["expectation"]["membership"] == status]
        return {"numerator": sum(r["correct"] for r in rows), "denominator": len(rows)}

    report = {
        "audit": "agent-scope-v1",
        "provenance": truth["provenance"],
        "repositories": results,
        "finding_expectations": finding_rows,
        "metrics": {
            "membership_precision": quality(actual="in_scope"),
            "membership_recall": quality(expected="in_scope"),
            "exclusion_precision": quality(actual="out_of_scope"),
            "unknown_correctness": quality(expected="unknown"),
            "reviewed_membership": quality(),
            "unreviewed_membership_items": all_item_count - len(unique),
            "root_discovery": {
                "numerator": sum(r["root_inventory_correct"] for r in results),
                "denominator": len(results),
            },
            "source_accuracy": {"numerator": sum(ref_valid), "denominator": len(ref_valid)},
            "relevant_findings_retained": findings_quality("in_scope"),
            "known_outside_findings_excluded": findings_quality("out_of_scope"),
            "unknown_findings_preserved_as_diagnostics": findings_quality("unknown"),
        },
        "limitations": [
            (
                "Controlled structural membership only, not deployment/reachability "
                "or engineer-validated finding relevance."
            ),
            (
                "Human review pending; source-first expectations do not establish "
                "operational actionability."
            ),
            "No target execution, matcher changes, persistence or source call-graph expansion.",
        ],
    }
    clean = excerpt_free(report)
    assert isinstance(clean, dict)
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_scope_audit()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Scope report must be a JSON file under docs/.")
        output.write_text(serialize_report(report))
    else:
        print(serialize_report(report), end="")


if __name__ == "__main__":
    main()
