"""Every flag a shipped doc shows after a command must be one that command accepts.

The docs are the contract a reader acts on; `cli.COMMAND_FLAGS` is what the CLI
enforces. Once a command is registered, every `mcptoon <command> ... --flag` in the
shipped markdown has to be either consumed by the global pre-pass or owned by that
command — otherwise we document an invocation that now exits 2.

This is the net that lets the registry grow one command at a time: registering a
command with an incomplete flag set fails here rather than in a user's terminal.
It is a text sweep, so it cannot see a flag that only exists in someone's shell
history — it catches the flags we *promise*, which is the failure mode that matters.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from mcptoon import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "README.zh-CN.md", ROOT / "DEVELOPERS.md",
        ROOT / "AGENTS.md", ROOT / "ROADMAP.md", ROOT / "CONTRIBUTING.md",
        *sorted((ROOT / "docs").glob("*.md"))]

CALL = re.compile(r"mcptoon\s+([a-z][a-z0-9-]*)([^\n`|]*)")
FLAG = re.compile(r"--[a-z][a-z0-9-]*")


def documented_flags() -> dict[str, set[str]]:
    """{command: flags the shipped docs show it taking}."""
    seen: dict[str, set[str]] = {}
    for path in DOCS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            for match in CALL.finditer(line):
                seen.setdefault(match.group(1), set()).update(FLAG.findall(match.group(2)))
    return seen


def test_the_sweep_actually_reads_the_docs():
    seen = documented_flags()
    assert len(seen) > 20, f"only {len(seen)} commands found - the sweep is broken"
    assert {"list", "manifest", "install"} <= set(seen)


@pytest.mark.parametrize("command", sorted(cli.COMMAND_FLAGS))
def test_every_documented_flag_of_a_registered_command_is_accepted(command):
    cited = documented_flags().get(command, set())
    owned = cli.COMMAND_FLAGS[command]
    # Only flags the *ownership* check can reject count. A name outside KNOWN_FLAGS is
    # already an unknown option for every command — the docs cite `--jsn` on purpose,
    # as a typo demo — so that is the pre-pass's test, not this table's.
    rejectable = cli.KNOWN_FLAGS - cli.PREPASS_FLAGS
    rejected = sorted(f for f in cited if f in rejectable and f not in owned)
    assert not rejected, (
        f"the docs show `mcptoon {command} ... {' '.join(rejected)}`, but the "
        f"ownership check would exit 2 - add it to COMMAND_FLAGS or fix the doc"
    )


def test_prepass_flags_are_recognised_globals():
    assert cli.PREPASS_FLAGS <= cli.KNOWN_FLAGS


def test_no_command_declares_a_prepass_flag():
    """A pre-pass flag never reaches `rest`, so declaring it as owned is dead weight
    that hides a real omission (the set would look complete while a flag is missing)."""
    for command, owned in sorted(cli.COMMAND_FLAGS.items()):
        overlap = sorted(owned & cli.PREPASS_FLAGS)
        assert not overlap, f"{command} declares pre-pass flag(s) {overlap}"


def test_every_registered_flag_is_a_known_flag():
    """The pre-pass rejects an unknown flag before ownership is even consulted, so a
    name that is not in KNOWN_FLAGS could never be reached — it would be a typo in
    this table that no test would otherwise catch."""
    unknown = {c: sorted(f for f in flags if f not in cli.KNOWN_FLAGS)
               for c, flags in cli.COMMAND_FLAGS.items()}
    assert not {c: f for c, f in unknown.items() if f}, f"not in KNOWN_FLAGS: {unknown}"
