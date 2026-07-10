"""Moves — the arms. Every move is ONE composition: m = α ∘ φ ∘ π.

π (projection) reads one typed slice of the event or workspace; φ (guard) is an exact, total
predicate over it; α (action) is an envelope type — rewrite dict, Deny, Block, advisory str —
or ⊥ (None: no opinion, the resting state per LAW.md). Capture is the one permitted side-map:
monotone writes into the store and nowhere else (LAW two-tier). No model, no network, no other
writes, ever. WHEN is not an axis — it is which substrate π reads (event / workspace / ledger).
WHERE is not hand-declared — each move carries its (dom π, cod α) station pairs via @_flows
and detent/cells.py derives the punchcard's move rows from them. One named π asymmetry:
`_testrun_fact` reads via detent/facts.py (Makoto's chain BY SHAPE — never `import makoto` — or
the session transcript): deterministic and zero-cost, but not a pure function of the event.

tests/test_laws.py holds every move to three universal laws at once: guard totality (malformed
events yield ⊥, never a raise), rewrite idempotence (m∘m = ⊥), store monotonicity (objects
immutable, ledger append-only — CALM: monotone ⇒ coordination-free, why N agents need zero
coordination machinery). Each move corrects only silent omission, never explicit caller
intent — see each docstring's "does not touch" clause.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

from detent.contract import Block, Deny
from detent.facts import latest_verified_fact
from detent.store import firings as store_firings
from detent.store import get as store_get
from detent.store import has as store_has
from detent.store import put as store_put
from detent.store import put_file as store_put_file
from detent.store import record as store_record

# ── generators ─────────────────────────────────────────────────────────────────────────────
# Every π is TOTAL: a wrong type or unreadable substrate is ⊥ (None / empty), never a raise —
# so every guard composed on top is total by construction (law 1). Every threshold constant is
# env-overridable (DETENT_*, read once at import): configuration, not judgment — the predicate
# stays exact either way, only the operand moves.


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


GREP_DEFAULT_HEAD_LIMIT = _env_int("DETENT_GREP_HEAD_LIMIT", 200)
# The harness's own Bash cap: stdout longer than this reaches hooks ALREADY truncated (verified
# live 2026-07-10: 44.8k arrived as exactly 30000 chars) while the harness persists the true
# full bytes itself. Prefer-native: a capture at exactly this length must not claim "full".
_BASH_NATIVE_CAP = _env_int("BASH_MAX_OUTPUT_LENGTH", 30_000)
# Truncation must never invert its verb: for any config, output < input. The floor keeps the
# threshold above the marker's worst case (~320 chars: two 20-digit counts, a line count, and
# an address-bearing note citing a 64-hex artifact twice); the keep must be non-negative and
# leave marker room, else it clamps to threshold//4 (floor 700 keeps that clamp consistent:
# 2*(700//4) <= 700-320).
BASH_TRUNCATE_THRESHOLD = max(_env_int("DETENT_TRUNCATE_THRESHOLD", 8_000), 700)
BASH_TRUNCATE_KEEP = _env_int("DETENT_TRUNCATE_KEEP", 2_000)
if not 0 <= 2 * BASH_TRUNCATE_KEEP <= BASH_TRUNCATE_THRESHOLD - 320:
    BASH_TRUNCATE_KEEP = BASH_TRUNCATE_THRESHOLD // 4
READ_LARGE_FILE_BYTES = _env_int("DETENT_READ_LARGE_BYTES", 100_000)
READ_DEFAULT_LIMIT = _env_int("DETENT_READ_DEFAULT_LIMIT", 2_000)


def _input(event: dict[str, Any]) -> dict[str, Any]:
    """π: the tool_input slice; {} unless actually a dict."""
    value = event.get("tool_input")
    return value if isinstance(value, dict) else {}


def _str_of(mapping: dict[str, Any], key: str) -> str | None:
    """π: a string field; ⊥ on absence OR wrong type — law 1 owes totality to every caller."""
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _file_bytes(path: str) -> bytes | None:
    """π: workspace substrate; ⊥ on any unreadable/missing target (fail open)."""
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def _head_tail(value: str, note: str) -> str:
    """α-payload: same bytes, fewer of them — head + tail + exact count of the cut. Never a
    summary, never a paraphrase."""
    omitted = len(value) - 2 * BASH_TRUNCATE_KEEP
    return (value[:BASH_TRUNCATE_KEEP]
            + f"\n... [{omitted} chars omitted — {len(value)} total; {note}] ...\n"
            + value[-BASH_TRUNCATE_KEEP:])


def _capture(thunk) -> None:
    """Capture side-map: store writes are monotone and fail OPEN — an observation that could
    not be recorded never becomes an action that blocks."""
    try:
        thunk()
    except (OSError, ValueError, TypeError):
        pass


def _testrun_fact(event: dict[str, Any], template: str) -> str | None:
    """π over the ledger substrate: the latest recorded test-run fact, provenance always named
    (CHAIN-FORMAT v1), formatted into `template`; ⊥ when nothing is recorded."""
    fact = latest_verified_fact(
        "testrun",
        session_id=_str_of(event, "session_id"),
        transcript_path=_str_of(event, "transcript_path"))
    if fact is None or not fact.get("value"):
        return None
    return template.format(provenance=fact["provenance"], value=fact["value"])


def _flows(*flows: str):
    """Bind a move's (dom π, cod α) station pairs onto it — cells.py derives WHERE from these."""
    def bind(fn):
        fn.flows = flows
        return fn
    return bind


