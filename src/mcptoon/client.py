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
mcptoon client — Universal MCP client (HTTP + stdio)

Supports both transport modes defined by the Model Context Protocol:
  - stdio:  subprocess + JSON-RPC over stdin/stdout
  - http:   POST JSON-RPC to HTTP endpoint, handle SSE responses

Usage:
    # stdio (most common — any npx @anthropic/mcp-xxx works out of box)
    client = MCPClient(stdio=["npx", "-y", "@modelcontextprotocol/server-fetch"])
    client.initialize()
    tools = client.list_tools()
    result = client.call_tool("fetch", {"url": "https://example.com"})
    client.close()

    # http
    client = MCPClient(http="http://localhost:3001/mcp", headers={"Authorization": "Bearer xxx"})
    client.initialize()
    result = client.call_tool("search", {"query": "AI"})
    client.close()
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Any, Optional


# ─── MCP Protocol Constants ───

PROTOCOL_VERSION = "2024-11-05"

# Read version dynamically to avoid hardcoding drift
try:
    from . import __version__ as _pkg_version
except ImportError:
    _pkg_version = "0.0.0"
_CLIENT_INFO = {"name": "mcptoon", "version": _pkg_version}

# Request ID counter (thread-safe)
_id_lock = threading.Lock()
_id_counter = [0]


def _next_id() -> int:
    with _id_lock:
        _id_counter[0] += 1
        return _id_counter[0]


class MCPError(Exception):
    """MCP protocol or transport error."""

    def __init__(self, code: str, message: str, retry: bool = False):
        self.code = code
        self.message = message
        self.retry = retry
        super().__init__(f"[{code}] {message}")


