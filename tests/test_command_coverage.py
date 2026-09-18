"""Every command the CLI advertises must be documented in both READMEs.

Why this exists: v0.7.17 nearly shipped with `mcptoon skills` — the entire headline
feature of the release — absent from the top-level help text *and* from both
READMEs. The feature worked, the suite was green, and no user could discover it.
Nothing in the repo noticed, because every other guard checks numbers, not coverage.

The CLI's own help is the authority for "what commands exist": if a command is
listed there, a reader is entitled to find it in the README that ships as the PyPI
description. This guard fails loudly when the two drift apart.

Deliberately scoped to top-level commands (the ones in the Usage block), not
subcommands or flags — `mcptoon skills resolve` is covered by `mcptoon skills`.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README.zh-CN.md")

# Anchor to the start of a Usage line so prose like "legacy mcptoon pipe format"
# cannot be mistaken for a command named `pipe`.
_USAGE_LINE = re.compile(r"^\s+mcptoon ([a-z][a-z-]+)", re.M)


def _advertised_commands() -> set[str]:
    from mcptoon import cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._print_help()
    help_text = buf.getvalue()
    assert "Usage:" in help_text, (
        "_print_help() printed no Usage block; this guard needs updating alongside "
        "the CLI structure"
    )
    return set(_USAGE_LINE.findall(help_text))


def test_help_block_advertises_commands():
    commands = _advertised_commands()
    assert len(commands) >= 15, f"parsed only {len(commands)} commands from help"


@pytest.mark.parametrize("readme", READMES)
def test_every_advertised_command_is_documented(readme):
    text = (ROOT / readme).read_text(encoding="utf-8")
    missing = sorted(c for c in _advertised_commands() if f"mcptoon {c}" not in text)
    assert not missing, (
        f"{readme} never mentions these commands that `mcptoon help` advertises: "
        f"{missing}. A command nobody can discover may as well not exist — document "
        f"it in the 'All commands' block."
    )


def test_the_skills_family_is_documented():
    """The regression that motivated this file: the headline feature was invisible."""
    for readme in READMES:
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert "mcptoon skills list" in text, f"{readme} does not document the skills command"
        assert "mcptoon skills sync" in text, f"{readme} does not document skills sync"
