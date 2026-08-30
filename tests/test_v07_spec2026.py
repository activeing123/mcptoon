"""Tests for MCP 2026-07-28 (latest spec) support — v0.7.0.

Covers:
- spec negotiation: server/discover probe → modern mode
- silent legacy fallback when the probe is rejected (auto mode)
- explicit spec="2026-07-28" fails loudly, spec="legacy" never probes
- modern request shaping: _meta protocol annotation, no handshake
- modern HTTP: Mcp-Method / Mcp-Name headers, no Mcp-Session-Id
- legacy HTTP: session id captured and replayed
- resultType handling: missing → complete, "input_required" → MRTR error
- MRTR retry with input_responses
- UnsupportedProtocolVersionError → one-time auto fallback + retry
- pool passes spec from server config
"""
import json
import os
import sys
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.client import (
    MCPClient,
    MCPClientPool,
    MCPError,
    MCPInputRequired,
    LATEST_PROTOCOL_VERSION,
    LEGACY_PROTOCOL_VERSION,
    ERR_UNSUPPORTED_PROTOCOL_VERSION,
    _META_PROTOCOL_KEY,
    _META_CAPS_KEY,
    _META_CLIENT_KEY,
)


def rpc_result(_id, result):
    return {"jsonrpc": "2.0", "id": _id, "result": result}


def rpc_error(_id, code, message):
    return {"jsonrpc": "2.0", "id": _id,
            "error": {"code": code, "message": message}}


DISCOVER_OK = {
    "protocolVersions": ["2026-07-28"],
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "modern-srv", "version": "1.0.0"},
}


class ScriptedClient(MCPClient):
    """MCPClient with a scripted in-memory transport (no real I/O).

    handlers: list of callables (msg: dict) -> dict (JSON-RPC response body).
    Exposes every request message in `self.seen` and HTTP headers in
    `self.seen_headers`.
    """

    def __init__(self, handlers, transport="stdio", headers=None, spec="auto"):
        # bypass __init__ subprocess wiring via direct object setup
        self._transport = transport
        self._stdio_cmd = ["unused"]
        self._http_url = "http://localhost:9999/mcp"
        self._headers = headers or {}
        self._env = None
        self._timeout = 5
        self._proc = None
        self._stdout_lock = __import__("threading").Lock()
        self._session_id = None
        self._spec = spec if spec in ("auto", "2026-07-28", "legacy") else "auto"
        self._mode = None
        self._negotiated = None
        self._in_probe = False
        self._fell_back = False
        self.server_info = None
        self.server_capabilities = None
        self._initialized = False
        self._tools_cache = []
        self.handlers = list(handlers)
        self.seen = []
        self.seen_headers = []

    def _stdio_request(self, payload: bytes) -> dict:
        msg = json.loads(payload.decode())
        self.seen.append(msg)
        return self.handlers.pop(0)(msg)

    def _http_request(self, payload: bytes, timeout=None, extra_headers=None) -> dict:
        msg = json.loads(payload.decode())
        self.seen.append(msg)
        hdr = dict(extra_headers or {})
        if self._session_id and self._mode != "modern":
            hdr["Mcp-Session-Id"] = self._session_id
        self.seen_headers.append(hdr)
        resp = self.handlers.pop(0)(msg)
        return resp

    def _http_notify(self, payload: bytes):
        pass  # record nothing; legacy handshake notification is irrelevant here

    def _stdio_notify(self, payload: bytes):
        pass  # legacy handshake notification — no real stdin to write to

    def _spawn_stdio(self):
        pass


