"""Build/inspect/install actual artifacts and validate the CLI outside this checkout.

Dependency installation may use a package index. Product runtime smoke tests run
under network/subprocess guards. This tool never uploads, tags, commits or pushes.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from shutil import copy2
from typing import Any, cast
from zipfile import ZipFile

from tools.release_smoke import GUARD

PROJECT = Path(__file__).resolve().parents[1]
CHECK_VERSIONS = ("3.12", "3.13", "3.14", "3.15")
EXAMPLE_FILES = {
    "pydantic-ai-agent": (
        "agent.py",
        "evals.py",
        "README.md",
        "requirements.txt",
        "tests/test_tools.py",
        "tests/solutions/test_retry.py.example",
    ),
    "langgraph-agent": (
        "workflow.py",
        "README.md",
        "requirements.txt",
        "tests/test_refund_policy.py",
        "evals/refund_paths.jsonl",
        "evals/escalation_path.jsonl.example",
    ),
    "crewai-agent": (
        "crew.py",
        "README.md",
        "requirements.txt",
        "tests/test_tools.py",
        "tests/solutions/test_escalation.py.example",
    ),
}


def copy_examples(project: Path, workspace: Path) -> None:
    """Copy an explicit public manifest, never local state, private files or environments."""
    for example, files in EXAMPLE_FILES.items():
        for relative in files:
            target = workspace / example / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(project / "examples" / example / relative, target)


def clean_environment() -> dict[str, str]:
    result = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        result.pop(name, None)
    result.update(PIP_DISABLE_PIP_VERSION_CHECK="1", SOURCE_DATE_EPOCH="1704067200")
    return result


def run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=environment, text=True, capture_output=True, timeout=600
    )
    if result.returncode:
        raise RuntimeError(
            f"Validation subprocess failed: {Path(command[0]).name}: "
            + result.stdout
            + result.stderr
        )
    return result.stdout


def environment_python(
    interpreter: str, destination: Path, *, cwd: Path, environment: dict[str, str]
) -> Path:
    run([interpreter, "-m", "venv", str(destination)], cwd=cwd, environment=environment)
    return destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _unwanted(name: str) -> bool:
    path = PurePosixPath(name)
    bad_parts = {
        ".agentguard",
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        "node_modules",
        "demo",
    }
    return (
        path.is_absolute()
        or ".." in path.parts
        or bool(bad_parts.intersection(path.parts))
        or any(part == ".env" or part.startswith(".env.") for part in path.parts)
        or path.suffix in {".db", ".sqlite", ".sqlite3", ".pyc", ".pem", ".key", ".mp4", ".gif"}
        or path.name in {"credentials.json", "secrets.json"}
    )


def inspect_artifact(path: Path, project: Path, version: str) -> dict[str, Any]:
    """Validate runtime completeness and archive boundaries against source metadata."""
    configuration = tomllib.loads((project / "pyproject.toml").read_text())
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            entries = {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
        metadata_name = next(n for n in entries if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(entries[metadata_name])
        expected = {
            f"agentguard/{f.relative_to(project / 'src/agentguard').as_posix()}"
            for f in (project / "src/agentguard").rglob("*")
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"
        }
        assert expected.issubset(entries), f"Missing runtime files: {expected - set(entries)}"
        for name in expected:
            assert entries[name] == (project / "src" / name).read_bytes(), name
        assert all(n.startswith(("agentguard/", "skout_scan-")) for n in entries)
        assert not any(n.startswith(("tests/", "tools/", "examples/")) for n in entries)
        entry_points = next(
            data for name, data in entries.items() if name.endswith("/entry_points.txt")
        )
        assert b"skout = agentguard.cli:app" in entry_points
        assert b"Tag: py3-none-any" in next(
            data for name, data in entries.items() if name.endswith(".dist-info/WHEEL")
        )
        assert metadata["Name"] == "skout-scan" and metadata["Version"] == version
        assert metadata["Requires-Python"] == configuration["project"]["requires-python"]
        assert metadata["License-Expression"] == "Apache-2.0"
        assert metadata["Description-Content-Type"] == "text/markdown"
        description = cast(bytes, metadata.get_payload(decode=True)).decode("utf-8")
        assert description.strip() == (project / "README.md").read_text().strip()
        assert "dev" in metadata.get_all("Provides-Extra", [])
        declared = configuration["project"]["dependencies"]
        actual = [x for x in metadata.get_all("Requires-Dist", []) if "extra ==" not in x]

        def constraint_key(requirement: str) -> tuple[str, tuple[str, ...]]:
            # Current runtime declarations are four plain version-bounded names.
            # Permit backend specifier ordering without weakening the bounds.
            match = re.fullmatch(r"([A-Za-z0-9_-]+)([<>=!~0-9.,]+)", requirement)
            assert match is not None, "Review new requirement syntax explicitly"
            return match[1].lower().replace("_", "-"), tuple(sorted(match[2].split(",")))

        assert sorted(map(constraint_key, actual)) == sorted(map(constraint_key, declared))
        for key, url in configuration["project"]["urls"].items():
            assert f"{key}, {url}" in metadata.get_all("Project-URL", [])
        metadata_result = {
            "name": metadata["Name"],
            "version": metadata["Version"],
            "requires_python": metadata["Requires-Python"],
            "license": metadata["License-Expression"],
            "runtime_requirements": sorted(actual),
            "entry_point": "skout = agentguard.cli:app",
            "wheel_tag": "py3-none-any",
            "generator": BytesParser().parsebytes(
                next(data for name, data in entries.items() if name.endswith(".dist-info/WHEEL"))
            )["Generator"],
            "runtime_files": len(expected),
        }
    else:
        with tarfile.open(path) as source_archive:
            entries = {}
            for member in source_archive.getmembers():
                assert member.isfile() or member.isdir(), "Unexpected link/device in sdist"
                if member.isfile():
                    stream = source_archive.extractfile(member)
                    assert stream is not None
                    entries[member.name] = stream.read()
        prefix = f"skout_scan-{version}/"
        assert all(n.startswith(prefix) for n in entries)
        assert all(not _unwanted(n) for n in entries)
        stripped = {n.removeprefix(prefix): value for n, value in entries.items()}
        assert {"pyproject.toml", "README.md", "LICENSE", "PKG-INFO"}.issubset(stripped)
        for source in (project / "src/agentguard").rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
                relative = source.relative_to(project).as_posix()
                assert stripped.get(relative) == source.read_bytes(), relative
        assert not any(n.startswith(("tests/", "tools/", "examples/", "demo/")) for n in stripped)
        assert tomllib.loads(stripped["pyproject.toml"].decode())["project"]["version"] == version
        metadata_result = {
            "name": "skout-scan",
            "version": version,
            "rebuild_source_complete": True,
            "examples_tests_audits_intentionally_excluded": True,
        }
    assert all(not _unwanted(name) for name in entries)
    assert any(name.endswith("/LICENSE") or name == "LICENSE" for name in entries)
    assert not any(str(project).encode() in value for value in entries.values())
    return {
        "status": "pass",
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
        "file_count": len(entries),
        "metadata": metadata_result,
        "unwanted_files": [],
    }


def workflow_contract(
    python: Path, project: Path, temporary: Path, environment: dict[str, str]
) -> dict[str, Any]:
    # YAML is a declared runtime dependency in this clean wheel environment.
    script = """import json,sys,yaml
