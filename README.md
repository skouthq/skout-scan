# Skout Scan

**Find what your AI agent evals aren't testing.**

Skout Scan statically scans your agent code and eval suite to surface
high-confidence behaviors that may be insufficiently tested.

**Local-first. No code execution. No source upload. No API key required.**

## Try Skout Scan

### 1. Install

Skout Scan requires Python 3.12 or newer.

```bash
pip install skout-scan
```

### 2. Scan your agent repository

```bash
cd your-agent-repo
skout scan .
```

Skout Scan discovers repository artifacts, extracts eval scenarios and
deterministic agent behaviors, matches behaviors against existing eval evidence,
and surfaces selected high-confidence potential gaps.

### 3. Review the findings

```bash
skout review
```

Run `skout review` from the same repository you scanned; review state is stored
locally in that repository. From another directory, use
`skout review --repository path/to/your-agent-repo`.

The full local workflow is:

```bash
cd your-agent-repo
skout scan .
skout review
skout metrics --repository .
```

The interactive review shows the source, evidence, coverage assessment, and a
suggested eval for each high-confidence potential gap. Skout Scan lets you
classify each finding as:

- `add_eval` — you intend to add or modify an eval
- `valid_later` — the gap is valid but is not a current priority
- `already_covered` — adequate coverage already exists
- `not_relevant` — the behavior does not need an eval
- `suppressed` — hide the finding from normal output

### 4. See your validation metrics

```bash
skout metrics --repository .
skout metrics --repository . --json
```

The JSON form provides a machine-readable export that you can share with the
Skout Scan team during V0 validation.

### 5. Give feedback

We're validating Skout Scan with engineers building real AI agents. If you try
it, we'd really value 2 minutes of feedback:

[Share feedback](https://forms.gle/EfTMt3dyhZnCTphN6)

Generate the JSON to paste into the feedback form with:

```bash
skout metrics --repository . --json
```

Skout Scan does not automatically upload metrics, source code, or repository
contents.

## What Skout Scan finds

A finding is an explainable potential gap, for example:

```text
Potential eval gap

Tool:
create_jira_ticket

Why flagged:
Skout Scan found the tool behavior but no eval that both exercises the behavior
and verifies its expected outcome.

Suggested test:
Invoke create_jira_ticket with valid inputs and verify the expected mutation.
```

Each detected behavior receives one of these assessments:

- `covered` — an eval meaningfully exercises the behavior and verifies its
  expected outcome or invariant
- `partially_covered` — an eval exercises the functionality, but does not fully
  verify a relevant condition, branch, failure path, or expected outcome
- `potentially_uncovered` — no discovered eval appears to materially exercise
  and verify the behavior

Skout Scan selects high-confidence actionable findings from these assessments.
It does not turn every raw assessment into a finding or calculate an overall
behavioral coverage percentage.

## Supported patterns

V0 extracts eval evidence from:

- pytest `test_*` functions and test methods in `Test*` classes
- direct `assert` statements and `pytest.raises`
- statically resolvable calls and literal arguments
- JSONL eval scenarios with an `input`, optional `expected`, and optional
  metadata such as a name or tool list

JSONL files are first classified with a bounded deterministic schema probe.
Files under eval-oriented paths or whose sampled object records consistently
contain `input` are parsed as eval datasets. Application JSONL used for memory,
caches, logs, or other data is ignored for eval coverage when its sampled schema
is clearly not an eval schema.

V0 extracts deterministic behaviors from:

- functions decorated with `@tool`, qualified `@*.tool`, or `@function_tool`
- local functions registered through literal tool collections, `tools=[...]`,
  or `bind_tools([...])`
- explicit raised exceptions and explicit failure returns
- deterministic conditional branches with visible return, raise, escalation,
  or handoff outcomes
- supported LangGraph `add_edge` transitions and literal
  `add_conditional_edges` routes on statically assigned `StateGraph` instances

Calls through `.invoke`, `.ainvoke`, and `.coroutine` are recognized as tool
invocations only when the receiver is already known statically as a tool. The
wrapper call alone does not prove that an expected outcome or failure path was
verified.

V0 also supports common statically analyzable CrewAI patterns:

- direct `Agent(...)`, `Task(...)`, and `Crew(...)` construction
- `@CrewBase` classes with `@agent`, `@task`, `@crew`, `@before_kickoff`, and
  `@after_kickoff` methods
- statically linked CrewAI YAML and plain JSON agent/task configuration
- CrewAI `@tool` functions, `BaseTool` subclasses, and literal agent/task tool
  attachments
- literal sequential task order, task context dependencies, and hierarchical
  crew metadata without inferred runtime delegation paths
- explicit Flow `@start`, `@listen`, and `@router` relationships and literal
  router targets

CrewAI role, goal, backstory, task description, and expected-output text are
retained as structured evidence. Skout does not interpret that prose as a
behavioral guarantee.

Skout reports provenance counts for statically linked CrewAI YAML and JSON
configuration. Literal Markdown or text instruction files referenced by those
configs may be retained as linked evidence, but their natural-language contents
are not converted into behavioral obligations.

## How it works

```text
Repository
↓
Discover artifacts
↓
Extract eval scenarios
↓
Extract deterministic agent behaviors
↓
Match behaviors to eval evidence
↓
Surface high-confidence potential gaps
↓
Engineer reviews findings
↓
Persist local lifecycle and feedback
```

Analysis and matching are static and deterministic. Skout Scan never imports or
executes Python from the target repository. It stores finding history, review
feedback, and scan history in `.agentguard/agentguard.db` within the scanned
repository.

Behavior and finding IDs are designed to survive formatting, whitespace, and
line movement where possible. On later scans with sufficient evidence for a
finding, Skout Scan can observe when a new or modified eval covers it and record
that finding as resolved. Review choices and lifecycle history persist locally
across scans.

## Limitations

- Static analysis is intentionally conservative. Indirect calls, fixture
  indirection, aliases, and wrappers outside the supported patterns may be
  missed.
- Dynamically constructed tool, agent, or workflow registration may not be
  discovered.
- Dynamic CrewAI task/agent lists, runtime orchestration, computed config paths,
  and non-literal Flow routes may not be recoverable. CrewAI JSONC configuration
  is detected but is not parsed in V0.
- Dynamic pytest parametrization has limited support.
- Prompt files are discovered, but natural-language prompt obligations are not
  extracted as behaviors in V0.
- Ambiguous JSONL produces one classification warning and is skipped. Malformed
  records in a recognized eval dataset remain incomplete eval evidence.
- Unsupported or dynamic evidence can make affected assessments unavailable.
  Unrelated application data and skipped cache directories do not invalidate
  otherwise assessable behaviors.
- File moves, symbol renames, and major restructuring may change stable IDs.
- V0 does not use semantic, embedding, or LLM-based matching.
- V0 does not analyze production traces.
- Skout Scan does not calculate an overall numeric behavioral coverage
  percentage.
- Findings are potential testing gaps. They do not certify that an agent is
  safe, unsafe, production-ready, or inadequately tested.

## Configuration

Configuration is optional. When present, `agentguard.toml` must be in the root
of the repository being scanned.

```toml
include = ["**/*.py", "**/*.jsonl"]
exclude = ["**/.venv/**", "**/.agentguard/**", "**/build/**", "**/dist/**"]
```

`include` selects candidate artifacts and `exclude` removes matching paths;
exclusions take precedence. Patterns match POSIX-style paths relative to the
repository root and support recursive `**` segments.

Without a configuration file, Skout Scan includes Python, text, Markdown, and
JSONL files and excludes common Git, virtual-environment, dependency, cache,
tool-runtime, build, distribution, and local-state directories, including
`.uv-cache` and `.tools`. `knowledge/`, `config/`, `skills/`, and `output/` are
not excluded by default. Symbolic links are not followed.

## Development

Create a Python 3.12 environment and install the project with development tools:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The public distribution and command are `skout-scan` and `skout`. The current
internal Python package remains `agentguard` under `src/agentguard/`.

Run the contributor checks:

```bash
pytest
ruff check .
ruff format --check .
mypy src/agentguard
```

Validate release artifacts with:

```bash
python -m build
python -m twine check dist/*
```

Release maintainers should follow the
[release guide](https://github.com/skouthq/skout-scan/blob/main/docs/releasing.md).