# bash_deny_raw_grep_search's grammar atoms. Any shell metacharacter (pipe/sequencing/
# redirection/backgrounding/backtick/`$(`) means "not a single simple command" -- bail before
# tokenizing.
_SHELL_METACHARACTERS = re.compile(r'[|;&`<>]|\$\(')
# grep and rg DIVERGE on -E/-r/-R -- confirmed live against both binaries, 2026-07-09, after an
# adversarial review caught a shared-flag-set draft mistranslating `rg -r X pattern`:
#   grep -i/-n and rg -i/-n: 1:1 to the Grep tool's own -i/-n.
#   grep -r/-R: real boolean recursion -- safe no-op (the Grep tool already recurses into a
#     directory path unconditionally).
#   grep -E: real boolean extended-regex toggle -- widens which patterns are safe (see below).
#   rg -r: `--replace` (MANDATORY arg, search-and-replace, NOT recursion); rg -R: not a real
#     flag ("rg: unrecognized flag", exit 2); rg -E: `--encoding` (MANDATORY arg). None of the
#     three is a safe boolean for rg -- each must fall through untouched.
# "-w" is in NEITHER set: the Grep tool has no word-boundary parameter, so dropping it would
# produce a confidently wrong (non-word-bounded) substitute -- fall through untouched.
_GREP_BOOLEAN_FLAGS = {"-i", "-n", "-r", "-R", "-E"}
_RG_BOOLEAN_FLAGS = {"-i", "-n"}
# Characters whose meaning differs between plain grep's BRE and the Grep tool's engine (a bare
# "+" is literal in BRE, a quantifier in the tool). Without "-E" a pattern containing any of
# these can't be proven equivalent -- rejected rather than risked. grep ONLY: rg's syntax is
# already the tool's own ripgrep-family engine, no BRE ambiguity to have.
_BRE_AMBIGUOUS_RX = re.compile(r'[+?|(){}]')
# Glob characters shlex.split does NOT expand -- "*.py" reaching here is the literal unexpanded
# string, not what Bash itself would have run. Same for a leading "~".
_UNEXPANDED_PATH_RX = re.compile(r'[*?\[]')
# Flags taking exactly one numeric argument, mapped straight to Grep's own params.
_GREP_CONTEXT_FLAGS = {"-A", "-B", "-C"}


@_flows("WORKSPACE→CONTEXT")
def grep_bound_unbounded_content(event: dict[str, Any]) -> dict[str, Any] | None:
    """PreToolUse / Grep: inject a default head_limit when the caller omitted it entirely on
    the expensive output_mode ("content") — Grep's own documented default is unlimited, and an
    unbounded content-mode search is a real, common, silent token cost with no upside.

    Does NOT touch: other output modes (bounded by nature), or a head_limit the caller set
    explicitly — including an explicit 0, respected as "I mean it, truly unlimited." Only an
    *absent* key is corrected."""
    tool_input = _input(event)
    if tool_input.get("output_mode", "files_with_matches") != "content":
        return None
    if "head_limit" in tool_input:
        return None
    return {**tool_input, "head_limit": GREP_DEFAULT_HEAD_LIMIT}


@_flows("WORKSPACE→CONTEXT")
def read_bound_unbounded_content(event: dict[str, Any]) -> dict[str, Any] | None:
    """PreToolUse / Read: inject a default `limit` when the caller omitted it entirely on a
    file the filesystem already reports as large — the structural sibling of the Grep move.
    A byte threshold, not a line count: counting lines would mean reading the whole file,
    the exact cost this move exists to avoid.

    Does NOT touch: a `limit` or `offset` the caller set explicitly — only an *absent* key is
    corrected. A missing/unreadable/unstat-able path is silently untouched (fail open) — this
    move only ever adds a bound, never blocks or errors the call."""
    tool_input = _input(event)
    if "limit" in tool_input or "offset" in tool_input:
        return None
    file_path = _str_of(tool_input, "file_path")
    if not file_path:
        return None
    try:
        size = os.stat(file_path).st_size
    except OSError:
        return None
    if size <= READ_LARGE_FILE_BYTES:
        return None
    return {**tool_input, "limit": READ_DEFAULT_LIMIT}


