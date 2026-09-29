"""Smoke tests for the README's headline user path.

These are the only tests that run the *installed CLI* the way a first-time user
does: as a subprocess, in a throwaway HOME, over the exact commands the README
puts on its first screen. Unit tests call functions with every path injected;
this file deliberately injects nothing and lets the CLI pick its own defaults —
the layer where `install --pack` crashed for real users while the suite stayed
green (the default `packs_root()` path was never exercised by any test).

HOME (and on Windows USERPROFILE) is redirected to a temp dir so nothing touches
the developer's real ~/.mcptoon or any agent config. The crash regression uses a
user pack whose only tool has an unrecognised shape, so no installer runs: zero
network, zero side effects, but the exact default code path a real pack takes.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestReadmeUserPath(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        home = Path(self._td.name)
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)          # Windows Path.home()
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # Keep the CLI from spawning agents or asking for input in CI.
        env["MCPTOON_SKIP_SELF_HEAL"] = "1"
        env["MCPTOON_NO_TAKEOVER_OFFER"] = "1"
        self.env = env
        self.home = home

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


if __name__ == "__main__":
    unittest.main()
