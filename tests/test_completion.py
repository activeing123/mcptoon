"""Tests for v0.2.1: shell completion."""
import pytest
from mcptoon.cli import _cmd_completion
import io
import contextlib


class TestCompletion:
    def test_bash_completion(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["bash"])
        output = buf.getvalue()
        assert "Bash" in output
        assert "complete -F" in output
        assert "mcptoon" in output

    def test_zsh_completion(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["zsh"])
        output = buf.getvalue()
        assert "Zsh" in output
        assert "compdef" in output

    def test_fish_completion(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["fish"])
        output = buf.getvalue()
        assert "Fish" in output
        assert "complete -c" in output

    def test_powershell_completion(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["powershell"])
        output = buf.getvalue()
        assert "PowerShell" in output
        assert "Register-ArgumentCompleter" in output

    def test_ps_alias(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["ps"])
        output = buf.getvalue()
        assert "PowerShell" in output

    def test_default_shell_is_bash(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion([])
        output = buf.getvalue()
        assert "Bash" in output

    def test_unknown_shell(self):
        buf = io.StringIO()
        with pytest.raises(SystemExit):
            with contextlib.redirect_stdout(buf):
                _cmd_completion(["tcsh"])

    def test_completion_mentions_all_commands(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _cmd_completion(["bash"])
        output = buf.getvalue()
        for cmd in ["init", "manifest", "call", "doctor", "discover"]:
            assert cmd in output, f"Command '{cmd}' missing from completion"
