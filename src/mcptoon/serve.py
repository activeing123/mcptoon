# Copyright 2025-2026 activeing123
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
mcptoon serve — stdio bridge MCP server (ADR 0004)

Acts as a single MCP server in front of the agent, proxying all
underlying MCP servers. The agent only connects to mcptoon (1 server),
not 100 individual servers.

  Agent  ←→  mcptoon serve (stdio)  ←→  MCP server 1, 2, ... N

Key behaviors:
  - tools/list: returns simplified schemas (fewer tokens, ADR 0006)
  - tools/call: routes to underlying server, validates args with full schema,
    applies safety checks, compresses output
  - Tool names: {server}_{tool} namespaced (ADR 0007)
  - Parallel manifest loading: 100 servers in ~5s instead of 500s
  - Per-request timeout: no single server can hang the bridge
  - Remote MCP: supports HTTP-stream (SSE) MCP servers transparently

Usage:
  # In agent's mcpServers config:
  "mcptoon": {
    "command": "mcptoon",
    "args": ["serve"]
  }

  # Or with options:
  "mcptoon": {
    "command": "mcptoon",
    "args": ["serve", "--format", "toon"]
  }
"""

from __future__ import annotations

import concurrent.futures
import io
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler

from . import __version__
from . import config
from .config import load_config, resolve_server_name, _is_self_entry, strip_self_entries
from .client import (
    MCPClient,
    MCPClientPool,
    MCPError,
    SUPPORTED_PROTOCOL_VERSIONS,
    ERR_UNSUPPORTED_PROTOCOL_VERSION,
    _META_PROTOCOL_KEY,
    default_call_timeout,
)
from . import manifest as manifest_mod
from . import native_tools
from . import router as router_mod
from . import usage
from .schema_simplifier import (
    simplify_tool_def,
    validate_args,
    namespaced_tool_name,
    split_namespaced,
)

# MCP protocol version we speak as a server
PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "mcptoon", "version": __version__}

# Shown to the model via the `instructions` field of the initialize result. The
# reader is always an MCP client that has this gateway's tools mounted, which is
# why the skill pointer names the tool (`mcptoon_resolve_skills`) rather than the
# shell command: the tool is reachable from every host, the CLI is not.
#
# Two duties, one budget. It is the only channel that reaches the model with no
# action of its own, so it carries the two things the model cannot discover by
# itself: that a skill catalog exists (mcptoon_skills and the resolve tool are in
# the tool list, but a list of tools says nothing about when to reach for one),
# and how to report the savings honestly. Kept as short as both duties allow —
# it rides in context on every turn, the very cost this tool exists to cut.
# Suppressed entirely when the user sets `footer off`.
_INSTRUCTIONS = (
    "You are working through mcptoon, a gateway that compresses MCP tool "
    "definitions to save context. Before acting, call `mcptoon_resolve_skills` "
    "with the user's request and read only the SKILL.md files it returns; never "
    "load the whole catalog. End a turn with one short line reporting what mcptoon "
    "saved — only when the numbers have changed since the line you last showed: "
    "run `mcptoon footer-facts` and paste its output verbatim — a first line "
    "starting `🎉 mcptoon:` plus the `note:` line when printed, in the language it "
    "printed. If byte-identical to the last one this session, show nothing. Do not "
    "retype it from memory, do not translate, and never invent figures. It reads "
    "the cache, never a server, so it is safe every turn; do not substitute "
    "`mcptoon status`, which may spend seconds refreshing. For a per-server "
    "breakdown load the `mcptoon` skill (mcptoon usage, mcptoon bench). If the line "
    "is noisy, `mcptoon config set footer off`. When this turn routed an upstream "
    "tool call, also run `mcptoon statusline` and quote its one line — the presence "
    "receipt (calls, tokens saved, mode) that proves the gateway did the work even "
    "when the savings figures did not move."
)

# _meta key for server identity on results (2026-07-28 _meta world)
_META_SERVERINFO_KEY = "io.modelcontextprotocol/serverInfo"

# Rides in context ONLY while the upstream tool list is withheld
# (setting `exposure=compact`, the default). Without it the model opens a
# `tools/list` holding nothing but mcptoon's own tools and concludes the user's
# MCP servers are gone — that is the failure this directive exists to prevent, and
# it is the whole reason `compact` can be the default at all. Three short
# sentences is deliberate: it is paid for on every turn, but it buys back roughly
# 16,000 tokens that enumerating the upstream tools would cost. The skill
# (`Skill-as-Explainer`) carries the long version, including how to switch back.
_COMPACT_TOOLS_DIRECTIVE = (
    "Your tool list here holds only mcptoon's own tools: the upstream MCP tool "
    "definitions are deliberately withheld to save context (they would cost "
    "thousands of tokens on every turn). They remain fully callable — call "
    "`mcptoon_manifest` to see them by name, `mcptoon_inspect` for one tool's "
    "parameters, then `mcptoon_call` to run it. Ask for the manifest before "
    "concluding that a tool does not exist."
)

# CacheableResult defaults (SEP-2549) for list/read results. Env-tunable:
# MCPTOON_LIST_TTL_MS / MCPTOON_LIST_CACHE_SCOPE.
_LIST_TTL_DEFAULT_MS = 300_000
_LIST_SCOPE_DEFAULT = "public"


def _list_cache_fields() -> dict:
    """CacheableResult hints (SEP-2549) for list/read results.

    Returns {"ttlMs": int >= 1, "cacheScope": "public" | "private"}. Invalid
    env values fall back to the defaults instead of breaking the bridge.
    """
    ttl = _LIST_TTL_DEFAULT_MS
    raw = (os.environ.get("MCPTOON_LIST_TTL_MS") or "").strip()
    if raw:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = -1
        if parsed >= 1:
            ttl = parsed
        else:
            _log(f"invalid MCPTOON_LIST_TTL_MS={raw!r}, "
                 f"using default {_LIST_TTL_DEFAULT_MS}")
    scope = (os.environ.get("MCPTOON_LIST_CACHE_SCOPE") or "").strip().lower()
    if scope not in ("public", "private"):
        if scope:
            _log(f"invalid MCPTOON_LIST_CACHE_SCOPE={scope!r}, "
                 f"using default {_LIST_SCOPE_DEFAULT}")
        scope = _LIST_SCOPE_DEFAULT
    return {"ttlMs": ttl, "cacheScope": scope}

# Default timeout per tool call (seconds)
_DEFAULT_CALL_TIMEOUT = 30
# Default timeout for manifest loading (per server, seconds)
_DEFAULT_MANIFEST_TIMEOUT = 10
# Max workers for parallel manifest loading
_MAX_MANIFEST_WORKERS = 20


class MCPServerBridge:
    """Stdio bridge: speaks MCP server protocol to agent, proxies to underlying servers.

    Thread-safe: each JSON-RPC request is handled in the main thread but
    underlying server calls are non-blocking with timeout.
    """

    def __init__(self, output_format: str = "auto"):
        """
        Args:
            output_format: How to compress tool call results.
                "auto" | "toon" | "slim" | "compact" | "json" | "raw"
        """
        self._output_format = output_format
        self._pool: MCPClientPool | None = None
        self._servers: dict = {}
        # Servers whose last fetch *failed* (as opposed to answered with no tools).
        # `_handle_health` needs this distinction: it used to infer "failed" from
        # "absent from `_tool_index`", which is also true of a healthy server that
        # exposes zero tools — so one alive-but-empty server made /health report
        # `status: "error"` (reproduced 2026-10-02).
        self._server_fetch_errors: dict[str, str] = {}
        # tool_index: namespaced_name → {server, tool, full_schema, full_def}
        self._tool_index: dict[str, dict] = {}
        self._tool_index_lock = threading.RLock()
        # prompts_index: prompt_name → {path, description} (plugin skills)
        self._prompts_index: dict[str, dict] = {}
        self._initialized = False
        self._lock = threading.Lock()
        self._shutdown = False
        # One bridge is one conversation. The CCR store keys its "already sent
        # this exact payload" bookkeeping by session, so the reference-instead-of-
        # body shortcut can only fire against results this conversation actually
        # saw — never against a previous run's (ccr.begin_session).
        try:
            from . import ccr as _ccr
            _ccr.begin_session()
        except Exception:
            pass
        # Last JSON-RPC response built by handle_request (in-process read-back
        # hook; the response is still delivered via _send_response as before).
        self._last_response: dict | None = None
        # Progressive throttle for the gateway's own search tools. Bucketed per
        # agent context (see floodguard's docstring for the fan-out bug a global
        # counter causes). Only the search-shaped tools consult it: a throttle on
        # `mcptoon_manifest` would punish normal discovery.
        from .floodguard import FloodGuard
        self._flood = FloodGuard()

    # ═══════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════

    def _ensure_initialized(self):
        """Lazily load config and build tool index on first use.

        Thread-safe: uses lock, double-check pattern.
        Performance: uses cache (fast path) or parallel loading (slow path).
        """
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._servers = load_config()
            # Last line of defense: `load_config` already strips the gateway's
            # own entry, but if one ever reaches here the gateway would launch
            # itself recursively (fork bomb, measured 2026-10-12: 294 processes,
            # 10.4 GB). Drop it again at the point of use, loudly.
            _self_dropped = [n for n, c in self._servers.items()
                             if _is_self_entry(n, c)]
            if _self_dropped:
                sys.stderr.write(
                    "mcptoon: ignoring self-referencing server entry "
                    f"{_self_dropped!r} — the gateway cannot be its own upstream.\n")
                self._servers = strip_self_entries(self._servers)
            # Hand the documented call timeout down to the clients too: the
            # wrapper in _call_with_timeout can wait 900s, but the client's own
            # deadline fired first at its 30s default (issue #34, 2026-10-22).
            self._pool = MCPClientPool(self._servers, timeout=_get_call_timeout())
            self._build_tool_index()
            self._build_prompts_index()
            self._initialized = True

    def _build_tool_index(self):
        """Build the namespaced tool index from all configured servers.

        Performance strategy:
          1. Fist try cached manifest (fast path, no server startup)
          2. If cache miss for some servers, load them in parallel (ThreadPoolExecutor)
          3. Cache limit: 5 minutes TTL, configurable via MCPTOON_CACHE_TTL
        """
        # Step 1: Try cache first (fast path)
        cached_manifest = {}
        try:
            cached_manifest = manifest_mod.get_manifest(use_cache=True)
        except Exception:
            pass

        # Step 2: Find which servers need live fetch
        all_servers = list(self._servers.keys())
        cached_servers = set(cached_manifest.keys())
        uncached = [s for s in all_servers if s not in cached_servers]

        # Step 3: Build index from cache entries
        for server_name in all_servers:
            tools = cached_manifest.get(server_name, [])
            if not isinstance(tools, list) or not tools:
                continue
            for tool_def in tools:
                if not isinstance(tool_def, dict) or "error" in tool_def:
                    continue
                tool_name = tool_def.get("name", "")
                if not tool_name:
                    continue
                ns_name = namespaced_tool_name(server_name, tool_name)
                with self._tool_index_lock:
                    self._tool_index[ns_name] = {
                        "server": server_name,
                        "tool": tool_name,
                        "full_schema": tool_def.get("inputSchema", {}),
                        "full_def": tool_def,
                    }

        # Step 4: Live fetch uncached servers in parallel
        if uncached and self._pool:
            _log(f"Loading {len(uncached)} uncached servers in parallel...")
            self._refresh_servers_in_parallel(uncached)
            _log(f"Tool index built: {len(self._tool_index)} tools from {len(all_servers)} servers")

    def _refresh_servers_in_parallel(self, server_names: list[str]):
        """Fetch tools from specified servers in parallel using ThreadPoolExecutor.

        This is the key performance optimization for 100+ server scenarios.
        Instead of 100 × 5s = 500s serial, it runs in parallel with max 20 workers.
        """
        if not server_names or not self._pool:
            return

        def _fetch_one(srv: str) -> tuple[str, list[dict]]:
            try:
                tools = self._pool.list_tools(srv)
                # Cache the result; the fingerprint tells us whether this
                # server's callable surface drifted since the last refresh.
                try:
                    from .cache import set_cached_tools
                    if set_cached_tools(srv, tools):
                        _log(f"  [{srv}] tool set changed on refresh "
                             f"({len(tools)} tools) - index updated")
                except Exception:
                    pass
                with self._tool_index_lock:
                    self._server_fetch_errors.pop(srv, None)
                return srv, tools
            except Exception as e:
                _log(f"  [{srv}] fetch failed: {e}")
                with self._tool_index_lock:
                    self._server_fetch_errors[srv] = str(e)[:200]
                return srv, []

        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_MANIFEST_WORKERS,
            thread_name_prefix="mcptoon-manifest",
        )
        try:
            fut_map = {executor.submit(_fetch_one, srv): srv for srv in server_names}
            for fut in concurrent.futures.as_completed(fut_map, timeout=60):
                try:
                    srv, tools = fut.result(timeout=_DEFAULT_MANIFEST_TIMEOUT)
                    for tool_def in tools:
                        if not isinstance(tool_def, dict) or "error" in tool_def:
                            continue
                        tool_name = tool_def.get("name", "")
                        if not tool_name:
                            continue
                        ns_name = namespaced_tool_name(srv, tool_name)
                        with self._tool_index_lock:
                            self._tool_index[ns_name] = {
                                "server": srv,
                                "tool": tool_name,
                                "full_schema": tool_def.get("inputSchema", {}),
                                "full_def": tool_def,
                            }
                except concurrent.futures.TimeoutError:
                    _log(f"  [{fut_map[fut]}] timed out ({_DEFAULT_MANIFEST_TIMEOUT}s)")
                except Exception as e:
                    _log(f"  [{fut_map[fut]}] error: {e}")
        except concurrent.futures.TimeoutError:
            # as_completed hit its 60s wall clock. Do NOT wait for the stragglers:
            # the `with` form would call shutdown(wait=True) here, blocking startup
            # until each hung server reaches its own client timeout (30s, or up to
            # MCPTOON_CALL_TIMEOUT=900s) — which defeats the 60s cap entirely while
            # `_ensure_initialized`'s lock stays held. Cancel pending futures and
            # proceed with whatever landed; late arrivals still index under the lock.
            _log("  manifest refresh exceeded 60s — proceeding with a partial index")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def close(self):
        """Clean up resources."""
        if self._pool:
            try:
                self._pool.close()
            except Exception:
                pass
        self._initialized = False

    # ═══════════════════════════════════════════════════
    # MCP Server Protocol — JSON-RPC over stdio
    # ═══════════════════════════════════════════════════

    def run(self):
        """Main loop: read JSON-RPC from stdin, write responses to stdout.

        This is the entry point for `mcptoon serve`.
        """
        # Force UTF-8 on the stdio pipes. Windows picks the ANSI code page
        # (cp1252/cp936) for a piped stdout unless UTF-8 mode is on; a response
        # carrying a Chinese tool result would then raise UnicodeEncodeError inside
        # `_send_response`'s try/except, get swallowed, and hang the client waiting
        # for a reply that never comes. The bundled demo bridge already does
        # exactly this — serve was the one path missing it. reconfigure is 3.7+.
        for _stream in (sys.stdin, sys.stdout):
            _reconf = getattr(_stream, "reconfigure", None)
            if _reconf is not None:
                try:
                    _reconf(encoding="utf-8")
                except (OSError, ValueError):
                    pass
        _log(f"mcptoon serve started — stdio bridge mode (format={self._output_format})")

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    _send_response({
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    })
                    continue

                self._handle_request(request)

                if self._shutdown:
                    break

        except KeyboardInterrupt:
            _log("Interrupted")
        except EOFError:
            _log("stdin closed")
        except Exception as e:
            _log(f"Fatal: {e}")
            traceback.print_exc(file=sys.stderr)
        finally:
            self.close()
            _log("mcptoon serve stopped")

    def _respond(self, response: dict):
        """Send a response and remember it for in-process callers/tests."""
        self._last_response = response
        _send_response(response)

    def handle_request(self, request: dict) -> dict | None:
        """Process one JSON-RPC request; return its response (None = no reply).

        Delivery is unchanged (_send_response still runs), so stdio and HTTP
        modes behave exactly as before. Returns the response for convenience.
        """
        self._last_response = None
        self._handle_request(request)
        return self._last_response

    def _handle_request(self, request: dict):
        """Dispatch a single JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})
        if not isinstance(params, dict):
            params = {}

        # Notification (no id) — don't respond
        if req_id is None:
            if method == "notifications/initialized":
                _log("Client initialized notification received")
            return

        # 2026-07-28 GA: requests are self-describing. A _meta protocolVersion
        # we cannot speak is rejected up front (UnsupportedProtocolVersionError).
        meta = params.get("_meta")
        if isinstance(meta, dict):
            meta_version = meta.get(_META_PROTOCOL_KEY) or meta.get("protocolVersion")
            if meta_version and meta_version not in SUPPORTED_PROTOCOL_VERSIONS:
                self._respond(_make_error_response(
                    req_id,
                    ERR_UNSUPPORTED_PROTOCOL_VERSION,
                    f"Unsupported protocol version: {meta_version}",
                ))
                return

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
                self._respond(_make_success(req_id, result))
            elif method == "server/discover":
                result = self._handle_discover()
                self._respond(_make_success(req_id, result))
            elif method == "tools/list":
                result = self._handle_list_tools(params)
                self._respond(_make_success(req_id, result))
            elif method == "tools/call":
                result = self._handle_call_tool(params)
                self._respond(_make_success(req_id, result))
            elif method == "ping":
                self._respond(_make_success(req_id, {"resultType": "complete"}))
            elif method == "resources/list":
                result = self._handle_list_resources()
                self._respond(_make_success(req_id, result))
            elif method == "resources/read":
                self._respond(_make_success(
                    req_id,
                    {"contents": [], **_list_cache_fields()},
                ))
            elif method == "prompts/list":
                result = self._handle_list_prompts()
                self._respond(_make_success(req_id, result))
            elif method == "prompts/get":
                result = self._handle_get_prompt(params)
                if result is None:
                    self._respond(_make_error_response(
                        req_id, -32602, "Unknown prompt"))
                else:
                    self._respond(_make_success(req_id, result))
            elif method == "logging/setLevel":
                _log(f"Client set logging level: {params.get('level', 'info')}")
                self._respond(_make_success(req_id, {}))
            elif method == "health":
                result = self._handle_health()
                result["resultType"] = "complete"
                self._respond(_make_success(req_id, result))
            else:
                self._respond(_make_error_response(req_id, -32601, f"Method not found: {method}"))
        except MCPError as e:
            self._respond(_make_error_response(req_id, -32603, f"[{e.code}] {e.message}"))
        except Exception as e:
            self._respond(_make_error_response(req_id, -32603, str(e)[:200]))

        if method == "shutdown":
            self._shutdown = True

    # ═══════════════════════════════════════════════════
    # MCP Method Handlers
    # ═══════════════════════════════════════════════════

    def _handle_initialize(self, params: dict) -> dict:
        """Respond to the (legacy) initialize handshake.

        2026-07-28 removed the handshake from the protocol — the bridge no
        longer requires it — but pre-GA clients still send it, so it keeps
        working. A requested version we support is echoed back; anything
        else gets the legacy default.
        """
        _log(f"Initialize from client: {params.get('clientInfo', {})}")
        # Remember who is driving us, so the activity ledger and `status` can say
        # "last used by Cursor, 2 minutes ago" instead of only counting calls. The
        # MCP handshake carries the client's self-reported name; a client that
        # omits it leaves the host unknown (never guessed). Best-effort: an
        # unknown client must not break the handshake it is reporting in.
        try:
            _ci = params.get("clientInfo")
            if isinstance(_ci, dict):
                usage.set_host(_ci.get("name") or _ci.get("title"))
                # Remember it for the flood guard's per-agent bucketing.
                self._client_name = _ci.get("name") or _ci.get("title") or ""
        except Exception:
            pass
        client_version = params.get("protocolVersion", PROTOCOL_VERSION)
        version = (
            client_version
            if client_version in SUPPORTED_PROTOCOL_VERSIONS
            else PROTOCOL_VERSION
        )
        result = {
            "protocolVersion": version,
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
                # 2026-07-28: capabilities carry an extensions field
                "extensions": {},
            },
            "serverInfo": _SERVER_INFO,
            "resultType": "complete",
        }
        # The gateway's one line of voice. `instructions` is the protocol's
        # official channel for a server to brief the model, so every client that
        # honours it learns what mcptoon is without anyone editing a system
        # prompt. Kept to one sentence plus one imperative: it costs context on
        # every turn, which is the very thing this tool exists to save.
        #
        # The two directives are assembled separately on purpose. The savings-line
        # duty (`_INSTRUCTIONS`) is the footer's business and goes away with
        # `footer off`. Where the upstream tools went is NOT the footer's business:
        # under `exposure=compact` that directive is the only thing standing between
        # the model and "the user's MCP servers are gone". Tying it to the footer
        # flag would silently remove the tools a second time.
        directives = []
        if config.footer_enabled():
            directives.append(_INSTRUCTIONS)
        if config.compact_exposure():
            directives.append(_COMPACT_TOOLS_DIRECTIVE)
        if directives:
            result["instructions"] = "\n\n".join(directives)
        return result

    def _handle_discover(self) -> dict:
        """server/discover (2026-07-28): advertise versions/capabilities/identity.

        Clients MAY call this before any other request for up-front version
        selection. Cheap by design: no config load, no server startup.
        """
        return {
            "protocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
                "extensions": {},
            },
            "serverInfo": dict(_SERVER_INFO),
            "resultType": "complete",
        }

    def _handle_list_resources(self) -> dict:
        """resources/list: the bridge exposes no resources (empty, cached)."""
        result = {"resources": []}
        result.update(_list_cache_fields())
        result["resultType"] = "complete"
        return result

    def _handle_health(self) -> dict:
        """Health check endpoint — honestly reports status."""
        if not self._initialized:
            return {
                "status": "starting",
                "version": __version__,
                "servers": 0,
                "tools": 0,
            }
        total_tools = len(self._tool_index)
        total_servers = len(self._servers)
        # "Failed" means the fetch raised, tracked in `_server_fetch_errors` — not
        # merely "absent from `_tool_index`", which is also true of a server that
        # connects and legitimately exposes no tools. Inferring failure from the
        # index made one alive-but-empty server report `status: "error"`.
        failed = len(self._server_fetch_errors)
        if failed > 0 and failed == total_servers:
            status = "error"
        elif failed > 0:
            status = "degraded"
        else:
            status = "ok"
        payload = {
            "status": status,
            "version": __version__,
            "servers": total_servers,
            "tools": total_tools,
            "failed_servers": failed,
            "uptime": time.time() - getattr(self, "_start_time", time.time()),
        }
        if failed:
            payload["errors"] = dict(self._server_fetch_errors)
        return payload

    # ═══════════════════════════════════════════════════
    # Plugin skills as MCP prompts (v0.7.2)
    # ═══════════════════════════════════════════════════

    def _build_prompts_index(self):
        """Index installed Agent Plugin skills as MCP prompts.

        Layout: <plugins_dir>/<plugin>/skills/<skill>/SKILL.md. Prompt names
        are namespaced as "plugin_skill" for consistency with tool
        namespacing. Failures never break serve — a broken skill is skipped.
        """
        from .plugin import _plugins_dir, parse_skill_md

        root = _plugins_dir()
        if not root.is_dir():
            return
        for skill_md in sorted(root.glob("*/skills/*/SKILL.md")):
            try:
                name, description, body = parse_skill_md(skill_md)
            except OSError:
                continue
            if not name:
                name = skill_md.parts[-2]  # fall back to the skill dir name
            plugin = skill_md.parts[-4]  # .../<plugin>/skills/<skill>/SKILL.md
            prompt_name = f"{plugin}_{name}"
            self._prompts_index[prompt_name] = {
                "path": str(skill_md),
                "description": description[:200],
                "body": body,
            }

    def _handle_list_prompts(self) -> dict:
        """prompts/list: Agent Plugin skills exposed as prompts."""
        self._ensure_initialized()
        prompts = [
            {
                "name": name,
                "description": info.get("description", ""),
            }
            for name, info in sorted(self._prompts_index.items())
        ]
        _log(f"prompts/list: returning {len(prompts)} plugin skill prompts")
        result = {"prompts": prompts}
        result.update(_list_cache_fields())
        result["resultType"] = "complete"
        return result

    def _handle_get_prompt(self, params: dict) -> dict | None:
        """prompts/get: return the skill's markdown as one user message."""
        from .plugin import parse_skill_md

        self._ensure_initialized()
        name = str(params.get("name", ""))
        info = self._prompts_index.get(name)
        if info is None:
            return None
        # Re-read from disk: skills are static per install, but re-reading
        # keeps serve honest after a `plugin install` while serving.
        try:
            _, _, body = parse_skill_md(Path(info["path"]))
        except OSError:
            body = info.get("body", "")
        # v0.7.3: prompts were previously returned unscanned — a poisoned
        # SKILL.md could inject instructions straight into the agent context.
        # Run the same heuristic the tool-result path uses, under the same
        # switch: a host that turned the screen off (`config set guard off` /
        # MCPTOON_NO_GUARD=1) does not expect the *other* path to keep blocking
        # (issue #60 asked for exactly one switch that covers both).
        if router_mod.guard_active():
            poison = router_mod._check_poisoning(body)
            if poison:
                raise MCPError(-32003, f"prompt blocked: {poison}"
                                       f"{router_mod._GUARD_HINT}")
        return {
            "description": info.get("description", ""),
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": body},
                }
            ],
        }

    def _handle_list_tools(self, params: dict) -> dict:
        """Return the gateway's tool list.

        Two exposure presets (CONTEXT.md: "Tool Exposure Preset", ADR 0012):

        * ``compact`` (default) — mcptoon's own tools only. Upstream tools stay
          reachable (`mcptoon_manifest` names them, `mcptoon_call` runs them) but
          are not enumerated, which is what makes the gateway cost ~2.0k tokens
          per turn instead of ~18.0k. This is the "compact manifest" ADR 0004
          promised: "Claude Code 只看到 1 个 MCP server".
        * ``full`` — also list every upstream tool with a simplified schema
          (ADR 0006 layered schema). The pre-2026-09-25 behavior, kept as the
          fallback for a host whose tool panel reads this list, or a model that
          will not ask for the manifest.

        Each tool name is namespaced: {server}_{tool} (ADR 0007).
        Thread-safe: reads from _tool_index under RLock.
        """
        self._ensure_initialized()

        compact = config.compact_exposure()

        with self._tool_index_lock:
            tools: list[dict] = []
            if not compact:
                for ns_name, info in sorted(self._tool_index.items()):
                    full_def = info.get("full_def", {})
                    simplified = simplify_tool_def(full_def)
                    simplified["name"] = ns_name  # Override with namespaced name
                    tools.append(simplified)

            # First-party tools: published even with zero upstream servers, so a
            # gateway launched in a clean environment never reports an empty catalog
            # (a directory crawler or client that just started us would otherwise see
            # a tool-less server and have nothing to evaluate). An upstream tool that
            # happens to claim the same namespaced name wins — we skip ours.
            # Under `compact` these are the whole list, which is exactly why the
            # initialize directive has to say where the upstream tools went.
            for defn in native_tools.native_tools():
                if defn["name"] in self._tool_index:
                    continue
                tools.append(simplify_tool_def(defn))

        _log(f"tools/list: returning {len(tools)} tools "
             f"(exposure={'compact' if compact else 'full'})")
        # SEP-2549 CacheableResult + GA resultType on list results
        result = {"tools": tools}
        result.update(_list_cache_fields())
        result["resultType"] = "complete"
        return result

    def _native_state(self) -> dict:
        """Read-only snapshot of bridge state for the first-party tools."""
        with self._tool_index_lock:
            index = dict(self._tool_index)
            fetch_errors = dict(getattr(self, "_server_fetch_errors", {}) or {})
        return {
            "servers": self._servers or {},
            "tool_index": index,
            # The *authoritative* failure signal: a server whose fetch raised. The
            # native health tool must use this, not "absent from tool_index" — that
            # is also true of a healthy server that exposes no tools, and inferring
            # failure from the index made one alive-but-empty server report error.
            "fetch_errors": fetch_errors,
            "output_format": self._output_format,
            "initialized": self._initialized,
            "uptime": time.time() - getattr(self, "_start_time", time.time()),
        }

    def _throttle_search(self, name: str) -> dict | None:
        """Apply the per-agent flood guard to the gateway's search tools.

        Returns a tool result to send *instead of* running the tool when the call
        is blocked, or None to let it proceed. Only the search-shaped tools are
        throttled — throttling `mcptoon_manifest` would punish ordinary discovery,
        which is the opposite of what the gateway is for.

        The bucket key is the calling agent context. A stdio bridge serves one
        client, so ``clientInfo`` name plus thread identity is the honest
        granularity available; it keeps a fan-out of subagents from sharing one
        budget (the bug that made a legitimate 10-agent × 2-call fan-out look like
        a flood in the project this guard is modelled on).
        """
        if name not in ("mcptoon_kb_search", "mcptoon_resolve_skills"):
            return None
        key = f"{getattr(self, '_client_name', '') or 'unknown'}:{threading.get_ident()}"
        guard = getattr(self, "_flood", None)
        if guard is None:
            # A bridge built by a test double may skip __init__; create the guard
            # on first use rather than assuming construction ran.
            from .floodguard import FloodGuard
            guard = self._flood = FloodGuard()
        decision = guard.record(key, int(time.time() * 1000))
        if decision.blocked:
            return _make_tool_error(decision.message(name))
        if decision.soft_capped:
            # Soft cap is advisory: the tool still runs, but the caller is told
            # the budget is thinning so it can batch instead of piling on.
            self._last_throttle_note = decision.message(name)
        return None

    def _handle_call_tool(self, params: dict) -> dict:
        """Route a tool call to the underlying server (ADR 0004).

        Thread-safe: reads from _tool_index under RLock.
        Timeout: 30s default, configurable via MCPTOON_CALL_TIMEOUT.
        """
        self._ensure_initialized()

        name = params.get("name", "")
        arguments = params.get("arguments", {})

        # First-party tools are answered by the gateway itself, no upstream needed.
        # Skipped if an upstream tool owns that name (upstream always wins).
        # Stamped like a proxied result: the gateway's own tools are what an agent
        # reaches for first, so leaving them out would mean a client that only ever
        # calls `mcptoon_manifest` never sees the line at all.
        if native_tools.is_native(name):
            with self._tool_index_lock:
                owned_upstream = name in self._tool_index
            if not owned_upstream:
                if name == "mcptoon_call":
                    # The bridge's own escape hatch for `exposure=compact`: unwrap
                    # {name, arguments} and re-enter the very path a direct call
                    # takes, so validation, danger checks, compression and usage
                    # tracking are shared rather than duplicated. This is what makes
                    # withholding the tool list safe — the listing is gone, the
                    # capability is not.
                    inner = arguments if isinstance(arguments, dict) else {}
                    target = inner.get("name", "")
                    target = target.strip() if isinstance(target, str) else ""
                    if not target:
                        return _make_tool_error(
                            "mcptoon_call needs `name` — the namespaced upstream tool to "
                            "run (server_tool, e.g. fetch_fetch). Call mcptoon_manifest "
                            "to list what is loaded.")
                    if target == "mcptoon_call":
                        return _make_tool_error(
                            "mcptoon_call cannot call itself; pass the upstream tool name.")
                    target_args = inner.get("arguments", {})
                    if not isinstance(target_args, dict):
                        target_args = {}
                    return self._wrap_call_envelope(
                        target,
                        self._handle_call_tool({"name": target, "arguments": target_args}))
                guard = self._throttle_search(name)
                if guard is not None:
                    return guard
                return self._stamp_footer(
                    self._track_native(name, native_tools.call_native(
                        name, arguments, self._native_state())))
        elif name.startswith("mcptoon_"):
            # Reserved prefix, but not one of ours: say so plainly instead of
            # letting split_namespaced misread "mcptoon" as a server name.
            with self._tool_index_lock:
                owned = name in self._tool_index or any(
                    i.get("tool") == name for i in self._tool_index.values())
            if not owned:
                return _make_tool_error(
                    f"Unknown tool: '{name}'. The 'mcptoon_' prefix is reserved for the "
                    f"gateway's own tools: {', '.join(native_tools.NATIVE_NAMES)}. "
                    f"Upstream tools look like <server>_<tool> (e.g. fetch_fetch); "
                    f"call mcptoon_manifest to list what is loaded."
                )

        # Split namespaced name
        known_servers = list(self._servers.keys()) if self._servers else []
        server, tool = split_namespaced(name, known_servers)

        if not server:
            # Try fuzzy: maybe the agent called just the tool name
            with self._tool_index_lock:
                server = _find_server_for_tool(name, self._tool_index)
            tool = name if server else tool

        if not server or not tool:
            with self._tool_index_lock:
                available = list(self._tool_index.keys())[:10]
            return _make_tool_error(
                f"Unknown tool: '{name}'. "
                f"Use namespaced format: server_tool (e.g. fetch_fetch). "
                f"Available: {', '.join(available)}..."
            )

        # Resolve server name (handles aliases)
        server = resolve_server_name(server)

        # Validate args against full schema
        with self._tool_index_lock:
            info = self._tool_index.get(name)
        annotations = None
        if info:
            full_schema = info.get("full_schema", {})
            full_def = info.get("full_def") or {}
            if isinstance(full_def, dict):
                ann = full_def.get("annotations")
                if isinstance(ann, dict):
                    annotations = ann
            errors = validate_args(arguments, full_schema)
            if errors:
                return _make_tool_error(
                    f"Parameter validation failed: {'; '.join(errors)}"
                )

        # Safety checks via router (pass in-memory annotations so a readOnlyHint
        # clears a name false-positive and a destructiveHint blocks a neutral name)
        danger = router_mod._check_dangerous(server, tool, arguments, annotations)
        if danger:
            return _make_tool_error(
                f"Blocked: {danger}. Use CLI with --destructive to override."
            )

        # Route to underlying server (with timeout)
        _t0 = time.monotonic()
        try:
            if not self._pool:
                self._pool = MCPClientPool(self._servers, timeout=_get_call_timeout())

            # Call with timeout. Keep the full envelope, not just the extracted
            # payload: a tool that advertises an outputSchema in tools/list MUST
            # answer with matching structuredContent, or a strict client rejects
            # the whole result (issue #22). call() would unwrap that away.
            call_timeout = _get_call_timeout()
            envelope = self._call_with_timeout(self._pool, server, tool, arguments, call_timeout)

            # Usage accounting and --format compression still run on the payload
            # view, exactly as before — no reported number changes.
            payload = _unwrap_envelope(envelope)
            usage.track_call(server, tool, ok=True, payload=payload,
                             ms=int((time.monotonic() - _t0) * 1000))
            self._log_event(server, tool, arguments, ok=True)

            if isinstance(envelope, dict) and envelope.get("structuredContent") is not None:
                # Build the response from the envelope explicitly. Passing the
                # payload to _make_tool_result() would misread one that carries a
                # "content" key (filesystem's list_directory declares exactly that)
                # as an already-wrapped result and return that same object, so
                # attaching structuredContent would nest the result inside itself.
                result = dict(envelope)
                compressed = self._compress_result(payload, server, tool)
                if compressed is not payload or not isinstance(result.get("content"), list):
                    # A compression format re-renders the text view; otherwise keep
                    # the upstream content blocks and only synthesise them if absent.
                    result["content"] = [{"type": "text", "text": (
                        compressed if isinstance(compressed, str)
                        else json.dumps(compressed, ensure_ascii=False))}]
                result.setdefault("isError", False)
                result.setdefault("resultType", "complete")
            else:
                result = _make_tool_result(self._compress_result(payload, server, tool))

            return self._stamp_footer(result)

        except MCPError as e:
            usage.track_call(server, tool, ok=False,
                             err=f"{e.code}: {str(e.message)[:160]}",
                             ms=int((time.monotonic() - _t0) * 1000))
            self._log_event(server, tool, arguments, ok=False)
            return _make_tool_error(f"[{e.code}] {e.message}")
        except concurrent.futures.TimeoutError:
            usage.track_call(server, tool, ok=False,
                             err=f"timeout after {_get_call_timeout()}s",
                             ms=int((time.monotonic() - _t0) * 1000))
            self._log_event(server, tool, arguments, ok=False)
            return _make_tool_error(f"Call timed out after {_get_call_timeout()}s")
        except Exception as e:
            usage.track_call(server, tool, ok=False,
                             err=f"{type(e).__name__}: {str(e)[:160]}",
                             ms=int((time.monotonic() - _t0) * 1000))
            self._log_event(server, tool, arguments, ok=False)
            return _make_tool_error(f"Call failed: {str(e)[:200]}")

    def _wrap_call_envelope(self, target: str, result: dict) -> dict:
        """Wrap a routed answer in the shape `mcptoon_call` advertises.

        `mcptoon_call` declares an outputSchema requiring `tool` and `server`, but
        the escape hatch re-enters the direct-call path and returned that path's
        envelope verbatim — so when the upstream tool answered with its own
        structuredContent (``{"entities": [], "relations": []}`` and the like), a
        strict client rejected every such call: the response did not match the
        schema the gateway itself published (issue #33, a side effect of #22).

        This rebuilds ``{tool, server, result}`` from whatever the routed call
        produced, so the declared schema is always satisfied:

        * success with structuredContent -> ``result`` is that structuredContent,
          and the upstream text view is kept as the content block;
        * success without it -> ``result`` is the unwrapped payload;
        * a routed failure (bad args, danger block, timeout, unknown tool) ->
          ``isError`` stays true (the failure is still reported) and ``result``
          carries the error text, so even an error answer matches the schema.

        It wraps, it does not re-run: validation, danger checks, compression,
        usage accounting and the footer stamp all already happened inside the
        routed call and are preserved here.
        """
        server = ""
        tool = target
        with self._tool_index_lock:
            info = self._tool_index.get(target)
        if info:
            server = info.get("server", "") or ""
            tool = info.get("tool", target) or target
        else:
            known = list(self._servers.keys()) if self._servers else []
            server, split_tool = split_namespaced(target, known)
            tool = split_tool or target

        failed = bool(isinstance(result, dict) and result.get("isError"))
        structured = result.get("structuredContent") if isinstance(result, dict) else None
        if structured is None:
            if failed:
                # No upstream payload to expose; surface the error text as the
                # wrapped result rather than inventing an empty object.
                text = _error_text(result)
                structured = {"error": text} if text else {}
            else:
                structured = _unwrap_envelope(result)

        wrapped = {"tool": tool, "server": server, "result": structured}

        out: dict = {
            "structuredContent": wrapped,
            "isError": failed,
            "resultType": "complete",
        }
        if isinstance(result, dict) and isinstance(result.get("content"), list):
            out["content"] = result["content"]
        else:
            out["content"] = [{"type": "text", "text": json.dumps(
                structured, ensure_ascii=False)}]
        return out

    def _log_event(self, server: str, tool: str, arguments: Any, ok: bool) -> None:
        """Record one routed call in the per-project session log.

        Best-effort and never raises: the log is a convenience for catching up
        after a compaction, and must not be able to fail the call it is logging.
        """
        try:
            from . import session_log
            session_log.record(server, tool, arguments, ok=ok)
        except Exception:
            pass

    def _call_with_timeout(
        self, pool: MCPClientPool, server: str, tool: str,
        arguments: dict, timeout: int,
    ) -> Any:
        """Execute a tool call with a timeout in a worker thread.

        This prevents a single hung MCP server from blocking the entire bridge.
        On timeout, the thread is abandoned (daemon) but the subprocess is killed.
        """
        result_container = []
        error_container = []
        event = threading.Event()
        worker_thread = [None]  # Store reference for cleanup

        def _worker():
            t = threading.current_thread()
            worker_thread[0] = t
            try:
                r = _call_pool_full(pool, server, tool, arguments)
                result_container.append(r)
            except Exception as e:
                error_container.append(e)
            finally:
                event.set()

        t = threading.Thread(target=_worker, daemon=True, name=f"mcptoon-call-{server}-{tool}")
        t.start()

        if not event.wait(timeout=timeout):
            # Timeout — try to kill the underlying subprocess if possible
            # This is best-effort since the thread is stuck in I/O
            try:
                client = pool._clients.get(server)
                if client and client._proc:
                    client._proc.kill()
            except Exception:
                pass
            raise concurrent.futures.TimeoutError(f"Tool call timed out after {timeout}s")

        if error_container:
            raise error_container[0]
        return result_container[0] if result_container else None

    # ═══════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════

    def _track_native(self, name: str, payload: dict) -> dict:
        """Record a gateway-native tool call in the activity ledger.

        The gateway's own tools (`mcptoon_resolve_skills`, `_manifest`, `_inspect`,
        `_call`, `_skills`) are the ones an agent reaches for first — and
        `mcptoon_resolve_skills` is the *skill-distribution* moment this whole
        presence channel exists to make visible. They are answered in-bridge, never
        through the router, so `usage.track_call` in `_handle_call_tool`'s upstream
        path never sees them: before this, a session that only ever distributed
        skills left the activity ledger empty, i.e. the single most important "was I
        used" event was invisible.

        Counted under the reserved server name ``mcptoon`` so `activity` and
        `status` can tell a gateway tool from an upstream one. `payload` is the
        result; errors are recorded as errors like any other call. Never raises —
        presence accounting must not break the tool it is recording.

        Also the place the one-per-session **skill-delivery banner** is attached
        (`_maybe_skill_banner`): the moment `mcptoon_resolve_skills` actually hands
        an agent some skills is the "mcptoon is distributing your capabilities"
        event the presence channel exists to surface, and it is otherwise invisible
        to the user.
        """
        try:
            is_err = bool(isinstance(payload, dict) and payload.get("isError"))
            detail = None
            err = None
            if is_err:
                # Pull the short reason off the error payload so `activity` can
                # say *why* a native call is red, not just that it is.
                try:
                    blocks = payload.get("content") or []
                    txt = blocks[0].get("text", "") if blocks else ""
                    err = str(txt)[:160] or "native tool error"
                except Exception:
                    err = "native tool error"
            if name == "mcptoon_resolve_skills" and not is_err:
                # Record *which* skills were distributed, not just that the tool
                # ran: "distributing your capabilities" is only meaningful if the
                # ledger names the capabilities. Slugs only, capped, best-effort.
                shortlist = (payload.get("structuredContent") or {}).get("shortlist")
                if isinstance(shortlist, list) and shortlist:
                    slugs = [str(s.get("slug")) for s in shortlist
                             if isinstance(s, dict) and s.get("slug")]
                    if slugs:
                        detail = "distributed: " + ", ".join(slugs)
            usage.track_call("mcptoon", name, ok=not is_err, payload=payload,
                             detail=detail, err=err)
        except Exception:
            pass
        if name == "mcptoon_resolve_skills":
            payload = self._maybe_skill_banner(payload)
        return payload

    def _maybe_skill_banner(self, payload: dict) -> dict:
        """Attach a one-line 'delivered N skills' notice to the first skill resolve.

        Once per session (``self._skill_banner_done``), only when the resolve
        actually surfaced skills, only when presence is on, and never on an error.
        This is best-effort presence: a GUI host may fold the tool result so the
        user never sees it (Claude Desktop issue #22127) — the durable record is
        the activity ledger, not this line. It costs a few tokens once, and the
        payload is otherwise untouched.
        """
        if getattr(self, "_skill_banner_done", False):
            return payload
        try:
            from . import config as _cfg
            if not _cfg.presence_enabled():
                return payload
            if not isinstance(payload, dict) or payload.get("isError"):
                return payload
            shortlist = payload.get("structuredContent", {}).get("shortlist")
            if not isinstance(shortlist, list) or not shortlist:
                return payload
            content = payload.get("content")
            if not isinstance(content, list):
                return payload
            n = len(shortlist)
            noun = "skill" if n == 1 else "skills"
            content.append({
                "type": "text",
                "text": (f"▸ mcptoon distributed {n} {noun} for this task "
                         f"(see `mcptoon activity`)"),
            })
            self._skill_banner_done = True
        except Exception:
            return payload
        return payload

    def _stamp_footer(self, payload: dict) -> dict:
        """Append the savings line to the first successful result of a session.

        This is the MCP half of the universal-surface design in the `footer`
        module. The gateway routes every call, so `_make_tool_result` is the one
        funnel all of them pass through — stamping there reaches Claude Desktop,
        Cursor, Cline, Windsurf, VS Code Copilot and any other client with no
        per-client configuration, and it rides the protocol payload rather than a
        prompt, so the effect does not depend on the model cooperating.

        **Once per session, not once per call.** The block costs ~32 tokens on
        the tiktoken cl100k_base caliber while a full catalog compression saves
        ~5,200, so stamping every result would break even at ~162 calls — a
        feature that can eat the savings it advertises is not a feature. One
        stamp per session, plus the handshake `instructions` and the CLI tail,
        is enough for the number to be on screen.

        Skipped for error payloads: the model already has a failure to react to,
        and a savings line there is noise.

        Also skipped when the line is byte-identical to the one already shown
        (`footer.changed`): a repeat adds nothing the transcript does not already
        carry, and the whole complaint this round addresses is a line that says
        the same thing every turn. The once-per-session flag is still spent, so a
        session that opens with a repeat does not restamp later.
        """
        if getattr(self, "_footer_stamped", False):
            return payload
        try:
            from . import footer as footer_mod

            if not footer_mod.enabled() or payload.get("isError"):
                return payload
            content = payload.get("content")
            if not isinstance(content, list):
                return payload
            text = footer_mod.block()
            if footer_mod.changed(text):
                content.append({"type": "text", "text": text})
                footer_mod.remember(text)
            self._footer_stamped = True
        except Exception:
            return payload
        return payload

    def _compress_result(self, result: Any, server: str, tool: str) -> Any:
        """Compress tool call result based on output format.

        A per-tool compression policy (mcptoon policy) wins over the
        bridge-wide format: "raw"/"json" protects results that must not be
        compressed (images, base64 payloads), a specific format forces a
        shape for one chatty tool without touching the rest.
        """
        effective = self._output_format
        try:
            from . import config as _cfg
            effective = _cfg.resolve_output_format(server, tool, effective)
        except Exception:
            pass

        if effective in ("raw", "json", "auto"):
            return result

        if effective == "smart":
            return self._smart_compress(result, server, tool)

        try:
            from . import output as output_mod
            compressed = output_mod.render(result, fmt=effective)
            if compressed is not None:
                return compressed
        except Exception:
            pass

        return result

    def _smart_compress(self, result: Any, server: str, tool: str) -> Any:
        """Structure-aware compression + CCR (see compressor.py / ccr.py).

        The compressed payload is the summary; the *original* goes to the CCR
        store and its handle rides along in a one-line notice, so a model that
        needs a dropped detail can call ``mcptoon_retrieve`` instead of being
        stuck. A result that was not shrunk is returned untouched. A result that
        *was* shrunk but could not be stored still comes back compressed — with a
        notice that says so — because the one thing this path must never produce
        is a trimmed view with no way back and no explanation.
        """
        try:
            from . import compressor as _compressor
            text, _stats = _compressor.compress_with_ccr(result, server=server, tool=tool)
            return text if text is not None else result
        except Exception:
            return result


