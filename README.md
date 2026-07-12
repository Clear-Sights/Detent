# Detent

**One question: of everything an agent does, how much can be made reliably deterministic?**

Detent is a strictly passive, deterministic leverage layer for coding agents. The LLM's
irreducible remainder is reasoning — deciding, and emitting specs. Everything else — every read,
write, retrieval, verification, and presentation of fact — runs through deterministic machinery
instead of the default token transport: pure functions of the event and disk state, no model
call anywhere, ever. Generation is stochastic exactly once; the moment output exists it is a
content-addressed artifact, and every later use is a deterministic copy, never a re-emission.
Denial is never the point — it is only the redirect at the boundary, used exactly where the
default path is provably identical to a free deterministic one.

Read [`LAW.md`](LAW.md) (the admission test any move must pass). The primitive layer itself —
5 stations, 20 flow cells, complete by construction, every cell SERVED,
PARTIAL-with-named-machinery, or VOID-with-reason; silence is not a state — ships as code:
`detent/cells.py`, the punchcard.

## What's here

| Piece | What it is |
|---|---|
| `detent/contract.py` | the bound: Claude Code's documented hook schema as data, plus the three envelope types (rewrite dict / `Deny` / `Block` / advisory str) |
| `detent/dispatch.py` | the pivot: one stdin→stdout hook entrypoint; `(event, tool)` table lookup; picks the envelope by return type, never by content |
| `detent/moves.py` | the arms: every move is one composition **m = α∘φ∘π** — total projections, exact guards, typed envelope actions; 17 moves across three tiers, enforcement (pure), capture (write only to the store, atomically), and display (render-by-address at the screen boundary), each declaring its own station flows; coverage is a quotient, not an enumeration — wildcard rows bound EVERY tool's oversized output and gate the whole →WORLD class, including tools that don't exist yet |
| `detent/store.py` | the substrate: content-addressed artifact store — `put`/`get`/`materialize`/`slice` + an append-only firing ledger; identical bytes coincide, so N concurrent writers need zero coordination |
| `detent/cells.py` | the punchcard: the 20-cell coverage topology as data; the move rows are *derived* from each move's own flow declaration, reconciled against importable reality by tests — coverage drift is a red test, not a discovery |
| `tests/test_laws.py` | the universal laws, one parametrized test each over ALL moves: guard totality, rewrite idempotence (m∘m = ⊥), store monotonicity (CALM: monotone ⇒ coordination-free) |
| `detent/facts.py` | verified-fact reader (Makoto's hash-verified chain, or the session transcript) feeding the injection moves |
| `tools/mine_corpus.py` | corpus probe: re-derives what actually fires in your environment |

## Install (plugin)

```
/plugin marketplace add Clear-Sights/Detent
/plugin install detent@detent
```

Enabling the plugin is the whole install and the sign-off: `.claude-plugin/plugin.json` +
`hooks/hooks.json` auto-wire dispatch on enable.

For development:

```
pip install -e ".[test]"
pytest -q          # the public smoke test: catalog certifies, dispatch rewrites and denies
                   # on the real wire, store round-trips, status runtime exits clean.
                   # (The full 487-test falsifiability suite lives in the dev repo.)
python -m detent    # the status trace: wiring, 20-cell coverage, store stats; nonzero on drift
```

Every threshold is an env-overridable operand (`DETENT_GREP_HEAD_LIMIT`, `DETENT_TRUNCATE_THRESHOLD`,
`DETENT_TRUNCATE_KEEP`, `DETENT_READ_LARGE_BYTES`, `DETENT_READ_DEFAULT_LIMIT`) — read once at
import, which in production means per hook firing, since each firing is a fresh process. The
path operands (`DETENT_STORE_DIR`, `DETENT_UPLOADS_DIR`) are read per call. Configuration moves
the operand, never the predicate shape: a truncate-keep spanning the threshold (which would make
"truncation" inflate the payload) is clamped, not honored. Dispatch overhead, measured: ~60 ms
per hook invocation (interpreter startup dominates).

**Pointers, not transport.** The model may emit a reference where bytes it did not originate
belong, and machinery does the copy/paste (measured motivation: 11.5% of one build session's
entire model output was `old_string` anchor transport — bytes already on disk, re-typed to
point at them). A Write whose content is exactly `detent://<addr>` materializes those store
bytes (verified live: 73 output characters, arbitrary payload). An Edit whose old_string is
exactly `detent://L<a>-<b>` expands to those lines of the target file, then faces the same
cardinality gate as a typed anchor. Fragments paste by range: `detent://<addr>:L<a>-<b>` as a
Write's content or an Edit's new_string materializes exactly those lines of the stored
artifact — copy a piece of anything that ever existed, in one pointer. And the pointers work
for the human too: type `detent://<addr>` (or `:L<a>-<b>`) anywhere in a prompt and the hook
pushes the bytes to the model — measured motivation: 7.6% of one session's user-prompt bytes
were re-pastes of lines already in context. Dangling references are named, never dropped.
(Current Claude Code versions validate Edit input before PreToolUse rewrites apply, so the
Edit form routes through the harness's own documented seam instead: the pre hook answers
`permissionDecision: "defer"`, and the PermissionRequest hook applies the expansion as a
condition of approval — before the client's validation. The Write form works at PreToolUse
directly.)

Content search over the store needs no index: objects are plain files, so
`grep -rl 'needle' ~/.claude/detent_store/objects/` (or the Grep tool on that directory)
finds any artifact that ever mentioned a string — then slice it back by address. The 1973
primitive composes with the 2026 store; nothing new to learn or build.

`/detent` (the one slash command) relays that trace verbatim — the human's way to ask
"is the rod latched?" without trusting anyone's word for it.

## Adding a move

One composition in `detent/moves.py` (built from the π/φ/α generators at the top of the file,
carrying its `@_flows` station declaration), one row in the `MOVES` table, one red-then-green
test pair. The punchcard updates itself — cell rows are derived from the declaration — and the
universal law tests hold the new move to totality, idempotence, and monotonicity with zero new
test code. If it needs more than that — a database, a summarization step, a judgment call — it
isn't a Detent move; `LAW.md`'s five-clause test decides, not taste.

## License

Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). The explicit patent grant is
deliberate: this is infrastructure meant to be adopted, embedded, and ported.

## Sibling

[Makoto](https://github.com/Clear-Sights/Makoto) holds the agent to its word (integrity gates —
judgment-shaped checks); Detent holds the machinery to determinism (no judgment anywhere). The
two never import each other; Detent reads Makoto's chain by shape only.
