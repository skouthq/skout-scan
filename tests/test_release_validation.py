"""Artifact/runtime validation stays isolated and never authorizes publishing."""

import os
import subprocess
import tarfile
import tomllib
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from tools import release_smoke
from tools.release_smoke import GUARD
from tools.release_validation import (
    CHECK_VERSIONS,
    EXAMPLE_FILES,
    PROJECT,
    _unwanted,
    clean_environment,
    copy_examples,
    inspect_artifact,
)


@pytest.mark.parametrize("command", ["findings", "review"])
def test_smoke_help_assertions_ignore_ci_ansi_styling(command):
    from typer.testing import CliRunner

    from agentguard.cli import app

    result = CliRunner().invoke(
        app, [command, "--help"], color=True, env={"FORCE_COLOR": "1", "COLUMNS": "120"}
    )
    assert result.exit_code == 0
    # CI's Rich styling can insert an escape between the dashes and option name.
    styled = result.stdout.replace("--details", "--\x1b[1mdetails\x1b[0m")
    assert "--details" not in styled
    assert "--details" in release_smoke.plain_output(styled)


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "project"
    source = root / "src/agentguard"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("")
    (source / "cli.py").write_text("app = None\n")
    (source / "py.typed").write_text("")
    (root / "README.md").write_text("# Unicode README\nFeedback → local-first.\n")
    (root / "LICENSE").write_text("Apache License\nVersion 2.0\n")
    configuration = (PROJECT / "pyproject.toml").read_text()
    (root / "pyproject.toml").write_text(configuration)
    return root


def wheel_contents(root):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    version = project["version"]
    prefix = f"skout_scan-{version}.dist-info"
    headers = [
        "Metadata-Version: 2.4",
        "Name: skout-scan",
        f"Version: {version}",
        "License-Expression: Apache-2.0",
        "Requires-Python: >=3.12",
        "Description-Content-Type: text/markdown",
        "Provides-Extra: dev",
    ]
    headers.extend(f"Requires-Dist: {d}" for d in project["dependencies"])
    headers.extend(f"Project-URL: {key}, {value}" for key, value in project["urls"].items())
    metadata = "\n".join(headers) + "\n\n" + (root / "README.md").read_text()
    return {
        "agentguard/__init__.py": b"",
        "agentguard/cli.py": b"app = None\n",
        "agentguard/py.typed": b"",
        f"{prefix}/METADATA": metadata.encode(),
        f"{prefix}/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\nGenerator: test\n",
        f"{prefix}/entry_points.txt": b"[console_scripts]\nskout = agentguard.cli:app\n",
        f"{prefix}/licenses/LICENSE": (root / "LICENSE").read_bytes(),
    }


def write_wheel(path, contents):
    with ZipFile(path, "w") as archive:
        for name, value in contents.items():
            archive.writestr(name, value)


def test_wheel_checks_unicode_readme_metadata_license_resources_and_dependency_bounds(package):
    path = package.parent / "package.whl"
    contents = wheel_contents(package)
    write_wheel(path, contents)
    version = tomllib.loads((package / "pyproject.toml").read_text())["project"]["version"]
    result = inspect_artifact(path, package, version)
    assert result["status"] == "pass"
    assert result["metadata"]["runtime_files"] == 3
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_module",
        "missing_typed",
        "changed_source",
        "state",
        "secret",
        "absolute",
        "traversal",
        "runtime_dev_dependency",
        "weakened_constraint",
        "wrong_readme",
        "wrong_version",
    ],
)
def test_invalid_wheel_is_rejected(package, mutation):
    path = package.parent / "invalid.whl"
    contents = wheel_contents(package)
    metadata = next(n for n in contents if n.endswith("/METADATA"))
    if mutation == "missing_module":
        contents.pop("agentguard/cli.py")
    elif mutation == "missing_typed":
        contents.pop("agentguard/py.typed")
    elif mutation == "changed_source":
        contents["agentguard/cli.py"] = b"changed"
    elif mutation == "state":
        contents["agentguard/.agentguard/state.db"] = b"private"
    elif mutation == "secret":
        contents["agentguard/.env"] = b"private"
    elif mutation == "absolute":
        contents["/absolute.py"] = b""
    elif mutation == "traversal":
        contents["agentguard/../../outside.py"] = b""
    elif mutation == "runtime_dev_dependency":
        contents[metadata] = contents[metadata].replace(
            b"Provides-Extra: dev", b"Requires-Dist: pytest>=8.3\nProvides-Extra: dev"
        )
    elif mutation == "weakened_constraint":
        contents[metadata] = contents[metadata].replace(b"typer>=0.12,<1.0", b"typer>=0.12")
    elif mutation == "wrong_readme":
        contents[metadata] += b"Unexpected contents\n"
    elif mutation == "wrong_version":
        contents[metadata] = contents[metadata].replace(b"Version: 0.", b"Version: 9.")
    write_wheel(path, contents)
    version = tomllib.loads((package / "pyproject.toml").read_text())["project"]["version"]
    with pytest.raises(AssertionError):
        inspect_artifact(path, package, version)


