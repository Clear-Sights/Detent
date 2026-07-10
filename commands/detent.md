---
description: Detent status — is the rod latched, is the punchcard honest. Runs the deterministic status trace and relays it verbatim.
---

Run `python3 -m detent` from the plugin root (if that import fails, run it with
`PYTHONPATH=${CLAUDE_PLUGIN_ROOT}`). Relay its COMPLETE output verbatim in a code block — do not
summarize, reorder, or annotate it; the trace IS the status (BEDROCK cell 17's contract). If it
exited nonzero, state only: "coverage check FAILED — see FAIL lines above." Nothing else.
