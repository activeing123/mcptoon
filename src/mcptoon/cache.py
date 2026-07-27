# -*- coding: utf-8 -*-
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
"""
import json
import os
import time
from pathlib import Path

from .config import CACHE_DIR

_DEFAULT_TTL = 300  # 5 minutes
_CACHE_FILE = CACHE_DIR / "schema_cache.json"


def _get_ttl() -> int:
    try:
        return int(os.environ.get("MCPTOON_CACHE_TTL", _DEFAULT_TTL))
    except ValueError:
        return _DEFAULT_TTL


def _load_cache() -> dict:
    """Load the cache file."""
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict):
    """Save the cache file."""
    try:
        _CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def get_cached_tools(server: str) -> list[dict] | None:
    """Get cached tools for a server, or None if cache miss/expired."""
    cache = _load_cache()
    entry = cache.get(server)
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > _get_ttl():
        return None
    return entry.get("tools", [])


def set_cached_tools(server: str, tools: list[dict]):
    """Cache tools for a server."""
    cache = _load_cache()
    cache[server] = {"tools": tools, "ts": time.time()}
    _save_cache(cache)


def clear_cache():
    """Clear all cached tools."""
    try:
        _CACHE_FILE.unlink()
    except FileNotFoundError:
        pass


def clear_server_cache(server: str):
    """Clear cached tools for a specific server."""
    cache = _load_cache()
    if server in cache:
        del cache[server]
        _save_cache(cache)
