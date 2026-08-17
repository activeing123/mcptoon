"""Tests for cross-server tool search and auto-routing."""
from unittest.mock import patch

import pytest

from mcptoon.manifest import (
    search_tools,
    find_tool_across_servers,
    _tokenize,
    _search_score,
)
from mcptoon.router import call_tool_auto
from mcptoon.errors import is_error


# ─── Test fixtures ───

MOCK_MANIFEST = {
    "exa": [
        {"name": "search", "description": "Search the web for information", "inputSchema": {"properties": {"query": {"type": "string"}, "num": {"type": "integer"}}, "required": ["query"]}},
        {"name": "find_similar", "description": "Find similar pages to a URL", "inputSchema": {"properties": {"url": {"type": "string"}}}},
    ],
    "fetch": [
        {"name": "fetch", "description": "Fetch a URL and return content", "inputSchema": {"properties": {"url": {"type": "string"}}, "required": ["url"]}},
    ],
    "github": [
        {"name": "search_repositories", "description": "Search GitHub repositories", "inputSchema": {"properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "create_issue", "description": "Create a GitHub issue", "inputSchema": {"properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title"]}},
    ],
}


@pytest.fixture
def mock_manifest():
    """Patch get_manifest to return a known set of tools."""
    with patch("mcptoon.manifest.get_manifest", return_value=MOCK_MANIFEST):
        yield


# ═══════════════════════════════════════════════════
# Tokenize tests
# ═══════════════════════════════════════════════════

class TestTokenize:
    def test_simple_word(self):
        assert _tokenize("search") == ["search"]

    def test_multi_word(self):
        tokens = _tokenize("search web pages")
        assert "search" in tokens
        assert "web" in tokens
        assert "pages" in tokens

    def test_with_separators(self):
        tokens = _tokenize("git-commit")
        assert "git" in tokens
        assert "commit" in tokens

    def test_filters_short_tokens(self):
        tokens = _tokenize("a b cd ef")
        assert "cd" in tokens
        assert "ef" in tokens
        assert "a" not in tokens
        assert "b" not in tokens

    def test_empty(self):
        assert _tokenize("") == []

    def test_numbers(self):
        tokens = _tokenize("page123")
        assert "page123" in tokens


# ═══════════════════════════════════════════════════
# Search score tests
# ═══════════════════════════════════════════════════

class TestSearchScore:
    def test_exact_match(self):
        score = _search_score("search", {"search"}, "search", "search the web")
        assert score == 1.0

    def test_prefix_match(self):
        score = _search_score("search", {"search"}, "search_repositories", "search repos")
        assert score >= 0.85

    def test_substring_match(self):
        score = _search_score("fetch", {"fetch"}, "fetch_url", "fetch a url")
        assert score >= 0.75

    def test_token_overlap(self):
        score = _search_score("search web", {"search", "web"}, "web_search", "search the web")
        assert score >= 0.6

    def test_description_match(self):
        # desc is already lowercased (as search_tools does before calling _search_score)
        score = _search_score("github", {"github"}, "search_repositories", "search github repositories")
        assert score >= 0.45

    def test_no_match(self):
        score = _search_score("xyz", {"xyz"}, "search", "search the web")
        assert score == 0.0

    def test_empty_query(self):
        assert _search_score("", set(), "search", "desc") == 0.0

    def test_empty_name(self):
        assert _search_score("search", {"search"}, "", "desc") == 0.0

    def test_fuzzy_typo(self):
        # "serch" vs "search" — fuzzy should catch this
        # Even with tokens, if no overlap, fuzzy should still be tried
        score = _search_score("serch", {"serch"}, "search", "")
        assert score > 0.0


# ═══════════════════════════════════════════════════
# search_tools tests
# ═══════════════════════════════════════════════════

class TestSearchTools:
    def test_search_exact_name(self, mock_manifest):
        results = search_tools("search")
        assert len(results) > 0
        # exa/search should be top result (exact match)
        top = results[0]
        assert top["server"] == "exa"
        assert top["name"] == "search"
        assert top["score"] == 1.0

    def test_search_multi_word(self, mock_manifest):
        results = search_tools("search web")
        assert len(results) > 0
        # exa/search should match well
        exa_results = [r for r in results if r["server"] == "exa" and r["name"] == "search"]
        assert len(exa_results) > 0

    def test_search_description(self, mock_manifest):
        results = search_tools("github")
        assert len(results) > 0
        # github/search_repositories should match
        gh_results = [r for r in results if r["server"] == "github"]
        assert len(gh_results) > 0

    def test_search_no_results(self, mock_manifest):
        results = search_tools("xyz_nonexistent")
        assert len(results) == 0

    def test_search_limit(self, mock_manifest):
        results = search_tools("search", limit=2)
        assert len(results) <= 2

    def test_search_results_have_fields(self, mock_manifest):
        results = search_tools("search")
        assert len(results) > 0
        r = results[0]
        assert "server" in r
        assert "name" in r
        assert "description" in r
        assert "params" in r
        assert "score" in r

    def test_search_sorted_by_score(self, mock_manifest):
        results = search_tools("search")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_fetch_tool(self, mock_manifest):
        results = search_tools("fetch")
        assert len(results) > 0
        fetch_results = [r for r in results if r["server"] == "fetch" and r["name"] == "fetch"]
        assert len(fetch_results) > 0
        assert fetch_results[0]["score"] == 1.0

    def test_search_params_included(self, mock_manifest):
        results = search_tools("search")
        exa_search = [r for r in results if r["server"] == "exa" and r["name"] == "search"][0]
        # search has query:string* and num:integer
        assert "query" in exa_search["params"]
        assert "string*" in exa_search["params"]  # required string


# ═══════════════════════════════════════════════════
# find_tool_across_servers tests
# ═══════════════════════════════════════════════════

class TestFindToolAcrossServers:
    def test_find_existing_tool(self, mock_manifest):
        servers = find_tool_across_servers("search")
        assert "exa" in servers
        assert "github" not in servers  # github has search_repositories, not search

    def test_find_nonexistent_tool(self, mock_manifest):
        servers = find_tool_across_servers("nonexistent_tool")
        assert servers == []

    def test_find_fetch(self, mock_manifest):
        servers = find_tool_across_servers("fetch")
        assert "fetch" in servers

    def test_find_create_issue(self, mock_manifest):
        servers = find_tool_across_servers("create_issue")
        assert "github" in servers


# ═══════════════════════════════════════════════════
# call_tool_auto tests
# ═══════════════════════════════════════════════════

class TestCallToolAuto:
    def test_auto_find_tool(self, mock_manifest):
        """call_tool_auto should find the server that has the tool."""
        with patch("mcptoon.router.call_tool") as mock_call:
            mock_call.return_value = {"result": "ok"}
            call_tool_auto("fetch", {"url": "http://example.com"})
            # Should have called call_tool with server="fetch"
            assert mock_call.called
            args = mock_call.call_args
            assert args[0][0] == "fetch"  # server name
            assert args[0][1] == "fetch"  # tool name

    def test_auto_tool_not_found(self, mock_manifest):
        """call_tool_auto should return error for non-existent tool."""
        result = call_tool_auto("nonexistent_tool")
        assert is_error(result)
        err = result["_error"]
        assert err["code"] == "TOOL_NOT_FOUND"

    def test_auto_multiple_servers_picks_first(self, mock_manifest):
        """When multiple servers have the same tool, should pick one."""
        # Add a second server with "search" tool
        manifest_with_dup = dict(MOCK_MANIFEST)
        manifest_with_dup["brave"] = [
            {"name": "search", "description": "Brave search", "inputSchema": {"properties": {"q": {"type": "string"}}}},
        ]
        with patch("mcptoon.manifest.get_manifest", return_value=manifest_with_dup):
            with patch("mcptoon.router.call_tool") as mock_call:
                mock_call.return_value = {"result": "ok"}
                with patch("mcptoon.router.usage.get_usage_stats", return_value={"by_server": {}}):
                    call_tool_auto("search", {"query": "AI"})
                    assert mock_call.called
                    # Should have called with one of the servers
                    server_used = mock_call.call_args[0][0]
                    assert server_used in ("exa", "brave")

    def test_auto_with_destructive(self, mock_manifest):
        """call_tool_auto should pass is_destructive through."""
        with patch("mcptoon.router.call_tool") as mock_call:
            mock_call.return_value = {"result": "ok"}
            call_tool_auto("fetch", {"url": "http://example.com"}, is_destructive=True)
            # is_destructive is passed as 4th positional arg (index 3)
            assert mock_call.call_args[0][3] is True