def _captured_note(value: str, label: str, fallback: str) -> str:
    """Capture `value` into the store FIRST, then return the receipt note citing the artifact
    and the exact slice command — first-contact determinism: the cut middle is never lost, it
    is one deterministic command away. Falls back to `fallback` (no address, never a lie) if
    the store is unwritable."""
    try:
        addr = store_put(value.encode())
    except (OSError, ValueError):
        return fallback
    return (f"{value.count(chr(10)) + 1} lines; {label}: detent://{addr} — "
            f"python3 -m detent.store slice {addr} <start> <end>")


@_flows("WORKSPACE→CONTEXT")
def bash_deny_raw_grep_search(event: dict[str, Any]) -> Deny | None:
    """PreToolUse / Bash: deny a raw `grep`/`rg` invocation when it sits in an exact,
    losslessly-translatable grammar, naming the equivalent Grep-tool call in the reason. A type
    check, not a quality judgment: within the grammar the two calls are provably the same
    search — no reading of intent, no "which tool is better" ranking.

    Grammar (anything outside this exact shape is untouched — fails open, never guesses): a
    single simple command (no shell metacharacters); argv[0] exactly "grep" or "rg" (not
    path-prefixed or look-alike); flags only from the per-binary whitelist above (-A/-B/-C
    each requiring one numeric argument immediately after); exactly one pattern, not starting
    with "-" and containing none of `+?|(){}` unless "-E" was given (BRE vs the tool's engine
    — see _BRE_AMBIGUOUS_RX); at most one path, with no glob character or leading `~` (shlex
    expands neither, so the literal token is NOT what Bash's own expansion would have used).

    Does NOT touch: shell metacharacters, unparseable commands (shlex raises on unbalanced
    quotes), any flag outside the whitelist (including "-w" — see the atoms above), a context
    flag missing its numeric argument, more than one pattern/path, or anything outside the
    character constraints — none have a provable 1:1 translation, and a wrong substitution is
    worse than none. find/cat/head/tail/sed/awk are parked (the dev repo's docs/archive/EVENT-COVERAGE.md): sed/awk
    have no lossless translation at all; the rest need their own grammar, not a reuse of
    grep's."""
    command = _str_of(_input(event), "command")
    if not command:
        return None
    if _SHELL_METACHARACTERS.search(command):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0] not in ("grep", "rg"):
        return None
    binary = tokens[0]
    boolean_flags = _GREP_BOOLEAN_FLAGS if binary == "grep" else _RG_BOOLEAN_FLAGS

    flags: dict[str, Any] = {}
    positional: list[str] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in _GREP_CONTEXT_FLAGS:
            if i + 1 >= len(tokens) or not tokens[i + 1].isdigit():
                return None  # missing/non-numeric argument -- ambiguous, bail
            flags[token] = int(tokens[i + 1])
            i += 2
            continue
        if token in boolean_flags:
            flags[token] = True
            i += 1
            continue
        if token.startswith("-"):
            return None  # a flag outside this binary's whitelist -- outside the safe grammar
        positional.append(token)
        i += 1

    if not positional or len(positional) > 2:
        return None  # need exactly a pattern, optionally one path
    pattern = positional[0]
    if binary == "grep" and "-E" not in flags and _BRE_AMBIGUOUS_RX.search(pattern):
        return None  # BRE vs the Grep tool's regex engine disagree on these characters
    if len(positional) == 2 and (_UNEXPANDED_PATH_RX.search(positional[1])
                                 or positional[1].startswith("~")):
        return None  # a glob/~ shlex never expanded -- not the path Bash itself would have used

    grep_call: dict[str, Any] = {"pattern": pattern, "output_mode": "content"}
    if len(positional) == 2:
        grep_call["path"] = positional[1]
    for flag in ("-i", "-n", "-A", "-B", "-C"):
        if flag in flags:
            grep_call[flag] = flags[flag]

    return Deny(
        f"Denied: raw Bash '{tokens[0]}' is an exact-translatable search. Use the Grep tool "
        f"instead, with these exact parameters -- it answers the same query for free: {grep_call!r}")


