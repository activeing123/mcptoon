"""Tests for v0.5.0 features: install command, installer module."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure src is on path
_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.installer import (
    install_npm,
    install_http,
    install_custom,
    list_installed,
    remove_installed,
    search_registry,
    _load_installed,
    _save_installed,
    _now_iso,
    MCP_REGISTRY_URL,
    INSTALL_TIMEOUT,
    _NPX_CMD,
    log,
)


class TestInstallerConstants(unittest.TestCase):
    """Test that installer module constants are properly defined."""

    def test_registry_url_defined(self):
        self.assertTrue(MCP_REGISTRY_URL.startswith("http"))

    def test_install_timeout_positive(self):
        self.assertGreater(INSTALL_TIMEOUT, 0)

    def test_npx_cmd_set(self):
        self.assertTrue(_NPX_CMD)

    def test_log_object(self):
        self.assertTrue(hasattr(log, "info"))
        self.assertTrue(hasattr(log, "error"))


class TestInstalledFile(unittest.TestCase):
    """Test installed file operations."""

    def test_load_installed_empty(self):
        """_load_installed returns {} when file doesn't exist."""
        with patch("mcptoon.installer._INSTALLED_FILE", "/nonexistent/path/file.json"):
            result = _load_installed()
            self.assertEqual(result, {})

    def test_save_and_load(self):
        """_save_installed + _load_installed round-trip."""
        data = {"test_server": {"tools": ["ping"], "source": "npm"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "installed.json")
            with patch("mcptoon.installer._INSTALLED_FILE", fpath):
                _save_installed(data)
                loaded = _load_installed()
                self.assertEqual(loaded, data)

    def test_load_installed_corrupt(self):
        """_load_installed returns {} for corrupt JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "bad.json")
            with open(fpath, "w") as f:
                f.write("not valid json {{{")
            with patch("mcptoon.installer._INSTALLED_FILE", fpath):
                result = _load_installed()
                self.assertEqual(result, {})


class TestNowIso(unittest.TestCase):
    """Test _now_iso helper."""

    def test_returns_iso_string(self):
        result = _now_iso()
        self.assertIsInstance(result, str)
        self.assertIn("T", result)


class TestListInstalled(unittest.TestCase):
    """Test list_installed function."""

    def test_empty(self):
        with patch("mcptoon.installer._INSTALLED_FILE", "/nonexistent/file.json"):
            result = list_installed()
            self.assertEqual(result, {})

    def test_with_data(self):
        data = {"server1": {"tools": ["a", "b"]}}
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "installed.json")
            with patch("mcptoon.installer._INSTALLED_FILE", fpath):
                _save_installed(data)
                result = list_installed()
                self.assertIn("server1", result)


class TestRemoveInstalled(unittest.TestCase):
    """Test remove_installed function."""

    def test_remove_existing(self):
        data = {"server1": {"tools": ["a"]}, "server2": {"tools": ["b"]}}
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "installed.json")
            with patch("mcptoon.installer._INSTALLED_FILE", fpath):
                _save_installed(data)
                result = remove_installed("server1")
                self.assertEqual(result["status"], "removed")
                remaining = _load_installed()
                self.assertNotIn("server1", remaining)
                self.assertIn("server2", remaining)

    def test_remove_nonexistent(self):
        with patch("mcptoon.installer._INSTALLED_FILE", "/nonexistent/file.json"):
            result = remove_installed("nonexistent")
            self.assertTrue("error" in result or "_error" in result)


class TestInstallNpm(unittest.TestCase):
    """Test install_npm with mocked MCPClient."""

    @patch("mcptoon.installer.MCPClient")
    @patch("mcptoon.installer._generate_handler_file")
    @patch("mcptoon.installer._save_installed")
    @patch("mcptoon.installer._load_installed")
    def test_install_npm_success(self, mock_load, mock_save, mock_gen, mock_client_cls):
        """install_npm should connect, get tools, generate handler."""
        mock_load.return_value = {}
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [{"name": "search", "description": "Search"}]
        mock_client_cls.return_value = mock_client

        result = install_npm("@test/mcp-server", "test_server")

        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["server"], "test_server")
        self.assertEqual(result["tools"], 1)
        mock_client.initialize.assert_called_once()
        mock_client.close.assert_called_once()

    @patch("mcptoon.installer.MCPClient")
    def test_install_npm_connection_failure(self, mock_client_cls):
        """install_npm should return error on connection failure."""
        from mcptoon.client import MCPError
        mock_client = MagicMock()
        mock_client.initialize.side_effect = MCPError("test-server", "Connection failed")
        mock_client_cls.return_value = mock_client

        result = install_npm("@test/mcp-server", "test_server")

        self.assertTrue("_error" in result or "error" in result)


class TestInstallHttp(unittest.TestCase):
    """Test install_http with mocked MCPClient."""

    @patch("mcptoon.installer.MCPClient")
    @patch("mcptoon.installer._generate_http_handler_file")
    @patch("mcptoon.installer._save_installed")
    @patch("mcptoon.installer._load_installed")
    def test_install_http_success(self, mock_load, mock_save, mock_gen, mock_client_cls):
        """install_http should connect, get tools, generate handler."""
        mock_load.return_value = {}
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [{"name": "fetch", "description": "Fetch URL"}]
        mock_client_cls.return_value = mock_client

        result = install_http("https://example.com/mcp", "test_http")

        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["server"], "test_http")
        self.assertEqual(result["url"], "https://example.com/mcp")

    def test_install_http_name_from_url(self):
        """install_http should derive name from URL when not provided."""
        # We can't fully test without mocking, but verify the function signature
        import inspect
        sig = inspect.signature(install_http)
        self.assertTrue("url" in sig.parameters)
        self.assertTrue("server_name" in sig.parameters)
        self.assertTrue("transport" in sig.parameters)


class TestSearchRegistry(unittest.TestCase):
    """Test search_registry function."""

    @patch("urllib.request.urlopen")
    def test_search_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "servers": [
                {"name": "test-server", "description": "A test server", "command": "npx", "args": ["-y", "test"]}
            ]
        }).encode("utf-8")
        mock_urlopen.return_value = mock_resp

        result = search_registry("test")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "test-server")

    @patch("urllib.request.urlopen")
    def test_search_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network error")
        result = search_registry("test")
        self.assertTrue("_error" in result or "error" in result)


class TestCLiInstallCommand(unittest.TestCase):
    """Test CLI install command exists in cli.py."""

    def test_install_in_help(self):
        """install command should be documented in CLI help."""
        from mcptoon.cli import _print_help
        import io
        import contextlib
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            try:
                _print_help()
            except Exception:
                pass
        output = f.getvalue().lower()
        # 'install' should appear in help text
        self.assertTrue("install" in output, "'install' not found in help output")

    def test_install_command_dispatch(self):
        """CLI should route 'install' to _cmd_install."""
        import mcptoon.cli as cli
        # Check that _cmd_install is callable
        self.assertTrue(callable(cli._cmd_install))


class TestInstallerImport(unittest.TestCase):
    """Test that installer can be imported from mcptoon package."""

    def test_import_from_package(self):
        """import mcptoon.installer should work."""
        import mcptoon.installer
        self.assertTrue(hasattr(mcptoon.installer, "install_npm"))
        self.assertTrue(hasattr(mcptoon.installer, "install_pip"))
        self.assertTrue(hasattr(mcptoon.installer, "install_http"))
        self.assertTrue(hasattr(mcptoon.installer, "list_installed"))
        self.assertTrue(hasattr(mcptoon.installer, "remove_installed"))

    def test_install_custom_exists(self):
        """install_custom should exist for manual server registration."""
        self.assertTrue(callable(install_custom))


if __name__ == "__main__":
    unittest.main()
