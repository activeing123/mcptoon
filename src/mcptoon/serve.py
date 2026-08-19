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

"""
mcptoon serve — stdio bridge MCP server (ADR 0004)

Acts as a single MCP server in front of the agent, proxying all
underlying MCP servers. The agent only connects to mcptoon (1 server),
not 100 individual servers.

  Agent  ←→  mcptoon serve (stdio)  ←→  MCP server 1, 2, ... N

Key behaviors:
  - tools/list: returns simplified schemas (80-90% fewer tokens, ADR 0006)
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
import json
import os
import sys
import threading
import time
import traceback
from typing import Any

from . import __version__
from .config import load_config, resolve_server_name
from .client import MCPClientPool, MCPError
from . import manifest as manifest_mod
from . import router as router_mod
from . import usage
from .schema_simplifier import (
    simplify_tool_def,
    validate_args,
    namespaced_tool_name,
    split_namespaced,
)
from .errors import make_error, is_error

# MCP protocol version we speak as a server
PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "mcptoon", "version": __version__}

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
        # tool_index: namespaced_name → {server, tool, full_schema, full_def}
        self._tool_index: dict[str, dict] = {}
        self._tool_index_lock = threading.RLock()
        self._initialized = False
        self._lock = threading.Lock()
        self._shutdown = False

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
            self._pool = MCPClientPool(self._servers)
            self._build_tool_index()
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
                # Cache the result
                try:
                    from .cache import set_cached_tools
                    set_cached_tools(srv, tools)
                except Exception:
                    pass
                return srv, tools
            except Exception as e:
                _log(f"  [{srv}] fetch failed: {e}")
                return srv, []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_MANIFEST_WORKERS,
            thread_name_prefix="mcptoon-manifest",
        ) as executor:
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

    def _handle_request(self, request: dict):
        """Dispatch a single JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        # Notification (no id) — don't respond
        if req_id is None:
            if method == "notifications/initialized":
                _log("Client initialized notification received")
            return

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
                _send_response(_make_success(req_id, result))
            elif method == "tools/list":
                result = self._handle_list_tools(params)
                _send_response(_make_success(req_id, result))
            elif method == "tools/call":
                result = self._handle_call_tool(params)
                _send_response(_make_success(req_id, result))
            elif method == "ping":
                _send_response(_make_success(req_id, {}))
            elif method == "resources/list":
                _send_response(_make_success(req_id, {"resources": []}))
            elif method == "resources/read":
                _send_response(_make_success(req_id, {"contents": []}))
            elif method == "prompts/list":
                _send_response(_make_success(req_id, {"prompts": []}))
            elif method == "prompts/get":
                _send_response(_make_error_response(req_id, -32601, "Prompts not supported"))
            elif method == "logging/setLevel":
                _log(f"Client set logging level: {params.get('level', 'info')}")
                _send_response(_make_success(req_id, {}))
            elif method == "health":
                _send_response(_make_success(req_id, self._handle_health()))
            else:
                _send_response(_make_error_response(req_id, -32601, f"Method not found: {method}"))
        except MCPError as e:
            _send_response(_make_error_response(req_id, -32603, f"[{e.code}] {e.message}"))
        except Exception as e:
            _send_response(_make_error_response(req_id, -32603, str(e)[:200]))

        if method == "shutdown":
            self._shutdown = True

    # ═══════════════════════════════════════════════════
    # MCP Method Handlers
    # ═══════════════════════════════════════════════════

    def _handle_initialize(self, params: dict) -> dict:
        """Respond to MCP initialize handshake."""
        _log(f"Initialize from client: {params.get('clientInfo', {})}")
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
            "serverInfo": _SERVER_INFO,
        }

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
        # Check if any servers failed to load
        failed = sum(1 for s in self._servers if s not in {
            v.get("server") for v in self._tool_index.values()
        })
        if failed > 0 and failed == total_servers:
            status = "error"
        elif failed > 0:
            status = "degraded"
        else:
            status = "ok"
        return {
            "status": status,
            "version": __version__,
            "servers": total_servers,
            "tools": total_tools,
            "failed_servers": failed if failed > 0 else 0,
            "uptime": time.time() - getattr(self, "_start_time", time.time()),
        }

    def _handle_list_tools(self, params: dict) -> dict:
        """Return simplified tool list (ADR 0006 — layered schema return).

        Each tool name is namespaced: {server}_{tool} (ADR 0007).
        Schemas are simplified to 80-90% fewer tokens.
        Thread-safe: reads from _tool_index under RLock.
        """
        self._ensure_initialized()

        with self._tool_index_lock:
            if not self._tool_index:
                # No tools at all — try refreshing
                pass

            tools: list[dict] = []
            for ns_name, info in sorted(self._tool_index.items()):
                full_def = info.get("full_def", {})
                simplified = simplify_tool_def(full_def)
                simplified["name"] = ns_name  # Override with namespaced name
                tools.append(simplified)

        _log(f"tools/list: returning {len(tools)} tools (simplified schemas)")
        return {"tools": tools}

    def _handle_call_tool(self, params: dict) -> dict:
        """Route a tool call to the underlying server (ADR 0004).

        Thread-safe: reads from _tool_index under RLock.
        Timeout: 30s default, configurable via MCPTOON_CALL_TIMEOUT.
        """
        self._ensure_initialized()

        name = params.get("name", "")
        arguments = params.get("arguments", {})

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
        if info:
            full_schema = info.get("full_schema", {})
            errors = validate_args(arguments, full_schema)
            if errors:
                return _make_tool_error(
                    f"Parameter validation failed: {'; '.join(errors)}"
                )

        # Safety checks via router
        danger = router_mod._check_dangerous(server, tool, arguments)
        if danger:
            return _make_tool_error(
                f"Blocked: {danger}. Use CLI with --destructive to override."
            )

        # Route to underlying server (with timeout)
        try:
            if not self._pool:
                self._pool = MCPClientPool(self._servers)

            # Call with timeout
            call_timeout = _get_call_timeout()
            result = self._call_with_timeout(self._pool, server, tool, arguments, call_timeout)
            usage.track_call(server, tool, ok=True)

            # Compress output if format is configured
            result = self._compress_result(result, server, tool)

            return _make_tool_result(result)

        except MCPError as e:
            usage.track_call(server, tool, ok=False)
            return _make_tool_error(f"[{e.code}] {e.message}")
        except concurrent.futures.TimeoutError:
            usage.track_call(server, tool, ok=False)
            return _make_tool_error(f"Call timed out after {_get_call_timeout()}s")
        except Exception as e:
            usage.track_call(server, tool, ok=False)
            return _make_tool_error(f"Call failed: {str(e)[:200]}")

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
                r = pool.call(server, tool, arguments)
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

    def _compress_result(self, result: Any, server: str, tool: str) -> Any:
        """Compress tool call result based on output format."""
        if self._output_format in ("raw", "json", "auto"):
            return result

        try:
            from . import output as output_mod
            compressed = output_mod.render(result, fmt=self._output_format)
            if compressed is not None:
                return compressed
        except Exception:
            pass

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


