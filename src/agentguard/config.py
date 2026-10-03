"""Typed loading for repository-local AgentGuard configuration."""

import tomllib
from pathlib import Path

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


class ConfigError(ValueError):
    """Raised when an AgentGuard configuration file cannot be loaded."""


def load_config(repository_root: str | Path) -> AgentGuardConfig:
    """Load ``agentguard.toml`` from a repository root, or return defaults."""
    config_path = Path(repository_root) / CONFIG_FILENAME
    try:
        if not config_path.exists():
            return AgentGuardConfig()
        config_data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Unable to read configuration {config_path}: {error}") from error

    try:
        return AgentGuardConfig.model_validate(config_data)
    except ValidationError as error:
        raise ConfigError(f"Invalid configuration {config_path}: {error}") from error