@_flows("STORE→CONTEXT")
def subagent_warm_start(event: dict[str, Any]) -> str | None:
    """SubagentStart: inject the latest recorded test-run fact into the new subagent's opening
    context, so it starts already knowing the current test state instead of re-deriving it.
    ADVISORY tier — SubagentStart is documented as strictly informational (no rewrite envelope
    exists for this event), so this is LAW.md's fallback tier by necessity, not choice.
    Provenance is always named in the injected text, never laundered (CHAIN-FORMAT v1).

    Does NOT touch: a spawn when there is nothing recorded yet (silence, the resting state)."""
    return _testrun_fact(
        event, "[detent: the most recently recorded test-runner output this session "
               "({provenance}) was:\n{value}]")


@_flows("STORE→CONTEXT")
def post_compact_re_inject(event: dict[str, Any]) -> str | None:
    """SessionStart, source=="compact" only: re-inject the same fact subagent_warm_start
    reads, so a post-compaction continuation starts already knowing the current test state.
    One lookup, gated on the ONE `source` value that means "follows a compaction" — the whole
    design; the checkpoint-file draft it replaced was disqualified in the dev repo's docs/archive/D3-D4-SPEC.md.

    Does NOT touch: `source` values other than "compact" ("startup"/"resume"/"clear" have no
    compaction to recover from — SubagentStart/session boot has its own move)."""
    if event.get("source") != "compact":
        return None
    return _testrun_fact(
        event, "[detent: post-compaction re-inject -- the most recently recorded test-runner "
               "output this session ({provenance}) was:\n{value}]")


@_flows("CONTEXT→WORKSPACE")
def edit_deny_ambiguous_anchor(event: dict[str, Any]) -> Deny | None:
    """PreToolUse / Edit (enforcement): deny an Edit whose anchor violates its own cardinality
    contract BEFORE the call burns a round trip — LAW.md's declared-contract-or-hard-error
    clause at the only moment it's cheap. Exactly one occurrence (or declared replace_all)
    proceeds; zero or several is denied with the exact count.

    Does NOT touch: replace_all edits, a missing/unreadable file, absent params (fail open)."""
    tool_input = _input(event)
    file_path, old = _str_of(tool_input, "file_path"), _str_of(tool_input, "old_string")
    if not file_path or not old or tool_input.get("replace_all"):
        return None
    data = _file_bytes(file_path)
    if data is None:
        return None
    count = data.count(old.encode())
    if count == 1:
        return None
    return Deny(f"Denied: old_string occurs {count} times in {file_path} (contract requires "
                f"exactly 1, or declare replace_all). Disambiguate the anchor and retry.")


@_flows("CONTEXT→WORKSPACE")
def write_deny_reemission(event: dict[str, Any]) -> Deny | None:
    """PreToolUse / Write (enforcement): deny re-emitting bytes already on disk — EXACT
    identity only. proposed == current is a no-op write: pure equality, the one predicate
    shape this system allows. (A similarity-threshold variant was built, then struck: a fuzzy
    ratio is judgment wearing a threshold's clothes — its own probe scored 49/50 identical
    lines at 0.78 — and near-match is banned by the same law that bans it in MEMOIZE.)

    Does NOT touch: content differing from disk by even one byte, new files, unreadable
    targets (fail open)."""
    tool_input = _input(event)
    file_path, content = _str_of(tool_input, "file_path"), _str_of(tool_input, "content")
    if not file_path or content is None:
        return None
    current = _file_bytes(file_path)
    if current is None or content.encode() != current:
        return None
    return Deny(f"Denied: proposed Write to {file_path} is byte-identical to what is on "
                f"disk — a no-op re-emission. Skip the write.")


# Reference grammars the model may emit in place of bytes it did not originate. Measured
# before building (2026-07-10): 70,663 chars of old_string — 11.5% of ALL model output that
# session — was anchor transport, bytes already on disk re-emitted solely to point at them.
# The model types a ~20-char pointer; the hook does the copy/paste.
_LINE_REF_RX = re.compile(r"detent://L(\d+)(?:-(\d+))?\Z")
_ADDR_REF_RX = re.compile(r"detent://([0-9a-f]{64})(?::L(\d+)-(\d+))?\Z")


def _resolve_addr_ref(value: str) -> str | None:
    """π: store bytes named by detent://<addr>, or the exact lines a..b of them when the
    reference carries :L<a>-<b> — a FRAGMENT paste by pointer. ⊥ on no-match, unresolvable
    address, or a range past EOF (a hard miss falls through untouched, never guessed)."""
    m = _ADDR_REF_RX.fullmatch(value)
    if not m:
        return None
    try:
        body = store_get(m.group(1)).decode("utf-8", "replace")
    except (KeyError, OSError, ValueError):
        return None
    if not m.group(2):
        return body
    a, b = int(m.group(2)), int(m.group(3))
    lines = body.splitlines(keepends=True)
    if a < 1 or b < a or b > len(lines):
        return None
    return "".join(lines[a - 1:b])


