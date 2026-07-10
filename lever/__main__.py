"""`python -m lever` — the one human-facing trace: is the rod latched, is the punchcard honest.

Prints, all machine-derived (nothing paraphrased): wiring (which active configs reference
lever's dispatch), the 20-cell coverage table straight from cells.CELLS, store stats from disk,
and every coverage failure. Exit 0 only when the punchcard matches reality — a status that
cannot return FALSE is theater, so this IS the check (`/lever` relays it verbatim).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from lever.cells import CELLS, coverage_failures


def main() -> int:
    wired = []
    for p in (Path.home() / ".claude" / "settings.json",
              Path(".claude") / "settings.json",
              Path(".claude") / "settings.local.json"):
        try:
            if "lever" in p.read_text():
                wired.append(str(p))
        except OSError:
            pass
    print(f"wiring: {', '.join(wired) if wired else 'NOT WIRED (no active config references lever)'}")

    counts: dict[str, int] = {}
    for n in sorted(CELLS):
        cell = CELLS[n]
        counts[cell["status"]] = counts.get(cell["status"], 0) + 1
        detail = ", ".join(cell.get("machinery", ())) or cell.get("reason", "")
        print(f"cell {n:>2} {cell['flow']:<22} {cell['status']:<7} {detail}")
    print("coverage: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    store_root = Path(os.environ.get("LEVER_STORE_DIR", "~/.claude/lever_store")).expanduser()
    objects = store_root / "objects"
    ledger = store_root / "firings.jsonl"
    n_objects = len(list(objects.iterdir())) if objects.is_dir() else 0
    n_firings = sum(1 for line in ledger.read_text().splitlines() if line) if ledger.is_file() else 0
    print(f"store: {n_objects} objects, {n_firings} firings ({store_root})")

    failures = coverage_failures()
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
