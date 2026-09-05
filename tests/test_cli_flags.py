"""Unknown CLI flags must be reported, not swallowed.

Background: the README advertised `mcptoon manifest --compact --tokens` as the way
to reproduce the headline token numbers. --tokens was never implemented, and the
parser dropped unknown flags silently, so the command "worked" and printed no
count. These tests keep both halves honest: the parser warns, and the warning
allowlist cannot drift away from the flags the CLI actually implements.
"""

from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import mcptoon
from mcptoon import cli
from mcptoon.cli import KNOWN_FLAGS, unknown_flag_warnings

CLI_SOURCE = Path(__file__).resolve().parents[1] / "src" / "mcptoon" / "cli.py"

# Names that appear in cli.py only to be cited as examples of what does NOT exist.
DOCUMENTED_AS_ABSENT = {"--tokens"}


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


class TestKnownFlagRegistry(unittest.TestCase):
    def test_registry_covers_every_flag_literal_in_the_cli(self):
        """A new --flag in cli.py must be added to KNOWN_FLAGS or this fails."""
        source = CLI_SOURCE.read_text(encoding="utf-8")
        literals = set(re.findall(r"--[a-z][a-z0-9-]*", source))
        unregistered = literals - set(KNOWN_FLAGS) - DOCUMENTED_AS_ABSENT
        self.assertFalse(
            unregistered,
            f"flags used in cli.py but missing from KNOWN_FLAGS: {sorted(unregistered)}",
        )

    def test_registry_has_no_dead_entries(self):
        """A flag removed from the CLI must leave KNOWN_FLAGS too."""
        source = CLI_SOURCE.read_text(encoding="utf-8")
        literals = set(re.findall(r"--[a-z][a-z0-9-]*", source))
        dead = set(KNOWN_FLAGS) - literals
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


if __name__ == "__main__":
    unittest.main()
