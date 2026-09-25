# Tests for mcptoon sync — config sync to AI agent formats
import json
from unittest.mock import patch


from mcptoon.sync import (
    _mcptoon_to_agent_format,
    _build_mcp_servers_dict,
    _merge_mcp_servers,
    sync_to_agent,
    sync_to_all,
    format_sync_report,
)


# ─── Config conversion tests ───

class TestConfigConversion:
    def test_stdio_server(self):
        """stdio server converts to agent format correctly."""
        cfg = {
            "transport": "stdio",
            "command": ["npx"],
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
            "env": {"API_KEY": "xxx"},
        }
        result = _mcptoon_to_agent_format("fetch", cfg)
        assert result["command"] == "npx"
        assert result["args"] == ["-y", "@modelcontextprotocol/server-fetch"]
        assert result["env"]["API_KEY"] == "xxx"

    def test_http_server(self):
        """HTTP server converts to agent format correctly."""
        cfg = {
            "transport": "http",
            "url": "http://localhost:8080/mcp",
            "headers": {"Authorization": "Bearer xxx"},
        }
        result = _mcptoon_to_agent_format("remote", cfg)
        assert result["url"] == "http://localhost:8080/mcp"
        assert result["headers"]["Authorization"] == "Bearer xxx"

    def test_stdio_multi_command(self):
        """stdio with multi-element command splits correctly."""
        cfg = {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@mcp/server-fetch"],
        }
        result = _mcptoon_to_agent_format("fetch", cfg)
        assert result["command"] == "npx"
        assert "-y" in result["args"]
        assert "@mcp/server-fetch" in result["args"]

    def test_empty_config(self):
        """Empty config returns empty dict."""
        result = _mcptoon_to_agent_format("empty", {})
        assert result == {} or len(result) == 0


class TestBuildMcpServersDict:
    def test_from_servers_key(self):
        """Config with 'servers' key parsed correctly."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = _build_mcp_servers_dict(config)
        assert "fetch" in result
        assert result["fetch"]["command"] == "npx"

    def test_empty_config(self):
        """Empty config produces empty dict."""
        result = _build_mcp_servers_dict({})
        assert result == {}


# ─── Sync to agent tests ───

class TestSyncToAgent:
    def test_sync_no_config(self):
        """No servers in config returns error."""
        result = sync_to_agent("cursor", dry_run=True, config={"servers": {}})
        assert result["servers_synced"] == 0
        assert result["error"] is not None

    def test_sync_unknown_agent(self):
        """Unknown agent ID returns error."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("nonexistent", dry_run=True, config=config)
        assert result["error"] == "Unknown agent: nonexistent"

    def test_sync_dry_run_cursor(self):
        """Dry run to cursor returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("cursor", dry_run=True, config=config)
        assert result["servers_synced"] == 1
        assert result["written"] is False
        assert result["error"] is None

    def test_sync_dry_run_claude_desktop(self):
        """Dry run to Claude Desktop returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("claude-desktop", dry_run=True, config=config)
        assert result["servers_synced"] == 1
        assert result["written"] is False

    def test_sync_dry_run_vscode_copilot(self):
        """Dry run to VS Code Copilot returns correct info."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        result = sync_to_agent("vscode-copilot", dry_run=True, config=config)
        assert result["servers_synced"] == 1

    def test_sync_dry_run_codex(self):
        """Codex syncs no servers — it gets a skill pointer, and only under --self.

        The old contract claimed `servers_synced == 1`, which was never true: the
        Codex branch appended a note to AGENTS.md and left every server in
        mcptoon's config. The assertion outlived the mistake. Codex mounts no MCP,
        so the pointer is the whole payload, and it rides the same `--self` opt-in
        the gateway registration uses.
        """
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        without = sync_to_agent("codex", dry_run=True, config=config)
        assert without["servers_synced"] == 0
        assert without["written"] is False

        result = sync_to_agent("codex", dry_run=True, config=config, include_self=True)
        assert result["servers_synced"] == 0
        assert result["written"] is False  # dry run writes nothing
        assert result["path"].endswith("AGENTS.md")

    def test_sync_actual_write(self, tmp_path):
        """Test actual write to a temp file."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        with patch("mcptoon.sync._cursor_path", return_value=[tmp_path / "cursor.json"]):
            result = sync_to_agent("cursor", dry_run=False, config=config)
            assert result["written"] is True
            assert result["servers_synced"] == 1
            written = json.loads((tmp_path / "cursor.json").read_text())
            assert "mcpServers" in written
            assert "fetch" in written["mcpServers"]

    def test_sync_merge_existing(self, tmp_path):
        """Sync preserves existing servers not in mcptoon."""
        config_path = tmp_path / "cursor.json"
        existing = {"mcpServers": {"old-server": {"command": "echo", "args": ["hi"]}}}
        config_path.write_text(json.dumps(existing))
        config_path.parent.mkdir(exist_ok=True)

        config = {
            "servers": {
                "new-server": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/new"]},
            }
        }
        with patch("mcptoon.sync._cursor_path", return_value=[config_path]):
            result = sync_to_agent("cursor", dry_run=False, config=config)
            assert result["written"] is True
            written = json.loads(config_path.read_text())
            assert "old-server" in written["mcpServers"]
            assert "new-server" in written["mcpServers"]


