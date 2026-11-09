"""Curated M11 evidence views over existing fixtures; not a new evaluation engine."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentguard.comparison import VerificationInventory, analyze_snapshot
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import BehaviorCoverageAssessment
from agentguard.rejection_provenance import enrich_rejection_explanations
from agentguard.scopes import discover_scope_roots
from tools.behavior_audit.runner import PROJECT_ROOT

INVENTORY = Path("tests/fixtures/actionability_audit/inventory.json")


@dataclass(frozen=True)
class GuidanceCase:
    expectation: dict[str, Any]
    full: VerificationInventory
    assessment: BehaviorCoverageAssessment


def load_cases(*, project: Path = PROJECT_ROOT) -> tuple[GuidanceCase, ...]:
    truth = json.loads((project / INVENTORY).read_text())
    cases = []
    for case in truth["cases"]:
        root = (project / case["repository"]).resolve()
        if not root.is_relative_to(project.resolve()):
            raise ValueError("Actionability cases must remain inside project")
        full = analyze_snapshot(root, case.get("excludes", ()))
        scenarios = full.evals.scenarios
        if case.get("eval_names") is not None:
            scenarios = tuple(s for s in scenarios if s.name in case["eval_names"])
        if case.get("eval_source"):
            scenarios = tuple(s for s in scenarios if s.source_type.value == case["eval_source"])
        evals = full.evals.model_copy(update={"scenarios": scenarios})
        matching = match_behaviors_to_evals(full.behaviors, evals)
        inventory = discover_scope_roots(full.discovery, full.behaviors)
        matching = enrich_rejection_explanations(full.behaviors, matching, inventory)
        selected = [
            b
            for b in full.behaviors.behaviors
            if b.source_file == case["source_file"]
            and b.subject == case["subject"]
            and b.behavior_type.value == case["behavior_type"]
            and (not case.get("outcome") or b.action and b.action.outcome == case["outcome"])
            and (not case.get("target") or b.action and b.action.target == case["target"])
        ]
        if len(selected) != 1:
            raise ValueError(f"Case {case['case_id']} does not identify one existing behavior")
        assessment = next(
            a for a in matching.assessments if a.behavior_id == selected[0].behavior_id
        )
        cases.append(GuidanceCase(case, full, assessment))
    return tuple(cases)
