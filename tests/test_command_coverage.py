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


# ─── The other direction: the dispatcher is the authority, not the help ───
#
# The guards above all start from `_print_help()` and look outward, which quietly
# assumes the help is complete. It was not. `mcptoon config`, `mcptoon stats` and
# `mcptoon toggle` were fully implemented and reachable — while appearing in
# neither `--help` nor either README. `config` is the worst of the three to lose:
# it is how a user turns the per-turn savings line off, so the release that
# promised "you can switch this off" shipped with the switch unfindable.
#
# A command you cannot discover may as well not exist, and no outward-looking
# guard can ever catch that. These two go inward: the dispatcher in cli.py is the
# source of truth, and everything it accepts must be either advertised or an
# explicitly declared alias of something advertised.

#: Commands that exist only as short forms of an advertised one. Every entry is
#: checked below to make sure its target really is advertised, so this cannot be
#: used to smuggle a hidden command past the guard.
_ALIASES = {
    "servers": "list",
    "tools": "manifest",
    "qs": "quickstart",
    "brief": "status",
    "help": "help",
    "-h": "help",
    "--help": "help",
}

#: Top-level subcommands whose parent command is what a user is told to type.
#: `mcptoon skills resolve` is covered by `mcptoon skills`; the dispatcher has no
#: branch of its own for these because the parent hands `rest` to its own parser.
_SUBCOMMANDS_OF_AN_ADVERTISED_PARENT = {"resolve", "route", "index"}

_DISPATCH_BRANCH = re.compile(
    r"(?:el)?if command (?:== \"([a-z][a-z-]*)\"|in \(([^)]*)\))", re.M)


def _dispatched_commands() -> set[str]:
    """Every command name the dispatch chain in cli.py accepts."""
    source = (ROOT / "src" / "mcptoon" / "cli.py").read_text(encoding="utf-8")
    found: set[str] = set()
    for single, group in _DISPATCH_BRANCH.findall(source):
        if single:
            found.add(single)
        found |= set(re.findall(r'"([a-z][a-z-]*)"', group))
    return found


def test_the_dispatch_scraper_still_works():
    """Guard the guard: if the dispatch shape changes, fail loudly, do not pass empty."""
    found = _dispatched_commands()
    assert len(found) >= 25, (
        f"only parsed {len(found)} commands out of cli.py's dispatch chain — the "
        f"scraper in this file no longer matches the code it audits"
    )
    assert {"list", "call", "sync", "config"}.issubset(found)


def test_every_dispatched_command_is_either_advertised_or_a_declared_alias():
    advertised = _advertised_commands()
    dispatched = _dispatched_commands()
    hidden = sorted(
        c for c in dispatched
        if c not in advertised
        and c not in _ALIASES
        and c not in _SUBCOMMANDS_OF_AN_ADVERTISED_PARENT
    )
    assert not hidden, (
        f"cli.py accepts these commands but `mcptoon --help` never mentions them: "
        f"{hidden}. A command nobody can find may as well not exist — add it to "
        f"_print_help(), or declare it in _ALIASES if it is only a short form."
    )


def test_every_declared_alias_points_at_something_advertised():
    """`_ALIASES` must not become a place to hide a command."""
    advertised = _advertised_commands()
    orphaned = sorted(a for a, target in _ALIASES.items()
                      if target not in advertised and target != "help")
    assert not orphaned, (
        f"these aliases point at a command that is not advertised: {orphaned}"
    )


def test_the_help_has_no_duplicate_command_lines():
    """Within one section of `--help`, no command may be listed twice.

    The `Start here` block is a highlight: it deliberately repeats four commands
    that also have a place in the Usage list, which is what a front door is for.
    Repetition *inside* one section is the defect — the Usage block listed
    `mcptoon uninstall` twice (bare, and again as `--dry`), which reads as two
    different commands and made the page longer than it was informative.
    """
    from mcptoon import cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._print_help()

    duplicates: dict[str, list[str]] = {}
    section = "top"
    seen: dict[str, str] = {}
    for line in buf.getvalue().splitlines():
        if re.match(r"^\S.*:\s*$", line):  # a section header, e.g. "Usage:"
            section = line.strip().rstrip(":")
            seen = {}
            continue
        m = re.match(r"^\s+mcptoon ([a-z][a-z-]+)\s{2,}\S", line)
        if not m:  # continuation lines and argument-only examples do not count
            continue
        command = m.group(1)
        if command in seen:
            duplicates.setdefault(section, []).append(command)
        seen[command] = line
    assert not duplicates, (
        f"`mcptoon --help` lists the same command more than once inside a single "
        f"section: {duplicates}"
    )


def test_the_help_description_column_does_not_drift():
    """Keep the front door aligned.

    The help had drifted into two alignment groups — everything down to `install`
    padded to column 42, the rest to 41 — which is visible as a ragged edge in the
    one block whose entire job is to look like a front door.
    """
    from mcptoon import cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._print_help()
    columns = {}
    for line in buf.getvalue().splitlines():
        m = re.match(r"^(    mcptoon .*?)(\s{2,})(\S.*)$", line)
        if m:
            columns.setdefault(len(m.group(1)) + len(m.group(2)), []).append(line)
    assert columns, "_print_help() printed no aligned command lines"
    dominant = max(columns, key=lambda c: len(columns[c]))
    strays = {c: lines for c, lines in columns.items() if c != dominant}
    assert not strays, (
        "\n".join(f"column {c} (expected {dominant}): {lines[0].strip()}"
                  for c, lines in strays.items())
    )

