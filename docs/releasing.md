# Releasing Skout Scan

Skout Scan uses PyPI Trusted Publishing. The release workflow exchanges a
GitHub Actions identity token for a short-lived PyPI publishing token, so the
repository does not store a PyPI password or API token.

## One-time PyPI and GitHub setup

1. Create or sign in to the maintainer account at
   [PyPI](https://pypi.org/account/login/) and enable two-factor authentication.
2. Create a GitHub environment named `pypi` in
   `skouthq/skout-scan` under **Settings → Environments**.
3. Add required reviewers to the `pypi` environment. Restrict deployment to
   protected tags matching `v*` when that option is available for the
   repository plan.
4. Configure a PyPI Trusted Publisher for these exact values:

   | Setting | Value |
   | --- | --- |
   | PyPI project name | `skout-scan` |
   | GitHub owner | `skouthq` |
   | GitHub repository | `skout-scan` |
   | Workflow filename | `release.yml` |
   | GitHub environment | `pypi` |

For the first release, if the `skout-scan` project does not exist yet, open
**Your account → Publishing** on PyPI and add a **pending publisher** with the
values above. A pending publisher creates the project during its first upload;
it does not reserve the project name beforehand. If the project already exists
under an account you control, open **Your projects → skout-scan → Manage →
Publishing** and add the publisher there. The publisher configuration and
`.github/workflows/release.yml` must use the same owner, repository, workflow
filename, and environment.

## Prepare and publish a release

1. Confirm that `pyproject.toml` contains the intended version and that the
   working tree is clean.
2. Run the release checks locally:

   ```bash
   python -m pip install -e ".[dev]"
   pytest
   ruff check .
   ruff format --check .
   mypy src/agentguard
   mypy tools/behavior_audit tools/release_validation.py tools/release_smoke.py
   python -m build
   python -m twine check dist/*
   python -m tools.release_validation --artifacts dist --report release-validation.json
   ```

3. Merge the release-ready commit into the default branch and confirm CI is
   green.
4. Tag that exact commit with the version from `pyproject.toml` and push the
   tag:

   ```bash
   git tag -a v0.1.0 -m "Skout Scan 0.1.0"
   git push origin v0.1.0
   ```

   The release workflow verifies that the tag and package version match before
   building distributions.

5. In GitHub Actions, review the `Release` workflow run. Approve its `pypi`
   environment deployment after checking the tag and built artifacts.

The tag starts the release workflow. Ordinary branch pushes and pull requests
cannot publish to PyPI.

## Validate the distribution before authorizing publication

The [release-readiness report](release-readiness.md) distinguishes current source
from the published package. Version remains authoritative in `pyproject.toml`.
Do not reuse a published version for changed artifacts.

The reusable harness can build its own artifacts and test additional locally
installed interpreters:

```bash
python -m tools.release_validation --python /path/to/python3.13 --report release-validation.json
```

It creates dedicated temporary build/install environments outside the checkout,
installs both wheel and sdist with declared dependencies, runs `pip check`, and
checks the actual installed console entry point. Public examples, SQLite
resolution/feedback, M9 comparison, scopes, guidance and invalid arguments are
exercised. Dependencies may download during setup; runtime network and unsupported
subprocesses are blocked, and framework libraries/API keys are unnecessary.
Only harness-owned temporary directories are cleaned up. No upload, tag, commit
or user database reset is performed. `--artifacts dist` validates already built
artifacts; supply exactly one wheel and one sdist for the current source version.

CI now requests Python 3.12, 3.13, 3.14 and 3.15 and retains a validation report
for each matrix job. The existing `test-and-build` check name is retained as an
aggregate gate requiring every matrix job to pass. Configuring that matrix is not
evidence that it has passed.
Before publishing, verify the exact release-ready commit has green matrix checks.
The tag build also requires clean artifact-install smoke tests before artifacts
can reach the separate OIDC publishing job. No publishing trigger or permission
has been widened.

Trusted Publisher and environment protection settings live outside this repository.
Confirm the exact repository/workflow/environment values and required approvals
in GitHub/PyPI before authorizing a release. Static workflow inspection alone
does not confirm these external settings. See the
[draft release notes](release-notes-draft.md) for the proposed next release.

## Verify the published package

Wait for the PyPI project page to show the new release, then test from a clean
directory and virtual environment:

```bash
python3.12 -m venv /tmp/skout-release-check
/tmp/skout-release-check/bin/python -m pip install --upgrade pip
/tmp/skout-release-check/bin/python -m pip install skout-scan==0.1.0
/tmp/skout-release-check/bin/skout --version
/tmp/skout-release-check/bin/skout --help
/tmp/skout-release-check/bin/python -c "import agentguard"
```

PyPI does not allow replacing a file for an existing project/version pair. If
a release artifact is wrong, increment the package version, rebuild, and create
a new tag rather than retrying the same version.
