"""Independent, read-only obligation eligibility/evidence audit; no production integration."""

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from agentguard.extractors import extract_behaviors, parse_eval_artifacts
from agentguard.matchers import match_behaviors_to_evals
from agentguard.models import BehaviorExtractionResult, CoverageStatus, EvalParseResult
from agentguard.scanners import scan_repository
from tools.behavior_audit.obligation_models import (
    Eligibility,
    ExpectedObligation,
    ObligationCandidate,
    ObligationCorpus,
)
from tools.behavior_audit.obligations import map_obligations
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report

INVENTORY = PROJECT_ROOT / "tests/fixtures/obligation_audit/inventory.json"


def _root(project: Path, relative: str) -> Path:
    root = (project / relative).resolve()
    if not root.is_relative_to(project.resolve()) or not root.is_dir():
        raise ValueError("Obligation repository must be within the project")
    return root


def _pin(root: Path, file: str, digest: str) -> None:
    path = (root / file).resolve()
    if (
        not path.is_relative_to(root)
        or not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != digest
    ):
        raise ValueError("Obligation inventory source is stale or outside its root")


def _matches(c: ObligationCandidate, e: ExpectedObligation) -> bool:
    return (
        c.source_file == e.source_file
        and c.subject == e.subject
        and c.relationship_kind == e.relationship_kind
        and c.obligation_type == e.obligation_type
        and c.dispatch_key == e.dispatch_key
        and c.exception_condition == e.exception_condition
        and c.target_symbol == e.target_symbol
    )


