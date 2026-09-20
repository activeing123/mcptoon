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

"""HTTP transport User-Agent behavior.

Why this exists: urllib announces ``Python-urllib/3.x`` when no User-Agent is
set, and bot filters in front of public hosted MCP endpoints (Cloudflare
error 1010) reject that signature with HTTP 403 before the server is ever
reached. The transport therefore must announce itself by default, and a
caller-supplied User-Agent must still win.

All tests mock the opener — no network.
"""
import threading
import unittest
from unittest.mock import patch

from mcptoon.client import DEFAULT_USER_AGENT, MCPClient


def _build_client(headers=None):
    """HTTP-mode client with subprocess wiring bypassed."""
    c = object.__new__(MCPClient)
    c._transport = "http"
    c._stdio_cmd = None
    c._http_url = "https://example.test/mcp"
    c._headers = headers or {}
    c._env = None
    c._timeout = 5
    c._cwd = None
    c._proc = None
    c._stdout_lock = threading.Lock()
    c._session_id = None
    c._spec = "auto"
    c._mode = None
    c._negotiated = None
    c._in_probe = False
    c._fell_back = False
    c.server_info = None
    c.server_capabilities = None
    c._initialized = False
    c._tools_cache = []
    return c


class _FakeResponse:
    """Minimal response object for the transport's read/headers surface."""

    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        return self._body

    headers = {"Content-Type": "application/json"}


class _CaptureOpener:
    """Stands in for urllib's opener; records the Request it was given."""

    def __init__(self, resp=None):
        self.requests = []
        self._resp = resp or _FakeResponse(
            b'{"jsonrpc":"2.0","id":1,"result":{}}'
        )

    def open(self, req, timeout=None):
        self.requests.append(req)
        return self._resp


def _header(req, name):
    """Fetch a header case-insensitively — Request keys are capitalize()d."""
    value = {k.lower(): v for k, v in req.headers.items()}.get(name.lower())
    assert value is not None, f"header {name!r} missing from request"
    return value


class TestDefaultUserAgent(unittest.TestCase):
    def test_constant_is_mcptoon_slash_version(self):
        self.assertTrue(DEFAULT_USER_AGENT.startswith("mcptoon/"))
        self.assertNotEqual(DEFAULT_USER_AGENT, "mcptoon/dev")

    def test_http_request_sends_default_user_agent(self):
        client = _build_client()
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        req = opener.requests[0]
        self.assertEqual(_header(req, "user-agent"), DEFAULT_USER_AGENT)

    def test_default_ua_is_not_python_urllib(self):
        client = _build_client()
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        ua = _header(opener.requests[0], "user-agent")
        self.assertFalse(ua.lower().startswith("python-urllib"),
                         f"transport still announces {ua!r}")

    def test_http_notify_sends_default_user_agent(self):
        client = _build_client()
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_notify(b'{"jsonrpc":"2.0","method":"notifications/init"}')
        self.assertEqual(_header(opener.requests[0], "user-agent"),
                         DEFAULT_USER_AGENT)


class TestCallerSuppliedUserAgentWins(unittest.TestCase):
    def test_exact_case_override(self):
        client = _build_client(headers={"User-Agent": "my-agent/1.0"})
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        self.assertEqual(_header(opener.requests[0], "user-agent"), "my-agent/1.0")

    def test_lowercase_override(self):
        client = _build_client(headers={"user-agent": "my-agent/2.0"})
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        self.assertEqual(_header(opener.requests[0], "user-agent"), "my-agent/2.0")

    def test_extra_headers_do_not_shadow_default_ua(self):
        client = _build_client()
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}',
                                 extra_headers={"Mcp-Method": "tools/call"})
        req = opener.requests[0]
        self.assertEqual(_header(req, "user-agent"), DEFAULT_USER_AGENT)
        self.assertEqual(_header(req, "mcp-method"), "tools/call")


class TestOtherHeadersUnaffected(unittest.TestCase):
    def test_content_type_and_accept_still_sent(self):
        client = _build_client()
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        req = opener.requests[0]
        self.assertEqual(_header(req, "content-type"), "application/json")
        self.assertEqual(_header(req, "accept"),
                         "application/json, text/event-stream")

    def test_caller_headers_still_sent_alongside_default_ua(self):
        client = _build_client(headers={"Authorization": "Bearer t"})
        opener = _CaptureOpener()
        with patch("urllib.request.build_opener", return_value=opener):
            client._http_request(b'{"jsonrpc":"2.0","id":1}')
        req = opener.requests[0]
        self.assertEqual(_header(req, "authorization"), "Bearer t")
        self.assertEqual(_header(req, "user-agent"), DEFAULT_USER_AGENT)


if __name__ == "__main__":
    unittest.main()
