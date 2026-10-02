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

"""mcptoon compressor — structure-aware result compression (zero dependencies).

Why this exists
---------------
mcptoon's existing output formats (``--toon``/``--slim``/``--compact``) only
*re-encode* a payload: JSON becomes TOON, and the same content costs fewer tokens —
1.8%-48.6% on call results depending on the result's shape, 11.8% on tool schemas
(measured 2026-10-02, assets/benchmark_results.json + benchmark_schemas_repro.json;
there is no single flat figure, which is why the README stopped quoting one). They never touch the content itself. Measured on this machine, a
25-row search result costs 6,327 tokens as JSON and 5,827 as TOON — an 8% win.

The compression layer this module adds is different: it is **content-aware**.
It keeps the *navigation* (keys, structure, booleans, nulls, the top-ranked
items) and compresses the *payload* (long string values, redundant array tails).
The same 25-row payload lands at 973 tokens — an 85% win — while every key name
and every scalar type survives, so a model reading the result still understands
the shape of the data.

This mirrors the SmartCrusher / ContentRouter / LogCompressor / SearchCompressor
design of ``headroomlabs-ai/headroom`` (Apache-2.0), reimplemented here on the
standard library so it can live inside mcptoon without breaking the project's
zero-dependency rule (see ``AGENTS.md``; CI enforces it via
``scripts/check_zero_deps.py``).

Reversibility is the other half, and it lives in :mod:`mcptoon.ccr`: whatever
this module drops can be fetched back with ``mcptoon_retrieve``. Compression is
therefore not a dead end — it is lazy loading.

Invariants (pinned by ``tests/test_compressor.py``)
---------------------------------------------------
1. Every dict key in the input is present in the output.
2. Scalar types (bool / None / int / float) pass through unchanged.
3. The output is always JSON-serialisable.
4. ``compress()`` is idempotent: compressing an already-compressed payload does
   not shrink it further.
5. Binary / base64-looking payloads are never compressed.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ─── Defaults ───

DEFAULT_STR_BUDGET = 120   # chars a string value may keep before truncation
DEFAULT_KEEP_HEAD = 8      # array items kept when a list is truncated
DEFAULT_MAX_ITEMS = 40     # hard cap for non-uniform arrays of scalars
ELLIPSIS = "\u2026"        # the single marker a truncated string ends with

# ─── Content detection ───

_SEARCH_KEYS = frozenset(
    {"path", "file", "filename", "score", "line", "lineno", "snippet",
     "matched_terms", "url", "title", "rank", "relevance", "excerpt"}
)
_LOG_LINE_RE = re.compile(
    r"^\s*(?:\[?\d{4}-\d{2}-\d{2}|\[?\d{2}:\d{2}:\d{2}|\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    r"|\b(?:INFO|WARN|WARNING|ERROR|DEBUG|TRACE|CRITICAL|FATAL)\b"
)
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n\s]+$")


def _looks_binary(text: str) -> bool:
    """True for base64 blobs / data URIs — payloads that must never be compressed.

    A truncated base64 blob is not "smaller context", it is a corrupted image the
    model can no longer reason about. Callers that hit this return the input
    untouched, which is also why the check is deliberately generous.
    """
    if not isinstance(text, str):
        return False
    if text.startswith("data:") and ";base64," in text[:128]:
        return True
    stripped = text.strip()
    if len(stripped) < 256:
        return False
    if not _BASE64_RE.match(stripped):
        return False
    # Base64 has no long runs of a single character; prose/JSON does not match
    # the alphabet above in the first place. Length alone is the discriminator.
    return True


def detect_kind(obj: Any) -> str:
    """Classify a payload so the right compressor can be chosen.

    Returns one of: ``"binary"``, ``"search"``, ``"log"``, ``"json"``,
    ``"text"``, ``"scalar"``. Detection is conservative: anything unrecognised
    falls through to ``"json"`` / ``"text"`` rather than guessing.
    """
    if isinstance(obj, str):
        if _looks_binary(obj):
            return "binary"
        lines = obj.splitlines()
        if len(lines) >= 5 and sum(1 for ln in lines if _LOG_LINE_RE.search(ln)) >= max(3, len(lines) // 4):
            return "log"
        return "text"

    if isinstance(obj, list) and obj and all(isinstance(i, dict) for i in obj):
        keys = set().union(*(i.keys() for i in obj))
        if len(keys & _SEARCH_KEYS) >= 2:
            return "search"

    if isinstance(obj, (dict, list)):
        # A dict whose values are all strings that look like log lines.
        if isinstance(obj, dict):
            vals = [v for v in obj.values() if isinstance(v, str)]
            if vals and all(_LOG_LINE_RE.search(v) for v in vals):
                return "log"
        return "json"

    return "scalar"


# ─── Token counting (one caliber, shared with bench/usage) ───

def _count_tokens(payload: Any) -> int:
    """Tokens for a payload, on the same caliber ``mcptoon bench`` uses."""
    try:
        from .usage import count_tokens
        return count_tokens(payload)
    except Exception:
        try:
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            return max(1, len(text) // 4)
        except (TypeError, ValueError):
            return 0


# ─── SmartCrusher ───

def _crush_string(text: str, budget: int) -> tuple[str, int]:
    """Truncate one string at a word boundary. Returns (value, truncated_flag)."""
    if len(text) <= budget:
        return text, 0
    if text.endswith(ELLIPSIS):
        return text, 0  # already crushed — keeps compress() idempotent
    cut = text[:budget]
    space = cut.rfind(" ")
    if space > budget // 2:
        cut = cut[:space]
    return cut + ELLIPSIS, 1


def _maybe_json_string(text: str) -> Any:
    """Parse a string that carries an embedded JSON object/array, else None.

    Plenty of MCP servers ship structured results as JSON *inside* a text field
    (``structuredContent: {"content": "<json string>"}``). Blind-truncating that
    string throws away the structure SmartCrusher exists to preserve, so the
    walker recurses into it when it parses and re-serialises the crushed form.
    """
    s = text.strip()
    if len(s) < 64 or s[0] not in "[{":
        return None
    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _contains_list(node: Any, depth: int = 0) -> bool:
    """True when the payload holds a list anywhere, embedded JSON included."""
    if isinstance(node, list):
        return True
    if isinstance(node, dict):
        return any(_contains_list(v, depth) for v in node.values())
    if isinstance(node, str) and depth < 4:
        embedded = _maybe_json_string(node)
        if embedded is not None:
            return _contains_list(embedded, depth + 1)
    return False


def is_compressible(obj: Any) -> bool:
    """Whether a payload is a *safe* target for structure-aware compression.

    This gate is what lets compression run **by default** without eating data.
    The shapes SmartCrusher helps are the redundant ones: a list of records
    (search results, directory entries), a JSON object with nested arrays, or a
    repetitive log. The shape it would *harm* is a single document — a source
    file, a long prose answer, one big text blob — where truncating the one
    string that carries the payload destroys it while saving little.

    So: a lone long string, or a small dict holding one long string and nothing
    structured, is passed through untouched. A payload with a list in it, or
    enough keys to be a record, is fair game.
    """
    if detect_kind(obj) == "binary":
        return False
    if isinstance(obj, list):
        return len(obj) >= 2
    if isinstance(obj, dict):
        return _contains_list(obj) or len(obj) >= 8
    if isinstance(obj, str):
        return detect_kind(obj) == "log"
    return False


def smart_crush(obj: Any, *, str_budget: int = DEFAULT_STR_BUDGET,
                keep_head: int = DEFAULT_KEEP_HEAD,
                max_items: int = DEFAULT_MAX_ITEMS) -> tuple[Any, dict]:
    """Keep the navigation, compress the payload.

    Dicts keep every key and recurse; lists keep their head and drop a redundant
    tail; strings are truncated at a word boundary; scalars pass through. Returns
    ``(crushed, stats)``.
    """
    stats = {"truncated_strings": 0, "dropped_items": 0, "deduped_items": 0}

    def walk(node: Any, depth: int = 0) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, depth) for k, v in node.items()}
        if isinstance(node, list):
            items = [walk(v, depth) for v in node]
            # Dedupe identical records (log/JSON tails are often repeats).
            seen: set[str] = set()
            deduped: list[Any] = []
            for it in items:
                try:
                    key = json.dumps(it, sort_keys=True, ensure_ascii=False)
                except (TypeError, ValueError):
                    key = repr(it)
                if key in seen:
                    stats["deduped_items"] += 1
                    continue
                seen.add(key)
                deduped.append(it)
            items = deduped
            # Truncate a long uniform list to its head; the dropped tail stays
            # reachable through CCR, so nothing is really lost.
            limit = keep_head if len(items) > keep_head else max_items
            if len(items) > limit:
                stats["dropped_items"] += len(items) - limit
                items = items[:limit]
            return items
        if isinstance(node, str):
            if depth < 4:
                embedded = _maybe_json_string(node)
                if embedded is not None:
                    return walk(embedded, depth + 1)
            value, cut = _crush_string(node, str_budget)
            stats["truncated_strings"] += cut
            return value
        return node  # bool / None / int / float untouched

    return walk(obj), stats


# ─── Log / Search compressors ───

def _compress_log(text: str) -> tuple[str, dict]:
    """Collapse repeated log lines into ``line  (xN)``, preserving first order."""
    lines = text.splitlines()
    counts: dict[str, int] = {}
    order: list[str] = []
    for ln in lines:
        if ln not in counts:
            counts[ln] = 0
            order.append(ln)
        counts[ln] += 1
    out = []
    merged = 0
    for ln in order:
        if counts[ln] > 1:
            out.append(f"{ln}  (x{counts[ln]})")
            merged += counts[ln] - 1
        else:
            out.append(ln)
    return "\n".join(out), {"merged_lines": merged, "kept_lines": len(order)}


def _compress_search(rows: list, keep_head: int) -> tuple[list, dict]:
    """Keep the top-ranked rows; drop the low-relevance tail."""
    if len(rows) <= keep_head:
        return rows, {"dropped_items": 0}
    return rows[:keep_head], {"dropped_items": len(rows) - keep_head}


# ─── Public entry point ───

def compress(obj: Any, *, str_budget: int = DEFAULT_STR_BUDGET,
             keep_head: int = DEFAULT_KEEP_HEAD) -> tuple[Any, dict]:
    """Compress a tool result. Returns ``(compressed, stats)``.

    ``stats`` carries: ``kind``, ``applied`` (bool), ``before_tokens``,
    ``after_tokens``, ``saved_tokens``, ``pct`` and the per-compressor counters.
    ``applied`` is False when the payload was skipped (binary) or when nothing
    changed — callers use it to decide whether a retrieve handle is worth
    storing.
    """
    before = _count_tokens(obj)
    kind = detect_kind(obj)

    if not is_compressible(obj):
        return obj, {
            "kind": kind, "applied": False, "before_tokens": before,
            "after_tokens": before, "saved_tokens": 0, "pct": 0,
            "truncated_strings": 0, "dropped_items": 0, "deduped_items": 0,
        }

    if kind == "log" and isinstance(obj, str):
        out, extra = _compress_log(obj)
        stats = {"truncated_strings": 0, "dropped_items": 0, "deduped_items": 0, **extra}
    elif kind == "search" and isinstance(obj, list):
        out, extra = _compress_search(obj, keep_head)
        out, stats = smart_crush(out, str_budget=str_budget, keep_head=keep_head)
        stats.update(extra)
    else:
        out, stats = smart_crush(obj, str_budget=str_budget, keep_head=keep_head)

    after = _count_tokens(out)
    saved = max(0, before - after)
    pct = round(100 * saved / before) if before else 0
    applied = after < before

    stats.update({
        "kind": kind, "applied": applied, "before_tokens": before,
        "after_tokens": after, "saved_tokens": saved, "pct": pct,
    })
    return out, stats


def notice(stats: dict, handle: str | None = None) -> str:
    """The one-line signal appended to a compressed result.

    It tells the model two things it cannot otherwise know: that the payload was
    compressed, and how to get the untruncated original back. Without the second
    half, a model that needs a dropped detail has no way to ask for it.
    """
    if not stats.get("applied"):
        return ""
    parts = [f"{stats['before_tokens']}\u2192{stats['after_tokens']} tok "
             f"(\u2212{stats['pct']}%)"]
    if stats.get("dropped_items"):
        parts.append(f"-{stats['dropped_items']} items")
    if stats.get("merged_lines"):
        parts.append(f"-{stats['merged_lines']} log lines")
    if stats.get("truncated_strings"):
        parts.append(f"{stats['truncated_strings']} strings cut")
    tail = f" \u00b7 full text: mcptoon_retrieve handle={handle}" if handle else ""
    return "[mcptoon smart: " + " \u00b7 ".join(parts) + tail + "]"


def compress_with_ccr(obj: Any, *, server: str, tool: str,
                      str_budget: int = DEFAULT_STR_BUDGET,
                      keep_head: int = DEFAULT_KEEP_HEAD) -> tuple[str | None, dict]:
    """Compress, store the original for retrieval, and render the text view.

    This is the whole smart pipeline in one place so the MCP bridge
    (``serve._smart_compress``) and the CLI (``cli._cmd_call``) cannot drift: both
    get a compressed JSON text carrying a retrieve handle. Returns
    ``(text, stats)``; ``text`` is None when nothing was compressed, which tells
    the caller to pass the result through untouched.
    """
    crushed, stats = compress(obj, str_budget=str_budget, keep_head=keep_head)
    if not stats.get("applied"):
        return None, stats
    _mark_applied()
    handle = None
    try:
        from . import ccr as _ccr
        handle = _ccr.store(obj, server=server, tool=tool)
    except Exception:
        handle = None
    text = json.dumps(crushed, ensure_ascii=False, separators=(",", ":"))
    line = notice(stats, handle)
    if line:
        text = f"{text}\n{line}"
    return text, stats


# Whether this *process* compressed a result. The CLI runs one command per
# process, so the footer can ask "did this turn compress anything?" and get a
# truthful answer without any cross-turn bookkeeping that could go stale. The
# long-lived `serve` process stamps its footer at session start, before any call,
# so the flag is False there — which is correct: a session banner is not a turn.
_APPLIED_THIS_RUN = False


def _mark_applied() -> None:
    global _APPLIED_THIS_RUN
    _APPLIED_THIS_RUN = True


def compressed_this_run() -> bool:
    """True once this process has compressed at least one result."""
    return _APPLIED_THIS_RUN


def reset_compressed_this_run() -> None:
    """Clear the flag. The CLI calls this at the top of a run so a long-lived
    embedding process (a test harness, a REPL) cannot inherit a stale True."""
    global _APPLIED_THIS_RUN
    _APPLIED_THIS_RUN = False
