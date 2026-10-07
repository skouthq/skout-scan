"""Tests for deterministic, static repository discovery."""

from pathlib import Path

import pytest

import agentguard.scanners.repository as repository_scanner
from agentguard.models import ArtifactType, ScanCompleteness, SkipReason
from agentguard.scanners import matches_glob, scan_repository


def write_file(root: Path, relative_path: str, contents: str = "") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def artifact_paths(root: Path) -> list[str]:
    return [artifact.path for artifact in scan_repository(root).artifacts]


def test_empty_repository_is_complete(tmp_path: Path) -> None:
    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.COMPLETE
    assert result.artifacts == ()
    assert result.warnings == ()
    assert result.errors == ()


def test_supported_artifacts_are_classified_with_relative_paths(tmp_path: Path) -> None:
    write_file(tmp_path, "agent.py", "VALUE = 1\n")
    write_file(tmp_path, "prompts/system.txt", "Be helpful")
    write_file(tmp_path, "prompts/policy.md", "# Policy")
    write_file(tmp_path, "evals/cases.jsonl", '{"input": "hello"}\n')
    write_file(tmp_path, "README.rst", "ignored")

    result = scan_repository(tmp_path)

    assert [(artifact.path, artifact.artifact_type) for artifact in result.artifacts] == [
        ("agent.py", ArtifactType.PYTHON),
        ("evals/cases.jsonl", ArtifactType.JSONL),
        ("prompts/policy.md", ArtifactType.PROMPT_MARKDOWN),
        ("prompts/system.txt", ArtifactType.PROMPT_TEXT),
    ]
    assert all(not Path(artifact.path).is_absolute() for artifact in result.artifacts)
    assert result.completeness is ScanCompleteness.COMPLETE


def test_default_exclusions_are_pruned_and_recorded(tmp_path: Path) -> None:
    write_file(tmp_path, ".venv/library.py")
    write_file(tmp_path, "services/worker/.venv/library.py")
    write_file(tmp_path, "frontend/node_modules/package/README.md")
    write_file(tmp_path, "package/__pycache__/cached.py")
    write_file(tmp_path, "build/generated.py")
    write_file(tmp_path, "frontend/build/generated.py")
    write_file(tmp_path, "dist/released.py")
    write_file(tmp_path, ".uv-cache/archive/package.py")
    write_file(tmp_path, ".tools/runtime/package.py")
    write_file(tmp_path, "src/kept.py")

    result = scan_repository(tmp_path)

    assert [artifact.path for artifact in result.artifacts] == ["src/kept.py"]
    assert {item.path for item in result.skipped} == {
        ".venv",
        ".tools",
        ".uv-cache",
        "build",
        "dist",
        "frontend/build",
        "frontend/node_modules",
        "package/__pycache__",
        "services/worker/.venv",
    }
    assert all(item.reason is SkipReason.EXCLUDED for item in result.skipped)
    assert result.completeness is ScanCompleteness.COMPLETE


def test_custom_include_rules_replace_defaults(tmp_path: Path) -> None:
    write_file(tmp_path, "agentguard.toml", 'include = ["prompts/**/*.txt"]\nexclude = []\n')
    write_file(tmp_path, "agent.py")
    write_file(tmp_path, "prompts/nested/system.txt")
    write_file(tmp_path, "other.txt")

    assert artifact_paths(tmp_path) == ["prompts/nested/system.txt"]


def test_custom_exclude_rules_are_honored(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "agentguard.toml",
        'include = ["**/*.py"]\nexclude = ["generated/**"]\n',
    )
    write_file(tmp_path, "app.py")
    write_file(tmp_path, "generated/code.py")

    result = scan_repository(tmp_path)

    assert [artifact.path for artifact in result.artifacts] == ["app.py"]
    assert result.skipped[0].path == "generated"
    assert result.skipped[0].reason is SkipReason.EXCLUDED


def test_cli_exclusions_are_additive_and_repeatable(tmp_path: Path) -> None:
    write_file(tmp_path, "agentguard.toml", 'exclude = ["vendor/**"]\n')
    write_file(tmp_path, "src/kept.py")
    write_file(tmp_path, "vendor/library.py")
    write_file(tmp_path, "output/result.py")
    write_file(tmp_path, "generated/code.py")
    write_file(tmp_path, ".venv/library.py")

    result = scan_repository(
        tmp_path,
        extra_excludes=("output/**", "generated/**"),
    )

    assert [artifact.path for artifact in result.artifacts] == ["src/kept.py"]
    assert {item.path for item in result.skipped} >= {
        ".venv",
        "generated",
        "output",
        "vendor",
    }
    assert result.repository.config_exclude_patterns == ("vendor/**",)
    assert result.repository.cli_exclude_patterns == ("output/**", "generated/**")
    assert "**/.venv/**" in result.repository.exclude_patterns


def test_excluded_directory_is_pruned_before_descendant_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = tmp_path / "generated"
    write_file(tmp_path, "generated/broken.py", "def broken(:\n")
    write_file(tmp_path, "src/kept.py")
    original_entries = repository_scanner._directory_entries

    def fail_if_generated_is_visited(path: Path) -> list[object]:
        if path == generated:
            raise AssertionError("excluded directory was traversed")
        return original_entries(path)

    monkeypatch.setattr(repository_scanner, "_directory_entries", fail_if_generated_is_visited)

    result = scan_repository(tmp_path, extra_excludes=("generated/**",))

    assert [artifact.path for artifact in result.artifacts] == ["src/kept.py"]
    assert result.warnings == ()
    assert result.completeness is ScanCompleteness.COMPLETE


