# Copyright 2025-2026 cxh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""mcptoon CCR — Compress, Cache, Retrieve (zero dependencies).

Why this exists
---------------
:mod:`mcptoon.compressor` throws bytes away: it truncates strings and drops
array tails. On its own that is a one-way door — the moment a model needs the
detail that was dropped, the task stalls. CCR is the door back.

When a result is compressed, the **original** is written to a short-TTL local
store and the compressed view carries a handle. If the model finds the summary
insufficient it calls ``mcptoon_retrieve`` with that handle and gets the full
payload back. Compression stops being lossy and becomes *lazy loading* — the
decision to pay for the detail is deferred to the model, which is the only
party that knows whether it needs it.

This is the same idea as Headroom's ``headroom_retrieve`` tool
(``headroomlabs-ai/headroom``, Apache-2.0), reimplemented on the standard
library. Design choices worth naming:

* **Content-addressed handles.** The handle is a hash of the payload, so the
  same result stored twice is stored once — the store self-dedupes.
* **TTL, not permanence.** Entries expire (default: the same 5 minutes
  ``cache.py`` uses) so the store cannot grow without bound.
* **Never raises.** A failed store or retrieve degrades to "no handle" / "not
  found" — compression must not break a tool call because a temp file was busy.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_DEFAULT_TTL = 300            # 5 minutes, matching cache.py
_MAX_ENTRY_BYTES = 1_000_000  # 1 MB per entry — bigger results are not cached
_MAX_STORE_BYTES = 50_000_000  # 50 MB total; oldest entries evicted past this


def _store_dir() -> Path:
    """Where handles live. ``MCPTOON_CCR_DIR`` redirects it (tests, CI)."""
    override = os.environ.get("MCPTOON_CCR_DIR")
    if override:
        return Path(override)
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return Path(home) / ".mcptoon" / "ccr"


def _ttl() -> int:
    try:
        return int(os.environ.get("MCPTOON_CCR_TTL", _DEFAULT_TTL))
    except (TypeError, ValueError):
        return _DEFAULT_TTL


def _handle_for(server: str, tool: str, payload: Any) -> str:
    """Content-addressed handle: same payload → same handle."""
    try:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        blob = repr(payload)
    digest = hashlib.sha1(f"{server}:{tool}:{blob}".encode()).hexdigest()
    return digest[:12]


def store(original: Any, *, server: str, tool: str, ttl: int | None = None) -> str | None:
    """Persist ``original`` and return its handle, or None if it was not stored.

    Returns None (rather than raising) when the payload is too large to cache or
    the disk write fails: a missing handle means "you cannot retrieve this",
    which the caller renders by simply omitting the retrieve hint.
    """
    try:
        blob = json.dumps(original, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    if len(blob.encode("utf-8")) > _MAX_ENTRY_BYTES:
        return None

    handle = _handle_for(server, tool, original)
    path = _store_dir() / f"{handle}.json"
    try:
        _store_dir().mkdir(parents=True, exist_ok=True)
        entry = {
            "handle": handle,
            "server": server,
            "tool": tool,
            "ts": time.time(),
            "ttl": _ttl() if ttl is None else ttl,
            "original": original,
        }
        tmp = path.with_name(f"{handle}.json.tmp.{os.getpid()}")
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return None

    _maybe_evict()
    return handle


def retrieve(handle: str) -> Any | None:
    """Return the stored original for ``handle``, or None if missing/expired."""
    if not handle or not isinstance(handle, str):
        return None
    # A handle is a hex digest prefix; reject anything else before touching disk.
    if not all(c in "0123456789abcdef" for c in handle):
        return None
    path = _store_dir() / f"{handle}.json"
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(entry, dict):
        return None
    if time.time() - entry.get("ts", 0) > entry.get("ttl", _DEFAULT_TTL):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return entry.get("original")


def sweep() -> int:
    """Delete expired entries. Returns how many were removed."""
    removed = 0
    d = _store_dir()
    if not d.exists():
        return 0
    now = time.time()
    for path in d.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if now - entry.get("ts", 0) > entry.get("ttl", _DEFAULT_TTL):
                path.unlink()
                removed += 1
        except (OSError, json.JSONDecodeError):
            continue
    return removed


def _maybe_evict() -> None:
    """Evict oldest entries when the store exceeds its byte budget."""
    d = _store_dir()
    try:
        files = [(p, p.stat().st_mtime, p.stat().st_size) for p in d.glob("*.json")]
    except OSError:
        return
    total = sum(size for _, _, size in files)
    if total <= _MAX_STORE_BYTES:
        return
    for path, _, size in sorted(files, key=lambda f: f[1]):
        if total <= _MAX_STORE_BYTES:
            break
        try:
            path.unlink()
            total -= size
        except OSError:
            continue


def stats() -> dict:
    """Small read-only summary — count, bytes and oldest age of the store."""
    d = _store_dir()
    if not d.exists():
        return {"count": 0, "bytes": 0, "oldest_age": 0}
    count = size = 0
    oldest = 0.0
    now = time.time()
    for path in d.glob("*.json"):
        try:
            st = path.stat()
            count += 1
            size += st.st_size
            oldest = max(oldest, now - st.st_mtime)
        except OSError:
            continue
    return {"count": count, "bytes": size, "oldest_age": round(oldest, 1)}
