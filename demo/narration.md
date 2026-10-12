# V2 narration — approximately 90 seconds

Your AI agent has tests. But are they testing the behaviors that matter?

This Pydantic AI refund assistant already has a tool test and eval evidence.
Skout inspects the repository locally, without running the agent or uploading
source. Doctor confirms the framework is recognized and the repository can be
assessed. That does not mean the agent has adequate test coverage.

The scan identifies a potentially uncovered validator failure path.
For refunds above five hundred, validate_refund raises ModelRetry to request
human review. The existing eval evidence does not verify that outcome.

The engineer reviews the source evidence and suggested scenario, then classifies
the finding as add_eval. That records an intention. It does not generate a test,
and it does not resolve the finding.

Now the engineer adds the supplied eval. The test constructs a high-value refund
and verifies that the validator raises ModelRetry.

Skout rescans the same repository, preserving the finding history. New eval
evidence exercises the condition and verifies the expected exception.
The original finding is now resolved, with covered status and the same identity.
The evidence references tests/test_retry.py.

Skout Scan finds potential gaps in your AI agent evals.
Open source. Local-first. No source upload.
Try it at github.com/skouthq/skout-scan.

This is a script for optional voice recording; no synthetic voice or recorded
narration is included. Captions remain sufficient without audio.

## LinkedIn accompanying post

Your agent has evals. But are they testing the behaviors that matter?

This demo follows one real gap through the full workflow: Skout flags a Pydantic
AI validator retry path, an engineer reviews it and records add_eval, then adds
an eval. On rescan, Skout recognizes the new evidence and resolves the original
finding. Selecting add_eval alone does not write a test or resolve anything.

Static inspection. Local-first. No source upload.
https://github.com/skouthq/skout-scan

Try it on your agent repository. Did it identify a missing eval you would add?

A short LinkedIn video edit is deferred until the full v2 master is approved.
