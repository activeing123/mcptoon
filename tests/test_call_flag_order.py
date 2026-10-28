"""Issue #37 — `mcptoon call` options must work before *or* after the positionals.

Reported: `mcptoon call --destructive <server> <tool>` fed the flag in as the server
name and died with UNKNOWN_SERVER, while the identical flag placed after the
positionals worked. `--destructive` was the one call-level flag not stripped before
the positionals were read; `--envelope`, `--stdin`, `--input-responses`,
`--request-state` and `--auto` already were.

Two layers are pinned here: the user-visible symptom (which server the error names)
and the semantics (`--destructive` must still be *recognised*, not merely skipped —
a strip that silently dropped it would "fix" the symptom and disable the safeguard).
"""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from mcptoon import cli


def _run(argv):
    """Drive cli.main() end-to-end, capturing (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with patch.object(sys, "argv", ["mcptoon"] + argv):
        try:
            with redirect_stdout(out), redirect_stderr(err):
                cli.main()
        except SystemExit as e:
            code = e.code if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


def _capture(argv, monkeypatch):
    """Run a `call` with the router stubbed; return (exit_code, what call_tool saw)."""
    seen = {}

    def fake_call(server, tool, args=None, **kw):
        seen.update(server=server, tool=tool, args=args,
                    is_destructive=kw.get("is_destructive"))
        return {"ok": True}

    monkeypatch.setattr(cli, "call_tool", fake_call)
    code, _out, err = _run(argv)
    return code, seen, err


# ── the semantics: the flag is recognised in both positions ──

def test_destructive_is_recognised_before_and_after_the_positionals(monkeypatch):
    want = {"server": "srv", "tool": "tool", "args": {}, "is_destructive": True}
    for argv in (["call", "--destructive", "srv", "tool"],
                 ["call", "srv", "tool", "--destructive"]):
        code, seen, err = _capture(argv, monkeypatch)
        assert code == 0, err
        assert seen == want, f"{argv} parsed as {seen!r}"


def test_without_the_flag_the_call_is_not_marked_destructive(monkeypatch):
    code, seen, err = _capture(["call", "srv", "tool"], monkeypatch)
    assert code == 0, err
    assert seen["is_destructive"] is False


def test_json_args_survive_the_flag_in_either_position(monkeypatch):
    before = _capture(["call", "--destructive", "srv", "tool", '{"q": 1}'], monkeypatch)[1]
    after = _capture(["call", "srv", "tool", '{"q": 1}', "--destructive"], monkeypatch)[1]
    assert before == after
    assert before["args"] == {"q": 1}
    assert before["is_destructive"] is True


# ── the reported symptom, against the real (unstubbed) path ──

def test_the_reported_symptom_is_gone():
    code, out, err = _run(["call", "--destructive", "nosuchserver", "nosuchtool"])
    assert code != 0
    assert "nosuchserver" in err, err
    assert "'--destructive'" not in err, "the flag was read as the server name"
    assert "--destructive" not in out


def test_both_orders_fail_identically():
    before = _run(["call", "--destructive", "nosuchserver", "nosuchtool"])
    after = _run(["call", "nosuchserver", "nosuchtool", "--destructive"])
    assert before == after, (
        f"flag order must not change the outcome: {before!r} vs {after!r}")


def test_a_flag_with_no_server_is_a_usage_error_not_a_server_lookup():
    # The flag is stripped before the arity check, so this is "missing arguments"
    # rather than reading `nosuchserver` as the tool name.
    code, _out, err = _run(["call", "--destructive", "nosuchserver"])
    assert code != 0
    assert "Usage:" in err, err


def test_the_already_order_insensitive_flags_stay_that_way():
    for argv in (["call", "--envelope", "nosuchserver", "nosuchtool"],
                 ["call", "nosuchserver", "nosuchtool", "--envelope"]):
        code, _out, err = _run(argv)
        assert code != 0
        assert "--envelope" not in err, argv