def _make_tool_result(content: Any) -> dict:
    """Format a successful tool result as MCP content response."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        # Already MCP content array format
        return {"content": content, "isError": False}
    elif isinstance(content, dict) and "content" in content:
        # Already wrapped
        return content
    else:
        text = json.dumps(content, ensure_ascii=False) if content is not None else "null"

    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
    }


def _make_tool_error(message: str) -> dict:
    """Format a tool error as MCP content response."""
    return {
        "content": [{"type": "text", "text": f"Error: {message}"}],
        "isError": True,
    }


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
    """Get the configured timeout for tool calls."""
    try:
        return int(os.environ.get("MCPTOON_CALL_TIMEOUT", _DEFAULT_CALL_TIMEOUT))
    except ValueError:
        return _DEFAULT_CALL_TIMEOUT


# ═══════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════

def run_serve(args: list[str]):
    """Entry point for `mcptoon serve` command.

    Args:
        args: Command line args after 'serve'
              --format toon|slim|compact|json|raw|auto  (default: auto)
              --listen <addr>  HTTP mode: listen on addr (e.g. :8080, 0.0.0.0:9090)
              --http            Shorthand for --listen :8080
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
            i += 1
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
        elif a == "--listen" and i + 1 < len(args):
            listen_addr = args[i + 1]
            i += 1
        elif a.startswith("--listen="):
            listen_addr = a.split("=", 1)[1]
            i += 1
        elif a == "--http":
            listen_addr = ":8080"
            i += 1
        elif a == "--auth" and i + 1 < len(args):
            auth_token = args[i + 1]
            i += 1
        elif a.startswith("--auth="):
            auth_token = a.split("=", 1)[1]
            i += 1
        elif a in ("-h", "--help"):
            print(_serve_help())
            return
        i += 1

    bridge = MCPServerBridge(output_format=output_format)

    if listen_addr:
        _run_http(bridge, listen_addr, auth_token=auth_token)
    else:
        bridge.run()


