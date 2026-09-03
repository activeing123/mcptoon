"""Regression tests for v0.7.4 — stdio response pump with per-request timeout.

Background (2026-09-03 investigation):
    A server that stays SILENT on the ``server/discover`` probe (e.g.
    mcp_server_fetch 2026.8.18, which sends nothing at all — not even a
    -32601 error) hung the client forever: ``_stdio_request`` used a
    blocking ``stdout.readline()`` with no deadline. ``mcptoon doctor``,
    ``manifest`` and ``discover`` (which enumerate every configured
    server) were permanently stuck by one dead entry.

Fix:
    - Background pump thread (module-level ``_stdio_pump``) owns stdout;
      routes JSON-RPC responses to per-id queues.
    - ``_stdio_request`` waits on the queue with a deadline → silent
      server now surfaces as MCPError("RESPONSE_TIMEOUT").
    - Probe uses a short dedicated deadline (≤10s) so auto-fallback to
      the legacy handshake costs seconds, not the full request timeout.
    - EOF wakes all waiters (fail fast on process death).
    - Late responses for timed-out requests are parked (lost & found)
      instead of poisoning the next request.

Test strategy:
    Real subprocesses via sys.executable for transport tests (the hang
    reproduced exactly as in production); fake-process unit tests for
    pump routing edge cases.
"""
import json
import os
import queue
import subprocess  # noqa: F401 — kept for parity with other transport tests
import sys
import threading
import time
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.client import (
    MCPClient,
    MCPError,
    LEGACY_PROTOCOL_VERSION,
    _stdio_pump,
)

PY = sys.executable


# ─── Test servers (written to tmp files, run as real subprocesses) ───

SILENT_SERVER = r'''
"""MCP stdio server that NEVER answers server/discover (the hang repro).
Everything else answers normally (initialize, tools/list, tools/call)."""
import json, sys
def handle_initialize(req):
    return {"protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "silent-legacy", "version": "0.1.0"}}
def handle_tools_list(req):
    return {"tools": [{"name": "ping",
                       "description": "reply ping",
                       "inputSchema": {"type": "object", "properties": {}}}]}
def handle_tools_call(req):
    name = req["params"]["name"]
    if name == "ping":
        return {"content": [{"type": "text", "text": "pong"}], "isError": False}
    return {"content": [{"type": "text", "text": "unknown tool"}], "isError": True}
HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = req.get("method", "")
    if method == "server/discover" or method == "notifications/initialized":
        continue  # THE BUG: total silence on the probe
    handler = HANDLERS.get(method)
    if handler:
        resp = {"jsonrpc": "2.0", "id": req.get("id", 0), "result": handler(req)}
    else:
        resp = {"jsonrpc": "2.0", "id": req.get("id", 0),
                "error": {"code": -32601, "message": "Unknown method"}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
'''

SLOW_PROBE_SERVER = r'''
"""Answers server/discover after a fixed delay (tests the probe deadline).
Also answers the legacy initialize handshake for fallback tests."""
import json, sys, time
DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
def handle_initialize(req):
    return {"protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "slow-legacy", "version": "0"}}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = req.get("method", "")
    if method == "notifications/initialized":
        continue
    if method == "server/discover":
        time.sleep(DELAY)
        resp = {"jsonrpc": "2.0", "id": req.get("id", 0),
                "result": {"protocolVersions": ["2026-07-28"],
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "slow-modern", "version": "0"}}}
    elif method == "initialize":
        resp = {"jsonrpc": "2.0", "id": req.get("id", 0),
                "result": handle_initialize(req)}
    else:
        resp = {"jsonrpc": "2.0", "id": req.get("id", 0),
                "error": {"code": -32601, "message": "Unknown method"}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
'''

DIE_ON_FIRST_REQUEST = r'''
"""Exits immediately after reading the first request (EOF wake-up test)."""
import sys
for line in sys.stdin:
    break
sys.exit(0)
'''


def _write_server(tmpdir, code, name):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return path


