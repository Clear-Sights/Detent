"""Public smoke test — the ONE test file shipped to the public repo (the full falsifiability
suite lives in the dev repo, same split as Makoto's). Self-contained by contract: no imports
from other test files, no fixtures beyond tmp_path/monkeypatch, and it exercises the REAL wire
(subprocess stdin→stdout), not just the Python API — so public CI proves the shipped artifact
actually latches: catalog certifies, dispatch rewrites and denies on the wire, the store
round-trips, the status runtime exits clean.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("LEVER_STORE_DIR", str(tmp_path / "store"))


def _dispatch(event: dict) -> dict:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run([sys.executable, "-m", "lever.dispatch"],
                       input=json.dumps(event), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else {}


def test_punchcard_certifies():
    from lever.cells import CELLS, coverage_failures
    assert sorted(CELLS) == list(range(1, 21))
    assert coverage_failures() == []


def test_dispatch_rewrites_on_the_wire():
    out = _dispatch({"hook_event_name": "PreToolUse", "tool_name": "Grep",
                     "tool_input": {"pattern": "x", "output_mode": "content"}})
    updated = out["hookSpecificOutput"]["updatedInput"]
    assert updated["head_limit"] > 0


def test_dispatch_denies_on_the_wire(tmp_path):
    f = tmp_path / "same.txt"
    f.write_text("identical bytes")
    out = _dispatch({"hook_event_name": "PreToolUse", "tool_name": "Write",
                     "tool_input": {"file_path": str(f), "content": "identical bytes"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_dispatch_silent_on_foreign_event():
    assert _dispatch({"hook_event_name": "PreToolUse", "tool_name": "NoSuchTool",
                      "tool_input": {}}) == {}


def test_store_round_trips(tmp_path):
    from lever import store
    addr = store.put(b"artifact bytes")
    assert store.get(addr) == b"artifact bytes"
    dst = tmp_path / "out.bin"
    store.materialize(addr, str(dst))
    assert dst.read_bytes() == b"artifact bytes"


def test_status_runtime_exits_clean():
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run([sys.executable, "-m", "lever"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "coverage:" in r.stdout
