# Copyright 2025 cxh
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

"""
mcptoon cache — Schema cache for tool discovery

Caches tool lists per server to avoid repeated initialize/list_tools round-trips.
TTL: 5 minutes (configurable via MCPTOON_CACHE_TTL env var)

Thread-safe: uses file locking for multi-process safety.
"""
import hashlib
import json
import os
import time
import threading

from .config import CACHE_DIR

_DEFAULT_TTL = 300  # 5 minutes
_CACHE_FILE = CACHE_DIR / "schema_cache.json"
_LOCK_FILE = CACHE_DIR / "schema_cache.lock"

# In-process lock (for multi-thread, same process)
_process_lock = threading.Lock()


def _get_ttl() -> int:
    try:
        return int(os.environ.get("MCPTOON_CACHE_TTL", _DEFAULT_TTL))
    except ValueError:
        return _DEFAULT_TTL


def tools_fingerprint(tools: list[dict]) -> str:
    """Content signature for a server's tool set: sorted names + each tool's
    required-param list. Cheap and stable; changes exactly when the callable
    surface changes (tool added/removed, or a tool's required args change),
    which is precisely when a cached manifest becomes unsafe to trust.
    Defensive against malformed servers (null inputSchema, non-dict entries).
    """
    surface = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        req = (t.get("inputSchema") or {}).get("required") or []
        surface.append((t.get("name", "?"), sorted(req)))
    surface.sort()
    blob = json.dumps(surface, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _load_cache() -> dict:
    """Load the cache file."""
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict):
    """Save the cache file with in-process lock + atomic write."""
    try:
        # Atomic write: write to temp file, then rename
        tmp_file = _CACHE_FILE.with_suffix(".tmp")
        tmp_file.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        # os.replace is atomic on most platforms
        os.replace(str(tmp_file), str(_CACHE_FILE))
    except OSError:
        pass


def get_cached_tools(server: str) -> list[dict] | None:
    """Get cached tools for a server, or None if cache miss/expired."""
    with _process_lock:
        cache = _load_cache()
    entry = cache.get(server)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > _get_ttl():
        return None
    return entry.get("tools", [])


def set_cached_tools(server: str, tools: list[dict]) -> bool:
    """Cache tools for a server (thread-safe, atomic write).

    Stores a content fingerprint alongside the tools and returns True when the
    server's *callable surface* (tool names + required args) actually changed
    versus what was cached, False when it is identical. `serve` uses that
    signal to log MCP tool drift across manifest refreshes without diffing
    payloads itself.
    """
    fp = tools_fingerprint(tools)
    with _process_lock:
        cache = _load_cache()
        old_fp = cache.get(server, {}).get("fp")
        cache[server] = {"tools": tools, "ts": time.time(), "fp": fp}
        _save_cache(cache)
    return old_fp != fp


def clear_cache():
    """Clear all cached tools."""
    with _process_lock:
        try:
            _CACHE_FILE.unlink()
        except FileNotFoundError:
            pass


def clear_server_cache(server: str):
    """Clear cached tools for a specific server."""
    with _process_lock:
        cache = _load_cache()
        if server in cache:
            del cache[server]
            _save_cache(cache)
