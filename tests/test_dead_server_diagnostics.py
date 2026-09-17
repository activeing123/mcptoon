# Copyright 2025-2026 cxh
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

"""A dead server must report WHY it died, not the first bytes of noise.

Found 2026-09-17 during the Windows first-install field test. Three configured
servers (`git`, `time`, `docker`) point at npm packages that no longer exist
(E404). They die on startup, and mcptoon then reports:

    [PROCESS_DIED] MCP server process exited. stderr: (node:6035) Warning: Sett...

The real cause — `npm error 404 Not Found ... server-git` — sits at the END of
stderr, past both the 500-char read window and the 100-char message cap, so a
user sees a Node TLS warning instead of "this package does not exist".

`tests/test_demo_dead_package.py` covers the same class of failure but feeds a
48-character stderr, so it never exercised the truncation. These tests use a
realistic npm stderr: a long warning block first, the diagnostic last.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcptoon.client import MCPClient, MCPError  # noqa: E402

# A realistic npm failure: ~600 chars of Node warning, THEN the diagnostic.
_NODE_WARNING = (
    "(node:12345) Warning: Setting the NODE_TLS_REJECT_UNAUTHORIZED "
    "environment variable to '0' makes TLS connections and HTTPS requests "
    "insecure by disabling certificate verification.\n"
    "(Use `node --trace-warnings ...` to show where the warning was created)\n"
)
_NPM_404 = (
    "npm error code E404\n"
    "npm error 404 Not Found - GET "
    "https://registry.npmjs.org/@modelcontextprotocol%2fserver-git - Not found\n"
    "npm error 404\n"
    "npm error 404  The requested resource "
    "'@modelcontextprotocol/server-git@*' could not be found.\n"
)
# Pad so the diagnostic lands past 500 chars — exactly the real-world layout.
_REALISTIC_STDERR = (_NODE_WARNING * 4) + _NPM_404

_DEAD_SERVER = [
    sys.executable, "-c",
    "import sys; sys.stderr.write(sys.argv[1]); sys.stderr.flush(); sys.exit(1)",
    _REALISTIC_STDERR,
]


class TestDiagnosticSurvivesTruncation(unittest.TestCase):
    """The actionable line must reach the user, however long the preamble is."""

    def test_diagnostic_past_the_warning_block_is_reported(self):
        client = MCPClient(stdio=_DEAD_SERVER, timeout=10)
        try:
            with self.assertRaises(MCPError) as cm:
                client.initialize()
        finally:
            try:
                client.close()
            except Exception:
                pass
        self.assertEqual(cm.exception.code, "PROCESS_DIED")
        msg = str(cm.exception)
        # The whole point: the 404 is at ~char 600 of stderr.
        self.assertIn(
            "npm error 404", msg,
            "the real cause (npm E404) was truncated away; user sees only the "
            "Node warning. Full message was:\n" + msg)

    def test_the_node_warning_is_not_the_headline(self):
        """Diagnostic lines should lead; the TLS warning is background noise."""
        client = MCPClient(stdio=_DEAD_SERVER, timeout=10)
        try:
            with self.assertRaises(MCPError) as cm:
                client.initialize()
        finally:
            try:
                client.close()
            except Exception:
                pass
        msg = str(cm.exception)
        npm_at = msg.find("npm error")
        warn_at = msg.find("NODE_TLS_REJECT_UNAUTHORIZED")
        # A user should not have to read past a wall of Node warnings to learn
        # that the package is missing. Either the warning is dropped entirely,
        # or the diagnostic leads.
        self.assertNotEqual(npm_at, -1, "the diagnostic is missing entirely")
        self.assertTrue(
            warn_at == -1 or npm_at < warn_at,
            "the Node warning is reported before the actual diagnostic")


class TestStderrTailKeepsTheEnd(unittest.TestCase):
    """`_stderr_tail` must return the TAIL — process errors are printed last."""

    def test_tail_keeps_the_final_bytes(self):
        client = MCPClient(stdio=_DEAD_SERVER, timeout=10)
        try:
            try:
                client.initialize()
            except MCPError:
                pass
            tail = client._stderr_tail()
        finally:
            try:
                client.close()
            except Exception:
                pass
        self.assertTrue(tail, "stderr tail was empty")
        self.assertIn("npm error 404", tail,
                      "tail dropped the diagnostic at the end of stderr")


if __name__ == "__main__":
    unittest.main()
