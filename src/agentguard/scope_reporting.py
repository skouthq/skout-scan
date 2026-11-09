"""Presentation for opt-in scope commands; ordinary scan rendering is untouched."""

from typing import cast

from pydantic import JsonValue
from rich.console import Console
from rich.table import Table

from agentguard.guidance import render_finding_guidance
from agentguard.models import ScopedScanReport, ScopeInventory, ScopeMembership
from agentguard.rejection_provenance import render_rejection_context


def scope_json(report: ScopeInventory | ScopedScanReport) -> JsonValue:
    """Follow comparison JSON conventions: references remain, source excerpts do not."""

    def clean(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key != "excerpt"}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(cast(JsonValue, report.model_dump(mode="json")))


def render_scope_inventory(output: Console, inventory: ScopeInventory) -> None:
    output.print("Selectable declared scopes", style="bold")
    table = Table()
    for column in ("Selector", "Framework", "Root kind", "Provenance", "Source"):
        table.add_column(column)
    for root in inventory.roots:
        line = root.evidence[0].start_line if root.evidence else None
        table.add_row(
            root.selector,
            root.framework,
            root.root_kind,
            root.resolution.value,
            f"{root.source_file}:{line or '?'}",
        )
    output.print(table)
    if inventory.roots:
        output.print("Copyable selectors:")
    for root in inventory.roots:
        output.print(f"  --scope '{root.selector}'", markup=False, soft_wrap=True)
        if root.has_opaque_configuration:
            output.print(
                f"  Incomplete declared surface for {root.selector}: "
                "expanded constructor arguments.",
                markup=False,
            )
    if not inventory.roots:
        output.print("No uniquely resolved supported roots were found.")
    if inventory.candidates:
        output.print("Unselectable root candidates:")
        for root in inventory.candidates:
            output.print(
                f"  {root.selector} ({root.root_kind}): {root.resolution.value}", markup=False
            )
    output.print(f"Discovery completeness: {inventory.completeness.value}", markup=False)
    for limitation in inventory.limitations:
        output.print(f"  Limitation: {limitation}", markup=False)
    output.print("Use skout scan . --scope 'relative/file.py#symbol' to select a listed root.")


def render_scoped_scan(output: Console, report: ScopedScanReport) -> None:
    scope = report.scope
    output.print(f"Repository: {report.repository}", markup=False)
    output.print(f"Selected scope: {scope.root.selector}", style="bold", markup=False)
    output.print(
        f"Framework: {scope.root.framework}; root kind: {scope.root.root_kind}", markup=False
    )
    output.print(f"Scan completeness: {report.completeness.value}", markup=False)
    output.print(f"Scope attribution completeness: {scope.completeness.value}", markup=False)
    table = Table(title="Selected structural surface")
    table.add_column("Membership")
    table.add_column("Behaviors", justify="right")
    table.add_column("Open findings", justify="right")
    for status in ScopeMembership:
        table.add_row(
            status.value,
            str(scope.behavior_counts[status.value]),
            str(scope.finding_counts[status.value]),
        )
    output.print(table)
    output.print(
        f"Repository-wide behaviors: {report.repository_summary['behaviors']}; "
        f"repository-wide stored findings: {report.repository_summary['stored_findings']}",
        markup=False,
    )
    output.print(
        f"Repository-wide lifecycle: {report.repository_summary['resolved']} resolved, "
        f"{report.repository_summary['reopened']} reopened.",
        markup=False,
    )
    output.print(
        f"Scoped open findings: {len(report.findings)} (suppressed findings omitted)", markup=False
    )
    for finding in report.findings:
        output.print(
            f"  {finding.finding_id}: {finding.title} [{finding.source_file}]", markup=False
        )
        if not render_finding_guidance(output, finding, compact=True):
            render_rejection_context(output, finding.structured_explanation)
    for status, findings in (
        (ScopeMembership.OUT_OF_SCOPE, report.out_of_scope_findings),
        (ScopeMembership.UNKNOWN, report.unknown_findings),
    ):
        output.print(
            f"{status.value} open findings (not presented as in-scope): {len(findings)}",
            markup=False,
        )
        for finding in findings[:25]:
            output.print(
                f"  {finding.finding_id}: {finding.source_file}::{finding.behavior_subject}",
                markup=False,
            )
        if len(findings) > 25:
            output.print("  More diagnostics are available with --json.")
    for status in (ScopeMembership.OUT_OF_SCOPE, ScopeMembership.UNKNOWN):
        rows = [r for r in report.behavior_membership if r.membership is status]
        output.print(f"{status.value} behavior diagnostics: {len(rows)}", markup=False)
        for row in rows[:25]:
            output.print(
                f"  {row.item_id}: {row.source_file}::{row.source_symbol or '?'} — {row.reason}",
                markup=False,
            )
        if len(rows) > 25:
            output.print("  More diagnostics are available with --json.")
    output.print(
        f"Considered eval candidates for in-scope behaviors: {len(report.considered_evidence)}",
        markup=False,
    )
    output.print("Candidate evidence is not automatically sufficient verification.")
    output.print(
        "Use --json for selected behaviors, assessments, considered evidence and all diagnostics."
    )
    for limitation in scope.limitations:
        output.print(f"  Limitation: {limitation}", markup=False)
