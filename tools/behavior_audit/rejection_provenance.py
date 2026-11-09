"""Source-pinned explanation-only audit; no lifecycle, execution or source inference."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from agentguard.comparison import analyze_snapshot, compare_inventories, comparison_json
from agentguard.findings import select_findings
from agentguard.models import ComparisonBaseline
from agentguard.rejection_provenance import enrich_rejection_explanations, rejection_provenance
from agentguard.scopes import discover_scope_roots, scope_membership
from tools.behavior_audit.registrations import reference_valid
from tools.behavior_audit.runner import PROJECT_ROOT, excerpt_free, serialize_report

FIXTURE = Path("tests/fixtures/rejection_audit")


def compatibility_snapshot(path: Path) -> str:
    """Exact pre-M10.2e raw M8, finding, identity, relationship, scope and M9 contract."""
    full = analyze_snapshot(path)
    scopes = discover_scope_roots(full.discovery, full.behaviors)
    selected = select_findings(
        full.behaviors, full.matching, observed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    payload = {
        "behaviors": full.behaviors.model_dump(mode="json"),
        "evals": full.evals.model_dump(mode="json"),
        "matching": full.matching.model_dump(mode="json"),
        "findings": selected.model_dump(mode="json"),
        "scopes": scopes.model_dump(mode="json"),
        "memberships": {
            r.selector: [
                [x.model_dump(mode="json") for x in rows] if isinstance(rows, tuple) else rows
                for rows in scope_membership(scopes, full.behaviors, r)
            ]
            for r in scopes.roots
        },
        "m9": comparison_json(
            compare_inventories(
                full,
                full,
                baseline=ComparisonBaseline(
                    requested_ref="audit",
                    resolved_commit="0" * 40,
                    repository_root="[audit]",
                    scan_path=".",
                ),
                repository="[audit]",
            )
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_rejection_audit(*, project: Path = PROJECT_ROOT) -> dict[str, Any]:
    root = project / FIXTURE
    truth = json.loads((root / "inventory.json").read_text())
    for name, digest in truth["source_hashes"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Audit source must remain inside its fixture root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Pinned rejection audit source has changed")
    full = analyze_snapshot(root)
    inventory = discover_scope_roots(full.discovery, full.behaviors)
    contexts = rejection_provenance(full.behaviors, inventory)
    explained = enrich_rejection_explanations(full.behaviors, full.matching, inventory)
    observations = []
    eligible, enriched, expected_owners, correct_owners, observed_owners = 0, 0, 0, 0, 0
    abstentions, abstention_total, dedup, dedup_total = 0, 0, 0, 0
    reviewed: set[str] = set()
    for expectation in truth["expectations"]:
        matches = [
            c
            for c in contexts
            if c.source_file == expectation["source_file"]
            and c.source_symbol == expectation["symbol"]
            and c.condition.normalized_expression == expectation["condition"]
            and c.outcome.outcome == expectation["outcome"]
        ]
        expected = set(expectation["owners"])
        actual = {owner for c in matches for owner in c.owner_identities}
        if expected:
            eligible += 1
            enriched += int(len(matches) == 1 and actual == expected)
            expected_owners += len(expected)
            observed_owners += sum(len(c.owner_identities) for c in matches)
            correct_owners += len(actual & expected)
            dedup_total += 1
            dedup += int(len(matches) == 1 and len(matches[0].related_behavior_ids) == 2)
        else:
            abstention_total += 1
            abstentions += int(not matches)
        reviewed.update(c.primary_behavior_id for c in matches)
        observations.append(
            {
                "expectation": expectation,
                "provenance": [c.model_dump(mode="json") for c in matches],
                "correct": (len(matches) == 1 and actual == expected) if expected else not matches,
            }
        )
    refs = [
        ref
        for c in contexts
        for ref in (
            *c.source_evidence,
            *(
                ref
                for r in c.registrations
                for ref in (
                    *r.owner_evidence,
                    r.registration_evidence,
                    r.callable_evidence,
                )
            ),
        )
    ]
    old = [a.model_dump(mode="json") for a in full.matching.assessments]
    new = [
        a.model_dump(mode="json", exclude={"structured_explanation": {"rejection_provenance"}})
        for a in explained.assessments
    ]
    before = select_findings(
        full.behaviors, full.matching, observed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    after = select_findings(full.behaviors, explained, observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    finding_equal = [f.model_dump(mode="json") for f in before.findings] == [
        f.model_dump(mode="json", exclude={"structured_explanation": {"rejection_provenance"}})
        for f in after.findings
    ]
    baseline = json.loads((root / "compatibility_baseline.json").read_text())
    snapshots = {
        name: compatibility_snapshot(project / name) == expected
        for name, expected in sorted(baseline["repositories"].items())
    }
    reports = {
        name: hashlib.sha256((project / "docs" / name).read_bytes()).hexdigest() == digest
        for name, digest in sorted(baseline["reports"].items())
    }

    def metric(n: int, d: int) -> dict[str, int]:
        return {"numerator": n, "denominator": d}

    return cast(
        dict[str, Any],
        excerpt_free(
            {
                "audit": "rejection-provenance-v1",
                "human_review": "pending",
                "metrics": {
                    "eligible_enrichment_recall": metric(enriched, eligible),
                    "owner_attribution_precision": metric(correct_owners, observed_owners),
                    "owner_attribution_recall": metric(correct_owners, expected_owners),
                    "deduplication_correctness": metric(dedup, dedup_total),
                    "source_reference_accuracy": metric(
                        sum(reference_valid(root, r) for r in refs), len(refs)
                    ),
                    "abstention_correctness": metric(abstentions, abstention_total),
                    "assessment_preservation": metric(
                        sum(a == b for a, b in zip(old, new, strict=True)), len(old)
                    ),
                    "finding_preservation": metric(int(finding_equal), 1),
                    "historical_inventory_snapshots": metric(
                        sum(snapshots.values()), len(snapshots)
                    ),
                    "historical_audit_reports": metric(sum(reports.values()), len(reports)),
                },
                "observations": observations,
                "snapshots": snapshots,
                "prior_reports": reports,
                "context_controls": truth["context_controls"],
                "unreviewed_enrichment_count": len(
                    {c.primary_behavior_id for c in contexts} - reviewed
                ),
                "limitations": [
                    "Controlled source-first expectations; independent human review pending.",
                    "No claim about runtime execution, actionable gaps or behavioral recall.",
                    "Raw M8 judgments are preserved, including their existing limitations.",
                ],
            }
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = serialize_report(run_rejection_audit())
    if args.output:
        output = args.output.resolve()
        if output.suffix != ".json" or not output.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Rejection audit output must be JSON under docs/.")
        output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
