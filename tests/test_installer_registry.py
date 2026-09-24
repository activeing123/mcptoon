"""Tests for the registry-backed installer (search + routing).

These are all offline: ``_fetch_json`` is patched, so the suite stays green without
a network — that is deliberate (a zero-dependency stdlib project should not need the
internet to run ``pytest``). The live check that the configured hosts still exist
lives in ``scripts/check_registry_sources.py`` and is run separately.

The payload shapes asserted here were captured from the real APIs on 2026-09-24.
"""
import os
import sys
import unittest
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.installer import (  # noqa: E402
    MCP_REGISTRY_URL,
    SMITHERY_API_URL,
    RegistryError,
    _relevant,
    _search_mcp_registry,
    _search_smithery,
    _slug,
    install_by_name,
    search_registry,
)

# ── real payload shapes ──

SMITHERY_PAYLOAD = {
    "servers": [
        {"id": "944cef5a", "qualifiedName": "github", "displayName": "GitHub",
         "description": "Connect your AI agents to GitHub", "verified": True,
         "useCount": 6059, "remote": True, "isDeployed": True},
        {"id": "abc", "qualifiedName": "michael-johnson/hello-mcp",
         "displayName": "Hello", "description": "A greeting server",
         "verified": False, "useCount": 0, "remote": True, "isDeployed": True},
    ],
    "pagination": {"totalCount": 2},
}

