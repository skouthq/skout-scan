"""Final M11.1 visual contracts, using actual Rich output and existing source facts."""

import json
from dataclasses import replace
from io import BytesIO, StringIO, TextIOWrapper
from shutil import copytree, ignore_patterns

import pytest
from rich.cells import cell_len
from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.feedback import FindingStore
from agentguard.models import RegistrationResolution
from agentguard.presentation import (
    ASCII_ICONS,
    ICONS,
    callable_display_names,
    display_ids,
    render_finding,
    render_preview,
    render_summary,
    view_for_assessment,
    view_for_finding,
)
from tools.behavior_audit.actionability_cases import load_cases
from tools.behavior_audit.runner import PROJECT_ROOT

CASES = {c.expectation["case_id"]: c for c in load_cases()}


@pytest.fixture
def example(tmp_path):
    root = tmp_path / "example"
    copytree(
        PROJECT_ROOT / "examples/pydantic-ai-agent",
        root,
        ignore=ignore_patterns(".agentguard", ".venv", "__pycache__"),
    )
    assert CliRunner().invoke(app, ["scan", str(root), "--no-progress"]).exit_code == 0
    return root, FindingStore(root).list_findings()[0]


def render(finding, width=100, *, color=False, preview=False):
    stream = StringIO()
    console = Console(
        file=stream, width=width, force_terminal=color, color_system="standard" if color else None
    )
    if preview:
        render_preview(console, finding)
    else:
        render_finding(console, finding, details=True)
    return stream.getvalue()


@pytest.mark.parametrize("width", [60, 80, 100, 120])
def test_rich_icons_spacing_connected_statement_and_width(example, width):
    _, finding = example
    raw = render(finding, width)
    assert "\x1b[" not in raw
    assert all(cell_len(line) <= width for line in raw.splitlines())
    assert all(cell_len(icon) == 1 for icon in ICONS.values())
    for name, icon in ICONS.items():
        assert f"{icon} {name}" in raw
    for heading in ["◇ Evidence:", "→ Next step:", "≡ Additional details"]:
        lines = raw.splitlines()
        at = lines.index(heading)
        assert lines[at - 1] == "" and lines[at - 2] != ""
    primary = raw.split("≡ Additional details")[0]
    assert "\n\n\n" not in primary
    visible = " ".join(raw.split())
    assert "If decision.refund_amount > 500 → raises ModelRetry" in visible
    assert (
        "Test validate_refund with the condition above and explicitly assert ModelRetry." in visible
    )
    assert "this callable" not in raw
    assert finding.finding_id in raw and finding.behavior_id in raw
    assert raw.index("Identifiers:") > raw.index("Lifecycle:")
    assert raw.index("Provenance identifiers:") > raw.index("Identifiers:")


def test_canonical_name_collisions_and_ambiguous_identity(example):
    _, finding = example
    context = finding.structured_explanation.rejection_provenance
    other_context = context.model_copy(
        update={"source_file": "other.py", "callable_id": "callable_other"}
    )
    other = finding.model_copy(
        update={
            "finding_id": "finding_other",
            "structured_explanation": finding.structured_explanation.model_copy(
                update={"rejection_provenance": other_context}
            ),
        }
    )
    names = callable_display_names((finding, other))
    assert names[finding.finding_id] == "agent.py::validate_refund"
    assert names[other.finding_id] == "other.py::validate_refund"
    for item in (finding, other):
        step = view_for_finding(item, display_name=names[item.finding_id]).next_step
        assert step.count(names[item.finding_id]) == 1
    ambiguous = finding.model_copy(
        update={
            "structured_explanation": finding.structured_explanation.model_copy(
                update={
                    "rejection_provenance": context.model_copy(
                        update={"resolution": RegistrationResolution.AMBIGUOUS}
                    ),
                }
            ),
        }
    )
    assert callable_display_names((ambiguous,))[ambiguous.finding_id] is None
    assert "Target this callable." in view_for_finding(ambiguous).next_step
    assert "Test validate_refund" not in view_for_finding(ambiguous).next_step


def test_unresolved_symbol_is_not_guessed_from_title(example):
    _, finding = example
    detail = finding.structured_explanation
    unresolved = finding.model_copy(
        update={
            "structured_explanation": detail.model_copy(
                update={
                    "rejection_provenance": None,
                    "behavior": detail.behavior.model_copy(update={"source_symbol": None}),
                }
            )
        }
    )
    assert callable_display_names((unresolved,))[unresolved.finding_id] is None
    assert "Target this callable." in view_for_finding(unresolved).next_step


