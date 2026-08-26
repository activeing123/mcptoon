"""Tests for stats command and toggle command."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import config as cfg


class TestToggleConfig(unittest.TestCase):
    """Test toggle persistence in config module."""

    def setUp(self):
        self._orig_toggle = cfg.TOGGLE_FILE
        self.tmpdir = tempfile.mkdtemp()
        cfg.TOGGLE_FILE = Path(os.path.join(self.tmpdir, "toggles.json"))

    def tearDown(self):
        cfg.TOGGLE_FILE = self._orig_toggle
        try:
            Path(cfg.TOGGLE_FILE).unlink(missing_ok=True)
        except (OSError, TypeError):
            pass

    def test_tool_enabled_by_default(self):
        """Tools should be enabled by default."""
        self.assertTrue(cfg.is_tool_enabled("exa", "search"))

    def test_toggle_tool(self):
        """Toggle should flip state."""
        state = cfg.toggle_tool("exa", "search")
        self.assertFalse(state)  # now disabled
        self.assertFalse(cfg.is_tool_enabled("exa", "search"))

    def test_toggle_tool_back(self):
        """Double toggle should re-enable."""
        cfg.toggle_tool("exa", "search")
        state = cfg.toggle_tool("exa", "search")
        self.assertTrue(state)  # re-enabled
        self.assertTrue(cfg.is_tool_enabled("exa", "search"))

    def test_list_disabled_tools(self):
        """list_disabled_tools should show only disabled ones."""
        cfg.toggle_tool("exa", "search")
        cfg.toggle_tool("github", "create_issue")
        disabled = cfg.list_disabled_tools()
        self.assertIn("exa:search", disabled)
        self.assertIn("github:create_issue", disabled)

    def test_load_save_toggles(self):
        """Toggles should persist across load/save."""
        cfg.toggle_tool("exa", "search")
        toggles = cfg.load_toggles()
        self.assertFalse(toggles["exa:search"])

    def test_empty_toggles_file(self):
        """Corrupt file should return empty dict."""
        Path(cfg.TOGGLE_FILE).write_text("not json!!!", encoding="utf-8")
        toggles = cfg.load_toggles()
        self.assertEqual(toggles, {})


class TestStatsCommand(unittest.TestCase):
    """Test stats command dispatch and output."""

    def test_stats_exists(self):
        """_cmd_stats should be callable."""
        import mcptoon.cli as cli
        self.assertTrue(callable(cli._cmd_stats))

    def test_toggle_exists(self):
        """_cmd_toggle should be callable."""
        import mcptoon.cli as cli
        self.assertTrue(callable(cli._cmd_toggle))

    def test_toggle_list_dispatch(self):
        """CLI should route 'toggle --list' without error."""
        import mcptoon.cli as cli
        import io
        f = io.StringIO()
        with patch("sys.stdout", f):
            try:
                cli._cmd_toggle(["--list"], "auto")
            except SystemExit:
                pass
        output = f.getvalue().lower()
        # Should mention disabled or no tools
        self.assertTrue("disabled" in output or "no tools" in output or "no tools are disabled" in output)


if __name__ == "__main__":
    unittest.main()
