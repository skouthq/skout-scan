# Run from the checkout root, with installed skout and Python on PATH.
Require skout
Require python
Output demo/assets/skout-demo-v2-terminal.mp4
Set Shell bash
Set Width 1440
Set Height 1000
Set FontSize 32
Set TypingSpeed 15ms
Set Padding 24
Set Framerate 25
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
Type "# Your agent has tests. What are they missing?"
Enter
Type "ls agent.py evals.py tests/test_tools.py"
Enter
Sleep 6s
Ctrl+L
Type "skout doctor | grep -A 3 -E 'Detected frameworks|Repository readiness'"
Enter
Sleep 5s
Ctrl+L
Type "skout scan . --no-progress | sed -n '/Open findings:/,$p'"
Enter
Sleep 8s
Ctrl+L
Type "skout review"
Enter
Sleep 9s
Type "add_eval"
Sleep 3s
Enter
Sleep 3s
Ctrl+L
Type "skout findings | head -n 12"
Enter
Sleep 6s
Ctrl+L
Type 'sh "$DEMO_SCRIPTS/enable_solution.sh" "$DEMO_ROOT"'
Enter
Type "sed -n '9,14p' tests/test_retry.py"
Enter
Sleep 12s
Ctrl+L
Type "skout scan . --no-progress | sed -n '/Coverage assessments/,$p'"
Enter
Sleep 8s
Ctrl+L
Type "skout findings | head -n 12"
Enter
Sleep 5s
Ctrl+L
Type 'python "$DEMO_SCRIPTS/show_resolution.py"'
Enter
Sleep 9s
Ctrl+L
Type "# Find what your AI agent evals aren't testing."
Enter
Type "# Open source. Local-first. No source upload."
Enter
Type "# github.com/skouthq/skout-scan"
Enter
Sleep 9s
