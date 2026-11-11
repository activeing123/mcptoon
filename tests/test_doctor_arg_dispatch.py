# Copyright 2025-2026 activeing123
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

"""Where `doctor`'s JSON mode is decided — on the resolved command, not a token.

Review item on #44 (2026-11-08): the global pre-pass asked `"doctor" in cmd_args`,
a membership test over the raw tokens. It is true for a command that merely
*carries* `doctor` as a value (`mcptoon inspect doctor --json`) and false for
`mcptoon --json doctor`, because a leading `--json` is consumed as a global format
flag before the command token is ever appended. That spelling therefore lost its
JSON output, which the pre-refactor `fmt == "json" or "--json" in rest` check did
honour. These drive `cli.main` end-to-end with the handlers stubbed out.
"""
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from mcptoon import cli


def _drive(argv, monkeypatch, doctor_calls, inspect_calls=None):
    """Run `cli.main()` for `argv`, recording which handler got what."""
    monkeypatch.setattr(
        cli, "_cmd_doctor",
        lambda rest, json_mode=False: doctor_calls.append((list(rest), json_mode)),
    )
    if inspect_calls is not None:
        monkeypatch.setattr(cli, "_cmd_inspect", lambda *a, **k: inspect_calls.append(a))
    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, "argv", ["mcptoon"] + argv), \
            redirect_stdout(out), redirect_stderr(err):
        try:
            cli.main()
        except SystemExit:
            pass
    return out.getvalue(), err.getvalue()


def test_json_after_the_command_reaches_doctor(monkeypatch):
    calls = []
    _drive(["doctor", "--json"], monkeypatch, calls)
    assert calls == [([], True)], "`mcptoon doctor --json` must arrive as json_mode"


def test_json_before_the_command_reaches_doctor(monkeypatch):
    # The regression their pre-pass introduced: `--json` is consumed before the
    # command token exists, so a token test could never see it.
    calls = []
    _drive(["--json", "doctor"], monkeypatch, calls)
    assert calls == [([], True)], "`mcptoon --json doctor` must arrive as json_mode"


def test_plain_doctor_stays_human_readable(monkeypatch):
    calls = []
    _drive(["doctor"], monkeypatch, calls)
    assert calls == [([], False)], "no --json anywhere → human output"


def test_doctor_as_an_argument_value_elsewhere_is_not_doctor(monkeypatch):
    # `doctor` here is a server name for `inspect`, not the command. The branch
    # must stay with `inspect`, and no flag may be re-routed into its tail.
    calls, seen = [], []
    _drive(["inspect", "doctor", "--json"], monkeypatch, calls, inspect_calls=seen)
    assert calls == [], "an argument value must not switch parsing modes"
    assert seen and seen[0][0] == ["doctor"], f"inspect lost its tail: {seen!r}"
