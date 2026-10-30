"""Post-fix graph ownership audit; historical M10.2d evidence is retained separately."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.matchers.graph_ownership import check_graph_owner, is_conditional_graph_route
from agentguard.models import ComparisonBaseline
from tools.behavior_audit.obligation_audit import run_obligation_audit
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report

FIXTURE = "tests/fixtures/graph_ownership"


def run_graph_ownership_audit(*, project: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = (project / FIXTURE).resolve()
    if not root.is_relative_to(project.resolve()):
        raise ValueError("Ownership fixture must be within the project")
    truth = json.loads((root / "inventory.json").read_text())
    for name, digest in truth["sources"].items():
        source = (root / name).resolve()
        if (
            not source.is_relative_to(root)
            or not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Graph ownership source inventory is stale or outside its root")
    for name in ("pre_fix_assessments", "compatibility_baseline"):
        if (
            hashlib.sha256((root / f"{name}.json").read_bytes()).hexdigest()
            != truth[f"{name}_sha256"]
        ):
            raise ValueError("Pre-fix ownership observations changed")
    historical_path = project / "docs/verification-obligation-audit-m10-2d.json"
    if (
        hashlib.sha256(historical_path.read_bytes()).hexdigest()
        != truth["historical_report_sha256"]
    ):
        raise ValueError("Historical obligation audit changed")
    historical = json.loads(historical_path.read_text())
    current = run_obligation_audit(
        project / "tests/fixtures/obligation_audit/inventory.json", project=project
    )
    old_cases = {e["case"]["case_id"]: e for e in historical["evidence_experiments"]}
    original = []
    for now in current["evidence_experiments"]:
        if now["assessment"] is None:
            continue
        old = old_cases[now["case"]["case_id"]]
        if old["case"] != now["case"]:
            raise ValueError("Original independent evidence expectations changed")
        original.append(
            {
                "case": now["case"],
                "before": old["assessment"],
                "after": now["assessment"],
                "actual_covered": now["actual_covered"],
                "agrees_with_original_expectation": now["agrees_with_required_sufficiency"],
            }
        )
    snapshot = analyze_snapshot(root)
    previous = json.loads((root / "pre_fix_assessments.json").read_text())
    controls = []
    names = [c["name"] for c in truth["cases"]]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate ownership control")
    for case in truth["cases"]:
        b = next(
            b
            for b in snapshot.behaviors.behaviors
            if b.subject == case["owner"]
            and is_conditional_graph_route(b)
            and b.action
            and b.action.target == case["target"]
        )
        a = next(a for a in snapshot.matching.assessments if a.behavior_id == b.behavior_id)
        m = next(m for m in a.matches if m.name == case["name"])
        s = next(s for s in snapshot.evals.scenarios if s.eval_id == m.eval_id)
        old = next(
            (m for m in previous[b.behavior_id]["matches"] if m["name"] == case["name"]), None
        )
        ownership = check_graph_owner(b, s)
        refs = (*b.evidence, *s.evidence, *(r.evidence for r in s.referenced_symbols))
        controls.append(
            {
                "expectation": case,
                "before": old,
                "after": m.model_dump(mode="json"),
                "scenario": s.model_dump(mode="json"),
                "ownership": asdict(ownership),
                "source_references_valid": all(reference_valid(root, ref) for ref in refs),
                "correct": m.coverage_status is not None
                and m.coverage_status.value == case["expected"],
            }
        )
    baseline = json.loads((root / "compatibility_baseline.json").read_text())
    comparisons = []
    context = ComparisonBaseline(
        requested_ref="audit", resolved_commit="0" * 40, repository_root="[audit]", scan_path="."
    )
    for path, old in sorted(baseline.items()):
        now = analyze_snapshot(project / path)
        conditional = {
            b.behavior_id for b in now.behaviors.behaviors if is_conditional_graph_route(b)
        }
        old_assessments = {a["behavior_id"]: a for a in old["assessments"]}
        changed = [
            a
            for a in now.matching.assessments
            if a.model_dump(mode="json") != old_assessments[a.behavior_id]
        ]
        comparisons.append(
            {
                "repository": path,
                "behaviors_unchanged": hashlib.sha256(
                    json.dumps(
                        [b.model_dump(mode="json") for b in now.behaviors.behaviors], sort_keys=True
                    ).encode()
                ).hexdigest()
                == old["behaviors"],
                "relationships_unchanged": hashlib.sha256(
                    json.dumps(
                        [
                            r.model_dump(mode="json")
                            for r in now.behaviors.registration_relationships
                        ],
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                == old["relationships"],
                "finding_ids_unchanged": now.finding_ids == old["finding_ids"],
                "assessment_changes": [
                    {
                        "behavior_id": a.behavior_id,
                        "conditional_graph_route": a.behavior_id in conditional,
                        "before": old_assessments[a.behavior_id]["coverage_status"],
                        "after": a.coverage_status.value if a.coverage_status else None,
                    }
                    for a in changed
                ],
                "m9_same_snapshot": comparison_json(
                    compare_inventories(now, now, baseline=context, repository="[audit]")
                ),
            }
        )
    corrected = {
        e["case"]["case_id"]: e["actual_covered"]
        for e in original
        if e["case"]["case_id"]
        in {"route_wrong_owner", "route_helper_only", "pydantic_route_wrong_owner"}
    }
    return cast(
        dict[str, Any],
        excerpt_free(
            {
                "audit": "graph-route-evidence-ownership-v1",
                "provenance": truth["provenance"],
                "sources": truth["sources"],
                "historical_report": "docs/verification-obligation-audit-m10-2d.json",
                "historical_sha256": truth["historical_report_sha256"],
                "original_cases": original,
                "owner_controls": controls,
                "compatibility": comparisons,
                "metrics": {
                    "historical_agreement": historical["metrics"]["m8_experiment_agreement"],
                    "post_fix_original_agreement": current["metrics"]["m8_experiment_agreement"],
                    "three_original_false_coverage_corrected": {
                        "numerator": sum(v is False for v in corrected.values()),
                        "denominator": 3,
                    },
                    "control_agreement": {
                        "numerator": sum(c["correct"] for c in controls),
                        "denominator": len(controls),
                    },
                    "control_source_accuracy": {
                        "numerator": sum(c["source_references_valid"] for c in controls),
                        "denominator": len(controls),
                    },
                    "obligation_eligibility": current["metrics"]["reviewed_decisions"],
                },
                "limitations": [
                    (
                        "Legacy metadata.tools is not verified graph ownership; "
                        "the old route_supported positive is now partial."
                    ),
                    (
                        "Explicit graph_owner declares an eval subject, "
                        "not runtime invocation or passing execution."
                    ),
                    (
                        "No general aliases, compiled-variable tracing, graph reachability, "
                        "dispatch/fallback matching or callback-state verification."
                    ),
                ],
            }
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_graph_ownership_audit()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Ownership report must be a JSON file under docs/.")
        output.write_text(serialize_report(report))
    else:
        print(serialize_report(report), end="")


if __name__ == "__main__":
    main()
