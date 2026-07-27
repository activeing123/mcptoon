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
mcptoon manifest — Tool discovery

Lists all tools from all configured servers, with optional caching.
"""
import json
from typing import Any

from . import cache as cache_mod
from .config import load_config
from .client import MCPClientPool, MCPError
from .errors import is_error


def get_manifest(use_cache: bool = True) -> dict[str, list[dict]]:
    """Get tool manifest: {server_name: [tool_defs]}.

    Uses cache when available to avoid slow re-discovery.
    """
    servers = load_config()
    result = {}

    for name in sorted(servers.keys()):
        # Try cache first
        if use_cache:
            cached = cache_mod.get_cached_tools(name)
            if cached is not None:
                result[name] = cached
                continue

        # Fetch from server
        try:
            pool = MCPClientPool(servers)
            tools = pool.list_tools(name)
            result[name] = tools
            cache_mod.set_cached_tools(name, tools)
            pool.close()
        except (MCPError, Exception) as e:
            result[name] = [{"error": str(e)[:100]}]

    return result


def get_server_tools(server: str, use_cache: bool = True) -> list[dict]:
    """Get tools for a single server."""
    # Try cache
    if use_cache:
        cached = cache_mod.get_cached_tools(server)
        if cached is not None:
            return cached

    # Fetch
    servers = load_config()
    if server not in servers:
        return []

    try:
        pool = MCPClientPool(servers)
        tools = pool.list_tools(server)
        cache_mod.set_cached_tools(server, tools)
        pool.close()
        return tools
    except (MCPError, Exception):
        return []


def inspect_tool(server: str, tool: str) -> dict | None:
    """Get detailed schema for a specific tool."""
    tools = get_server_tools(server)
    for t in tools:
        if t.get("name") == tool:
            return t
    return None


def format_manifest(manifest: dict, full: bool = False) -> str:
    """Format manifest as human-readable text."""
    lines = []
    for server, tools in sorted(manifest.items()):
        if not tools:
            continue
        has_error = any("error" in t for t in tools)
        if has_error:
            lines.append(f"  {server}: [error: {tools[0].get('error', '?')[:60]}]")
            continue

        if full:
            lines.append(f"\n  [{server}] ({len(tools)} tools)")
            for t in tools:
                name = t.get("name", "?")
                desc = t.get("description", "")[:80]
                lines.append(f"    {name}: {desc}")
                schema = t.get("inputSchema", {})
                props = schema.get("properties", {})
                if props:
                    for pk, pv in props.items():
                        ptype = pv.get("type", "?")
                        pdesc = pv.get("description", "")[:60]
                        req = " (required)" if pk in schema.get("required", []) else ""
                        lines.append(f"      {pk}: {ptype}{req} — {pdesc}")
        else:
            names = " ".join(t.get("name", "?") for t in tools)
            lines.append(f"  {server} ({len(tools)}): {names}")

    return "\n".join(lines)