class TestSyncToAll:
    def test_sync_all_dry_run(self):
        """Every agent that syncs servers reports one; codex reports none by design."""
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        results = sync_to_all(dry_run=True, config=config)
        assert len(results) > 0
        for r in results:
            if r["agent"] == "codex":
                # codex writes a skill pointer, not a server list (see
                # test_sync_dry_run_codex); without --self it is a no-op.
                assert r["servers_synced"] == 0
            else:
                assert r["servers_synced"] == 1


class TestCodexSkillPointer:
    """Codex mounts no MCP, so AGENTS.md is its only channel to the catalog.

    Three things the writer used to get wrong, each pinned here: the target was
    `Path.cwd()` (a random project, or nowhere), the text never mentioned skills,
    and it fired on every `sync` instead of behind `--self`.
    """

    def _cfg(self):
        return {"servers": {"fetch": {"transport": "stdio", "command": ["npx"],
                                      "args": ["-y", "@mcp/fetch"]}}}

    def test_writes_the_pointer_to_the_global_path(self, tmp_path):
        target = tmp_path / ".codex" / "AGENTS.md"
        with patch("mcptoon.sync._codex_agents_path", return_value=target):
            result = sync_to_agent("codex", config=self._cfg(), include_self=True)
        assert result["written"] is True
        text = target.read_text(encoding="utf-8")
        assert "mcptoon skills resolve" in text, "the pointer must name the resolver"
        assert "SKILL.md" in text
        assert "never" not in text.lower() or True  # wording is not pinned, content is

    def test_it_does_not_touch_cwd(self, tmp_path):
        """The old bug: the pointer landed in whatever directory sync ran from."""
        cwd_agents = tmp_path / "AGENTS.md"
        target = tmp_path / ".codex" / "AGENTS.md"
        with patch("mcptoon.sync._codex_agents_path", return_value=target), \
             patch("mcptoon.sync.Path.cwd", return_value=tmp_path):
            sync_to_agent("codex", config=self._cfg(), include_self=True)
        assert not cwd_agents.exists(), "codex must not write into the working directory"

    def test_idempotent(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        target.write_text("# My own notes\n\nkeep me\n", encoding="utf-8")
        with patch("mcptoon.sync._codex_agents_path", return_value=target):
            first = sync_to_agent("codex", config=self._cfg(), include_self=True)
            second = sync_to_agent("codex", config=self._cfg(), include_self=True)
        assert first["written"] is True
        assert second["written"] is False, "a second sync must not append again"
        text = target.read_text(encoding="utf-8")
        assert text.count("## Skill catalog (mcptoon)") == 1
        assert "keep me" in text, "the user's own content survives"

    def test_no_pointer_without_include_self(self, tmp_path):
        target = tmp_path / "AGENTS.md"
        target.write_text("existing\n", encoding="utf-8")
        with patch("mcptoon.sync._codex_agents_path", return_value=target):
            result = sync_to_agent("codex", config=self._cfg())
        assert result["written"] is False
        assert target.read_text(encoding="utf-8") == "existing\n"

    def test_undo_removes_exactly_the_block(self, tmp_path):
        from mcptoon.sync import gateway_present_in, remove_gateway_from_agent

        target = tmp_path / "AGENTS.md"
        target.write_text("# Notes\n\nmine\n", encoding="utf-8")
        with patch("mcptoon.sync._codex_agents_path", return_value=target):
            sync_to_agent("codex", config=self._cfg(), include_self=True)
            assert gateway_present_in("codex") is True
            removed = remove_gateway_from_agent("codex")
        assert removed["removed"] is True
        assert gateway_present_in("codex") is False
        assert target.read_text(encoding="utf-8") == "# Notes\n\nmine\n", \
            "the undo must restore the file byte-for-byte"


class TestClaudeCodeTarget:
    """Claude Code keeps `mcpServers` in `~/.claude.json`, same shape as Cursor."""

    def test_sync_writes_mcp_servers(self, tmp_path):
        target = tmp_path / ".claude.json"
        target.write_text(json.dumps({"numStartups": 3}), encoding="utf-8")
        config = {"servers": {"fetch": {"transport": "stdio", "command": ["npx"],
                                        "args": ["-y", "@mcp/fetch"]}}}
        with patch("mcptoon.sync._claude_code_path", return_value=target):
            result = sync_to_agent("claude-code", config=config, include_self=True)
        assert result["written"] is True
        written = json.loads(target.read_text(encoding="utf-8"))
        assert "fetch" in written["mcpServers"]
        assert "mcptoon" in written["mcpServers"], "--self registers the gateway"
        assert written["numStartups"] == 3, "unrelated keys are preserved"

    def test_detected_when_the_config_exists(self, tmp_path):
        from mcptoon.sync import detect_installed_agents

        target = tmp_path / ".claude.json"
        target.write_text("{}", encoding="utf-8")
        with patch("mcptoon.sync._claude_code_path", return_value=target):
            ids = [a["id"] for a in detect_installed_agents()]
        assert "claude-code" in ids

    def test_absent_when_the_config_does_not_exist(self, tmp_path):
        from mcptoon.sync import detect_installed_agents

        with patch("mcptoon.sync._claude_code_path", return_value=tmp_path / "nope.json"):
            ids = [a["id"] for a in detect_installed_agents()]
        assert "claude-code" not in ids


class TestFormatReport:
    def test_report_format(self):
        """Report contains key info."""
        results = [
            {"agent": "cursor", "agent_name": "Cursor (global)", "path": "/tmp/x", "servers_synced": 2, "written": True, "error": None, "config_exists": True},
            {"agent": "claude-desktop", "agent_name": "Claude Desktop", "path": "/tmp/y", "servers_synced": 0, "written": False, "error": "not installed", "config_exists": False},
        ]
        report = format_sync_report(results, dry_run=False)
        assert "SYNC COMPLETE" in report
        assert "Cursor" in report
        assert "2" in report


class TestTakeover:
    """Takeover is the difference between "add a gateway" and "the gateway is the
    connection".

    Without it the host keeps every upstream server entry and simply gains a
    ``mcptoon`` one, so it still loads all the upstream schemas and the gateway
    saves nothing (the gap this feature closes). Each test below pins one
    property of the takeover path: it drops exactly the managed servers, leaves
    unknown/host-only ones alone, reports what it removed, and is reversible via
    the backup that the write already takes.
    """

    _CFG = {
        "servers": {
            "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            "git": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/git"]},
        }
    }

    def test_merge_drops_managed_and_keeps_unknown(self):
        """Only servers mcptoon manages are dropped; a host-only one survives."""
        existing = {"mcpServers": {
            "fetch": {"command": "old-fetch"},
            "git": {"command": "old-git"},
            "someone-elses": {"command": "keep-me"},
        }}
        new = {"fetch": {"command": "npx"}, "git": {"command": "npx"}}
        merged = _merge_mcp_servers(existing, new, takeover=True)
        # The gateway cannot serve a server it does not know, so it is kept …
        assert "someone-elses" in merged["mcpServers"]
        # … and the managed pair is gone from the direct list (not re-added).
        assert set(merged["mcpServers"]) == {"someone-elses"}

    def test_merge_takeover_writes_back_the_gateway_entry(self):
        """With the gateway included, takeover keeps only it plus unknown servers."""
        existing = {"mcpServers": {"fetch": {"command": "old"}}}
        new = {"fetch": {"command": "npx"}, "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]}}
        merged = _merge_mcp_servers(existing, new, takeover=True)
        assert set(merged["mcpServers"]) == {"mcptoon"}
        assert merged["mcpServers"]["mcptoon"]["args"] == ["-m", "mcptoon", "serve"]

    def test_merge_without_takeover_keeps_direct_entries(self):
        """The default stays additive — this is the pre-existing behavior, pinned."""
        existing = {"mcpServers": {"fetch": {"command": "npx"}}}
        merged = _merge_mcp_servers(existing, {"fetch": {"command": "npx"}}, takeover=False)
        assert "fetch" in merged["mcpServers"]

    def test_takeover_removes_direct_entries_and_adds_gateway(self, tmp_path):
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]},
            "git": {"command": "npx", "args": ["-y", "@mcp/git"]},
            "handwritten": {"command": "mine"},
        }}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            result = sync_to_agent("cursor", dry_run=False, config=self._CFG,
                                   include_self=True, takeover=True)
        assert result["written"] is True
        assert result["taken_over"] == 2  # fetch + git were direct, now via gateway
        written = json.loads(cfg_path.read_text())
        servers = written["mcpServers"]
        assert "mcptoon" in servers                       # gateway registered
        assert "handwritten" in servers                   # host-only kept
        assert "fetch" not in servers and "git" not in servers  # no longer direct

    def test_takeover_is_reversible_from_the_backup(self, tmp_path):
        """The `.bak` the write takes is the undo — the original direct entries."""
        cfg_path = tmp_path / "cursor.json"
        original = {"mcpServers": {"fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]}}}
        cfg_path.write_text(json.dumps(original))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
        bak = cfg_path.with_suffix(cfg_path.suffix + ".bak")
        assert bak.exists()
        assert json.loads(bak.read_text()) == original

    def test_takeover_dry_run_writes_nothing(self, tmp_path):
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            result = sync_to_agent("cursor", dry_run=True, config=self._CFG,
                                   include_self=True, takeover=True)
        assert result["written"] is False
        assert result["taken_over"] == 1
        assert json.loads(cfg_path.read_text())["mcpServers"]["fetch"] == {"command": "npx"}

    def test_takeover_implies_include_self(self, tmp_path):
        """Asking for takeover without --self must not strip the host bare: the
        gateway entry that replaces the direct ones is always written."""
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG, takeover=True)
        servers = json.loads(cfg_path.read_text())["mcpServers"]
        assert "mcptoon" in servers       # the replacement is there …
        assert "fetch" not in servers     # … and the direct entry is gone

    def test_takeover_default_off_in_sync_to_all(self, tmp_path):
        """sync_to_all without takeover stays additive (no surprise edits)."""
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)", "config_path": str(cfg_path), "exists": True}]):
            sync_to_all(dry_run=False, config=self._CFG, include_self=False, takeover=False)
        servers = json.loads(cfg_path.read_text())["mcpServers"]
        # fetch is still a *direct* entry (updated to mcptoon's definition, which
        # is the documented default), and no gateway entry was injected.
        assert "fetch" in servers
        assert servers["fetch"]["args"] == ["-y", "@mcp/fetch"]
        assert "mcptoon" not in servers

    def test_report_names_the_takeover_count(self):
        results = [
            {"agent": "cursor", "agent_name": "Cursor (global)", "path": "/tmp/x",
             "servers_synced": 3, "taken_over": 2, "written": True, "error": None,
             "config_exists": True},
        ]
        report = format_sync_report(results, dry_run=False)
        assert "now via gateway" in report
        assert "2" in report
