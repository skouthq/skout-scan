"""Typed loading for repository-local AgentGuard configuration."""

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

CONFIG_FILENAME = "agentguard.toml"

DEFAULT_INCLUDE = (
    "**/*.py",
    "**/*.txt",
    "**/*.md",
    "**/*.jsonl",
)

DEFAULT_EXCLUDE = (
    "**/.git/**",
    "**/.agentguard/**",
    "**/.venv/**",
    "**/.uv-cache/**",
    "**/.tools/**",
    "**/venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/build/**",
    "**/dist/**",
)


class AgentGuardConfig(BaseModel):
    """Validated configuration used by future repository discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    include: tuple[str, ...] = DEFAULT_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE


class ResolvedConfig(BaseModel):
    """Effective scan configuration with exclusion provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    include: tuple[str, ...]
    exclude: tuple[str, ...]
    default_exclude: tuple[str, ...]
    config_exclude: tuple[str, ...]
    cli_exclude: tuple[str, ...]


class ConfigError(ValueError):
    """Raised when an AgentGuard configuration file cannot be loaded."""


def _load_config_data(repository_root: str | Path) -> dict[str, Any] | None:
    config_path = Path(repository_root) / CONFIG_FILENAME
    try:
        if not config_path.exists():
            return None
        return tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Unable to read configuration {config_path}: {error}") from error


def _validate_config(repository_root: str | Path, config_data: dict[str, Any]) -> AgentGuardConfig:
    config_path = Path(repository_root) / CONFIG_FILENAME

    try:
        return AgentGuardConfig.model_validate(config_data)
    except ValidationError as error:
        raise ConfigError(f"Invalid configuration {config_path}: {error}") from error


def load_config(repository_root: str | Path) -> AgentGuardConfig:
    """Load ``agentguard.toml`` from a repository root, or return defaults."""
    config_data = _load_config_data(repository_root)
    return (
        AgentGuardConfig()
        if config_data is None
        else _validate_config(repository_root, config_data)
    )


def resolve_config(
    repository_root: str | Path,
    *,
    cli_exclude: Sequence[str] = (),
) -> ResolvedConfig:
    """Resolve built-in, file-defined, and temporary CLI exclusions additively."""
    config_data = _load_config_data(repository_root)
    config = (
        AgentGuardConfig()
        if config_data is None
        else _validate_config(repository_root, config_data)
    )
    configured_exclude = (
        config.exclude if config_data is not None and "exclude" in config_data else ()
    )
    cli_patterns = tuple(cli_exclude)
    effective_exclude = tuple(dict.fromkeys((*DEFAULT_EXCLUDE, *configured_exclude, *cli_patterns)))
    return ResolvedConfig(
        include=config.include,
        exclude=effective_exclude,
        default_exclude=DEFAULT_EXCLUDE,
        config_exclude=configured_exclude,
        cli_exclude=cli_patterns,
    )
