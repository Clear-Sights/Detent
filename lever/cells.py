"""The punchcard: BEDROCK's 20-cell coverage table as data.

Each cell: flow, status (SERVED / PARTIAL / HOLE / VOID), and either the machinery serving it
or the reason it's void. The `lever.moves.*` rows are NOT hand-declared here — every move
carries its own (dom π, cod α) station pairs (moves.py's @_flows), and this module derives the
punchcard's move machinery from those declarations: WHERE is an image of the algebra, so a
move and its cell row cannot drift apart. Hand-declared entries remain only for machinery that
is not a move: store primitives (`lever.store.*`) and declared-external `harness:` / `env:`
mechanisms. Dotted `lever.` paths are import-checked by `coverage_failures()` (CONSERVE run on
Lever itself — machinery that vanished fails loudly, never silently); tests/test_cells.py
reconciles this dict against BEDROCK.md's table in both directions.
"""
from __future__ import annotations

import importlib


def derived_move_machinery() -> dict[str, tuple[str, ...]]:
    """flow -> lever.moves.* names, derived from each move's own @_flows declaration."""
    from lever.moves import MOVES
    image: dict[str, set[str]] = {}
    for fn in set(MOVES.values()):
        for flow in getattr(fn, "flows", ()):
            image.setdefault(flow, set()).add(f"lever.moves.{fn.__name__}")
    return {flow: tuple(sorted(names)) for flow, names in image.items()}


# Hand-declared base: status, reason, and non-move machinery ONLY. Adding a lever.moves.* entry
# here is a red test (test_laws: derived == declared) — move rows come from @_flows, nowhere else.
_BASE: dict[int, dict] = {
    1:  {"flow": "USER→CONTEXT",      "status": "PARTIAL", "ceiling": "protocol",
         "ceiling_reason": "UserPromptSubmit has no rewrite envelope; forcing reuse of a "
                           "cached reply would need one. Advisory is the protocol's maximum, "
                           "and it is fully used."},
    2:  {"flow": "USER→WORKSPACE",    "status": "SERVED", "machinery": ("harness:uploads",)},
    3:  {"flow": "USER→STORE",        "status": "PARTIAL", "ceiling": "protocol",
         "ceiling_reason": "the harness fires no upload event; first-read is the earliest "
                           "deterministic capture point that exists, and it is used."},
    4:  {"flow": "USER→WORLD",        "status": "VOID",
         "reason": "Lever never initiates; the owner's own outward acts are not its writ"},
    5:  {"flow": "WORLD→USER",        "status": "VOID",
         "reason": "no direct channel in this harness; routes STORE→USER"},
    6:  {"flow": "WORLD→CONTEXT",     "status": "SERVED"},
    7:  {"flow": "WORLD→WORKSPACE",   "status": "SERVED", "machinery": ("harness:download",)},
    8:  {"flow": "WORLD→STORE",       "status": "SERVED"},
    9:  {"flow": "WORKSPACE→USER",    "status": "SERVED", "machinery": ("harness:send-file",)},
    10: {"flow": "WORKSPACE→CONTEXT", "status": "SERVED"},
    11: {"flow": "WORKSPACE→STORE",   "status": "SERVED",
         "machinery": ("lever.store.put", "lever.store.put_file")},
    12: {"flow": "WORKSPACE→WORLD",   "status": "PARTIAL", "ceiling": "external",
         "ceiling_reason": "git-transport pushes bypass the hook layer by construction (the "
                           "proxy/git own that wire); the deterministic gate lives env-side "
                           "(pre-push gitleaks), named and active.",
         "machinery": ("env:pre-push-gitleaks",)},
    13: {"flow": "STORE→USER",        "status": "SERVED",
         "machinery": ("lever.store.materialize", "harness:send-file")},
    14: {"flow": "STORE→CONTEXT",     "status": "SERVED"},
    15: {"flow": "STORE→WORKSPACE",   "status": "SERVED",
         "machinery": ("lever.store.materialize",)},
    16: {"flow": "STORE→WORLD",       "status": "SERVED", "machinery": ("lever.store.get",)},
    17: {"flow": "CONTEXT→USER",      "status": "PARTIAL", "ceiling": "boundary",
         "ceiling_reason": "the checkable slice is fully enforced (replies captured, cited "
                           "addresses must resolve or the turn blocks, citations render at "
                           "the display); distinguishing transported FACTS from reasoning "
                           "inside prose is judgment — the sibling faculty's writ. The "
                           "quote-transport gate was measured (0.0% of output) and declined "
                           "by the benefit rule."},
    18: {"flow": "CONTEXT→WORLD",     "status": "PARTIAL", "ceiling": "boundary",
         "ceiling_reason": "the exact slice is total (secret grammars over the entire →WORLD "
                           "class); deciding which outbound CLAIMS need receipts is judgment "
                           "— the sibling faculty's writ."},
    19: {"flow": "CONTEXT→WORKSPACE", "status": "SERVED"},
    20: {"flow": "CONTEXT→STORE",     "status": "SERVED"},
}


def _compose() -> dict[int, dict]:
    derived = derived_move_machinery()
    cells: dict[int, dict] = {}
    for n, base in _BASE.items():
        machinery = tuple(base.get("machinery", ())) + derived.get(base["flow"], ())
        cell = {k: v for k, v in base.items() if k != "machinery"}
        if machinery:
            cell["machinery"] = machinery
        cells[n] = cell
    return cells


CELLS: dict[int, dict] = _compose()


def coverage_failures() -> list[str]:
    """Every way the punchcard disagrees with reality, as strings; empty means certified."""
    failures = []
    for n, cell in sorted(CELLS.items()):
        for entry in cell.get("machinery", ()):
            if not entry.startswith("lever."):
                continue  # declared-external (harness:/env:) — listed, not checkable from here
            module_name, attr = entry.rsplit(".", 1)
            try:
                obj = getattr(importlib.import_module(module_name), attr)
            except (ImportError, AttributeError) as e:
                failures.append(f"cell {n}: machinery {entry} does not resolve ({e})")
                continue
            if not callable(obj):
                failures.append(f"cell {n}: machinery {entry} is not callable")
    return failures