def run_obligation_audit(
    inventory: Path = INVENTORY, *, project: Path = PROJECT_ROOT
) -> dict[str, Any]:
    truth = ObligationCorpus.model_validate_json(inventory.read_text())
    repository_ids = [r.repository for r in truth.repositories]
    if len(repository_ids) != len(set(repository_ids)):
        raise ValueError("Duplicate obligation repository")
    expectation_ids = [e.expectation_id for e in truth.expectations]
    if len(expectation_ids) != len(set(expectation_ids)):
        raise ValueError("Duplicate obligation expectation")
    if (
        any(e.repository not in repository_ids for e in truth.expectations)
        or any(e.repository not in repository_ids for e in truth.absence_expectations)
        or any(e.repository not in repository_ids for e in truth.evidence_cases)
    ):
        raise ValueError("Unknown obligation repository")
    evidence_root = _root(project, truth.evidence_root)
    for name, digest in truth.evidence_hashes.items():
        _pin(evidence_root, name, digest)
    evals = parse_eval_artifacts(scan_repository(evidence_root))
    extracted: dict[str, BehaviorExtractionResult] = {}
    candidates: dict[str, tuple[ObligationCandidate, ...]] = {}
    repositories: list[dict[str, Any]] = []
    reviewed: list[dict[str, Any]] = []
    candidate_refs: list[bool] = []
    refs: list[bool] = []
    for repo in sorted(truth.repositories, key=lambda r: r.repository):
        root = _root(project, repo.path)
        for name, digest in repo.source_hashes.items():
            _pin(root, name, digest)
        full = extract_behaviors(scan_repository(root))
        extraction = full.model_copy(
            update={
                "behaviors": tuple(
                    b for b in full.behaviors if b.source_file in repo.source_hashes
                ),
                "registration_relationships": tuple(
                    r
                    for r in full.registration_relationships
                    if r.source_file in repo.source_hashes
                ),
                "callable_capabilities": tuple(
                    c for c in full.callable_capabilities if c.source_file in repo.source_hashes
                ),
            }
        )
        extracted[repo.repository] = extraction
        mapping = map_obligations(extraction)
        candidates[repo.repository] = mapping.candidates
        rows = []
        claimed = set()
        for e in (e for e in truth.expectations if e.repository == repo.repository):
            if e.source_file not in repo.source_hashes:
                raise ValueError("Obligation expectation must pin its source")
            lines = (root / e.source_file).read_text().splitlines()
            if not 1 <= e.source_line <= len(lines) or e.anchor not in lines[e.source_line - 1]:
                raise ValueError("Obligation source anchor moved")
            matches = [c for c in mapping.candidates if _matches(c, e)]
            correct = False
            if len(matches) == 1:
                c = matches[0]
                if c.candidate_id in claimed:
                    raise ValueError("Duplicate ground truth selects the same candidate")
                claimed.add(c.candidate_id)
                correspondence = (
                    not c.existing_behavior_ids
                    if e.existing_behavior_subject is None
                    else c.classification == "existing_behavior_enrichment"
                    and any(
                        b.subject == e.existing_behavior_subject
                        and b.behavior_id in c.existing_behavior_ids
                        for b in extraction.behaviors
                    )
                )
                correct = (
                    c.eligibility is e.eligibility
                    and c.matcher_compatibility is e.matcher_compatibility
                    and c.evidence_requirement.dimensions == e.required_dimensions
                    and len(c.originating_relationship_ids) >= e.minimum_origins
                    and correspondence
                    and all(reference_valid(root, ref) for ref in c.source_evidence)
                    and any(
                        ref.source_file == e.source_file
                        and ref.start_line is not None
                        and ref.end_line is not None
                        and ref.start_line <= e.source_line <= ref.end_line
                        for ref in c.source_evidence
                    )
                )
            row = {
                "expectation": e.model_dump(mode="json"),
                "correct": correct,
                "actual_ids": [c.candidate_id for c in matches],
            }
            rows.append(row)
            if e.review_status == "confirmed":
                reviewed.append(
                    {
                        "expected": e,
                        "actual": matches[0] if len(matches) == 1 else None,
                        "correct": correct,
                    }
                )
        for c in mapping.candidates:
            valid = [reference_valid(root, ref) for ref in c.source_evidence]
            candidate_refs.append(bool(valid) and all(valid))
            refs.extend(valid)
        absent = []
        for absence in truth.absence_expectations:
            if absence.repository != repo.repository:
                continue
            if (
                absence.source_file not in repo.source_hashes
                or absence.anchor not in (root / absence.source_file).read_text()
            ):
                raise ValueError("Absence expectation source must be pinned")
            absent.append(
                {
                    "expectation": absence.model_dump(mode="json"),
                    "correct": not any(
                        c.source_file == absence.source_file for c in mapping.candidates
                    ),
                }
            )
        repositories.append(
            {
                "repository": repo.repository,
                "path": repo.path,
                "source_hashes": repo.source_hashes,
                "expectations": rows,
                "absence_expectations": absent,
                "candidates": [excerpt_free(c.model_dump(mode="json")) for c in mapping.candidates],
                "raw_eligible_mappings": mapping.raw_eligible_mappings,
                "duplicates_removed": mapping.duplicates_removed,
                "unreviewed_ids": sorted(
                    c.candidate_id for c in mapping.candidates if c.candidate_id not in claimed
                ),
            }
        )

    experiments = []
    for case in truth.evidence_cases:
        if case.evidence_file not in truth.evidence_hashes:
            raise ValueError("Evidence case must pin its artifact")
        scenarios = [
            s
            for s in evals.scenarios
            if s.source_file == case.evidence_file and s.name == case.scenario
        ]
        if len(scenarios) != 1:
            raise ValueError(f"Evidence case must identify one extracted scenario: {case.case_id}")
        matched = [
            c
            for c in candidates[case.repository]
            if c.subject == case.subject
            and c.obligation_type == case.obligation_type
            and c.target_symbol == case.target_symbol
            and c.eligibility is Eligibility.ELIGIBLE
        ]
        if case.obligation_type == "literal_route_selection":
            matched = [c for c in matched if c.dispatch_key == "search"]
        if len(matched) != 1:
            raise ValueError(f"Evidence case must identify one eligible claim: {case.case_id}")
        c = matched[0]
        source = extracted[case.repository]
        existing = [b for b in source.behaviors if b.behavior_id == c.obligation_id]
        assessment = None
        if existing:
            # Exactly the current Behavior and EvalScenario; no synthetic behavior or new evaluator.
            matching = match_behaviors_to_evals(
                source.model_copy(update={"behaviors": tuple(existing)}),
                EvalParseResult(scenarios=(scenarios[0],), completeness=evals.completeness),
            )
            assessment = matching.assessments[0]
        actual_covered = (
            assessment.coverage_status is CoverageStatus.COVERED if assessment else None
        )
        experiments.append(
            {
                "case": case.model_dump(mode="json"),
                "candidate_id": c.candidate_id,
                "matcher_compatibility": c.matcher_compatibility.value,
                "qualifies_for_matching": scenarios[0].qualifies_for_matching,
                "source_references_valid": all(
                    reference_valid(evidence_root, ref)
                    for ref in (
                        *scenarios[0].evidence,
                        *(a.evidence for a in scenarios[0].assertions),
                        *(r.evidence for r in scenarios[0].referenced_symbols),
                    )
                ),
                "scenario": excerpt_free(scenarios[0].model_dump(mode="json")),
                "assessment": excerpt_free(assessment.model_dump(mode="json"))
                if assessment
                else None,
                "actual_covered": actual_covered,
                "agrees_with_required_sufficiency": actual_covered == case.should_cover
                if actual_covered is not None
                else None,
                "limitation": None
                if assessment
                else "No existing Behavior represents this relationship claim; M8 was not run.",
            }
        )

    eligible = [
        r
        for r in reviewed
        if r["actual"] is not None and r["actual"].eligibility is Eligibility.ELIGIBLE
    ]
    expected_eligible = [r for r in reviewed if r["expected"].eligibility is Eligibility.ELIGIBLE]
    abstentions = [r for r in reviewed if r["expected"].eligibility is not Eligibility.ELIGIBLE]

    def quality(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {"numerator": sum(r["correct"] for r in rows), "denominator": len(rows)}

    raw_reviewed = len(reviewed) + sum(
        max(0, r["actual"].raw_eligible_mappings - 1) for r in reviewed if r["actual"] is not None
    )
    duplicate_count = raw_reviewed - len(reviewed)
    all_candidates = [c for values in candidates.values() for c in values]
    new_ids = [
        (repository, c.obligation_id)
        for repository, values in candidates.items()
        for c in values
        if c.obligation_id
    ]
    return {
        "corpus": truth.corpus_id,
        "provenance": truth.provenance,
        "repositories": repositories,
        "evidence_experiments": experiments,
        "metrics": {
            "eligibility_precision": quality(eligible),
            "eligibility_recall": quality(expected_eligible),
            "reviewed_decisions": quality(reviewed),
            "by_relationship_type": {
                kind: {
                    "precision": quality(
                        [r for r in eligible if r["expected"].relationship_kind == kind]
                    ),
                    "recall": quality(
                        [r for r in expected_eligible if r["expected"].relationship_kind == kind]
                    ),
                    "decisions": quality(
                        [r for r in reviewed if r["expected"].relationship_kind == kind]
                    ),
                }
                for kind in sorted({r["expected"].relationship_kind for r in reviewed})
            },
            "pre_dedup_duplicate_rate": {"numerator": duplicate_count, "denominator": raw_reviewed},
            "residual_duplicate_rate": {
                "numerator": len(new_ids) - len(set(new_ids)),
                "denominator": len(all_candidates),
            },
            "source_traceability": {
                "numerator": sum(candidate_refs),
                "denominator": len(candidate_refs),
            },
            "source_references": {"numerator": sum(refs), "denominator": len(refs)},
            "abstention_correctness": {
                "numerator": sum(
                    r["actual"] is not None and r["actual"].eligibility is not Eligibility.ELIGIBLE
                    for r in abstentions
                ),
                "denominator": len(abstentions),
            },
            "actionability_proxy": {
                "numerator": sum(
                    r["correct"]
                    and r["expected"].actionable_proxy
                    and bool(
                        r["actual"].functionality
                        and r["actual"].condition
                        and r["actual"].expected_outcome
                    )
                    for r in eligible
                ),
                "denominator": len(eligible),
            },
            "unreviewed_candidates": sum(len(r["unreviewed_ids"]) for r in repositories),
            "statuses": dict(sorted(Counter(c.eligibility.value for c in all_candidates).items())),
            "m8_experiment_agreement": {
                "numerator": sum(
                    e["agrees_with_required_sufficiency"] is True for e in experiments
                ),
                "denominator": sum(e["assessment"] is not None for e in experiments),
            },
            "experiments_requiring_new_contract": sum(e["assessment"] is None for e in experiments),
        },
        "limitations": [
            "Curated source-only corpus; one source reviewer, not production-wide quality.",
            "Actionability is a testability proxy, not validated engineer intent.",
            "Eligibility is not coverage or high-confidence finding selection.",
            (
                "M8 disagreements are reported without changing matching "
                "or inventing replacement evidence."
            ),
            (
                "Dedup measures relationship join fanout and equivalent existing behaviors; "
                "no persisted identities are created."
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_obligation_audit()
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Obligation report must be a JSON file under docs/.")
        output.write_text(serialize_report(report))
    else:
        print(serialize_report(report), end="")


if __name__ == "__main__":
    main()
