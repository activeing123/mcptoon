"""Tests for mcptoon discover — auto-discovery module."""
import json
import os
from pathlib import Path
from unittest.mock import patch


from mcptoon.discover import (
    DiscoveryResult,
    auto_discover,
    _scan_claude_desktop,
    _scan_cursor,
    _detect_from_env,
    _detect_local_tools,
    _probe_http_mcp,
    _probe_endpoint,
    _normalize_imported_config,
    _which,
    probe_http_endpoint,
    make_http_config,
)
from mcptoon import discover as discover_mod


# ═══════════════════════════════════════════════════════════════
# DiscoveryResult tests
# ═══════════════════════════════════════════════════════════════

class TestDiscoveryResult:
    def test_empty_result(self):
        r = DiscoveryResult()
        assert r.count == 0
        assert "Discovered 0" in r.summary()

    def test_with_servers(self):
        r = DiscoveryResult()
        r.servers = {"github": {"transport": "stdio"}}
        r.sources = {"github": ["env"]}
        r.reasons = {"github": "Found GITHUB_TOKEN"}
        assert r.count == 1
        assert "github" in r.summary()

    def test_skipped_in_summary(self):
        r = DiscoveryResult()
        r.skipped = ["slack"]
        assert "Skipped" in r.summary()
        assert "slack" in r.summary()


# ═══════════════════════════════════════════════════════════════
# Config normalization tests
# ═══════════════════════════════════════════════════════════════

class TestNormalizeConfig:
    def test_stdio_string_command(self):
        """Claude Desktop format: command is a string."""
        cfg = {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-fetch"]}
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "stdio"
        assert "npx" in result["command"]

    def test_stdio_list_command(self):
        """mcptoon format: command is a list."""
        cfg = {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-fetch"],
        }
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "stdio"

    def test_http_config(self):
        cfg = {"transport": "http", "url": "http://localhost:8080/mcp"}
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert result["transport"] == "http"
        assert result["url"] == "http://localhost:8080/mcp"

    def test_empty_config(self):
        assert _normalize_imported_config({}) is None

    def test_none_config(self):
        assert _normalize_imported_config(None) is None

    def test_with_env(self):
        cfg = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"},
        }
        result = _normalize_imported_config(cfg)
        assert result is not None
        assert "env" in result
        assert "GITHUB_PERSONAL_ACCESS_TOKEN" in result["env"]


# ═══════════════════════════════════════════════════════════════
# Environment variable detection tests
# ═══════════════════════════════════════════════════════════════

