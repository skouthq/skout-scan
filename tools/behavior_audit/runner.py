"""Compare source-curated expectations with existing extraction; never infer new behaviors."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from agentguard.extractors import extract_behaviors
from agentguard.models import Behavior, ScanCompleteness, SourceEvidence
from agentguard.scanners import scan_repository
from tools.behavior_audit.models import Corpus, Discovery, ExpectedBehavior, Role

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = PROJECT_ROOT / "tests/fixtures/behavior_audit/inventory.json"


def excerpt_free(value: Any) -> Any:
    """Keep audit artifacts source-reference-only, including nested provenance."""
    if isinstance(value, dict):
        return {k: excerpt_free(v) for k, v in value.items() if k != "excerpt"}
    if isinstance(value, list | tuple):
        return [excerpt_free(v) for v in value]
    return value


def _safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Audit source must be an existing file within its repository: {relative}")
    return path


def load_corpus(path: Path = DEFAULT_INVENTORY, *, project: Path = PROJECT_ROOT) -> Corpus:
    corpus = Corpus.model_validate_json(path.read_text(encoding="utf-8"))
    repositories = {repository.repository: repository for repository in corpus.repositories}
    if len(repositories) != len(corpus.repositories):
        raise ValueError("Duplicate audit repository identifier.")
    ids: set[tuple[str, str]] = set()
    for repository in corpus.repositories:
        root = (project / repository.path).resolve()
        if not root.is_relative_to(project.resolve()) or not root.is_dir():
            raise ValueError("Audit repositories must be explicitly curated within the project.")
        for file, digest in repository.source_hashes.items():
            if hashlib.sha256(_safe_file(root, file).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Source inventory is stale: {repository.repository}/{file}")
    for expected in corpus.expectations:
        key = expected.repository, expected.expectation_id
        if key in ids or expected.repository not in repositories:
            raise ValueError("Duplicate expectation ID or unknown repository.")
        ids.add(key)
        if expected.review_status not in {"confirmed", "uncertain", "unreviewed"}:
            raise ValueError("Unknown review status.")
        if expected.expected_discovery not in {"discovered", "not_discovered", "uncertain"}:
            raise ValueError("Unknown expected discovery status.")
        if expected.support_status not in {"supported", "unsupported", "negative_control"}:
            raise ValueError("Unknown support status.")
        root = (project / repositories[expected.repository].path).resolve()
        lines = _safe_file(root, expected.source_file).read_text(encoding="utf-8").splitlines()
        if not (expected.start_line <= expected.end_line <= len(lines)):
            raise ValueError(f"Invalid curated source span: {key}")
        if expected.source_anchor not in lines[expected.start_line - 1]:
            raise ValueError(f"Curated source anchor moved: {key}")
        if expected.source_file not in repositories[expected.repository].source_hashes:
            raise ValueError(f"Expected source is not pinned: {key}")
    return corpus


def _reference(root: Path, source_file: str, evidence: SourceEvidence) -> dict[str, Any]:
    path_correct = False
    location_correct = False
    try:
        path = _safe_file(root, evidence.source_file)
        path_correct = evidence.source_file == source_file
        lines = path.read_text(encoding="utf-8").splitlines()
        if (
            evidence.start_line is not None
            and evidence.end_line is not None
            and 1 <= evidence.start_line <= evidence.end_line <= len(lines)
        ):
            text = "\n".join(lines[evidence.start_line - 1 : evidence.end_line]).strip()
            location_correct = bool(evidence.excerpt.strip()) and evidence.excerpt.strip() in text
    except (OSError, UnicodeError, ValueError):
        pass
    return {
        "source_file": evidence.source_file,
        "source_symbol": evidence.source_symbol,
        "start_line": evidence.start_line,
        "end_line": evidence.end_line,
        "kind": evidence.kind,
        "path_correct": path_correct,
        "location_correct": location_correct,
    }


def _same_identity(expected: ExpectedBehavior, actual: Behavior) -> bool:
    return (
        actual.source_file == expected.source_file
        and actual.subject == expected.selector.subject
        and actual.source_symbol == expected.selector.source_symbol
    )


def _full_match(expected: ExpectedBehavior, actual: Behavior) -> bool:
    if not _same_identity(expected, actual):
        return False
    selector = expected.selector
    return (
        actual.behavior_type in selector.behavior_types
        and (
            selector.action_target is None
            or (actual.action is not None and actual.action.target == selector.action_target)
        )
        and (
            selector.action_outcome is None
            or (actual.action is not None and actual.action.outcome == selector.action_outcome)
        )
    )


def _span_matches(expected: ExpectedBehavior, actual: Behavior) -> bool:
    return any(
        e.source_file == expected.source_file
        and e.start_line is not None
        and e.end_line is not None
        and e.start_line <= expected.end_line
        and e.end_line >= expected.start_line
        for e in actual.evidence
    )


def classify_repository(
    root: Path,
    expectations: tuple[ExpectedBehavior, ...],
    actual: tuple[Behavior, ...],
    *,
    complete: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact authored selectors only; related container evidence never becomes full discovery."""
    records: list[dict[str, Any]] = []
    references = {
        b.behavior_id: [_reference(root, b.source_file, e) for e in b.evidence] for b in actual
    }
    candidates = {
        e.expectation_id: tuple(b for b in actual if _full_match(e, b)) for e in expectations
    }
    claims = Counter(b.behavior_id for matches in candidates.values() for b in matches)
    for expected in sorted(expectations, key=lambda e: e.expectation_id):
        full = candidates[expected.expectation_id]
        related = tuple(
            b
            for b in actual
            if (
                _same_identity(expected, b)
                and b.behavior_type in expected.selector.related_types
                and _span_matches(expected, b)
            )
        )
        if (
            expected.review_status != "confirmed"
            or expected.expected_discovery == "uncertain"
            or len(full) > 1
            or any(claims[b.behavior_id] > 1 for b in full)
        ):
            classification = Discovery.AMBIGUOUS
        elif expected.expected_discovery == "not_discovered":
            classification = (
                Discovery.UNEXPECTED
                if full
                else (Discovery.CORRECTLY_ABSENT if complete else Discovery.AMBIGUOUS)
            )
        elif full:
            valid = all(
                references[b.behavior_id]
                and all(
                    r["path_correct"] and r["location_correct"] for r in references[b.behavior_id]
                )
                and _span_matches(expected, b)
                for b in full
            )
            classification = Discovery.CORRECT if valid else Discovery.PARTIAL
        elif related:
            classification = Discovery.PARTIAL
        else:
            classification = Discovery.MISSED if complete else Discovery.AMBIGUOUS
        issue = None
        if classification in {Discovery.MISSED, Discovery.PARTIAL, Discovery.UNEXPECTED}:
            issue = expected.gap_category
            if full and classification is Discovery.PARTIAL:
                issue = "incorrect_source_reference"
        elif classification is Discovery.AMBIGUOUS:
            issue = (
                "unresolved_dynamic_registration"
                if expected.review_status == "uncertain"
                else "identity_ambiguity"
            )
        records.append(
            {
                "expectation": expected.model_dump(mode="json"),
                "classification": classification.value,
                "actual_ids": sorted(b.behavior_id for b in full),
                "related_actual_ids": sorted(b.behavior_id for b in related),
                "gap_category": issue,
                "observation": (
                    "Exact source/symbol/type/action and source span were found."
                    if classification is Discovery.CORRECT
                    else (
                        "Only registered-container or incomplete "
                        "source-reference evidence was found."
                    )
                    if classification is Discovery.PARTIAL
                    else "No exact behavior record was found in a complete extraction."
                    if classification is Discovery.MISSED
                    else "A confirmed non-agent control was promoted to a behavior."
                    if classification is Discovery.UNEXPECTED
                    else "No behavior record was found for the negative control."
                    if classification is Discovery.CORRECTLY_ABSENT
                    else "Expectation, correspondence, or extraction evidence remains uncertain."
                ),
                "root_cause_hypothesis": expected.root_cause_hypothesis if issue else None,
                "downstream_impact": (
                    {
                        "inventory": (
                            "Missing or partial operation/relationship in the behavior inventory."
                        ),
                        "eval_matching": (
                            "Cannot assess a missing behavior; this is not a matcher failure."
                        ),
                        "finding_selection": (
                            "No actionable finding can be selected for a missing behavior."
                        ),
                        "m8_explanations": (
                            "Can explain only the discovered behavior, not the omitted contract."
                        ),
                        "m9_comparison": (
                            "Cannot directly identify changes to an unrepresented behavior."
                        ),
                    }
                    if classification in {Discovery.MISSED, Discovery.PARTIAL}
                    else {
                        "inventory": "May include an internal detail as an agent behavior.",
                        "eval_matching": "May consider tests for a non-agent concern.",
                        "finding_selection": (
                            "May surface a low-value concern; no finding was created by this audit."
                        ),
                        "m8_explanations": (
                            "Source provenance can be correct while agent "
                            "registration is unjustified."
                        ),
                        "m9_comparison": (
                            "May treat internal edits as changes to an agent behavior."
                        ),
                    }
                    if classification is Discovery.UNEXPECTED
                    else None
                ),
            }
        )
    actual_records: list[dict[str, Any]] = []
    for behavior in sorted(actual, key=lambda b: b.behavior_id):
        exact = [r for r in records if behavior.behavior_id in r["actual_ids"]]
        reviewed = [
            r
            for r in exact
            if r["classification"]
            in {
                Discovery.CORRECT.value,
                Discovery.UNEXPECTED.value,
            }
        ]
        structural_valid = bool(reviewed) and all(
            r["classification"] == Discovery.CORRECT.value for r in reviewed
        )
        roles = {r["expectation"]["role"] for r in reviewed}
        relevance = {r["expectation"]["operational_relevance"] for r in reviewed}
        actual_records.append(
            {
                **behavior.model_dump(mode="json", exclude={"evidence", "arguments"}),
                "references": references[behavior.behavior_id],
                "review_status": "reviewed" if reviewed else "unreviewed",
                "structurally_valid": structural_valid if reviewed else None,
                "role": next(iter(roles)) if len(roles) == 1 else Role.UNKNOWN.value,
                "operational_relevance": next(iter(relevance))
                if len(relevance) == 1
                else "unknown",
                "matched_expectations": sorted(r["expectation"]["expectation_id"] for r in exact),
                "classification": (
                    "reviewed_valid"
                    if structural_valid
                    else "unexpected"
                    if reviewed
                    else "ambiguous"
                    if exact
                    else "unexpected_unreviewed"
                ),
            }
        )
    return records, actual_records


