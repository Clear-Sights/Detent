"""Read-only access to a certified/observed fact, from ONE of a small named set of sources --
BY SHAPE, never by import (LAW.md's own rule 5, restated for this coupling: Detent and Makoto are
separate faculties in separate repos; Detent never `import makoto`, and never writes to Makoto's
store). See docs/CHAIN-FORMAT-v1.md -- this module is that spec's Detent-side implementation,
kept byte-consistent with makoto-dev's `ledger.py` via the golden vectors in
tests/vectors/chain_v1/, not via a shared package.

Owner's design (2026-07-07, "a simple pointer difference... whatever other sources if needed"):
a caller (a move, a test) asks for the latest fact of a `kind`; this module picks ONE source --

  - `"chain"`  -- Makoto's hash-chained `<state_dir>/chain.jsonl`, when it exists. Trust comes
    from re-walking and verifying every link (`read_verified_rows`) -- a row is never used
    unless its own chain position checks out.
  - `"transcript"` -- when no chain exists (Makoto absent, or hasn't run yet this session): the
    CURRENT session's own `transcript_path` (a documented top-level field on every Claude Code
    hook payload), read DIRECTLY for the most recent test-runner Bash tool_use/tool_result pair.
    Trust here is "the transcript is host-written ground truth" (the exact non-forgeable-turn
    contract Makoto's own `ackblock.py` relies on for the SAME reason) -- there is no hash chain
    to walk when none exists; this is the "one hour solo" value Detent has with zero install.

Auto-selected by `latest_verified_fact` (chain present -> "chain"; absent -> "transcript"); a
caller may force one explicitly via `source=`. A third source is one new reader function plus
one registry entry -- never a redesign of the callers.

This module reads ONLY -- no lock, no write path, nothing that could ever race Makoto's own
writer or the harness's own transcript writer. A partial trailing line (mid-write) reads as
absent, never corrupt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable, Optional

# ---- Source "chain": Makoto's hash-chained store, ported BY SHAPE (see module docstring) -------

def _state_dir() -> Path:
    env = os.environ.get("MAKOTO_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "makoto_state"


def _norm_sha256(content: str) -> str:
    normalized = "\n".join(line.rstrip() for line in content.splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _dumps(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _canonical(row: dict) -> str:
    return _dumps({k: v for k, v in row.items() if k != "row_hash"})


def _row_hash(prev_hash: str, row: dict) -> str:
    return _norm_sha256(prev_hash + _canonical(row))


def verify_chain(*, root: Optional[Path] = None, name: str = "chain") -> Optional[int]:
    """CHAIN-FORMAT v1's verification contract, Detent's own copy. None = fully intact
    (including vacuously-absent/empty); else the 0-based index of the first broken row. Golden
    vectors (tests/vectors/chain_v1/) pin this against Makoto's own implementation."""
    target = (root or _state_dir()) / f"{name}.jsonl"
    if not target.exists():
        return None
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    expected_prev = ""
    idx = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except ValueError:
            return idx
        if not isinstance(row, dict):
            return idx
        if row.get("prev_hash", "") != expected_prev:
            return idx
        if row.get("row_hash") != _row_hash(expected_prev, row):
            return idx
        expected_prev = row.get("row_hash", "")
        idx += 1
    return None


def read_verified_rows(*, root: Optional[Path] = None, name: str = "chain") -> list[dict]:
    """The PREFIX of `<root or default>/<name>.jsonl` whose hash-chain links are actually
    intact, oldest first -- stops at (excludes) the first row that fails to parse, isn't a
    dict, or whose prev_hash/row_hash link doesn't verify. Absent/empty file -> []. NEVER
    RAISES. This is the one function every certified-fact reader in this module goes through --
    nothing here ever trusts an unverified row, by construction."""
    target = (root or _state_dir()) / f"{name}.jsonl"
    if not target.exists():
        return []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    expected_prev = ""
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except ValueError:
            break
        if not isinstance(row, dict):
            break
        if row.get("prev_hash", "") != expected_prev:
            break
        if row.get("row_hash") != _row_hash(expected_prev, row):
            break
        out.append(row)
        expected_prev = row.get("row_hash", "")
    return out


