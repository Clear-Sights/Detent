"""STORE — the hash-addressed artifact substrate every same-station flow routes through.

The substrate CALLED BY the machinery of BEDROCK cells 3/8/11/20 (X→STORE, `put`), 13/15/16
(STORE→X, `get`/`materialize`), and the bounded payloads of 6/10/14 (`slice_lines` — the only
shape in which bytes may enter CONTEXT). Cell wiring status lives in BEDROCK.md's table, not
here — a primitive existing does not mark a cell SERVED. Layout under $LEVER_STORE_DIR
(default ~/.claude/lever_store): `objects/<sha256hex>` immutable artifacts named by their own
checksum; `firings.jsonl` the append-only ledger, one JSON line per operation.

Constitutional properties (BEDROCK): pure function of (args, disk state); artifacts land via
full-write + fsync + rename (POSIX-atomic, short writes looped, temp unlinked on failure);
identical bytes coincide at the same address so N concurrent writers cannot conflict (scale
invariance needs no machinery); the address IS the checksum — validated as 64 lowercase hex
before any filesystem access, re-verified on every read; unknown address, tampered bytes, an
ambiguous source, or a coordinate that doesn't pin real bytes is a HARD ERROR — never a guess,
never a silent clip.

Pinned rulings: the ledger's `ts` field is provenance metadata ONLY — replay, ORDER, and
CONSERVE read LINE ORDER, never timestamp order (under N writers clock reads can invert
relative to append order); no machinery may branch on `ts`. The slice line-universe is
`bytes.splitlines` (\\n, \\r, and \\r\\n all break) — coordinates must come from that same
universe. `put` takes in-memory bytes (context-scale payloads); `put_file` streams from disk in
chunks and never loads the whole file. No model, no network, no judgment. stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_ADDRESS_RX = re.compile(r"[0-9a-f]{64}\Z")


def _root() -> Path:
    return Path(os.environ.get("LEVER_STORE_DIR", "~/.claude/lever_store")).expanduser()


def _record(op: str, address: str | None, **detail) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "op": op,
                       "address": address, **detail})
    with open(root / "firings.jsonl", "a") as f:
        f.write(line + "\n")


def _load_verified(address: str) -> bytes:
    if not isinstance(address, str) or not _ADDRESS_RX.fullmatch(address):
        raise KeyError(f"unknown address: {address!r}")
    obj = _root() / "objects" / address
    if not obj.is_file():
        raise KeyError(f"unknown address: {address}")
    data = obj.read_bytes()
    if hashlib.sha256(data).hexdigest() != address:
        raise ValueError(f"tampered object: bytes at {address} do not hash to their address")
    return data


def _write_atomic(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=".tmp-")
    closed = False
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        os.close(fd)
        closed = True
        os.replace(tmp, dst)
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def put(data: bytes) -> str:
    """bytes → address. Idempotent: identical bytes coincide at the same address."""
    address = hashlib.sha256(data).hexdigest()
    obj = _root() / "objects" / address
    if not obj.exists():
        _write_atomic(obj, data)
    _record("put", address, size=len(data))
    return address


def put_file(path: str) -> str:
    """file → address, streamed: hashed and copied in one chunked pass, never loading the
    whole file into memory (the source file itself is untouched)."""
    objects = _root() / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=objects, prefix=".tmp-")
    closed = False
    try:
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as src:
            while chunk := src.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                view = memoryview(chunk)
                while view:
                    view = view[os.write(fd, view):]
        os.fsync(fd)
        os.close(fd)
        closed = True
        address = digest.hexdigest()
        os.replace(tmp, objects / address)
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _record("put", address, size=size, source=path)
    return address


def get(address: str) -> bytes:
    """address → exact bytes, integrity re-verified."""
    data = _load_verified(address)
    _record("get", address)
    return data


def materialize(address: str, dst: str) -> None:
    """address → byte-exact file on disk, atomic. Verifies before touching the destination."""
    data = _load_verified(address)
    _write_atomic(Path(dst), data)
    _record("materialize", address, dst=dst)


def slice_lines(address: str | None = None, path: str | None = None,
                start: int | None = None, end: int | None = None) -> bytes:
    """Exactly one source + a 1-indexed inclusive line range → those lines and nothing else."""
    if (address is None) == (path is None):
        raise ValueError("exactly one of address/path must be given")
    if start is None or end is None or start < 1 or end < start:
        raise ValueError(f"invalid line range: start={start} end={end}")
    if address is not None:
        data = _load_verified(address)
    else:
        assert path is not None  # guaranteed by the exactly-one guard above
        data = Path(path).read_bytes()
    lines = data.splitlines(keepends=True)
    if end > len(lines):
        raise ValueError(f"range ends at line {end} but source has {len(lines)} lines")
    _record("slice", address, path=path, start=start, end=end)
    return b"".join(lines[start - 1:end])


def has(address) -> bool:
    """Does this address resolve? Invalid shape is simply False — no error, no fs read."""
    if not isinstance(address, str) or not _ADDRESS_RX.fullmatch(address):
        return False
    return (_root() / "objects" / address).is_file()


def record(op: str, address: str | None = None, **detail) -> None:
    """Capture-tier ledger append (LAW two-tier amendment): observations only, atomic line,
    order is line order. Public alias of the internal writer."""
    _record(op, address, **detail)


def firings() -> list[dict]:
    """The ledger, parsed, in LINE order (the only order that exists -- ts is provenance)."""
    ledger = _root() / "firings.jsonl"
    if not ledger.is_file():
        return []
    out = []
    for lineno, line in enumerate(ledger.read_text().splitlines(), 1):
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"ledger corrupt at line {lineno}: {e}") from e
    return out


def main() -> int:
    try:
        cmd = sys.argv[1]
        if cmd == "put":
            print(put(sys.stdin.buffer.read()))
        elif cmd == "put-file":
            print(put_file(sys.argv[2]))
        elif cmd == "get":
            sys.stdout.buffer.write(get(sys.argv[2]))
        elif cmd == "materialize":
            materialize(sys.argv[2], sys.argv[3])
        elif cmd == "slice":
            sys.stdout.buffer.write(slice_lines(address=sys.argv[2],
                                                start=int(sys.argv[3]), end=int(sys.argv[4])))
        else:
            raise ValueError(f"unknown command: {cmd}")
    except IndexError:
        print("usage: python -m lever.store put | put-file <path> | get <addr> | "
              "materialize <addr> <dst> | slice <addr> <start> <end>", file=sys.stderr)
        return 1
    except (KeyError, ValueError, OSError) as e:
        print(f"lever.store: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
