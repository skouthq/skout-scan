# V2 recording / V3 visual-polish storyboard

The recording uses real CLI commands and a fresh temporary copy of the supplied
Pydantic AI example. Relative source paths and one state database remain stable.
Exact finalized caption and annotation timestamps are in the editable SRT/JSON.

| Approximate time | Visual | Command/action | Viewer understanding |
| --- | --- | --- | --- |
| 0–9s | Agent, eval and test files | `ls agent.py evals.py tests/test_tools.py` | The agent already has tests. |
| 9–14s | Framework/readiness excerpt | `skout doctor` with grep | Pydantic AI is recognized; readiness is assessability. |
| 14–23s | Validator gap, red outline | `skout scan . --no-progress` with sed | Existing evidence does not verify the failure path. |
| 23–38s | Actual review prompt, amber outline | `skout review`, type `add_eval`, Enter | The engineer reviews and records intent. |
| 38–44s | Open finding classified add_eval | `skout findings` with head | Classification persists; it has not resolved the gap. |
| 44–58s | New test, amber assertion outline | Existing activation script; show test excerpt | The engineer adds an eval verifying ModelRetry. |
| 58–66s | Rescan coverage/lifecycle summaries | `skout scan . --no-progress` with sed | Same repository/database; new evidence is detected. |
| 66–81s | Resolved/covered and exact matched test | `skout findings`; read-only `show_resolution.py` | Original ID preserved; test path supports resolution. |
| 81–90.72s | Project URL | Shell comments (clearly presentation text) | Open source, local-first; try Skout. |

The evidence helper is explicitly labelled and never presented as a built-in CLI
command. It joins real stored matched IDs to real statically extracted evals.
Captions explain the actions; they are not substitutes for terminal results.
No generated test, target execution, confirmed-impact claim or state editing.

## V3 overlay schedule (recording unchanged)

| Time | Visual treatment | Meaning |
| --- | --- | --- |
| 14–16s | DISCOVER THE GAP, teal accent | Enter discovery stage. |
| 18–21.5s | 5 px red rounded outline | Actual potentially uncovered validator finding. |
| 23–25s | REVIEW & CLASSIFY | Engineer inspects the finding. |
| 32–44s | Short intent caption plus subtle classification-only label | add_eval does not create a test. |
| 33.5–36.5s | 5 px amber rounded outline | Actual typed add_eval selection. |
| 44–46s | ADD THE MISSING EVAL | Separate engineer action activates supplied test. |
| 49–53s | 5 px amber rounded outline | pytest.raises(ModelRetry) verifies the expected failure. |
| 58–60s | VERIFY RESOLUTION | Same repository is rescanned. |
| 66–72s | New eval evidence detected | Actual scan/findings output establishes coverage. |
| 74–79s | 6 px green rounded outline and payoff overlay | Real resolved/covered values; unchanged ID and matched test remain visible. |
| 81–90.72s | Short closing caption | Project positioning and URL. |

No zoom or frozen frames: the existing evidence scene already provides enough
reading time. V3 reuses the exact V2 audio stream and preserves all prior assets.
