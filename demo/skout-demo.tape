# Run from the repository root with skout on PATH.
Require skout
Require sh
Require grep
Require cat
Output demo/assets/skout-demo.gif
# Optional outreach video: uncomment locally; keep large intermediates untracked.
# Output demo/assets/skout-demo.mp4
Set Shell bash
Set Width 1440
Set Height 1000
Set FontSize 24
Set TypingSpeed 20ms
Set Padding 20
Set Framerate 12
Set CursorBlink false
Env PS1 "$ "
Env NO_COLOR "1"
Hide
Type 'export DEMO_SCRIPTS="$PWD/demo/scripts"; DEMO_ROOT=$(sh demo/scripts/prepare_demo.sh) || exit 1; export DEMO_ROOT'
Enter
Sleep 1s
Type 'cd "$DEMO_ROOT" || exit 1; clear'
Enter
Sleep 500ms
Show
Type "# Your agent has evals. Are they testing the behaviors that matter?"
Enter
Type "ls agent.py evals.py tests/test_tools.py"
Enter
Sleep 5s
Type `skout doctor | grep -A 3 -E 'Detected frameworks|Eval discovery|Behavior discovery|Repository readiness'`
Enter
Sleep 6s
# Display a genuine diagnostic excerpt, then focus the next scene.
Ctrl+L
Type "skout scan . --no-progress"
Enter
Sleep 7s
Ctrl+L
Type "skout findings"
Enter
Sleep 15s
Ctrl+L
Type 'sh "$DEMO_SCRIPTS/enable_solution.sh" "$DEMO_ROOT"'
Enter
Type "cat tests/test_retry.py"
Enter
Sleep 10s
Ctrl+L
Type "skout scan . --no-progress"
Enter
Sleep 6s
Ctrl+L
Type "skout findings"
Enter
Sleep 12s
Ctrl+L
Type "# Open source. Local-first. No source upload."
Enter
Type "# https://github.com/skouthq/skout-scan"
Enter
Sleep 5s
# No reset between scans: they share one repository and state database.
