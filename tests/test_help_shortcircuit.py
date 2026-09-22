"""A help request must never run the command it asks about.

Background (found 2026-09-14 while auditing the try-before-install funnel):
`mcptoon quickstart --help` ignored the flag and executed the whole onboarding
flow — it discovered servers and wrote them into ~/.mcptoon/config.json (measured:
4 servers in, 13 out). `mcptoon manifest --help` ignored it too and went out to every
configured server, still running two minutes later. A first-time user probing the CLI
with --help was mutating their machine, or waiting on a network round trip, before
reading a single line of help.

These tests pin the contract: -h/--help anywhere after the command prints help and
returns; the command body is never reached — except in commands that ship their own
help text (demo, serve), which must keep showing it instead of the general page.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from mcptoon import cli


def _exploder(name):
    """Return a callable that fails the test if the command body is reached."""

    def _boom(*args, **kwargs):
        raise AssertionError(f"{name} executed while only help was requested")

    return _boom


class TestHelpShortCircuit(unittest.TestCase):
    def _run(self, argv, patched):
        """Run cli.main() with `patched` (command -> fake body); return stdout."""
        buf = io.StringIO()
        stack = [patch.object(cli, cmd, body) for cmd, body in patched.items()]
        with patch.object(sys, "argv", ["mcptoon", *argv]), redirect_stdout(buf):
            for ctx in stack:
                ctx.start()
            try:
                cli.main()
            finally:
                for ctx in stack:
                    ctx.stop()
        return buf.getvalue()

    def test_quickstart_help_does_not_write_config(self):
        out = self._run(["quickstart", "--help"], {"_cmd_quickstart": _exploder("quickstart")})
        self.assertIn("mcptoon quickstart", out)

    def test_quickstart_short_help_same_behaviour(self):
        out = self._run(["qs", "-h"], {"_cmd_quickstart": _exploder("quickstart")})
        self.assertIn("mcptoon quickstart", out)

    def test_serve_keeps_its_own_help_page(self):
        """serve prints command-specific help and exits — the guard must not swallow it."""
        buf = io.StringIO()
        with patch.object(sys, "argv", ["mcptoon", "serve", "--help"]), redirect_stdout(buf):
            with self.assertRaises(SystemExit) as caught:
                cli.main()
        self.assertEqual(caught.exception.code, 0)
        out = buf.getvalue()
        self.assertIn("mcptoon serve", out)
        self.assertIn("Parallel manifest loading", out)
        self.assertNotIn("Token-efficient MCP CLI client", out)

    def test_manifest_help_does_not_go_to_the_network(self):
        """The other half of the incident: asking help must not cost a server round trip."""
        out = self._run(["manifest", "--help"], {"_cmd_manifest": _exploder("manifest")})
        self.assertIn("mcptoon manifest", out)

    def test_state_changing_commands_all_short_circuit(self):
        for command, func in (
            ("init", "_cmd_init"),
            ("sync", "_cmd_sync"),
            ("add", "_cmd_add"),
            ("remove", "_cmd_remove"),
            ("install", "_cmd_install"),
            ("discover", "_cmd_auto_discover"),
            ("plugin", "_cmd_plugin"),
        ):
            with self.subTest(command=command):
                out = self._run([command, "--help"], {func: _exploder(command)})
                self.assertIn("Output flags:", out)

    def test_read_only_commands_short_circuit_too(self):
        for command, func in (
            ("manifest", "_cmd_manifest"),
            ("list", "_cmd_list"),
            ("doctor", "_cmd_doctor"),
            ("health", "_cmd_health"),
        ):
            with self.subTest(command=command):
                out = self._run([command, "--help"], {func: _exploder(command)})
                self.assertIn("mcptoon quickstart", out)

    def test_help_is_still_help_before_a_command(self):
        out = self._run(["--help"], {"_cmd_manifest": _exploder("manifest")})
        self.assertIn("one gateway for all your MCP tools", out)
        # The front door must also show the exit: a CLI whose help never mentions
        # how to undo its agent-config writes is the reason mcptoon felt like a
        # trojan. `off`/`uninstall` live in the help's "Start here" block.
        self.assertIn("mcptoon off", out)
        self.assertIn("mcptoon uninstall", out)

    def test_demo_keeps_its_own_help_handler(self):
        """demo prints command-specific help itself; the guard must not swallow it."""
        seen = {}

        def _record(rest, *args, **kwargs):
            seen["rest"] = list(rest)

        out = self._run(["demo", "--help"], {"_cmd_demo": _record})
        self.assertEqual(seen.get("rest"), ["--help"])
        self.assertEqual(out, "")

    def test_arguments_are_not_mistaken_for_help(self):
        """A JSON payload or value containing --help still reaches the command."""
        seen = {}

        def _record(rest, *args, **kwargs):
            seen["rest"] = list(rest)

        argv = ["call", "srv", "tool", '{"text":"mcptoon --help"}']
        with patch.object(cli, "_cmd_call", _record):
            with patch.object(sys, "argv", ["mcptoon", *argv]), redirect_stdout(io.StringIO()):
                cli.main()
        self.assertEqual(seen.get("rest"), ["srv", "tool", '{"text":"mcptoon --help"}'])


if __name__ == "__main__":
    unittest.main()