REGISTRY_PAYLOAD = {
    "servers": [
        {"server": {"name": "com.mcparmory/github", "version": "1.0.0",
                    "description": "Manage repositories and GitHub workflows",
                    "packages": [{"registryType": "pypi", "identifier": "mcparmory",
                                  "transport": {"type": "stdio"}}],
                    "remotes": None},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # an older version of the same server — must be dropped
        {"server": {"name": "com.mcparmory/github", "version": "0.9.0",
                    "description": "old", "packages": [], "remotes": None},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": False}}},
        {"server": {"name": "ac.inference.sh/mcp", "version": "1.0.0",
                    "description": "Run 150+ AI apps",
                    "packages": None,
                    "remotes": [{"type": "streamable-http", "url": "https://sh.inference.ac"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
    ],
    "metadata": {"nextCursor": "x", "count": 3},
}


def _fake_fetch(smithery=SMITHERY_PAYLOAD, registry=REGISTRY_PAYLOAD):
    def _fetch(url, timeout=10):
        if "smithery" in url:
            return smithery
        if "modelcontextprotocol.io" in url:
            return registry
        raise AssertionError(f"unexpected URL: {url}")
    return _fetch


class TestSlug(unittest.TestCase):
    def test_registry_names(self):
        self.assertEqual(_slug("ai.adeu/adeu"), "adeu")
        self.assertEqual(_slug("com.mcparmory/github"), "github")
        self.assertEqual(_slug("@scope/pkg"), "pkg")

    def test_lowercased_and_sanitised(self):
        self.assertEqual(_slug("GitHub"), "github")
        self.assertEqual(_slug("some.name"), "some_name")

    def test_never_empty(self):
        self.assertEqual(_slug(""), "server")
        self.assertEqual(_slug("///"), "server")


class TestRelevance(unittest.TestCase):
    def test_real_match_passes(self):
        self.assertTrue(_relevant("postgres", {"name": "PostgreSQL", "description": ""}))
        self.assertTrue(_relevant("github", {"name": "github", "description": ""}))

    def test_typo_is_rejected(self):
        # Smithery fuzzy-fallback would return unrelated servers for a typo.
        self.assertFalse(_relevant("githbu", {"name": "michael-johnson/hello-mcp",
                                              "description": "A greeting server"}))

    def test_stopword_only_query_browses(self):
        # "mcp" alone matches everything by design; do not filter it to nothing.
        self.assertTrue(_relevant("mcp", {"name": "anything", "description": ""}))

    def test_matches_description_too(self):
        self.assertTrue(_relevant("obsidian", {"name": "vault-sync",
                                               "description": "Sync your Obsidian notes"}))


class TestSourceParsing(unittest.TestCase):
    def test_smithery_marks_verified_and_hosted(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = _search_smithery("github", 10)
        by_name = {r["name"]: r for r in out}
        self.assertTrue(by_name["github"]["verified"])
        self.assertEqual(by_name["github"]["uses"], 6059)
        self.assertEqual(by_name["github"]["command"], "")  # hosted, not a package
        self.assertFalse(by_name["michael-johnson/hello-mcp"]["verified"])

    def test_registry_uses_search_param_not_q(self):
        calls = []

        def _capture(url, timeout=10):
            calls.append(url)
            return REGISTRY_PAYLOAD

        with patch("mcptoon.installer._fetch_json", _capture):
            _search_mcp_registry("github", 10)
        self.assertTrue(any("search=github" in u for u in calls), calls)
        self.assertFalse(any("q=github" in u for u in calls), calls)

    def test_registry_dedupes_versions_and_prefers_latest(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = _search_mcp_registry("github", 10)
        names = [r["name"] for r in out]
        self.assertEqual(names.count("com.mcparmory/github"), 1)

    def test_registry_maps_pypi_to_uvx(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = _search_mcp_registry("github", 10)
        pkg = next(r for r in out if r["name"] == "com.mcparmory/github")
        self.assertEqual(pkg["command"], "uvx")
        self.assertEqual(pkg["args"], ["mcparmory"])
        self.assertEqual(pkg["kind"], "pypi")

    def test_registry_keeps_remote_url_when_no_package(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = _search_mcp_registry("github", 10)
        remote = next(r for r in out if r["name"] == "ac.inference.sh/mcp")
        self.assertEqual(remote["url"], "https://sh.inference.ac")
        self.assertEqual(remote["command"], "")


class TestSearchRegistry(unittest.TestCase):
    def test_merges_both_sources(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = search_registry("github", 10)
        sources = {r["source"] for r in out}
        self.assertEqual(sources, {"smithery", "registry"})

    def test_exact_name_ranks_first(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()):
            out = search_registry("github", 10)
        self.assertEqual(out[0]["name"], "github")

    def test_empty_result_when_sources_alive(self):
        empty = {"servers": [], "pagination": {}}
        with patch("mcptoon.installer._fetch_json", _fake_fetch(smithery=empty, registry=empty)):
            self.assertEqual(search_registry("github", 10), [])

    def test_raises_when_every_source_fails(self):
        def _boom(url, timeout=10):
            raise OSError("getaddrinfo failed")
        with patch("mcptoon.installer._fetch_json", _boom):
            with self.assertRaises(RegistryError):
                search_registry("github", 10)

    def test_one_live_source_is_enough(self):
        def _half(url, timeout=10):
            if "smithery" in url:
                raise OSError("smithery down")
            return REGISTRY_PAYLOAD
        with patch("mcptoon.installer._fetch_json", _half):
            out = search_registry("github", 10)
        self.assertTrue(out)
        self.assertTrue(all(r["source"] == "registry" for r in out))


class TestInstallRouting(unittest.TestCase):
    def test_not_found_returns_error_envelope(self):
        empty = {"servers": [], "pagination": {}}
        with patch("mcptoon.installer._fetch_json", _fake_fetch(smithery=empty, registry=empty)):
            res = install_by_name("nosuchthing")
        self.assertEqual(res["_error"]["code"], "NOT_FOUND")

    def test_registry_unreachable_is_not_reported_as_not_found(self):
        def _boom(url, timeout=10):
            raise OSError("getaddrinfo failed")
        with patch("mcptoon.installer._fetch_json", _boom):
            res = install_by_name("github")
        self.assertEqual(res["_error"]["code"], "REGISTRY_UNREACHABLE")

    def test_hosted_entry_routes_to_http(self):
        with patch("mcptoon.installer._fetch_json", _fake_fetch()), \
             patch("mcptoon.installer._smithery_url", return_value="https://github.run.tools"), \
             patch("mcptoon.installer.install_http") as http:
            install_by_name("github")
        http.assert_called_once()
        self.assertEqual(http.call_args[0][0], "https://github.run.tools")

    def test_package_entry_routes_to_custom_runner(self):
        payload = {"servers": [
            {"server": {"name": "acme/github", "version": "1.0.0",
                        "description": "github things",
                        "packages": [{"registryType": "npm",
                                      "identifier": "@acme/mcp-github"}],
                        "remotes": None},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        ], "metadata": {}}
        empty = {"servers": [], "pagination": {}}
        with patch("mcptoon.installer._fetch_json",
                   _fake_fetch(smithery=empty, registry=payload)), \
             patch("mcptoon.installer.install_custom") as custom:
            install_by_name("github")
        custom.assert_called_once()
        _key, command, args = custom.call_args[0][:3]
        # Platform-agnostic: the runner may be resolved to a full path on Windows
        # (npx.cmd), which is the point of _resolve_runner.
        self.assertIn("npx", command.lower())
        self.assertEqual(args, ["-y", "@acme/mcp-github"])

    def test_unroutable_entry_refuses_instead_of_writing_broken_config(self):
        payload = {"servers": [
            {"server": {"name": "acme/ghost", "version": "1.0.0",
                        "description": "ghost tool", "packages": [], "remotes": []},
             "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        ], "metadata": {}}
        empty = {"servers": [], "pagination": {}}
        with patch("mcptoon.installer._fetch_json",
                   _fake_fetch(smithery=empty, registry=payload)):
            res = install_by_name("ghost")
        self.assertEqual(res["_error"]["code"], "NOT_INSTALLABLE")


class TestRunnerResolution(unittest.TestCase):
    def test_bare_npx_becomes_launchable(self):
        from mcptoon.installer import _resolve_runner
        self.assertIn("npx", _resolve_runner("npx").lower())

    def test_unknown_runner_passes_through(self):
        from mcptoon.installer import _resolve_runner
        self.assertEqual(_resolve_runner("my-runner"), "my-runner")


class TestHandlersDir(unittest.TestCase):
    """A fresh clone has no handlers/ (it is gitignored), so the generator must make it."""

    def test_generate_creates_missing_handlers_dir(self):
        import tempfile
        from pathlib import Path
        from mcptoon.installer import _generate_handler_file
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "handlers"
            self.assertFalse(target.exists())
            with patch("mcptoon.installer._handlers_dir",
                       side_effect=lambda: (target.mkdir(parents=True, exist_ok=True),
                                            str(target))[1]):
                _generate_handler_file("demo", [], "npx", ["-y", "x"], [], "test")
            self.assertTrue((target / "demo.py").is_file())


class TestConfiguredHosts(unittest.TestCase):
    """Regression guard for the rot that silently killed this feature."""

    def test_smithery_host_is_the_live_one(self):
        self.assertEqual(SMITHERY_API_URL, "https://registry.smithery.ai")

    def test_official_host_is_the_live_one(self):
        self.assertEqual(MCP_REGISTRY_URL, "https://registry.modelcontextprotocol.io/v0")

    def test_dead_hosts_are_gone(self):
        for dead in ("smithery.ai/api", "registry.modelcontextprotocol.org", "mcp.so"):
            self.assertNotIn(dead, SMITHERY_API_URL + MCP_REGISTRY_URL)


if __name__ == "__main__":
    unittest.main()
