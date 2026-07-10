"""The pivot. One hook entrypoint, wired to every event named in moves.MOVES (see
hooks/hooks.json). Reads the event, folds the cell functions lookup() returns, and shapes the
first result through ONE table: ENVELOPE[(event, result-type)] -> protocol shape. This module
knows the protocol; moves.py knows nothing about it (that separation is deliberate: a move's
tests never need to know where in the JSON envelope its output lands).

Everything dispatch knows is rows. A move's return TYPE picks the row — dict (REWRITE, the
strong form: the call/result/input is substituted outright), Deny (a gate, not a rewrite —
LAW.md §2.1), Defer (route the decision and the rewrite seam to PermissionRequest), Block
(the top-level decision envelope), str (ADVISORY, the fallback). Capability IS row existence:
a decision type returned on an event with no row raises (a Detent wiring bug, never data);
dict/str with no row emit {} — the harness treats an empty response as "no opinion", exactly
the detent's resting state. Never initiates: no move fires, nothing is emitted.
"""
from __future__ import annotations

import sys
from typing import Any

from detent.contract import Block, Defer, Deny, emit, read_event
from detent.moves import _is_world_tool, lookup


def _hso(event_name: str, **fields) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": event_name, **fields}}


# The whole protocol, as rows. Each is a documented shape (code.claude.com/docs/en/hooks,
# confirmed 2026-07-09/10); adding a capability is adding a row, never a branch.
ENVELOPE: dict[tuple[str, type], Any] = {
    # REWRITE — substitution outright. MessageDisplay is deliberately absent: displayContent
    # is display-only (changes what's rendered, never what the model sees or pays for), so a
    # dict there would be a rewrite that rewrites nothing — it fails LAW.md's selection test.
    ("PreToolUse", dict): lambda e, v: _hso(e, updatedInput=v),
    ("PostToolUse", dict): lambda e, v: _hso(e, updatedToolOutput=v),
    # PermissionRequest's rewrite IS the approval: decision.updatedInput applies as a condition
    # of behavior "allow" — the one event where the rewrite precedes client-side validation
    # (the defer seam's landing site).
    ("PermissionRequest", dict): lambda e, v: _hso(
        e, decision={"behavior": "allow", "updatedInput": v}),
    # DENY — a gate effect of READ, not its own primitive (LAW.md §2.1); the reason is the
    # only channel back to the caller and must never re-emit what it caught.
    ("PreToolUse", Deny): lambda e, v: _hso(
        e, permissionDecision="deny", permissionDecisionReason=v.reason),
    ("PermissionRequest", Deny): lambda e, v: _hso(
        e, decision={"behavior": "deny", "message": v.reason}),
    # DEFER — route the permission decision (and with it the rewrite opportunity) to the
    # PermissionRequest hook, whose updatedInput lands BEFORE client-side input validation.
    ("PreToolUse", Defer): lambda e, v: _hso(
        e, permissionDecision="defer", permissionDecisionReason=v.reason),
    # BLOCK — the top-level decision envelope: Stop keeps the model working with `reason` as
    # its next instruction; UserPromptSubmit rejects the prompt.
    ("Stop", Block): lambda e, v: {"decision": "block", "reason": v.reason},
    ("UserPromptSubmit", Block): lambda e, v: {"decision": "block", "reason": v.reason},
    # ADVISORY — the fallback, used only where no stronger shape exists. displayContent is
    # display-only by protocol: transcript and model keep the original; a failed hook displays
    # the original — the harness itself fails open.
    ("SubagentStart", str): lambda e, v: _hso(e, additionalContext=v),
    ("Stop", str): lambda e, v: _hso(e, additionalContext=v),
    ("SessionStart", str): lambda e, v: _hso(e, additionalContext=v),
    ("UserPromptSubmit", str): lambda e, v: _hso(e, additionalContext=v),
    ("MessageDisplay", str): lambda e, v: _hso(e, displayContent=v),
}

_DECISION_TYPES = (Deny, Block, Defer)


def route(event: dict[str, Any]) -> dict[str, Any]:
    hook_event_name = event.get("hook_event_name")
    tool_name = event.get("tool_name")
    advisories = []
    replacement = None
    for move in lookup(hook_event_name, tool_name):
        result = move(event)
        if result is None:
            continue
        if isinstance(result, str):
            advisories.append(result)   # advisories accumulate across cell functions
            continue
        replacement = result            # first non-advisory envelope wins; later fns skipped
        break
    if replacement is None and advisories:
        replacement = "\n".join(advisories)
    if replacement is None:
        return {}
    shape = ENVELOPE.get((hook_event_name, type(replacement)))
    if shape is None:
        if isinstance(replacement, _DECISION_TYPES):
            raise RuntimeError(
                f"a move for {hook_event_name!r} returned {type(replacement).__name__}, but "
                f"ENVELOPE has no ({hook_event_name!r}, {type(replacement).__name__}) row -- "
                f"a Detent wiring bug (an enforcement promise the protocol can't express "
                f"here), never a data problem.")
        return {}  # dict/str with no row: refuse silently — the documented resting state
    return shape(hook_event_name, replacement)


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
        # route() raising is always a Detent wiring bug (a decision type without an ENVELOPE
        # row), never external data. Loud to stderr; then the failure DIRECTION is chosen by
        # what was at stake: rewrites and capture fail OPEN ({} -- availability, the harness
        # proceeds untouched), but the outbound enforcement gate fails CLOSED -- a security
        # gate that silently vanishes when its own machinery errors was never a gate. Scope
        # is exact: (PreToolUse, ->WORLD-class tool) only, decided by the same _is_world_tool
        # predicate the gate itself uses.
        print(f"detent.dispatch: move raised {e!r}", file=sys.stderr)
        emit(_failure_envelope(event))
        return 0
    emit(result)
    return 0


def _failure_envelope(event: dict[str, Any]) -> dict[str, Any]:
    try:
        if (event.get("hook_event_name") == "PreToolUse"
                and _is_world_tool(str(event.get("tool_name") or ""))):
            return _hso("PreToolUse", permissionDecision="deny",
                        permissionDecisionReason=(
                            "detent: internal error while the outbound gate was due to run; "
                            "failing closed for the →WORLD tool class (see dispatch "
                            "stderr). Retry the call; report if it persists."))
    except Exception:
        pass  # the failure path must never itself fail; fall through to open
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
