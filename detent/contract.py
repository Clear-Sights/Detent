"""The bound: Claude Code's own published hook-event schema, restated as data.

Source: https://code.claude.com/docs/en/hooks (Anthropic's own documentation — not the
March 2026 source-map leak, which this project deliberately does not use; see the dev repo's docs/archive/PROVENANCE.md).
This is the finite, versioned event taxonomy the harness already commits to. Detent's job is never
to guess at it — only to read what's already true here and act. If a future harness version adds,
renames, or removes an event, this file is the one place that changes; nothing below should ever
need to widen its own scope to compensate.

No LLM, no network, no state. Pure parsing of what the harness already put on stdin.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

# The complete, closed set of hook_event_name values, as documented. Not exhaustive of every
# field per event (tool-specific payloads are opaque dicts, by design — see moves.py), only of
# which events exist at all.
KNOWN_EVENTS = frozenset({
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PostToolUse", "PostToolUseFailure",
    "PermissionDenied", "PostToolBatch", "Stop", "StopFailure",
    "SubagentStart", "SubagentStop", "TeammateIdle", "TaskCreated", "TaskCompleted",
    "Notification", "PreCompact", "PostCompact", "InstructionsLoaded", "ConfigChange",
    "CwdChanged", "FileChanged", "SessionEnd", "Elicitation", "ElicitationResult",
    "MessageDisplay", "WorktreeCreate", "WorktreeRemove",
})

# The capability sets that used to live here (REWRITE/DENY/DEFER/BLOCK_CAPABLE) are now rows
# of dispatch.ENVELOPE — one table, (event, result-type) -> protocol shape, capability IS row
# existence. The doc citations moved onto the rows. The nominal types below remain the exact
# vocabulary a move answers with; dispatch tells envelopes apart by TYPE alone, never by
# inspecting dict content.

@dataclass(frozen=True)
class Deny:
    """A move's signal to veto the call outright, with a reason surfaced to the caller. A
    distinct nominal type (not a dict) so dispatch can tell it apart from a rewrite by TYPE
    alone, never by inspecting dict content — the same discipline REWRITE (dict) and ADVISORY
    (str) already follow."""
    reason: str


@dataclass(frozen=True)
class Defer:
    """A move's signal to route the permission decision to the PermissionRequest hook, where
    the same move fires again and its rewrite applies as a condition of approval. Same
    nominal-type discipline as Deny/Block: dispatch tells envelopes apart by TYPE alone."""
    reason: str


@dataclass(frozen=True)
class Block:
    """A move's signal to block the EVENT (not a tool call) via the top-level decision envelope
    — Stop keeps the model working with `reason` as its next instruction; UserPromptSubmit
    rejects the prompt. Same nominal-type discipline as Deny."""
    reason: str


def read_event(stream=None) -> dict[str, Any]:
    """Parse one hook invocation's JSON stdin payload. Raises ValueError on malformed input —
    a hook script should fail loudly, not guess, on a contract violation."""
    raw = (stream or sys.stdin).read()
    if not raw.strip():
        raise ValueError("empty stdin: hook was invoked with no payload")
    event = json.loads(raw)
    if "hook_event_name" not in event:
        raise ValueError("payload missing required 'hook_event_name' field")
    return event


def emit(output: dict[str, Any] | None, stream=None) -> None:
    """Write the hook's JSON stdout response. An empty/None output means: no opinion, pass
    through unchanged — Detent's default state is silence, per its own law."""
    out = stream or sys.stdout
    out.write(json.dumps(output or {}))
    out.write("\n")
