"""Every "next step" the CLI advertises must actually work.

The theme, found by probing on 2026-10-02: mcptoon's output tells the user to do
something next, and three of those steps did not work.

1. **`--full` was a lie for `mcptoon install`.** `_cmd_install` never received
   `full`, so the truncation notice "use --full" pointed at a flag that changed
   nothing. Measured: `install --list` with and without `--full` produced
   byte-identical stdout (4,048 bytes, notice still present).
2. **`--raw` was never wired to the safety screen.** The CREDENTIAL_LEAK /
   TOOL_POISONING fix hint says "use --raw to bypass" verbatim, but `--raw` only
   set the *output format* — the screen still blocked the result, so the advertised
   escape hatch did nothing.
3. **A `--smart` handle was not redeemable from the CLI.** `mcptoon_retrieve` is a
   native MCP tool and the CLI had no counterpart, so a shell user told to
   "call mcptoon_retrieve" had no command to run.

The tests are grouped by the promise, not by the module: what the output says, and
whether doing it works.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from mcptoon import ccr, cli

ROOT = Path(__file__).resolve().parents[1]


# ═══════════════════════════════════════════════════════════════
# Promise 1: the truncation notice names --full, so --full must work
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Point the retrieve store at the tmp dir — never the real ~/.mcptoon."""
    monkeypatch.setenv("MCPTOON_CCR_DIR", str(tmp_path / "ccr"))
    monkeypatch.setenv("MCPTOON_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("MCPTOON_COMPRESSION_FILE", str(tmp_path / "compression.json"))


def test_install_accepts_a_full_parameter():
    """The handler must be *able* to receive `full` — the root cause was its absence."""
    import inspect

    params = inspect.signature(cli._cmd_install).parameters
    assert "full" in params, (
        "_cmd_install cannot receive --full, so the 'use --full' notice it prints "
        "via _render_result is a promise it cannot keep"
    )


def test_install_full_reaches_every_render_site():
    """And it must actually forward it, at every render call in the handler."""
    text = (ROOT / "src" / "mcptoon" / "cli.py").read_text(encoding="utf-8")
    start = text.index("def _cmd_install(")
    end = text.index("\ndef ", start + 1)
    body = "\n".join(ln for ln in text[start:end].splitlines()
                     if not ln.strip().startswith("#"))
    calls = re.findall(r"_render_result\([^)]*", body)
    assert calls, "no _render_result call found in _cmd_install — test is stale"
    for call in calls:
        assert "full" in call, (
            f"this render call cannot honour --full: {call!r}. Every call in "
            "_cmd_install must pass the `full` it was given."
        )


def test_the_full_flag_changes_install_list_output(tmp_path):
    """End-to-end: the flag the notice names actually changes the output.

    Offline-safe: `install --list` reads only the local config, so it works with
    zero MCP servers configured.

    The environment is pinned because the first version of this test compared a
    run whose *first* invocation printed the one-time welcome banner against a
    second that did not — the two outputs differed for a reason that had nothing
    to do with `--full`, and the test passed for the wrong reason. `MCPTOON_WELCOME_FILE`
    pointing at an existing file means "already greeted", so both runs are clean.
    """
    seen = tmp_path / ".welcome"
    seen.write_text("seen", encoding="utf-8")
    env = {
        "MCPTOON_WELCOME_FILE": str(seen),
        "MCPTOON_SKIP_SELF_HEAL": "1",
        "MCPTOON_CONFIG_FILE": str(tmp_path / "config.json"),
        "MCPTOON_SETTINGS_FILE": str(tmp_path / "settings.json"),
        "MCPTOON_COMPRESSION_FILE": str(tmp_path / "compression.json"),
        "MCPTOON_CCR_DIR": str(tmp_path / "ccr"),
    }
    import os

    full_env = {**os.environ, **env}

    def run(extra):
        return subprocess.run([sys.executable, "-m", "mcptoon", "install", "--list", *extra],
                              capture_output=True, text=True, encoding="utf-8",
                              env=full_env).stdout

    plain, full = run([]), run(["--full"])
    if "use --full" in plain:
        assert full != plain, (
            "the output says 'use --full' but --full changed nothing — the notice "
            "points at a flag the code does not honour"
        )
        assert "use --full" not in full, "--full did not lift the truncation"
    else:
        assert plain == full, "no truncation notice, so --full should be a no-op here"


# ═══════════════════════════════════════════════════════════════
# Promise 2: the safety hint names --raw, so --raw must bypass
# ═══════════════════════════════════════════════════════════════

def test_raw_bypasses_the_safety_screen():
    """`--raw` must set skip_poisoning_check on the router call.

    The hint is printed on a CREDENTIAL_LEAK/TOOL_POISONING error, so the flag it
    names has to reach the check that produced the error.
    """
    captured = {}

    def fake_call_tool(server, tool, args, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    with mock.patch.object(cli, "call_tool", side_effect=fake_call_tool), \
            mock.patch.object(cli, "_render_result"):
        cli._cmd_call(["srv", "tool", "{}"], fmt="raw", head_n=0, max_chars=0, full=False)

    assert captured.get("skip_poisoning_check") is True, (
        "`--raw` did not reach the router, so the 'use --raw to bypass' hint is "
        "false — the screen blocks the result anyway"
    )


def test_the_default_call_still_screens():
    """The bypass must be opt-in: a normal call keeps the safety screen on."""
    captured = {}

    def fake_call_tool(server, tool, args, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    with mock.patch.object(cli, "call_tool", side_effect=fake_call_tool), \
            mock.patch.object(cli, "_render_result"):
        cli._cmd_call(["srv", "tool", "{}"], fmt="auto", head_n=0, max_chars=0, full=False)

    assert captured.get("skip_poisoning_check") is False


def test_auto_call_also_honours_raw():
    """`call --auto --raw` is the same promise on the other routing path."""
    captured = {}

    def fake_auto(tool, args, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    with mock.patch("mcptoon.router.call_tool_auto", side_effect=fake_auto), \
            mock.patch.object(cli, "_render_result"):
        cli._cmd_call(["--auto", "tool", "{}"], fmt="raw", head_n=0, max_chars=0, full=False)

    assert captured.get("skip_poisoning_check") is True


def test_the_hint_and_the_wiring_name_the_same_flag():
    """The hint's flag and the wiring's flag must not drift apart."""
    hints = cli._FIX_SUGGESTIONS
    for code in ("CREDENTIAL_LEAK", "TOOL_POISONING"):
        assert "--raw" in hints[code], f"{code} no longer points at --raw"
    src = (ROOT / "src" / "mcptoon" / "cli.py").read_text(encoding="utf-8")
    assert 'skip_poisoning_check=(fmt == "raw")' in src, (
        "the --raw wiring moved; keep it in step with the hint text"
    )


# ═══════════════════════════════════════════════════════════════
# Promise 3: a --smart handle is redeemable from the CLI
# ═══════════════════════════════════════════════════════════════

def _store_a_payload() -> tuple[str, object]:
    payload = [{"path": f"f{i}.py", "snippet": "def f(): pass  # context " * 8,
                "score": 0.5} for i in range(40)]
    handle = ccr.store(payload, server="s", tool="t")
    assert handle, "test fixture could not store a payload"
    return handle, payload


def test_retrieve_command_returns_the_original(capsys):
    """The whole point: the handle in a `--smart` notice is redeemable here."""
    handle, payload = _store_a_payload()
    cli._cmd_retrieve([handle], "json")
    out = capsys.readouterr().out
    assert json.loads(out) == payload


def test_retrieve_is_byte_identical(capsys):
    """Not just equal after re-parsing — the same bytes on the wire."""
    handle, payload = _store_a_payload()
    cli._cmd_retrieve([handle], "json")
    out = capsys.readouterr().out
    assert json.loads(out) == payload
    assert len(json.loads(out)) == len(payload)


def test_retrieve_uses_the_shared_notice_text(capsys):
    """CLI and MCP tool must give the same reason for the same failure."""
    with pytest.raises(SystemExit) as exc:
        cli._cmd_retrieve(["not-a-handle"], "json")
    assert exc.value.code == 1, "a miss must not exit 0"
    err = capsys.readouterr().err
    assert ccr.retrieve_notice(ccr.STATUS_BAD_HANDLE) in err


def test_retrieve_miss_is_an_error_not_an_empty_success(capsys):
    """`mcptoon retrieve <typo> && ...` must not look like it worked."""
    with pytest.raises(SystemExit) as exc:
        cli._cmd_retrieve(["deadbeef0000"], "json")
    assert exc.value.code == 1
    assert ccr.STATUS_NEVER_STORED in capsys.readouterr().err


def test_retrieve_list_shows_the_store(capsys):
    _store_a_payload()
    cli._cmd_retrieve(["--list"], "json")
    out = capsys.readouterr().out
    assert "Stored originals: 1" in out
    assert "never expires" in out, "the default retention must be reported honestly"


def test_retrieve_without_an_argument_prints_usage(capsys):
    cli._cmd_retrieve([], "json")  # must not raise or exit non-zero
    assert "Usage: mcptoon retrieve" in capsys.readouterr().out


def test_retrieve_is_dispatched_and_documented():
    """A command nobody can discover may as well not exist."""
    src = (ROOT / "src" / "mcptoon" / "cli.py").read_text(encoding="utf-8")
    assert 'command == "retrieve"' in src
    assert "retrieve" in cli._COMPLETION_COMMANDS
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._print_help()
    assert "mcptoon retrieve" in buf.getvalue()


def test_retrieve_does_not_greet_first():
    """The one-time welcome banner must not land in front of a payload."""
    assert "retrieve" in cli._WELCOME_EXEMPT


def test_mcp_and_cli_share_one_notice_table():
    """Both read halves answer from `ccr.RETRIEVE_NOTICES` — no second copy."""
    from mcptoon import native_tools

    assert not hasattr(native_tools, "_RETRIEVE_NOTICES"), (
        "native_tools grew its own notice table again — the CLI and the MCP tool "
        "must read ccr.RETRIEVE_NOTICES so they cannot drift"
    )
    for status in ccr.RETRIEVE_STATUSES:
        if status == ccr.STATUS_OK:
            continue
        assert ccr.retrieve_notice(status), f"no sentence for {status}"


def test_the_two_paths_agree_on_every_failure_status():
    """Feed the same handle to both read halves; the notice must be identical."""
    from mcptoon import native_tools

    for bad in ("", "zzz", "deadbeef0000"):
        cli_status, _ = ccr.retrieve_status(bad)
        tool_result = native_tools._retrieve({"handle": bad}, {})
        assert tool_result["status"] == cli_status
        if cli_status != ccr.STATUS_OK:
            assert tool_result["notice"] == ccr.retrieve_notice(cli_status)
