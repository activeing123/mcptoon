"""Tests for Agent Plugins installer (v0.7.1 phase 2).

Covers install / list / remove with full env isolation:
MCPTOON_PLUGINS_DIR / MCPTOON_PLUGINS_DATA_DIR / MCPTOON_PLUGINS_REGISTRY
redirect every side effect into a temp dir; MCPTOON_CONFIG_FILE points the
config layer at a temp file.
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
    install_plugin,
    list_plugins,
    remove_plugin,
)


def make_plugin(tmp: str, name="demo-greeter", version="1.0.0",
                extra_servers=None):
    root = Path(tmp)
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(json.dumps({
        "$schema": PLUGIN_SCHEMA_URL,
        "name": name,
        "version": version,
        "description": "installer test plugin",
    }), encoding="utf-8")
    servers = {
        "greeter": {
            "type": "stdio",
            "command": "./bin/run.sh",
            "args": ["--root", "${PLUGIN_ROOT}", "--data", "${PLUGIN_DATA}"],
            "env": {"HOME_DIR": "${PLUGIN_DATA}/state"},
            "cwd": "${PLUGIN_ROOT}/work",
        }
    }
    if extra_servers:
        servers.update(extra_servers)
    (root / "mcp.json").write_text(json.dumps({
        "$schema": MCP_SCHEMA_URL, "mcpServers": servers,
    }), encoding="utf-8")
    (root / "bin").mkdir(exist_ok=True)
    (root / "bin" / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    skills = root / "skills" / "greet"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "SKILL.md").write_text("---\nname: greet\n---\nhi\n", encoding="utf-8")
    return str(root)


class _Isolated(unittest.TestCase):
    """Redirect all plugin/config side effects into a temp sandbox."""

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        self.base = Path(self.sandbox.name)
        self._old = {
            k: os.environ.get(k)
            for k in ("MCPTOON_PLUGINS_DIR", "MCPTOON_PLUGINS_DATA_DIR",
                      "MCPTOON_PLUGINS_REGISTRY", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML", "MCPTOON_SYNC_HOME",
                      "MCPTOON_NO_SYNC", "HOME", "USERPROFILE")
        }
        os.environ["MCPTOON_PLUGINS_DIR"] = str(self.base / "plugins")
        os.environ["MCPTOON_PLUGINS_DATA_DIR"] = str(self.base / "plugins-data")
        os.environ["MCPTOON_PLUGINS_REGISTRY"] = str(self.base / "plugins.json")
        # Point the config layer's ~/.mcptoon at the sandbox
        fake_home = self.base / "home"
        fake_home.mkdir()
        (fake_home / ".mcptoon").mkdir()
        os.environ["MCPTOON_CONFIG_FILE"] = str(fake_home / ".mcptoon" / "config.json")
        self._fake_home = fake_home

    def tearDown(self):
        self.sandbox.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestInstall(_Isolated):
    def test_install_full_flow(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)
            r = install_plugin(src, sync_agents=False)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["name"], "demo-greeter")
            self.assertEqual(r["version"], "1.0.0")
            self.assertEqual(r["servers"], ["demo-greeter:greeter"])
            self.assertEqual(r["skills"], ["greet"])

            # plugin dir copied
            dest = Path(r["dest"])
            self.assertTrue((dest / "plugin.json").is_file())
            self.assertTrue((dest / "bin" / "run.sh").is_file())
            # persistent data dir created
            self.assertTrue(Path(r["data_dir"]).is_dir())

            # config.json: namespace entry with pre-expanded paths
            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            entry = cfg["servers"]["demo-greeter:greeter"]
            self.assertEqual(entry["transport"], "stdio")
            self.assertEqual(entry["command"], ["./bin/run.sh"])
            self.assertEqual(entry["args"][0], "--root")
            self.assertEqual(entry["args"][1], str(dest))          # PLUGIN_ROOT expanded
            self.assertEqual(entry["args"][3], str(Path(r["data_dir"])))  # PLUGIN_DATA expanded
            self.assertEqual(entry["env"]["HOME_DIR"], str(Path(r["data_dir"]) / "state"))
            self.assertEqual(entry["cwd"], str(dest / "work"))
            # pool env injection markers present
            self.assertEqual(entry["plugin_root"], str(dest))
            self.assertEqual(entry["plugin_data"], str(Path(r["data_dir"])))
            # no raw placeholders survive anywhere in the entry
            self.assertNotIn("${PLUGIN_ROOT}", json.dumps(entry))
            self.assertNotIn("${PLUGIN_DATA}", json.dumps(entry))

    def test_install_conflict_then_force(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src, version="1.0.0")
            self.assertTrue(install_plugin(src, sync_agents=False)["ok"])
            r = install_plugin(src, sync_agents=False)
            self.assertFalse(r["ok"])
            self.assertEqual(r["stage"], "conflict")
            # force upgrade keeps the data dir
            data_dir = Path(self.base) / "plugins-data" / "demo-greeter"
            (data_dir / "user-state.json").write_text("{}", encoding="utf-8")
            r2 = install_plugin(src, force=True, sync_agents=False)
            self.assertTrue(r2["ok"])
            self.assertTrue((data_dir / "user-state.json").is_file())
            self.assertEqual(r2["version"], "1.0.0")

    def test_install_invalid_rejected(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)
            Path(src, "plugin.json").write_text('{"$schema": "x", "name": "!"}',
                                                encoding="utf-8")
            r = install_plugin(src, sync_agents=False)
            self.assertFalse(r["ok"])
            self.assertEqual(r["stage"], "scan")
            self.assertTrue(r["fatal"])
            # nothing was copied or registered
            self.assertEqual(list_plugins(), [])
            self.assertFalse((Path(self.base) / "plugins").exists())

    def test_install_http_server_entry(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src, extra_servers={
                "remote": {"type": "streamable-http",
                           "url": "https://example.com/mcp",
                           "headers": {"X-Trace": "1"}},
            })
            r = install_plugin(src, sync_agents=False)
            self.assertTrue(r["ok"])
            self.assertEqual(
                r["servers"], ["demo-greeter:greeter", "demo-greeter:remote"])
            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            entry = cfg["servers"]["demo-greeter:remote"]
            self.assertEqual(entry["transport"], "http")
            self.assertEqual(entry["url"], "https://example.com/mcp")
            self.assertEqual(entry["headers"], {"X-Trace": "1"})

    def test_registry_recorded(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)
            install_plugin(src, sync_agents=False)
            reg = json.loads(
                Path(os.environ["MCPTOON_PLUGINS_REGISTRY"]).read_text(encoding="utf-8"))
            self.assertIn("demo-greeter", reg)
            self.assertEqual(reg["demo-greeter"]["version"], "1.0.0")
            self.assertEqual(reg["demo-greeter"]["servers"], ["demo-greeter:greeter"])
            self.assertTrue(reg["demo-greeter"]["installed_at"])


class TestListRemove(_Isolated):
    def test_list_empty(self):
        self.assertEqual(list_plugins(), [])

    def test_list_and_remove_roundtrip(self):
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)
            install_plugin(src, sync_agents=False)
            plugins = list_plugins()
            self.assertEqual(len(plugins), 1)
            self.assertEqual(plugins[0]["name"], "demo-greeter")
            self.assertEqual(plugins[0]["servers"], ["demo-greeter:greeter"])

            r = remove_plugin("demo-greeter", sync_agents=False)
            self.assertTrue(r["ok"])
            self.assertEqual(r["removed_servers"], ["demo-greeter:greeter"])
            # plugin dir gone, data dir KEPT (spec: persistent storage)
            self.assertFalse((Path(self.base) / "plugins" / "demo-greeter").exists())
            self.assertTrue((Path(self.base) / "plugins-data" / "demo-greeter").is_dir())
            self.assertEqual(list_plugins(), [])

            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            self.assertNotIn("demo-greeter:greeter", cfg["servers"])

    def test_remove_unknown(self):
        r = remove_plugin("never-installed", sync_agents=False)
        self.assertFalse(r["ok"])

    def test_remove_defensive_namespace_sweep(self):
        """Entries left in config without a registry record still get removed."""
        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)
            install_plugin(src, sync_agents=False)
            # corrupt the registry: drop the server list
            reg_path = os.environ["MCPTOON_PLUGINS_REGISTRY"]
            reg = json.loads(Path(reg_path).read_text(encoding="utf-8"))
            reg["demo-greeter"]["servers"] = []
            Path(reg_path).write_text(json.dumps(reg), encoding="utf-8")

            r = remove_plugin("demo-greeter", sync_agents=False)
            self.assertTrue(r["ok"])
            self.assertEqual(r["removed_servers"], ["demo-greeter:greeter"])
            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            self.assertNotIn("demo-greeter:greeter", cfg["servers"])


class TestCliPluginEndToEnd(_Isolated):
    """The acceptance path: scan → install → list → config → remove."""

    def test_cli_end_to_end(self):
        import subprocess
        env = dict(os.environ)

        with tempfile.TemporaryDirectory() as src:
            make_plugin(src)

            def run(*cli_args):
                return subprocess.run(
                    [sys.executable, "-m", "mcptoon", "plugin", *cli_args],
                    capture_output=True, text=True, timeout=90, env=env,
                )

            # scan → exit 0
            r = run("scan", src)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            # install → exit 0
            r = run("install", src, "--no-sync")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("demo-greeter", r.stdout)

            # list → shows the plugin
            r = run("list")
            self.assertIn("demo-greeter", r.stdout)
            self.assertIn("demo-greeter:greeter", r.stdout)

            # config check: pre-expanded absolute paths
            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            entry = cfg["servers"]["demo-greeter:greeter"]
            self.assertNotIn("${", json.dumps(entry))
            self.assertTrue(Path(entry["args"][1]).is_absolute())

            # remove → exit 0, config clean
            r = run("remove", "demo-greeter", "--no-sync")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            cfg = json.loads(Path(os.environ["MCPTOON_CONFIG_FILE"]).read_text(encoding="utf-8"))
            self.assertNotIn("demo-greeter:greeter", cfg["servers"])


if __name__ == "__main__":
    unittest.main()