class TestNegotiation(unittest.TestCase):

    def test_auto_probe_success_uses_modern(self):
        c = ScriptedClient([lambda m: rpc_result(m["id"], DISCOVER_OK)])
        c.initialize()
        self.assertEqual(c._mode, "modern")
        self.assertEqual(c._negotiated, LATEST_PROTOCOL_VERSION)
        self.assertTrue(c._initialized)
        # no initialize handshake was sent
        methods = [m["method"] for m in c.seen]
        self.assertEqual(methods, ["server/discover"])
        self.assertEqual(c.server_info["name"], "modern-srv")

    def test_auto_falls_back_to_legacy_on_method_not_found(self):
        def handler(m):
            if m["method"] == "server/discover":
                return rpc_error(m["id"], -32601, "Method not found")
            if m["method"] == "initialize":
                return rpc_result(m["id"], {"serverInfo": {"name": "old-srv"},
                                            "protocolVersion": "2025-06-18"})
            raise AssertionError("unexpected method " + m["method"])

        c = ScriptedClient([handler, handler, handler])
        c.initialize()
        self.assertEqual(c._mode, "legacy")
        self.assertEqual(c._negotiated, LEGACY_PROTOCOL_VERSION)
        methods = [m["method"] for m in c.seen]
        self.assertEqual(methods, ["server/discover", "initialize"])
        # legacy handshake declares 2025-06-18 (not the old 2024-11-05)
        self.assertEqual(c.seen[1]["params"]["protocolVersion"], "2025-06-18")

    def test_auto_falls_back_on_transport_error(self):
        def handler(m):
            if m["method"] == "server/discover":
                raise MCPError("CONNECTION_ERROR", "nope")
            return rpc_result(m["id"], {"serverInfo": {"name": "x"}})

        c = ScriptedClient([handler, handler, handler])
        c.initialize()
        self.assertEqual(c._mode, "legacy")

    def test_explicit_modern_fails_loudly(self):
        c = ScriptedClient(
            [lambda m: rpc_error(m["id"], -32601, "Method not found")],
            spec="2026-07-28")
        with self.assertRaises(MCPError) as cm:
            c.initialize()
        self.assertEqual(cm.exception.code, "NO_MODERN_SUPPORT")

    def test_explicit_legacy_never_probes(self):
        calls = []

        def handler(m):
            calls.append(m["method"])
            return rpc_result(m["id"], {"serverInfo": {"name": "old"}})

        c = ScriptedClient([handler, handler], spec="legacy")
        c.initialize()
        self.assertEqual(calls, ["initialize"])
        self.assertEqual(c._mode, "legacy")


class TestModernRequestShaping(unittest.TestCase):

    def _modern_client(self, handler):
        c = ScriptedClient(
            [lambda m: rpc_result(m["id"], DISCOVER_OK), handler, handler],
            spec="auto")
        c.initialize()
        return c

    def test_meta_annotation_injected(self):
        c = self._modern_client(lambda m: rpc_result(m["id"], {"tools": []}))
        c.list_tools(use_cache=False)
        req = c.seen[1]
        meta = req["params"]["_meta"]
        self.assertEqual(meta[_META_PROTOCOL_KEY], "2026-07-28")
        self.assertEqual(meta[_META_CAPS_KEY], {})
        self.assertEqual(meta[_META_CLIENT_KEY]["name"], "mcptoon")

    def test_existing_meta_preserved(self):
        c = self._modern_client(lambda m: rpc_result(m["id"], {"tools": []}))
        c._request("tools/list", {"_meta": {"custom": 1}})
        meta = c.seen[1]["params"]["_meta"]
        self.assertEqual(meta["custom"], 1)
        self.assertIn(_META_PROTOCOL_KEY, meta)

    def test_http_modern_headers_no_session(self):
        c = ScriptedClient(
            [lambda m: rpc_result(m["id"], DISCOVER_OK),
             lambda m: rpc_result(m["id"], {"tools": []})],
            transport="http")
        c.initialize()
        c.list_tools(use_cache=False)
        # discovery + tools/list both carry Mcp-Method, no session id
        self.assertEqual(c.seen_headers[0]["Mcp-Method"], "server/discover")
        self.assertEqual(c.seen_headers[1]["Mcp-Method"], "tools/list")
        self.assertNotIn("Mcp-Session-Id", c.seen_headers[0])
        self.assertNotIn("Mcp-Session-Id", c.seen_headers[1])

    def test_http_modern_call_carries_mcp_name(self):
        c = ScriptedClient(
            [lambda m: rpc_result(m["id"], DISCOVER_OK),
             lambda m: rpc_result(m["id"], {"content": []})],
            transport="http")
        c.initialize()
        c.call_tool("search", {"query": "x"})
        hdr = c.seen_headers[1]
        self.assertEqual(hdr["Mcp-Method"], "tools/call")
        self.assertEqual(hdr["Mcp-Name"], "search")

    def test_http_legacy_captures_and_replays_session(self):
        class SessionScripted(ScriptedClient):
            def _http_request(self, payload, timeout=None, extra_headers=None):
                msg = json.loads(payload.decode())
                self.seen.append(msg)
                hdr = dict(extra_headers or {})
                # mirror the real transport: replay session (legacy only)
                if self._session_id and self._mode != "modern":
                    hdr["Mcp-Session-Id"] = self._session_id
                self.seen_headers.append(hdr)
                self._session_id = "sid-123"  # server sets it on first reply
                return self.handlers.pop(0)(msg)

        c = SessionScripted(
            [lambda m: rpc_result(m["id"], {"serverInfo": {"name": "old"}}),
             lambda m: rpc_result(m["id"], {"tools": []})],
            transport="http", spec="legacy")
        c.initialize()
        c.list_tools(use_cache=False)
        # second request replayed the session id (legacy semantics)
        self.assertEqual(c.seen_headers[1].get("Mcp-Session-Id"), "sid-123")


