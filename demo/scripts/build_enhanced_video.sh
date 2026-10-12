#!/bin/sh
# Rebuild enhanced exports without changing the original terminal recording.
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'Python 3 is required.' >&2; exit 1; }
exec python3 "$script_dir/enhance_video.py"
