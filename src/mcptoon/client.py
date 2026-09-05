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

import collections
import json
import os
import queue
import subprocess
import threading
import time
import urllib.request
import urllib.error
from typing import Any, Optional


# ─── MCP Protocol Constants ───

#: Newest MCP specification revision this client implements.
#: 2026-07-28 is the stateless revision: no initialize handshake, per-request
#: ``_meta`` versioning, ``server/discover`` RPC, MRTR multi round-trips.
LATEST_PROTOCOL_VERSION = "2026-07-28"

#: Revision used for the legacy initialize() handshake. Servers reply with
#: their own version; anything at or below this gets classic session semantics.
LEGACY_PROTOCOL_VERSION = "2025-06-18"

#: Every revision mcptoon knows how to talk to, newest first.
SUPPORTED_PROTOCOL_VERSIONS = [
    "2026-07-28",
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]

#: Backwards-compat alias (was hardcoded to "2024-11-05" before v0.7.0).
PROTOCOL_VERSION = LEGACY_PROTOCOL_VERSION

# _meta keys defined by the 2026-07-28 spec (stateless request annotation)
_META_PROTOCOL_KEY = "io.modelcontextprotocol/protocolVersion"
_META_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
_META_CLIENT_KEY = "io.modelcontextprotocol/clientInfo"

#: JSON-RPC error code for UnsupportedProtocolVersionError (2026-07-28)
ERR_UNSUPPORTED_PROTOCOL_VERSION = -32022

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


def _stdio_pump(proc, response_queues: dict, rq_lock,
                late_queue, late_lock):
    """Background stdout reader for stdio transport (v0.7.4).

    Reads raw lines from ``proc.stdout`` forever and routes every JSON-RPC
    message with an ``id`` into the matching per-id queue (popped from
    ``response_queues``). Everything else — debug output, notifications,
    responses for requests that already timed out — is parked in
    ``late_queue`` (lost & found) instead of poisoning the next request.

    On EOF, every registered waiter receives a ``None`` sentinel so
    in-flight requests fail fast instead of hanging on a dead process.

    Module-level so tests can drive it directly against a fake process.
    """
    stdout = proc.stdout
    while True:
        try:
            line = stdout.readline()
        except (OSError, ValueError):
            line = b""
        if not line:
            with rq_lock:
                for q in list(response_queues.values()):
                    q.put(None)
            return
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            # Debug output / partial line — no response id to route.
            with late_lock:
                late_queue.append((text, time.time()))
            continue
        if not isinstance(msg, dict) or "id" not in msg:
            # Notification — no response id; park for diagnostics.
            with late_lock:
                late_queue.append((msg, time.time()))
            continue
        rid = msg["id"]
        with rq_lock:
            q = response_queues.pop(rid, None)
        if q is not None:
            q.put(msg)
        else:
            # Response for a request that already timed out — park it
            # (lost & found) instead of poisoning the next request.
            with late_lock:
                late_queue.append((msg, time.time()))


class MCPError(Exception):
    """MCP protocol or transport error."""

    def __init__(self, code: str, message: str, retry: bool = False):
        self.code = code
        self.message = message
        self.retry = retry
        super().__init__(f"[{code}] {message}")