from pathlib import Path
ci=yaml.safe_load(Path(sys.argv[1]).read_text())
release=yaml.safe_load(Path(sys.argv[2]).read_text())
events=lambda d: d.get("on", d.get(True, {}))
publish=release["jobs"]["publish"]
ci_steps=ci["jobs"]["test-matrix"]["steps"]
release_steps=release["jobs"]["build"]["steps"]
checks={
 "ci_push_and_pr_only":set(events(ci))=={"push","pull_request"},
 "ci_read_only_permissions":ci.get("permissions")=={"contents":"read"},
 "ci_artifact_smoke":any("tools.release_validation" in s.get("run","") for s in ci_steps),
 "stable_ci_gate":ci["jobs"]["test-and-build"]["needs"]=="test-matrix"
                  and ci["jobs"]["test-and-build"]["if"]=="${{ always() }}",
 "tag_only_publish":events(release)=={"push":{"tags":["v*"]}},
 "build_before_publish":publish.get("needs")=="build",
 "trusted_publishing":any(s.get("uses","").startswith("pypa/gh-action-pypi-publish@")
                          for s in publish["steps"]),
 "oidc_publish_only":publish.get("permissions")=={"id-token":"write"},
 "pypi_environment":publish.get("environment",{}).get("name")=="pypi",
 "tag_matches_metadata":any(s.get("name")=="Verify tag matches package version"
                            for s in release_steps),
 "release_artifact_smoke":any("tools.release_validation" in s.get("run","") for s in release_steps),
}
matrix=ci["jobs"]["test-matrix"]["strategy"]["matrix"]["python-version"]
print(json.dumps({"checks":checks,"ci_python_matrix":matrix},sort_keys=True))
"""
    output = run(
        [
            str(python),
            "-I",
            "-c",
            script,
            str(project / ".github/workflows/ci.yml"),
            str(project / ".github/workflows/release.yml"),
        ],
        cwd=temporary,
        environment=environment,
    )
    result = json.loads(output)
    assert all(result["checks"].values()), result
    assert set(result["ci_python_matrix"]) == set(CHECK_VERSIONS)
    return cast(dict[str, Any], result)


def validate(
    project: Path, *, interpreters: list[str], artifacts: Path | None = None
) -> dict[str, Any]:
    configuration = tomllib.loads((project / "pyproject.toml").read_text())
    version = configuration["project"]["version"]
    environment = clean_environment()
    with tempfile.TemporaryDirectory(prefix="skout-distribution-validation-") as directory:
        temporary = Path(directory)
        build_python = environment_python(
            interpreters[0], temporary / "build-env", cwd=temporary, environment=environment
        )
        tools = [
            d
            for d in configuration["project"]["optional-dependencies"]["dev"]
            if d.startswith(("build>", "twine>"))
        ]
        run(
            [str(build_python), "-m", "pip", "install", *tools],
            cwd=temporary,
            environment=environment,
        )
        artifact_dir = artifacts.resolve() if artifacts else temporary / "artifacts"
        if artifacts is None:
            run(
                [str(build_python), "-m", "build", "--outdir", str(artifact_dir), str(project)],
                cwd=temporary,
                environment=environment,
            )
        wheels = list(artifact_dir.glob("*.whl"))
        sdists = list(artifact_dir.glob("*.tar.gz"))
        assert len(wheels) == len(sdists) == 1, "Provide exactly one wheel and one sdist"
        wheel, sdist = wheels[0], sdists[0]
        artifact_reports = [inspect_artifact(path, project, version) for path in [wheel, sdist]]
        run(
            [str(build_python), "-m", "twine", "check", str(wheel), str(sdist)],
            cwd=temporary,
            environment=environment,
        )
        backend = configuration["build-system"]["requires"][0]
        minimum = re.fullmatch(r"hatchling>=([0-9.]+),<[0-9.]+", backend)
        assert minimum is not None, "Review changed build-backend requirements explicitly"
        minimum_version = minimum[1]
        run(
            [str(build_python), "-m", "pip", "install", f"hatchling=={minimum_version}"],
            cwd=temporary,
            environment=environment,
        )
        minimum_dir = temporary / "minimum-backend-artifacts"
        run(
            [
                str(build_python),
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(minimum_dir),
                str(project),
            ],
            cwd=temporary,
            environment=environment,
        )
        minimum_artifacts = [
            inspect_artifact(path, project, version) for path in sorted(minimum_dir.iterdir())
        ]
        assert len(minimum_artifacts) == 2
        installations = []
        workflow = None
        for index, interpreter in enumerate(interpreters):
            for kind, artifact in [("wheel", wheel), ("sdist", sdist)]:
                base = temporary / f"install-{index}-{kind}"
                python = environment_python(
                    interpreter, base / "environment", cwd=temporary, environment=environment
                )
                run(
                    [str(python), "-m", "pip", "install", "--force-reinstall", str(artifact)],
                    cwd=temporary,
                    environment=environment,
                )
                run([str(python), "-m", "pip", "check"], cwd=temporary, environment=environment)
                site_packages = Path(
                    run(
                        [
                            str(python),
                            "-I",
                            "-c",
                            'import sysconfig; print(sysconfig.get_path("purelib"))',
                        ],
                        cwd=temporary,
                        environment=environment,
                    ).strip()
                )
                # A stdlib sitecustomize can shadow a venv's copy (e.g. Homebrew).
                # A unique .pth import reliably activates the temporary guard under -I.
                (site_packages / "_skout_release_guard.py").write_text(GUARD)
                (site_packages / "skout_release_guard.pth").write_text(
                    "import _skout_release_guard\n"
                )
                workspace = base / "workspace"
                workspace.mkdir()
                copy_examples(project, workspace)
                runner = base / "smoke.py"
                copy2(project / "tools/release_smoke.py", runner)
                report_path = base / "smoke.json"
                run(
                    [
                        str(python),
                        "-I",
                        str(runner),
                        "--workspace",
                        str(workspace),
                        "--version",
                        version,
                        "--report",
                        str(report_path),
                    ],
                    cwd=workspace,
                    environment=environment,
                )
                result = json.loads(report_path.read_text())
                installations.append({"artifact": kind, **result, "pip_check": "pass"})
                if workflow is None:
                    workflow = workflow_contract(python, project, temporary, environment)
        covered = sorted({installation["python"] for installation in installations})
        return {
            "validation": "skout-release-readiness-v1",
            "version": version,
            "build_status": "pass",
            "metadata_validation": "pass",
            "artifacts": artifact_reports,
            "minimum_build_backend": {
                "name": "hatchling",
                "version": minimum_version,
                "build_status": "pass",
                "artifacts": minimum_artifacts,
            },
            "installations": installations,
            "python_coverage": {
                v: ("pass" if v in covered else "blocked: interpreter/CI result unavailable")
                for v in CHECK_VERSIONS
            },
            "declared_python": configuration["project"]["requires-python"],
            "workflow": workflow,
            "external_trusted_publisher_and_environment_protections": (
                "requires maintainer verification"
            ),
            "recommendation": "conditionally_ready",
            "limitations": [
                "Setup/build/dependency downloads may require network access.",
                "Runtime guards are controlled smoke checks, "
                "not a malicious-repository security audit.",
                "Metadata has no upper Python bound; "
                "untested future interpreters are not certified.",
                "Examples/tests/audit tooling intentionally do not ship in wheel/sdist.",
                "No package upload, version change, commit, push or tag was performed.",
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", action="append", default=[], help="Additional interpreter to test."
    )
    parser.add_argument(
        "--artifacts", type=Path, help="Validate existing artifacts instead of building."
    )
    parser.add_argument("--report", type=Path, default=PROJECT / "docs/release-validation.json")
    args = parser.parse_args()
    result = validate(
        PROJECT, interpreters=[sys.executable, *args.python], artifacts=args.artifacts
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"Validated {len(result['installations'])} clean artifact installations; "
        f"report: {args.report.name}"
    )


if __name__ == "__main__":
    main()
