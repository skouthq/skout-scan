"""Local Git object snapshots; no checkout, filters, hooks, or state writes."""

import os
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from agentguard.config import DEFAULT_EXCLUDE, ConfigError, resolve_config
from agentguard.scanners.repository import matches_glob

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
GIT_TIMEOUT = 60


class GitComparisonError(ValueError):
    """A user-facing failure to obtain a local baseline."""


@dataclass(frozen=True)
class GitContext:
    root: Path
    current: Path
    scope: str
    requested_ref: str
    commit: str


@dataclass(frozen=True)
class GitSnapshot:
    root: Path
    limitations: tuple[str, ...]


def _git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    env = dict(os.environ)
    # Ignore inherited Git redirection and injected configuration. Read only the
    # selected repository, and never let a partial clone lazily fetch objects.
    for name in tuple(env):
        if name.startswith("GIT_"):
            del env[name]
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-C",
        str(root),
        *args,
    ]
    try:
        result = subprocess.run(
            command, input=data, capture_output=True, env=env, timeout=GIT_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitComparisonError(f"Unable to read local Git baseline: {error}") from error
    if result.returncode:
        raise GitComparisonError(
            "Unable to read local Git baseline (invalid revision, missing local objects, "
            "or unsupported Git repository). No fetch is attempted."
        )
    return result.stdout


def resolve_git_context(path: Path, revision: str) -> GitContext:
    supplied = path.expanduser().resolve()
    if not supplied.exists():
        raise GitComparisonError(f"Repository path does not exist: {path}")
    if not supplied.is_dir():
        raise GitComparisonError(f"Repository path is not a directory: {path}")
    if not revision or revision.startswith("-") or any(c in revision for c in "\n\r\0"):
        raise GitComparisonError("Baseline must be a valid local Git revision.")
    root = Path(
        os.fsdecode(_git(supplied, "rev-parse", "--show-toplevel")).removesuffix("\n")
    ).resolve()
    local_config = _git(root, "config", "--local", "--null", "--list")
    for setting in local_config.split(b"\0"):
        key, _, value = setting.partition(b"\n")
        key = key.lower()
        if key == b"extensions.partialclone" or (
            key.startswith(b"remote.")
            and key.endswith(b".promisor")
            and value.lower() not in {b"false", b"no", b"off", b"0"}
        ):
            raise GitComparisonError(
                "Partial/promisor clones are unsupported for baseline comparison; "
                "use a repository with local objects. No fetch is attempted."
            )
    try:
        scope = supplied.relative_to(root).as_posix()
    except ValueError as error:
        raise GitComparisonError("Scan path must be within the Git working tree.") from error
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}")
    return GitContext(
        root, supplied, "" if scope == "." else scope, revision, commit.decode().strip()
    )


def _relative(path: str, scope: str) -> str | None:
    if not scope:
        return path
    prefix = scope + "/"
    return path[len(prefix) :] if path.startswith(prefix) else None


def _excluded(path: str, patterns: Sequence[str]) -> bool:
    parts = PurePosixPath(path).parts
    return any(
        matches_glob("/".join(parts[:index]), pattern)
        for index in range(1, len(parts) + 1)
        for pattern in patterns
    )


def _blobs(context: GitContext, objects: Sequence[str]) -> dict[str, bytes]:
    if not objects:
        return {}
    raw = _git(
        context.root, "cat-file", "--batch", data="".join(x + "\n" for x in objects).encode()
    )
    offset = 0
    blobs: dict[str, bytes] = {}
    for oid in objects:
        end = raw.find(b"\n", offset)
        header = raw[offset:end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise GitComparisonError(
                "Baseline contains an unavailable local blob; no fetch attempted."
            )
        size = int(header[2])
        offset = end + 1
        blobs[oid] = raw[offset : offset + size]
        offset += size + 1
    return blobs


@contextmanager
def baseline_snapshot(context: GitContext, excludes: Sequence[str] = ()) -> Iterator[GitSnapshot]:
    """Materialize raw regular blobs in a disposable directory, preserving scoped paths."""
    entries: list[tuple[str, str, str, int]] = []
    for raw_entry in _git(context.root, "ls-tree", "-r", "-l", "-z", context.commit).split(b"\0"):
        if not raw_entry:
            continue
        header, raw_path = raw_entry.split(b"\t", 1)
        raw_mode, _, raw_oid, raw_size = header.split()
        relative = _relative(os.fsdecode(raw_path), context.scope)
        if relative is None or _excluded(relative, DEFAULT_EXCLUDE):
            continue
        parts = PurePosixPath(relative).parts
        if (
            not parts
            or relative.startswith("/")
            or "\\" in relative
            or ":" in relative
            or any(p in {".", ".."} or p.casefold() == ".git" for p in parts)
        ):
            raise GitComparisonError("Unsafe Git snapshot path was rejected.")
        entries.append(
            (
                relative,
                raw_mode.decode(),
                raw_oid.decode(),
                int(raw_size) if raw_size != b"-" else 0,
            )
        )
    with TemporaryDirectory(prefix="skout-baseline-") as directory:
        root = Path(directory)
        limitations: list[str] = []
        config = next((e for e in entries if e[0] == "agentguard.toml"), None)
        if config and config[1] in {"100644", "100755"} and config[3] <= MAX_FILE_BYTES:
            (root / config[0]).write_bytes(_blobs(context, [config[2]])[config[2]])
        try:
            patterns = resolve_config(root, cli_exclude=excludes).exclude
        except ConfigError:
            patterns = (*DEFAULT_EXCLUDE, *excludes)
        selected: list[tuple[str, str, str, int]] = []
        total = 0
        for entry in sorted(entries):
            path, mode, _, size = entry
            if _excluded(path, patterns):
                continue
            if mode not in {"100644", "100755"}:
                limitations.append(f"Unsupported Git entry ({mode}): {path}")
                continue
            if size > MAX_FILE_BYTES or total + size > MAX_SNAPSHOT_BYTES:
                limitations.append(f"Baseline snapshot size limit: {path}")
                continue
            selected.append(entry)
            total += size
        blobs = _blobs(context, sorted({e[2] for e in selected}))
        for path, _, oid, _ in selected:
            target = root.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blobs[oid])
        yield GitSnapshot(root, tuple(limitations))


def current_git_limitations(context: GitContext, excludes: Sequence[str]) -> tuple[str, ...]:
    """Detect in-scope submodules and unresolved index entries without running status/hooks."""
    try:
        patterns = resolve_config(context.current, cli_exclude=excludes).exclude
    except ConfigError:
        patterns = (*DEFAULT_EXCLUDE, *excludes)
    limitations: set[str] = set()
    for entry in _git(context.root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, _, stage = header.split()
        path = _relative(os.fsdecode(raw_path), context.scope)
        if path is None or _excluded(path, patterns):
            continue
        if mode == b"160000":
            limitations.add(f"Current Git submodule is unsupported: {path}")
        if stage != b"0":
            limitations.add(f"Unmerged index entry: {path}")
    return tuple(sorted(limitations))