def _expand_line_ref(path: str, ref: str) -> str | None:
    """π: the exact bytes of whole lines a..b (1-indexed, inclusive, newlines included) of the
    target file, named by a detent://L<a>-<b> reference; ⊥ if the reference doesn't parse, the
    file is unreadable, or the range runs past EOF (a hard miss must fall through untouched,
    never guess)."""
    m = _LINE_REF_RX.match(ref)
    if not m:
        return None
    data = _file_bytes(path)
    if data is None:
        return None
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    lines = data.decode("utf-8", "replace").splitlines(keepends=True)
    if a < 1 or b < a or b > len(lines):
        return None
    return "".join(lines[a - 1:b])


@_flows("CONTEXT→WORKSPACE", "STORE→WORKSPACE")
def edit_by_reference(event: dict[str, Any]) -> dict[str, Any] | Deny | None:
    """PreToolUse / Edit: pointers instead of transport, then the cardinality gate. An
    old_string of exactly detent://L<a>-<b> expands to those whole lines of the target file;
    an old_string or new_string of exactly detent://<64hex> expands to those store bytes —
    the model emits a reference, machinery moves the bytes. The expanded anchor is then held
    to the SAME cardinality contract as a hand-typed one (a line-derived block that repeats
    elsewhere in the file is ambiguous and denied, never guessed), and a non-reference Edit
    passes straight through to edit_deny_ambiguous_anchor unchanged.

    Does NOT touch: strings that are not exactly a reference (no scanning inside content),
    unreadable files, out-of-range line references (fall through untouched — the ordinary
    anchor match will fail loudly at the tool instead).

    Live ceiling, pinned 2026-07-10: this client version validates Edit.old_string against
    the file BEFORE PreToolUse rewrites apply, so the pointer form currently errors cleanly
    at the tool (nothing corrupted — fail closed) while write_by_address applies live. The
    hook side is correct per the documented protocol and verified on the wire; the gate
    opens the moment the harness orders validation after rewrites."""
    tool_input = _input(event)
    file_path = _str_of(tool_input, "file_path")
    old = _str_of(tool_input, "old_string")
    new = _str_of(tool_input, "new_string")
    expanded = dict(tool_input)
    changed = False
    if file_path and old:
        for value, key in ((old, "old_string"), (new, "new_string")):
            if value is None:
                continue
            body = _resolve_addr_ref(value)
            if body is not None:
                expanded[key] = body
                changed = True
            elif key == "old_string":
                lines = _expand_line_ref(file_path, value)
                if lines is not None:
                    expanded[key] = lines
                    changed = True
    if not changed:
        return edit_deny_ambiguous_anchor(event)
    gate = edit_deny_ambiguous_anchor({**event, "tool_input": expanded})
    if isinstance(gate, Deny):
        return Deny(f"{gate.reason} (anchor was expanded from a detent:// reference — widen "
                    f"the line range until the block is unique)")
    return expanded


@_flows("CONTEXT→WORKSPACE", "STORE→WORKSPACE")
def write_by_address(event: dict[str, Any]) -> dict[str, Any] | Deny | None:
    """PreToolUse / Write: write-by-address. A content of exactly detent://<64hex>
    materializes those store bytes into the write — ~70 output characters instead of the
    whole payload; generation is stochastic once and every later use is a deterministic copy,
    now enforced on the EMISSION side too. The expanded content is then held to the same
    re-emission gate as a hand-typed one (materializing bytes identical to what is already
    on disk is still a no-op and still denied), and a non-reference Write passes straight
    through to write_deny_reemission unchanged.

    Does NOT touch: content that is not exactly one reference, addresses that don't resolve
    (fall through untouched — the model wrote a pointer to nothing, and the ordinary write
    of that literal string is at least visible)."""
    tool_input = _input(event)
    content = _str_of(tool_input, "content")
    if not content or not _ADDR_REF_RX.fullmatch(content):
        return write_deny_reemission(event)
    body = _resolve_addr_ref(content)
    if body is None:
        return None
    expanded = {**tool_input, "content": body}
    gate = write_deny_reemission({**event, "tool_input": expanded})
    if isinstance(gate, Deny):
        return gate
    return expanded


