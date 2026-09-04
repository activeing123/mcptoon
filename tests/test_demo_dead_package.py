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

"""Regression tests for the demo dead-package failure (found 2026-09-05).

`mcptoon demo` spawned `npx -y @modelcontextprotocol/server-fetch`, a
package that no longer exists on the npm registry (E404, verified
2026-09-05). The server died instantly and every `mcptoon demo` failed
with `PROCESS_DIED failed writing ... [Errno 22]` on Windows (broken
pipe on POSIX) plus a misleading "install Node.js" hint, with the real
`npm error 404` swallowed.

These tests pin the fix:
  1. the demo never references the dead package again,
  2. a server that dies before responding surfaces its stderr tail,
  3. the demo flow calls the `echo` tool and returns its text,
  4. the benchmark table shows the official tiktoken numbers.
"""

import os
import sys
import unittest
import contextlib
from unittest import mock
from io import StringIO

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcptoon import demo as demo_mod
from mcptoon.client import MCPClient, MCPError

_DEMO_SRC = os.path.join(
    os.path.dirname(__file__), "..", "src", "mcptoon", "demo.py")

_DEAD_SERVER_CMD = [
    sys.executable, "-c",
    "import sys; sys.stderr.write('npm error 404 E404: package gone'); "
    "sys.stderr.flush(); sys.exit(1)",
]


class TestDemoServerPackage(unittest.TestCase):
    """The demo must not reference packages that are gone from npm."""

    def test_no_dead_fetch_package(self):
        """server-fetch is gone from npm (E404) — never spawn it again."""
        with open(_DEMO_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn(
            '"npx", "-y", "@modelcontextprotocol/server-fetch"', src)

    def test_uses_everything_reference_server(self):
        """The demo spawns the official everything reference server."""
        with open(_DEMO_SRC, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("@modelcontextprotocol/server-everything", src)


class TestDeadServerStderrSurfaces(unittest.TestCase):
    """A server dying before responding must surface its stderr tail."""

    def test_process_died_includes_stderr(self):
        """Real subprocess: stderr tail reaches the MCPError message."""
        client = MCPClient(stdio=_DEAD_SERVER_CMD, timeout=10)
        try:
            with self.assertRaises(MCPError) as cm:
                client.initialize()
        finally:
            try:
                client.close()
            except Exception:
                pass
        self.assertEqual(cm.exception.code, "PROCESS_DIED")
        # Either the write path (Errno 22 / EPIPE) or the EOF-sentinel
        # path fires first — both must carry the stderr tail now.
        self.assertIn("npm error 404", str(cm.exception))


class TestDemoEchoFlow(unittest.TestCase):
    """The demo flow talks to the server via the echo tool."""

    def test_demo_call_uses_echo_tool(self):
        """echo replaces the dead fetch tool; result text is returned."""
        fake = mock.MagicMock()
        fake.list_tools.return_value = [{"name": "echo"}]
        fake.call_tool.return_value = [
            {"type": "text", "text": "Echo: mcptoon demo works"},
        ]
        with mock.patch.object(demo_mod, "MCPClient", return_value=fake):
            text = demo_mod._demo_call(
                "demo-everything", ["npx", "-y", "x"],
                "mcptoon demo works", quick=True)
        fake.call_tool.assert_called_once_with(
            "echo", {"message": "mcptoon demo works"})
        self.assertEqual(text, "Echo: mcptoon demo works")
        fake.close.assert_called_once()

    def test_demo_call_failure_closes_client(self):
        """On failure the client is still closed (no leaked processes)."""
        fake = mock.MagicMock()
        fake.initialize.side_effect = MCPError(
            "PROCESS_DIED", "boom | server stderr: npm error 404")
        with mock.patch.object(demo_mod, "MCPClient", return_value=fake):
            buf = StringIO()
            with contextlib.redirect_stdout(buf):
                text = demo_mod._demo_call(
                    "demo-everything", ["npx", "-y", "x"], "hi", quick=True)
        self.assertIsNone(text)
        fake.close.assert_called_once()
        self.assertIn("npm error 404", buf.getvalue())


class TestBenchmarkOfficialNumbers(unittest.TestCase):
    """The benchmark table shows the official tiktoken numbers."""

    def test_benchmark_shows_official_numbers(self):
        """255 tools: 71,929 → 123 (−99.8%), aligned with
        assets/benchmark_tiktoken.json."""
        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            demo_mod._show_benchmark()
        out = buf.getvalue()
        self.assertIn("71,929", out)
        self.assertIn("47,438", out)
        self.assertIn("8,282", out)
        self.assertIn("123", out)
        self.assertIn("99.8%", out)


if __name__ == "__main__":
    unittest.main()
