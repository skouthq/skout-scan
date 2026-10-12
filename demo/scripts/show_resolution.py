"""Read-only demo evidence: join persisted matched IDs to statically parsed evals."""

from pathlib import Path

from agentguard.extractors import parse_eval_artifacts
from agentguard.feedback import FindingStore
from agentguard.models import CoverageStatus, FindingDisposition, FindingStatus
from agentguard.scanners import scan_repository


def main() -> None:
    root = Path.cwd()
    findings = [
        finding
        for finding in FindingStore(root).list_findings()
        if finding.behavior_subject == "validate_refund" and finding.source_file == "agent.py"
    ]
    if len(findings) != 1:
        raise SystemExit("Expected exactly one refund validator finding.")
    finding = findings[0]
    if (
        finding.status is not FindingStatus.RESOLVED
        or finding.coverage_status is not CoverageStatus.COVERED
        or finding.current_disposition is not FindingDisposition.ADD_EVAL
        or not finding.resolution_evidence
    ):
        raise SystemExit("Expected persisted add_eval, resolved and covered evidence.")
    scenarios = parse_eval_artifacts(
        scan_repository(root),
        known_tool_names={"lookup_order"},
        known_agent_names={"refund_agent"},
    ).scenarios
    matched = [
        scenario
        for scenario in scenarios
        if scenario.eval_id in finding.resolution_evidence.matched_eval_ids
    ]
    if not any(scenario.source_file == "tests/test_retry.py" for scenario in matched):
        raise SystemExit("The supplied solution is absent from resolution evidence.")
    print("Read-only persisted resolution evidence")
    print(f"Finding: {finding.finding_id}")
    print(f"Lifecycle: {finding.status.value} | Coverage: {finding.coverage_status.value}")
    print(f"Classification: {finding.current_disposition.value}")
    for scenario in matched:
        print(f"Matched eval: {scenario.source_file}")
        print(f"  {scenario.eval_id}")


if __name__ == "__main__":
    main()
