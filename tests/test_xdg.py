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

"""XDG Base Directory support for mcptoon's own files (issue #25).

The issue asked for four things, and each one gets a test here:

1. `$XDG_CONFIG_HOME` / `$XDG_STATE_HOME` / `$XDG_CACHE_HOME` are honoured.
2. Unset XDG variables fall back to the pre-XDG layout, so nothing breaks.
3. `MCPTOON_HOME` and `--dir` are explicit overrides.
4. The legacy `~/.mcptoon` is not created once every location has been
   overridden.

These tests do not import `mcptoon.config` in-process: the module computes its
roots at import time, so every case has to be observed in a fresh interpreter.
Each case therefore runs a small subprocess with a controlled environment,
which is also how the original report reproduced the bug.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Prints the resolved roots as JSON. Kept as a source string so it runs in the
# subprocess, after that process's environment is set.
PROBE = textwrap.dedent(
    """
    import json, sys
    from mcptoon import config as cfg
    from mcptoon import usage as _u
    print(json.dumps({
        "config": str(cfg.CONFIG_DIR),
        "cache": str(cfg.CACHE_DIR),
        "logs": str(cfg.LOG_DIR),
        "usage": str(_u._USAGE_FILE),
        "policy": str(cfg.POLICY_FILE),
    }))
    """
)


def _run_probe(env_overrides: dict, legacy_exists: bool = False,
               xdg_exists: bool = False, argv_dir: str = "") -> dict:
    """Resolve the roots in a clean interpreter under a fabricated HOME."""
    import json

    home = Path(tempfile.mkdtemp(prefix="mcptoon-xdg-home-"))
    if legacy_exists:
        (home / ".mcptoon").mkdir(parents=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": str(REPO / "src"),
        "PYTHONIOENCODING": "utf-8",
    }
    if xdg_exists:
        env.setdefault("XDG_CONFIG_HOME", str(home / ".config"))
        env.setdefault("XDG_CACHE_HOME", str(home / ".cache"))
        env.setdefault("XDG_STATE_HOME", str(home / ".local" / "state"))
    env.update(env_overrides)
    if xdg_exists:
        Path(env["XDG_CONFIG_HOME"]).mkdir(parents=True, exist_ok=True)

    code = PROBE
    if argv_dir:
        # Exercise the real CLI entry point, not apply_home directly: `--dir` is
        # only correct if it lands before the first path read.
        code = (
            f"import sys; sys.argv = ['mcptoon', '--dir', {argv_dir!r}, '--version']\n"
            "from mcptoon.cli import main\n"
            "try:\n    main()\nexcept SystemExit:\n    pass\n"
        ) + PROBE
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, env=env, cwd=str(REPO), timeout=120)
    if r.returncode != 0:
        raise AssertionError(f"probe failed: {r.stderr[-800:]}")
    return json.loads(r.stdout.strip().splitlines()[-1]), home


class TestXdgDirectories(unittest.TestCase):

    def test_1_xdg_variables_are_honoured(self):
        """XDG set and the directory exists -> use it, for config and cache."""
        out, home = _run_probe({}, xdg_exists=True)
        self.assertEqual(out["config"], str(home / ".config" / "mcptoon"))
        self.assertEqual(out["cache"], str(home / ".cache" / "mcptoon"))
        self.assertNotEqual(out["config"], str(home / ".mcptoon"))

    def test_1b_state_goes_to_xdg_state_home_when_configured(self):
        """State (logs/toggles) follows XDG_STATE_HOME, not the config root."""
        home = Path(tempfile.mkdtemp(prefix="mcptoon-xdg-state-"))
        state = home / "state"
        state.mkdir(parents=True)
        cfg_home = home / ".config"
        (cfg_home / "mcptoon").mkdir(parents=True)
        out, _ = _run_probe(
            {"XDG_CONFIG_HOME": str(cfg_home), "XDG_STATE_HOME": str(state)},
            xdg_exists=True)
        self.assertEqual(out["logs"], str(state / "mcptoon" / "logs"))

    def test_2_unset_xdg_falls_back_to_legacy_layout(self):
        """No XDG variables at all -> exactly the pre-XDG paths."""
        out, home = _run_probe({})
        self.assertEqual(out["config"], str(home / ".mcptoon"))
        self.assertEqual(out["logs"], str(home / ".mcptoon" / "logs"))
        self.assertEqual(out["cache"], str(home / ".cache" / "mcptoon"))

    def test_2b_existing_install_keeps_legacy_when_xdg_is_empty(self):
        """The migration guard: XDG set but empty, legacy present -> stay legacy.

        Without this, upgrading a Linux user would silently move their servers
        to a new directory and look like data loss.
        """
        out, home = _run_probe({}, legacy_exists=True, xdg_exists=True)
        self.assertEqual(out["config"], str(home / ".mcptoon"))
        self.assertFalse((home / ".config" / "mcptoon").exists(),
                         "the XDG directory must not be created for a legacy install")

    def test_3_mcptoon_home_overrides_everything(self):
        home = Path(tempfile.mkdtemp(prefix="mcptoon-home-override-"))
        out, _ = _run_probe({"MCPTOON_HOME": str(home)}, xdg_exists=True)
        self.assertEqual(out["config"], str(home))
        self.assertEqual(out["cache"], str(home / "cache"))
        self.assertEqual(out["logs"], str(home / "logs"))

    def test_3b_dir_flag_overrides_everything(self):
        """`--dir` must beat XDG and MCPTOON_HOME, and land before first read."""
        home = Path(tempfile.mkdtemp(prefix="mcptoon-dirflag-"))
        out, _ = _run_probe({"MCPTOON_HOME": str(home / "ignored")},
                            xdg_exists=True, argv_dir=str(home / "chosen"))
        self.assertEqual(out["config"], str(home / "chosen"))
        self.assertEqual(out["cache"], str(home / "chosen" / "cache"))
        self.assertEqual(out["usage"], str(home / "chosen" / "cache" / "usage.json"))
        self.assertEqual(out["policy"], str(home / "chosen" / "compression.json"))

    def test_4_legacy_directory_is_not_created_when_overridden(self):
        """The complaint in the issue: an empty ~/.mcptoon in $HOME."""
        home = Path(tempfile.mkdtemp(prefix="mcptoon-nolegacy-"))
        chosen = home / "elsewhere"
        _run_probe({"MCPTOON_HOME": str(chosen)}, xdg_exists=True)
        self.assertFalse((home / ".mcptoon").exists(),
                         "every location was overridden; ~/.mcptoon must not appear")
        self.assertTrue(chosen.exists(), "the chosen root must exist")

    def test_4b_dir_flag_also_avoids_the_legacy_directory(self):
        home = Path(tempfile.mkdtemp(prefix="mcptoon-nolegacy-dir-"))
        _run_probe({}, xdg_exists=True, argv_dir=str(home / "elsewhere"))
        self.assertFalse((home / ".mcptoon").exists())


class TestUsageAndPolicyFollowTheRoot(unittest.TestCase):
    """The two import-time bindings that would otherwise ignore the override."""

    def test_usage_file_follows_mcptoon_home(self):
        home = Path(tempfile.mkdtemp(prefix="mcptoon-usage-root-"))
        out, _ = _run_probe({"MCPTOON_HOME": str(home)})
        self.assertEqual(out["usage"], str(home / "cache" / "usage.json"))

    def test_policy_file_follows_mcptoon_home(self):
        home = Path(tempfile.mkdtemp(prefix="mcptoon-policy-root-"))
        out, _ = _run_probe({"MCPTOON_HOME": str(home)})
        self.assertEqual(out["policy"], str(home / "compression.json"))


class TestDirFlagIsConsumedByTheParser(unittest.TestCase):
    """`--dir` has to be *eaten*, not just applied.

    Found by running the real CLI: the flag relocated every path correctly and
    then fell through to the dispatcher, which read it as the command name and
    printed `Unknown command: --dir`. Applying a global flag and consuming it
    are two separate jobs, and only the first one had a test.
    """

    def _run(self, args, cwd):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(cwd),
            "USERPROFILE": str(cwd),
            "PYTHONPATH": str(REPO / "src"),
            "PYTHONIOENCODING": "utf-8",
        }
        return subprocess.run([sys.executable, "-m", "mcptoon"] + args,
                              capture_output=True, text=True, env=env,
                              cwd=str(REPO), timeout=180)

    def test_dir_flag_does_not_become_the_command(self):
        sandbox = Path(tempfile.mkdtemp(prefix="mcptoon-dirparse-"))
        target = sandbox / "chosen"
        r = self._run(["--dir", str(target), "list"], sandbox)
        self.assertNotIn("Unknown command", r.stdout + r.stderr)
        self.assertNotIn("--dir", (r.stdout + r.stderr).split("Unknown command")[-1]
                         if "Unknown command" in r.stdout + r.stderr else "")
        self.assertTrue(target.exists(), "the chosen root was not created")

    def test_dir_flag_equals_form_also_works(self):
        sandbox = Path(tempfile.mkdtemp(prefix="mcptoon-dirparse-eq-"))
        target = sandbox / "chosen2"
        r = self._run([f"--dir={target}", "list"], sandbox)
        self.assertNotIn("Unknown command", r.stdout + r.stderr)
        self.assertTrue(target.exists())

    def test_a_real_write_lands_in_the_dir_root(self):
        """The whole point of the issue: config must live where the user said."""
        import json as _json

        sandbox = Path(tempfile.mkdtemp(prefix="mcptoon-dirwrite-"))
        target = sandbox / "chosen3"
        r = self._run(["--dir", str(target), "add", "demo",
                       "--stdio", "npx", "-y", "foo"], sandbox)
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = target / "config.json"
        self.assertTrue(cfg.is_file(), f"config.json missing under {target}: {sorted(p.name for p in target.iterdir())}")
        self.assertIn("demo", _json.loads(cfg.read_text(encoding="utf-8"))["servers"])
        self.assertFalse((sandbox / ".mcptoon").exists(),
                         "the legacy directory must not appear when --dir was given")


if __name__ == "__main__":
    unittest.main()