class TestEnvDetection:
    def test_github_token(self):
        with patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "github" in names

    def test_brave_api_key(self):
        with patch.dict(os.environ, {"BRAVE_API_KEY": "BSA_test123"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "brave-search" in names

    def test_no_env_vars(self):
        # Clear all known env vars
        env_vars_to_clear = [
            "GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN",
            "BRAVE_API_KEY", "EXA_API_KEY", "TAVILY_API_KEY",
            "FIRECRAWL_API_KEY", "SLACK_BOT_TOKEN", "SLACK_TOKEN",
            "NOTION_API_KEY", "NOTION_TOKEN", "DATABASE_URL",
        ]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_clear}
        with patch.dict(os.environ, clean_env, clear=True):
            results = _detect_from_env()
            assert len(results) == 0

    def test_placeholder_ignored(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "<your-token>"}):
            results = _detect_from_env()
            names = [r["name"] for r in results]
            assert "github" not in names

    def test_env_config_has_env_key(self):
        with patch.dict(os.environ, {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_test123"}):
            results = _detect_from_env()
            github = [r for r in results if r["name"] == "github"][0]
            assert "env" in github["config"]
            assert "GITHUB_PERSONAL_ACCESS_TOKEN" in github["config"]["env"]


# ═══════════════════════════════════════════════════════════════
# Local tool detection tests
# ═══════════════════════════════════════════════════════════════

class TestLocalDetection:
    def test_npx_available(self):
        # npx is likely available in test env
        results = _detect_local_tools()
        # If npx is available, the npm-published zero-config servers appear.
        # `fetch`/`time`/`git` are PyPI packages and must NOT be offered via
        # npx (they 404) — they come from uvx, gated on uvx being present.
        if _which("npx"):
            names = [r["name"] for r in results]
            assert "filesystem" in names
            assert "memory" in names
            assert "sequential-thinking" in names

    def test_git_is_offered_once_and_only_when_the_git_binary_exists(self):
        """`git` is one entry in the uvx table, gated on the git binary itself.

        Two regressions are pinned here, both found 2026-10-02 on a clean Windows
        box where `quickstart` printed the git server **twice** and then showed it
        dead (`[PROCESS_DIED] … All git commands will error until this is
        rectified`) while still counting it as a working server:

        1. `git` was added *twice* — once from the uvx table and once from a
           leftover "we are in a git repository" special case that `a106dc5`
           (2026-09-18) forgot to delete when it moved git off npx. The duplicate
           stayed invisible because the old assertion filtered on the phrase
           "git repository", which only matched the leftover copy.
        2. `git` was offered whenever `uvx` existed, even with no git binary —
           `mcp-server-git` starts, but every tool errors, and the celebration
           still counted the server as ready.

        Assert on the *count* of git entries (not on a phrase in the reason), so a
        second copy can never hide behind a filter again.
        """
        with patch.object(discover_mod, "_which",
                          side_effect=lambda c: "uvx" if c == "uvx" else None):
            names = [r["name"] for r in _detect_local_tools()]
        assert "git" not in names, (
            "git must not be offered when the git binary is absent — uvx cannot "
            "stand in for it, and every mcp-server-git tool errors without it"
        )

        with patch.object(discover_mod, "_which",
                          side_effect=lambda c: c if c in ("uvx", "git") else None):
            results = _detect_local_tools()
        git_entries = [r for r in results if r["name"] == "git"]
        assert len(git_entries) == 1, (
            f"git must appear exactly once, got {len(git_entries)}: "
            f"{[r['reason'] for r in git_entries]}"
        )
        # The *runner* is what matters here, not the literal string: when the
        # package is installed locally the entry is `python -m mcp_server_git`
        # (see `_resolve_local_module`), and either is a working launcher.
        cmd = git_entries[0]["config"]["command"]
        assert cmd == ["uvx"] or (cmd and "python" in cmd[0].lower()), (
            f"git must launch via uvx or a local python, got {cmd!r}"
        )


# ═══════════════════════════════════════════════════════════════
# Dead-package regression guard (found 2026-09-18)
# ═══════════════════════════════════════════════════════════════

# Packages that are gone from the npm registry (E404, verified 2026-09-18).
# `mcptoon quickstart` used to recommend all of these via `npx -y`, so a fresh
# machine saw five dead servers and a wall of `npm error 404`.
_DEAD_NPM_PACKAGES = (
    "@modelcontextprotocol/server-fetch",
    "@modelcontextprotocol/server-time",
    "@modelcontextprotocol/server-git",
    "@modelcontextprotocol/server-docker",
    "@modelcontextprotocol/server-sqlite",
)


class TestNoDeadPackagesOffered:
    """Discovery must never hand `npx` a package that is not on npm."""

    def test_candidate_lists_are_clean(self):
        blob = repr(discover_mod._NPX_ZERO_CONFIG_SERVERS)
        for pkg in _DEAD_NPM_PACKAGES:
            assert pkg not in blob, f"dead npm package offered: {pkg}"

    def test_pypi_servers_use_uvx_not_npx(self):
        # fetch/time/git live on PyPI; they must be launched with uvx.
        for name, command, _args, _reason, _requires, _mod in discover_mod._UVX_ZERO_CONFIG_SERVERS:
            assert command == ["uvx"], f"{name} should run via uvx, got {command}"

    def test_live_packages_still_offered(self):
        names = [n for n, _c, _a, _r in discover_mod._NPX_ZERO_CONFIG_SERVERS]
        for expected in ("filesystem", "memory", "sequential-thinking"):
            assert expected in names

    def test_npx_gated_on_npx_and_uvx_on_uvx(self):
        # npx present, uvx absent -> only the npm servers, no fetch/time.
        with patch.object(discover_mod, "_which",
                          lambda cmd: "npx" if cmd == "npx" else None):
            names = [r["name"] for r in _detect_local_tools()]
        assert "filesystem" in names
        assert "fetch" not in names
        assert "time" not in names
        # uvx present, npx absent -> only the PyPI servers.
        with patch.object(discover_mod, "_which",
                          lambda cmd: "uvx" if cmd == "uvx" else None):
            names = [r["name"] for r in _detect_local_tools()]
        assert "fetch" in names
        assert "time" in names
        assert "filesystem" not in names


# ═══════════════════════════════════════════════════════════════
# Config scanning tests
# ═══════════════════════════════════════════════════════════════

class TestConfigScanning:
    def test_scan_claude_desktop_mock(self):
        """Test scanning Claude Desktop config with a mock file."""
        mock_config = {
            "mcpServers": {
                "fetch": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-fetch"],
                },
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"},
                },
            }
        }

        with patch("mcptoon.discover._home") as mock_home:
            mock_home.return_value = Path("/fake/home")
            with patch("mcptoon.discover.sys.platform", "darwin"):
                config_path = Path("/fake/home/Library/Application Support/Claude/claude_desktop_config.json")
                with patch.object(Path, "exists", lambda self: str(self) == str(config_path)):
                    with patch.object(Path, "read_text", lambda self, encoding=None: json.dumps(mock_config)):
                        results = _scan_claude_desktop()
                        assert len(results) == 2
                        names = [r["name"] for r in results]
                        assert "fetch" in names
                        assert "github" in names

    def test_scan_cursor_mock(self):
        mock_config = {
            "mcpServers": {
                "exa": {
                    "command": "npx",
                    "args": ["-y", "exa-mcp-server"],
                },
            }
        }

        with patch.object(Path, "exists", lambda self: ".cursor" in str(self) and "mcp.json" in str(self)):
            with patch.object(Path, "read_text", lambda self, encoding=None: json.dumps(mock_config)):
                results = _scan_cursor()
                assert len(results) >= 1
                assert results[0]["name"] == "exa"