class _FakeStdout:
    """Pre-scripted stdout stand-in for pump unit tests."""

    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class TestStdioResponsePump(unittest.TestCase):
    """Real-subprocess regression tests for the v0.7.4 hang fix."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmpdir = tempfile.mkdtemp(prefix="mcptoon-pump-test-")
        cls.silent = _write_server(cls.tmpdir, SILENT_SERVER, "silent_server.py")
        cls.slow = _write_server(cls.tmpdir, SLOW_PROBE_SERVER, "slow_probe.py")
        cls.dier = _write_server(cls.tmpdir, DIE_ON_FIRST_REQUEST, "dier.py")

    def test_silent_probe_falls_back_and_works(self):
        """The production hang: silent probe → deadline → legacy fallback →
        tools/list + tools/call all work. Before the fix this hung forever."""
        client = MCPClient(stdio=[PY, self.silent], timeout=10)
        client.initialize()  # must NOT hang: probe times out, falls back
        self.assertEqual(client._mode, "legacy")
        self.assertEqual(client._negotiated, LEGACY_PROTOCOL_VERSION)
        tools = client.list_tools()
        self.assertEqual([t["name"] for t in tools], ["ping"])
        result = client.call_tool("ping", {})
        self.assertIn("pong", str(result))
        client.close()

    def test_silent_probe_deadline_is_short(self):
        """Probe deadline is capped at 10s even when client timeout is 30s —
        a legacy server costs seconds, not the full request timeout."""
        t0 = time.time()
        client = MCPClient(stdio=[PY, self.silent], timeout=30)
        client.initialize()
        elapsed = time.time() - t0
        client.close()
        self.assertEqual(client._mode, "legacy")
        self.assertLess(elapsed, 25,  # probe ≤10s + handshake margin
                        f"initialize took {elapsed:.1f}s; probe deadline "
                        f"cap (≤10s) not applied")

    def test_explicit_modern_fails_fast_on_silence(self):
        """spec='2026-07-28' against a silent server: RESPONSE_TIMEOUT
        (not a hang), surfaced as NO_MODERN_SUPPORT."""
        client = MCPClient(stdio=[PY, self.silent],
                           timeout=3, spec="2026-07-28")
        t0 = time.time()
        with self.assertRaises(MCPError) as cm:
            client.initialize()
        elapsed = time.time() - t0
        self.assertEqual(cm.exception.code, "NO_MODERN_SUPPORT")
        self.assertLess(elapsed, 10)
        client.close()

    def test_eof_wakes_waiter_fail_fast(self):
        """Server dies after first request → EOF sentinel wakes the queue
        waiter → PROCESS_DIED immediately (not the full timeout)."""
        client = MCPClient(stdio=[PY, self.dier], timeout=30)
        t0 = time.time()
        with self.assertRaises(MCPError) as cm:
            client.initialize()
        elapsed = time.time() - t0
        self.assertEqual(cm.exception.code, "PROCESS_DIED")
        self.assertLess(elapsed, 15, f"took {elapsed:.1f}s; EOF wake-up failed")
        client.close()

    def test_slow_probe_within_deadline_still_modern(self):
        """A slow-but-alive modern server (3s < 10s cap) still negotiates
        modern mode — the short probe deadline must not break slow servers."""
        client = MCPClient(stdio=[PY, self.slow, "3"], timeout=30)
        client.initialize()
        self.assertEqual(client._mode, "modern")
        client.close()

    def test_slow_probe_beyond_deadline_falls_back(self):
        """A server answering the probe after 12s (> 10s cap) falls back to
        legacy — accepted trade-off, documented in the probe docstring."""
        client = MCPClient(stdio=[PY, self.slow, "12"], timeout=30)
        client.initialize()
        self.assertEqual(client._mode, "legacy")
        client.close()

    def test_lost_and_found_parks_late_response(self):
        """A response arriving after its request timed out is parked in the
        late queue and does NOT get routed to the next request's queue."""
        client = MCPClient(stdio=[PY, self.slow, "12"], timeout=30)
        # Probe (id N) times out at ~10s → fallback handshake (id N+1...);
        # the late probe response arrives ~12s in and must be parked.
        # (Ids are process-global, so we assert on the payload — the parked
        # message IS the server/discover reply, recognizable by
        # protocolVersions — not on a hardcoded id.)
        client.initialize()
        self.assertEqual(client._mode, "legacy")
        # Give the pump a moment to deliver the late probe response.
        deadline = time.time() + 10
        parked_probe = None
        while time.time() < deadline:
            with client._late_lock:
                for m, _ in client._late_queue:
                    if (isinstance(m, dict)
                            and isinstance(m.get("result"), dict)
                            and "protocolVersions" in m["result"]):
                        parked_probe = m
                        break
            if parked_probe:
                break
            time.sleep(0.1)
        self.assertIsNotNone(
            parked_probe,
            f"late probe response must be parked, got {client._late_queue!r}")
        client.close()


