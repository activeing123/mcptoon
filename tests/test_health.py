# Tests for mcptoon health — batch health check
from unittest.mock import patch, MagicMock


from mcptoon.health import check_server, check_all, format_health_report


# ─── check_server tests ───

class TestCheckServer:
    def test_no_config(self):
        """Server not in config returns no-config status."""
        with patch("mcptoon.health.load_config", return_value={"servers": {}}):
            with patch("mcptoon.health.get_server_config", return_value=None):
                result = check_server("nonexistent")
                assert result["status"] == "no-config"
                assert result["server"] == "nonexistent"

    def test_stdio_ok(self):
        """stdio server with working connection returns ok."""
        mock_config = {"servers": {"fetch": {"transport": "stdio", "command": ["echo"], "args": []}}}
        mock_server_cfg = {"transport": "stdio", "command": ["echo"], "args": []}

        mock_client = MagicMock()
        mock_client.list_tools.return_value = [{"name": "fetch"}]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("mcptoon.health.load_config", return_value=mock_config):
            with patch("mcptoon.health.get_server_config", return_value=mock_server_cfg):
                with patch("mcptoon.health.MCPClient", return_value=mock_client):
                    result = check_server("fetch")
                    assert result["status"] == "ok"
                    assert result["tools"] == 1
                    assert result["latency_ms"] >= 0

    def test_http_ok(self):
        """HTTP server with working connection returns ok."""
        mock_config = {"servers": {"remote": {"transport": "http", "url": "http://localhost:8080/mcp"}}}
        mock_server_cfg = {"transport": "http", "url": "http://localhost:8080/mcp", "headers": {}}

        mock_client = MagicMock()
        mock_client.list_tools.return_value = [{"name": "tool1"}, {"name": "tool2"}]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("mcptoon.health.load_config", return_value=mock_config):
            with patch("mcptoon.health.get_server_config", return_value=mock_server_cfg):
                with patch("mcptoon.health.MCPClient", return_value=mock_client):
                    result = check_server("remote")
                    assert result["status"] == "ok"
                    assert result["tools"] == 2

    def test_timeout(self):
        """Server that times out returns timeout status."""
        mock_config = {"servers": {"slow": {"transport": "stdio", "command": ["sleep"], "args": ["100"]}}}
        mock_server_cfg = {"transport": "stdio", "command": ["sleep"], "args": ["100"]}

        with patch("mcptoon.health.load_config", return_value=mock_config):
            with patch("mcptoon.health.get_server_config", return_value=mock_server_cfg):
                with patch("mcptoon.health.MCPClient", side_effect=TimeoutError()):
                    result = check_server("slow", timeout=1.0)
                    assert result["status"] == "timeout"

    def test_error(self):
        """Server with connection error returns error status."""
        mock_config = {"servers": {"broken": {"transport": "stdio", "command": ["nonexistent-cmd"], "args": []}}}
        mock_server_cfg = {"transport": "stdio", "command": ["nonexistent-cmd"], "args": []}

        with patch("mcptoon.health.load_config", return_value=mock_config):
            with patch("mcptoon.health.get_server_config", return_value=mock_server_cfg):
                with patch("mcptoon.health.MCPClient", side_effect=Exception("Connection refused")):
                    result = check_server("broken")
                    assert result["status"] == "error"
                    assert "Connection refused" in result["error"]


# ─── check_all tests ───

class TestCheckAll:
    def test_no_servers(self):
        """No servers configured returns empty list."""
        with patch("mcptoon.health.load_config", return_value={"servers": {}}):
            with patch("mcptoon.health.list_servers", return_value=[]):
                results = check_all()
                assert results == []

    def test_multiple_servers(self):
        """Multiple servers checked in parallel."""
        servers = ["server1", "server2", "server3"]
        with patch("mcptoon.health.list_servers", return_value=servers):
            with patch("mcptoon.health.check_server", side_effect=[
                {"server": "server1", "transport": "stdio", "status": "ok", "tools": 3, "latency_ms": 100, "error": None},
                {"server": "server2", "transport": "stdio", "status": "error", "tools": 0, "latency_ms": 50, "error": "refused"},
                {"server": "server3", "transport": "http", "status": "ok", "tools": 5, "latency_ms": 200, "error": None},
            ]):
                results = check_all()
                assert len(results) == 3
                # Errors should be sorted first
                assert results[0]["status"] == "error"


# ─── format_health_report tests ───

class TestFormatReport:
    def test_empty_results(self):
        """Empty results produces helpful message."""
        report = format_health_report([])
        assert "No servers configured" in report

    def test_all_ok(self):
        """All healthy report shows ok."""
        results = [
            {"server": "fetch", "transport": "stdio", "status": "ok", "tools": 3, "latency_ms": 100, "error": None},
            {"server": "github", "transport": "http", "status": "ok", "tools": 12, "latency_ms": 340, "error": None},
        ]
        report = format_health_report(results)
        assert "2/2 alive" in report
        assert "All 2 servers healthy" in report
        assert "✓" in report

    def test_mixed_status(self):
        """Mixed ok/error report shows both."""
        results = [
            {"server": "fetch", "transport": "stdio", "status": "ok", "tools": 3, "latency_ms": 100, "error": None},
            {"server": "broken", "transport": "stdio", "status": "error", "tools": 0, "latency_ms": 50, "error": "Connection refused"},
            {"server": "slow", "transport": "stdio", "status": "timeout", "tools": 0, "latency_ms": 10000, "error": "Timed out after 10s"},
        ]
        report = format_health_report(results)
        assert "1/3 alive" in report
        assert "2/3 servers unreachable" in report
        assert "✗" in report
        assert "⏱" in report

    def test_latency_displayed(self):
        """Latency is shown in report."""
        results = [
            {"server": "fast", "transport": "stdio", "status": "ok", "tools": 1, "latency_ms": 42, "error": None},
        ]
        report = format_health_report(results)
        assert "42" in report
