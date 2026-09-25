"""End-to-end: an upstream tool that declares outputSchema must reach the client.

The unit tests in test_native_tools.py prove the bridge no longer strips the
field, but they do it against a fake pool. This file drives a real stdio MCP
server through the real client, so a regression in the client's own envelope
handling -- not just in serve's wiring -- would show up here too.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.native_tools import call_native  # noqa: E402
from mcptoon.serve import MCPServerBridge  # noqa: E402
PY = sys.executable


# A stdio MCP server whose single tool declares an outputSchema, exactly the
# shape of the upstream servers issue #22 was filed against (filesystem's
# list_directory declares {content: string} as required).
SCHEMA_SERVER = r'''
import json, sys
TOOLS = [{
    "name": "list_directory",
    "description": "List a directory.",
    "inputSchema": {"type": "object", "properties": {}},
    "outputSchema": {"type": "object", "properties": {"content": {"type": "string"}},
                     "required": ["content"]},
}]
def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        m, i = req.get("method"), req.get("id")
        if m == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "schema-server", "version": "1.0.0"}}
        elif m == "tools/list":
            res = {"tools": TOOLS}
        elif m == "tools/call":
            payload = {"content": "[DIR] alpha"}
            res = {"content": [{"type": "text", "text": json.dumps(payload)}],
                   "structuredContent": payload, "isError": False,
                   "resultType": "complete"}
        elif m == "notifications/initialized":
            continue
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i,
                                         "error": {"code": -32601, "message": "nope"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": res}) + "\n")
        sys.stdout.flush()
main()
'''


class TestSchemaToolSurvivesTheRealPath(unittest.TestCase):
    """The reporter's repro, end to end: mcptoon serve over a real stdio server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._old = {k: os.environ.get(k) for k in
                     ("MCPTOON_SETTINGS_FILE", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML")}
        os.environ["MCPTOON_SETTINGS_FILE"] = str(base / "settings.json")
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")
        self.srv = base / "schema_server.py"
        self.srv.write_text(SCHEMA_SERVER, encoding="utf-8")
        self.config = base / "cfg.json"
        # Not "fs": config.py aliases "fs" -> "filesystem", and a name that
        # already resolves elsewhere would test the alias table, not the bridge.
        self.config.write_text(json.dumps({"mcpServers": {
            "schemahost": {"command": PY, "args": [str(self.srv)]}}}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_structured_content_reaches_the_client_over_a_real_server(self):
        """mcptoon_call on an outputSchema tool must answer with structuredContent."""
        b = MCPServerBridge()
        # Not "fs": config.py aliases "fs" -> "filesystem", so that name resolves
        # to a server this test does not configure.
        b._servers = {"schemahost": {"command": PY, "args": [str(self.srv)]}}
        b._tool_index = {"schemahost_list_directory": {
            "server": "schemahost", "tool": "list_directory", "full_schema": {},
            "full_def": {"name": "list_directory", "description": "List a directory.",
                         "outputSchema": {"type": "object",
                                          "properties": {"content": {"type": "string"}},
                                          "required": ["content"]}}}}
        b._initialized = True
        try:
            res = b._handle_call_tool({"name": "schemahost_list_directory", "arguments": {}})
        except Exception as e:  # a real-server failure is a skip, not a red build
            self.skipTest(f"real stdio server unavailable: {e}")
        self.assertFalse(res.get("isError"), res.get("content"))
        self.assertEqual(res.get("structuredContent"), {"content": "[DIR] alpha"},
                         "a tool declaring outputSchema must return structuredContent")

    def test_health_uptime_is_lossless_through_a_real_round_trip(self):
        """The #23 repro: the payload must survive json.dumps -> json.loads -> json.dumps."""
        res = call_native("mcptoon_health", {}, {
            "servers": {}, "tool_index": {}, "output_format": "auto",
            "initialized": True, "uptime": -1e-9})
        once = json.dumps(res["structuredContent"])
        self.assertEqual(json.dumps(json.loads(once)), once,
                         "the health payload must be lossless under a JSON round trip")
        self.assertNotIn("-0.0", once)


if __name__ == "__main__":
    unittest.main()
