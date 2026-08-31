"""Tests for Agent Plugins 1.0.0 support (v0.7.1 phase 1).

Covers plugin.json / mcp.json validation, failure classification
(fatal vs skippable entry), placeholder rules and skills discovery.
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

from mcptoon.plugin import (
    MCP_SCHEMA_URL,
    PLUGIN_SCHEMA_URL,
    expand_placeholders,
    scan_plugin,
)


def make_plugin(tmp: str, manifest=None, mcp_json="KEEP", skills=("greet",),
                mcp_override=None):
    """Build a plugin fixture in tmp. mcp_json=None omits the file."""
    root = Path(tmp)
    root.mkdir(parents=True, exist_ok=True)

    if manifest is None:
        manifest = {
            "$schema": PLUGIN_SCHEMA_URL,
            "name": "hello-greet",
            "version": "1.0.0",
            "description": "A greeting plugin",
        }
    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    if mcp_json == "KEEP":
        mcp = mcp_override if mcp_override is not None else {
            "$schema": MCP_SCHEMA_URL,
            "mcpServers": {
                "greeter": {
                    "type": "stdio",
                    "command": "./bin/run.sh",
                    "args": ["--root", "${PLUGIN_ROOT}", "--data", "${PLUGIN_DATA}"],
                    "env": {"GREET_LANG": "en"},
                    "cwd": "${PLUGIN_DATA}/cache",
                }
            },
        }
        (root / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    elif mcp_json is not None:
        (root / "mcp.json").write_text(mcp_json, encoding="utf-8")

    for skill in skills or ():
        d = root / "skills" / skill
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text("---\nname: x\n---\nbody", encoding="utf-8")

    return str(root)


class TestValidPlugins(unittest.TestCase):
    def test_minimal_manifest_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_json=None, skills=())
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["fatal"], [])
            self.assertEqual(r["plugin"]["name"], "hello-greet")

    def test_full_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp)
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["plugin"]["name"], "hello-greet")
            self.assertEqual(r["plugin"]["version"], "1.0.0")
            self.assertEqual(r["skills"], ["greet"])
            self.assertEqual(r["servers"], [{"name": "greeter", "type": "stdio"}])
            self.assertEqual(r["skipped_servers"], [])

    def test_two_skills_and_remote_servers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(
                tmp,
                skills=("greet", "farewell"),
                mcp_override={
                    "$schema": MCP_SCHEMA_URL,
                    "mcpServers": {
                        "api": {"type": "streamable-http",
                                "url": "https://example.com/mcp"},
                        "old": {"type": "sse",
                                "url": "http://localhost:9933/sse",
                                "headers": {"X-Trace": "1"}},
                    },
                },
            )
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["skills"], ["farewell", "greet"])
            self.assertEqual(len(r["servers"]), 2)
            types = {s["name"]: s["type"] for s in r["servers"]}
            self.assertEqual(types["api"], "streamable-http")
            self.assertEqual(types["old"], "sse")

    def test_loopback_http_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"local": {"type": "sse",
                                         "url": "http://127.0.0.1:8080/sse"}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"][0]["name"], "local")


class TestFatalProblems(unittest.TestCase):
    def test_missing_dir(self):
        r = scan_plugin("Z:/definitely/not/here")
        self.assertFalse(r["ok"])
        self.assertEqual(r["fatal"][0]["code"], "PLUGIN_DIR_MISSING")

    def test_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "mcp.json").write_text("{}", encoding="utf-8")
            r = scan_plugin(tmp)
            self.assertFalse(r["ok"])
            self.assertEqual(r["fatal"][0]["code"], "MANIFEST_MISSING")

    def test_invalid_json_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "plugin.json").write_text("{not json", encoding="utf-8")
            r = scan_plugin(tmp)
            self.assertFalse(r["ok"])
            self.assertEqual(r["fatal"][0]["code"], "MANIFEST_INVALID")

    def test_wrong_schema_url_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, manifest={
                "$schema": "https://agent-plugins.org/schemas/1.1.0/plugin.schema.json",
                "name": "hello",
            })
            r = scan_plugin(p)
            self.assertFalse(r["ok"])
            self.assertTrue(any(f["code"] == "SCHEMA_MISMATCH" for f in r["fatal"]))

    def test_name_rules(self):
        bad_names = ["Hello", "-lead", "trail-", "a--b", "a..b", "a b", "", "x" * 65]
        for n in bad_names:
            with tempfile.TemporaryDirectory() as tmp, self.subTest(name=n):
                p = make_plugin(tmp, manifest={
                    "$schema": PLUGIN_SCHEMA_URL, "name": n})
                r = scan_plugin(p)
                self.assertFalse(r["ok"])
                codes = {f["code"] for f in r["fatal"]}
                # empty → NAME_MISSING; malformed → NAME_INVALID
                self.assertTrue(codes & {"NAME_INVALID", "NAME_MISSING"},
                                f"name={n!r}: got {codes}")

    def test_good_name_boundaries(self):
        ok_names = ["a", "9", "a.b-c9", "x" * 64]
        for n in ok_names:
            with tempfile.TemporaryDirectory() as tmp, self.subTest(name=n):
                p = make_plugin(tmp, manifest={
                    "$schema": PLUGIN_SCHEMA_URL, "name": n})
                r = scan_plugin(p)
                self.assertTrue(r["ok"], r["fatal"])

    def test_typed_field_violations_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, manifest={
                "$schema": PLUGIN_SCHEMA_URL, "name": "ok-name",
                "version": 12, "keywords": "not-a-list",
            })
            r = scan_plugin(p)
            self.assertFalse(r["ok"])
            codes = {f["code"] for f in r["fatal"]}
            self.assertIn("VERSION_INVALID", codes)
            self.assertIn("KEYWORDS_INVALID", codes)


class TestNonFatalSkippable(unittest.TestCase):
    def test_unknown_top_level_field_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, manifest={
                "$schema": PLUGIN_SCHEMA_URL, "name": "hello",
                "displayName": "Hello!",  # 1.1.0 draft field → warning
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            codes = [w["code"] for w in r["warnings"]]
            self.assertIn("UNKNOWN_FIELD", codes)

    def test_reserved_env_key_skips_entry_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {
                    "bad": {"type": "stdio", "command": "run",
                            "env": {"PLUGIN_ROOT": "/hack"}},
                    "good": {"type": "stdio", "command": "run2"},
                },
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"], r["fatal"])
            self.assertEqual([s["name"] for s in r["servers"]], ["good"])
            self.assertEqual(r["skipped_servers"][0]["name"], "bad")

    def test_shell_string_command_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"sh": {"type": "stdio",
                                      "command": "python -c 'print(1)'"}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])
            self.assertEqual(len(r["skipped_servers"]), 1)

    def test_command_placeholder_forbidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"x": {"type": "stdio",
                                     "command": "${PLUGIN_ROOT}/run.sh"}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])

    def test_absolute_command_forbidden(self):
        for cmd in ("/usr/bin/python", "C:\\tools\\run.exe", "~/run.sh"):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(cmd=cmd):
                p = make_plugin(tmp, mcp_override={
                    "$schema": MCP_SCHEMA_URL,
                    "mcpServers": {"x": {"type": "stdio", "command": cmd}},
                })
                r = scan_plugin(p)
                self.assertTrue(r["ok"])
                self.assertEqual(r["servers"], [])

    def test_non_https_url_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"insecure": {"type": "streamable-http",
                                            "url": "http://example.com/mcp"}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])

    def test_url_userinfo_and_fragment_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {
                    "a": {"type": "sse", "url": "https://user:pw@example.com/mcp"},
                    "b": {"type": "sse", "url": "https://example.com/mcp#frag"},
                },
            })
            r = scan_plugin(p)
            self.assertEqual(len(r["skipped_servers"]), 2)

    def test_credential_header_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"leaky": {
                    "type": "streamable-http",
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer sk-123"}},
                },
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])

    def test_variant_mixing_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"mix": {"type": "stdio", "command": "run",
                                       "url": "https://example.com"}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])

    def test_bad_cwd_form_skipped(self):
        for cwd in ("/abs/path", "relative", "${OTHER}/x", "${PLUGIN_ROOT}/../up"):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(cwd=cwd):
                p = make_plugin(tmp, mcp_override={
                    "$schema": MCP_SCHEMA_URL,
                    "mcpServers": {"x": {"type": "stdio", "command": "run",
                                         "cwd": cwd}},
                })
                r = scan_plugin(p)
                self.assertEqual(r["servers"], [], f"cwd={cwd} should skip")

    def test_mcp_json_closed_top_level_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL, "mcpServers": {}, "extra": True,
            })
            r = scan_plugin(p)
            self.assertFalse(r["ok"])
            self.assertTrue(
                any(f["code"] == "MCP_JSON_UNKNOWN_FIELD" for f in r["fatal"]))

    def test_mcp_json_wrong_schema_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={"$schema": "x", "mcpServers": {}})
            r = scan_plugin(p)
            self.assertFalse(r["ok"])

    def test_empty_mcpservers_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={"$schema": MCP_SCHEMA_URL,
                                               "mcpServers": {}})
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [])


class TestPlaceholders(unittest.TestCase):
    def test_expand_both_vars(self):
        out = expand_placeholders("${PLUGIN_ROOT}/bin:${PLUGIN_DATA}/cache",
                                  "/opt/p", "/home/u/.data")
        self.assertEqual(out, "/opt/p/bin:/home/u/.data/cache")

    def test_non_recursive(self):
        # Root literally contains the other placeholder text → must stay unexpanded
        out = expand_placeholders("${PLUGIN_ROOT}/x",
                                  '/tmp/${PLUGIN_DATA}', "/d")
        self.assertEqual(out, '/tmp/${PLUGIN_DATA}/x')

    def test_unknown_var_in_args_warns_but_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, mcp_override={
                "$schema": MCP_SCHEMA_URL,
                "mcpServers": {"x": {"type": "stdio", "command": "run",
                                     "args": ["--ws", "${WORKSPACE_ROOT}"]}},
            })
            r = scan_plugin(p)
            self.assertTrue(r["ok"])
            self.assertEqual(r["servers"], [{"name": "x", "type": "stdio"}])
            self.assertTrue(any(w["code"] == "UNKNOWN_PLACEHOLDER"
                                for w in r["warnings"]))


class TestSkillsDiscovery(unittest.TestCase):
    def test_incomplete_skill_dir_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_plugin(tmp)
            (root / "skills" / "empty").mkdir()
            r = scan_plugin(tmp)
            self.assertTrue(r["ok"])
            self.assertEqual(r["skills"], ["greet"])
            self.assertTrue(any(w["code"] == "SKILL_INCOMPLETE"
                                for w in r["warnings"]))

    def test_skills_not_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_plugin(tmp)
            nested = root / "skills" / "greet" / "sub"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text("x", encoding="utf-8")
            r = scan_plugin(tmp)
            self.assertEqual(r["skills"], ["greet"])


class TestCliScan(unittest.TestCase):
    def test_cli_scan_valid_exit0(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp)
            proc = subprocess.run(
                [sys.executable, "-m", "mcptoon", "plugin", "scan", p],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("hello-greet", proc.stdout)
            self.assertIn("Valid plugin", proc.stdout)

    def test_cli_scan_fatal_exit1(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            p = make_plugin(tmp, manifest={"$schema": PLUGIN_SCHEMA_URL,
                                           "name": "Bad--Name"})
            proc = subprocess.run(
                [sys.executable, "-m", "mcptoon", "plugin", "scan", p],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("rejected", proc.stdout)


if __name__ == "__main__":
    unittest.main()