# ═══════════════════════════════════════════════════════════════
# Network probe tests
# ═══════════════════════════════════════════════════════════════

class TestNetworkProbe:
    def test_probe_dead_endpoint(self):
        """Probing a port that's definitely not running should return False."""
        result = _probe_endpoint("http://127.0.0.1:59999/mcp", timeout=0.1)
        assert result is False

    def test_probe_http_endpoint_dead(self):
        """probe_http_endpoint on dead URL returns None."""
        result = probe_http_endpoint("http://127.0.0.1:59999/mcp", timeout=0.1)
        assert result is None

    def test_make_http_config_normalizes_url(self):
        cfg = make_http_config("localhost:8080")
        assert cfg["transport"] == "http"
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_make_http_config_already_has_http(self):
        cfg = make_http_config("http://localhost:8080/mcp")
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_make_http_config_with_trailing_slash(self):
        cfg = make_http_config("http://localhost:8080/")
        assert cfg["url"] == "http://localhost:8080/mcp"

    def test_http_probe_no_network(self):
        """With no MCP_HTTP_URL env var set, _probe_http_mcp should return empty list."""
        # Clear all HTTP MCP env vars
        env_vars_to_clear = ["MCP_HTTP_URL", "MCP_SERVER_URL"]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_clear}
        with patch.dict(os.environ, clean_env, clear=True):
            results = _probe_http_mcp()
            assert isinstance(results, list)
            assert len(results) == 0  # No env vars set → no results

    def test_http_probe_with_env_var(self):
        """When MCP_HTTP_URL is set, _probe_http_mcp should try to probe it."""
        # Use a dead port — should get empty results (probe fails)
        with patch.dict(os.environ, {"MCP_HTTP_URL": "http://127.0.0.1:59999/mcp"}):
            results = _probe_http_mcp()
            assert isinstance(results, list)
            assert len(results) == 0  # Probe failed → not included


# ═══════════════════════════════════════════════════════════════
# auto_discover integration tests
# ═══════════════════════════════════════════════════════════════