class MCPInputRequired(MCPError):
    """MRTR interim result (Multi Round-Trip Request, MCP 2026-07-28).

    A 2026-07-28 server returned ``resultType: "input_required"``: the tool
    needs more information before it can finish. Retry the original request
    with ``input_responses=`` supplying answers for ``input_requests``.
    """

    def __init__(self, message: str, input_requests: Any = None,
                 request_state: Any = None):
        super().__init__("INPUT_REQUIRED", message)
        self.input_requests = input_requests if isinstance(input_requests, list) else []
        self.request_state = request_state


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
        spec: str = "auto",
        cwd: Optional[str] = None,
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
        self._cwd = cwd

        # stdio state
        self._proc: Optional[subprocess.Popen] = None
        self._stdout_lock = threading.Lock()
        # One-shot stderr tail cache: the FIRST consumer (EOF sentinel or
        # write-failure path) drains the pipe; later error paths must reuse
        # the cached tail instead of reading an already-empty pipe.
        self._stderr_cache: Optional[str] = None

        # Response pump (v0.7.4): a background thread reads stdout lines and
        # routes every JSON-RPC message into a queue keyed by response id.
        # Requests then wait on the queue with a deadline — a silent server
        # (e.g. one that never replies to unknown RPCs) can no longer hang
        # the client forever via a blocking readline().
        self._pump_thread: Optional[threading.Thread] = None
        self._response_queues: dict[int, queue.Queue] = {}
        self._response_queues_lock = threading.Lock()
        self._late_queue: collections.deque[tuple[Any, float]] = collections.deque(
            maxlen=16)
        self._late_lock = threading.Lock()

        # http state
        self._session_id: Optional[str] = None

        # common state
        self._initialized = False
        self._tools_cache: list[dict] = []

        # protocol negotiation (MCP 2026-07-28)
        #   spec="auto":        probe server/discover, fall back to handshake
        #   spec="2026-07-28":  modern only — fail loudly if unsupported
        #   spec="legacy":      classic initialize() handshake, never probe
        #   mode: "modern" | "legacy" | None (before negotiation)
        self._spec = spec if spec in ("auto", "2026-07-28", "legacy") else "auto"
        self._mode: Optional[str] = None
        self._negotiated: Optional[str] = None
        self._in_probe = False
        self._fell_back = False
        self.server_info: Optional[dict] = None
        self.server_capabilities: Optional[dict] = None

    # ═══════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════

    def initialize(self) -> dict:
        """Connect and negotiate the best MCP protocol version.

        With ``spec="auto"`` (default) the client probes the server with
        ``server/discover`` (MCP 2026-07-28). A server that answers gets
        stateless modern semantics; anything that rejects the probe
        silently falls back to the classic initialize() handshake
        (2025-06-18 and older revisions).
        """
        if self._transport == "stdio":
            self._spawn_stdio()

        if self._spec in ("auto", "2026-07-28"):
            try:
                result = self._probe_modern()
                self._mode = "modern"
                self._negotiated = LATEST_PROTOCOL_VERSION
                if isinstance(result, dict):
                    self.server_info = result.get("serverInfo")
                    self.server_capabilities = result.get("capabilities")
                self._initialized = True
                return result if isinstance(result, dict) else {}
            except MCPError as e:
                if self._spec == "2026-07-28":
                    raise MCPError(
                        "NO_MODERN_SUPPORT",
                        f"server/discover failed ({e.message}); server does not "
                        f"speak MCP {LATEST_PROTOCOL_VERSION}. "
                        f"Retry with spec='legacy'.",
                    ) from e
                # spec == "auto" → fall through to the legacy handshake

        result = self._legacy_initialize()
        self._mode = "legacy"
        self._negotiated = LEGACY_PROTOCOL_VERSION
        self._initialized = True
        return result

    def _probe_modern(self) -> dict:
        """Probe a server with the 2026-07-28 ``server/discover`` RPC.

        Returns the discovery result on success; raises MCPError when the
        server clearly does not implement the modern protocol (unknown
        method, unsupported version, transport failure, ...).

        Uses a short dedicated deadline (capped at 10s): a legacy server
        that stays silent on this RPC should cost seconds, not the full
        request timeout, before the auto-fallback to the classic handshake.
        """
        self._in_probe = True
        try:
            probe_timeout = min(self._timeout, 10.0)
            return self._request("server/discover", {}, timeout=probe_timeout)
        finally:
            self._in_probe = False

    def _legacy_initialize(self) -> dict:
        """Classic initialize handshake (MCP <= 2025-11-25 semantics)."""
        result = self._request("initialize", {
            "protocolVersion": LEGACY_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        })
        if isinstance(result, dict):
            self.server_info = result.get("serverInfo")
            self.server_capabilities = result.get("capabilities")
        # Send initialized notification (required by legacy MCP spec)
        self._notify("notifications/initialized", {})
        return result

    def list_tools(self, use_cache: bool = True) -> list[dict]:
        """List available tools. Returns list of tool definitions."""
        if use_cache and self._tools_cache:
            return self._tools_cache

        result = self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        self._tools_cache = tools
        return tools

    def call_tool(self, name: str, arguments: dict | None = None,
                  input_responses: dict | None = None,
                  request_state: str | None = None) -> Any:
        """Call a tool by name with arguments.

        Returns the raw MCP result (content array) or parsed content.

        ``input_responses`` (MCP 2026-07-28 MRTR): answers for a previous
        ``resultType: "input_required"`` response; the request is retried
        with the answers attached as ``params.inputResponses``. Pass
        ``request_state`` (the token from ``MCPInputRequired.request_state``)
        alongside it so a stateless server can correlate the retry with the
        original request (sent as ``params.requestState``).
        """
        params = {
            "name": name,
            "arguments": arguments or {},
        }
        if input_responses:
            params["inputResponses"] = input_responses
        if request_state:
            params["requestState"] = request_state
        result = self._request("tools/call", params)
        return self._extract_content(result)

    def call_tool_full(self, name: str, arguments: dict | None = None,
                       input_responses: dict | None = None,
                       request_state: str | None = None) -> Any:
        """Call a tool and return the COMPLETE MCP tools/call result envelope.

        Unlike call_tool(), this keeps every protocol-level field intact:
        structuredContent, _meta, resultType, isError, content — everything
        the server sent. Required for newer MCP spec servers that return
        structured output instead of plain text content.

        Raises MCPInputRequired when the server answers with MRTR
        ``resultType: "input_required"`` (2026-07-28); retry with
        ``input_responses=`` (+ ``request_state=`` for stateless
        server-side correlation).
        """
        params = {
            "name": name,
            "arguments": arguments or {},
        }
        if input_responses:
            params["inputResponses"] = input_responses
        if request_state:
            params["requestState"] = request_state
        return self._request("tools/call", params)

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
                    self._proc.wait(timeout=1)
                except Exception:
                    pass
            finally:
                self._proc = None
        self._initialized = False

    def _reconnect_if_dead(self):
        """Check if stdio process is dead and try to reconnect.

        Called before each request. If process has exited, restarts it.
        """
        if self._transport != "stdio":
            return
        if self._proc is None:
            # Not started yet — spawn
            self._spawn_stdio()
            self._initialized = False
            return
        if self._proc.poll() is not None:
            # Process has exited — restart
            def _log_fn(msg):
                pass  # no-op logger
            self._proc = None
            self._initialized = False
            self._tools_cache = []  # Clear cache on reconnect
            self._spawn_stdio()

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
            cwd=self._cwd,
            bufsize=0,  # unbuffered — critical for JSON-RPC over pipes
        )
        self._start_response_pump()
        # Fresh process → forget any stderr tail from the previous one.
        self._stderr_cache = None

    def _start_response_pump(self):
        """Start the background stdout reader thread (v0.7.4).

        The pump reads raw lines and routes JSON-RPC responses to per-id
        queues. Requests block on ``queue.get(timeout=...)`` instead of a
        blocking ``readline()`` — the fix for infinite hangs on servers
        that never answer some RPCs (e.g. old servers that stay silent on
        the 2026-07-28 ``server/discover`` probe).
        """
        self._pump_thread = threading.Thread(
            target=_stdio_pump,
            args=(self._proc, self._response_queues,
                  self._response_queues_lock, self._late_queue,
                  self._late_lock),
            daemon=True,
            name=f"mcptoon-stdio-pump-{id(self._proc)}",
        )
        self._pump_thread.start()

    def _stderr_tail(self) -> str:
        """Best-effort tail of a dead server's stderr, cached one-shot.

        Only the first call after a process death reads the pipe (EOF once
        the child is gone); the result is cached so later error paths —
        e.g. the auto-probe failure followed by the legacy-handshake
        failure — all carry the same diagnostic tail.
        """
        if self._stderr_cache is not None:
            return self._stderr_cache
        if not (self._proc and self._proc.stderr):
            return ""
        # NOTE: do NOT gate this read on poll() — inside the exit race a
        # child's pipe handles close (EOF becomes visible) before the
        # process object flips to signaled, so poll() can still report
        # alive on a process whose stderr is already fully written. Read
        # in a helper thread with a 1s cap instead: post-mortem reads
        # return immediately, and a live server never blocks the caller.
        def _drain() -> None:
            try:
                tail = self._proc.stderr.read().decode(  # type: ignore[union-attr]
                    "utf-8", errors="replace")[:500]
            except Exception:
                tail = ""  # stderr diagnostics are best-effort
            self._stderr_cache = tail

        t = threading.Thread(target=_drain, daemon=True,
                             name="mcptoon-stderr-drain")
        t.start()
        t.join(timeout=1.0)
        if self._stderr_cache is None:
            return ""  # still draining in background; don't block callers
        return self._stderr_cache

    def _stdio_request(self, payload: bytes, timeout: float | None = None) -> dict:
        """Send JSON-RPC request over stdin, wait for the response with a
        deadline.

        The background pump thread owns stdout; this method registers a
        per-id queue, writes the request, then blocks on the queue with a
        timeout. A server that never replies now surfaces as a
        ``RESPONSE_TIMEOUT`` MCPError instead of hanging forever.
        """
        rid = None
        try:
            req_msg = json.loads(payload.decode("utf-8"))
            rid = req_msg.get("id")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        if not isinstance(rid, int):
            raise MCPError("PROTOCOL_ERROR", "request payload has no numeric id")

        response_q: queue.Queue = queue.Queue(maxsize=1)
        with self._response_queues_lock:
            self._response_queues[rid] = response_q

        try:
            with self._stdout_lock:
                assert self._proc is not None
                assert self._proc.stdin is not None
                self._proc.stdin.write(payload + b"\n")
                self._proc.stdin.flush()
        except (OSError, ValueError, BrokenPipeError) as e:
            with self._response_queues_lock:
                self._response_queues.pop(rid, None)
            # A write failure almost always means the process already
            # exited (e.g. npx E404 on a missing package). Surface the
            # stderr tail so users see the real cause, not just Errno 22.
            stderr = self._stderr_tail()
            detail = f"failed writing to MCP server: {e}"
            if stderr.strip():
                detail += f" | server stderr: {stderr.strip()}"
            raise MCPError("PROCESS_DIED", detail) from e

        deadline = timeout if timeout is not None else self._timeout
        try:
            msg = response_q.get(timeout=deadline)
        except queue.Empty:
            with self._response_queues_lock:
                self._response_queues.pop(rid, None)
            raise MCPError(
                "RESPONSE_TIMEOUT",
                f"no JSON-RPC response for request id {rid} "
                f"within {deadline}s (server went silent)",
                retry=False,
            ) from None

        if msg is None:
            # Pump EOF sentinel — process died. Surface stderr tail
            # (one-shot cached; later error paths reuse it).
            stderr = self._stderr_tail()
            raise MCPError(
                "PROCESS_DIED",
                f"MCP server process exited. stderr: {stderr}")

        return msg

    def _stdio_notify(self, payload: bytes):
        """Send notification (no response expected) over stdio."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write(payload + b"\n")
        self._proc.stdin.flush()

    # ═══════════════════════════════════════════════════
    # HTTP transport
    # ═══════════════════════════════════════════════════

    def _http_request(self, payload: bytes, timeout: float | None = None,
                      extra_headers: dict | None = None) -> dict:
        """POST JSON-RPC to HTTP endpoint, handle SSE/Streamable HTTP/JSON response.

        Supports:
          - Plain JSON response (Content-Type: application/json)
          - SSE stream (Content-Type: text/event-stream) — both old and Streamable HTTP
          - Streamable HTTP with Mcp-Session-Id header (legacy revisions)
          - Stateless 2026-07-28 requests (Mcp-Method/Mcp-Name headers, no session)
        """
        req = urllib.request.Request(self._http_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        for k, v in self._headers.items():
            req.add_header(k, v)
        if extra_headers:
            for k, v in extra_headers.items():
                req.add_header(k, v)
        # Legacy revisions only: 2026-07-28 removed protocol-level sessions
        if self._session_id and self._mode != "modern":
            req.add_header("Mcp-Session-Id", self._session_id)

        # Disable proxy (MCP servers are usually local)
        handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(handler)

        try:
            resp = opener.open(req, timeout=timeout or self._timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            # Try to parse as JSON error
            try:
                err_data = json.loads(body)
                if isinstance(err_data, dict) and "error" in err_data:
                    return err_data
            except (json.JSONDecodeError, ValueError):
                pass
            raise MCPError("HTTP_ERROR", f"HTTP {e.code}: {body[:300]}", retry=e.code >= 500) from e
        except urllib.error.URLError as e:
            raise MCPError("CONNECTION_ERROR", str(e.reason)[:200], retry=True) from e

        # Save session ID from response headers (Streamable HTTP)
        new_sid = resp.headers.get("Mcp-Session-Id", "")
        if new_sid:
            self._session_id = new_sid

        # Check content type for SSE vs JSON
        content_type = resp.headers.get("Content-Type", "")

        if "text/event-stream" in content_type:
            # SSE stream — read all events and find the response
            body = resp.read().decode("utf-8", errors="replace")
            return self._parse_http_body(body)
        else:
            # Plain JSON response
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
        """Send a JSON-RPC request and return the result.

        MCP 2026-07-28 (modern mode): every request is annotated with
        ``_meta`` carrying the protocol version, client capabilities and
        client info — there is no initialize handshake. HTTP requests also
        carry the required ``Mcp-Method`` / ``Mcp-Name`` headers and never
        send a session id.

        Legacy mode: requests go out bare; the initialize handshake has
        already established the session.
        """
        # Auto-reconnect if stdio process died
        if self._transport == "stdio":
            self._reconnect_if_dead()

        modern = self._mode == "modern" or getattr(self, "_in_probe", False)

        # 2026-07-28: annotate every request with protocol _meta
        if modern:
            params = dict(params)
            meta = dict(params.get("_meta") or {})
            meta[_META_PROTOCOL_KEY] = self._negotiated or LATEST_PROTOCOL_VERSION
            meta[_META_CAPS_KEY] = {}
            meta[_META_CLIENT_KEY] = _CLIENT_INFO
            params["_meta"] = meta

        # 2026-07-28 Streamable HTTP: standard request headers
        extra_headers = None
        if modern and self._transport == "http":
            extra_headers = {"Mcp-Method": method}
            if method == "tools/call" and isinstance(params.get("name"), str):
                extra_headers["Mcp-Name"] = params["name"]

        msg = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": method,
            "params": params,
        }
        payload = json.dumps(msg).encode()

        if self._transport == "stdio":
            data = self._stdio_request(payload, timeout=timeout)
        else:
            data = self._http_request(payload, timeout=timeout,
                                      extra_headers=extra_headers)

        if isinstance(data, dict):
            if "error" in data:
                err = data["error"]
                code = err.get("code", "MCP_ERROR")
                # 2026-07-28: server rejected our protocol version — fall
                # back to the legacy handshake once (auto mode only), then
                # retry the request under legacy semantics.
                if (modern and code == ERR_UNSUPPORTED_PROTOCOL_VERSION
                        and self._spec == "auto" and not self._fell_back):
                    self._fell_back = True
                    self._mode = "legacy"
                    self._negotiated = LEGACY_PROTOCOL_VERSION
                    if self._transport == "http":
                        self._session_id = None
                    self._legacy_initialize()
                    return self._request(method, params, timeout=timeout)
                raise MCPError(
                    code,
                    err.get("message", str(err)),
                    retry=False,
                )
            if "result" in data:
                result = data["result"]
                # 2026-07-28 MRTR: interim result asking for more input.
                # (Servers predating the field omit resultType — clients
                # MUST treat those as "complete", which is the default here.)
                if isinstance(result, dict) and result.get("resultType") == "input_required":
                    raise MCPInputRequired(
                        "tool needs more input before it can finish (MRTR)",
                        input_requests=result.get("inputRequests"),
                        request_state=result.get("requestState"),
                    )
                return result
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
        """Parse HTTP response — handles SSE (data: lines) and plain JSON.

        Also handles Streamable HTTP where response may include
        multiple SSE events (notifications + final response).
        Returns the last valid JSON-RPC response found.
        """
        last_result = None

        # SSE format: lines starting with "data: "
        for line in body.split("\n"):
            s = line.strip()
            if s.startswith("data: "):
                try:
                    d = json.loads(s[6:])
                    if isinstance(d, dict):
                        # Keep the last response with a result or error
                        if "result" in d or "error" in d or "id" in d and "method" not in d:
                            last_result = d
                except json.JSONDecodeError:
                    continue

        if last_result is not None:
            return last_result

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

        New MCP spec (2025-06-18+) servers may return `structuredContent`
        instead of / alongside text content — when present, it is preferred
        as the authoritative result.
        """
        if not isinstance(result, dict):
            return result

        # New protocol: structuredContent is the authoritative result
        if result.get("structuredContent") is not None:
            return result["structuredContent"]

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
        """Get or create a client for server name.

        Thread-safe: uses lock only for dict access, NOT for initialize().
        This allows parallel server initialization across different servers.
        Resource-safe: if two threads create clients for the same server,
        the losing client is properly closed.
        """
        # Fast path: already connected
        cached = self._clients.get(name)
        if cached is not None:
            return cached

        # Check config
        cfg = self._servers.get(name)
        if not cfg:
            raise MCPError("UNKNOWN_SERVER", f"Server '{name}' not in config")

        # Create client (no lock needed — each thread creates its own)
        client = self._make_client(cfg)
        client.initialize()

        # Store in pool (lock only for dict write)
        with self._lock:
            # Double-check: another thread may have connected in parallel
            if name in self._clients:
                # Another thread won; close ours properly
                try:
                    client.close()
                except Exception:
                    # Best-effort cleanup — don't let close() failure leak resources
                    pass
                return self._clients[name]
            self._clients[name] = client
            return client

    @staticmethod
    def _make_client(cfg: dict) -> MCPClient:
        """Create MCPClient from config dict."""
        transport = cfg.get("transport", "stdio")

        if transport == "stdio":
            command = cfg.get("command", [])
            if isinstance(command, str):
                command = [command]  # lenient: "command": "python" == ["python"]
            # Agent Plugins (v0.7.1): inject the two reserved variables the
            # spec requires at server start (paths were pre-expanded at install)
            env = dict(cfg.get("env") or {})
            if cfg.get("plugin_root"):
                env.setdefault("PLUGIN_ROOT", cfg["plugin_root"])
            if cfg.get("plugin_data"):
                env.setdefault("PLUGIN_DATA", cfg["plugin_data"])
            return MCPClient(
                stdio=command + cfg.get("args", []),
                env=env or None,
                timeout=cfg.get("timeout", 30),
                spec=cfg.get("spec", "auto"),
                cwd=cfg.get("cwd"),
            )
        elif transport == "http":
            return MCPClient(
                http=cfg["url"],
                headers=cfg.get("headers", {}),
                timeout=cfg.get("timeout", 30),
                spec=cfg.get("spec", "auto"),
            )
        else:
            raise MCPError("BAD_CONFIG", f"Unknown transport: {transport}")

    def list_tools(self, name: str) -> list[dict]:
        """List tools for a specific server."""
        return self._get_client(name).list_tools()

    def call(self, server: str, tool: str, arguments: dict | None = None,
             input_responses: dict | None = None,
             request_state: str | None = None) -> Any:
        """Call a tool on a specific server."""
        client = self._get_client(server)
        if input_responses or request_state:
            return client.call_tool(tool, arguments, input_responses=input_responses,
                                    request_state=request_state)
        return client.call_tool(tool, arguments)

    def call_full(self, server: str, tool: str, arguments: dict | None = None,
                  input_responses: dict | None = None,
                  request_state: str | None = None) -> Any:
        """Call a tool and return the complete MCP tools/call result envelope.

        Keeps protocol-level fields intact: structuredContent, _meta,
        resultType, isError, content. Raises MCPInputRequired on MRTR
        interim results (2026-07-28); retry with ``input_responses=``.
        """
        client = self._get_client(server)
        if input_responses or request_state:
            return client.call_tool_full(tool, arguments,
                                         input_responses=input_responses,
                                         request_state=request_state)
        return client.call_tool_full(tool, arguments)

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