# ═══════════════════════════════════════════════════
# JSON-RPC helpers
# ═══════════════════════════════════════════════════

def _make_success(req_id, result: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


def _make_error_response(req_id, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _call_pool_full(pool: Any, server: str, tool: str, arguments: Any) -> Any:
    """Call a tool and return the complete MCP tools/call result envelope.

    Prefers ``pool.call_full`` (keeps structuredContent, _meta, resultType,
    isError, content). Falls back to ``pool.call`` for pools that predate it, so
    a duck-typed or older pool keeps working.
    """
    call_full = getattr(pool, "call_full", None)
    if callable(call_full):
        return call_full(server, tool, arguments)
    return pool.call(server, tool, arguments)


def _unwrap_envelope(envelope: Any) -> Any:
    """Reduce a tools/call envelope to the payload ``pool.call`` used to return.

    ``pool.call`` is ``_extract_content(pool.call_full(...))`` by construction, so
    this keeps usage accounting and --format compression seeing exactly the value
    they saw before the envelope was preserved. Non-dict inputs pass straight
    through (e.g. the legacy fallback pool, which already returns a payload).
    """
    if isinstance(envelope, dict) and ("content" in envelope or "structuredContent" in envelope):
        return MCPClient._extract_content(envelope)
    return envelope


def _make_tool_result(content: Any) -> dict:
    """Format a successful tool result as MCP content response."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Already MCP content array format
        return {"content": content, "isError": False, "resultType": "complete"}
    elif isinstance(content, dict) and "content" in content:
        # Already wrapped
        return content
    else:
        text = json.dumps(content, ensure_ascii=False) if content is not None else "null"

    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
        "resultType": "complete",
    }


def _make_tool_error(message: str) -> dict:
    """Format a tool error as MCP content response."""
    return {
        "content": [{"type": "text", "text": f"Error: {message}"}],
        "isError": True,
        "resultType": "complete",
    }


def _error_text(result: Any) -> str:
    """Pull the human-readable message out of a routed error result."""
    if not isinstance(result, dict):
        return str(result) if result else ""
    for block in result.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            return block["text"]
    return ""

def _find_server_for_tool(tool_name: str, tool_index: dict) -> str:
    """Try to find which server owns a tool by name (fuzzy fallback)."""
    for ns_name, info in tool_index.items():
        if info["tool"] == tool_name:
            return info["server"]
    return ""


import io

# Thread-local storage for response capture (fixes concurrency race condition)
_response_capture = threading.local()


def _send_response(response: dict):
    """Send a JSON-RPC response.

    In stdio mode: writes to stdout.
    In HTTP mode: writes to thread-local capture buffer (set by do_POST).
    """
    data = json.dumps(response, ensure_ascii=False)

    # Check if we're in HTTP capture mode (thread-local)
    capture_buf = getattr(_response_capture, "buf", None)
    if capture_buf is not None:
        capture_buf.write(data + "\n")
        return

    # Stdio mode: write to stdout
    try:
        sys.stdout.write(data + "\n")
        sys.stdout.flush()
    except Exception as e:
        _log(f"Failed to send response: {e}")


def _log(msg: str):
    """Log to stderr (stdout is reserved for JSON-RPC protocol)."""
    sys.stderr.write(f"[mcptoon serve] {msg}\n")
    sys.stderr.flush()


def _get_call_timeout() -> int:
    """Get the configured timeout for tool calls.

    Delegates to client.default_call_timeout() so the gateway and the CLI can
    never disagree about MCPTOON_CALL_TIMEOUT (issue #34).
    """
    return int(default_call_timeout())


# ═══════════════════════════════════════════════════
# Background / persistent serve mode
# ═══════════════════════════════════════════════════

# `serve` in the foreground dies when the terminal closes, which is the single
# biggest reason a "try it once" never becomes "runs on my machine every day".
# `--background` detaches it: the process survives the shell, pid + log land under
# the mcptoon state dir, and `--status`/`--stop` manage it. Auto-start on login is
# left to the OS (Windows: a Startup shortcut; POSIX: launchd/systemd — the exact
# command is printed so the user wires the one they use).

_BG_PID = config.STATE_DIR / "serve.pid"
_BG_LOG = config.LOG_DIR / "serve.log"


def _bg_paths():
    """(pid_file, log_file), resolved at call time so a --dir override is honoured."""
    return config.STATE_DIR / "serve.pid", config.LOG_DIR / "serve.log"


def _pid_alive(pid: int) -> bool:
    """True if a process with this pid exists. Cross-platform, no psutil.

    CRITICAL (Windows): ``os.kill(pid, 0)`` does NOT probe on Windows — its
    Windows implementation calls ``TerminateProcess``, so a "liveness check"
    would KILL the process. (This actually took down an unrelated node process
    during development.) On Windows we open the handle with query-only rights
    and read its exit code instead; only POSIX gets the harmless ``kill(pid, 0)``.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return False  # gone, or access denied (treat as not-ours)
            try:
                code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        return getattr(e, "errno", None) == 1  # EPERM = alive but not ours
    except Exception:
        return False
    return True


def _proc_create_time(pid: int):
    """The process creation time (epoch seconds) as a float, or None.

    The identity check that makes ``--stop`` safe: a pid alone is not unique over
    time (Windows recycles them aggressively), so we record the creation time when
    we spawn and refuse to kill a pid whose creation time no longer matches.
    """
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME)]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return None
            try:
                ft = wintypes.FILETIME()
                if kernel32.GetProcessTimes(h, ctypes.byref(ft), ctypes.byref(wintypes.FILETIME()),
                                            ctypes.byref(wintypes.FILETIME()),
                                            ctypes.byref(wintypes.FILETIME())):
                    ticks = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
                    return ticks / 1e7 - 11644473600.0  # FILETIME epoch → Unix epoch
                return None
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            return None
    try:
        import subprocess as _sp
        out = _sp.run(["ps", "-o", "etimes=", "-p", str(pid)],
                      capture_output=True, text=True, encoding="utf-8", timeout=5).stdout.strip()
        if out.isdigit():
            return time.time() - int(out)
    except Exception:
        pass
    return None


def _write_pidfile(pid: int) -> None:
    """Record the spawned pid together with its creation time (identity)."""
    pid_file, _ = _bg_paths()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    rec = {"pid": pid, "created": _proc_create_time(pid)}
    pid_file.write_text(json.dumps(rec), encoding="utf-8")


def _read_pid():
    """Return the running background serve pid, or None (also clears a stale file).

    Only returns a pid we can still vouch for: it must be alive AND its creation
    time must match the one recorded at spawn. A recycled pid, a crash, or a
    reboot leaves a record we no longer trust, so we clear it and report None
    rather than hand ``--stop`` a pid that now belongs to something else.
    """
    pid_file, _ = _bg_paths()
    if not pid_file.exists():
        return None
    pid, created = -1, None
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
        try:
            rec = json.loads(raw)
        except ValueError:
            rec = raw  # not JSON at all; maybe a plain int or garbage
        if isinstance(rec, dict):
            pid = int(rec.get("pid", -1))
            created = rec.get("created")
        else:
            pid = int(rec)  # tolerate an old plain-int file ("4321" or 4321)
    except (ValueError, TypeError, OSError):
        pid = -1

    trusted = False
    if pid > 0 and _pid_alive(pid):
        if created is None:
            trusted = True  # old format, no identity: accept a live pid (best effort)
        else:
            now_created = _proc_create_time(pid)
            trusted = now_created is not None and abs(now_created - float(created)) < 2.0
    if trusted:
        return pid
    try:
        pid_file.unlink()
    except OSError:
        pass
    return None


def _tcp_probe(host: str, port: int, timeout: float = 0.25) -> bool:
    """True if something accepts a TCP connection at host:port right now."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _background_start(args: list[str], listen_addr: str | None) -> int:
    """Spawn a detached `serve` and write its pid. Returns a shell exit code."""
    pid_file, log_file = _bg_paths()
    existing = _read_pid()
    if existing:
        print(f"  mcptoon serve is already running in the background (pid {existing}).")
        print("  stop it first: mcptoon serve --stop")
        return 1

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Refuse early if the port is already taken. This is the common failure and,
    # checked before spawning, it is unambiguous: afterwards a successful connect
    # could be *someone else's* listener, not our child. (Windows lets a second
    # binder share a port when both set SO_REUSEADDR, so we cannot rely on the
    # child's own bind error being the first signal.)
    host, port = _parse_listen_addr(listen_addr)
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    if _tcp_probe(probe_host, port):
        print(f"  cannot start: {listen_addr} is already in use.")
        print("  pick another port with --listen host:port, or stop what is using it.")
        return 1

    # Re-run the same serve invocation in the child, minus the control flags, so
    # the detached process is byte-identical to the foreground one.
    child_args = [a for a in args
                  if a not in ("--background", "--daemon", "--start")
                  and not a.startswith("--install")]
    cmd = [sys.executable, "-m", "mcptoon", "serve", *child_args]

    popen_kw = {}
    if os.name == "nt":
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP: no console, survives the shell.
        popen_kw["creationflags"] = 0x00000008 | 0x00000200
    else:
        popen_kw["start_new_session"] = True  # setsid: survives the controlling terminal

    with open(log_file, "ab") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=log, close_fds=True, **popen_kw)

    # The port was free a moment ago, so a connect now means *our* child bound it.
    # Poll until it binds (fast) or dies / times out (fail) — never a hopeful guess.
    deadline = time.time() + 10.0
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        if _tcp_probe(probe_host, port):
            ready = True
            break
        time.sleep(0.1)
    if not ready or proc.poll() is not None:
        # Child exited, or never bound the port in time — the start failed.
        try:
            log_tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
        except OSError:
            log_tail = []
        print("  mcptoon serve failed to start — it did not bind "
              f"{listen_addr} (child exit code {proc.poll()}).")
        if log_tail:
            print(f"  last log lines ({log_file}):")
            for line in log_tail:
                print(f"    {line}")
        print("  hint: the port may already be in use — pick another with --listen host:port.")
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        return 1

    _write_pidfile(proc.pid)
    where = listen_addr or "stdio"
    print(f"  mcptoon serve started in the background (pid {proc.pid}, {where}).")
    print(f"  log: {log_file}")
    print("  status: mcptoon serve --status   ·   stop: mcptoon serve --stop")
    print()
    print("  to auto-start at login, run once:")
    print("    mcptoon serve --install-autostart --listen host:port")
    print("  (or add this to a Startup shortcut / scheduled task yourself:)")
    print(f"    {sys.executable} -m mcptoon serve{' ' + ' '.join(child_args) if child_args else ''}")
    return 0


_AUTOSTART_TASK = os.environ.get("MCPTOON_AUTOSTART_TASK", "mcptoon-serve")


def _autostart_command(args: list[str], listen_addr: str) -> list[str]:
    """The exact argv an autostart entry should run: a foreground serve."""
    child_args = [a for a in args
                  if a not in ("--background", "--daemon", "--start",
                               "--install-autostart", "--uninstall-autostart")
                  and not a.startswith("--install")]
    return [sys.executable, "-m", "mcptoon", "serve", *child_args]


def _install_autostart(args: list[str], listen_addr: str | None) -> int:
    """Register a login-time autostart for the serve command. Explicit, opt-in."""
    if not listen_addr:
        print("  --install-autostart needs an HTTP address: add --listen host:port.",
              file=sys.stderr)
        return 2
    cmd = _autostart_command(args, listen_addr)
    if os.name == "nt":
        # schtasks chokes on a /TR that embeds a spaced python path with inner
        # quotes, so write a tiny launcher next to the pid/log and point the task
        # at that single (space-free) path instead.
        state_dir = _bg_paths()[0].parent
        state_dir.mkdir(parents=True, exist_ok=True)
        launcher = state_dir / "serve-autostart.cmd"
        quoted = " ".join(f'"{a}"' if " " in a else a for a in cmd)
        launcher.write_text(f"@echo off\r\n{quoted}\r\n", encoding="utf-8")
        tr = (f'schtasks /Create /TN {_AUTOSTART_TASK} /SC ONLOGON /RL LIMITED '
              f'/TR "{launcher}" /F')
        res = subprocess.run(tr, shell=True, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(f"  could not create the scheduled task: {res.stderr.strip() or res.stdout.strip()}")
            return 1
        print(f"  autostart installed: Scheduled Task '{_AUTOSTART_TASK}' runs at logon.")
        print(f"    launcher: {launcher}")
        print(f"    command:  {quoted}")
        print("  remove it later with: mcptoon serve --uninstall-autostart")
        return 0
    # POSIX: write a systemd --user unit.
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit = unit_dir / f"{_AUTOSTART_TASK}.service"
    exec_start = " ".join(cmd)
    unit.write_text(
        "[Unit]\n"
        "Description=mcptoon serve (background MCP gateway)\n\n"
        "[Service]\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )
    print(f"  autostart unit written: {unit}")
    print(f"    enable it: systemctl --user enable --now {_AUTOSTART_TASK}.service")
    print("  remove it later with: mcptoon serve --uninstall-autostart")
    return 0


def _uninstall_autostart() -> int:
    """Remove whatever _install_autostart created. Idempotent."""
    if os.name == "nt":
        res = subprocess.run(["schtasks", "/Delete", "/TN", _AUTOSTART_TASK, "/F"],
                             capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            print(f"  no autostart task to remove (or removal failed): "
                  f"{res.stderr.strip() or res.stdout.strip()}")
            return 0
        launcher = _bg_paths()[0].parent / "serve-autostart.cmd"
        try:
            launcher.unlink()
        except OSError:
            pass
        print(f"  autostart removed: Scheduled Task '{_AUTOSTART_TASK}' deleted.")
        return 0
    unit = Path.home() / ".config" / "systemd" / "user" / f"{_AUTOSTART_TASK}.service"
    if unit.exists():
        try:
            unit.unlink()
        except OSError as e:
            print(f"  could not remove {unit}: {e}")
            return 1
        print(f"  autostart unit removed: {unit}")
        print(f"    (disable first if still enabled: systemctl --user disable {_AUTOSTART_TASK}.service)")
    else:
        print("  no autostart unit to remove.")
    return 0


def _background_status() -> int:
    pid_file, log_file = _bg_paths()
    pid = _read_pid()
    if not pid:
        print("  mcptoon serve is not running in the background.")
        return 0
    print(f"  mcptoon serve is running (pid {pid}).")
    if log_file.exists():
        try:
            tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        except OSError:
            tail = []
        if tail:
            print(f"  last log lines ({log_file}):")
            for line in tail:
                print(f"    {line}")
    return 0


def _background_stop() -> int:
    pid_file, _ = _bg_paths()
    pid = _read_pid()
    if not pid:
        print("  mcptoon serve is not running in the background — nothing to stop.")
        return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, check=False)
        else:
            os.kill(pid, 15)  # SIGTERM
    except Exception as e:
        print(f"  could not stop pid {pid}: {type(e).__name__}: {e}")
        return 1
    # Give it a moment, then clear the pid file regardless.
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    try:
        pid_file.unlink()
    except OSError:
        pass
    print(f"  mcptoon serve stopped (pid {pid}).")
    return 0


# ═══════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════


# Sentinel for `--auth` given without a value → token is generated at startup
# and printed to stderr exactly once (Jupyter-style). Value is a placeholder
# marker, never an actual credential.
_AUTO_TOKEN = "<auto>"


def _parse_serve_args(args: list[str]) -> tuple[str, str | None, str | None]:
    """Parse `mcptoon serve` arguments.

    Returns (output_format, listen_addr, auth_token).
    listen_addr None = stdio mode; auth_token _AUTO_TOKEN = generate at startup.
    """
    output_format = "auto"
    listen_addr = None  # None = stdio mode; "addr:port" = HTTP mode
    auth_token = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format" and i + 1 < len(args):
            output_format = args[i + 1]
            i += 1
        elif a.startswith("--format="):
            output_format = a.split("=", 1)[1]
        elif a in ("--toon",):
            output_format = "toon"
        elif a in ("--slim",):
            output_format = "slim"
        elif a in ("--compact",):
            output_format = "compact"
        elif a in ("--raw",):
            output_format = "raw"
        elif a in ("--json",):
            output_format = "json"
        elif a in ("--smart",):
            output_format = "smart"
        elif a == "--listen" and i + 1 < len(args):
            listen_addr = args[i + 1]
            i += 1
        elif a.startswith("--listen="):
            listen_addr = a.split("=", 1)[1]
        elif a == "--http":
            # `--http` is the shorthand for `--listen :8080`. But it used to ignore a
            # following address: `serve --background --http :18099` silently kept
            # :8080, then failed with "8080 is already in use" — never mentioning the
            # port the user actually asked for (measured 0.8.29). If the next token
            # looks like an address (":port" or "host:port"), consume it; otherwise
            # it is the documented bare shorthand.
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt is not None and not nxt.startswith("-") and ":" in nxt:
                listen_addr = nxt
                i += 1
            else:
                listen_addr = ":8080"
        elif a.startswith("--http="):
            listen_addr = a.split("=", 1)[1]
        elif a == "--auth":
            # v0.7.3: bare `--auth` (or followed by another flag) generates
            # a random token; `--auth <value>` sets it explicitly.
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt is None or nxt.startswith("--"):
                auth_token = _AUTO_TOKEN
            else:
                auth_token = nxt
                i += 1
        elif a.startswith("--auth="):
            v = a.split("=", 1)[1]
            auth_token = v if v else _AUTO_TOKEN
        elif a in ("-h", "--help"):
            _help_text = _serve_help()
            try:
                print(_help_text)
            except UnicodeEncodeError:
                # Windows cp1252 can't encode Unicode — fallback to UTF-8
                sys.stdout.buffer.write(_help_text.encode("utf-8"))
                sys.stdout.buffer.write(b"\n")
                sys.stdout.buffer.flush()
            sys.exit(0)
        i += 1

    return output_format, listen_addr, auth_token


def run_serve(args: list[str]):
    """Entry point for `mcptoon serve` command.

    Args:
        args: Command line args after 'serve'
              --format toon|slim|compact|smart|json|raw|auto  (default: auto)
              --listen <addr>  HTTP mode: listen on addr (e.g. :8080)
              --http            Shorthand for --listen :8080 (binds 127.0.0.1)
              --auth [token]    Bearer token; bare --auth generates one
              --background      Detach and run in the background (HTTP mode)
              --status          Report the background instance, then exit
              --stop            Stop the background instance, then exit
    """
    # Control flags are handled before _parse_serve_args so its documented
    # (format, listen, auth) contract stays exactly as tests pin it.
    if any(a == "--status" for a in args):
        sys.exit(_background_status())
    if any(a == "--stop" for a in args):
        sys.exit(_background_stop())
    if any(a == "--install-autostart" for a in args):
        _, _listen, _ = _parse_serve_args([a for a in args if a != "--install-autostart"])
        sys.exit(_install_autostart(args, _listen))
    if any(a == "--uninstall-autostart" for a in args):
        sys.exit(_uninstall_autostart())

    output_format, listen_addr, auth_token = _parse_serve_args(args)

    if any(a in ("--background", "--daemon", "--start") for a in args):
        if not listen_addr:
            # A detached stdio server has no reader — refuse rather than orphan it.
            print("  --background needs an HTTP address: use --background --http "
                  "(or --listen :8080).", file=sys.stderr)
            sys.exit(2)
        sys.exit(_background_start(args, listen_addr))

    bridge = MCPServerBridge(output_format=output_format)

    if listen_addr:
        _run_http(bridge, listen_addr, auth_token=auth_token)
    else:
        bridge.run()


# ═══════════════════════════════════════════════════
# HTTP server mode — for remote/multi-agent access
# ═══════════════════════════════════════════════════


# ─── HTTP security helpers (v0.7.3) ──────────────────

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _parse_listen_addr(listen_addr: str) -> tuple[str, int]:
    """Parse 'addr:port'. Bare ':port' binds loopback (v0.7.3 — was 0.0.0.0)."""
    if ":" not in listen_addr:
        listen_addr = ":" + listen_addr
    host, _, port_str = listen_addr.rpartition(":")
    if not host:
        host = "127.0.0.1"
    try:
        port = int(port_str)
    except ValueError:
        port = 8080
    return host, port


def _is_loopback(host: str) -> bool:
    return host.lower().strip("[]") in _LOOPBACK_HOSTS


def _allowed_browser_hosts(host: str) -> set[str]:
    """Hosts acceptable in Origin/Host headers.

    Loopback names always allowed; the explicit bind host allowed when it is
    a specific address; extra names via MCPTOON_ALLOWED_HOSTS (comma-sep).
    """
    allowed = {h.lower() for h in _LOOPBACK_HOSTS}
    if host and not _is_wildcard(host):
        allowed.add(host.lower().strip("[]"))
    extra = os.environ.get("MCPTOON_ALLOWED_HOSTS", "")
    for name in extra.split(","):
        name = name.strip().lower()
        if name:
            allowed.add(name)
    return allowed


def _is_wildcard(host: str) -> bool:
    return host.lower().strip("[]") in {"0.0.0.0", "::"}


def _browser_guard(headers, allowed: set[str], auth_enabled: bool) -> str | None:
    """Reject browser-originated requests when they don't belong here.

    Browsers always attach Origin on cross-origin fetch and always send Host;
    curl/agents/scripts send neither or a loopback Host. DNS rebinding shows
    up as a non-loopback Host on a loopback-bound server → caught here.

    Returns a rejection reason, or None to allow.
    """
    origin = headers.get("Origin")
    if origin:
        try:
            ohost = (urlsplit(origin).hostname or "").lower()
        except ValueError:
            return f"cross-origin request rejected: malformed Origin '{origin}'"
        if ohost and ohost in allowed:
            return None
        return f"cross-origin request rejected: Origin '{origin}' not allowed"

    host_hdr = headers.get("Host")
    if host_hdr and not auth_enabled:
        hname = host_hdr.rsplit(":", 1)[0].strip("[]").lower()
        if hname and hname not in allowed:
            return (f"DNS-rebinding guard: Host '{hname}' not allowed "
                    f"(allow via MCPTOON_ALLOWED_HOSTS or enable --auth)")
    return None


def _validate_http_bind(host: str, auth_token: str | None) -> str | None:
    """Return error message if this bind is unsafe, None if OK.

    Policy (v0.7.3): loopback may run without a token; binding beyond
    loopback REQUIRES one — the 'LAN-exposed + unauthenticated' combination
    is refused outright instead of allowed by accident.
    """
    if not _is_loopback(host) and not auth_token:
        return (
            f"Refusing to bind {host} without authentication.\n"
            f"  A network-exposed, unauthenticated MCP gateway would let anyone\n"
            f"  on the network call your tools. Either:\n"
            f"    - drop --listen (or keep it on 127.0.0.1) to stay on loopback, or\n"
            f"    - pass --auth <token> (or bare --auth to auto-generate one)"
        )
    return None


class MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler that dispatches JSON-RPC to the bridge (v0.7.3 hardened).

    Order of checks on every request:
      1. Origin/Host browser guard (CSRF + DNS-rebinding)
      2. Bearer token (if configured) — before any body parsing
      3. Content-Type (POST only, when header is present)
    """

    def _browser_guard(self) -> str | None:
        return _browser_guard(
            self.headers,
            getattr(self.server, "_mcptoon_allowed_hosts", set()),
            bool(getattr(self.server, "_mcptoon_auth_token", None)),
        )

    def _check_auth(self) -> bool:
        auth_token = getattr(self.server, "_mcptoon_auth_token", None)
        if not auth_token:
            return True
        provided = self.headers.get("Authorization", "")
        if provided.startswith("Bearer "):
            provided = provided[7:]
        return provided == auth_token

    def do_POST(self):
        reason = self._browser_guard()
        if reason:
            self.send_error(403, reason)
            return
        if not self._check_auth():
            self._send_json({
                "jsonrpc": "2.0",
                "error": {"code": -32001, "message": "Unauthorized"},
                "id": None,
            }, status=401)
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        # Reject only browser form-post types (the CSRF vector). JSON clients
        # and curl-style raw posts are unaffected; the Origin/Host guard above
        # is the primary browser defense.
        if ctype in ("text/plain", "multipart/form-data"):
            self.send_error(415, "Content-Type must be application/json")
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            })
            return

        bridge = self.server._mcptoon_bridge

        # Handle JSON-RPC batch (array of requests)
        if isinstance(request, list):
            responses = []
            for req in request:
                resp = self._handle_single(bridge, req)
                if resp is not None:
                    responses.append(resp)
            if responses:
                self._send_json(responses[0] if len(responses) == 1 else responses)
            return

        # Single request
        response = self._handle_single(bridge, request)
        if response is not None:
            self._send_json(response)
        else:
            self._send_json({
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32603, "message": "No response"},
            })

    def _handle_single(self, bridge, request: dict) -> dict | None:
        """Handle a single JSON-RPC request, return response dict or None."""
        if not isinstance(request, dict):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": "Invalid request"},
                "id": None,
            }

        # Notification (no id) — don't respond
        req_id = request.get("id")
        if req_id is None:
            # Handle cancellation notifications
            method = request.get("method", "")
            if method == "notifications/cancelled":
                _log("Cancellation request received (best-effort)")
            elif method == "notifications/initialized":
                _log("Client initialized notification received")
            return None

        # Use thread-local capture buffer (concurrency-safe)
        buf = io.StringIO()
        _response_capture.buf = buf
        # Scope CCR de-duplication to this agent. One HTTP process serves several
        # agents concurrently, so a shared "already sent" set would tell one agent
        # it had already seen another's payload — a wrong answer that looks like a
        # saving. The MCP Streamable HTTP session header names the conversation;
        # without it, de-duplication is switched off for this call rather than
        # guessed at. (begin_session is thread-local, so parallel requests cannot
        # stomp each other; see ccr.begin_session.)
        try:
            from . import ccr as _ccr
            sid = (self.headers.get("Mcp-Session-Id") or "").strip()
            _ccr.begin_session(sid or None, dedup=bool(sid))
        except Exception:
            pass
        try:
            bridge._handle_request(request)
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)[:200]},
            }
        finally:
            _response_capture.buf = None

        output_text = buf.getvalue().strip()
        if output_text:
            try:
                return json.loads(output_text)
            except json.JSONDecodeError:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": "Internal error"},
                }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": "No response from bridge"},
        }

    def do_GET(self):
        """Health check endpoint (v0.7.3: token + browser guard enforced)."""
        reason = self._browser_guard()
        if reason:
            self.send_error(403, reason)
            return
        if not self._check_auth():
            self._send_json({
                "jsonrpc": "2.0",
                "error": {"code": -32001, "message": "Unauthorized"},
                "id": None,
            }, status=401)
            return
        if self.path in ("/health", "/status", "/"):
            bridge = self.server._mcptoon_bridge
            bridge._ensure_initialized()
            health = bridge._handle_health()
            self._send_json(health)
        else:
            self.send_error(404, "Not found")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default logging (or route to stderr)
        _log(f"HTTP {self.address_string()} - {format % args}")


