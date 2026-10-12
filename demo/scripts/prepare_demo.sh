#!/bin/sh
# stdout is the new workspace path; human guidance goes to stderr.
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
. "$script_dir/common.sh"
[ "$#" -eq 0 ] || fail "Usage: sh demo/scripts/prepare_demo.sh"
command -v skout >/dev/null 2>&1 || fail "Install skout-scan and put skout on PATH first."
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
example="$repo_root/examples/pydantic-ai-agent"
# Explicit allowlist: never copy local state, environments, caches or active solutions.
for relative in agent.py evals.py README.md requirements.txt tests/test_tools.py tests/solutions/test_retry.py.example; do
    [ -f "$example/$relative" ] && [ ! -L "$example/$relative" ] ||
        fail "Missing or linked source: $relative"
done
workspace=$(mktemp -d /tmp/skout-demo.XXXXXX)
printf '%s\n' 'skout-public-demo-v1' > "$workspace/.skout-demo-owned"
mkdir -p "$workspace/tests/solutions"
for relative in agent.py evals.py README.md requirements.txt tests/test_tools.py tests/solutions/test_retry.py.example; do
    cp "$example/$relative" "$workspace/$relative"
done
printf '%s\n' "$workspace"
printf '%s\n' "Fresh demo ready. Next: cd \"$workspace\"; skout doctor; skout scan . --no-progress" >&2
printf '%s\n' "Enable: sh \"$script_dir/enable_solution.sh\" \"$workspace\"" >&2
printf '%s\n' 'Then rescan the SAME workspace; do not reset between scans.' >&2
