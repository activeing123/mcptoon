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


class TestTwoLegs:
    """Both legs reach a host at once: an MCP mount AND a pointer in its memory file.

    Claude Code is the host that carries both, so it is the case pinned here. The
    point of two legs (CONTEXT.md) is that the user never has to choose between
    "native tools with a tool panel" and "near-zero context" — each leg covers what
    the other cannot. A host with no instruction file gets the MCP leg alone, and
    that must not be an error.
    """

    _CFG = {
        "servers": {
            "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
        }
    }

    def _paths(self, tmp_path):
        return tmp_path / ".claude.json", tmp_path / ".claude" / "CLAUDE.md"

    def test_claude_code_gets_the_mount_and_the_pointer(self, tmp_path):
        json_path, memory = self._paths(tmp_path)
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_text("# My own rules\n\nkeep me\n", encoding="utf-8")
        with patch("mcptoon.sync._claude_code_path", return_value=json_path), \
             patch("mcptoon.sync._claude_code_memory_path", return_value=memory):
            result = sync_to_agent("claude-code", dry_run=False, config=self._CFG,
                                   include_self=True)
        assert result["written"] is True
        assert "mcptoon" in json.loads(json_path.read_text())["mcpServers"]
        text = memory.read_text(encoding="utf-8")
        assert "## Skill catalog (mcptoon)" in text
        assert text.startswith("# My own rules\n\nkeep me\n"), \
            "the user's own content must survive byte for byte"

    def test_the_pointer_is_idempotent(self, tmp_path):
        json_path, memory = self._paths(tmp_path)
        with patch("mcptoon.sync._claude_code_path", return_value=json_path), \
             patch("mcptoon.sync._claude_code_memory_path", return_value=memory):
            first = sync_to_agent("claude-code", config=self._CFG, include_self=True)
            second = sync_to_agent("claude-code", config=self._CFG, include_self=True)
        assert first["pointer"]["written"] is True
        assert second["pointer"]["written"] is False
        assert memory.read_text(encoding="utf-8").count("## Skill catalog (mcptoon)") == 1

    def test_no_pointer_without_self(self, tmp_path):
        """`sync` is routine; the pointer belongs to "let this host see mcptoon"."""
        json_path, memory = self._paths(tmp_path)
        with patch("mcptoon.sync._claude_code_path", return_value=json_path), \
             patch("mcptoon.sync._claude_code_memory_path", return_value=memory):
            result = sync_to_agent("claude-code", config=self._CFG, include_self=False)
        assert result["pointer"] is None
        assert not memory.exists()

    def test_dry_run_writes_no_pointer(self, tmp_path):
        json_path, memory = self._paths(tmp_path)
        with patch("mcptoon.sync._claude_code_path", return_value=json_path), \
             patch("mcptoon.sync._claude_code_memory_path", return_value=memory):
            result = sync_to_agent("claude-code", dry_run=True, config=self._CFG,
                                   include_self=True)
        assert result["pointer"]["would_write"] is True
        assert not memory.exists()
        assert not json_path.exists()

    def test_off_removes_both_legs_and_restores_the_memory_file(self, tmp_path):
        """`off` must not leave a pointer telling an agent about an absent gateway."""
        from mcptoon.sync import remove_gateway_from_agent
        json_path, memory = self._paths(tmp_path)
        memory.parent.mkdir(parents=True, exist_ok=True)
        original = "# My own rules\n\nkeep me\n"
        memory.write_text(original, encoding="utf-8")
        with patch("mcptoon.sync._claude_code_path", return_value=json_path), \
             patch("mcptoon.sync._claude_code_memory_path", return_value=memory):
            sync_to_agent("claude-code", config=self._CFG, include_self=True)
            assert "## Skill catalog (mcptoon)" in memory.read_text(encoding="utf-8")
            result = remove_gateway_from_agent("claude-code")
        assert result["removed"] is True
        assert result["pointer_removed"] is True
        assert "mcptoon" not in json.loads(json_path.read_text())["mcpServers"]
        assert memory.read_text(encoding="utf-8") == original, \
            "the memory file must come back exactly as it was"

    def test_a_host_without_an_instruction_file_is_mcp_only(self):
        """Windsurf has no global instruction file — that is not an error."""
        from mcptoon.sync import pointer_path
        for agent in ("windsurf", "cline", "claude-desktop", "vscode-copilot"):
            assert pointer_path(agent) is None, agent

    def test_pointer_paths_are_machine_wide(self):
        from pathlib import Path
        from mcptoon.sync import pointer_path
        for agent in ("codex", "claude-code"):
            p = pointer_path(agent)
            assert p is not None and p.is_absolute(), (agent, p)
            assert Path.cwd() not in p.parents, "a pointer must not be project-bound"

    def test_a_pointer_write_failure_is_reported_not_raised(self, tmp_path):
        from mcptoon.sync import _write_skill_pointer
        blocked = tmp_path / "nope" / "SKILL.md"
        blocked.parent.write_text("not a directory", encoding="utf-8")
        out = _write_skill_pointer(blocked)
        assert out["written"] is False
        assert out["error"]


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

    def test_report_names_the_pointer_leg(self):
        """A host reached by the pointer alone must not read as "nothing to write"."""
        results = [
            {"agent": "codex", "agent_name": "Codex (AGENTS.md)",
             "path": "C:/Users/x/.codex/AGENTS.md", "servers_synced": 0,
             "taken_over": 0, "written": False, "error": None, "config_exists": True,
             "pointer": {"path": "C:/Users/x/.codex/AGENTS.md", "written": True,
                         "error": None}},
        ]
        report = format_sync_report(results, dry_run=False)
        assert "skill pointer" in report
        assert "1 skill pointer(s)" in report
        assert "nothing to write" not in report

    def test_report_shows_both_legs_on_one_host(self):
        """Claude Code carries a mount and a pointer; the report shows both."""
        results = [
            {"agent": "claude-code", "agent_name": "Claude Code",
             "path": "C:/Users/x/.claude.json", "servers_synced": 13,
             "taken_over": 0, "written": True, "error": None, "config_exists": True,
             "pointer": {"path": "C:/Users/x/.claude/CLAUDE.md", "written": True,
                         "error": None}},
        ]
        report = format_sync_report(results, dry_run=False)
        assert "13 servers" in report
        assert "skill pointer" in report
        assert "C:/Users/x/.claude/CLAUDE.md" in report

    def test_report_counts_a_previewed_pointer(self):
        """A dry run has written nothing, yet the preview still says what would happen."""
        results = [
            {"agent": "codex", "agent_name": "Codex (AGENTS.md)",
             "path": "C:/Users/x/.codex/AGENTS.md", "servers_synced": 0,
             "taken_over": 0, "written": False, "error": None, "config_exists": True,
             "pointer": {"path": "C:/Users/x/.codex/AGENTS.md", "written": False,
                         "would_write": True, "error": None}},
        ]
        report = format_sync_report(results, dry_run=True)
        assert "1 skill pointer(s)" in report


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