def _build_http_server(bridge, listen_addr: str, auth_token: str | None = None):
    """Construct the hardened HTTP server (bind + auth + browser guard).

    Separated from _run_http so tests can build servers on ephemeral ports.
    """
    # ThreadingHTTPServer, not the single-threaded HTTPServer: the docstring of
    # `_run_http` promises "multiple concurrent agents", but a plain HTTPServer
    # handles one request at a time, so a single slow upstream call blocks every
    # other agent (a self-inflicted DoS). Each request runs in its own daemon
    # thread; the bridge's shared state is already lock-guarded.
    from http.server import ThreadingHTTPServer

    host, port = _parse_listen_addr(listen_addr)

    # Resolve auth: explicit --auth value > bare --auth (generate) > env var
    if auth_token == _AUTO_TOKEN:
        import secrets
        auth_token = secrets.token_urlsafe(32)
        _log("Auth: auto-generated token (shown ONCE — store it now):")
        sys.stderr.write(f"mcptoon auth token: {auth_token}\n")
        sys.stderr.flush()
    if not auth_token:
        auth_token = os.environ.get("MCPTOON_AUTH_TOKEN", "")

    error = _validate_http_bind(host, auth_token)
    if error:
        sys.stderr.write(f"mcptoon serve: {error}\n")
        raise SystemExit(2)

    server = ThreadingHTTPServer((host, port), MCPHTTPHandler)
    server.daemon_threads = True
    server._mcptoon_auth_token = auth_token or None
    server._mcptoon_allowed_hosts = _allowed_browser_hosts(host)
    server._mcptoon_bridge = bridge
    return server


