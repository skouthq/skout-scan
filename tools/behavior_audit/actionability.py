"""Independent controlled guidance audit; never a product metric or lifecycle engine."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from agentguard.guidance import guidance_for_assessment
from tools.behavior_audit.actionability_cases import INVENTORY, load_cases
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.rejection_provenance import compatibility_snapshot
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report


def run_actionability_audit(*, project: Path = PROJECT_ROOT) -> dict[str, Any]:
    truth = json.loads((project / INVENTORY).read_text())
    ids = [c["case_id"] for c in truth["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate actionability case")
    for repo, sources in truth["source_hashes"].items():
        root = (project / repo).resolve()
        if not root.is_relative_to(project.resolve()):
            raise ValueError("Audit source must remain in project")
        for name, digest in sources.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Audit source must remain within its repository")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Pinned actionability source has changed")
    observations = []
    factual: list[bool] = []
    missing: list[bool] = []
    dimension_checks: list[bool] = []
    specific: list[bool] = []
    recommendations: list[bool] = []
    unsupported: list[bool] = []
    refs: list[bool] = []
    abstentions: list[bool] = []
    deterministic: list[bool] = []
    for case in load_cases(project=project):
        expected, assessment = case.expectation, case.assessment
        guidance = guidance_for_assessment(assessment)
        if guidance is None or assessment.structured_explanation is None:
            raise ValueError("Curated source-backed case unexpectedly lacks guidance")
        behavior = assessment.structured_explanation.behavior
        facts = expected["expected_facts"]
        # Claims must agree with independently pinned source expectations AND
        # the original Behavior, not merely a matching recommendation string.
        checks = [
            behavior.subject == facts["subject"] and facts["subject"] in guidance.behavior_summary,
            behavior.condition is not None
            and behavior.condition.expression == facts["condition"]
            and facts["condition"] in guidance.behavior_summary
            and facts["condition"] in guidance.verification_goal,
            behavior.action is not None and behavior.action.kind == facts["action"],
            behavior.action is not None
            and (behavior.action.outcome if facts["action"] == "raise" else behavior.action.target)
            == facts["outcome"]
            and facts["outcome"] in guidance.verification_goal
            and facts["outcome"] in guidance.behavior_summary,
        ]
        factual.extend(checks)
        actual_missing = [gap.dimension.value for gap in guidance.missing_evidence]
        expected_missing = expected["expected_missing_dimensions"]
        # Missing and extra dimensions both count against the case, never a union
        # of separate candidates. Preserve candidate order and closest ID exactly.
        missing.append(
            actual_missing
            == expected_missing
            == [d.value for d in assessment.structured_explanation.missing_dimensions]
        )
        dimension_checks.extend(
            dimension in actual_missing
            and dimension in [d.value for d in assessment.structured_explanation.missing_dimensions]
            for dimension in expected_missing
        )
        evidence_exact = (
            guidance.observed_evidence == assessment.matches
            and guidance.closest_eval_id == assessment.structured_explanation.closest_eval_id
        )
        action_checks = []
        for gap in guidance.missing_evidence:
            if not gap.suggested_action:
                continue
            if gap.dimension.value == "functionality":
                backed = behavior.source_file in gap.suggested_action
            elif gap.dimension.value == "condition":
                backed = facts["condition"] in gap.suggested_action
            else:
                backed = facts["outcome"] in gap.suggested_action
            action_checks.append(backed and gap.dimension.value in expected["allowed_actions"])
        specific.extend(action_checks)
        if expected["allowed_actions"]:
            recommendations.append(
                bool(action_checks)
                and all(action_checks)
                and {g.dimension.value for g in guidance.missing_evidence if g.suggested_action}
                == set(expected["allowed_actions"])
            )
        uncertain = guidance.interpretation == "analysis_uncertain"
        if expected["expected_uncertainty"]:
            abstentions.append(uncertain and not action_checks)
        text = " ".join(
            (guidance.behavior_summary, guidance.verification_goal, guidance.suggested_next_step)
        ).lower()
        unsupported.append(
            not all(checks)
            or not evidence_exact
            or actual_missing != expected_missing
            or not all(action_checks)
            or any(claim in text for claim in expected["forbidden_claims"])
            or uncertain != expected["expected_uncertainty"]
        )
        refs.extend(
            reference_valid(project / expected["repository"], ref)
            for ref in guidance.source_references
        )
        deterministic.append(guidance == guidance_for_assessment(assessment))
        observations.append(
            {
                "case": expected,
                "guidance": guidance.model_dump(mode="json"),
                "factual_claims_correct": checks,
                "evidence_preserved": evidence_exact,
                "missing_evidence_correct": missing[-1],
                "actions_source_backed": action_checks,
                "unsupported_recommendation": unsupported[-1],
            }
        )
    baseline = json.loads((project / INVENTORY.parent / "baseline.json").read_text())
    snapshots = {
        path: compatibility_snapshot(project / path) == digest
        for path, digest in baseline["technical_snapshots"].items()
    }
    reports = {
        name: hashlib.sha256((project / "docs" / name).read_bytes()).hexdigest() == digest
        for name, digest in baseline["prior_reports"].items()
    }

    def rate(values: list[bool]) -> dict[str, int]:
        return {"numerator": sum(values), "denominator": len(values)}

    return cast(
        dict[str, Any],
        excerpt_free(
            {
                "audit": "finding-actionability-v1",
                "human_usefulness": "not_yet_validated",
                "human_review": "pending",
                "metrics": {
                    "factual_correctness": rate(factual),
                    "missing_evidence_correctness": rate(dimension_checks),
                    "exact_missing_dimension_sets": rate(missing),
                    "action_specificity": rate(recommendations),
                    "source_backed_action_steps": rate(specific),
                    "unsupported_claim_rate": rate(unsupported),
                    "source_reference_accuracy": rate(refs),
                    "abstention_correctness": rate(abstentions),
                    "determinism": rate(deterministic),
                    "technical_compatibility": rate(list(snapshots.values())),
                    "prior_audit_compatibility": rate(list(reports.values())),
                },
                "observations": observations,
                "snapshots": snapshots,
                "prior_reports": reports,
                "limitations": [
                    "Curated correctness is not demonstrated engineer usefulness.",
                    "Single-candidate evidence views use the unchanged M8 matcher.",
                    "Partial/covered assessment contexts do not create new findings.",
                ],
            }
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = serialize_report(run_actionability_audit())
    if args.output:
        path = args.output.resolve()
        if path.suffix != ".json" or not path.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Guidance audit output must be JSON under docs/.")
        path.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
