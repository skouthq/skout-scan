"""Controlled terminal presentation audit over existing source-backed M11 cases."""

import argparse
import json
import tempfile
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from shutil import copytree, ignore_patterns
from typing import Any

from rich.cells import cell_len
from rich.console import Console
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.feedback import FindingStore
from agentguard.guidance import guidance_for_assessment
from tools.behavior_audit.actionability_cases import load_cases
from tools.behavior_audit.rejection_provenance import compatibility_snapshot
from tools.behavior_audit.runner import PROJECT_ROOT, serialize_report

BASELINE = PROJECT_ROOT / "tests/fixtures/presentation_audit/baseline.json"
PRE_POLISH = BASELINE.parent / "pre_polish.json"
REPOSITORIES = {
    "validator": ("examples/pydantic-ai-agent", None),
    "tool_evidence": ("tests/fixtures/rejection_audit", None),
    "graph_public": ("examples/langgraph-agent", None),
    "graph": ("tests/fixtures/graph_ownership", None),
    "shared_scoped": ("tests/fixtures/scope_audit/agents", "alpha"),
    "multiple": ("tests/fixtures/scope_audit/agents", None),
}


def normalize(value: Any, workspace: Path) -> Any:
    if isinstance(value, dict):
        return {
            k: normalize(v, workspace)
            for k, v in value.items()
            if k
            not in {"first_seen", "last_seen", "occurred_at", "scanned_at", "scan_id", "event_id"}
        }
    if isinstance(value, list):
        return [normalize(v, workspace) for v in value]
    if isinstance(value, str):
        return value.replace(str(workspace), "[workspace]")
    return value


def capture() -> dict[str, Any]:
    """Actual commands on copied repositories; never touch developer feedback."""
    runner = CliRunner()
    results = {}
    for name, (relative, scope) in REPOSITORIES.items():
        with tempfile.TemporaryDirectory(prefix="skout-presentation-") as directory:
            # Skout resolves the repository path. Match that spelling even
            # when the system temporary directory is accessed through a symlink.
            root = Path(directory).resolve() / "repository"
            copytree(
                PROJECT_ROOT / relative,
                root,
                ignore=ignore_patterns(".agentguard", ".venv", "__pycache__", ".pytest_cache"),
            )

            def cli(*args: str, input_text: str | None = None, root: Path = root) -> str:
                result = runner.invoke(
                    app,
                    list(args),
                    input=input_text,
                    terminal_width=100,
                    env={"COLUMNS": "100", "NO_COLOR": "1", "TTY_COMPATIBLE": "0"},
                )
                if result.exit_code:
                    raise AssertionError(result.output) from result.exception
                output = result.output.replace(str(root), "[workspace]")
                # Rich may move the absolute path onto the next line. The
                # placeholder fits on the heading line on every host.
                return output.replace("Repository: \n[workspace]", "Repository: [workspace]")

            scan_args = ["scan", str(root), "--no-progress"]
            if scope:
                scan_args.extend(["--scope", scope])
            commands = {"scan": cli(*scan_args)}
            store = FindingStore(root)
            before = (root / ".agentguard/agentguard.db").read_bytes()
            for command in ("findings", "review"):
                for details in (False, True):
                    args = [command, "--repository", str(root)]
                    if details:
                        args.append("--details")
                    commands[command + ("_details" if details else "")] = cli(
                        *args, input_text="skip\n" * 100 if command == "review" else None
                    )
            metrics = json.loads(cli("metrics", "--repository", str(root), "--json"))
            scopes = json.loads(cli("scopes", str(root), "--json"))
            after = (root / ".agentguard/agentguard.db").read_bytes()
            scoped = None
            if scope:
                scoped = json.loads(cli("scan", str(root), "--scope", scope, "--json"))
            results[name] = {
                "repository": relative,
                "scope": scope,
                "commands": commands,
                "metrics": normalize(metrics, root),
                "scopes": normalize(scopes, root),
                "scoped_json": normalize(scoped, root),
                "read_only_views": before == after,
                "technical_snapshot": compatibility_snapshot(root),
                "finding_ids": [f.finding_id for f in store.list_findings()],
            }
    contexts = {}
    for case in load_cases():
        guidance = guidance_for_assessment(case.assessment)
        assert guidance is not None
        contexts[case.expectation["case_id"]] = {
            "kind": "existing M11 assessment context; not a selected finding",
            "assessment": case.assessment.model_dump(mode="json"),
            "guidance": guidance.model_dump(mode="json"),
        }
    return {"repositories": results, "assessment_contexts": contexts}


