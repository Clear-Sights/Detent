# The law

A detent adds no energy. It is a rigid body on a low-friction pivot; every bit of motion through
it comes from force already in flight. This project is that, literally, not as a metaphor to
decorate an architecture doc: **Detent never initiates.** No LLM call of its own, no polling, no
orchestration round, no motor. It is positioned at a point a coding-agent harness already hits on
every tool call, and it converts whatever force lands there into more displacement than the force
would have produced landing flat.

## The bound

Claude Code's own hook documentation (`code.claude.com/docs/en/hooks`) defines a finite, closed
set of event types — `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `PreCompact`, and about
25 others, `detent/contract.py:KNOWN_EVENTS` — plus a common envelope present on every one of them
(`session_id`, `cwd`, `permission_mode`, `hook_event_name`, `agent_id`, ...). This is the actual
bound: not something Detent has to construct by sampling transcripts and hoping the rare cases show
up, but something Anthropic already enumerated and versioned. A deterministic corpus probe (see
`docs/archive/SIGNAL-INVENTORY.md` (dev repo)) still matters — it confirms which events a given harness build
actually fires and fills in the tool-specific parts of `tool_input`/`tool_response` the schema
deliberately leaves generic — but the schema gives completeness the probe alone cannot: a rare,
extreme-impact event (a sandboxed-bypass flag, a blocking error) doesn't have to have already
fired in a small corpus to be real and worth a pivot.

**No matter which model is behind the session, this schema is the same.** It's emitted by the
harness and the tool-call protocol, not by the model's behavior — which is exactly why Detent
works identically under Sonnet, Opus, Fable, or a future model nobody's named yet. The signals
exist because of the scaffolding, not the intelligence running inside it.

## Rewrite over observe

Three of the documented envelope slots are stronger than the rest: `PreToolUse` may return
`hookSpecificOutput.updatedInput`, `PermissionRequest` may return
`hookSpecificOutput.decision.updatedInput` (the same substitution, at the approval gate instead
of the pre-execution gate), and `PostToolUse` may return `hookSpecificOutput.updatedToolOutput`.
Most of what an awareness layer like this could do is the weak form — annotate, advise, inject a
line of `additionalContext` and hope it's read. The strong form is different in kind: **hand back
a different call, or a different result, before either one costs anything.** Trim a Grep result to
the part that matters before the other nine thousand lines are ever paid for. That's not force
nudged in a better direction — it's force substituted outright, which is the literal definition of
a detent, not an analogy for one.

(`MessageDisplay`'s `hookSpecificOutput.displayContent` is a rewrite-shaped field but not a
rewrite in this sense — it changes what's rendered, never what the model sees, pays for, or
conditions future behavior on. It substitutes nothing costly, so it stays out of this tier
entirely; see `detent/contract.py`'s `REWRITE_CAPABLE` comment for the full reasoning.)

A block or veto is not a fourth primitive — §2.1 of this project's own design already settled
that a gate is READ with a gate effect, not its own op — but it is a third *envelope* shape,
distinct from both REWRITE and ADVISORY: `PreToolUse` may also return
`hookSpecificOutput.permissionDecision: "deny"` with a `permissionDecisionReason`, vetoing the
call outright with no substitute call offered. `detent/contract.py`'s `DENY_CAPABLE` names which
events support it (`PreToolUse` only, confirmed live 2026-07-09). This is strictly weaker than a
true cross-tool rewrite — Claude Code's protocol has no mechanism for a hook to substitute a
*different* tool's call in place of the one requested, only to modify the same tool's own input
or veto it — so a move built on this tier can stop a call and name what should have been called
instead, never silently make that call itself.

Every move in `detent/moves.py` targets a rewrite-capable event first. Advisory
(`additionalContext`) is the fallback for events that don't support a rewrite at all (`Stop`,
`SessionStart`, and — confirmed against Anthropic's own hooks reference, 2026-07-07 —
`SubagentStart`: strictly informational, no `updatedInput`-style prompt rewrite exists for it) —
real, but the weaker tier, used only when there's no stronger one available. `detent/dispatch.py`
implements both envelope shapes explicitly (a move's return TYPE — `dict` vs `str` — matches the
shape its registered event supports); this was previously described here before any advisory
move existed to exercise it (`subagent_warm_start`, targeting `SubagentStart`, is the first).

## Never transform with a model — only relocate or rewrite facts

The single mistake nearly every adjacent open-source project makes (verified this session against
Aider, Mem0, Letta, Zep, memvid, claude-mem, episodic-memory — see the research this repo's
history carries forward) is hiding a model call inside what's marketed as a deterministic
mechanism: "compress with AI," "summarize at write time," an embedding model a retrieval step
secretly depends on. Detent's rule against this is absolute: **a move is either a pure function of
data the harness already emitted, or it doesn't ship.** No move summarizes. No move judges. A move
truncates, defaults, counts, diffs, or blocks — operations a compiler could verify, not operations
a second opinion is needed for.

## Passive, and yet adaptive

Passive: nothing runs unless the harness was already going to call the hook regardless of Detent's
presence. Adaptive: because moves are written against the *documented, stable event shape*
(`hook_event_name`, `tool_name`, the specific field a move reads) rather than against a model's
behavior, the same dispatcher and the same table survive a model swap untouched. What does NOT
survive untouched is a harness-schema change — which is why `detent/contract.py` is the one file
that's allowed to need updating when a new Claude Code version ships, and why the corpus probe in
`docs/archive/SIGNAL-INVENTORY.md` is a re-runnable script, not a one-time table someone eyeballed once and
froze. A frozen table drifts the moment the harness it was mined from changes shape (this
project's own founding research hit exactly this: an imported 194-row signal frontier assumed
`toolUseResult.exitCode` existed; this deployment's real Bash results carry `stdout`/`stderr`/
`interrupted` instead — the frontier's *ratings* were still useful, its literal paths were not).

## Selection test for any future move

A candidate earns a place in `detent/moves.py` only if all five hold, checked per invocation — a
broad, widely-applicable mechanism is fine (ideal, even); what must never happen is any single
call being let through on a fuzzy or ambiguous input:

1. **Free** — every input it reads is already being emitted by the harness regardless of whether
   Detent exists.
2. **Deterministic** — no model call, no judgment call, in the write path or the read path.
3. **Determinate** — an input that admits two readings is rejected with a hard error, never
   resolved by a best-effort guess or a silent first-match fallback. ("Take the first match" is
   fine when it's the *declared contract*, fixed at authoring time — "the 3rd occurrence of X" —
   never when it's a repair grabbed after the fact because a call that expected exactly one match
   got several.)
4. **Closed** — no two inputs identical on the operation's *read-slice* (the specific fields it
   actually reads) can demand different correct outputs. This is the deepest test: a rule can be
   perfectly deterministic and still be deterministically *wrong* sometimes, if the correct answer
   depends on something outside what the rule reads. ("Auto-retry any failed Bash command once"
   fails this — a transient `mkdir` hiccup and a payment script dying partway through are
   identical on everything the rule reads (command string, exit code), yet the right response
   differs; idempotency isn't in the read-slice and can't be added to it. That's judgment wearing
   determinism's clothes, not a rule.)
5. **Standalone** — the move's absence must be detectable by a one-sentence outcome test that
   names no sibling move; a fragment only meaningful paired with another move (shipping just the
   delete half of a delete+insert pair) fails this.

Breadth is not a disqualifier — a mechanism invokable on almost every call is *more* in scope for
being widely invokable, not less, as long as every single invocation still passes all five above.
What a move's friction *cascades into* if left undetented is a real signal, but only for deciding
what to build **next** among candidates that already passed the five — it never admits or rejects
a candidate on its own, and a move that rarely fires is still legitimately Detent if it clears the
bar above, just low priority to build.

## Two tiers of move (amendment 2026-07-10, follows from BEDROCK)

**Enforcement moves** are pure functions of the event — they write nowhere but their return
value, exactly as before. **Capture moves** (the machinery of BEDROCK cells 3, 8, 11, 20) may
additionally write — but ONLY into the artifact store (`$DETENT_STORE_DIR`, via `detent.store`),
atomically and replayably, never anywhere else: not the workspace, not config, not the
transcript. A capture write is an observation being recorded, not an action being taken; it
never changes what any tool call does or returns. Both tiers remain bound by everything above —
no model, no network, no judgment, fail open on anything ambiguous.
