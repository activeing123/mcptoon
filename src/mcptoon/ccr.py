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

When a result is compressed, the **original** is written to a local store and the
compressed view carries a handle. If the model finds the summary insufficient it
calls ``mcptoon_retrieve`` with that handle and gets the full payload back.
Compression stops being lossy and becomes *lazy loading* — the decision to pay
for the detail is deferred to the model, which is the only party that knows
whether it needs it.

The lossless contract
---------------------
Compression may **hide** information from the context. It may never **destroy**
it. Three rules make that true; each one repairs a measured failure (the tests
that pin them live in ``tests/test_ccr_lossless.py``):

1. **No timer destroys data by default.** Entries used to expire after 5 minutes
   and ``retrieve`` unlinked the file, so five minutes after a tool call the
   truncated detail was gone for good. The default is now *no expiry*; a TTL is
   opt-in via ``MCPTOON_CCR_TTL`` for operators who would rather trade
   losslessness for disk.
2. **Size is not a reason to lose data.** Payloads over 1 MB used to be refused
   outright, and the compressed view then carried **no handle at all** — a model
   was told "-52 items · 8 strings cut" with nowhere to go. Anything that fits in
   the store is now stored, and anything that cannot is *said out loud* by
   :func:`mcptoon.compressor.notice` instead of silently.
3. **Failure is distinguishable.** ``retrieve`` used to answer ``None`` for four
   different situations (bad handle, never stored, evicted, expired), so a model
   could not tell "you misremembered the handle" from "that data is gone".
   :func:`retrieve_status` answers from a closed set instead.

Design choices worth naming:

* **Content-addressed handles.** The handle is a hash of the payload, so the
  same result stored twice is stored once — the store self-dedupes. That is also
  what makes session de-duplication possible (see below): the same payload always
  hashes to the same handle, so "have I already sent this?" is a set lookup.
* **Bounded by bytes, not by time.** The store is evicted oldest-first once it
  exceeds ``MCPTOON_CCR_MAX_BYTES`` (default 200 MB). Under the default
  configuration eviction is the *only* way an entry disappears — and a handle
  that pointed at an evicted entry reports ``never-stored`` rather than
  returning empty data.
* **Sessions.** :func:`begin_session` groups calls so the bridge can answer "did
  I already send this exact payload in this conversation?" and reply with a
  one-line reference instead of the body. The active session is thread-local,
  because `serve --listen` handles several agents at once: a process-wide id
  would let two request threads overwrite each other and one agent would be told
  it had already seen another agent's data. The default session is the process,
  which is what a one-shot CLI run wants — it has no earlier turn, so it can
  never de-duplicate against one. A caller that cannot name its conversation
  passes ``dedup=False`` and gets no shortcut at all.
* **Never raises.** A failed store or retrieve degrades to "no handle" / a
  status — compression must not break a tool call because a temp file was busy.

This is the same idea as Headroom's ``headroom_retrieve`` tool
(``headroomlabs-ai/headroom``, Apache-2.0), reimplemented on the standard
library.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, NamedTuple

# ─── Policy ───
#
# 0 means "never expires". That is the default because an expiring store is a
# lossy store, and not being lossy is the entire point of CCR. Operators who
# would rather bound the disk by time than by bytes set MCPTOON_CCR_TTL.
_NO_TTL = 0
_DEFAULT_MAX_STORE_BYTES = 200_000_000

# ─── Closed status set (retrieve) ───
#
# Four outcomes used to collapse into one `None`. They are different facts and a
# model needs to tell them apart: two mean "ask for something else", one means
# "this is gone", one means "you typed it wrong".
STATUS_OK = "ok"
STATUS_BAD_HANDLE = "bad-handle"
STATUS_NEVER_STORED = "never-stored"
STATUS_EXPIRED = "expired"
STATUS_UNREADABLE = "unreadable"

RETRIEVE_STATUSES = (
    STATUS_OK, STATUS_BAD_HANDLE, STATUS_NEVER_STORED, STATUS_EXPIRED,
    STATUS_UNREADABLE,
)

# ─── Closed reason set (store) ───
REASON_TOO_BIG = "too-big"
REASON_UNSERIALISABLE = "unserialisable"
REASON_WRITE_FAILED = "write-failed"


