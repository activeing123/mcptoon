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

"""End-to-end `mcptoon off` / `mcptoon uninstall`, in a home that is not yours.

`tests/test_reversible.py` exercises these commands in-process with patched paths.
That is the right level for logic, but it cannot show that the *installed* command
actually does what it says: process startup, argument dispatch, the real write
paths, and the real deletion all sit outside those unit tests. This file runs
`python -m mcptoon uninstall --yes` as a subprocess against a fabricated home.

The isolation is total, and that matters more here than anywhere else, because the
code under test deletes files:

  - `USERPROFILE` relocates `sync._home()`, which is what every agent path under
    `~` is built from (`.cursor`, `.codeium`, ...).
  - `APPDATA` relocates `sync._appdata()`, which is what Claude Desktop, Cline and
    VS Code Copilot paths are built from.
  - `MCPTOON_*` relocate mcptoon's own files and its cache.

With all of those pointed at a temp directory, `uninstall --yes` has nowhere real
to reach — which is itself part of what these tests assert, by checking afterwards
that the developer's actual `~/.mcptoon/config.json` and agent configs are byte-for
-byte unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_USER_SERVER = {"transport": "stdio", "command": "npx", "args": ["-y", "mine"]}
_GATEWAY = {"command": sys.executable, "args": ["-m", "mcptoon", "serve"]}
# What the developer's machine must still look like when these tests are done.
_REAL_HOME = Path.home()


class _FakeHome:
    """A throwaway home with mcptoon installed into it and one user server."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.appdata = self.root / "appdata"
        self.cache = self.home / ".cache" / "mcptoon"
        self.cursor = self.home / ".cursor" / "mcp.json"
        self.server_config = self.home / ".mcptoon" / "config.json"
        self.settings = self.home / ".mcptoon" / "settings.json"
        self.welcome = self.home / ".mcptoon" / ".welcome"
        for d in (self.cache, self.cursor.parent, self.server_config.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.server_config.write_text(
            json.dumps({"servers": {"mine": _USER_SERVER}}), encoding="utf-8")
        self.settings.write_text(json.dumps({"footer": "on"}), encoding="utf-8")
        self.welcome.write_text("", encoding="utf-8")
        (self.cache / "manifest.json").write_text("{}", encoding="utf-8")
        self.cursor.write_text(json.dumps(
            {"mcpServers": {"mcptoon": _GATEWAY, "mine": _USER_SERVER}}), encoding="utf-8")

    def cleanup(self):
        self._tmp.cleanup()

    def env(self) -> dict:
        env = dict(os.environ)
        env.update({
            "USERPROFILE": str(self.home),
            "APPDATA": str(self.appdata),
            "MCPTOON_CONFIG_FILE": str(self.server_config),
            "MCPTOON_CONFIG_FILE_TOML": str(self.home / ".mcptoon" / "config.toml"),
            "MCPTOON_SETTINGS_FILE": str(self.settings),
            "MCPTOON_WELCOME_FILE": str(self.welcome),
            "MCPTOON_SELFHEAL_FILE": str(self.home / ".mcptoon" / ".selfheal"),
            "MCPTOON_FOOTER_STATE_FILE": str(self.home / ".mcptoon" / "footer-state.json"),
            "MCPTOON_TOGGLE_FILE": str(self.home / ".mcptoon" / "toggles.json"),
            "MCPTOON_COMPRESSION_FILE": str(self.home / ".mcptoon" / "compression.json"),
            "MCPTOON_CACHE_DIR": str(self.cache),
        })
        return env

    def run(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "mcptoon", *args],
                              capture_output=True, text=True, env=self.env(),
                              cwd=str(ROOT), timeout=180)

    def cursor_servers(self) -> dict:
        return json.loads(self.cursor.read_text(encoding="utf-8"))["mcpServers"]

    def config_servers(self) -> dict:
        return json.loads(self.server_config.read_text(encoding="utf-8"))["servers"]


class _RealHomeUntouched(unittest.TestCase):
    """Shared guard: prove these tests left the developer's machine alone."""

    def _snapshot_real(self) -> dict:
        out = {}
        for p in (_REAL_HOME / ".mcptoon" / "config.json",
                  _REAL_HOME / ".mcptoon" / "settings.json",
                  _REAL_HOME / ".cursor" / "mcp.json"):
            out[str(p)] = p.read_text(encoding="utf-8") if p.exists() else None
        return out

    def setUp(self):
        self._before = self._snapshot_real()
        self.addCleanup(self._assert_real_home_untouched)

    def _assert_real_home_untouched(self):
        after = self._snapshot_real()
        for path, content in self._before.items():
            self.assertEqual(after[path], content,
                             f"this test modified the developer's real {path}")


