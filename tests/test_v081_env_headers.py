"""Issue #24 — environment-sourced HTTP headers, end to end.

The feature's whole value is that a credential never has to be written down, so
these tests assert the property that matters at each layer, not just the happy
path:

* ``headers.resolve_value`` expands ``${NAME}``, leaves literals alone, escapes
  ``$${NAME}``, and raises naming the variable when it is unset or empty.
* The **generated handler** and the **config record** carry the ``${NAME}``
  template, never a resolved secret — that is what makes the feature safe to
  install into a shared machine.
* A **real HTTP MCP server** reached through the real ``MCPClient`` sees the
  expanded header, so install-time verification and call-time resolution cannot
  drift apart.
* The install path reports a missing variable as a structured error naming it,
  not a traceback.

Deliberately no network: the server is a stdlib ``http.server`` on loopback, the
same shape as ``test_v073_http_security``.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import headers as headers_mod  # noqa: E402
from mcptoon.client import MCPClient, MCPError  # noqa: E402
from mcptoon.errors import error_code  # noqa: E402
from mcptoon import installer  # noqa: E402


class TestResolveValue(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("MCPTOON_T24",)}
        os.environ["MCPTOON_T24"] = "sekret-token"
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_expands_a_named_variable(self):
        self.assertEqual(
            headers_mod.resolve_value("Bearer ${MCPTOON_T24}"),
            "Bearer sekret-token")

    def test_a_value_without_a_marker_is_untouched(self):
        self.assertEqual(headers_mod.resolve_value("application/json"),
                         "application/json")
        self.assertFalse(headers_mod.needs_resolution("plain"))
        self.assertTrue(headers_mod.needs_resolution("Bearer ${X}"))

    def test_escaped_marker_yields_a_literal(self):
        self.assertEqual(headers_mod.resolve_value("$${MCPTOON_T24}"),
                         "${MCPTOON_T24}")

    def test_a_bare_dollar_is_ordinary_text(self):
        self.assertEqual(headers_mod.resolve_value("$5 and $HOME"),
                         "$5 and $HOME")

    def test_unset_variable_raises_naming_it(self):
        with self.assertRaises(headers_mod.HeaderEnvError) as ctx:
            headers_mod.resolve_value("Bearer ${MCPTOON_NOPE}")
        self.assertEqual(ctx.exception.name, "MCPTOON_NOPE")
        self.assertIn("MCPTOON_NOPE", str(ctx.exception))

    def test_empty_variable_is_treated_as_missing(self):
        os.environ["MCPTOON_EMPTY"] = ""
        self.addCleanup(os.environ.pop, "MCPTOON_EMPTY", None)
        with self.assertRaises(headers_mod.HeaderEnvError):
            headers_mod.resolve_value("${MCPTOON_EMPTY}")

    def test_resolve_headers_does_not_mutate_the_source(self):
        src = {"Authorization": "Bearer ${MCPTOON_T24}", "X-Static": "1"}
        out = headers_mod.resolve_headers(src)
        self.assertEqual(out["Authorization"], "Bearer sekret-token")
        # The template survives: nothing downstream can write the secret back.
        self.assertEqual(src["Authorization"], "Bearer ${MCPTOON_T24}")


class _EchoHeaderHandler(BaseHTTPRequestHandler):
    """A minimal MCP server that requires one Authorization value."""

    required = "Bearer sekret-token"
    seen = []

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except ValueError:
            req = {}
        auth = self.headers.get("Authorization", "")
        type(self).seen.append(auth)
        if auth != self.required:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"error": {"code": -32001, "message": "unauthorized"}}).encode())
            return

        method, rid = req.get("method"), req.get("id")
        if method == "server/discover":
            result = {"protocolVersion": "2026-07-28",
                      "serverInfo": {"name": "auth-echo", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "ping", "description": "Ping.",
                                 "inputSchema": {"type": "object", "properties": {}}}]}
        else:
            result = {}
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestRealServerSeesTheHeader(unittest.TestCase):
    """The chain that matters: config template → real HTTP request."""

    def setUp(self):
        _EchoHeaderHandler.seen = []
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHeaderHandler)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._srv.server_address[1]}/mcp"
        self.addCleanup(self._srv.shutdown)

    def test_a_template_header_reaches_the_server_expanded(self):
        os.environ["MCPTOON_T24"] = "sekret-token"
        self.addCleanup(os.environ.pop, "MCPTOON_T24", None)
        client = MCPClient(http=self.url,
                           headers={"Authorization": "Bearer ${MCPTOON_T24}"})
        try:
            client.initialize()
        finally:
            client.close()
        self.assertIn("Bearer sekret-token", _EchoHeaderHandler.seen)

    def test_a_missing_variable_fails_loudly_instead_of_sending_empty(self):
        os.environ.pop("MCPTOON_T24", None)
        client = MCPClient(http=self.url,
                           headers={"Authorization": "Bearer ${MCPTOON_T24}"})
        try:
            with self.assertRaises(MCPError) as ctx:
                client.initialize()
        finally:
            client.close()
        self.assertEqual(ctx.exception.code, "HEADER_ENV_MISSING")
        self.assertIn("MCPTOON_T24", str(ctx.exception))
        # The server must never have been reached with an empty credential.
        self.assertNotIn("", _EchoHeaderHandler.seen)

    def test_a_literal_header_still_works_unchanged(self):
        client = MCPClient(http=self.url,
                           headers={"Authorization": "Bearer sekret-token"})
        try:
            client.initialize()
        finally:
            client.close()
        self.assertIn("Bearer sekret-token", _EchoHeaderHandler.seen)


class TestInstallWritesTemplatesNotSecrets(unittest.TestCase):
    """The install path must persist the template and nothing else."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._installed = Path(self._tmp.name) / "installed.json"
        self._handlers = Path(self._tmp.name) / "handlers"
        self._handlers.mkdir()
        self._p1 = patch.object(installer, "_INSTALLED_FILE", self._installed)
        self._p2 = patch.object(installer, "_handlers_dir", lambda: str(self._handlers))
        self._p1.start()
        self._p2.start()
        self.addCleanup(self._p1.stop)
        self.addCleanup(self._p2.stop)

    def _install(self, headers):
        class _FakeClient:
            def __init__(self, **kw):
                self.kw = kw

            def initialize(self):
                return {"serverInfo": {"name": "x"}}

            def list_tools(self):
                return [{"name": "ping", "description": "p",
                         "inputSchema": {"type": "object", "properties": {}}}]

            def close(self):
                pass

        with patch.object(installer, "MCPClient", _FakeClient):
            return installer.install_http("https://example.com/mcp", "svc",
                                          headers=headers)

    def test_the_config_keeps_the_template_and_never_the_secret(self):
        os.environ["MCPTOON_T24"] = "sekret-token"
        self.addCleanup(os.environ.pop, "MCPTOON_T24", None)
        result = self._install({"Authorization": "Bearer ${MCPTOON_T24}"})
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["header_names"], ["Authorization"])
        raw = self._installed.read_text(encoding="utf-8")
        self.assertIn("${MCPTOON_T24}", raw)
        self.assertNotIn("sekret-token", raw)

    def test_the_generated_handler_carries_the_template(self):
        os.environ["MCPTOON_T24"] = "sekret-token"
        self.addCleanup(os.environ.pop, "MCPTOON_T24", None)
        self._install({"Authorization": "Bearer ${MCPTOON_T24}"})
        handler = (self._handlers / "svc.py").read_text(encoding="utf-8")
        self.assertIn("MCP_HEADERS", handler)
        self.assertIn("${MCPTOON_T24}", handler)
        self.assertNotIn("sekret-token", handler)
        # The handler must actually pass the mapping to the client.
        self.assertIn("headers=MCP_HEADERS", handler)

    def test_a_missing_variable_installs_as_a_named_error_not_a_traceback(self):
        os.environ.pop("MCPTOON_T24", None)

        def _boom(*a, **k):
            raise MCPError("HEADER_ENV_MISSING",
                           "header needs environment variable ${MCPTOON_T24} "
                           "but it is unset or empty")

        class _FakeClient:
            def __init__(self, **kw):
                pass

            def initialize(self):
                _boom()

            def close(self):
                pass

        with patch.object(installer, "MCPClient", _FakeClient):
            result = installer.install_http("https://example.com/mcp", "svc",
                                            headers={"Authorization":
                                                     "Bearer ${MCPTOON_T24}"})
        self.assertEqual(error_code(result), "VERIFY_FAILED")
        self.assertIn("MCPTOON_T24", result["_error"]["message"])


if __name__ == "__main__":
    unittest.main()