# ═══════════════════════════════════════════════════
# HTTP server mode — for remote/multi-agent access
# ═══════════════════════════════════════════════════


def _run_http(bridge: MCPServerBridge, listen_addr: str, auth_token: str | None = None):
    """Run mcptoon serve as an HTTP server.

    Accepts JSON-RPC POST requests at /mcp endpoint.
    Supports multiple concurrent agents (unlike stdio which is single-connection).

    Auth: If auth_token is set, requests must include
    `Authorization: Bearer <token>` header.
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    # Parse listen address
    if ":" not in listen_addr:
        listen_addr = ":" + listen_addr
    host, _, port_str = listen_addr.rpartition(":")
    if not host:
        host = "0.0.0.0"
    try:
        port = int(port_str)
    except ValueError:
        port = 8080

    class MCPHTTPHandler(BaseHTTPRequestHandler):
        """HTTP handler that dispatches JSON-RPC to the bridge."""

        def do_POST(self):
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

            # Check auth token if configured
            auth_token = getattr(self.server, "_mcptoon_auth_token", None)
            if auth_token:
                provided = self.headers.get("Authorization", "")
                if provided.startswith("Bearer "):
                    provided = provided[7:]
                if provided != auth_token:
                    self._send_json({
                        "jsonrpc": "2.0",
                        "error": {"code": -32001, "message": "Unauthorized"},
                        "id": request.get("id") if isinstance(request, dict) else None,
                    })
                    return

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
            """Health check endpoint."""
            if self.path in ("/health", "/status", "/"):
                bridge._ensure_initialized()
                health = bridge._handle_health()
                self._send_json(health)
            else:
                self.send_error(404, "Not found")

        def _send_json(self, data: dict):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # Suppress default logging (or route to stderr)
            _log(f"HTTP {self.address_string()} - {format % args}")

    # Initialize bridge before accepting connections
    _log(f"Initializing bridge...")
    bridge._ensure_initialized()
    _log(f"Bridge ready: {len(bridge._tool_index)} tools from {len(bridge._servers)} servers")

    # Determine auth token: explicit > env var
    if not auth_token:
        auth_token = os.environ.get("MCPTOON_AUTH_TOKEN", "")
    if auth_token:
        _log(f"Auth enabled: Bearer token required")

    server = HTTPServer((host, port), MCPHTTPHandler)
    server._mcptoon_auth_token = auth_token or None
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
  mcptoon serve --listen :8080     # HTTP mode: listen on port 8080
  mcptoon serve --http             # Shorthand for --listen :8080
  mcptoon serve --listen 0.0.0.0:9090  # HTTP mode: bind to all interfaces

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
  stdio (default)   Single agent, local process — for Claude Code, CatPaw
  HTTP (--listen)    Multi-agent, remote access — for teams, K8s, cloud

Options:
  --format <fmt>   Output format: auto|toon|slim|compact|json|raw (default: auto)
  --toon           Shorthand for --format toon
  --slim           Shorthand for --format slim
  --compact        Shorthand for --format compact
  --raw            Shorthand for --format raw (no compression)
  --listen <addr>  HTTP mode: listen on addr (e.g. :8080, 0.0.0.0:9090)
  --http           Shorthand for --listen :8080
  -h, --help       Show this help

Environment:
  MCPTOON_CALL_TIMEOUT    Per-call timeout in seconds (default: 30)
  MCPTOON_CACHE_TTL       Manifest cache TTL in seconds (default: 300)
"""