class TestPumpRouting(unittest.TestCase):
    """Unit tests for pump routing logic with a fake process (no I/O races)."""

    def _make_client(self):
        c = MCPClient.__new__(MCPClient)
        c._transport = "stdio"
        c._stdio_cmd = ["unused"]
        c._http_url = None
        c._headers = {}
        c._env = None
        c._timeout = 5
        c._cwd = None
        c._proc = None
        c._stdout_lock = threading.Lock()
        c._pump_thread = None
        c._response_queues = {}
        c._response_queues_lock = threading.Lock()
        c._late_queue = []
        c._late_lock = threading.Lock()
        c._initialized = False
        c._tools_cache = []
        return c

    def _drive_pump(self, c, fake_proc):
        t = threading.Thread(
            target=_stdio_pump,
            args=(fake_proc, c._response_queues, c._response_queues_lock,
                  c._late_queue, c._late_lock),
            daemon=True)
        t.start()
        t.join(timeout=5)

    def test_routing_by_id(self):
        c = self._make_client()
        fake_proc = type("P", (), {})()
        fake_proc.stdout = _FakeStdout([
            json.dumps({"jsonrpc": "2.0", "id": 7,
                        "result": {"v": "first"}}).encode() + b"\n",
            json.dumps({"jsonrpc": "2.0", "id": 8,
                        "result": {"v": "second"}}).encode() + b"\n",
        ])
        fake_proc.stderr = None
        q7, q8 = queue.Queue(), queue.Queue()
        c._response_queues = {7: q7, 8: q8}
        self._drive_pump(c, fake_proc)
        self.assertEqual(q7.get(timeout=1)["result"]["v"], "first")
        self.assertEqual(q8.get(timeout=1)["result"]["v"], "second")
        self.assertEqual(c._response_queues, {})

    def test_late_response_parked(self):
        c = self._make_client()
        fake_proc = type("P", (), {})()
        fake_proc.stdout = _FakeStdout([
            json.dumps({"jsonrpc": "2.0", "id": 99, "result": {}}).encode() + b"\n",
        ])
        fake_proc.stderr = None
        # no queue registered for id 99 → pump must park it
        self._drive_pump(c, fake_proc)
        self.assertEqual(len(c._late_queue), 1,
                         "late response must be parked in lost & found")
        self.assertEqual(c._late_queue[0][0].get("id"), 99)

    def test_non_json_lines_parked(self):
        c = self._make_client()
        fake_proc = type("P", (), {})()
        fake_proc.stdout = _FakeStdout([b"INFO: booting...\n"])
        fake_proc.stderr = None
        self._drive_pump(c, fake_proc)
        self.assertEqual(len(c._late_queue), 1)
        self.assertEqual(c._late_queue[0][0], "INFO: booting...")

    def test_notification_parked_not_routed(self):
        c = self._make_client()
        fake_proc = type("P", (), {})()
        fake_proc.stdout = _FakeStdout([
            json.dumps({"jsonrpc": "2.0", "method": "tools/list_changed"}).encode() + b"\n",
        ])
        fake_proc.stderr = None
        self._drive_pump(c, fake_proc)
        self.assertEqual(len(c._late_queue), 1,
                         "notification (no id) must be parked, not routed")

    def test_eof_wakes_registered_waiter(self):
        c = self._make_client()
        fake_proc = type("P", (), {})()
        fake_proc.stdout = _FakeStdout([])  # immediate EOF
        fake_proc.stderr = None
        q = queue.Queue()
        c._response_queues = {5: q}
        self._drive_pump(c, fake_proc)
        self.assertIsNone(q.get(timeout=1),
                          "EOF must send None sentinel to all waiters")


if __name__ == "__main__":
    unittest.main()
