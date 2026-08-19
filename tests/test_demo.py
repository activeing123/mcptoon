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

"""Tests for mcptoon demo command."""

import sys
import os
import subprocess
import unittest
from unittest import mock
from io import StringIO

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcptoon.demo import (
    _print_banner,
    _check_prerequisites,
    _extract_text,
    _show_token_comparison,
    _show_benchmark,
    _cleanup_demo,
    _demo_help,
    run_demo,
)


class TestDemoBanner(unittest.TestCase):
    """Test banner output."""

    def test_print_banner(self):
        """Banner should print without error."""
        with mock.patch("sys.stdout", StringIO()):
            _print_banner()
        # No exception = pass


class TestCheckPrerequisites(unittest.TestCase):
    """Test prerequisite checking."""

    def test_npx_found(self):
        """When npx is available, should return True."""
        with mock.patch("shutil.which", return_value="/usr/bin/npx"):
            self.assertTrue(_check_prerequisites())

    def test_npx_not_found(self):
        """When npx is not available, should return False."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("sys.stdout", StringIO()):
                self.assertFalse(_check_prerequisites())


class TestExtractText(unittest.TestCase):
    """Test MCP result text extraction."""

    def test_string_input(self):
        """String input should return as-is."""
        self.assertEqual(_extract_text("hello"), "hello")

    def test_list_of_text_items(self):
        """MCP content array with text type."""
        result = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        self.assertEqual(_extract_text(result), "hello\nworld")

    def test_dict_with_content_key(self):
        """Dict with content list."""
        result = {"content": [{"type": "text", "text": "nested"}]}
        self.assertEqual(_extract_text(result), "nested")

    def test_dict_with_text_key(self):
        """Dict with text string."""
        result = {"text": "plain text"}
        self.assertEqual(_extract_text(result), "plain text")

    def test_empty_result(self):
        """Empty string input."""
        self.assertEqual(_extract_text(""), "")


class TestShowTokenComparison(unittest.TestCase):
    """Test token comparison output."""

    def test_renders_without_error(self):
        """Token comparison should render without exception."""
        with mock.patch("sys.stdout", StringIO()):
            _show_token_comparison("sample text " * 100)
        # No exception = pass

    def test_empty_text(self):
        """Should handle empty text gracefully."""
        with mock.patch("sys.stdout", StringIO()):
            _show_token_comparison("")
        # No exception = pass


class TestShowBenchmark(unittest.TestCase):
    """Test benchmark display."""

    def test_renders_without_error(self):
        """Benchmark should render without exception."""
        with mock.patch("sys.stdout", StringIO()):
            _show_benchmark()
        # No exception = pass


class TestCleanupDemo(unittest.TestCase):
    """Test demo cleanup."""

    def test_cleanup_nonexistent_server(self):
        """Should not error if server doesn't exist in config."""
        with mock.patch("mcptoon.demo.cfg.load_config", return_value={}):
            with mock.patch("mcptoon.demo.cfg.save_config"):
                _cleanup_demo("nonexistent")
        # No exception = pass

    def test_cleanup_existing_server(self):
        """Should remove server from config."""
        servers = {"demo-fetch": {"transport": "stdio"}, "other": {}}
        with mock.patch("mcptoon.demo.cfg.load_config", return_value=servers.copy()):
            with mock.patch("mcptoon.demo.cfg.save_config") as mock_save:
                _cleanup_demo("demo-fetch")
                mock_save.assert_called_once()
                saved = mock_save.call_args[0][0]
                self.assertNotIn("demo-fetch", saved)
                self.assertIn("other", saved)


class TestDemoHelp(unittest.TestCase):
    """Test demo help text."""

    def test_help_contains_usage(self):
        """Help should contain usage info."""
        help_text = _demo_help()
        self.assertIn("mcptoon demo", help_text)
        self.assertIn("--quick", help_text)
        self.assertIn("--keep", help_text)


class TestRunDemoHelp(unittest.TestCase):
    """Test `mcptoon demo --help`."""

    def test_help_flag_prints_help(self):
        """--help should print help and return."""
        with mock.patch("sys.stdout", StringIO()):
            run_demo(["--help"])
        # No exception = pass

    def test_h_flag_prints_help(self):
        """-h should print help and return."""
        with mock.patch("sys.stdout", StringIO()):
            run_demo(["-h"])
        # No exception = pass


class TestDemoCLIIntegration(unittest.TestCase):
    """Test demo command through CLI dispatch."""

    def test_demo_in_help(self):
        """`mcptoon --help` should mention demo."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        self.assertIn("demo", result.stdout)

    def test_demo_help_subcommand(self):
        """`mcptoon demo --help` should print demo help."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "demo", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        self.assertIn("Zero-config", result.stdout)


if __name__ == "__main__":
    unittest.main()
