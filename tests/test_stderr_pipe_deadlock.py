"""Regression tests for the unread-stderr pipe deadlock (issue #19).

An unread stderr pipe holds only a few KB. A server that logs more than that
blocks inside ``write()``, stops reading stdin and stops answering stdout — so
every request times out as though the server had "gone silent". One
``server/discover`` probe is enough to trigger it: the Python reference
servers answer that unknown method with ~6.8 KB of pydantic validation
warnings, which is why ``uvx mcp-server-fetch|time|git`` looked dead on a
fresh machine while ``spec="legacy"`` worked.

The fake server below reproduces the shape without needing uv or the network:
it floods stderr, then serves the protocol. It floods in two shapes on
purpose — newline-separated, and one long run with no newline at all. The
second shape is the one that pins the drain to chunked reads: iterating the
pipe by lines would sit on a partial line until EOF and block exactly like an
unread pipe.
"""
from __future__ import annotations

import sys
import unittest

from mcptoon.client import MCPClient, MCPError

# Comfortably past any platform's pipe buffer (Windows ~4 KB, POSIX 64 KB).
FLOOD_BYTES = 200_000

_SERVER = r"""
import json, sys

flood_size = int(sys.argv[1])
shape = sys.argv[2]

if shape == "flat":
    chunk = "E" * 4096          # no newline ever: a line reader would block
else:
    chunk = "E" * 79 + "\n"     # the pydantic-warning shape

written = 0
while written < flood_size:
    sys.stderr.write(chunk)
    written += len(chunk)
sys.stderr.write("\nSTDERR-FLOOD-END\n")
sys.stderr.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue
    method = req.get("method")
    rid = req.get("id")
    if method == "server/discover":
        reply = {"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32601, "message": "Method not found"}}
    elif method == "initialize":
        reply = {"jsonrpc": "2.0", "id": rid,
                 "result": {"protocolVersion": "2025-06-18", "capabilities": {},
                            "serverInfo": {"name": "flood", "version": "1"}}}
    elif method == "tools/list":
        reply = {"jsonrpc": "2.0", "id": rid,
                 "result": {"tools": [{"name": "flooded", "description": "d",
                                       "inputSchema": {"type": "object"}}]}}
    elif rid is None:
        continue  # notification
    else:
        reply = {"jsonrpc": "2.0", "id": rid, "result": {}}
    sys.stdout.write(json.dumps(reply) + "\n")
    sys.stdout.flush()
"""


def _client(shape: str, timeout: float = 8.0) -> MCPClient:
    return MCPClient(
        stdio=[sys.executable, "-c", _SERVER, str(FLOOD_BYTES), shape],
        timeout=timeout,
        spec="auto",
    )


class TestStderrFloodDoesNotDeadlock(unittest.TestCase):
    """spec="auto" must survive a server that logs more than a pipe buffer."""

    def _run(self, shape: str):
        client = _client(shape)
        try:
            client.initialize()
            tools = client.list_tools()
            tail = client._stderr_tail()
        finally:
            try:
                client.close()
            except Exception:
                pass
        return tools, tail

    def test_lined_flood_still_answers(self):
        tools, tail = self._run("lined")
        self.assertEqual([t["name"] for t in tools], ["flooded"],
                         "the flooded server never answered tools/list")
        self.assertIn("STDERR-FLOOD-END", tail,
                      "stderr was not drained — the tail lost the end marker")

    def test_flat_flood_still_answers(self):
        # No newline anywhere in the flood: a line-based drain would block on
        # the unterminated line and deadlock just like an unread pipe.
        tools, tail = self._run("flat")
        self.assertEqual([t["name"] for t in tools], ["flooded"],
                         "the flooded server never answered tools/list")
        self.assertIn("STDERR-FLOOD-END", tail,
                      "stderr was not drained — the tail lost the end marker")

    def test_drain_starts_before_the_probe(self):
        """The pump must be running while the server is alive, not after death.

        Reading stderr only once the process exits is what made the probe
        deadlock: by then the server had already blocked in write().
        """
        client = _client("lined")
        try:
            client.initialize()
            self.assertIsNotNone(client._stderr_thread)
            self.assertGreater(len(client._stderr_buf), 0,
                               "nothing was drained while the server was alive")
        finally:
            try:
                client.close()
            except Exception:
                pass


class TestStderrTailStillReportsDeaths(unittest.TestCase):
    """The live drain must not cost the post-mortem diagnostic."""

    def test_tail_survives_a_dead_server(self):
        client = MCPClient(
            stdio=[sys.executable, "-c",
                   "import sys; sys.stderr.write('boom-404\\n'); sys.exit(3)"],
            timeout=5)
        try:
            with self.assertRaises(MCPError):
                client.initialize()
            tail = client._stderr_tail()
        finally:
            try:
                client.close()
            except Exception:
                pass
        self.assertIn("boom-404", tail, "a dead server's stderr tail was lost")


if __name__ == "__main__":
    unittest.main()
