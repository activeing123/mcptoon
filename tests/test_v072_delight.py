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

"""v0.7.2 小白爽感版 tests — A1 quickstart celebration, A2 demo plain numbers,
A3 one-line installers."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import demo as demo_mod
from mcptoon import discover as disc
from mcptoon import sync as sync_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


class _A1Celebration(unittest.TestCase):
    """A1: the quickstart payoff block."""

    def test_with_tool_count(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._quickstart_celebration(37, 5)
        out = buf.getvalue()
        self.assertIn("37 tools ready across 5 servers", out)
        self.assertIn("🎉", out)
        self.assertIn("Now you can:", out)
        self.assertIn("mcptoon status", out)
        self.assertIn("mcptoon serve", out)

    def test_without_tool_count(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._quickstart_celebration(None, 2)
        out = buf.getvalue()
        self.assertIn("2 MCP servers configured", out)
        self.assertIn("Now you can:", out)

    def test_few_servers_suggests_more(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._quickstart_celebration(3, 2)
        self.assertIn("Want more servers?", buf.getvalue())

    def test_many_servers_no_upsell(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._quickstart_celebration(200, 9)
        self.assertNotIn("Want more servers?", buf.getvalue())

    def test_manifest_tool_count_shapes(self):
        self.assertEqual(cli._manifest_tool_count({"tools": [1, 2, 3]}), 3)
        self.assertEqual(cli._manifest_tool_count({"a": 1, "b": 2}), 2)
        self.assertEqual(cli._manifest_tool_count([1, 2]), 2)
        self.assertEqual(cli._manifest_tool_count(None), 0)
        self.assertEqual(cli._manifest_tool_count("x"), 0)


class _FakeResult:
    """Minimal stand-in for disc.DiscoveryResult."""

    def __init__(self, n):
        self.servers = {f"s{i}": {"type": "stdio", "command": "x"} for i in range(n)}
        self.sources = {f"s{i}": ["local"] for i in range(n)}
        self.reasons = {f"s{i}": "fake" for i in range(n)}

    @property
    def count(self):
        return len(self.servers)

    def summary(self):
        return f"Discovered {self.count} MCP server(s):"


class _A1QuickstartIntegration(unittest.TestCase):
    """End-to-end quickstart output with discovery stubbed out."""

    def setUp(self):
        self._old_cwd = os.getcwd()
        self.sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(self.sandbox.cleanup)
        self.tmp = Path(self.sandbox.name)
        # Sandbox BOTH roots, not just the config path. quickstart now offers
        # takeover, and `takeover_plan()` resolves agent configs through
        # `_home()` (USERPROFILE) *and* `_appdata()` (APPDATA) — so a test that
        # relocates only the config file still reads — and, on a real machine,
        # writes — the live Claude Desktop / Cline configs. An empty sandbox home
        # means there is no plan, so the offer is silent and hermetic.
        self._env_patch = mock.patch.dict(os.environ, {
            "MCPTOON_CONFIG_FILE": str(self.tmp / "config.json"),
            "MCPTOON_CONFIG_FILE_TOML": str(self.tmp / "config.toml"),
            "HOME": str(self.tmp),
            "USERPROFILE": str(self.tmp),
            "APPDATA": str(self.tmp / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(self.tmp / "AppData" / "Local"),
        })
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def test_quickstart_full_shows_celebration(self):
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        out = buf.getvalue()
        self.assertIn("2 MCP servers configured", out)
        self.assertIn("Now you can:", out)
        self.assertIn("mcptoon status", out)
        self.assertIn("Could not fetch tools yet", out)

    def test_quickstart_indexes_the_skill_catalog(self):
        """Onboarding ends with a catalog that can already answer.

        `resolve` builds the index lazily on first use, but a user who has just
        installed should not have to discover that — the install path does it, so
        the very next command (including one an agent runs) has a catalog.
        """
        fake = _FakeResult(2)
        root = self.tmp / "skills" / "demo"
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            "---\nname: demo\ndescription: 演示技能。触发词：演示\n---\n\nbody\n",
            encoding="utf-8")
        index = self.tmp / "skills-index.json"
        with mock.patch.dict(os.environ, {"MCPTOON_SKILLS_INDEX": str(index),
                                          "MCPTOON_SKILLS_ROOTS": str(self.tmp / "skills")}), \
             mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        out = buf.getvalue()
        self.assertTrue(index.is_file(), "quickstart must leave an index behind")
        self.assertIn("Skill catalog indexed: 1 skill(s)", out)

    def test_quickstart_dry_builds_no_index(self):
        """A preview must not write the index — same rule as the config."""
        fake = _FakeResult(2)
        index = self.tmp / "skills-index.json"
        with mock.patch.dict(os.environ, {"MCPTOON_SKILLS_INDEX": str(index)}), \
             mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart(["--dry"])
        self.assertFalse(index.exists(), "a dry run must not write an index")

    def test_quickstart_survives_an_index_failure(self):
        """A read-only home is not an onboarding failure."""
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch("mcptoon.skills.ensure_index", side_effect=OSError("read-only")), \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        out = buf.getvalue()
        self.assertIn("2 MCP servers configured", out)
        self.assertIn("Now you can:", out)

    def test_quickstart_registers_the_gateway_in_agents(self):
        """quickstart is the install path that has to leave a trace: it must sync."""
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]) as fake_sync, \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        self.assertTrue(fake_sync.call_args.kwargs.get("include_self"),
                        "quickstart must register the mcptoon gateway, not just the servers")

    def test_quickstart_no_self_opts_out(self):
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]) as fake_sync, \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart(["--no-self"])
        self.assertFalse(fake_sync.call_args.kwargs.get("include_self"))

    def test_quickstart_survives_a_sync_failure(self):
        """A broken agent config must not abort onboarding."""
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", side_effect=OSError("disk")), \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        out = buf.getvalue()
        self.assertIn("Could not sync to agents yet", out)
        self.assertIn("2 MCP servers configured", out)

    def test_quickstart_offers_takeover_when_entries_are_registered_directly(self):
        """The install path must *say* that alongside-mounting saves nothing.

        With servers registered directly, quickstart keeps the additive default but
        prints the red warning and asks — and the interactive answer is honoured.
        """
        fake = _FakeResult(2)
        plan = [{"agent_id": "cursor", "agent_name": "Cursor (global)",
                 "path": str(self.tmp / "mcp.json"), "servers": ["fetch", "git"]}]
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch("mcptoon.sync.takeover_plan", return_value=plan), \
             mock.patch.object(cli.sys.stdin, "isatty", return_value=True), \
             mock.patch("builtins.input", return_value="y"), \
             mock.patch.object(cli, "_cmd_sync") as handed_off, \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        out = buf.getvalue()
        self.assertIn("WARNING", out)
        self.assertIn("not saving tokens yet", out)
        self.assertIn("Cursor (global): fetch, git", out)
        self.assertEqual(handed_off.call_args[0][0], ["--takeover", "--yes"])

    def test_quickstart_offer_stays_silent_without_direct_entries(self):
        """No managed entries registered directly means nothing to warn about."""
        fake = _FakeResult(2)
        with mock.patch.object(disc, "auto_discover", return_value=fake), \
             mock.patch.object(cfg, "CONFIG_FILE", self.tmp / "config.json"), \
             mock.patch.object(cfg, "CONFIG_FILE_TOML", self.tmp / "config.toml"), \
             mock.patch.object(cfg, "merge_servers", return_value=(2, 0, [])), \
             mock.patch.object(cfg, "save_config"), \
             mock.patch.object(sync_mod, "sync_to_all", return_value=[]), \
             mock.patch("mcptoon.sync.takeover_plan", return_value=[]), \
             mock.patch.object(cli, "_cmd_sync") as handed_off, \
             mock.patch.object(cli.manifest_mod, "get_manifest",
                               side_effect=RuntimeError("no servers running")):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart([])
        self.assertNotIn("WARNING", buf.getvalue())
        self.assertIsNone(handed_off.call_args)

    def test_quickstart_dry_has_no_celebration(self):
        fake = _FakeResult(1)
        with mock.patch.object(disc, "auto_discover", return_value=fake):
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli._cmd_quickstart(["--dry"])
        out = buf.getvalue()
        self.assertIn("(--dry mode", out)
        self.assertNotIn("🎉", out)
        self.assertNotIn("Now you can:", out)


class _A2DemoOutput(unittest.TestCase):
    """A2: demo speaks in before/after numbers and plain language."""

    def test_token_comparison_headline(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            demo_mod._show_token_comparison("hello world " * 200)
        out = buf.getvalue()
        self.assertIn("SAME data", out)
        self.assertIn("→", out)
        self.assertIn("%", out)
        self.assertIn("JSON", out)
        self.assertIn("TOON", out)
        self.assertIn("SLIM", out)

    def test_benchmark_has_now_you_can(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            demo_mod._show_benchmark()
        out = buf.getvalue()
        self.assertIn("Now you can:", out)
        self.assertIn("mcptoon sync", out)
        self.assertIn("mcptoon serve", out)
        # 这句曾经钉的是 "0 tokens (always)"——与同屏的 581 正面冲突（外部评测挑的
        # 就是这类"宣称≠实测"）。09-16 改成"按需取列表，不为每一轮付费"，
        # 断言跟着换成可核实的措辞 + 那个实测数本身。
        self.assertIn("fetched, not injected", out)
        self.assertIn("581 tokens", out)
        self.assertNotIn("0 tokens", out)


class _A3Installers(unittest.TestCase):
    """A3: one-line installers exist, are syntactically valid, and self-run."""

    def test_install_sh_exists_and_shape(self):
        p = REPO_ROOT / "install.sh"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("python3", text)
        self.assertIn("pip install", text)
        self.assertIn("mcptoon", text)
        self.assertIn("quickstart", text)
        self.assertIn("externally-managed", text)  # PEP 668 fallback

    def test_install_ps1_exists_and_shape(self):
        p = REPO_ROOT / "install.ps1"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("pip install", text)
        self.assertIn("quickstart", text)
        self.assertIn("Python 3.10", text)
        self.assertIn("winget", text)  # actionable hint when python missing

    def test_install_sh_bash_syntax(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        r = subprocess.run([bash, "-n", str(REPO_ROOT / "install.sh")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        if r.returncode == 127:
            self.skipTest("bash unusable (WSL stub on Windows)")
        self.assertEqual(r.returncode, 0, f"bash -n failed: {r.stderr}")

    def test_install_ps1_parses(self):
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            self.skipTest("no PowerShell on PATH")
        script = (
            "$e=$null;[void][System.Management.Automation.Language.Parser]"
            f"::ParseFile('{(REPO_ROOT / 'install.ps1').as_posix()}',"
            "[ref]$null,[ref]$e);if($e){$e|ForEach-Object{$_.Message};exit 1}"
            "else{'PARSE_OK'}"
        )
        r = subprocess.run([pwsh, "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, f"ps1 parse failed: {r.stderr}")
        self.assertIn("PARSE_OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
