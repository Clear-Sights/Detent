# Lever

**One question: of everything an agent does, how much can be made reliably deterministic?**

Lever is a strictly passive, deterministic leverage layer for coding agents. The LLM's
irreducible remainder is reasoning — deciding, and emitting specs. Everything else — every read,
write, transport, verification, and presentation of fact — is machinery here: pure functions of
the event and disk state, no model call anywhere, ever. Generation is stochastic exactly once;
the moment output exists it is a content-addressed artifact, and every later use is a
deterministic copy, never a re-emission.

Read [`LAW.md`](LAW.md) (the admission test any move must pass) and [`BEDROCK.md`](BEDROCK.md)
(the settled primitive layer: 5 stations, 20 flow cells — complete by construction, every cell
SERVED, PARTIAL-with-named-machinery, or VOID-with-reason; silence is not a state).

## What's here

| Piece | What it is |
|---|---|
| `lever/contract.py` | the bound: Claude Code's documented hook schema as data, plus the three envelope types (rewrite dict / `Deny` / `Block` / advisory str) |
| `lever/dispatch.py` | the pivot: one stdin→stdout hook entrypoint; `(event, tool)` table lookup; picks the envelope by return type, never by content |
| `lever/moves.py` | the arms: every move is one composition **m = α∘φ∘π** — total projections, exact guards, typed envelope actions; 17 moves across three tiers, enforcement (pure), capture (write only to the store, atomically), and display (render-by-address at the screen boundary), each declaring its own station flows; coverage is a quotient, not an enumeration — wildcard rows bound EVERY tool's oversized output and gate the whole →WORLD class, including tools that don't exist yet |
| `lever/store.py` | the substrate: content-addressed artifact store — `put`/`get`/`materialize`/`slice` + an append-only firing ledger; identical bytes coincide, so N concurrent writers need zero coordination |
| `lever/cells.py` | the punchcard: BEDROCK's 20-cell coverage as data; the move rows are *derived* from each move's own flow declaration, reconciled against the doc AND against importable reality by tests — coverage drift is a red test, not a discovery |
| `tests/test_laws.py` | the universal laws, one parametrized test each over ALL moves: guard totality, rewrite idempotence (m∘m = ⊥), store monotonicity (CALM: monotone ⇒ coordination-free) |
| `lever/facts.py` | verified-fact reader (Makoto's hash-verified chain, or the session transcript) feeding the injection moves |
| `tools/mine_corpus.py` | corpus probe: re-derives what actually fires in your environment |

## Install (plugin)

Enable the plugin — that's the whole install. `.claude-plugin/plugin.json` +
`hooks/hooks.json` auto-wire dispatch on enable; enabling **is** the sign-off.

For development:

```
pip install -e ".[test]"
pytest -q          # the public smoke test: catalog certifies, dispatch rewrites and denies
                   # on the real wire, store round-trips, status runtime exits clean.
                   # (The full 487-test falsifiability suite lives in the dev repo.)
python -m lever    # the status trace: wiring, 20-cell coverage, store stats; nonzero on drift
```

Every threshold is an env-overridable operand (`LEVER_GREP_HEAD_LIMIT`, `LEVER_TRUNCATE_THRESHOLD`,
`LEVER_TRUNCATE_KEEP`, `LEVER_READ_LARGE_BYTES`, `LEVER_READ_DEFAULT_LIMIT`) — read once at
import, which in production means per hook firing, since each firing is a fresh process. The
path operands (`LEVER_STORE_DIR`, `LEVER_UPLOADS_DIR`) are read per call. Configuration moves
the operand, never the predicate shape: a truncate-keep spanning the threshold (which would make
"truncation" inflate the payload) is clamped, not honored. Dispatch overhead, measured: ~60 ms
per hook invocation (interpreter startup dominates).

`/lever` (the one slash command) relays that trace verbatim — the human's way to ask
"is the rod latched?" without trusting anyone's word for it.

## Adding a move

One composition in `lever/moves.py` (built from the π/φ/α generators at the top of the file,
carrying its `@_flows` station declaration), one row in the `MOVES` table, one red-then-green
test pair. The punchcard updates itself — cell rows are derived from the declaration — and the
universal law tests hold the new move to totality, idempotence, and monotonicity with zero new
test code. If it needs more than that — a database, a summarization step, a judgment call — it
isn't a Lever move; `LAW.md`'s five-clause test decides, not taste.

## License

Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). The explicit patent grant is
deliberate: this is infrastructure meant to be adopted, embedded, and ported.

## Sibling

[Makoto](https://github.com/Clear-Sights/Makoto) holds the agent to its word (integrity gates —
judgment-shaped checks); Lever holds the machinery to determinism (no judgment anywhere). The
two never import each other; Lever reads Makoto's chain by shape only.
