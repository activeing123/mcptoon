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
Also provides cross-agent format export and fuzzy matching.
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


def fuzzy_match_tool(server: str, tool: str, max_suggestions: int = 3) -> list[str]:
    """Find similar tool names using edit distance.

    Returns list of suggestions like ["search", "search_all", "find"]
    """
    tools = get_server_tools(server)
    if not tools:
        return []

    names = [t.get("name", "") for t in tools if "error" not in t]
    if not names:
        return []

    # Simple Levenshtein-based scoring
    scored = []
    for name in names:
        score = _similarity(tool, name)
        if score > 0.4:  # threshold
            scored.append((name, score))

    scored.sort(key=lambda x: -x[1])
    return [name for name, _ in scored[:max_suggestions]]


def _similarity(a: str, b: str) -> float:
    """Normalized similarity score (0=unrelated, 1=identical)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    # Quick prefix/substring check
    if a in b or b in a:
        return 0.8

    # Levenshtein distance (optimized for short strings)
    dist = _levenshtein(a, b)
    max_len = max(len(a), len(b))
    return 1.0 - (dist / max_len)


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            ins = prev[j + 1] + 1
            dele = curr[j] + 1
            sub = prev[j] + (ca != cb)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]


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


def export_manifest(manifest: dict, fmt: str) -> str:
    """Export manifest in various agent-specific formats.

    Args:
        manifest: {server: [tool_defs]}
        fmt: "openai" | "openapi" | "mcp" | "json" | "human"

    Returns:
        Formatted string ready to use with the target agent/framework.
    """
    if fmt == "json":
        return json.dumps(manifest, indent=2, ensure_ascii=False)

    if fmt == "mcp":
        # MCP tools/list format: flat array of all tools
        all_tools = []
        for server, tools in manifest.items():
            for t in tools:
                if "error" not in t:
                    all_tools.append(t)
        return json.dumps({"tools": all_tools}, indent=2, ensure_ascii=False)

    if fmt == "openai":
        # OpenAI function calling format
        functions = []
        for server, tools in manifest.items():
            for t in tools:
                if "error" in t:
                    continue
                schema = t.get("inputSchema", {})
                functions.append({
                    "type": "function",
                    "function": {
                        "name": f"{server}_{t.get('name', '')}",
                        "description": t.get("description", ""),
                        "parameters": schema,
                    },
                })
        return json.dumps(functions, indent=2, ensure_ascii=False)

    if fmt == "openapi":
        # OpenAPI 3.0 spec
        paths = {}
        for server, tools in manifest.items():
            for t in tools:
                if "error" in t:
                    continue
                tool_name = t.get("name", "")
                path = f"/{server}/{tool_name}"
                schema = t.get("inputSchema", {})
                paths[path] = {
                    "post": {
                        "summary": t.get("description", ""),
                        "operationId": f"{server}_{tool_name}",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": schema or {"type": "object"}
                                }
                            }
                        },
                        "responses": {
                            "200": {"description": "Tool result"}
                        },
                    }
                }

        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "mcptoon MCP tools",
                "version": "0.2.0",
                "description": "Auto-generated from MCP tool manifest",
            },
            "paths": paths,
        }
        return json.dumps(spec, indent=2, ensure_ascii=False)

    if fmt == "human":
        return format_manifest(manifest, full=True)

    # Fallback
    return json.dumps(manifest, indent=2, ensure_ascii=False)
