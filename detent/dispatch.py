"""The pivot. One hook entrypoint, wired to every event named in moves.MOVES (see
hooks/detent-hook.json). Reads the event, looks up (hook_event_name, tool_name) in moves.MOVES,
and — if a move fires — places its return value in whichever envelope shape that event type
supports. This module knows the protocol; moves.py knows nothing about it (that separation is
deliberate: a move's tests never need to know where in the JSON envelope its output lands).

THREE envelope shapes, per LAW.md's own "rewrite over observe" hierarchy:
  - REWRITE (the strong form): PreToolUse/PostToolUse — a move returns a dict, placed under
    updatedInput/updatedToolOutput. The call or its result is substituted outright.
  - DENY (a gate, not a rewrite — LAW.md §2.1: a block/veto is READ with a gate effect, not its
    own primitive): PreToolUse only today (contract.DENY_CAPABLE) — a move returns a
    contract.Deny(reason), placed under permissionDecision: "deny" / permissionDecisionReason.
    The call never executes; the reason is the only channel back to the caller.
  - ADVISORY (the fallback, "used only when there's no stronger one available"): every other
    event a move can register against (SubagentStart today; Stop/SessionStart per LAW.md, not
    yet used by any move) — a move returns a str, placed under additionalContext. The event
    proceeds untouched; the string is surfaced alongside it.
A move's own return TYPE (dict / Deny / str) matches the shape its registered event supports —
dispatch picks the envelope by event name and return TYPE, never by inspecting a dict's content.

Never initiates. If nothing in the table matches, or a move returns None, this emits {} — the
harness treats an empty response as "no opinion," exactly the detent's resting state. A move CAN
gate a call now (DENY) — that was always within LAW.md's own law (§2.1), just unimplemented until
a move needed it; what dispatch still never does is invent a decision beyond what a move computed,
or block on anything outside a move registered in MOVES and a hook event the harness already fired.
"""
from __future__ import annotations

import sys
from typing import Any

from detent.contract import BLOCK_CAPABLE, DENY_CAPABLE, Block, Deny, emit, read_event
from detent.moves import lookup

# REWRITE events: a move's dict return goes under this key.
_REWRITE_ENVELOPE_KEY = {
    "PreToolUse": "updatedInput",
    "PostToolUse": "updatedToolOutput",
}

# STR-envelope events: a move's str return goes under the event's own key — advisory context
# for most, displayContent for MessageDisplay (display-only by protocol: transcript and model
# keep the original; a failed hook displays the original — the harness itself fails open).
_STR_ENVELOPE_KEY = {
    "SubagentStart": "additionalContext",
    "Stop": "additionalContext",
    "SessionStart": "additionalContext",
    "UserPromptSubmit": "additionalContext",
    "MessageDisplay": "displayContent",
}


def route(event: dict[str, Any]) -> dict[str, Any]:
    hook_event_name = event.get("hook_event_name")
    tool_name = event.get("tool_name")
    move = lookup(hook_event_name, tool_name)
    if move is None:
        return {}
    replacement = move(event)
    if replacement is None:
        return {}
    if isinstance(replacement, Block):
        if hook_event_name not in BLOCK_CAPABLE:
            raise RuntimeError(
                f"a move for {hook_event_name!r} returned Block, but {hook_event_name!r} is not "
                f"in BLOCK_CAPABLE -- a Detent wiring bug, not a data problem.")
        return {"decision": "block", "reason": replacement.reason}
    if isinstance(replacement, Deny):
        if hook_event_name not in DENY_CAPABLE:
            raise RuntimeError(
                f"a move for {hook_event_name!r} returned Deny, but {hook_event_name!r} is not "
                f"in DENY_CAPABLE -- this is a Detent wiring bug (MOVES table registered a move "
                f"against an event whose protocol can't express a deny), not a data problem.")
        return {"hookSpecificOutput": {"hookEventName": hook_event_name,
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": replacement.reason}}
    str_key = _STR_ENVELOPE_KEY.get(hook_event_name)
    if str_key is not None and isinstance(replacement, str):
        return {"hookSpecificOutput": {"hookEventName": hook_event_name,
                                       str_key: replacement}}
    envelope_key = _REWRITE_ENVELOPE_KEY.get(hook_event_name)
    if envelope_key is None:
        return {}  # a move was registered against an unrecognized event — refuse silently
    return {"hookSpecificOutput": {"hookEventName": hook_event_name, envelope_key: replacement}}


def main() -> int:
    try:
        event = read_event()
    except ValueError as e:
        print(f"detent.dispatch: {e}", file=sys.stderr)
        emit({})  # malformed input is never a reason to block the harness — fail open, silent,
        return 0  # but stdout must still be the valid-empty-response the harness expects
    try:
        result = route(event)
    except Exception as e:
        # route() raising is always a Detent wiring bug (e.g. Deny returned outside DENY_CAPABLE),
        # never external data -- but this module's own contract ("this emits {} ... the harness
        # treats an empty response as 'no opinion'") has to hold even then. Loud to stderr (a
        # developer sees it, a test can assert on it), safe to stdout (the harness never sees a
        # broken response) -- the same fail-loud-then-fail-safe split read_event() already uses.
        print(f"detent.dispatch: move raised {e!r}", file=sys.stderr)
        emit({})
        return 0
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