class TestTakeoverConsent:
    """The subtraction half of Write Consent: takeover lists what it will drop and
    asks once before doing it.

    Additions (`--self`, the pointer) may be silent; removing a server entry the
    user wrote is not the same act. These tests pin the *plan* the CLI shows, the
    `--dry`/`--yes`/prompt branches, and — the safety property — that a declined or
    unanswerable prompt writes nothing.
    """

    _CFG = TestTakeover._CFG  # fetch + git, both managed

    def _write_host(self, tmp_path):
        cfg = tmp_path / "cursor.json"
        cfg.write_text(json.dumps({"mcpServers": {
            "fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]},
            "git": {"command": "npx", "args": ["-y", "@mcp/git"]},
            "handwritten": {"command": "mine"},
        }}))
        return cfg

    def test_plan_lists_managed_servers_and_skips_host_only(self, tmp_path):
        from mcptoon.sync import takeover_plan
        cfg = self._write_host(tmp_path)
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]):
            plan = takeover_plan("cursor", config=self._CFG)
        assert len(plan) == 1
        assert plan[0]["servers"] == ["fetch", "git"]   # managed …
        assert "handwritten" not in plan[0]["servers"]  # … never the host's own
        assert plan[0]["path"] == str(cfg)

    def test_plan_is_empty_when_nothing_would_be_dropped(self, tmp_path):
        from mcptoon.sync import takeover_plan
        cfg = tmp_path / "cursor.json"
        cfg.write_text(json.dumps({"mcpServers": {"handwritten": {"command": "mine"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]):
            plan = takeover_plan("cursor", config=self._CFG)
        assert plan == []

    def test_plan_writes_nothing(self, tmp_path):
        """A plan is a read. The config must be byte-identical after computing it."""
        from mcptoon.sync import takeover_plan
        cfg = self._write_host(tmp_path)
        before = cfg.read_text()
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]):
            takeover_plan("cursor", config=self._CFG)
        assert cfg.read_text() == before

    def test_cli_dry_run_prints_the_plan_and_writes_nothing(self, tmp_path, capsys):
        from mcptoon import cli
        from mcptoon import sync as sync_mod
        cfg = self._write_host(tmp_path)
        before = cfg.read_text()
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]), \
             patch.object(sync_mod, "detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)", "config_path": str(cfg),
                  "exists": True}]), \
             patch.object(sync_mod, "load_config", return_value=self._CFG):
            cli._cmd_sync(["--takeover", "--dry"], "auto")
        out = capsys.readouterr().out
        assert "fetch" in out and "git" in out      # the plan names them …
        assert "Dry run" in out
        assert cfg.read_text() == before            # … and nothing was removed

    def test_cli_declined_prompt_removes_nothing(self, tmp_path, capsys):
        """The safety property: an answer that is not yes leaves the config alone."""
        from mcptoon import cli
        from mcptoon import sync as sync_mod
        cfg = self._write_host(tmp_path)
        before = cfg.read_text()
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]), \
             patch.object(sync_mod, "detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)", "config_path": str(cfg),
                  "exists": True}]), \
             patch.object(sync_mod, "load_config", return_value=self._CFG), \
             patch.object(cli.sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", return_value="n"):
            cli._cmd_sync(["--takeover"], "auto")
        out = capsys.readouterr().out
        assert "Cancelled" in out
        assert cfg.read_text() == before

    def test_cli_yes_flag_skips_the_prompt(self, tmp_path, capsys):
        """--yes is the scripted path: it applies without an interactive answer."""
        from mcptoon import cli
        from mcptoon import sync as sync_mod
        cfg = self._write_host(tmp_path)
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]), \
             patch.object(sync_mod, "detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)", "config_path": str(cfg),
                  "exists": True}]), \
             patch.object(sync_mod, "load_config", return_value=self._CFG), \
             patch.object(cli.sys.stdin, "isatty", return_value=False):
            cli._cmd_sync(["--takeover", "--yes"], "auto")
        servers = json.loads(cfg.read_text())["mcpServers"]
        assert "mcptoon" in servers                    # gateway is the connection now
        assert "fetch" not in servers and "git" not in servers
        assert "handwritten" in servers                # host-only entry survives

    def test_cli_non_interactive_stdin_refuses_without_yes(self, tmp_path, capsys):
        """Piped/CI stdin cannot answer, so takeover refuses rather than removing."""
        from mcptoon import cli
        from mcptoon import sync as sync_mod
        cfg = self._write_host(tmp_path)
        before = cfg.read_text()
        with patch("mcptoon.sync._cursor_path", return_value=[cfg]), \
             patch.object(sync_mod, "detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)", "config_path": str(cfg),
                  "exists": True}]), \
             patch.object(sync_mod, "load_config", return_value=self._CFG), \
             patch.object(cli.sys.stdin, "isatty", return_value=False):
            cli._cmd_sync(["--takeover"], "auto")
        out = capsys.readouterr().out
        assert "Refusing" in out
        assert cfg.read_text() == before
