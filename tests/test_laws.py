"""Universal laws — parametrized over ALL moves at once, LOCKed before the algebra existed.

Every move is one composition α∘φ∘π (action ∘ guard ∘ projection). That claim is only worth
making if it buys universal, per-move-free guarantees — these three, each falsifiable:

1. GUARD TOTALITY — φ is total: any JSON-shaped event, however malformed (wrong types, absent
   fields, None where a dict should be), yields ⊥ (None) or a typed envelope. Never a raise.
2. REWRITE IDEMPOTENCE — for a rewrite move m and event e with m(e) ≠ ⊥: applying the rewrite
   and re-running gives ⊥. A bound, once injected, is not re-injected; m∘m = m.
3. STORE MONOTONICITY — capture is a monotone side-map: across any move firing, existing
   objects never change and the ledger only appends. (CALM: monotone ⇒ coordination-free —
   this is the law that makes N agents scale with zero machinery.)

Plus the reassembly contract itself:

4. DERIVED = DECLARED — every move declares its (dom π, cod α) flows on itself; the punchcard's
   detent.moves.* machinery is the IMAGE of those declarations, not a hand-kept copy.
"""
import os
from pathlib import Path

import pytest

import detent.moves as moves
from detent.contract import Block, Defer, Deny
from detent.moves import (
    BASH_TRUNCATE_THRESHOLD,
    READ_LARGE_FILE_BYTES,
    MOVES,
    grep_bound_unbounded_content,
    read_bound_unbounded_content,
    response_capture_and_bound,
)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("DETENT_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("MAKOTO_STATE_DIR", str(tmp_path / "makoto"))


# --- law 1: guard totality ------------------------------------------------------------------

# JSON-shaped garbage: every value a JSON type, every shape wrong. A hook event is external
# input; a move that raises on any of these is a move whose guard was never total.
MALFORMED_EVENTS = [
    {},
    {"tool_input": None, "tool_response": None},
    {"tool_input": {}, "tool_response": {}},
    {"tool_input": "grep foo bar", "tool_response": "a long stdout"},
    {"tool_input": [1, 2], "tool_response": True},
    {"tool_input": {"file_path": 7, "content": 5, "old_string": 3, "command": 9,
                    "pattern": 1, "output_mode": 2, "url": 0, "head_limit": "x"}},
    {"tool_input": {"file_path": ["a"], "content": {"b": 1}, "new_string": 4}},
    {"tool_response": 11},
    {"tool_response": {"stdout": 13}},
    {"tool_response": [1, 2, 3]},
    {"prompt": 17, "prompt_id": 19},
    {"last_assistant_message": 23, "stop_hook_active": 0},
    {"source": "compact", "session_id": 29, "transcript_path": 31},
    {"delta": 5, "message_id": 7, "final": "x"},
    {"error": 3, "is_interrupt": "y", "duration_ms": "z"},
    {"compact_summary": 9, "trigger": 2},
    {"agent_id": 1, "agent_type": 2, "last_assistant_message": 4},
]

_ALL_MOVES = sorted({fn.__name__ for fns in MOVES.values() for fn in fns})


@pytest.mark.parametrize("battery_index", range(len(MALFORMED_EVENTS)))
@pytest.mark.parametrize("move_name", _ALL_MOVES)
def test_guard_totality_never_raises(move_name, battery_index):
    fn = getattr(moves, move_name)
    result = fn(dict(MALFORMED_EVENTS[battery_index]))
    assert result is None or isinstance(result, (dict, str, Defer, Deny, Block))


# --- law 2: rewrite idempotence -------------------------------------------------------------

def _apply_pre(event, updated):
    return {**event, "tool_input": updated}


def _apply_post(event, updated):
    return {**event, "tool_response": updated}


def _rewrite_move_names() -> list[str]:
    """The rewrite-α moves, DERIVED from the moves' own return annotations — a new rewrite
    move enters this law automatically; forgetting its fixture is a red test, not a silence."""
    import inspect
    return sorted(fn.__name__ for fns in MOVES.values() for fn in fns
                  if "dict" in str(inspect.signature(fn).return_annotation))


def _rewrite_cases(tmp_path):
    long_s = "y" * (BASH_TRUNCATE_THRESHOLD + 1)
    from detent.moves import context_to_workspace, into_context
    from detent.store import put as _law_put
    addr = _law_put(b"materialized body\n")
    return {
        into_context.__name__: (
            into_context,
            {"hook_event_name": "PreToolUse", "tool_name": "Grep",
             "tool_input": {"pattern": "x", "output_mode": "content"}}, _apply_pre),
        context_to_workspace.__name__: (
            context_to_workspace,
            {"hook_event_name": "PreToolUse", "tool_name": "Write",
             "tool_input": {"file_path": str(tmp_path / "new-out.txt"),
                            "content": f"detent://{addr}"}}, _apply_pre),
    }


@pytest.mark.parametrize("move_name", _rewrite_move_names())
def test_rewrite_idempotence(move_name, tmp_path, monkeypatch):
    import detent.moves as m
    monkeypatch.setattr(m, "BOUNDS_MODE", "inject")   # the law governs the rewrite alpha
    cases = _rewrite_cases(tmp_path)
    assert move_name in cases, f"{move_name}: rewrite move with no idempotence fixture"
    fn, event, apply_rewrite = cases[move_name]
    first = fn(dict(event))
    assert isinstance(first, dict), f"{move_name}: fixture must trigger the rewrite"
    assert fn(apply_rewrite(event, first)) is None, f"{move_name}: m∘m must be ⊥"


def test_deny_default_reaches_its_own_fixpoint():
    # The deny tier's idempotence analog, live-verified 2026-07-12: the deny names the exact
    # bounded call; an event carrying that named input is the fixpoint (⊥, no opinion).
    from detent.contract import Deny
    from detent.moves import into_context
    event = {"hook_event_name": "PreToolUse", "tool_name": "Grep",
             "tool_input": {"pattern": "x", "output_mode": "content"}}
    first = into_context(dict(event))
    assert isinstance(first, Deny)
    import ast
    named = ast.literal_eval(first.reason.split("bounded with the default: ", 1)[1])
    assert into_context({**event, "tool_input": named}) is None


def test_rewrite_fixtures_name_only_real_rewrite_moves(tmp_path):
    assert set(_rewrite_cases(tmp_path)) == set(_rewrite_move_names())


# --- law 3: store monotonicity --------------------------------------------------------------

def _store_state():
    root = Path(os.environ["DETENT_STORE_DIR"])
    objects = {}
    obj_dir = root / "objects"
    if obj_dir.is_dir():
        objects = {p.name: p.read_bytes() for p in obj_dir.iterdir() if p.is_file()}
    ledger = root / "firings.jsonl"
    lines = ledger.read_text().splitlines() if ledger.is_file() else []
    return objects, lines


def test_store_monotonicity_across_every_move(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("hello")
    long_s = "y" * (BASH_TRUNCATE_THRESHOLD + 1)
    wellformed = [
        {"tool_input": {"pattern": "x", "output_mode": "content"}},
        {"tool_input": {"file_path": str(f)}},
        {"tool_input": {"command": "grep foo bar.txt"}},
        {"tool_input": {"file_path": str(f), "old_string": "hello"}},
        {"tool_input": {"file_path": str(f), "content": "hello"}},
        {"tool_input": {"file_path": str(f), "new_string": "hi"}},
        {"tool_input": {"url": "https://x"}, "tool_response": {"result": long_s}},
        {"tool_response": {"stdout": long_s}},
        {"prompt": "same prompt", "prompt_id": "p1"},
        {"prompt": "same prompt", "prompt_id": "p2"},
        {"last_assistant_message": "done.", "prompt_id": "p1"},
        {"source": "compact", "session_id": "s", "transcript_path": str(tmp_path / "no.jsonl")},
    ]
    for fn in {f for fns in MOVES.values() for f in fns}:
        for event in wellformed:
            before_objects, before_lines = _store_state()
            fn(dict(event))
            after_objects, after_lines = _store_state()
            for name, data in before_objects.items():
                assert after_objects.get(name) == data, (
                    f"{fn.__name__}: object {name} mutated or vanished")
            assert after_lines[:len(before_lines)] == before_lines, (
                f"{fn.__name__}: ledger rewrote history instead of appending")


# --- law 4: the punchcard is an image of the algebra ----------------------------------------

# The human-pinned WHERE record: the independent half of "derived == declared". @_flows lives
# in model-written code and cells.py is derived FROM it, so comparing those two alone is
# tautological — a mistagged move between two populated cells passes everything (confirmed by
# a plant during review). THIS literal is the hand-owned side; retagging any move fails here.
PINNED_FLOWS = {
    "into_context": ("WORLD→CONTEXT", "WORKSPACE→CONTEXT"),
    "into_store": ("USER→STORE", "WORLD→STORE", "WORKSPACE→STORE", "CONTEXT→STORE"),
    "context_to_workspace": ("CONTEXT→WORKSPACE", "STORE→WORKSPACE"),
    "context_to_world": ("CONTEXT→WORLD", "STORE→WORLD"),
    "context_to_user": ("CONTEXT→USER",),
    "user_to_context": ("USER→CONTEXT",),
    "store_to_context": ("STORE→CONTEXT",),
    "store_to_user": ("STORE→USER",),
}


def test_flows_match_the_human_pinned_record():
    assert {fn.__name__: tuple(fn.flows)
            for fns in MOVES.values() for fn in fns} == PINNED_FLOWS


def test_every_move_declares_its_flows():
    from detent.cells import CELLS
    legal_flows = {cell["flow"] for cell in CELLS.values()}
    for fns in MOVES.values():
      for fn in fns:
        flows = getattr(fn, "flows", None)
        assert flows, f"{fn.__name__}: no declared (dom π, cod α) flows"
        for flow in flows:
            assert flow in legal_flows, f"{fn.__name__}: {flow} is not a BEDROCK flow"


@pytest.mark.parametrize("threshold, keep", [
    ("1000", "2000"),   # keep spans threshold
    ("1000", "-5"),     # negative keep: omitted-count would exceed the input's own length
    ("40", "10"),       # threshold below the marker itself: any "truncation" inflates
])
def test_truncate_config_can_never_invert_the_verb(monkeypatch, threshold, keep):
    # DETENT_* ints are read at import (each hook firing is a fresh process, so per-invocation
    # in production); for ANY config, truncation output must be shorter than its input.
    import importlib
    monkeypatch.setenv("DETENT_TRUNCATE_THRESHOLD", threshold)
    monkeypatch.setenv("DETENT_TRUNCATE_KEEP", keep)
    try:
        reloaded = importlib.reload(moves)
        assert 0 <= 2 * reloaded.BASH_TRUNCATE_KEEP <= reloaded.BASH_TRUNCATE_THRESHOLD - 320
        value = "z" * (reloaded.BASH_TRUNCATE_THRESHOLD + 1)
        out = reloaded.response_capture_and_bound(
            {"tool_response": {"stdout": value}})
        assert out is not None and len(out["stdout"]) < len(value)
    finally:
        monkeypatch.undo()
        importlib.reload(moves)


def test_cells_move_machinery_is_derived_not_hand_copied():
    from detent.cells import CELLS, derived_move_machinery
    derived = derived_move_machinery()
    declared = {}
    for cell in CELLS.values():
        entries = {m for m in cell.get("machinery", ()) if m.startswith("detent.moves.")}
        if entries:
            declared[cell["flow"]] = entries
    assert declared == {f: set(v) for f, v in derived.items() if v}