class TestUninstallEndToEnd(_RealHomeUntouched):
    def setUp(self):
        super().setUp()
        self.fake = _FakeHome()
        self.addCleanup(self.fake.cleanup)

    def test_dry_run_reports_the_plan_and_removes_nothing(self):
        proc = self.fake.run("uninstall", "--dry")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("DRY RUN", out)
        self.assertIn("KEEP config.json", out)
        self.assertTrue(self.fake.server_config.exists())
        self.assertTrue(self.fake.settings.exists())
        self.assertTrue(self.fake.welcome.exists())
        self.assertTrue(self.fake.cache.exists())
        self.assertIn("mcptoon", self.fake.cursor_servers())

    def test_yes_cleans_bookkeeping_and_gateway_but_keeps_servers(self):
        proc = self.fake.run("uninstall", "--yes")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("Removed the gateway", out)
        self.assertIn("Kept your server definitions", out)

        # Gone: mcptoon's own state and the regenerable cache.
        self.assertFalse(self.fake.settings.exists(), "settings.json survived")
        self.assertFalse(self.fake.welcome.exists(), "the first-run marker survived")
        self.assertFalse(self.fake.cache.exists(), "the cache directory survived")

        # Kept: the servers the user configured, on both sides.
        self.assertTrue(self.fake.server_config.exists(),
                        "uninstall deleted the user's server definitions")
        self.assertEqual(list(self.fake.config_servers()), ["mine"])

        # The gateway entry is gone from the agent; the user's server is not.
        servers = self.fake.cursor_servers()
        self.assertNotIn("mcptoon", servers)
        self.assertIn("mine", servers, "uninstall removed a user's agent server")

    def test_no_keep_config_removes_the_server_definitions_too(self):
        proc = self.fake.run("uninstall", "--yes", "--no-keep-config")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(self.fake.server_config.exists(),
                         "--no-keep-config must actually delete the server config")

    def test_refuses_when_stdin_is_a_pipe(self):
        """The CI case: piped stdin means we cannot ask, so refuse outright."""
        proc = subprocess.run([sys.executable, "-m", "mcptoon", "uninstall"],
                              capture_output=True, text=True, env=self.fake.env(),
                              cwd=str(ROOT), input="", timeout=180)
        self.assertIn("Refusing to delete without confirmation", proc.stdout)
        self.assertIn("--yes", proc.stdout)
        self._assert_nothing_removed()

    def test_refuses_when_stdin_is_the_null_device(self):
        """With stdin=DEVNULL the tool must refuse — by whichever route the OS takes.

        Windows quirk: NUL is a *character device*, so `isatty()` is True there.
        The `not sys.stdin.isatty()` guard therefore does not fire for
        `stdin=DEVNULL` — the prompt runs, `input()` raises EOFError, and the answer
        becomes empty, which is not "yes". On Linux/macOS DEVNULL makes `isatty()`
        False, so the earlier guard fires instead. Both are refusals; the point of
        pinning it is that the safety property must not depend on `isatty()` being a
        reliable test for "nobody is there to answer".
        """
        proc = subprocess.run([sys.executable, "-m", "mcptoon", "uninstall"],
                              capture_output=True, text=True, env=self.fake.env(),
                              cwd=str(ROOT), stdin=subprocess.DEVNULL, timeout=180)
        self.assertTrue(
            "nothing was removed" in proc.stdout
            or "Refusing to delete without confirmation" in proc.stdout,
            f"DEVNULL must be refused by one of the two routes, got:\n{proc.stdout}")
        self.assertNotIn("✓", proc.stdout, "it claimed to have removed something")
        self._assert_nothing_removed()

    def _assert_nothing_removed(self):
        self.assertTrue(self.fake.settings.exists())
        self.assertTrue(self.fake.welcome.exists())
        self.assertTrue(self.fake.cache.exists())
        self.assertTrue(self.fake.server_config.exists())
        self.assertIn("mcptoon", self.fake.cursor_servers())

    def test_is_idempotent(self):
        first = self.fake.run("uninstall", "--yes")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.fake.run("uninstall", "--yes")
        self.assertEqual(second.returncode, 0,
                         f"a second uninstall must not crash:\n{second.stderr}")
        self.assertTrue(self.fake.server_config.exists())


class TestOffEndToEnd(_RealHomeUntouched):
    def setUp(self):
        super().setUp()
        self.fake = _FakeHome()
        self.addCleanup(self.fake.cleanup)

    def test_off_removes_only_the_gateway(self):
        proc = self.fake.run("off")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("removed the gateway entry", proc.stdout)

        servers = self.fake.cursor_servers()
        self.assertNotIn("mcptoon", servers)
        self.assertIn("mine", servers)

        # Everything mcptoon owns is untouched — `off` is not a cleanup.
        self.assertTrue(self.fake.server_config.exists())
        self.assertTrue(self.fake.settings.exists())
        self.assertTrue(self.fake.welcome.exists())
        self.assertTrue(self.fake.cache.exists())

    def test_off_then_sync_self_is_a_round_trip(self):
        self.assertEqual(self.fake.run("off").returncode, 0)
        self.assertNotIn("mcptoon", self.fake.cursor_servers())

        back = self.fake.run("sync", "--self")
        self.assertEqual(back.returncode, 0, back.stderr)
        servers = self.fake.cursor_servers()
        self.assertIn("mcptoon", servers, "sync --self did not restore the gateway")
        self.assertIn("mine", servers)

    def test_status_reflects_the_gateway_state(self):
        self.assertIn("yes", self._gateway_line())
        self.assertEqual(self.fake.run("off").returncode, 0)
        self.assertIn("no", self._gateway_line())

    def _gateway_line(self) -> str:
        proc = self.fake.run("status")
        for line in proc.stdout.splitlines():
            if "Gateway in agents" in line:
                return line
        self.fail(f"status printed no gateway line:\n{proc.stdout}")

    def test_agent_config_keeps_its_backup(self):
        """The pre-change state stays one copy away — the reversibility promise."""
        self.assertIn("mcptoon", self.fake.cursor_servers())
        self.assertEqual(self.fake.run("off").returncode, 0)
        backups = list(self.fake.cursor.parent.glob("mcp.json.bak*"))
        self.assertTrue(backups, "off wrote no backup of the agent config")
        restored = json.loads(backups[0].read_text(encoding="utf-8"))["mcpServers"]
        self.assertIn("mcptoon", restored, "the backup does not predate the change")


if __name__ == "__main__":
    unittest.main()
