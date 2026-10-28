"""Development-only independent registration audit; no matching or lifecycle writes."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from agentguard.extractors import extract_behaviors
from agentguard.models import SourceEvidence
from agentguard.scanners import scan_repository
from tools.behavior_audit.runner import PROJECT_ROOT, load_corpus, run_audit, serialize_report

CORPUS_ROOT = PROJECT_ROOT / "tests/fixtures/registration_audit"


def reference_valid(root: Path, evidence: SourceEvidence) -> bool:
    path = (root / evidence.source_file).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return False
    lines = path.read_text().splitlines()
    start, end = evidence.start_line, evidence.end_line
    return (
        start is not None
        and end is not None
        and 1 <= start <= end <= len(lines)
        and bool(evidence.excerpt.strip())
        and evidence.excerpt.strip() in "\n".join(lines[start - 1 : end])
    )


def run_registration_audit(root: Path = CORPUS_ROOT) -> dict[str, Any]:
    truth = json.loads((root / "inventory.json").read_text())
    for file, digest in truth["sources"].items():
        path = (root / file).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Registration source inventory is stale or outside its corpus")
    extraction = extract_behaviors(scan_repository(root))
    capabilities = {c.callable_id: c for c in extraction.callable_capabilities}
    rows = []
    claimed: set[str] = set()
    for expected in truth["expectations"]:
        owner = f"{expected['source_file']}#{expected['owner']}"
        matches = [
            r
            for r in extraction.registration_relationships
            if r.owner_identity == owner and r.referenced_symbol == expected["referenced_symbol"]
        ]
        correct = False
        if len(matches) == 1:
            relationship = matches[0]
            claimed.add(relationship.relationship_id)
            cap = capabilities.get(relationship.callable_id or "")
            correct = (
                relationship.resolution.value == expected["resolution"]
                and relationship.framework == expected["framework"]
                and (cap.qualified_name if cap else None) == expected["qualified_name"]
                and relationship.registration.start_line == expected["registration_line"]
            )
        rows.append(
            {
                "expectation": expected,
                "correct": correct,
                "actual_ids": sorted(r.relationship_id for r in matches),
            }
        )
    resolved = [
        r for r in extraction.registration_relationships if r.resolution.value == "resolved"
    ]
    reviewed_resolved = [r for r in resolved if r.relationship_id in claimed]
    expected_positive = [r for r in rows if r["expectation"]["resolution"] == "resolved"]
    correct_positive = sum(r["correct"] for r in expected_positive)
    actual = [
        r.model_dump(mode="json", exclude={"registration": {"excerpt"}, "definition": {"excerpt"}})
        for r in extraction.registration_relationships
    ]
    refs = [
        ref
        for r in extraction.registration_relationships
        for ref in (r.registration, r.definition)
        if ref is not None
    ]
    bound = [
        r
        for r in expected_positive
        if f"{r['expectation']['source_file']}#{r['expectation']['qualified_name']}"
        in truth["bound_methods"]
    ]
    unverified_owners = set(truth["forbidden_owners"]) | {
        f"{r['expectation']['source_file']}#{r['expectation']['owner']}"
        for r in rows
        if r["expectation"]["resolution"] != "resolved"
    }
    false_ownership = sum(
        r.resolution.value == "resolved" and r.owner_identity in unverified_owners
        for r in extraction.registration_relationships
    )
    unexpected = [
        r.relationship_id
        for r in extraction.registration_relationships
        if r.relationship_id not in claimed
    ]
    return {
        "corpus": "registration-audit-v1",
        "provenance": truth["provenance"],
        "source_hashes": truth["sources"],
        "expectations": rows,
        "actual": actual,
        "capabilities": [
            c.model_dump(mode="json", exclude={"definition": {"excerpt"}})
            for c in extraction.callable_capabilities
        ],
        "metrics": {
            "registration_recall": {
                "numerator": correct_positive,
                "denominator": len(expected_positive),
            },
            "reviewed_registration_precision": {
                "numerator": correct_positive,
                "denominator": len(reviewed_resolved),
            },
            "reviewed_resolution_outcomes": {
                "numerator": sum(r["correct"] for r in rows),
                "denominator": len(rows),
            },
            "bound_method_resolution": {
                "numerator": sum(r["correct"] for r in bound),
                "denominator": len(bound),
            },
            "unknown_or_ambiguous": len(rows) - len(expected_positive),
            "incorrect_ownership_promotions": false_ownership,
            "shared_fixture": {
                "capabilities": sum(c.source_file == "shared.py" for c in capabilities.values()),
                "distinct_owners": len(
                    {r.owner_identity for r in resolved if r.source_file == "shared.py"}
                ),
            },
            "unexpected_unreviewed": len(unexpected),
            "excluded_unreviewed_resolved": len(resolved) - len(reviewed_resolved),
            "source_accuracy": {
                "correct": sum(reference_valid(root, ref) for ref in refs),
                "denominator": len(refs),
            },
            "statuses": dict(
                sorted(
                    Counter(
                        r.resolution.value for r in extraction.registration_relationships
                    ).items()
                )
            ),
        },
        "unexpected_ids": unexpected,
        "limits": [
            "Curated corpus, single source reviewer; not production-wide quality.",
            "Registration is not runtime execution or qualifying eval evidence.",
            (
                "Unresolved/ambiguous relationships are excluded from resolved precision "
                "and positive recall."
            ),
        ],
    }


def run_report() -> dict[str, Any]:
    original = run_audit(load_corpus())
    registration = run_registration_audit()
    registration["original_behavior_metrics"] = original["metrics"]
    registration["original_corpus_relationships"] = [
        {
            "repository": repo["repository"],
            "relationships": repo.get("registration_relationships", []),
            "capabilities": repo.get("callable_capabilities", []),
        }
        for repo in original["repositories"]
    ]
    return registration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Registration audit output must be a JSON report under docs/.")
        output.write_text(serialize_report(run_report()))
    else:
        print(serialize_report(run_report()), end="")


if __name__ == "__main__":
    main()
