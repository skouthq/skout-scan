"""Development audit of orchestration facts, independently from behavior/eval coverage."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from agentguard.extractors import extract_behaviors
from agentguard.extractors.orchestration import ORCHESTRATION_KINDS
from agentguard.models import RegistrationResolution
from agentguard.scanners import scan_repository
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

INVENTORY = PROJECT_ROOT / "tests/fixtures/orchestration_audit/inventory.json"


def run_orchestration_audit(
    inventory: Path = INVENTORY,
    *,
    project: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    truth = json.loads(inventory.read_text())
    repository_ids = [r["repository"] for r in truth["repositories"]]
    if len(set(repository_ids)) != len(repository_ids):
        raise ValueError("Duplicate orchestration repository")
    keys = set()
    for e in truth["expectations"]:
        key = (
            e["repository"],
            e["source_file"],
            e["kind"],
            e["owner"],
            e["registered_identity"],
            e["referenced_symbol"],
        )
        if (
            key in keys
            or e["repository"] not in repository_ids
            or e["kind"] not in ORCHESTRATION_KINDS
            or e["resolution"] not in {"resolved", "unresolved", "ambiguous"}
        ):
            raise ValueError("Invalid or duplicate orchestration expectation")
        keys.add(key)
    repositories: list[dict[str, Any]] = []
    reviewed: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    reference_results: list[bool] = []
    for repository in sorted(truth["repositories"], key=lambda r: r["repository"]):
        root = (project / repository["path"]).resolve()
        if not root.is_relative_to(project.resolve()) or not root.is_dir():
            raise ValueError("Orchestration audit repository must be within the project")
        for name, digest in repository["sources"].items():
            path = (root / name).resolve()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("Orchestration source inventory is stale or outside its root")
        extraction = extract_behaviors(scan_repository(root))
        actual = [r for r in extraction.registration_relationships if r.kind in ORCHESTRATION_KINDS]
        capabilities = {c.callable_id: c for c in extraction.callable_capabilities}
        expected = [e for e in truth["expectations"] if e["repository"] == repository["repository"]]
        rows = []
        claimed: set[str] = set()
        for expectation in expected:
            if expectation["source_file"] not in repository["sources"]:
                raise ValueError("Orchestration expectation source must be pinned")
            lines = (root / expectation["source_file"]).read_text().splitlines()
            if not 1 <= expectation["registration_line"] <= len(lines):
                raise ValueError("Orchestration source location is invalid")
            anchor = expectation["evidence"].split(": ", 1)[1]
            if anchor not in lines[expectation["registration_line"] - 1]:
                raise ValueError("Orchestration curated anchor moved")
            matches = [
                r
                for r in actual
                if (
                    r.source_file == expectation["source_file"]
                    and r.kind == expectation["kind"]
                    and r.owner_identity == f"{expectation['source_file']}#{expectation['owner']}"
                    and r.registered_identity == expectation["registered_identity"]
                    and r.referenced_symbol == expectation["referenced_symbol"]
                )
            ]
            correct = False
            if len(matches) == 1:
                relationship = matches[0]
                claimed.add(relationship.relationship_id)
                target_correct = (
                    (
                        relationship.executor_identity
                        == f"{expectation['source_file']}#{expectation['referenced_symbol']}"
                        if relationship.kind == "task_agent_executor"
                        else (
                            relationship.callable_id in capabilities
                            and capabilities[relationship.callable_id].qualified_name
                            == expectation["referenced_symbol"]
                        )
                    )
                    if expectation["resolution"] == "resolved"
                    else (
                        relationship.callable_id is None
                        and relationship.executor_identity is None
                        and relationship.definition is None
                    )
                )
                correct = (
                    relationship.resolution.value == expectation["resolution"]
                    and relationship.framework == expectation["framework"]
                    and relationship.registration.start_line == expectation["registration_line"]
                    and target_correct
                    and (
                        expectation["resolution"] != "resolved"
                        or (
                            relationship.definition is not None
                            and relationship.definition.source_file == expectation["source_file"]
                            and relationship.definition.source_symbol
                            == expectation["referenced_symbol"]
                        )
                    )
                    and reference_valid(root, relationship.registration)
                    and (
                        relationship.definition is None
                        or reference_valid(root, relationship.definition)
                    )
                )
                reviewed.append(
                    {
                        "relationship_id": relationship.relationship_id,
                        "resolved": relationship.resolution is RegistrationResolution.RESOLVED,
                        "framework": relationship.framework,
                        "correct": correct,
                        "expected_resolution": expectation["resolution"],
                    }
                )
            rows.append(
                {
                    "expectation": expectation,
                    "correct": correct,
                    "actual_ids": sorted(r.relationship_id for r in matches),
                }
            )
        refs = [ref for r in actual for ref in (r.registration, r.definition) if ref is not None]
        reference_results.extend(reference_valid(root, ref) for ref in refs)
        all_rows.extend(rows)
        repositories.append(
            {
                **repository,
                "expectations": rows,
                "actual": [
                    r.model_dump(
                        mode="json",
                        exclude={"registration": {"excerpt"}, "definition": {"excerpt"}},
                    )
                    for r in actual
                ],
                "capabilities": [
                    c.model_dump(mode="json", exclude={"definition": {"excerpt"}})
                    for c in extraction.callable_capabilities
                    if any(r.callable_id == c.callable_id for r in actual)
                ],
                "unexpected_ids": sorted(
                    r.relationship_id for r in actual if r.relationship_id not in claimed
                ),
                "incorrect_ownership_promotions": sum(
                    r.source_file == truth["negative_source"]
                    and r.resolution is RegistrationResolution.RESOLVED
                    for r in actual
                ),
            }
        )
    positives = [r for r in all_rows if r["expectation"]["resolution"] == "resolved"]
    resolved = [r for r in reviewed if r["resolved"]]
    return {
        "corpus": "orchestration-audit-v1",
        "provenance": truth["provenance"],
        "repositories": repositories,
        "metrics": {
            "orchestration_recall": {
                "numerator": sum(r["correct"] for r in positives),
                "denominator": len(positives),
            },
            "reviewed_resolved_precision": {
                "numerator": sum(r["correct"] for r in resolved),
                "denominator": len(resolved),
            },
            "resolution_outcomes": {
                "numerator": sum(r["correct"] for r in all_rows),
                "denominator": len(all_rows),
            },
            "by_framework": {
                framework: {
                    "numerator": sum(
                        r["correct"] and r["expectation"]["framework"] == framework
                        for r in positives
                    ),
                    "denominator": sum(
                        r["expectation"]["framework"] == framework for r in positives
                    ),
                }
                for framework in ["LangGraph", "CrewAI", "Pydantic AI"]
            },
            "source_accuracy": {
                "correct": sum(reference_results),
                "denominator": len(reference_results),
            },
            "incorrect_ownership_promotions": sum(
                r["incorrect_ownership_promotions"] for r in repositories
            )
            + sum(r["resolved"] and r["expected_resolution"] != "resolved" for r in reviewed),
            "unreviewed_extractions": sum(len(r["unexpected_ids"]) for r in repositories),
            "expected_unknown_or_ambiguous": len(all_rows) - len(positives),
            "statuses": dict(
                sorted(Counter(a["resolution"] for r in repositories for a in r["actual"]).items())
            ),
        },
        "limitations": truth["limitations"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Orchestration report must be a JSON file under docs/.")
        output.write_text(serialize_report(run_orchestration_audit()))
    else:
        print(serialize_report(run_orchestration_audit()), end="")


if __name__ == "__main__":
    main()
