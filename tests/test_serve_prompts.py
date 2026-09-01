"""Tests for Agent Plugin skills exposed as MCP prompts via `mcptoon serve`.

Serves the bridge in isolation: no real servers are contacted — the tool
index is left empty and only the prompts surface is exercised.
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


class TestSkillPrompts(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        base = Path(self.sandbox.name)
        self.plugins = base / "plugins"
        self._old = {
            k: os.environ.get(k)
            for k in ("MCPTOON_PLUGINS_DIR", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML")
        }
        os.environ["MCPTOON_PLUGINS_DIR"] = str(self.plugins)
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")

        # Install layout: <plugin>/skills/<skill>/SKILL.md
        skill = self.plugins / "demo" / "skills" / "greet"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: greet\ndescription: Say hello properly\n---\n"
            "## Greeting protocol\n\n1. bow\n2. smile\n", encoding="utf-8")
        # Second plugin, skill without frontmatter (dir-name fallback)
        skill2 = self.plugins / "other" / "skills" / "bare"
        skill2.mkdir(parents=True)
        (skill2 / "SKILL.md").write_text("Just some instructions\n",
                                         encoding="utf-8")

    def tearDown(self):
        self.sandbox.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _bridge(self):
        from mcptoon.serve import MCPServerBridge

        b = MCPServerBridge()
        b._ensure_initialized()
        return b

    def test_prompts_list_namespaced(self):
        b = self._bridge()
        result = b._handle_list_prompts()
        names = [p["name"] for p in result["prompts"]]
        self.assertEqual(names, ["demo_greet", "other_bare"])
        by_name = {p["name"]: p for p in result["prompts"]}
        self.assertEqual(by_name["demo_greet"]["description"],
                         "Say hello properly")

    def test_prompts_get_returns_body(self):
        b = self._bridge()
        result = b._handle_get_prompt({"name": "demo_greet"})
        self.assertIsNotNone(result)
        msg = result["messages"][0]
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["content"]["type"], "text")
        self.assertIn("Greeting protocol", msg["content"]["text"])
        self.assertIn("bow", msg["content"]["text"])
        # frontmatter must not leak into the body
        self.assertNotIn("description:", msg["content"]["text"])

    def test_prompts_get_unknown_returns_none(self):
        b = self._bridge()
        self.assertIsNone(b._handle_get_prompt({"name": "nope"}))

    def test_prompt_without_frontmatter_falls_back_to_dirname(self):
        b = self._bridge()
        result = b._handle_get_prompt({"name": "other_bare"})
        self.assertIn("Just some instructions", result["messages"][0]
                      ["content"]["text"])

    def test_no_plugins_dir_means_empty_prompts(self):
        os.environ["MCPTOON_PLUGINS_DIR"] = str(
            Path(self.sandbox.name) / "missing")
        b = self._bridge()
        self.assertEqual(b._handle_list_prompts()["prompts"], [])

    def test_initialize_advertises_prompts_capability(self):
        from mcptoon.serve import MCPServerBridge

        b = MCPServerBridge()
        caps = b._handle_initialize({})["capabilities"]
        self.assertIn("prompts", caps)

    def test_handle_request_dispatch_prompts(self):
        """Full dispatch path: prompts/list & prompts/get through
        handle_request produce valid JSON-RPC responses."""
        b = self._bridge()
        out: list = []
        from mcptoon import serve as serve_mod
        orig = serve_mod._send_response
        serve_mod._send_response = out.append
        try:
            b._handle_request({"jsonrpc": "2.0", "id": 1,
                               "method": "prompts/list", "params": {}})
            b._handle_request({"jsonrpc": "2.0", "id": 2, "method":
                               "prompts/get", "params": {"name": "demo_greet"}})
            b._handle_request({"jsonrpc": "2.0", "id": 3, "method":
                               "prompts/get", "params": {"name": "nope"}})
        finally:
            serve_mod._send_response = orig
        self.assertEqual(len(out), 3)
        self.assertNotIn("error", out[0])
        self.assertEqual(out[0]["id"], 1)
        names = [p["name"] for p in out[0]["result"]["prompts"]]
        self.assertEqual(names, ["demo_greet", "other_bare"])
        self.assertNotIn("error", out[1])
        self.assertIn("Greeting protocol",
                      out[1]["result"]["messages"][0]["content"]["text"])
        self.assertEqual(out[2]["error"]["code"], -32602)

    def test_json_serializable(self):
        b = self._bridge()
        json.dumps(b._handle_list_prompts())
        json.dumps(b._handle_get_prompt({"name": "demo_greet"}))


if __name__ == "__main__":
    unittest.main()
