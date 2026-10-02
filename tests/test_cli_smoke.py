"""Smoke tests for the README's headline user path.

These are the only tests that run the *installed CLI* the way a first-time user
does: as a subprocess, in a throwaway HOME, over the exact commands the README
puts on its first screen. Unit tests call functions with every path injected;
this file deliberately injects nothing and lets the CLI pick its own defaults —
the layer where `install --pack` crashed for real users while the suite stayed
green (the default `packs_root()` path was never exercised by any test).

Every environment variable the CLI derives a *user* path from is redirected to a
temp dir, so nothing touches the developer's real ~/.mcptoon or any agent config.
On Windows that means HOME, USERPROFILE, **APPDATA and LOCALAPPDATA** — the CLI's
agent-config discovery reads %APPDATA% (discover.py: _appdata()), which a HOME
redirect alone does not move. Getting that wrong is how a test run once wrote
mcptoon's own entry into the developer's real Claude Desktop / Cline / VS Code
configs (2026-09-29); the guard below pins it.

The crash regression uses a user pack whose only tool has an unrecognised shape,
so no installer runs: zero network, zero side effects, but the exact default code
path a real pack takes.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _isolated_env(home: Path, minimal_path: bool = True) -> dict:
    """Every user-path root the CLI can read, pointed at ``home``.

    Kept in one place so a new test cannot silently reintroduce the
    APPDATA leak: the agent-load test below fails loudly if the CLI writes
    anywhere outside ``home``.

    ``minimal_path`` strips ``npx``/``uvx`` from PATH. `quickstart` spawns every
    zero-config server it discovers to list their tools; the first run has to
    download those npm/PyPI packages, which took **140 s** on the author's
    machine (vs 0.4 s for `discover`/`manifest`). With them off PATH the same
    command runs in well under a second, offline, and deterministically — a
    crash check should not depend on the network. The commands under test
    (`--version`, `quickstart`, `install --pack`) never need a runner.
    """
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)                       # Windows Path.home()
    env["APPDATA"] = str(home / "AppData" / "Roaming")   # discover._appdata()
    env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # Keep the CLI from spawning agents or asking for input in CI.
    env["MCPTOON_SKIP_SELF_HEAL"] = "1"
    env["MCPTOON_NO_TAKEOVER_OFFER"] = "1"
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(key, None)
    if minimal_path:
        # Just the interpreter's own directory: `python` still resolves, but
        # `npx`/`uvx` do not, so no server is spawned and no package downloaded.
        env["PATH"] = str(Path(sys.executable).parent)
    return env


class TestReadmeUserPath(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors: the CLI may leave a live npx/npm cache under
        # HOME, and Windows can briefly hold a handle on it while we tear down.
        # A failed rmtree of the *temp* dir must not fail an otherwise green run.
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self._td.name)
        self.env = _isolated_env(self.home)

    def tearDown(self):
        self._td.cleanup()

    def _mcptoon(self, *args, timeout=180):
        return subprocess.run([sys.executable, "-m", "mcptoon", *args],
                              capture_output=True, text=True,
                              env=self.env, timeout=timeout)

    def test_version_runs(self):
        r = self._mcptoon("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mcptoon", r.stdout.lower())

    def test_readme_first_command_does_not_crash(self):
        """`pip install mcptoon && mcptoon quickstart` — the README's first line."""
        r = self._mcptoon("quickstart", "--yes")
        out = r.stdout + r.stderr
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(r.returncode, 0, out)

    def test_install_pack_list_does_not_crash(self):
        r = self._mcptoon("install", "--packs")
        out = r.stdout + r.stderr
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(r.returncode, 0, out)

    def test_install_pack_uses_the_default_root_without_crashing(self):
        """Regression: the README's headline starter crashed with a TypeError.

        `packs.install_pack()` named its parameter `packs_root`, shadowing the
        module-level `packs_root()` function, so the default path
        `(packs_root or packs_root())` raised `'NoneType' object is not callable`
        before the prompt was written. The CLI calls `install_pack(pack)` with no
        destination, so a clean machine running `mcptoon install --pack essentials`
        got a raw traceback. Every unit test passed an explicit destination, which
        is why the suite missed it. The pack below has one tool of unknown shape,
        so no installer runs (offline, no side effects) but the default root path
        is exercised exactly as a real pack would exercise it.
        """
        catalog = {"version": 1, "packs": [{
            "name": "smoke",
            "title": "Smoke",
            "description": "offline regression pack",
            "tools": [{"name": "weird", "wat": "??"}],
            "prompt": "offline prompt",
        }]}
        cfg = self.home / ".mcptoon"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "packs.json").write_text(json.dumps(catalog), encoding="utf-8")

        r = self._mcptoon("install", "--pack", "smoke")
        out = r.stdout + r.stderr
        self.assertNotIn("Traceback", out, out)
        self.assertNotIn("TypeError", out, out)
        prompt = cfg / "packs" / "smoke" / "PROMPT.md"
        self.assertTrue(prompt.is_file(),
                        f"prompt was not written to the default root; output:\n{out[:2000]}")