class StoreOutcome(NamedTuple):
    """What :func:`store_ex` did: the handle (or ``None``) and why, on failure.

    ``store`` alone cannot express "I could not keep this", and a caller that
    silently loses the reason is exactly how a compressed view ends up with no
    handle and no explanation. ``bytes`` is the serialised size, so a caller can
    say how large the thing it could not keep was.
    """

    handle: str | None
    reason: str | None = None
    bytes: int = 0


# ─── Store location and policy readers ───

def _store_dir() -> Path:
    override = os.environ.get("MCPTOON_CCR_DIR")
    if override:
        return Path(override)
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return Path(home) / ".mcptoon" / "ccr"


def _ttl() -> int:
    """Entry lifetime in seconds. ``0`` (the default) means never expires."""
    raw = (os.environ.get("MCPTOON_CCR_TTL") or "").strip()
    if not raw:
        return _NO_TTL
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return _NO_TTL


def _max_store_bytes() -> int:
    raw = (os.environ.get("MCPTOON_CCR_MAX_BYTES") or "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return _DEFAULT_MAX_STORE_BYTES


def _handle_for(server: str, tool: str, blob: str) -> str:
    """Content-addressed handle: the same payload always hashes the same."""
    raw = f"{server}:{tool}:{blob}".encode("utf-8", "replace")
    return hashlib.sha1(raw).hexdigest()[:12]


def _payload_blob(original: Any) -> str | None:
    try:
        return json.dumps(original, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


# ─── Session bookkeeping ───
#
# De-duplication is only sound *inside one conversation*: telling a fresh session
# "same as handle X" would reference something it never saw. So the sent-set is
# keyed by session, and the default session is the process — a one-shot CLI run
# gets a session that can never match anything, which is the safe answer.
#
# The active session is **thread-local**, because `serve --listen` handles
# several agents concurrently in one process. A process-wide variable would let
# two request threads overwrite each other's session id, and the losing thread
# would then be told "you already saw this" about a payload it never received —
# a wrong answer dressed up as a saving. Thread-local state makes the isolation
# structural instead of hoped-for.

_session_lock = threading.RLock()
_session_local = threading.local()
_session_sent: dict[str, set[str]] = {}
_session_deduped: dict[str, int] = {}
# Fallback for a thread that never called begin_session (a worker pool, a test).
_process_session = ""
_process_dedup = True


def begin_session(session_id: str | None = None, *, dedup: bool = True) -> str:
    """Start (or switch to) a session on this thread; returns its id.

    ``dedup=False`` disables the reference-instead-of-body shortcut for this
    session and allocates no bookkeeping, which is the right answer when the
    caller cannot name the conversation: an HTTP request with no MCP session
    header may belong to any of several agents, and conflating them would tell
    one agent it had already seen another's data.

    ``serve`` calls this once per bridge (stdio: one process, one conversation).
    The HTTP handler calls it per request, so concurrent agents stay separate.
    """
    sid = (session_id or os.environ.get("MCPTOON_SESSION_ID") or "").strip()
    if not sid:
        sid = f"pid-{os.getpid()}"
    with _session_lock:
        global _process_session, _process_dedup
        _session_local.session_id = sid
        _session_local.dedup = bool(dedup)
        if dedup:
            _session_sent.setdefault(sid, set())
            _session_deduped.setdefault(sid, 0)
        else:
            _session_sent.pop(sid, None)
            _session_deduped.pop(sid, None)
        if not _process_session:
            _process_session, _process_dedup = sid, bool(dedup)
    return sid


def current_session() -> str:
    """The session id active on this thread (falling back to the process's)."""
    sid = getattr(_session_local, "session_id", "")
    if sid:
        return sid
    with _session_lock:
        return _process_session or begin_session()


def _dedup_enabled() -> bool:
    if not getattr(_session_local, "session_id", ""):
        return _process_dedup
    return getattr(_session_local, "dedup", True)


def was_sent(handle: str) -> bool:
    """True when this exact payload already went to the model this session."""
    if not handle:
        return False
    with _session_lock:
        if not _dedup_enabled():
            return False
        return handle in _session_sent.get(current_session(), set())


def mark_sent(handle: str) -> None:
    """Record that ``handle``'s payload has now been sent to the model."""
    if not handle:
        return
    with _session_lock:
        if not _dedup_enabled():
            return
        _session_sent.setdefault(current_session(), set()).add(handle)


def note_deduped() -> int:
    """Count one payload whose body was replaced by a reference; returns the total.

    The count is what lets the footer and ``mcptoon report`` state a saving that
    actually happened instead of a projection.
    """
    with _session_lock:
        sid = current_session()
        _session_deduped[sid] = _session_deduped.get(sid, 0) + 1
        return _session_deduped[sid]


def deduped_count(session_id: str | None = None) -> int:
    """How many bodies this session replaced with a reference."""
    with _session_lock:
        return _session_deduped.get(session_id or current_session(), 0)


def end_session(session_id: str | None = None) -> None:
    """Forget a session's bookkeeping. Stored payloads are left alone."""
    with _session_lock:
        global _process_session
        sid = session_id or current_session()
        _session_sent.pop(sid, None)
        _session_deduped.pop(sid, None)
        if getattr(_session_local, "session_id", "") == sid:
            _session_local.session_id = ""
        if _process_session == sid:
            _process_session = ""


# ─── Write half ───

def store(original: Any, *, server: str, tool: str,
          ttl: int | None = None) -> str | None:
    """Persist ``original`` and return its handle, or ``None`` if not stored.

    Kept for callers that only need the handle. Use :func:`store_ex` when the
    difference between "stored" and "could not store, and here is why" matters —
    which it does for anything that tells a model its result was trimmed.
    """
    return store_ex(original, server=server, tool=tool, ttl=ttl).handle


def store_ex(original: Any, *, server: str, tool: str,
             ttl: int | None = None) -> StoreOutcome:
    """Persist ``original``; report the handle *and* why nothing was stored.

    Never raises: a busy temp file must not fail a tool call. The one refusal
    that survives is "larger than the whole store budget", because keeping such
    an entry would evict everything else and still not fit it.

    The entry this call just wrote is **exempt from the eviction pass**. That is
    not politeness: eviction sorts by mtime, files written in the same clock tick
    tie, and a tie can put the new entry first — which deleted the entry whose
    handle was about to be returned (reproduced 2026-10-02: budget 6,000, a 5,911
    byte payload, `store_ex` answered with a handle and the store was left with
    zero files). A handle that points at nothing is the exact failure this module
    exists to prevent.
    """
    blob = _payload_blob(original)
    if blob is None:
        return StoreOutcome(None, REASON_UNSERIALISABLE)

    handle = _handle_for(server, tool, blob)
    path = _store_dir() / f"{handle}.json"
    entry_ttl = _ttl() if ttl is None else max(0, ttl)

    # Splice the already-serialised payload in rather than re-serialising the
    # wrapper: for a large result that second copy is the expensive part.
    head = json.dumps({
        "handle": handle, "server": server, "tool": tool,
        "ts": time.time(), "ttl": entry_ttl, "bytes": len(blob),
    }, ensure_ascii=False)
    text = f'{head[:-1]}, "original": {blob}}}'

    # The budget is compared against the bytes that actually land on disk, not
    # the payload alone: the wrapper adds a couple of hundred bytes, and judging
    # by the payload let an entry that "fits" be written and then immediately
    # evicted by its own cleanup pass.
    size = len(text.encode("utf-8"))
    budget = _max_store_bytes()
    if size > budget:
        return StoreOutcome(None, REASON_TOO_BIG, size)

    try:
        _store_dir().mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{handle}.json.tmp.{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return StoreOutcome(None, REASON_WRITE_FAILED, size)

    _maybe_evict(keep=handle)
    # Belt and braces: if the entry is somehow gone anyway, do not hand out a
    # handle to nothing — say it was not stored, so the notice is honest.
    if not path.exists():
        return StoreOutcome(None, REASON_WRITE_FAILED, size)
    return StoreOutcome(handle, None, size)


# ─── Read half ───

def retrieve(handle: str) -> Any | None:
    """Return the stored original for ``handle``, or ``None`` if unavailable.

    Kept for callers that only need the value. Use :func:`retrieve_status` when
    "you typed it wrong" and "that data is gone" must not look the same.
    """
    return retrieve_status(handle)[1]


def retrieve_status(handle: str) -> tuple[str, Any | None]:
    """Return ``(status, original)``; status is from :data:`RETRIEVE_STATUSES`.

    ``never-stored`` covers both "no such entry was ever written" and "it was
    evicted under the byte budget" — telling those apart would need a tombstone
    per evicted handle, which costs more than the distinction is worth. The
    important half is that the reference fails *loudly* with a specific reason
    instead of handing back empty data.
    """
    if not handle or not isinstance(handle, str):
        return STATUS_BAD_HANDLE, None
    # A handle is a hex digest prefix; reject anything else before touching disk.
    if not all(c in "0123456789abcdef" for c in handle):
        return STATUS_BAD_HANDLE, None

    path = _store_dir() / f"{handle}.json"
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return STATUS_NEVER_STORED, None
    except (OSError, json.JSONDecodeError):
        return STATUS_UNREADABLE, None
    if not isinstance(entry, dict):
        return STATUS_UNREADABLE, None

    ttl = entry.get("ttl", _NO_TTL)
    if ttl and time.time() - entry.get("ts", 0) > ttl:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return STATUS_EXPIRED, None
    return STATUS_OK, entry.get("original")


# One sentence per failure status, and **only one copy of them**. The MCP tool
# (`native_tools._retrieve`) and the CLI (`mcptoon retrieve`) both answer the same
# question — "why can't I have my data back?" — and the read half originally kept
# that text in `native_tools` alone, so a CLI entry point would have needed a
# second copy. Two copies of a message that must stay identical is exactly the
# drift this module exists to prevent, so the sentences live here, next to the
# closed status set they describe.
#
# The status is only useful if it changes what the reader does next: retype it,
# fetch it again, or stop asking.
RETRIEVE_NOTICES = {
    STATUS_BAD_HANDLE: "That handle is not a handle (they are 12 lowercase hex "
                       "characters, copied from a 'mcptoon_retrieve handle=...' line).",
    STATUS_NEVER_STORED: "No stored result for that handle. Either it was never "
                         "compressed, or the store evicted it to stay under its size "
                         "budget — call the tool again to regenerate it.",
    STATUS_EXPIRED: "That stored result expired and was deleted. Set "
                    "MCPTOON_CCR_TTL=0 (or unset it) to keep originals indefinitely.",
    STATUS_UNREADABLE: "The stored entry exists but could not be read (damaged or "
                       "unreadable file). Call the tool again to regenerate it.",
}


def retrieve_notice(status: str) -> str:
    """The one-sentence explanation for a failed :func:`retrieve_status`.

    Unknown statuses fall back to the ``unreadable`` sentence, because "the store
    exists but I cannot use it" is the honest description of any outcome this
    table does not name.
    """
    return RETRIEVE_NOTICES.get(status, RETRIEVE_NOTICES[STATUS_UNREADABLE])


def sweep() -> int:
    """Delete expired entries. Returns how many were removed.

    Under the default (no TTL) this removes nothing — it exists for operators who
    opted into ``MCPTOON_CCR_TTL``.
    """
    removed = 0
    d = _store_dir()
    if not d.exists():
        return 0
    now = time.time()
    for path in d.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            ttl = entry.get("ttl", _NO_TTL)
            if ttl and now - entry.get("ts", 0) > ttl:
                path.unlink()
                removed += 1
        except (OSError, json.JSONDecodeError):
            continue
    return removed


def _maybe_evict(keep: str | None = None) -> int:
    """Evict oldest entries while the store is over budget. Returns the count.

    This is the only way an entry disappears under the default configuration, so
    it is also the only way a previously issued handle can go stale. Handles that
    do go stale report ``never-stored`` on read.

    ``keep`` names a handle that must survive this pass — :func:`store_ex` passes
    the entry it just wrote, because mtime ties make "newest" a guess rather than
    a fact, and evicting the entry whose handle is about to be returned produces
    exactly the silent dead end this module exists to prevent. The byte budget
    still holds: an entry is only ever written when it fits the budget alone, so
    keeping it while evicting everything else cannot leave the store over budget.
    """
    d = _store_dir()
    budget = _max_store_bytes()
    try:
        files = [(p, p.stat().st_mtime, p.stat().st_size) for p in d.glob("*.json")]
    except OSError:
        return 0
    total = sum(size for _, _, size in files)
    if total <= budget:
        return 0
    keep_name = f"{keep}.json" if keep else None
    removed = 0
    for path, _, size in sorted(files, key=lambda f: f[1]):
        if total <= budget:
            break
        if keep_name and path.name == keep_name:
            continue
        try:
            path.unlink()
            total -= size
            removed += 1
        except OSError:
            continue
    return removed


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


def policy() -> dict:
    """The active retention policy, for anything that has to explain it.

    Separate from :func:`stats` (which reports what is on disk) because a caller
    printing "entries never expire" needs the *setting*, not a file count.
    """
    return {
        "ttl": _ttl(),
        "max_bytes": _max_store_bytes(),
        "session": current_session(),
        "deduped": deduped_count(),
    }
