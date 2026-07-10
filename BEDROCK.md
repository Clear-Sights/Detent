# BEDROCK — the primitive layer, settled

**Detent is one question: of everything an agent does, how much can be made reliably
deterministic?** The LLM's irreducible remainder is reasoning — deciding, and emitting specs.
Everything else — every read, write, move, transform, verification, and presentation of fact —
is machinery. Generation is stochastic exactly once: the moment output exists it is an artifact
with an address, and every later use is a deterministic copy, never a re-emission.

**Determinism invariant** (constitutional, one sentence): a bound piece of machinery's output is
a pure function of *(event, persisted state)*; state writes are atomic and replayable.

**Scale invariance** (constitutional): plain chat, one agent, and N agents are indistinguishable
to every cell, and no machinery may exist whose purpose is coordination between agents. This is
free by construction, and must stay free: dispatch is a pure function per event (stateless, one
process per hook call); STORE is content-addressed — identical bytes get identical addresses, so
concurrent writers cannot conflict, only coincide — with atomic write-then-rename and an
append-only ledger; CONTEXT means any window. A proposed piece of machinery that would need to
know how many agents exist has already failed this invariant.

## Stations — 5 vertices

| Station | What it is |
|---|---|
| `USER` | the human — Hourglass's ORACLE sink |
| `WORLD` | network, external services, live docs, remotes |
| `WORKSPACE` | the whole local machine: repo, filesystem, environment, processes, transcripts |
| `STORE` | the hash-addressed artifact store: everything that has ever existed once (uploads, fetches, tool results, model output), keyed by content hash, addressable by coordinate |
| `CONTEXT` | any model window — the main loop's and every subagent's alike; window→window transport (spawn briefs, results) routes CONTEXT→STORE→CONTEXT, so briefs are hash-addressed, replayable artifacts |

## Topology — 20 cells, complete by construction

Every ordered pair of distinct stations is a cell. No self-loops, for two stated reasons: a
same-station *flow* (file→file copy, window→window brief) routes through `STORE`, so every
transport gets hashing, verification, and memoization for free; and station-*internal*
operations (context compaction, store GC) are owned by the station itself — the harness compacts
CONTEXT, the store maintains STORE — they are not flows, and Detent mediates only flows.
Completeness is combinatorial, not curated — a script can verify every cell is **SERVED** (named
machinery), a **HOLE** (named, unbuilt), or **VOID** (declared, with reason). Silence is not a
state.

Conventions, pinned after an adversarial falsification sweep found the topology complete but
these four readings unwritten: an MCP server is `WORLD` even when it runs as a local child
process (protocol boundary, not process locality, decides); `CONTEXT` means harness-managed
windows only — an external LLM reached through arbitrary tool use is `WORLD`; cell 12 covers
content-free protocol traffic (handshakes, capability negotiation), not only content pushes;
control-plane events with no byte payload (signals, preemption) are outside this topology's
claim, which is about byte flows. One enforcement gap is on record: STORE-mediation of
window↔window transport is guaranteed only for the sanctioned spawn/result path — an ad hoc
mailbox file between peer sessions bypasses it (CONTEXT→WORKSPACE→CONTEXT), losing hashing and
memoization. Topology intact; the sanctioned path's RESULT leg is now enforced (`into_store`
at SubagentStop hashes every subagent reply); the spawn-brief leg and the ad hoc bypass remain open.

