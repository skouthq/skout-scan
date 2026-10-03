"""Safe, deterministic repository artifact discovery."""

import os
from collections.abc import Sequence
from fnmatch import fnmatchcase
from pathlib import Path

from agentguard.config import CONFIG_FILENAME, ConfigError, load_config
from agentguard.models import (
    ArtifactType,
    DiscoveredArtifact,
    RepositoryMetadata,
    ScanCompleteness,
    ScanError,
    ScanResult,
    ScanWarning,
    SkippedPath,
    SkipReason,
)

ARTIFACT_TYPES = {
    ".py": ArtifactType.PYTHON,
    ".txt": ArtifactType.PROMPT_TEXT,
    ".md": ArtifactType.PROMPT_MARKDOWN,
    ".jsonl": ArtifactType.JSONL,
}


def _match_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts
    if pattern_parts[0] == "**":
        return _match_parts(path_parts, pattern_parts[1:]) or (
            bool(path_parts) and _match_parts(path_parts[1:], pattern_parts)
        )
    return (
        bool(path_parts)
        and fnmatchcase(path_parts[0], pattern_parts[0])
        and _match_parts(path_parts[1:], pattern_parts[1:])
    )


def matches_glob(relative_path: str, pattern: str) -> bool:
    """Match a POSIX repository-relative path using ``**`` recursive segments."""
    path_parts = tuple(part for part in relative_path.split("/") if part)
    pattern_parts = tuple(part for part in pattern.replace("\\", "/").split("/") if part)
    return bool(pattern_parts) and _match_parts(path_parts, pattern_parts)


def _matches_any(relative_path: str, patterns: Sequence[str]) -> bool:
    return any(matches_glob(relative_path, pattern) for pattern in patterns)


def _directory_entries(path: Path) -> list[os.DirEntry[str]]:
    with os.scandir(path) as entries:
        return list(entries)


def _probe_readable(path: Path) -> int:
    with path.open("rb") as artifact_file:
        artifact_file.read(1)
    return path.stat().st_size


def _failed_result(requested_path: str, code: str, message: str) -> ScanResult:
    return ScanResult(
        repository=RepositoryMetadata(requested_path=requested_path),
        errors=(ScanError(code=code, message=message, path=requested_path),),
        completeness=ScanCompleteness.FAILED,
    )


def scan_repository(repository_path: str | Path) -> ScanResult:
    """Discover supported artifacts without importing or executing repository code."""
    requested_path = str(repository_path)
    supplied_path = Path(repository_path).expanduser()

    try:
        if not supplied_path.exists():
            return _failed_result(
                requested_path,
                "repository_not_found",
                f"Repository path does not exist: {requested_path}",
            )
        if not supplied_path.is_dir():
            return _failed_result(
                requested_path,
                "repository_not_directory",
                f"Repository path is not a directory: {requested_path}",
            )
        root = supplied_path.resolve()
    except OSError as error:
        return _failed_result(
            requested_path, "repository_unreadable", f"Unable to access repository: {error}"
        )

    try:
        config = load_config(root)
    except ConfigError as error:
        return ScanResult(
            repository=RepositoryMetadata(requested_path=requested_path, root=str(root)),
            errors=(ScanError(code="configuration_error", message=str(error)),),
            completeness=ScanCompleteness.FAILED,
        )

    config_file = root / CONFIG_FILENAME
    repository = RepositoryMetadata(
        requested_path=requested_path,
        root=str(root),
        config_path=CONFIG_FILENAME if config_file.is_file() else None,
        include_patterns=config.include,
        exclude_patterns=config.exclude,
    )
    artifacts: list[DiscoveredArtifact] = []
    skipped: list[SkippedPath] = []
    warnings: list[ScanWarning] = []
    errors: list[ScanError] = []

    def record_warning(code: str, message: str, relative_path: str) -> None:
        warnings.append(ScanWarning(code=code, message=message, path=relative_path))

    def visit(directory: Path, relative_directory: str = "") -> None:
        try:
            entries = sorted(_directory_entries(directory), key=lambda entry: entry.name)
        except OSError as error:
            if not relative_directory:
                errors.append(
                    ScanError(
                        code="repository_unreadable",
                        message=f"Unable to read repository directory: {error}",
                        path=requested_path,
                    )
                )
                return
            skipped.append(
                SkippedPath(
                    path=relative_directory,
                    reason=SkipReason.UNREADABLE,
                    is_directory=True,
                )
            )
            record_warning(
                "directory_unreadable",
                f"Unable to inspect directory: {error}",
                relative_directory,
            )
            return

        for entry in entries:
            relative_path = (
                f"{relative_directory}/{entry.name}" if relative_directory else entry.name
            )
            entry_path = Path(entry.path)

            if _matches_any(relative_path, config.exclude):
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_directory = False
                skipped.append(
                    SkippedPath(
                        path=relative_path,
                        reason=SkipReason.EXCLUDED,
                        is_directory=is_directory,
                    )
                )
                continue

            try:
                is_symlink = entry.is_symlink()
                is_directory = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError as error:
                skipped.append(SkippedPath(path=relative_path, reason=SkipReason.UNREADABLE))
                record_warning("path_unreadable", f"Unable to inspect path: {error}", relative_path)
                continue

            if is_symlink:
                skipped.append(SkippedPath(path=relative_path, reason=SkipReason.UNSUPPORTED))
                record_warning(
                    "symlink_unsupported",
                    "Symbolic links are not followed during repository discovery.",
                    relative_path,
                )
                continue
            if is_directory:
                visit(entry_path, relative_path)
                continue

            if not _matches_any(relative_path, config.include):
                continue

            artifact_type = ARTIFACT_TYPES.get(entry_path.suffix.lower())
            if artifact_type is None or not is_file:
                skipped.append(SkippedPath(path=relative_path, reason=SkipReason.UNSUPPORTED))
                record_warning(
                    "artifact_unsupported",
                    "Included path is not a supported regular artifact file.",
                    relative_path,
                )
                continue

            try:
                size_bytes = _probe_readable(entry_path)
            except OSError as error:
                skipped.append(SkippedPath(path=relative_path, reason=SkipReason.UNREADABLE))
                record_warning(
                    "artifact_unreadable", f"Unable to read artifact: {error}", relative_path
                )
                continue

            artifacts.append(
                DiscoveredArtifact(
                    path=relative_path,
                    artifact_type=artifact_type,
                    size_bytes=size_bytes,
                )
            )

    visit(root)

    if errors:
        completeness = ScanCompleteness.FAILED
    elif warnings:
        completeness = ScanCompleteness.INCOMPLETE
    else:
        completeness = ScanCompleteness.COMPLETE

    return ScanResult(
        repository=repository,
        artifacts=tuple(sorted(artifacts, key=lambda artifact: artifact.path)),
        skipped=tuple(sorted(skipped, key=lambda item: (item.path, item.reason.value))),
        warnings=tuple(
            sorted(
                warnings, key=lambda warning: (warning.path or "", warning.code, warning.message)
            )
        ),
        errors=tuple(
            sorted(errors, key=lambda error: (error.path or "", error.code, error.message))
        ),
        completeness=completeness,
    )
