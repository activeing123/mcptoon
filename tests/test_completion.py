"""Tests for v0.2.1: shell completion."""
import pytest
from mcptoon import cli
from mcptoon.cli import _cmd_completion
import io
import contextlib
import re
from pathlib import Path

_CLI_SOURCE = Path(cli.__file__).read_text(encoding="utf-8")


def _dispatch_verbs() -> set:
    """Every verb (and alias) the `_run` dispatch chain accepts, read out of the
    source. This is the authoritative set completion must cover — a hand-kept
    copy is exactly what drifted before (13 verbs went missing)."""
    verbs = set()
    for m in re.finditer(r"^\s*(?:el)?if command(?: in \(([^)]+)\)| == \"([^\"]+)\"):",
                         _CLI_SOURCE, re.M):
        if m.group(1):
            verbs |= {x.strip().strip('"') for x in m.group(1).split(",")}
        elif m.group(2):
            verbs.add(m.group(2))
    return {v for v in verbs if not v.startswith("-")}


def _completion_offered(shell: str) -> list:
    """The verb list a shell's completion script embeds, read back after the
    marker substitution `_cmd_completion` performs."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _cmd_completion([shell])
    out = buf.getvalue()
    assert "__MC_TOON_COMMANDS" not in out, "an unsubstituted marker leaked"
    # Every shell embeds the same canonical list, space- or comma-separated.
    needle = cli._CMD_WORDS if shell != "powershell" else cli._CMD_PS_WORDS
    assert needle in out, f"{shell} completion does not embed the canonical verb list"
    return list(cli._COMPLETION_COMMANDS)


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

    def test_completion_covers_every_dispatched_verb(self):
        """The bug this pins: four scripts hardcoded a stale verb list, so a third
        of the CLI (bench, config, footer-facts, off, plugin, report, restore,
        skills, stats, status, toggle, uninstall, update) could not be completed.
        The old spot-check of five names passed anyway."""
        offered = set(_completion_offered("bash"))
        missing = _dispatch_verbs() - offered
        assert not missing, f"completion cannot suggest dispatched verbs: {sorted(missing)}"

    def test_all_four_shells_offer_the_same_verbs(self):
        lists = {sh: _completion_offered(sh) for sh in ("bash", "zsh", "fish", "powershell")}
        assert len({tuple(v) for v in lists.values()}) == 1, \
            f"the shells disagree on the verb list: { {k: len(v) for k, v in lists.items()} }"

    def test_completion_includes_a_recently_added_verb(self):
        # `import` shipped in 0.8.x; a stale list would omit it. Guards the
        # regression from the other direction (the list must move with the CLI).
        assert "import" in _completion_offered("powershell")
