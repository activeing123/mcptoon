"""Unknown CLI flags — and a dropped `--smart` — must be reported, not swallowed.

Background: the README advertised `mcptoon manifest --compact --tokens` as the way
to reproduce the headline token numbers. --tokens was never implemented, and the
parser dropped unknown flags silently, so the command "worked" and printed no
count. These tests keep both halves honest: the parser warns, and the warning
allowlist cannot drift away from the flags the CLI actually implements.

The second silent drop is the same shape. The format flags are one family and the last
one wins, so `--smart` followed by `--json` compresses nothing and says nothing — the
output is still valid JSON, just larger, so the caller cannot notice. The sibling file
`tests/test_smart_reachability.py` pins that `smart` *reaches* the compressor; these
tests pin that it is not *silently removed before* it gets there.
"""

from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mcptoon
from mcptoon import cli
from mcptoon.cli import KNOWN_FLAGS, unknown_flag_warnings

CLI_SOURCE = Path(__file__).resolve().parents[1] / "src" / "mcptoon" / "cli.py"
SRC_PKG = Path(__file__).resolve().parents[1] / "src" / "mcptoon"

# Names that appear in cli.py only to be cited as examples of what does NOT exist.
DOCUMENTED_AS_ABSENT = {"--tokens"}


def package_flag_literals():
    """Every --flag written anywhere in the package, mapped to its source files."""
    hits = {}
    for path in sorted(SRC_PKG.glob("*.py")):
        for flag in re.findall(r"--[a-z][a-z0-9-]*", path.read_text(encoding="utf-8")):
            hits.setdefault(flag, set()).add(path.name)
    return hits


class TestUnknownFlagWarnings(unittest.TestCase):
    def test_phantom_flag_is_reported(self):
        self.assertEqual(
            unknown_flag_warnings(["manifest", "--compact", "--tokens"]), ["--tokens"]
        )

    def test_typo_of_a_real_flag_is_reported(self):
        self.assertEqual(unknown_flag_warnings(["--compakt"]), ["--compakt"])

    def test_known_flags_are_not_reported(self):
        argv = [
            "manifest", "--compact", "--slim", "--toon", "--json", "--full",
            "sync", "--dry", "--agent", "claude", "--watch",
            "call", "s", "t", "--stdin", "--envelope", "--timeout", "5",
            "discover", "--http", "http://x", "--health", "--write",
            "install", "n", "--npm", "pkg", "--pip", "pkg", "--url", "u", "--list",
            "--format", "openai", "--head", "5", "--max-chars", "80",
            "--no-sync", "--no-network", "--quiet", "--raw", "--mcptoon",
            "--fallback-json", "--request-state", "--input-responses", "--watch-mode",
            "--dry-run", "--force", "--remove", "--search", "--listen", "--stdio",
            "--no-configs", "--no-env", "--no-local", "--destructive", "--header",
            "--interval", "3", "--help",
        ]
        self.assertEqual(unknown_flag_warnings(argv), [])

    def test_value_flags_with_equals_are_recognised(self):
        self.assertEqual(unknown_flag_warnings(["--format=openai", "--head=5"]), [])

    def test_positional_and_json_payloads_are_untouched(self):
        argv = ["call", "srv", "tool", '{"q": "--not-a-flag"}', "-x"]
        self.assertEqual(unknown_flag_warnings(argv), [])

    def test_multiple_unknowns_are_all_reported(self):
        self.assertEqual(
            unknown_flag_warnings(["--nope", "list", "--nada"]), ["--nope", "--nada"]
        )

    def test_subcommand_local_flags_are_not_warned_about(self):
        """demo.py / serve.py parse these themselves; they are real, not phantoms."""
        argv = ["demo", "--quick", "--keep", "serve", "--http", "--auth", "tok"]
        self.assertEqual(unknown_flag_warnings(argv), [])


