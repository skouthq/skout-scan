#!/bin/sh
# Fresh restart only: remove only known generated files in an owned workspace.
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
. "$script_dir/common.sh"
validate_workspace "$@"
if [ -e "$target" ]; then
    cmp -s "$solution" "$target" || fail "Activated test has changes; refusing to delete it."
fi
[ ! -L "$workspace/.agentguard" ] || fail "Refusing linked scan state."
if [ -e "$workspace/.agentguard" ]; then
    [ -d "$workspace/.agentguard" ] || fail "Scan state is not a directory."
fi
# All validations happen before either deletion.
rm -f -- "$target"
rm -rf -- "$workspace/.agentguard"
printf '%s\n' 'Fresh demo restored: solution inactive; demo scan history removed.'
