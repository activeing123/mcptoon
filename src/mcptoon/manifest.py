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

from . import cache as cache_mod
from .config import load_config
from .client import MCPClientPool, MCPError


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


# ═══════════════════════════════════════════════════════════════
# Cross-server tool search
# ═══════════════════════════════════════════════════════════════

def search_tools(query: str, use_cache: bool = True, limit: int = 20) -> list[dict]:
    """Search tools across all configured servers by keyword.

    Searches tool names and descriptions using a multi-factor scoring
    algorithm (exact match > prefix > substring > token overlap > fuzzy).

    Args:
        query: Search query (e.g. "search web", "git commit", "fetch url")
        use_cache: Use cached tool manifests when available
        limit: Maximum results to return

    Returns:
        List of dicts, each with: server, tool, name, description, score
        Sorted by score (highest first).

    Example:
        >>> results = search_tools("search web")
        >>> # [{"server": "exa", "name": "search", "description": "...", "score": 1.0}, ...]
    """
    manifest = get_manifest(use_cache=use_cache)
    query_lower = query.lower().strip()
    query_tokens = set(_tokenize(query_lower))

    results = []

    for server, tools in sorted(manifest.items()):
        if not tools:
            continue

        for t in tools:
            if "error" in t:
                continue

            name = t.get("name", "")
            desc = t.get("description", "")
            name_lower = name.lower()
            desc_lower = desc.lower()

            score = _search_score(query_lower, query_tokens, name_lower, desc_lower)
            if score > 0:
                # Extract schema summary
                schema = t.get("inputSchema", {})
                props = schema.get("properties", {})
                required = set(schema.get("required", []))
                params = []
                for pname, pdef in props.items():
                    ptype = pdef.get("type", "any")
                    if isinstance(ptype, list):
                        ptype = ptype[0] if ptype else "any"
                    marker = "*" if pname in required else ""
                    params.append(f"{pname}:{ptype}{marker}")

                results.append({
                    "server": server,
                    "name": name,
                    "description": desc[:120] if desc else "",
                    "params": ",".join(params) if params else "",
                    "score": round(score, 2),
                })

    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def find_tool_across_servers(tool_name: str, use_cache: bool = True) -> list[str]:
    """Find which servers have a tool with the given name.

    Args:
        tool_name: Exact tool name to search for
        use_cache: Use cached manifests when available

    Returns:
        List of server names that have this tool.
        Empty list if no server has it.

    Example:
        >>> find_tool_across_servers("search")
        ["exa", "brave-search", "tavily"]
    """
    manifest = get_manifest(use_cache=use_cache)
    servers_with_tool = []

    for server, tools in sorted(manifest.items()):
        if not tools:
            continue
        for t in tools:
            if "error" in t:
                continue
            if t.get("name") == tool_name:
                servers_with_tool.append(server)
                break  # Found in this server, no need to check more tools

    return servers_with_tool


def _tokenize(text: str) -> list[str]:
    """Split text into search tokens.

    Splits on non-alphanumeric characters, filters short tokens.
    """
    tokens = []
    current = []
    for c in text:
        if c.isalnum():
            current.append(c)
        else:
            if current:
                token = "".join(current)
                if len(token) >= 2:
                    tokens.append(token)
                current = []
    if current:
        token = "".join(current)
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def _search_score(query: str, query_tokens: set, name: str, desc: str) -> float:
    """Multi-factor relevance score for tool search.

    Scoring factors:
      - Exact name match: 1.0
      - Name starts with query: 0.8
      - Query substring in name: 0.7
      - Name token in query tokens: 0.6 each
      - Query in description: 0.4
      - Query token overlap with description: 0.2 each
      - Fuzzy name similarity: 0.3 * similarity

    Returns 0 if no relevance.
    """
    if not query or not name:
        return 0.0

    score = 0.0

    # Factor 1: Exact match
    if query == name:
        return 1.0

    # Factor 2: Name starts with query
    if name.startswith(query):
        score = max(score, 0.85)

    # Factor 3: Query is substring of name
    if query in name:
        score = max(score, 0.75)

    # Factor 4: Name tokens match query tokens
    name_tokens = set(_tokenize(name))
    if query_tokens and name_tokens:
        overlap = len(query_tokens & name_tokens)
        if overlap > 0:
            score = max(score, 0.6 + 0.05 * overlap)

    # Factor 5: Query in description
    if desc and query in desc:
        score = max(score, 0.45)

    # Factor 6: Query token overlap with description
    if desc and query_tokens:
        desc_tokens = set(_tokenize(desc))
        overlap = len(query_tokens & desc_tokens)
        if overlap > 0:
            score = max(score, 0.2 + 0.05 * overlap)

    # Factor 7: Fuzzy similarity (for typos) — always try as a last resort
    sim = _similarity(query, name)
    if sim > 0.5:
        score = max(score, 0.3 * sim)

    return score