def test_unconditional_behavior_has_no_fabricated_if(example):
    _, finding = example
    detail = finding.structured_explanation
    from agentguard.models import BehaviorType

    behavior = detail.behavior.model_copy(
        update={"condition": None, "behavior_type": BehaviorType.TOOL_INVOCATION}
    )
    changed = finding.model_copy(
        update={
            "structured_explanation": detail.model_copy(
                update={"behavior": behavior, "rejection_provenance": None}
            )
        }
    )
    stream = StringIO()
    render_summary(Console(file=stream, width=100), view_for_finding(changed))
    assert "If " not in stream.getvalue()


def test_role_grouping_keeps_real_spans_and_full_provenance(example):
    _, finding = example
    raw = render(finding)
    rows = [
        "Agent declaration: agent.py:20–25",
        "Registration: agent.py:33",
        "Callable definition: agent.py:34–39",
        "Rejection: agent.py:37–38",
    ]
    assert all(raw.count(row) == 1 for row in rows)
    assert [raw.index(row) for row in rows] == sorted(raw.index(row) for row in rows)
    assert "Behavior source, Callable definition" not in raw
    assert "agent.py:20–39" not in raw  # No invented union span.
    context = finding.structured_explanation.rejection_provenance
    assert context.callable_id in raw
    assert all(r.relationship_id in raw for r in context.registrations)
    assert raw.count("Static analysis only;") == 1
    assert raw.count("Registration does not prove runtime execution or eval coverage.") == 1
    assert "business priority assessment" in raw


def test_no_color_color_redirect_and_ascii_fallback_preserve_facts(example):
    _, finding = example
    plain = render(finding)
    colored = render(finding, color=True)
    assert "\x1b[" in colored

    def visible(text):
        return " ".join(line for line in text.splitlines() if line.strip("─- "))

    assert " ".join(visible(Text.from_ansi(colored).plain).split()) == " ".join(
        visible(plain).split()
    )
    sink = BytesIO()
    stream = TextIOWrapper(sink, encoding="ascii", errors="strict")
    render_finding(
        Console(file=stream, width=60, color_system=None, force_terminal=False),
        finding,
        details=True,
    )
    stream.flush()
    text = sink.getvalue().decode("ascii")
    for name, icon in ASCII_ICONS.items():
        assert f"{icon} {name}" in text
    assert "If decision.refund_amount > 500 -> raises ModelRetry" in " ".join(text.split())
    assert "\x1b[" not in text and "\ufffd" not in text
    assert finding.finding_id in text
    assert "agent.py:34-39" in text
    assert all(len(line) <= 60 for line in text.splitlines())


def test_unicode_source_literal_is_preserved_or_escaped_not_rewritten():
    view = view_for_assessment(CASES["rejection_missing"].assessment)
    condition = "If label == '金 → 額'"
    view = replace(view, behavior=(condition, "raises ModelRetry"))
    stream = StringIO()
    render_summary(Console(file=stream, width=100), view)
    assert condition in stream.getvalue()
    sink = BytesIO()
    ascii_stream = TextIOWrapper(sink, encoding="ascii", errors="strict")
    render_summary(Console(file=ascii_stream, width=60), view)
    ascii_stream.flush()
    assert r"label == '\u91d1 \u2192 \u984d' -> raises ModelRetry" in " ".join(
        sink.getvalue().decode().split()
    )


def test_absent_optional_sections_do_not_leave_empty_headings(example):
    _, finding = example
    historical = finding.model_copy(
        update={"structured_explanation": None, "guidance": None, "source_evidence": ()}
    )
    text = render(historical)
    assert "Provenance:" not in text and "Source references:" not in text
    assert "Source evidence:" not in text
    assert "\n\n\n" not in text


def test_findings_review_and_preview_use_identical_words_icons_and_tokens(example):
    root, finding = example
    runner = CliRunner()
    basic = runner.invoke(app, ["findings", "--repository", str(root)])
    review = runner.invoke(app, ["review", "--repository", str(root)], input="skip\n")
    preview = render(finding, preview=True)
    for title in ["▸ Behavior:", "◇ Evidence:", "→ Next step:"]:
        assert title in basic.output and title in review.output and title in preview
    step = view_for_finding(finding).next_step
    assert " ".join(step.split()) in " ".join(basic.output.split())
    assert " ".join(step.split()) in " ".join(review.output.split())
    assert step in preview
    token = display_ids((finding,))[finding.finding_id]
    assert f"Finding: {token}" in basic.output and f"Finding: {token}" in preview
    assert finding.finding_id not in preview
    assert "Additional details" not in preview and "Provenance identifiers" not in preview
    exported = runner.invoke(app, ["metrics", "--repository", str(root), "--json"])
    assert exported.exit_code == 0
    assert json.loads(exported.output)["findings"][0]["finding_id"] == finding.finding_id
