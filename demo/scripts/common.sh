#!/bin/sh
# Shared safeguards for demo-owned temporary workspaces.
set -eu

fail() {
    printf '%s\n' "Demo error: $*" >&2
    exit 1
}

validate_workspace() {
    [ "$#" -eq 1 ] || fail "Supply the workspace path from prepare_demo.sh."
    [ -d "$1" ] && [ ! -L "$1" ] || fail "Workspace must be a real directory."
    workspace=$(CDPATH= cd -P -- "$1" && pwd)
    case "$workspace" in
        /tmp/skout-demo.*|/private/tmp/skout-demo.*) ;;
        *) fail "Refusing a path outside the demo-owned /tmp/skout-demo.* scope." ;;
    esac
    [ -f "$workspace/.skout-demo-owned" ] &&
        [ ! -L "$workspace/.skout-demo-owned" ] || fail "Missing ownership marker."
    [ "$(cat "$workspace/.skout-demo-owned")" = 'skout-public-demo-v1' ] ||
        fail "Invalid ownership marker."
    [ -d "$workspace/tests" ] && [ ! -L "$workspace/tests" ] ||
        fail "Missing or linked tests directory."
    [ -d "$workspace/tests/solutions" ] && [ ! -L "$workspace/tests/solutions" ] ||
        fail "Missing or linked solutions directory."
    solution="$workspace/tests/solutions/test_retry.py.example"
    target="$workspace/tests/test_retry.py"
    [ -f "$solution" ] && [ ! -L "$solution" ] || fail "Missing or linked solution eval."
    [ ! -L "$target" ] || fail "Refusing a linked activation target."
}
