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
        self.assertIn("mcptoon sync", out)
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
        self._env_patch = mock.patch.dict(os.environ, {
            "MCPTOON_CONFIG_FILE": str(self.tmp / "config.json"),
            "MCPTOON_CONFIG_FILE_TOML": str(self.tmp / "config.toml"),
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
        self.assertIn("mcptoon sync", out)
        self.assertIn("Could not fetch tools yet", out)

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
        self.assertIn("0 tokens", out)


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