def _chain_fact(kind: str, *, session_id: Optional[str], root: Optional[Path]) -> Optional[dict]:
    match = None
    for row in read_verified_rows(root=root):
        if row.get("kind") != kind:
            continue
        if session_id is not None and row.get("session_id") != session_id:
            continue
        match = row
    if match is None:
        return None
    return {"kind": match.get("kind"), "key": match.get("key"), "value": match.get("value"),
           "session_id": match.get("session_id"), "ts": match.get("ts"),
           "src": match.get("src", "makoto-legacy"), "provenance": "chain-verified"}


# ---- Source "transcript": the current session's own host-written record, read directly --------

_TEST_RUNNER_RX = re.compile(
    r"\b(pytest|py\.test|python[0-9.]*\s+-m\s+(?:pytest|unittest)|-m\s+unittest|"
    r"nox|tox|jest|vitest|mocha|ava|jasmine|go\s+test|cargo\s+(?:test|nextest)|"
    r"npm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"rspec|phpunit|ctest|gradlew?\s+test|mvn\s+test|make\s+test|just\s+test|rails\s+test"
    r")\b", re.IGNORECASE)
# Ported BY SHAPE from makoto's own lexicons._TEST_RUNNER_RX (copy, never import -- boundary law).


def _is_test_runner(command: str) -> bool:
    return bool(command) and bool(_TEST_RUNNER_RX.search(command))


def _transcript_fact(kind: str, *, session_id: Optional[str],
                     transcript_path: Optional[str]) -> Optional[dict]:
    """The most recent test-runner Bash tool_use/tool_result pair in the transcript at
    `transcript_path`, read directly (no chain, nothing to hash-verify -- trust is "the
    transcript is host-written," the same non-forgeable-turn contract makoto.ackblock relies
    on). Only `kind="testrun"` is derivable this way today; any other kind returns None (this
    source has no analog for judgment kinds -- it never claims one)."""
    if kind != "testrun" or not transcript_path:
        return None
    p = Path(transcript_path)
    if not p.exists():
        return None
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    pending_bash: dict[str, str] = {}   # tool_use_id -> command, for an unresolved Bash call
    match_value: Optional[str] = None
    match_ts: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except ValueError:
            continue
        if session_id is not None and entry.get("sessionId") not in (None, session_id):
            continue
        msg = entry.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        if entry.get("type") == "assistant":
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") == "Bash"):
                    cmd = (block.get("input") or {}).get("command", "") or ""
                    if _is_test_runner(cmd):
                        pending_bash[block.get("id")] = cmd
        elif entry.get("type") == "user" and "toolUseResult" in entry:
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                tool_use_id = block.get("tool_use_id")
                if tool_use_id not in pending_bash:
                    continue
                tr = entry.get("toolUseResult")
                stdout = tr.get("stdout", "") if isinstance(tr, dict) else ""
                match_value = stdout
                match_ts = entry.get("timestamp")
                del pending_bash[tool_use_id]
    if match_value is None:
        return None
    return {"kind": "testrun", "key": "bash", "value": match_value, "session_id": session_id,
           "ts": match_ts, "src": "transcript", "provenance": "unverified -- this session's own "
           "transcript, no chain/integrity system present; trusted only as host-written"}


# ---- the registry -------------------------------------------------------------------------------

_SOURCES: dict[str, Callable] = {
    "chain": lambda kind, session_id, root, transcript_path: _chain_fact(
        kind, session_id=session_id, root=root),
    "transcript": lambda kind, session_id, root, transcript_path: _transcript_fact(
        kind, session_id=session_id, transcript_path=transcript_path),
}


def latest_verified_fact(kind: str, *, session_id: Optional[str] = None,
                         root: Optional[Path] = None,
                         transcript_path: Optional[str] = None,
                         source: Optional[str] = None) -> Optional[dict]:
    """The latest fact of `kind`, from ONE source -- auto-selected (chain file present at
    `root or _state_dir()` -> "chain"; absent -> "transcript") unless `source` forces one. Never
    interprets or judges the value (LAW.md rule 2 -- the caller decides what to do with it).
    Returns None when the selected source has nothing to say."""
    chosen = source
    if chosen is None:
        chain_path = (root or _state_dir()) / "chain.jsonl"
        chosen = "chain" if chain_path.exists() else "transcript"
    reader = _SOURCES.get(chosen)
    if reader is None:
        return None
    return reader(kind, session_id, root, transcript_path)