@_flows("CONTEXT→STORE", "WORKSPACE→STORE")
def edit_write_capture(event: dict[str, Any]) -> None:
    """PostToolUse / Edit+Write (capture): record the emission (new_string/content) and the
    resulting file state into the store — generation is stochastic once, addressable forever.
    Always returns None; never alters the call or its result. Fails open on storage errors."""
    tool_input = _input(event)
    emitted = _str_of(tool_input, "content") or _str_of(tool_input, "new_string")
    file_path = _str_of(tool_input, "file_path")
    if emitted:
        _capture(lambda: store_put(emitted.encode()))
    if file_path:
        _capture(lambda: Path(file_path).is_file() and store_put_file(file_path))
    return None


@_flows("USER→STORE")
def upload_capture_on_read(event: dict[str, Any]) -> None:
    """PostToolUse / Read (capture): a user upload becomes an addressable artifact the first
    time it is read — the harness fires no upload event, so first-read is the earliest
    deterministic capture point. Exact path-component containment (the uploads directory,
    env-overridable via DETENT_UPLOADS_DIR), no guessing.

    Does NOT touch: any non-upload path; fails open on storage errors."""
    file_path = _str_of(_input(event), "file_path")
    if not file_path:
        return None
    uploads_root = Path(os.environ.get("DETENT_UPLOADS_DIR")
                        or Path.home() / ".claude" / "uploads")
    try:
        if not Path(file_path).resolve().is_relative_to(uploads_root.resolve()):
            return None  # path-component containment, not string prefix: uploads-evil/ is out
    except OSError:
        return None
    _capture(lambda: Path(file_path).is_file() and store_put_file(file_path))
    return None


@_flows("WORKSPACE→CONTEXT", "WORLD→CONTEXT", "WORKSPACE→STORE", "WORLD→STORE")
def response_capture_and_bound(event: dict[str, Any]) -> dict[str, Any] | None:
    """PostToolUse / * (the wildcard row — totality by construction): for EVERY tool the
    harness has or will ever grow, capture the full response into the store (the retrieval
    existed once, it is addressable forever — transport lands LOCAL first), then bound what
    enters CONTEXT: every top-level string field over the threshold gets head+tail plus an
    exact count and the field's OWN artifact address, so the cut middle is one slice command
    away. No tool enumeration, no field selection, no judgment — any tool, every oversized
    string, always. This one composition is what an enumerated {Bash, WebFetch, ...} list can
    never be: provably total over an open tool set. Spans WORKSPACE→ and WORLD→ because the
    wildcard cannot know a tool's provenance; both flows are served by the same predicate.

    Does NOT touch: responses with no oversized string field (captured, passed through),
    non-dict responses (captured only — no rewrite shape to preserve), and tools with their
    own exact row (Edit/Write/Read keep their specialist capture; Read is bounded on the PRE
    side by read_bound_unbounded_content, where the cost is avoided rather than trimmed)."""
    response = event.get("tool_response")
    if response is None:
        return None
    _capture(lambda: (
        store_put(json.dumps(response, sort_keys=True, default=str).encode()),
        store_record("result", None, tool=event.get("tool_name"),
                     url=_input(event).get("url"))))
    if not isinstance(response, dict):
        return None
    out: dict[str, Any] = {}
    for key, value in response.items():
        if isinstance(value, str) and len(value) > BASH_TRUNCATE_THRESHOLD:
            label = (f"capture at the native cap — true full output persists via the "
                     f"harness's own path; addressed {key}"
                     if len(value) >= _BASH_NATIVE_CAP else f"full {key}")
            note = _captured_note(value, label,
                                  "full response captured in the detent store")
            out[key] = _head_tail(value, note)
        else:
            out[key] = value
    return out if out != response else None


@_flows("USER→CONTEXT")
def prompt_capture_and_cache(event: dict[str, Any]) -> str | None:
    """UserPromptSubmit: capture the prompt as an artifact, and on an EXACT byte-match repeat
    of a prior prompt (sha256 equality — near-match is judgment and stays out, per MEMOIZE),
    advise with the prior captured reply's address instead of silence. Advisory tier:
    UserPromptSubmit has no rewrite envelope, so this cannot force reuse — it makes reuse free.

    Does NOT touch: first-time prompts (silence), near-matches (silence, by law)."""
    prompt = _str_of(event, "prompt")
    if not prompt:
        return None
    sha = hashlib.sha256(prompt.encode()).hexdigest()
    try:
        rows = store_firings()
        prior = [r for r in rows if r.get("op") == "prompt" and r.get("sha") == sha]
        addr = store_put(prompt.encode())
        store_record("prompt", addr, sha=sha, prompt_id=event.get("prompt_id"))
    except (OSError, ValueError):
        return None
    if not prior:
        return None
    prior_id = prior[-1].get("prompt_id")
    replies = ([r for r in rows if r.get("op") == "reply" and r.get("prompt_id") == prior_id]
               if prior_id is not None else [])  # None==None must never join A's repeat to B's reply
    if replies:
        return (f"[detent: this exact prompt was submitted before; the prior reply is artifact "
                f"detent://{replies[-1]['address']} — `python3 -m detent.store get <address>` to "
                f"reuse it instead of regenerating]")
    return "[detent: this exact prompt was submitted before (no captured reply on record)]"