def _run_http(bridge: MCPServerBridge, listen_addr: str, auth_token: str | None = None):
    """Run mcptoon serve as an HTTP server.

    Accepts JSON-RPC POST requests at /mcp endpoint.
    Supports multiple concurrent agents (unlike stdio which is single-connection).

    Security (v0.7.3):
      - Bare `:port` binds 127.0.0.1 (loopback) — was 0.0.0.0
      - Non-loopback bind requires --auth (hard error otherwise)
      - Token (if set) checked on POST /mcp AND GET health endpoints, before
        any body parsing
      - Origin/Host validation blocks browser CSRF and DNS rebinding
      - POST requires Content-Type: application/json when header is present
    """
    # Initialize bridge before accepting connections
    _log("Initializing bridge...")
    bridge._ensure_initialized()
    _log(f"Bridge ready: {len(bridge._tool_index)} tools from {len(bridge._servers)} servers")

    server = _build_http_server(bridge, listen_addr, auth_token=auth_token)
    host, port = server.server_address[0], server.server_address[1]
    if server._mcptoon_auth_token:
        _log("Auth enabled: Bearer token required")
    _log(f"mcptoon serve HTTP listening on {host}:{port}")
    _log(f"  Endpoint: POST http://{host}:{port}/mcp")
    _log(f"  Health:   GET  http://{host}:{port}/health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("Interrupted")
    finally:
        server.shutdown()
        bridge.close()
        _log("mcptoon serve HTTP stopped")


def _serve_help() -> str:
    return """mcptoon serve — stdio bridge MCP server

Run mcptoon as an MCP server that the agent connects to.
mcptoon proxies all your configured MCP servers behind a single connection.

  Agent  ←→  mcptoon serve  ←→  MCP server 1, 2, ... N

Usage:
  mcptoon serve                    # default stdio (auto format)
  mcptoon serve --format toon      # compress results with TOON
  mcptoon serve --format slim      # compress results with SLIM
  mcptoon serve --format raw       # no compression (pass-through)
  mcptoon serve --listen :8080     # HTTP mode: http://127.0.0.1:8080 (loopback)
  mcptoon serve --http             # Shorthand for --listen :8080
  mcptoon serve --http --auth      # HTTP mode with auto-generated token
  mcptoon serve --listen 0.0.0.0:9090 --auth <token>  # LAN/remote (token required)
  mcptoon serve --background --http   # detach: keep running after the terminal closes
  mcptoon serve --status              # is the background instance alive? last log lines
  mcptoon serve --stop                # stop the background instance

Background mode:
  --background detaches the HTTP server so it survives the shell. pid + log live
  under the mcptoon state dir (~/.mcptoon). --background requires an HTTP address
  (--http/--listen).
  --status   report the background instance and its last log lines
  --stop     stop the background instance
  --install-autostart / --uninstall-autostart
             create/remove a logon entry (Windows Scheduled Task; systemd --user
             unit on POSIX) that starts `serve` for you. Opt-in and reversible.

Security (v0.7.3):
  - Bare ':port' binds 127.0.0.1 (loopback) — never 0.0.0.0
  - Binding beyond loopback REQUIRES --auth (refused otherwise)
  - Browser CSRF / DNS-rebinding guard on every request
  - Extra hostnames allowed via MCPTOON_ALLOWED_HOSTS env (comma-separated)

Agent config (e.g. Claude Code ~/.claude.json):
  {
    "mcpServers": {
      "mcptoon": {
        "command": "mcptoon",
        "args": ["serve"]
      }
    }
  }

  # Or connect to remote HTTP mode:
  {
    "mcpServers": {
      "mcptoon": {
        "url": "http://your-server:8080/mcp"
      }
    }
  }

Performance features:
  - Parallel manifest loading: 100 servers in ~5s (20 concurrent workers)
  - Per-call timeout: 30s default (override: MCPTOON_CALL_TIMEOUT env var)
  - Cache: 5min TTL (override: MCPTOON_CACHE_TTL env var)
  - Remote MCP: HTTP/SSE servers supported transparently
  - Thread-safe: multiple tool calls don't block each other
  - HTTP mode: multiple agents can connect simultaneously

Modes:
  stdio (default)   Single agent, local process — for Claude Code and other local agents
  HTTP (--listen)    Multi-agent, remote access — for teams, K8s, cloud

Options:
  --format <fmt>   Output format: auto|toon|slim|compact|smart|json|raw (default: auto)
  --toon           Shorthand for --format toon
  --slim           Shorthand for --format slim
  --compact        Shorthand for --format compact
  --smart          Shorthand for --format smart (structure-aware compression)
  --raw            Shorthand for --format raw (no compression)
  --listen <addr>  HTTP mode: listen on addr (default bind 127.0.0.1)
  --http           Shorthand for --listen :8080
  --auth [token]   Bearer token (bare --auth generates one, printed once)
  -h, --help       Show this help

Environment:
  MCPTOON_CALL_TIMEOUT    Per-call timeout in seconds (default: 30)
  MCPTOON_CACHE_TTL       Manifest cache TTL in seconds (default: 300)
  MCPTOON_CCR_TTL         Smart-compression retrieve TTL in seconds (default: 300)
  MCPTOON_CCR_DIR         Where compressed originals are stored (default: ~/.mcptoon/ccr)
  MCPTOON_AUTH_TOKEN      HTTP mode bearer token (same as --auth)
  MCPTOON_ALLOWED_HOSTS   Extra hostnames accepted in Origin/Host checks
  MCPTOON_LIST_TTL_MS     CacheableResult ttlMs on list/read results (default: 300000)
  MCPTOON_LIST_CACHE_SCOPE  cacheScope on list/read results: public|private (default: public)
  MCPTOON_NO_GUARD        1/true/yes turns the injection + credential screen off
                          (same as `mcptoon config set guard off`; default: on)
  MCPTOON_GUARD           on|off — explicit form of the same switch; wins over
                          MCPTOON_NO_GUARD and over the stored setting

Protocol (2026-07-28):
  - Stateless-first: no initialize handshake required; every request is
    self-describing (_meta io.modelcontextprotocol/* keys honored)
  - server/discover advertises protocolVersions/capabilities/serverInfo
  - List/read results carry ttlMs + cacheScope (SEP-2549 CacheableResult)
  - Ordinary results carry resultType: "complete"
  - Legacy initialize-handshake clients remain fully supported
"""