def _ratio(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def calculate_metrics(repositories: list[dict[str, Any]]) -> dict[str, Any]:
    records = [r for repo in repositories for r in repo["expectations"]]
    actual = [a for repo in repositories for a in repo["actual"]]
    confirmed = [
        r
        for r in records
        if (
            r["expectation"]["review_status"] == "confirmed"
            and r["expectation"]["expected_discovery"] == "discovered"
            and r["expectation"]["role"]
            in {Role.AGENT_FACING.value, Role.ORCHESTRATED_INTERNAL.value}
        )
    ]
    supported = [r for r in confirmed if r["expectation"]["support_status"] == "supported"]
    reviewed = [a for a in actual if a["review_status"] == "reviewed"]
    valid = [a for a in reviewed if a["structurally_valid"]]
    references = [ref for a in actual for ref in a["references"]]
    patterns = sorted({r["expectation"]["pattern"] for r in records})
    pattern_results = []
    for pattern in patterns:
        rows = [r for r in confirmed if r["expectation"]["pattern"] == pattern]
        all_rows = [r for r in records if r["expectation"]["pattern"] == pattern]
        counts = Counter(r["classification"] for r in rows)
        pattern_results.append(
            {
                "pattern": pattern,
                "confirmed_expected": len(rows),
                "correctly_discovered": counts[Discovery.CORRECT.value],
                "missed": counts[Discovery.MISSED.value],
                "partial": counts[Discovery.PARTIAL.value],
                "ambiguous": sum(
                    r["classification"] == Discovery.AMBIGUOUS.value for r in all_rows
                ),
                "unexpected_extractions": sum(
                    r["classification"] == Discovery.UNEXPECTED.value for r in all_rows
                ),
                "negative_controls": sum(
                    r["expectation"]["expected_discovery"] == "not_discovered" for r in all_rows
                ),
                "support_status": sorted({r["expectation"]["support_status"] for r in all_rows}),
            }
        )
    return {
        "discovery_recall": _ratio(
            sum(r["classification"] == Discovery.CORRECT.value for r in confirmed), len(confirmed)
        ),
        "supported_pattern_recall": _ratio(
            sum(r["classification"] == Discovery.CORRECT.value for r in supported), len(supported)
        ),
        "structural_discovery_precision": _ratio(len(valid), len(reviewed)),
        "precision_by_role": {
            role.value: _ratio(
                sum(a["structurally_valid"] and a["role"] == role.value for a in reviewed),
                sum(a["role"] == role.value for a in reviewed),
            )
            for role in Role
        },
        "excluded_unreviewed_extractions": len(actual) - len(reviewed),
        "excluded_uncertain_expectations": sum(
            r["expectation"]["review_status"] != "confirmed" for r in records
        ),
        "confirmed_expected": len(confirmed),
        "actual_records": len(actual),
        "negative_controls_correctly_absent": sum(
            r["classification"] == Discovery.CORRECTLY_ABSENT.value for r in records
        ),
        "unexpected_unreviewed": sum(
            a["classification"] == "unexpected_unreviewed" for a in actual
        ),
        "source_accuracy": {
            "references": len(references),
            "correct_paths": sum(r["path_correct"] for r in references),
            "incorrect_paths": sum(not r["path_correct"] for r in references),
            "correct_locations": sum(r["location_correct"] for r in references),
            "incorrect_locations": sum(not r["location_correct"] for r in references),
            "missing_references": sum(not a["references"] for a in actual),
        },
        "roles": {role.value: sum(a["role"] == role.value for a in actual) for role in Role},
        "operational_relevance": dict(
            sorted(Counter(a["operational_relevance"] for a in actual).items())
        ),
        "patterns": pattern_results,
        "limitations": [
            "Curated public/controlled corpus only; not production-wide precision or recall.",
            "Single source reviewer; no independent second-reviewer agreement measured.",
            (
                "Precision counts raw reviewed extraction records once, "
                "including distinct owner relationships."
            ),
            (
                "Operational importance/use is separate from structural "
                "correctness; registration is not reachability."
            ),
            (
                "Recall excludes uncertain expectations, includes confirmed "
                "unsupported patterns, and counts partial separately."
            ),
            (
                "Source accuracy checks real file paths, bounded spans, and "
                "matching source text, not runtime execution."
            ),
        ],
    }


def run_audit(corpus: Corpus, *, project: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Read only explicitly curated sources. No eval, matching, lifecycle, Git, or SQLite calls."""
    repositories: list[dict[str, Any]] = []
    for repository in sorted(corpus.repositories, key=lambda r: r.repository):
        root = (project / repository.path).resolve()
        if not root.is_relative_to(project.resolve()) or not root.is_dir():
            raise ValueError("Audit repositories must be explicitly curated within the project.")
        scan = scan_repository(root)
        extraction = extract_behaviors(scan)
        expected = tuple(e for e in corpus.expectations if e.repository == repository.repository)
        records, actual = classify_repository(
            root,
            expected,
            extraction.behaviors,
            complete=scan.completeness is ScanCompleteness.COMPLETE
            and extraction.completeness is ScanCompleteness.COMPLETE,
        )
        repositories.append(
            {
                **repository.model_dump(mode="json"),
                "expectations": records,
                "actual": actual,
                "callable_capabilities": [
                    c.model_dump(mode="json", exclude={"definition": {"excerpt"}})
                    for c in extraction.callable_capabilities
                ],
                "registration_relationships": [
                    excerpt_free(r.model_dump(mode="json"))
                    for r in extraction.registration_relationships
                ],
                "scan_completeness": scan.completeness.value,
                "extraction_completeness": extraction.completeness.value,
                "warnings": [
                    w.model_dump(mode="json") for w in (*scan.warnings, *extraction.warnings)
                ],
                "errors": [e.model_dump(mode="json") for e in (*scan.errors, *extraction.errors)],
            }
        )
    for repository_result in repositories:
        repository_result["metrics"] = calculate_metrics([repository_result])
    metrics = calculate_metrics(repositories)
    metrics["by_architecture"] = {
        architecture: calculate_metrics(
            [r for r in repositories if r["architecture"] == architecture]
        )
        for architecture in sorted({r["architecture"] for r in repositories})
    }
    return {
        "corpus_id": corpus.corpus_id,
        "inventory_provenance": corpus.provenance,
        "reviewer": corpus.reviewer,
        "repositories": repositories,
        "metrics": metrics,
    }


def serialize_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