class TestAutoDiscover:
    def test_auto_discover_returns_result(self):
        """auto_discover should return a DiscoveryResult."""
        result = auto_discover(probe_network=False)
        assert isinstance(result, DiscoveryResult)
        assert isinstance(result.servers, dict)
        assert isinstance(result.sources, dict)

    def test_auto_discover_no_network(self):
        """With network probing disabled, local/env servers still show up.

        The set depends on which runners are installed, so assert the contract
        rather than a hardcoded name: npm servers iff npx exists, PyPI servers
        iff uvx exists. (This test previously hardcoded `fetch`, which is a
        PyPI package — it passed locally only because this machine has uvx.)
        """
        result = auto_discover(probe_network=False)
        if _which("npx"):
            assert "filesystem" in result.servers
        if _which("uvx"):
            assert "fetch" in result.servers

    def test_auto_discover_dedup(self):
        """Same server from multiple sources should be deduplicated."""
        result = auto_discover(probe_network=False)
        # Check no duplicate names
        for name, sources in result.sources.items():
            # A server can have multiple sources but only one config entry
            assert name in result.servers

    def test_auto_discover_selective(self):
        """Test disabling specific layers."""
        result = auto_discover(
            scan_configs=False,
            detect_env=False,
            detect_local=False,
            probe_network=False,
        )
        assert result.count == 0

    def test_auto_discover_env_only(self):
        """Test with only env detection."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}):
            result = auto_discover(
                scan_configs=False,
                detect_env=True,
                detect_local=False,
                probe_network=False,
            )
            assert "github" in result.servers


# ═══════════════════════════════════════════════════════════════
# _which utility test
# ═══════════════════════════════════════════════════════════════

class TestWhich:
    def test_which_python(self):
        """python/python3 should be in PATH."""
        py = _which("python") or _which("python3")
        assert py is not None

    def test_which_nonexistent(self):
        assert _which("definitely_not_a_real_command_xyz") is None


# ═══════════════════════════════════════════════════════════════
# Prefer-installed runners (found 2026-10-06)
# ═══════════════════════════════════════════════════════════════
#
# `uvx <pkg>` starts a second interpreter and unpacks the package into a fresh
# temp environment on every cold run. A config full of uvx entries — which is
# what `sync` pushes to every host — turns "open my agent" into "fetch N packages
# at once", which is the shape of the 2026-10-06 freeze. When the package is
# already importable, `python -m <module>` runs the same server with no fetch.
#
# The gate is two facts, not one: the module must resolve AND expose a
# `__main__` (`python -m` executes that). `json`/`http` resolve but have no
# `__main__`, so writing them would produce a server that dies on first launch.

class TestPreferInstalledRunners:
    def test_an_installed_runnable_module_wins_over_uvx(self):
        with patch.object(discover_mod, "_which", lambda c: "uvx" if c == "uvx" else None), \
             patch.object(discover_mod, "_resolve_local_module",
                          side_effect=lambda m: ["/py", "-m", m] if m == "mcp_server_fetch" else None):
            entries = {r["name"]: r["config"] for r in _detect_local_tools()}
        assert entries["fetch"]["command"] == ["/py"]
        assert entries["fetch"]["args"] == ["-m", "mcp_server_fetch"]
        # time has no local module in this scenario, so it keeps the fetch runner.
        assert entries["time"]["command"] == ["uvx"]
        assert entries["time"]["args"] == ["mcp-server-time"]

    def test_nothing_installed_still_offers_uvx(self):
        with patch.object(discover_mod, "_which", lambda c: "uvx" if c == "uvx" else None), \
             patch.object(discover_mod, "_resolve_local_module", return_value=None):
            entries = {r["name"]: r["config"] for r in _detect_local_tools()}
        assert entries["fetch"]["command"] == ["uvx"]
        assert entries["time"]["command"] == ["uvx"]

    def test_allow_fetch_keeps_uvx_even_when_installed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        from mcptoon import config as cfg
        cfg.set_setting("runners", "allow-fetch")
        with patch.object(discover_mod, "_which", lambda c: "uvx" if c == "uvx" else None), \
             patch.object(discover_mod, "_resolve_local_module", return_value=["/py", "-m", "mcp_server_fetch"]):
            entries = {r["name"]: r["config"] for r in _detect_local_tools()}
        assert entries["fetch"]["command"] == ["uvx"]

    def test_a_module_without_main_is_not_runnable(self):
        """`json` resolves but has no `__main__`, so `python -m json` would die.

        Pin the real function (not a mock) against a stdlib module that is
        importable everywhere — this is the check that keeps a bare
        `find_spec(module)` from writing a dead server entry.
        """
        assert discover_mod._resolve_local_module("json") is None
        assert discover_mod._resolve_local_module("no_such_module_zzz") is None

    def test_a_runnable_module_returns_the_interpreter_form(self):
        local = discover_mod._resolve_local_module("unittest")
        assert local is not None
        assert local[1:] == ["-m", "unittest"]
        assert local[0]  # an interpreter path, not a bare name

    def test_imported_uvx_row_becomes_a_local_module(self, monkeypatch, tmp_path):
        """`mcptoon import` must not carry a uvx row into mcptoon's own config.

        This is the exact route the 2026-10-06 incident took: `import --write`
        read the uvx rows out of Claude Desktop / Cline, and the next `sync`
        pushed them to all six hosts.
        """
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        with patch.object(discover_mod, "_resolve_local_module",
                          side_effect=lambda m: ["/py", "-m", m] if m == "mcp_server_fetch" else None):
            out = _normalize_imported_config(
                {"command": "uvx", "args": ["mcp-server-fetch"]})
        assert out["command"] == ["/py"]
        assert out["args"] == ["-m", "mcp_server_fetch"]

    def test_imported_uvx_row_survives_when_not_installed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        with patch.object(discover_mod, "_resolve_local_module", return_value=None):
            out = _normalize_imported_config(
                {"command": "uvx", "args": ["mcp-server-fetch"]})
        assert out["command"] == ["uvx"]
        assert out["args"] == ["mcp-server-fetch"]
