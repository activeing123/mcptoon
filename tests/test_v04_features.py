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

"""Tests for v0.4.0 features: __main__.py, error fix suggestions."""
import subprocess
import sys


# ─── __main__.py support ───

class TestMainModule:
    """Test that `python -m mcptoon` works."""

    def test_main_module_importable(self):
        """__main__.py should exist and be importable."""
        import mcptoon.__main__
        assert hasattr(mcptoon.__main__, "main")

    def test_python_m_mcptoon_help(self):
        """`python -m mcptoon --help` should show help text."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon", "help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "mcptoon" in result.stdout
        assert "manifest" in result.stdout

    def test_python_m_mcptoon_no_args(self):
        """`python -m mcptoon` with no args should show help."""
        result = subprocess.run(
            [sys.executable, "-m", "mcptoon"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "mcptoon" in result.stdout


# ─── Error fix suggestions ───

class TestFixSuggestions:
    """Test _fix_suggestion() for all error codes."""

    def test_server_not_found(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("SERVER_NOT_FOUND", "myserver")
        assert "mcptoon list" in result
        assert "mcptoon add" in result
        assert "mcptoon doctor" in result

    def test_config_missing(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("CONFIG_MISSING")
        assert "mcptoon init" in result

    def test_tool_not_found(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("TOOL_NOT_FOUND", "github")
        assert "mcptoon manifest" in result
        assert "mcptoon inspect" in result
        assert "github" in result

    def test_unknown_tool(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("UNKNOWN_TOOL", "github", "sarch")
        assert "mcptoon inspect" in result
        assert "github" in result

    def test_dangerous_op(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("DANGEROUS_OP")
        assert "--destructive" in result

    def test_credential_leak(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("CREDENTIAL_LEAK")
        assert "--raw" in result

    def test_tool_poisoning(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("TOOL_POISONING")
        assert "--raw" in result

    def test_connection_failed(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("CONNECTION_FAILED")
        assert "mcptoon doctor" in result

    def test_timeout(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("TIMEOUT")
        assert "mcptoon doctor" in result

    def test_parse_error(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("PARSE_ERROR", "github", "search")
        assert "mcptoon inspect" in result
        assert "github" in result

    def test_unknown_code_returns_empty(self):
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("NONEXISTENT_CODE")
        assert result == ""

    def test_server_substitution_in_fix(self):
        """Server name should be substituted into fix suggestion."""
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("TOOL_NOT_FOUND", "myserver")
        assert "myserver" in result

    def test_tool_substitution_in_fix(self):
        """Tool name should be substituted into fix suggestion."""
        from mcptoon.cli import _fix_suggestion
        result = _fix_suggestion("PARSE_ERROR", "github", "create_issue")
        assert "github" in result