def run_presentation_audit() -> dict[str, Any]:
    from agentguard.presentation import (
        ASCII_ICONS,
        ICONS,
        FindingPresentation,
        render_diagnostics,
        render_summary,
        view_for_assessment,
    )
    from tools.behavior_audit.registrations import reference_valid

    truth = json.loads((BASELINE.parent / "inventory.json").read_text())
    expected_icons = truth["polish_rules"]["section_icons"]
    before = json.loads(BASELINE.read_text())
    after = capture()
    previous = json.loads(PRE_POLISH.read_text())
    checks: dict[str, list[bool]] = {
        key: []
        for key in (
            "required_content_completeness",
            "evidence_statement_correctness",
            "action_preservation",
            "source_reference_accuracy",
            "full_id_accessibility",
            "narrow_terminal_layout",
            "json_compatibility",
            "deterministic_rendering",
            "primary_section_uniqueness",
            "connected_behavior",
            "callable_identity_display",
            "section_icons",
            "major_section_spacing",
            "ascii_fallback",
            "source_role_grouping",
        )
    }
    observations = []
    for case in load_cases():
        expected = case.expectation
        identifier = expected["case_id"]
        view = view_for_assessment(case.assessment)

        def render(width: int, details: bool = False, view: FindingPresentation = view) -> str:
            stream = StringIO()
            output = Console(
                file=stream, width=width, color_system=None, highlight=False, force_terminal=False
            )
            render_summary(output, view)
            if details:
                render_diagnostics(output, view)
            return stream.getvalue()

        text = render(100)
        compact = " ".join(text.split())
        facts = expected["expected_facts"]
        checks["required_content_completeness"].extend(
            [
                all(section in text for section in truth["required_sections"]),
                facts["subject"] in compact,
                facts["condition"] in compact,
                facts["outcome"] in compact,
                expected["source_file"] in view.source,
            ]
        )
        state = truth["evidence_states"][identifier]
        evidence = " ".join(view.evidence)
        correct = (
            "No qualifying eval candidates discovered." in evidence
            if state == "none"
            else "Qualifying verification evidence was found." in evidence
            if state == "covered"
            else "graph identity is ambiguous" in evidence
            if state == "ambiguous"
            else "does not verify the identity of this graph" in evidence
            if state == "owner"
            else "inconclusive" in evidence
            if state == "uncertain"
            else "Closest eval:" in evidence and "Still missing:" in evidence
        )
        checks["evidence_statement_correctness"].append(correct)
        actions = expected["allowed_actions"]
        next_step = view.next_step.lower()
        action_checks = [
            ("test " in next_step or "target this" in next_step) == ("functionality" in actions),
            ("condition above" in next_step) == ("condition" in actions),
            ("assert" in next_step) == ("expected_outcome" in actions),
            not any(claim in compact.lower() for claim in expected["forbidden_claims"]),
        ]
        checks["action_preservation"].append(all(action_checks))
        checks["connected_behavior"].append(
            f"If {facts['condition']} → " in compact and facts["outcome"] in compact
        )
        checks["callable_identity_display"].append(
            not actions
            or (
                not view.next_step.startswith(("Test ", "For "))
                if identifier in truth["unresolved_callable_cases"]
                else view.next_step.count(facts["subject"]) == 1
            )
        )
        full = render(100, True)
        full_lines = full.splitlines()
        expected_headings = {
            section: f"{icon} {section}" + ("" if section == "Additional details" else ":")
            for section, icon in expected_icons.items()
        }
        checks["section_icons"].extend(
            heading in full_lines for heading in expected_headings.values()
        )
        for section in truth["polish_rules"]["blank_line_before"]:
            heading = expected_headings[section]
            at = full_lines.index(heading) if heading in full_lines else 0
            checks["major_section_spacing"].append(
                at >= 2 and full_lines[at - 1] == "" and full_lines[at - 2] != ""
            )
        sink = BytesIO()
        stream = TextIOWrapper(sink, encoding="ascii", errors="strict")
        terminal = Console(file=stream, width=60, color_system=None, force_terminal=False)
        render_summary(terminal, view)
        render_diagnostics(terminal, view)
        stream.flush()
        ascii_text = sink.getvalue().decode("ascii")
        checks["ascii_fallback"].append(
            all(f"{icon} {heading}" in ascii_text for heading, icon in ASCII_ICONS.items())
            and all(len(line) <= 60 for line in ascii_text.splitlines())
            and "\x1b[" not in ascii_text
        )

        guidance = view.guidance
        assert guidance is not None
        checks["source_reference_accuracy"].extend(
            reference_valid(PROJECT_ROOT / expected["repository"], ref)
            for ref in guidance.source_references
        )
        checks["deterministic_rendering"].append(text == render(100))
        for width in truth["widths"]:
            primary, detailed = render(width), render(width, True)
            checks["narrow_terminal_layout"].append(
                detailed.startswith(primary)
                and all(cell_len(line) <= width for line in detailed.splitlines())
                and "…" not in detailed
            )
        checks["primary_section_uniqueness"].append(
            all(text.count(s) == 1 for s in truth["required_sections"])
        )
        observations.append(
            {
                "case": identifier,
                "context": "existing assessment; not promoted to finding",
                "evidence_state": state,
                "primary": text,
                "details": render(100, True),
                "evidence_correct": correct,
                "action_checks": action_checks,
            }
        )
    for name, row in after["repositories"].items():
        old = before["repositories"][name]
        for key in (
            "metrics",
            "scopes",
            "scoped_json",
            "technical_snapshot",
            "finding_ids",
            "read_only_views",
        ):
            checks["json_compatibility"].append(row[key] == old[key])
        for identity in row["finding_ids"]:
            checks["full_id_accessibility"].append(identity in row["commands"]["findings_details"])
    checks["json_compatibility"].append(
        before["assessment_contexts"] == after["assessment_contexts"]
    )
    validator_details = after["repositories"]["validator"]["commands"]["findings_details"]
    expected_roles = [
        "Agent declaration: agent.py:20–25",
        "Registration: agent.py:33",
        "Callable definition: agent.py:34–39",
        "Rejection: agent.py:37–38",
    ]
    checks["source_role_grouping"].extend(
        validator_details.count(role) == 1 for role in expected_roles
    )
    # Count repeated literals for three independently source-pinned facts. This
    # intentionally includes a condition repeated in a verbatim source proof;
    # it is not a claim that every literal repetition is unnecessary.
    facts = ["decision.refund_amount > 500", "agent.py::validate_refund", "agent.py#refund_agent"]
    duplicates = {}
    for phase, captured in (("before", before), ("after", after)):
        raw = " ".join(
            captured["repositories"]["validator"]["commands"]["findings_details"].split()
        )
        duplicates[phase] = {
            "facts": {fact: max(0, raw.count(fact) - 1) for fact in facts},
            "repeated_fact_occurrences": sum(max(0, raw.count(fact) - 1) for fact in facts),
            "finding_count": 1,
        }
    return {
        "audit": "finding-presentation-v1",
        "human_comprehension": "not_evaluated",
        "pre_polish_report": str(PRE_POLISH.relative_to(PROJECT_ROOT)),
        "pre_polish_metrics": previous["metrics"],
        "single_column_icons": {heading: cell_len(icon) for heading, icon in ICONS.items()},
        "metrics": {
            key: {"numerator": sum(values), "denominator": len(values)}
            for key, values in checks.items()
        },
        "duplicate_fact_count_per_finding": duplicates,
        "duplication_definition": (
            "Occurrences after the first of the pinned condition, canonical callable and owner "
            "in one actual validator detail trace; verbatim source proof is included."
        ),
        "observations": observations,
        "captures": {
            name: {
                "repository": row["repository"],
                "before": before["repositories"][name]["commands"],
                "before_polish": previous["captures"][name]["after"],
                "after": row["commands"],
            }
            for name, row in after["repositories"].items()
        },
        "limitations": [
            "M11 evidence-filtered cases remain assessment contexts, not newly selected findings.",
            "Layout correctness is not demonstrated human comprehension.",
            "Only volatile event/scan IDs, timestamps, and temporary repository paths "
            "and their heading wraps are normalized in compatibility captures.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = serialize_report(run_presentation_audit())
    if args.output:
        target = args.output.resolve()
        if target.suffix != ".json" or not target.is_relative_to((PROJECT_ROOT / "docs").resolve()):
            parser.error("Audit output must be JSON under docs/.")
        target.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