def test_nonexistent_cli_exclusion_is_harmless_and_does_not_mutate_config(
    tmp_path: Path,
) -> None:
    config_path = write_file(tmp_path, "agentguard.toml", 'exclude = ["vendor/**"]\n')
    write_file(tmp_path, "src/kept.py")
    before = config_path.read_text(encoding="utf-8")

    result = scan_repository(tmp_path, extra_excludes=("does-not-exist/**",))

    assert [artifact.path for artifact in result.artifacts] == ["src/kept.py"]
    assert result.completeness is ScanCompleteness.COMPLETE
    assert config_path.read_text(encoding="utf-8") == before


def test_exclude_wins_over_overlapping_include(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "agentguard.toml",
        'include = ["**/*.py"]\nexclude = ["src/private/**"]\n',
    )
    write_file(tmp_path, "src/public.py")
    write_file(tmp_path, "src/private/secret.py")

    assert artifact_paths(tmp_path) == ["src/public.py"]


def test_glob_matching_is_repository_relative_and_recursive() -> None:
    assert matches_glob("app.py", "**/*.py")
    assert matches_glob("src/nested/app.py", "**/*.py")
    assert matches_glob(".venv", ".venv/**")
    assert matches_glob("package/__pycache__", "**/__pycache__/**")
    assert not matches_glob("nested/.venv/app.py", ".venv/**")
    assert not matches_glob("src/app.py", "*.py")


def test_nonexistent_repository_returns_failed_result(tmp_path: Path) -> None:
    result = scan_repository(tmp_path / "missing")

    assert result.completeness is ScanCompleteness.FAILED
    assert result.errors[0].code == "repository_not_found"


def test_file_path_returns_failed_result(tmp_path: Path) -> None:
    file_path = write_file(tmp_path, "agent.py")

    result = scan_repository(file_path)

    assert result.completeness is ScanCompleteness.FAILED
    assert result.errors[0].code == "repository_not_directory"


def test_unreadable_file_makes_scan_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unreadable = write_file(tmp_path, "unreadable.py")
    original_probe = repository_scanner._probe_readable

    def fail_for_file(path: Path) -> int:
        if path == unreadable:
            raise PermissionError("permission denied")
        return original_probe(path)

    monkeypatch.setattr(repository_scanner, "_probe_readable", fail_for_file)

    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert result.artifacts == ()
    assert result.skipped[0].path == "unreadable.py"
    assert result.skipped[0].reason is SkipReason.UNREADABLE
    assert result.warnings[0].code == "artifact_unreadable"


def test_unreadable_subdirectory_makes_scan_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unreadable_directory = tmp_path / "unreadable"
    unreadable_directory.mkdir()
    original_entries = repository_scanner._directory_entries

    def fail_for_directory(path: Path) -> list[object]:
        if path == unreadable_directory:
            raise PermissionError("permission denied")
        return original_entries(path)

    monkeypatch.setattr(repository_scanner, "_directory_entries", fail_for_directory)

    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert result.skipped[0].path == "unreadable"
    assert result.skipped[0].is_directory
    assert result.warnings[0].code == "directory_unreadable"


def test_unreadable_root_returns_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_for_root(path: Path) -> list[object]:
        raise PermissionError(f"cannot read {path}")

    monkeypatch.setattr(repository_scanner, "_directory_entries", fail_for_root)

    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.FAILED
    assert result.errors[0].code == "repository_unreadable"


def test_included_unsupported_file_makes_scan_incomplete(tmp_path: Path) -> None:
    write_file(tmp_path, "agentguard.toml", 'include = ["**/*.yaml"]\nexclude = []\n')
    write_file(tmp_path, "agent.yaml", "name: agent")

    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.INCOMPLETE
    assert result.skipped[0].path == "agent.yaml"
    assert result.skipped[0].reason is SkipReason.UNSUPPORTED
    assert result.warnings[0].code == "artifact_unsupported"


def test_manifest_order_is_independent_of_directory_entry_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "z.py")
    write_file(tmp_path, "a.py")
    write_file(tmp_path, "nested/m.md")
    expected = scan_repository(tmp_path)
    original_entries = repository_scanner._directory_entries

    def reversed_entries(path: Path) -> list[object]:
        return list(reversed(original_entries(path)))

    monkeypatch.setattr(repository_scanner, "_directory_entries", reversed_entries)

    assert scan_repository(tmp_path) == expected


def test_python_artifact_is_never_executed(tmp_path: Path) -> None:
    sentinel = tmp_path / "executed"
    write_file(
        tmp_path,
        "dangerous.py",
        f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\n",
    )

    result = scan_repository(tmp_path)

    assert result.completeness is ScanCompleteness.COMPLETE
    assert not sentinel.exists()


def test_configuration_is_resolved_from_supplied_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root = tmp_path / "repository"
    other_root = tmp_path / "other"
    repository_root.mkdir()
    other_root.mkdir()
    write_file(repository_root, "agentguard.toml", 'include = ["**/*.txt"]\nexclude = []\n')
    write_file(repository_root, "included.txt")
    write_file(repository_root, "excluded.py")
    write_file(other_root, "agentguard.toml", 'include = ["**/*.py"]\nexclude = []\n')
    monkeypatch.chdir(other_root)

    assert artifact_paths(repository_root) == ["included.txt"]


def test_scan_creates_no_agentguard_state(tmp_path: Path) -> None:
    write_file(tmp_path, "agent.py")

    scan_repository(tmp_path)

    assert not (tmp_path / ".agentguard").exists()