class TestResultTypeAndMRTR(unittest.TestCase):

    def _client(self, handler):
        c = ScriptedClient(
            [lambda m: rpc_result(m["id"], DISCOVER_OK), handler, handler])
        c.initialize()
        return c

    def test_missing_result_type_treated_complete(self):
        """Servers predating 2026-07-28 omit resultType → MUST be complete."""
        c = self._client(lambda m: rpc_result(m["id"], {"content": [], "ok": 1}))
        out = c.call_tool_full("t", {})
        self.assertEqual(out["ok"], 1)

    def test_complete_result_type_passthrough(self):
        c = self._client(lambda m: rpc_result(
            m["id"], {"content": [], "resultType": "complete"}))
        out = c.call_tool_full("t", {})
        self.assertEqual(out["resultType"], "complete")

    def test_input_required_raises_mrtr_error(self):
        c = self._client(lambda m: rpc_result(m["id"], {
            "resultType": "input_required",
            "inputRequests": [{"method": "elicitation/create",
                               "params": {"message": "which env?"}}],
            "requestState": "st-1",
        }))
        with self.assertRaises(MCPInputRequired) as cm:
            c.call_tool_full("deploy", {})
        self.assertEqual(cm.exception.input_requests[0]["method"],
                         "elicitation/create")
        self.assertEqual(cm.exception.request_state, "st-1")
        self.assertEqual(cm.exception.code, "INPUT_REQUIRED")

    def test_input_responses_attached_on_retry(self):
        captured = {}

        def handler(m):
            captured.update(m["params"])
            return rpc_result(m["id"], {"content": []})

        c = self._client(handler)
        c.call_tool("deploy", {"region": "us"},
                    input_responses={"answer": "prod"})
        self.assertEqual(captured["inputResponses"], {"answer": "prod"})
        self.assertEqual(captured["arguments"], {"region": "us"})

    def test_request_state_attached_on_retry(self):
        """request_state (from MCPInputRequired) is echoed as params.requestState."""
        captured = {}

        def handler(m):
            captured.update(m["params"])
            return rpc_result(m["id"], {"content": []})

        c = self._client(handler)
        c.call_tool_full("deploy", {}, input_responses={"answer": "prod"},
                         request_state="st-42")
        self.assertEqual(captured["requestState"], "st-42")
        self.assertEqual(captured["inputResponses"], {"answer": "prod"})
        # absent → key never sent
        captured.clear()
        c.call_tool("deploy", {})
        self.assertNotIn("requestState", captured)

    def test_pool_forwards_request_state(self):
        """pool.call/call_full pass request_state through to the client."""
        captured = {}

        class PoolClient(ScriptedClient):
            def call_tool(self, name, arguments=None, input_responses=None,
                          request_state=None):
                captured["args"] = (input_responses, request_state)
                return {"content": []}

            def call_tool_full(self, name, arguments=None, input_responses=None,
                               request_state=None):
                captured["full"] = (input_responses, request_state)
                return {"content": []}

        class FakePool(MCPClientPool):
            def _get_client(self, name):
                return PoolClient([])

        pool = FakePool({"db": {"transport": "stdio", "command": ["x"]}})
        pool.call("db", "t", {}, input_responses={"a": 1}, request_state="st-9")
        pool.call_full("db", "t", {}, request_state="st-9")
        self.assertEqual(captured["args"], ({"a": 1}, "st-9"))
        self.assertEqual(captured["full"], (None, "st-9"))