def test_source_archive_rejects_links_before_extracting(package):
    version = tomllib.loads((package / "pyproject.toml").read_text())["project"]["version"]
    path = package.parent / "invalid.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        link = tarfile.TarInfo(f"skout_scan-{version}/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "/outside"
        archive.addfile(link)
    with pytest.raises(AssertionError, match="link/device"):
        inspect_artifact(path, package, version)
    assert not (package.parent / "outside").exists()


def test_explicit_example_manifest_never_copies_developer_state_or_private_files(tmp_path):
    project = tmp_path / "source"
    for example, files in EXAMPLE_FILES.items():
        for name in files:
            path = project / "examples" / example / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("public example\n")
        for name in [
            ".agentguard/agentguard.db",
            ".env",
            "private-dataset.jsonl",
            ".venv/private.py",
        ]:
            path = project / "examples" / example / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private\n")
    destination = tmp_path / "workspace"
    copy_examples(project, destination)
    files = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    expected = {f"{example}/{name}" for example, names in EXAMPLE_FILES.items() for name in names}
    assert files == expected
    assert (project / "examples/pydantic-ai-agent/.env").read_text() == "private\n"


def test_guard_activates_under_isolated_python_and_blocks_network_and_target_subprocess(tmp_path):
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = Path(
        subprocess.check_output(
            [str(python), "-I", "-c", 'import sysconfig;print(sysconfig.get_path("purelib"))'],
            text=True,
        ).strip()
    )
    site.mkdir(parents=True, exist_ok=True)
    (site / "_skout_release_guard.py").write_text(GUARD)
    (site / "skout_release_guard.pth").write_text("import _skout_release_guard\n")
    marker = tmp_path / "guard.log"
    env = {
        **clean_environment(),
        "SKOUT_RELEASE_OFFLINE": "1",
        "SKOUT_RELEASE_GUARD_LOG": str(marker),
    }
    for code in [
        "import socket; socket.socket()",
        'import subprocess,sys; subprocess.run([sys.executable,"-c","print(1)"])',
    ]:
        result = subprocess.run(
            [str(python), "-I", "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True
        )
        assert result.returncode != 0 and "Release smoke blocked" in result.stderr
    assert "socket." in marker.read_text() and "subprocess.Popen" in marker.read_text()


def test_setup_environment_removes_checkout_import_and_provider_credentials(monkeypatch):
    for key in ["PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        monkeypatch.setenv(key, "not-for-validation")
    result = clean_environment()
    assert all(
        key not in result
        for key in ["PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    )
    assert result["SOURCE_DATE_EPOCH"] == "1704067200"


def test_ci_and_release_validation_do_not_widen_publication_permissions():
    ci = yaml.safe_load((PROJECT / ".github/workflows/ci.yml").read_text())
    release = yaml.safe_load((PROJECT / ".github/workflows/release.yml").read_text())

    def events(config):
        return config.get("on", config.get(True))

    assert set(events(ci)) == {"push", "pull_request"}
    assert events(release) == {"push": {"tags": ["v*"]}}
    assert ci["permissions"] == {"contents": "read"}
    job = ci["jobs"]["test-matrix"]
    gate = ci["jobs"]["test-and-build"]
    assert gate["needs"] == "test-matrix" and gate["if"] == "${{ always() }}"
    assert gate["steps"][0]["run"] == 'test "$SKOUT_MATRIX_RESULT" = success'
    assert set(job["strategy"]["matrix"]["python-version"]) == set(CHECK_VERSIONS)
    assert any("tools.release_validation" in s.get("run", "") for s in job["steps"])
    publish = release["jobs"]["publish"]
    assert publish["needs"] == "build" and publish["permissions"] == {"id-token": "write"}
    assert publish["environment"]["name"] == "pypi"
    steps = release["jobs"]["build"]["steps"]
    validation = next(
        i for i, s in enumerate(steps) if "tools.release_validation" in s.get("run", "")
    )
    upload = next(
        i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert validation < upload
    assert not any("pypi-publish" in s.get("uses", "") for s in job["steps"])


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "x/.agentguard/state.db",
        "x/__pycache__/app.pyc",
        "../outside",
        "/absolute",
        "credentials.json",
        ".venv/python",
    ],
)
def test_artifact_privacy_boundaries_reject_unwanted_paths(name):
    assert _unwanted(name)
