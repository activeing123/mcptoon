"""HTTP de-duplication scoping (`serve.MCPHTTPHandler.do_POST`).

`mcptoon serve --listen` handles several agents concurrently in one process. The
CCR store's de-duplication answers "have I already sent this exact payload to
*you*?" — so it needs to know who "you" is. Two ways to get that wrong, both of
which lose information while looking like a saving:

* a process-wide session id, which two request threads would overwrite, so the
  losing agent is told it already received a body it never saw;
* treating "no session header" as one shared conversation, which conflates every
  anonymous client into a single agent.

The handler takes the MCP Streamable HTTP session header when the client sends
it, and switches de-duplication **off** when it does not. These tests drive a real
HTTP server with a bridge stub that reports what the session state was at request
time, because that state is the thing under test.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock

from mcptoon import ccr, serve


class ProbeBridge:
    """Bridge stub that records the CCR session state each request ran under."""

    def __init__(self):
        self._tool_index = {"fake_tool": {}}
        self._servers = ["fake"]
        self.initialized = False
        self.seen: list[tuple[str, bool]] = []
        self._lock = threading.Lock()

    def _ensure_initialized(self):
        self.initialized = True

    def _handle_health(self):
        return {"status": "ok"}

    def _handle_request(self, request):
        # `was_sent` before `mark_sent` is the question the compressor asks, so
        # this is exactly the decision de-duplication would make for this caller.
        handle = ccr._handle_for("probe", "tool", "same-payload")
        was = ccr.was_sent(handle)
        ccr.mark_sent(handle)
        with self._lock:
            self.seen.append((ccr.current_session(), was))
        buf = serve._response_capture.buf
        if buf is not None:
            buf.write(json.dumps({
                "jsonrpc": "2.0", "id": request.get("id"),
                "result": {"ok": True},
            }))

    def close(self):
        pass


class HTTPCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {
            "MCPTOON_CCR_DIR": self._tmp.name, "MCPTOON_CCR_TTL": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

        # Session bookkeeping is process-global and keyed by id, so a session name
        # an earlier test already used would make this test's *first* request look
        # like a repeat. Clear it rather than inventing per-test names, because the
        # ids are the thing some of these tests assert on.
        with ccr._session_lock:
            ccr._session_sent.clear()
            ccr._session_deduped.clear()

        self.bridge = ProbeBridge()
        self._server = serve._build_http_server(self.bridge, "127.0.0.1:0")
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address[:2]
        self.base = f"http://{host}:{port}"

    def tearDown(self):
        self._server.shutdown()
        self._server.server_close()

    def post(self, headers=None, req_id=1):
        body = json.dumps({"jsonrpc": "2.0", "id": req_id,
                           "method": "tools/list"}).encode()
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(self.base + "/mcp", data=body, headers=h)
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            json.loads(resp.read().decode())


class TestAnonymousClientsAreNotConflated(HTTPCase):
    def test_no_session_header_disables_dedup(self):
        self.post(req_id=1)
        self.post(req_id=2)
        self.assertEqual(len(self.bridge.seen), 2)
        # Neither request may be told "already sent": they could be two agents.
        self.assertEqual([was for _, was in self.bridge.seen], [False, False])

    def test_no_session_header_is_reported_as_such(self):
        self.post()
        sid, _ = self.bridge.seen[0]
        self.assertTrue(sid, "a session id is still reported, for logging")


class TestNamedSessionsAreIsolated(HTTPCase):
    def test_same_session_header_repeats_and_is_deduped(self):
        self.post(headers={"Mcp-Session-Id": "agent-a"}, req_id=1)
        self.post(headers={"Mcp-Session-Id": "agent-a"}, req_id=2)
        self.assertEqual([was for _, was in self.bridge.seen], [False, True])

    def test_different_session_headers_do_not_cross_contaminate(self):
        self.post(headers={"Mcp-Session-Id": "agent-a"}, req_id=1)
        self.post(headers={"Mcp-Session-Id": "agent-b"}, req_id=2)
        self.assertEqual([was for _, was in self.bridge.seen], [False, False])

    def test_session_ids_reach_the_store_verbatim(self):
        self.post(headers={"Mcp-Session-Id": "agent-a"})
        self.post(headers={"Mcp-Session-Id": "agent-b"})
        self.assertEqual([sid for sid, _ in self.bridge.seen], ["agent-a", "agent-b"])

    def test_header_name_is_case_insensitive(self):
        self.post(headers={"mcp-session-id": "agent-a"}, req_id=1)
        self.post(headers={"MCP-SESSION-ID": "agent-a"}, req_id=2)
        self.assertEqual([was for _, was in self.bridge.seen], [False, True])


class TestConcurrentAgents(HTTPCase):
    def test_parallel_agents_do_not_share_a_session(self):
        """The thread-local guarantee, over real concurrent HTTP requests."""
        errors: list[Exception] = []

        def fire(name: str, req_id: int) -> None:
            try:
                self.post(headers={"Mcp-Session-Id": name}, req_id=req_id)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=fire, args=(f"agent-{i}", i))
                   for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(sid for sid, _ in self.bridge.seen),
                         ["agent-0", "agent-1", "agent-2", "agent-3"])
        # Each agent sent its own first payload, so none is a repeat.
        self.assertEqual([was for _, was in self.bridge.seen], [False] * 4)


if __name__ == "__main__":
    unittest.main()