| # | Cell | Contract (essence) | Status |
|---|---|---|---|
| 1 | USER→CONTEXT | prompt enters; exact-match (or declared-normalized) hash check against STORE; hit → inject prior artifact, never regenerate | PARTIAL — `user_to_context` captures every prompt and advises with the prior reply artifact on an exact repeat; advisory tier only (no rewrite envelope exists here) |
| 2 | USER→WORKSPACE | upload lands verbatim; hashed on arrival | SERVED (harness uploads); capture into STORE is cell 3 |
| 3 | USER→STORE | uploads captured as artifacts | PARTIAL — `into_store` captures an upload the first time it is read (no upload event exists to fire earlier) |
| 4 | USER→WORLD | owner's own outward channel | VOID — Detent never initiates; owner acts are not its writ |
| 5 | WORLD→USER | external content directly to the human | VOID — no direct channel in this harness; routes STORE→USER |
| 6 | WORLD→CONTEXT | fetched content entering the window: always bounded, always sliced | SERVED: `into_context` bounds every oversized string field of EVERY tool's response, full bytes stay addressable |
| 7 | WORLD→WORKSPACE | download-to-disk; fetch lands as file first, context reads a slice after | SERVED (curl/harness); the store-side half is closed — `into_store` lands every fetch in the STORE at first contact |
| 8 | WORLD→STORE | fetches hash-cached; repeat fetch of same URL+hash is a STORE hit | SERVED: `into_store` captures every retrieval by hash — any tool, first contact |
| 9 | WORKSPACE→USER | file sent to the human directly | SERVED (harness send-file) |
| 10 | WORKSPACE→CONTEXT | bounded, addressed reads — the model never receives more than the declared slice | SERVED: `into_context` — ONE function: pre-side bounds (Grep/Read), the raw-search redirect (Bash), and the result-side bound for every tool including future ones |
| 11 | WORKSPACE→STORE | snapshot/capture: file state hashed into the store | SERVED: `store.put`/`put_file` (spec-invoked) + `into_store` (hook-fired on every Edit/Write) |
| 12 | WORKSPACE→WORLD | push / deploy / publish from disk — verify-gated, never model-gated | PARTIAL at external ceiling: git-transport pushes bypass the hook layer by construction; the deterministic gate lives env-side (pre-push gitleaks), named and active |
| 13 | STORE→USER | rendered artifact/report delivered to the human | SERVED: `store_to_user` — reply-by-address, rendered at the display boundary; plus `store.materialize` + harness send-file |
| 14 | STORE→CONTEXT | deterministic injection of cached artifacts | SERVED: `store_to_context` — the decidable slice injected automatically (latest recorded fact at spawn/post-compaction; any detent:// reference present in a prompt, materialized); CHOOSING what to inject is reasoning, the model's remainder |
| 15 | STORE→WORKSPACE | materialize artifact to file, byte-exact, hash-verified | SERVED: `store.materialize` — spec-invoked machinery is this cell's terminal form (the model emits the spec; hooks were never the right shape here) |
| 16 | STORE→WORLD | publish a stored artifact outward | SERVED: composition of `store.get` (transport) + the cell-18 gate, now total over the →WORLD class; dedicated publish machinery was DECLINED by the benefit rule — the composition already replaces the whole surface |
| 17 | CONTEXT→USER | the reply: every fact machine-included from a trace/artifact; the model contributes reasoning only — never transported facts | PARTIAL at boundary ceiling — the checkable slice is fully enforced (`context_to_user`: cited addresses resolve or the turn blocks; `store_to_user` renders them); distinguishing transported facts from reasoning inside prose is judgment — the sibling faculty's writ. Quote-transport gate measured 0.0% and declined by the benefit rule |
| 18 | CONTEXT→WORLD | outward composed acts (PR bodies, comments, API calls) — verify-gated | PARTIAL at boundary ceiling — `context_to_world` gates the ENTIRE →WORLD tool class (every `mcp__*` tool by the pinned MCP-is-WORLD convention, plus WebFetch/WebSearch) on exact secret grammars; deciding which outbound claims need receipts is judgment — the sibling faculty's writ |
| 19 | CONTEXT→WORKSPACE | Write/Edit: anchor resolved by declared cardinality (ambiguity = hard error, pre-checked before the call burns a round trip); no re-emission of bytes already on disk (small delta → Edit, not whole-file Write) | SERVED: `context_to_workspace` — pointers expand, anchors face the cardinality gate, byte-identical re-emissions are denied |
| 20 | CONTEXT→STORE | generation captured as artifact at emission; stochastic once, addressable forever | SERVED: `into_store` — every emission, result, failure, reply, subagent reply, and compaction summary |

## Graph rules (not cells)

- **MEMOIZE** — any repeat edge into CONTEXT whose inputs and world-slice hash-match a prior
  firing reroutes through STORE. Exact match only; near-match is judgment and stays out.
  Measured before building the reroute move (2026-07-10, 18-transcript build corpus, exact
  whole-result hashing): byte-identical repeat results are 0.3% of tool-result bytes — a
  timing digit breaks exact identity, and the harness already collapses the largest echo
  class itself (Edit results: 1.9M bytes internal, 18k rendered into context). The store and
  ledger substrate MEMOIZE needs is built; the reroute move waits for a corpus that justifies
  it — building it on this evidence would be machinery without a measured replacement, the
  exact thing the admission test exists to refuse.
- **ORDER** — given declared eats/emits per atom (the ledger), schedule and parallelism are a
  topological sort, never reasoned about. Ledger order IS line order: the `ts` field is
  provenance metadata only — under N writers clock reads can invert relative to append order,
  so no machinery may branch on `ts`.
- **CONSERVE** — completeness claims ("all N handled", "old and new inventories match") are
  certified only by set-diff over the ledger; a model claim of completeness is a belief.

## Algebra — every move is one equation

**m = α ∘ φ ∘ π.** A projection π reads one typed slice of the event or workspace (every π is
total: wrong type or unreadable substrate is ⊥, never a raise); a guard φ is an exact decidable
predicate over that slice; an action α is an envelope type — rewrite / deny / block / advise —
or ⊥ (silence, the resting state). Capture is the one permitted side-map: monotone writes into
the store, nowhere else. The three axes deconstruct as: **WHAT** = the accessor algebra (the π
generators at the top of `detent/moves.py`); **WHEN** is not an axis — it is which substrate π
reads (event / workspace / ledger); **WHERE** = the type image (dom π, cod α) — each move
declares its station pairs on itself (`@_flows`) and the punchcard's move rows in
`detent/cells.py` are *derived* from those declarations, so a move and its cell cannot drift
apart.

Three laws hold universally, as parametrized tests over every move at once (`tests/test_laws.py`),
each falsifiable and each seen failing before trusted: **guard totality** (any malformed event
yields ⊥ or a typed envelope — never an exception), **rewrite idempotence** (m∘m = ⊥: a bound
injected once is never re-injected), **store monotonicity** (objects immutable, ledger
append-only across any firing). Monotonicity is the load-bearing one: by CALM (Hellerstein &
Alvaro, "Keeping CALM: When Distributed Consistency Is Easy", CACM 2020), monotone programs
need no coordination — which is the formal reason one agent and N agents behave identically
here with zero coordination machinery. Thresholds are env-overridable operands (`DETENT_*`):
configuration moves the operand, never the predicate shape (an operand set that would invert a
verb — a "truncation" that inflates — is clamped, not honored).

Two deliberate deviations from full atomization, recorded rather than hidden: φ-guards stay
inline (`if`-lines inside each composition) where a named combinator (`absent(k)`, `equals`)
would add a layer without removing a judgment — replacement is the test, and there is nothing
those wrappers would replace; and the complex grammar predicates (the grep/rg parser, the
secret patterns) remain single named atoms with operands, not DSL victims. The declared WHERE
is double-entry: `@_flows` in code, and a human-pinned literal in `tests/test_laws.py` — the
derivation is checked against a record the deriving code cannot regenerate.

Three raised candidates for extending the algebra, resolved (2026-07-10):

- **"Does the grid have another dimension?"** It has exactly two, and both already exist: the
  20 flow cells (WHERE) × the move tier (enforcement | capture — α's codomain: envelope vs
  store). A third dimension must name a new *observable* in the event/workspace/ledger triple;
  none has been found, and "silence is not a state" applies to axes too — a proposed axis with
  no observable is not pinned.
- **"Would sha-normalization simplify the logic?"** The store IS the sha-normalization: every
  equality this system trusts is already address equality (MEMOIZE, the prompt cache, the
  reemission denial, N-writer coincidence). Normalizing anything further — whitespace,
  encodings, key order — manufactures near-matches, and near-match is judgment (banned by the
  same law that struck the similarity ratio).
- **"Two halves, not one — what does a move REPLACE?"** Pinned as a rule: every enforcement
  deny names its deterministic replacement in its reason (the Grep-tool call with exact
  parameters, the disambiguated anchor, the skip, the redaction). A deny that only forbids is
  half a move; all four shipped deny moves carry their second half. Cross-harness portability
  is likewise not future work but a property already held: exactly three files know the
  harness exists — see `docs/PORTING.md`.

## Enforcement rule

Where a deterministic path provably exists for a cell, the model-transport path is denied or
rewritten at the hook layer — every shipped move is an instance of this one rule. Only provably
lossless redirections fire; anything ambiguous passes untouched (fail open). The admission test
(Free, Deterministic, Determinate, Closed, Standalone — LAW.md) is the sole gate for new
machinery and enforcement alike. **Totality is by quotient, never by enumeration** (2026-07-10):
an enumerated tool list can never be proven total against an open tool set — a new tool is
silently uncovered forever, and that latency is undetectable from inside the list. Coverage is
therefore defined over event CLASSES: exact rows only for genuine specialists, a wildcard row
("*") for the whole class, and membership predicates (e.g. the →WORLD class) as exact φ-guards
over tool_name INSIDE moves. The wildcard row is the event-class LAW: `lookup` composes it
BEFORE any exact row (law first, specialist after — never instead), so no specialist row can
ever be a private route around a class gate, and a specialist rewrite can never preempt a
gate's deny. `lookup` has no uncovered case by construction, and the executable proof feeds
tools that do not exist yet through the real wire. One hazard from the harness's own docs, pinned: when two
`PreToolUse` hooks both set `updatedInput`, the last to finish wins and their order is
non-deterministic — Detent must therefore be the sole `updatedInput` writer for any tool it
rewrites, or its own purity claim breaks at the hook boundary.

## Boundary

Anything that weighs, scores, or judges belongs to Makoto or to the model's remainder — never
here. Detent holds only what a rule fully decides. (The 5-vertex/20-edge shape is cut down from
α, an older cause-registry design; its judgment-side vertices are precisely what Detent does not
absorb. Walking foreign cell inventories like α's remains a use-case quarry.)

## What "settled" means

This page is the roots; nothing above it changes without amending this page first. Build order:
the STORE and its two workhorse edges (11, 15 — capture and materialize) come first, because
cells 1, 8, 14, 20 and the MEMOIZE rule all compose from them; then cell 19's two enforcement
moves; then this table becomes a checked artifact (one row per cell, a script that fails on
drift — a SERVED cell whose machinery vanished, machinery serving no cell, a cell with no row).

**Benefit rule** (anti-facade, 2026-07-10): determinism that decorates a stochastic act instead
of replacing one is theater, and theater is complexity. Every move must name, on itself or in
its cell, one of exactly three things: what it REPLACES (tokens prevented, round trips saved,
incidents made impossible), what CONSUMES its captures (the reader that turns a record into a
benefit), or the fact that it is INVENTORY — substrate whose consumer is named future work.
Benefit claims are computed by deterministic replay (`tools/measure.py`), never asserted; a
proposed move whose replacement measures ~0 on the relevant corpus is not built, and that
decision is recorded (see MEMOIZE's reroute and the reply-quote gate: both measured ~0 on the
build corpus, both declined on the record rather than built as theater).

Declined 2026-07-10 — NotebookEdit specialists: a `("PreToolUse", "NotebookEdit")` row
(pointer expansion / identical-emission deny over `new_source`) and a notebook leg in
`edit_write_capture` measured **0 occurrences** on the full build corpus (main session +
subagents, 900+ tool calls). NotebookEdit is not uncovered — the class laws still hold it
(outbound gate at pre via the wildcard row; result capture and bound at post via the
universal route); only the workspace-write specialists are declined until a corpus shows
the tool in use.

**Prefer-native rule** (2026-07-10): where the harness already provides a deterministic path,
Detent uses it, defers to it, or must be measurably better — never a duplicate. Pinned
interplays, each verified live: Bash stdout above the harness's own cap (BASH_MAX_OUTPUT_LENGTH,
default 30k) reaches hooks pre-truncated while the harness persists the true full bytes — so
Detent serves the 8k–30k tier (where native does nothing and every byte would enter context),
labels at-cap captures honestly instead of claiming "full", and leaves the >30k tier's full
bytes to the native persisted-output path. Grep/Glob/Read/LSP are the native deterministic
lookups — Detent bounds them, never replaces them. Slash commands and skills are native
deterministic prompt-expansion — out of writ. jq/sed/python one-liners are native deterministic
computation and formatting — the model should reach for them; a hook cannot force that choice,
only the docs can teach it.

**Done-bar** (the completion criterion, falsifiable): the bedrock is complete when nothing an
agent does that can be made deterministic isn't — every act the model still performs is
reasoning or a first emission — and when going from one thread to any number requires no
machinery beyond what determinism already provides. A HOLE is open work, never an acceptable
resting state at completion; each file stays as minimal as its contract allows.
