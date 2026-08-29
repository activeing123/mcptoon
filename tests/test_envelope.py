"""Tests for new MCP protocol compatibility (v0.6.1).

Covers:
- structuredContent preference in _extract_content (2025-06-18+ spec servers)
- call_tool_full() envelope passthrough
- MCPClientPool.call_full()
- router.call_tool(return_envelope=True)
"""
import os
import sys
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.client import MCPClient, MCPClientPool
from mcptoon import router


class TestExtractContentStructured(unittest.TestCase):
    """_extract_content prefers structuredContent (new MCP spec)."""

    def test_structured_content_preferred(self):
        result = {
            "content": [{"type": "text", "text": "legacy text"}],
            "structuredContent": {"answer": 42, "source": "structured"},
        }
        out = MCPClient._extract_content(result)
        self.assertEqual(out, {"answer": 42, "source": "structured"})

    def test_no_structured_content_falls_back_to_text(self):
        result = {"content": [{"type": "text", "text": '{"a": 1}'}]}
        out = MCPClient._extract_content(result)
        self.assertEqual(out, {"a": 1})

    def test_structured_content_null_falls_back(self):
        """structuredContent present but falsy → fall through to legacy path."""
        result = {"content": [{"type": "text", "text": "hi"}], "structuredContent": None}
        out = MCPClient._extract_content(result)
        self.assertEqual(out, {"text": "hi"})

    def test_error_result_still_detected(self):
        result = {
            "isError": True,
            "content": [{"type": "text", "text": "boom"}],
        }
        out = MCPClient._extract_content(result)
        self.assertTrue(out["error"])
        self.assertIn("boom", out["message"])

    def test_non_dict_passthrough(self):
        self.assertEqual(MCPClient._extract_content("plain"), "plain")
        self.assertEqual(MCPClient._extract_content(None), None)


class TestEnvelopePassthrough(unittest.TestCase):
    """call_tool_full / pool.call_full / router return_envelope plumbing."""

    def _make_client(self):
        return MCPClient(stdio=["true"])  # exits immediately; not used for requests

    def test_call_tool_full_returns_envelope(self):
        """call_tool_full must return the raw tools/call result, not extracted."""
        captured = {}

        class FakeClient(MCPClient):
            def _request(self, method, params):
                captured["method"] = method
                return {
                    "content": [{"type": "text", "text": "ignored"}],
                    "structuredContent": {"rows": 7},
                    "_meta": {"serverHint": "db1"},
                    "isError": False,
                }

        c = FakeClient.__new__(FakeClient)
        envelope = MCPClient.call_tool_full(c, "query", {"sql": "SELECT 1"})
        self.assertEqual(captured["method"], "tools/call")
        self.assertEqual(envelope["structuredContent"], {"rows": 7})
        self.assertEqual(envelope["_meta"], {"serverHint": "db1"})
        self.assertFalse(envelope["isError"])

    def test_pool_call_full(self):
        class FakeClient:
            def call_tool_full(self, tool, arguments):
                return {"envelope": True, "tool": tool}

        class FakePool(MCPClientPool):
            def _get_client(self, name):
                return FakeClient()

        pool = FakePool({"db": {"transport": "stdio", "command": ["x"]}})
        out = pool.call_full("db", "query", {})
        self.assertTrue(out["envelope"])
        self.assertEqual(out["tool"], "query")

    def test_router_call_tool_envelope_flag_plumbed(self):
        """router.call_tool(return_envelope=True) hits pool.call_full."""
        calls = []

        class FakePool:
            def call(self, *a, **k):
                calls.append("call")
                return "extracted"

            def call_full(self, *a, **k):
                calls.append("call_full")
                return {"structuredContent": {"v": 1}, "content": []}

        original_get_pool = router._get_pool
        original_load_config = router.load_config
        router._get_pool = lambda: FakePool()
        router.load_config = lambda: {"db": {"transport": "stdio", "command": ["x"]}}
        try:
            out = router.call_tool("db", "query", {}, return_envelope=True)
            self.assertEqual(calls, ["call_full"])
            self.assertEqual(out["structuredContent"], {"v": 1})

            calls.clear()
            out = router.call_tool("db", "query", {})
            self.assertEqual(calls, ["call"])
            self.assertEqual(out, "extracted")
        finally:
            router._get_pool = original_get_pool
            router.load_config = original_load_config


if __name__ == "__main__":
    unittest.main()