class TestKnownFlagRegistry(unittest.TestCase):
    def test_registry_covers_every_flag_literal_in_the_package(self):
        """A new --flag anywhere in src/mcptoon must land in KNOWN_FLAGS.

        The scope is the whole package, not just cli.py: demo.py and serve.py parse
        their own flags (--quick, --keep, --auth), and while they were unregistered
        the central parser warned "unknown option ... ignored" on the very command a
        newcomer tries first.
        """
        offenders = {
            flag: sorted(sources)
            for flag, sources in package_flag_literals().items()
            if flag not in KNOWN_FLAGS and flag not in DOCUMENTED_AS_ABSENT
        }
        self.assertFalse(
            offenders,
            f"flags the package uses but KNOWN_FLAGS lacks: {offenders}",
        )

    def test_registry_has_no_dead_entries(self):
        """A flag removed from the CLI must leave KNOWN_FLAGS too."""
        source = CLI_SOURCE.read_text(encoding="utf-8")
        literals = set(re.findall(r"--[a-z][a-z0-9-]*", source))
        literals |= set(package_flag_literals())
        dead = set(KNOWN_FLAGS) - literals - DOCUMENTED_AS_ABSENT
        self.assertFalse(dead, f"KNOWN_FLAGS lists flags the CLI never mentions: {sorted(dead)}")


class TestVersionFlag(unittest.TestCase):
    def test_version_flag_prints_the_installed_version(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["mcptoon", "--version"]), redirect_stdout(buf):
            cli.main()
        self.assertEqual(buf.getvalue().strip(), f"mcptoon {mcptoon.__version__}")

    def test_short_version_flag_agrees(self):
        buf = io.StringIO()
        with patch.object(sys, "argv", ["mcptoon", "-V"]), redirect_stdout(buf):
            cli.main()
        self.assertEqual(buf.getvalue().strip(), f"mcptoon {mcptoon.__version__}")


class TestSmartFlagOverride(unittest.TestCase):
    """A superseded `--smart` must say so; a superseded `--toon` need not.

    `--smart`'s only effect is a smaller payload, so losing it is invisible: the command
    still exits 0 and prints well-formed JSON. The other format flags lose visibly — ask
    for TOON after `--json` and you can see you got JSON — so they stay quiet, and so does
    the order that works (`--json --smart`, which is how the gateway calls).
    """

    def test_smart_then_json_is_reported(self):
        note = cli.format_flag_override_note("--smart", "--json")
        self.assertIn("'--smart'", note)
        self.assertIn("'--json'", note)

    def test_the_note_names_the_consequence_not_just_the_order(self):
        note = cli.format_flag_override_note("--smart", "--toon")
        self.assertIn("NOT compressed", note)
        self.assertIn("put '--smart' last", note)

    def test_the_working_order_is_silent(self):
        self.assertEqual(cli.format_flag_override_note("--json", "--smart"), "")

    def test_pairs_that_lose_visibly_are_silent(self):
        self.assertEqual(cli.format_flag_override_note("--json", "--toon"), "")
        self.assertEqual(cli.format_flag_override_note("--compact", "--raw"), "")

    def test_nothing_to_supersede_is_silent(self):
        self.assertEqual(cli.format_flag_override_note("", "--json"), "")
        self.assertEqual(cli.format_flag_override_note("--smart", "--smart"), "")

    def test_every_format_flag_is_registered(self):
        """Pinned as a literal: the parse loop dispatches on this map now.

        A flag that is neither in the map nor anywhere else in the parser would silently
        stop selecting a format, which is the very failure this file exists to catch.
        """
        self.assertEqual(
            set(cli._FORMAT_FLAGS),
            {"--json", "--compact", "--toon", "--mcptoon", "--slim", "--smart", "--raw"},
        )

    def test_the_note_actually_reaches_stderr(self):
        """The unit is not enough — prove the parse loop prints it.

        `manifest --help` returns straight after the help guard, before the welcome and
        the first-run self-heal, so this drives the real parse loop with no network and
        no config writes.
        """
        err = io.StringIO()
        with patch.object(sys, "argv", ["mcptoon", "manifest", "--smart", "--json", "--help"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(err):
            cli.main()
        self.assertIn("overrides '--smart'", err.getvalue())

    def test_the_working_order_end_to_end_is_silent(self):
        err = io.StringIO()
        with patch.object(sys, "argv", ["mcptoon", "manifest", "--json", "--smart", "--help"]), \
                redirect_stdout(io.StringIO()), redirect_stderr(err):
            cli.main()
        self.assertNotIn("overrides", err.getvalue())


if __name__ == "__main__":
    unittest.main()