@_flows("CONTEXT→STORE", "CONTEXT→USER")
def stop_capture_and_cite_check(event: dict[str, Any]) -> Block | None:
    """Stop: capture the reply as an artifact (keyed to prompt_id, feeding the prompt cache),
    then hold the reply to its checkable slice: any detent:// address it cites must actually
    resolve — an unresolvable citation is a fact without a receipt, and the turn is blocked
    with the exact dangling address named. Honors stop_hook_active (the documented anti-loop
    flag).

    Does NOT touch: replies citing nothing, or citing only addresses that resolve."""
    if event.get("stop_hook_active"):
        return None
    message = _str_of(event, "last_assistant_message")
    if not message:
        return None
    try:
        reply_addr = store_put(message.encode())
        store_record("reply", reply_addr, prompt_id=event.get("prompt_id"))
    except (OSError, ValueError):
        reply_addr = None
    # Only the DECLARED citation grammar counts (_CITATION_RX): a bare sha256 in a reply
    # (docker digest, checksum, git object) is foreign data, not a store citation — treating
    # it as one was a confirmed false-positive class. Exact syntax, zero FP by construction.
    cited = {m.group(1) for m in _CITATION_RX.finditer(message)} - {reply_addr}
    missing = sorted(addr for addr in cited if not store_has(addr))
    if missing:
        return Block(f"reply cites store artifact(s) that do not resolve: "
                     f"{', '.join('detent://' + a for a in missing[:3])} — correct the citation "
                     f"or store the artifact before finishing.")
    return None


# The declared citation grammar — shared by the Stop gate (resolve-or-block) and the display
# materializer (render-on-screen). One regex, two sides of the same contract.
_CITATION_RX = re.compile(r"detent://([0-9a-f]{64})\b")


@_flows("WORKSPACE→STORE", "WORLD→STORE")
def failure_capture(event: dict[str, Any]) -> None:
    """PostToolUseFailure / * (capture, wildcard row): a tool failure is a fact worth an
    address — the error text is stored and the firing recorded with tool provenance, so
    failure history is queryable from the ledger instead of scrollback. Always returns None."""
    error = _str_of(event, "error")
    if not error:
        return None
    _capture(lambda: store_record("failure", store_put(error.encode()),
                                  tool=event.get("tool_name"),
                                  interrupt=bool(event.get("is_interrupt"))))
    return None


@_flows("CONTEXT→STORE")
def subagent_result_capture(event: dict[str, Any]) -> None:
    """SubagentStop (capture): the subagent's final reply is window→window transport — BEDROCK
    routes that through STORE, and this move is the sanctioned-path enforcement for the result
    leg: every subagent reply becomes a hash-addressed, replayable artifact at the moment it
    exists. Always returns None."""
    message = _str_of(event, "last_assistant_message")
    if not message:
        return None
    _capture(lambda: store_record("subagent_reply", store_put(message.encode()),
                                  agent_id=event.get("agent_id"),
                                  agent_type=event.get("agent_type")))
    return None


@_flows("CONTEXT→STORE")
def compact_summary_capture(event: dict[str, Any]) -> None:
    """PostCompact (capture): the compaction summary is the survivor of a lossy operation —
    the one artifact whose loss can never be re-derived (the originals are gone from context).
    Stored and recorded with its trigger. Always returns None."""
    summary = _str_of(event, "compact_summary")
    if not summary:
        return None
    _capture(lambda: store_record("compact", store_put(summary.encode()),
                                  trigger=event.get("trigger")))
    return None


@_flows("STORE→USER")
def display_materialize_citations(event: dict[str, Any]) -> str | None:
    """MessageDisplay (display tier — cell 13, STORE→USER): reply-by-address, rendered. When
    the model's streamed delta cites detent://<addr> and the artifact resolves, the DISPLAY
    shows the bytes beside the address — the model emits reasoning plus addresses; machinery
    renders content. Display-only by protocol: the transcript and what the model sees keep the
    original (the harness guarantees this), and a failed hook displays the original text, so
    this move can only ever add fidelity, never lose it.

    Does NOT touch: deltas with no citation, citations that don't resolve (the Stop gate owns
    complaining about those), citations split across delta boundaries (pass through — fail
    open, pinned v1 limitation). An oversized artifact renders bounded, same law as every
    other context/display window."""
    delta = _str_of(event, "delta")
    if not delta:
        return None

    def render(match: re.Match) -> str:
        addr = match.group(1)
        try:
            data = store_get(addr).decode("utf-8", "replace")
        except (KeyError, OSError, ValueError):
            return match.group(0)
        if len(data) > BASH_TRUNCATE_THRESHOLD:
            data = _head_tail(data, f"full artifact: detent://{addr}")
        return f"{match.group(0)} ⟦{data}⟧"

    out = _CITATION_RX.sub(render, delta)
    return out if out != delta else None


