#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
. "$script_dir/common.sh"
validate_workspace "$@"
if [ -e "$target" ]; then
    cmp -s "$solution" "$target" || fail "Activation target has changes; refusing to overwrite it."
else
    cp "$solution" "$target"
fi
printf '%s\n' 'Enabled tests/test_retry.py from the supplied solution; scan history preserved.'