class TestUnsupportedVersionFallback(unittest.TestCase):

    def test_unsupported_version_auto_falls_back_and_retries(self):
        """Server answered discover but rejects the version on real work."""
        calls = []

        def handler(m):
            calls.append(m["method"])
            if m["method"] == "server/discover":
                return rpc_result(m["id"], DISCOVER_OK)
            if (m["method"] == "tools/list"
                    and len([c for c in calls if c == "tools/list"]) == 1):
                # first real request → version rejected
                return rpc_error(m["id"], ERR_UNSUPPORTED_PROTOCOL_VERSION,
                                 "unsupported protocol version")
            return rpc_result(m["id"], {"tools": [{"name": "ok"}]})

        c = ScriptedClient([handler] * 8)
        c.initialize()
        tools = c.list_tools(use_cache=False)
        self.assertEqual(tools[0]["name"], "ok")
        self.assertEqual(c._mode, "legacy")
        self.assertTrue(c._fell_back)
        # retried under legacy semantics: initialize happened after fallback
        self.assertIn("initialize", calls)


class TestPoolSpecConfig(unittest.TestCase):

    def test_pool_passes_spec_from_config(self):
        made = {}

        real_make = MCPClientPool._make_client

        def fake_make(cfg):
            c = real_make(cfg)
            made["spec"] = c._spec
            return c

        class FakePool(MCPClientPool):
            _make_client = staticmethod(fake_make)

            def _get_client(self, name):
                cfg = self._servers[name]
                c = self._make_client(cfg)
                return c

        pool = FakePool({"db": {"transport": "stdio", "command": ["x"],
                                "spec": "legacy"}})
        pool._get_client("db")
        self.assertEqual(made["spec"], "legacy")

    def test_pool_default_spec_is_auto(self):
        real_make = MCPClientPool._make_client

        def fake_make(cfg):
            return real_make(cfg)

        class FakePool(MCPClientPool):
            _make_client = staticmethod(fake_make)

            def _get_client(self, name):
                return self._make_client(self._servers[name])

        pool = FakePool({"db": {"transport": "stdio", "command": ["x"]}})
        c = pool._get_client("db")
        self.assertEqual(c._spec, "auto")

    def test_make_client_accepts_string_command(self):
        """Lenient config: "command": "python" must behave like ["python"]."""
        c = MCPClientPool._make_client(
            {"transport": "stdio", "command": "python", "args": ["-u", "srv.py"]})
        self.assertEqual(c._stdio_cmd, ["python", "-u", "srv.py"])


class TestRouterEnvelopeMRTR(unittest.TestCase):
    """router.call_tool surfaces MRTR detail in the error envelope."""

    def test_input_required_envelope_carries_requests(self):
        from mcptoon import router

        class FakePool:
            def call(self, *a, **k):
                raise MCPInputRequired("needs input",
                                       input_requests=[{"method": "elicitation/create"}],
                                       request_state="s1")

        orig_pool, orig_cfg = router._get_pool, router.load_config
        router._get_pool = lambda: FakePool()
        router.load_config = lambda: {"db": {"transport": "stdio", "command": ["x"]}}
        try:
            out = router.call_tool("db", "deploy", {})
        finally:
            router._get_pool, router.load_config = orig_pool, orig_cfg
        self.assertTrue(out.get("_error"))
        self.assertEqual(out["_error"]["code"], "INPUT_REQUIRED")
        self.assertEqual(out["input_requests"][0]["method"], "elicitation/create")
        self.assertEqual(out["request_state"], "s1")


if __name__ == "__main__":
    unittest.main()