# Exact secret grammars for outbound payloads. Fixed prefixes/formats only — no entropy
# scoring, no ML, no judgment (those fail the admission test outright). The deny reason names
# the pattern KIND, never the matched text: a deny must not re-emit the secret it caught.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("GitHub personal access token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
)


def _is_world_tool(name: str) -> bool:
    """φ: the →WORLD tool class, as an exact predicate instead of an enumerated row list.
    Every mcp__* tool is WORLD by BEDROCK's own pinned convention (MCP servers are WORLD even
    if local); WebFetch/WebSearch reach the network by definition (a secret in a fetch URL is
    query-param exfiltration). Local tools (Bash, Edit, Write, Read, Grep) are excluded
    exactly — rotating a real credential inside the workspace is legitimate work, and a live
    session measured real false positives when this scope was wider."""
    return name.startswith("mcp__") or name in ("WebFetch", "WebSearch")


@_flows("CONTEXT→WORLD", "STORE→WORLD")
def outbound_deny_secret_pattern(event: dict[str, Any]) -> Deny | None:
    """PreToolUse / * (enforcement, wildcard row): deny publishing a payload matching an exact
    secret grammar through ANY →WORLD-class tool — membership decided by _is_world_tool's
    predicate, never by an enumerated row list that a new MCP server silently escapes. The
    reason names the pattern kind only — never the match.

    Does NOT touch: non-WORLD tools (exactly — see _is_world_tool), payloads matching no
    grammar (fail open — a tripwire, not a scanner with opinions)."""
    name = event.get("tool_name")
    if not isinstance(name, str) or not _is_world_tool(name):
        return None
    blob = json.dumps(_input(event))
    for kind, pattern in _SECRET_PATTERNS:
        if pattern.search(blob):
            return Deny(f"Denied: outbound payload matches the {kind} pattern. Redact the "
                        f"credential (and rotate it if real), then retry.")
    return None


# The table: (hook_event_name, tool_name) -> move. This is the whole mechanism. Adding a move
# is adding one row here plus one composition above — nothing else changes (jisei's "a
# capability is a row, never a module" discipline). SubagentStart/SessionStart have no
# tool_name (lifecycle events, not tool calls), so their key's second element is None.
# "*" rows are the totality guarantee: an exact row wins where a genuine specialist exists;
# EVERYTHING else in that event class — including tools that do not exist yet — falls through
# to the wildcard. Coverage is a quotient of the event space, never an enumeration, so a new
# tool can never be silently uncovered again.
MOVES: dict[tuple[str, str | None], Any] = {
    ("PreToolUse", "Grep"): grep_bound_unbounded_content,
    ("PreToolUse", "Read"): read_bound_unbounded_content,
    ("PreToolUse", "Bash"): bash_deny_raw_grep_search,
    ("PreToolUse", "Edit"): edit_by_reference,
    ("PreToolUse", "Write"): write_by_address,
    ("PreToolUse", "*"): outbound_deny_secret_pattern,
    ("PostToolUse", "Edit"): edit_write_capture,
    ("PostToolUse", "Write"): edit_write_capture,
    ("PostToolUse", "Read"): upload_capture_on_read,
    ("PostToolUse", "*"): response_capture_and_bound,
    ("PostToolUseFailure", "*"): failure_capture,
    ("UserPromptSubmit", None): prompt_capture_and_cache,
    ("Stop", None): stop_capture_and_cite_check,
    ("SubagentStart", None): subagent_warm_start,
    ("SubagentStop", None): subagent_result_capture,
    ("SessionStart", None): post_compact_re_inject,
    ("PostCompact", None): compact_summary_capture,
    ("MessageDisplay", None): display_materialize_citations,
}


def lookup(event_name, tool_name):
    """The total lookup: exact row, else the event's wildcard row, else None. Two tiers only —
    quotient membership beyond that lives INSIDE moves as exact predicates over tool_name
    (see _is_world_tool), keeping the table a table."""
    move = MOVES.get((event_name, tool_name))
    if move is None and tool_name is not None:
        move = MOVES.get((event_name, "*"))
    return move