class TestAgentLoadsTheGateway(unittest.TestCase):
    """The one thing mcptoon is *for*: an agent reads its config, spawns the
    entry mcptoon wrote, and reaches mcptoon's tools over MCP.

    Every other test stops at "the config file has the right JSON". That is not
    the same as "an agent can use it": the command could point at the wrong
    interpreter, `serve` could fail to start, or the handshake could answer with
    no tools. This test does the real thing — parse the written config, spawn
    that exact command as a subprocess, and speak the MCP handshake over stdio.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self._td.name)
        # Real PATH here: the point is that the *entry mcptoon writes* runs, and
        # on a machine with a runner it may name `npx`. The server we register
        # uses sys.executable, so the handshake itself needs no network.
        self.env = _isolated_env(self.home, minimal_path=False)

    def tearDown(self):
        self._td.cleanup()

    def _mcptoon(self, *args, timeout=180):
        return subprocess.run([sys.executable, "-m", "mcptoon", *args],
                              capture_output=True, text=True,
                              env=self.env, timeout=timeout)

    def _find_self_entry(self):
        """The gateway entry mcptoon wrote, wherever it landed under HOME.

        Two config shapes exist: Claude/Cline/Cursor use ``mcpServers``;
        VS Code uses ``mcp.servers``. We look for either, and fail loudly if
        the entry is missing — that alone is a real regression.
        """
        for path in self.home.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            servers = data.get("mcpServers")
            if not isinstance(servers, dict):
                mcp = data.get("mcp")
                servers = mcp.get("servers") if isinstance(mcp, dict) else None
            if isinstance(servers, dict) and "mcptoon" in servers:
                return path, servers["mcptoon"]
        return None, None

    def test_self_entry_is_written_and_the_handshake_succeeds(self):
        # A server must exist first: mcptoon only registers its own gateway
        # alongside real servers (an empty config has nothing to sit beside).
        # sys.executable keeps the registered command runnable with no download,
        # so the handshake below is offline and deterministic.
        add = self._mcptoon("add", "demo", "--stdio", sys.executable, "-m",
                            "mcptoon", "demo-server")
        self.assertEqual(add.returncode, 0, add.stdout + add.stderr)

        # `sync` now writes only where an agent is installed, and this temp HOME has
        # no agent — so make one exist. `detect_installed_agents` reads the host's
        # config *directories* (e.g. `~/.cursor`), so creating the parent is enough;
        # the file itself is what sync writes, and `_find_self_entry` looks for it.
        (self.home / ".cursor").mkdir(parents=True, exist_ok=True)

        sync = self._mcptoon("sync", "--self")
        self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)

        path, entry = self._find_self_entry()
        self.assertIsNotNone(entry,
                             f"no mcptoon gateway entry under {self.home}; "
                             f"sync output:\n{sync.stdout}")

        # 1) The entry must invoke mcptoon's serve — not some other command.
        argv = [entry.get("command", ""), *(entry.get("args") or [])]
        self.assertIn("mcptoon", " ".join(argv),
                      f"gateway entry does not run mcptoon: {argv}")
        self.assertIn("serve", argv, f"gateway entry is not `serve`: {argv}")

        # 2) Spawn that exact command and speak MCP over stdio.
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                env=self.env)
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2026-07-28", "capabilities": {},
                        "clientInfo": {"name": "smoke", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        payload = "".join(json.dumps(m) + "\n" for m in requests)
        try:
            out, err = proc.communicate(payload, timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            self.fail(f"`mcptoon serve` hung; stderr:\n{err[-1500:]}")

        responses = [json.loads(line) for line in out.splitlines() if line.strip()]
        by_id = {r.get("id"): r for r in responses if "id" in r}
        self.assertIn(1, by_id, f"no initialize reply; stdout:\n{out[:1500]}")
        self.assertIn("result", by_id[1], f"initialize failed: {by_id[1]}")
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "mcptoon")

        self.assertIn(2, by_id, f"no tools/list reply; stdout:\n{out[:1500]}")
        tools = by_id[2]["result"]["tools"]
        self.assertTrue(tools, "the gateway advertised zero tools")
        names = {t["name"] for t in tools}
        self.assertIn("mcptoon_manifest", names,
                      f"gateway is missing its own tools: {sorted(names)}")


class TestIsolationCoversEveryUserPathRoot(unittest.TestCase):
    """Guard: the temp HOME must capture *every* root the CLI can write under.

    On 2026-09-29 a probe run wrote mcptoon's gateway entry into the developer's
    real Claude Desktop, Cline and VS Code configs. The cause was not a bug in
    the CLI — it was a test that redirected HOME and USERPROFILE but not
    %APPDATA%, which is where the CLI's agent-config discovery looks on Windows.
    A HOME-only redirect is the intuitive thing to write and the wrong thing.

    This test does not trust the env dict; it asks the CLI itself what paths it
    would use, and fails if any of them escapes the temp home.
    """

    def test_cli_resolves_every_path_inside_the_temp_home(self):
        # The real defaults, from *this* test process's environment. On Windows
        # the temp home legitimately lives under the real profile's Temp, so
        # "inside the real home" is not the tell — "equal to the real default"
        # is.
        real_appdata = Path(os.environ.get("APPDATA", ""))
        real_config_dir = Path.home() / ".mcptoon"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            home = Path(td).resolve()
            env = _isolated_env(home)
            probe = (
                "import json, os\n"
                "from pathlib import Path\n"
                "from mcptoon import discover, config\n"
                "paths = {\n"
                "  'Path.home': str(Path.home()),\n"
                "  'discover._home': str(discover._home()),\n"
                "  'discover._appdata': str(discover._appdata()),\n"
                "  'config.HOME_DIR': str(config.HOME_DIR),\n"
                "  'config.CONFIG_DIR': str(config.CONFIG_DIR),\n"
                "}\n"
                "print(json.dumps(paths))\n"
            )
            r = subprocess.run([sys.executable, "-c", probe],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            resolved = json.loads(r.stdout)

            for label, value in resolved.items():
                p = Path(value).resolve()
                self.assertTrue(
                    str(p).startswith(str(home)),
                    f"{label} = {p} is outside the temp home {home} — the test "
                    f"env leaks into the real machine")
                if real_appdata:
                    self.assertNotEqual(p, real_appdata,
                                        f"{label} = {p} is the real APPDATA")
                self.assertNotEqual(p, real_config_dir,
                                    f"{label} = {p} is the real ~/.mcptoon")

    def test_appdata_is_redirected_not_just_home(self):
        """The exact regression: HOME set, APPDATA forgotten."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            home = Path(td).resolve()
            env = _isolated_env(home)
            self.assertEqual(Path(env["APPDATA"]).resolve(),
                             (home / "AppData" / "Roaming").resolve())
            # And the CLI must actually read it: no npx here, so discovery finds
            # nothing, but it must look in the temp AppData, not the real one.
            probe = ("from mcptoon import discover;"
                     "print(discover._appdata())")
            r = subprocess.run([sys.executable, "-c", probe],
                               capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(
                r.stdout.strip().startswith(str(home)),
                f"discover._appdata() = {r.stdout.strip()!r} escaped the temp home")


if __name__ == "__main__":
    unittest.main()