class MCPClient:
    """Universal MCP client — HTTP or stdio transport.

    Args:
        stdio:  Command list to spawn as subprocess (e.g. ["npx", "-y", "@mcp/server"])
        http:   HTTP endpoint URL (e.g. "http://localhost:3001/mcp")
        headers: HTTP headers (e.g. {"Authorization": "Bearer xxx"})
        env:    Environment variables for stdio subprocess
        timeout: Default timeout in seconds

    Pass exactly one of `stdio` or `http`.
    """

    def __init__(
        self,
        stdio: Optional[list[str]] = None,
        http: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        env: Optional[dict[str, str]] = None,
        timeout: float = 30,
    ):
        if stdio and http:
            raise ValueError("Pass exactly one of stdio= or http=")
        if not stdio and not http:
            raise ValueError("Must pass stdio= or http=")

        self._transport = "stdio" if stdio else "http"
        self._stdio_cmd = stdio
        self._http_url = http
        self._headers = headers or {}
        self._env = env
        self._timeout = timeout

        # stdio state
        self._proc: Optional[subprocess.Popen] = None
        self._stdout_lock = threading.Lock()

        # http state
        self._session_id: Optional[str] = None

        # common state
        self._initialized = False
        self._tools_cache: list[dict] = []

    # ═══════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════

    def initialize(self) -> dict:
        """Perform MCP initialize handshake. Must be called before other methods."""
        if self._transport == "stdio":
            self._spawn_stdio()

        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        })

        # For HTTP, save session ID from response headers
        # (handled in _http_request)

        # Send initialized notification (required by MCP spec)
        self._notify("notifications/initialized", {})

        self._initialized = True
        return result

    def list_tools(self, use_cache: bool = True) -> list[dict]:
        """List available tools. Returns list of tool definitions."""
        if use_cache and self._tools_cache:
            return self._tools_cache

        result = self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        self._tools_cache = tools
        return tools

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """Call a tool by name with arguments.

        Returns the raw MCP result (content array) or parsed content.
        """
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        return self._extract_content(result)

    def close(self):
        """Clean up: kill subprocess or close HTTP session."""
        if self._transport == "stdio" and self._proc:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        self._initialized = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *exc):
        self.close()

    # ═══════════════════════════════════════════════════
    # stdio transport
    # ═══════════════════════════════════════════════════

    def _spawn_stdio(self):
        """Start the subprocess for stdio transport."""
        import shutil
        import sys

        env = os.environ.copy()
        if self._env:
            env.update(self._env)

        cmd = list(self._stdio_cmd)

        # Windows: resolve npx/node/.cmd executables
        if sys.platform == "win32" and cmd:
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd[0] = resolved
            elif not cmd[0].endswith(".cmd"):
                # Try .cmd extension (npx.cmd, etc.)
                resolved = shutil.which(cmd[0] + ".cmd")
                if resolved:
                    cmd[0] = resolved

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,  # unbuffered — critical for JSON-RPC over pipes
        )

    def _stdio_request(self, payload: bytes) -> dict:
        """Send JSON-RPC request over stdin, read response from stdout."""
        with self._stdout_lock:
            assert self._proc is not None
            assert self._proc.stdin is not None
            assert self._proc.stdout is not None

            self._proc.stdin.write(payload + b"\n")
            self._proc.stdin.flush()

            # Read one line (one JSON-RPC response)
            line = self._proc.stdout.readline()
            if not line:
                # Process may have died — check stderr
                stderr = ""
                if self._proc.stderr:
                    stderr = self._proc.stderr.read().decode("utf-8", errors="replace")[:500]
                raise MCPError("PROCESS_DIED", f"MCP server process exited. stderr: {stderr}")

            return self._parse_json_line(line)

    def _stdio_notify(self, payload: bytes):
        """Send notification (no response expected) over stdio."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write(payload + b"\n")
        self._proc.stdin.flush()

    # ═══════════════════════════════════════════════════
    # HTTP transport
    # ═══════════════════════════════════════════════════

    def _http_request(self, payload: bytes, timeout: float | None = None) -> dict:
        """POST JSON-RPC to HTTP endpoint, handle SSE or JSON response."""
        req = urllib.request.Request(self._http_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        for k, v in self._headers.items():
            req.add_header(k, v)
        if self._session_id:
            req.add_header("Mcp-Session-Id", self._session_id)

        # Disable proxy (MCP servers are usually local)
        handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)

        try:
            resp = opener.open(req, timeout=timeout or self._timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise MCPError("HTTP_ERROR", f"HTTP {e.code}: {body[:300]}", retry=e.code >= 500) from e
        except urllib.error.URLError as e:
            raise MCPError("CONNECTION_ERROR", str(e.reason)[:200], retry=True) from e

        # Save session ID from response headers
        new_sid = resp.headers.get("Mcp-Session-Id", "")
        if new_sid:
            self._session_id = new_sid

        body = resp.read().decode("utf-8", errors="replace")
        return self._parse_http_body(body)

    def _http_notify(self, payload: bytes):
        """Send notification over HTTP (fire-and-forget)."""
        try:
            req = urllib.request.Request(self._http_url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            for k, v in self._headers.items():
                req.add_header(k, v)
            if self._session_id:
                req.add_header("Mcp-Session-Id", self._session_id)
            handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(handler)
            opener.open(req, timeout=5)
        except Exception:
            pass  # Notifications are fire-and-forget

    # ═══════════════════════════════════════════════════
    # Unified request dispatcher
    # ═══════════════════════════════════════════════════

    def _request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        """Send a JSON-RPC request and return the result."""
        msg = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": method,
            "params": params,
        }
        payload = json.dumps(msg).encode()

        if self._transport == "stdio":
            data = self._stdio_request(payload)
        else:
            data = self._http_request(payload, timeout=timeout)

        if isinstance(data, dict):
            if "error" in data:
                err = data["error"]
                raise MCPError(
                    err.get("code", "MCP_ERROR"),
                    err.get("message", str(err)),
                    retry=False,
                )
            if "result" in data:
                return data["result"]
            return data

        raise MCPError("PARSE_ERROR", f"Unexpected response type: {type(data)}")

    def _notify(self, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        payload = json.dumps(msg).encode()

        if self._transport == "stdio":
            self._stdio_notify(payload)
        else:
            self._http_notify(payload)

    # ═══════════════════════════════════════════════════
    # Response parsing
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _parse_json_line(line: bytes) -> dict:
        """Parse one line of JSON-RPC from stdio."""
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            raise MCPError("EMPTY_RESPONSE", "MCP server returned empty line")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise MCPError("PARSE_ERROR", f"Invalid JSON: {e}. Raw: {text[:200]}") from e

    @staticmethod
    def _parse_http_body(body: str) -> dict:
        """Parse HTTP response — handles SSE (data: lines) and plain JSON."""
        # SSE format: lines starting with "data: "
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith("data: "):
                try:
                    d = json.loads(s[6:])
                    if isinstance(d, dict):
                        return d
                except json.JSONDecodeError:
                    continue

        # Plain JSON
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise MCPError("PARSE_ERROR", f"Cannot parse response: {body[:200]}") from e

    @staticmethod
    def _extract_content(result: Any) -> Any:
        """Extract usable content from MCP tools/call result.

        MCP returns {"content": [{"type": "text", "text": "..."}], ...}
        We try to parse the text content as JSON for structured results.
        """
        if not isinstance(result, dict):
            return result

        # Check for MCP error
        if result.get("isError"):
            contents = result.get("content", [])
            err_text = " ".join(
                c.get("text", "") for c in contents
                if isinstance(c, dict) and c.get("type") == "text"
            )
            return {"error": True, "message": err_text or "MCP tool returned error"}

        contents = result.get("content", [])
        if not contents:
            return result

        # Extract text content
        texts = [
            c["text"] for c in contents
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        if not texts:
            return result

        combined = "".join(texts)

        # Try to parse as JSON (structured result)
        try:
            return json.loads(combined)
        except (json.JSONDecodeError, ValueError):
            try:
                return json.loads(combined, strict=False)
            except (json.JSONDecodeError, ValueError):
                return {"text": combined}


# ═══════════════════════════════════════════════════
# Convenience: connection pool (reuse clients across calls)
# ═══════════════════════════════════════════════════

class MCPClientPool:
    """Manage multiple MCPClient instances, reuse connections.

    Usage:
        pool = MCPClientPool(config)
        result = pool.call("exa", "search", {"query": "AI"})
        pool.close()
    """

    def __init__(self, servers: dict):
        """servers: {name: {transport config}} from config.json"""
        self._servers = servers
        self._clients: dict[str, MCPClient] = {}
        self._lock = threading.Lock()

    def _get_client(self, name: str) -> MCPClient:
        """Get or create a client for server name."""
        if name in self._clients:
            return self._clients[name]

        with self._lock:
            if name in self._clients:
                return self._clients[name]

            cfg = self._servers.get(name)
            if not cfg:
                raise MCPError("UNKNOWN_SERVER", f"Server '{name}' not in config")

            client = self._make_client(cfg)
            client.initialize()
            self._clients[name] = client
            return client

    @staticmethod
    def _make_client(cfg: dict) -> MCPClient:
        """Create MCPClient from config dict."""
        transport = cfg.get("transport", "stdio")

        if transport == "stdio":
            return MCPClient(
                stdio=cfg.get("command", []) + cfg.get("args", []),
                env=cfg.get("env"),
                timeout=cfg.get("timeout", 30),
            )
        elif transport == "http":
            return MCPClient(
                http=cfg["url"],
                headers=cfg.get("headers", {}),
                timeout=cfg.get("timeout", 30),
            )
        else:
            raise MCPError("BAD_CONFIG", f"Unknown transport: {transport}")

    def list_tools(self, name: str) -> list[dict]:
        """List tools for a specific server."""
        return self._get_client(name).list_tools()

    def call(self, server: str, tool: str, arguments: dict | None = None) -> Any:
        """Call a tool on a specific server."""
        return self._get_client(server).call_tool(tool, arguments)

    def list_all_tools(self) -> dict[str, list[dict]]:
        """List tools from all configured servers. Returns {server: [tools]}."""
        result = {}
        for name in self._servers:
            try:
                result[name] = self.list_tools(name)
            except Exception as e:
                result[name] = [{"error": str(e)[:100]}]
        return result

    def close(self):
        """Close all clients."""
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
