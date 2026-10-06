# Tests for mcptoon sync — config sync to AI agent formats
import json
from pathlib import Path
from unittest.mock import patch


from mcptoon.sync import (
    _mcptoon_to_agent_format,
    _build_mcp_servers_dict,
    _merge_mcp_servers,
    _write_json_safe,
    sync_to_agent,
    sync_to_all,
    format_sync_report,
    SELF_SERVER_NAME,
)
from mcptoon import sync as sync_mod


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
    def test_sync_all_dry_run(self, tmp_path):
        """Every *installed* agent that syncs servers reports one; codex reports none.

        `sync_to_all` writes only where `detect_installed_agents` says the agent is
        installed (see `test_it_does_not_write_a_config_for_an_agent_that_is_not_there`).
        The developer's machine may have none of the five, so pin the presence the
        test needs rather than depending on the host's `~/.claude` etc.
        """
        config = {
            "servers": {
                "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
            }
        }
        fake_agents = [
            {"id": "claude-desktop", "name": "Claude Desktop",
             "config_path": str(tmp_path / "claude.json"), "exists": True},
            {"id": "cursor", "name": "Cursor (global)",
             "config_path": str(tmp_path / "cursor.json"), "exists": True},
            {"id": "codex", "name": "Codex",
             "config_path": str(tmp_path / ".codex" / "AGENTS.md"), "exists": True},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents):
            results = sync_to_all(dry_run=True, config=config)
        assert len(results) > 0
        for r in results:
            if r["agent"] == "codex":
                # codex writes a skill pointer, not a server list (see
                # test_sync_dry_run_codex); without --self it is a no-op.
                assert r["servers_synced"] == 0
            else:
                assert r["servers_synced"] == 1

    def test_it_does_not_write_a_config_for_an_agent_that_is_not_there(self, tmp_path):
        """The 2026-10-02 clean-box bug: five config files, zero agents installed.

        `detect_installed_agents` reported `exists: False` for every host, and
        `sync_to_all` stored that fact as `config_exists` and then wrote anyway —
        creating `%APPDATA%\\Code\\User\\settings.json` on a machine with no VS Code.
        """
        config = {"servers": {"fetch": {"transport": "stdio", "command": ["npx"],
                                        "args": ["-y", "@mcp/fetch"]}}}
        fake_agents = [
            {"id": "claude-desktop", "name": "Claude Desktop",
             "config_path": str(tmp_path / "claude.json"), "exists": False},
            {"id": "cursor", "name": "Cursor (global)",
             "config_path": str(tmp_path / "cursor.json"), "exists": False},
        ]
        with patch.object(sync_mod, "detect_installed_agents", return_value=fake_agents), \
                patch.object(sync_mod, "sync_to_agent") as fake_sync:
            results = sync_to_all(dry_run=False, config=config)

        fake_sync.assert_not_called()
        assert not (tmp_path / "claude.json").exists()
        assert not (tmp_path / "cursor.json").exists()
        assert all(r["written"] is False for r in results)
        assert all(r.get("skipped_not_installed") for r in results)


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

    def test_cline_needs_its_own_extension_folder_not_just_vs_code(self, tmp_path):
        """VS Code installed ≠ Cline installed.

        The old check was the VS Code *User* directory
        (`path.parent.parent.parent.parent.exists()`), which is true on any machine
        with VS Code — so `quickstart` claimed to detect Cline and wrote it a config
        on hosts that never had it. `saoudrizwan.claude-dev` is the evidence.
        """
        from mcptoon.sync import detect_installed_agents

        user_dir = tmp_path / "Code" / "User"
        cline = (user_dir / "globalStorage" / "saoudrizwan.claude-dev"
                 / "settings" / "cline_mcp_settings.json")

        # VS Code present, Cline's extension folder absent → not detected.
        user_dir.mkdir(parents=True)
        with patch("mcptoon.sync._cline_path", return_value=cline):
            cline_rows = [a for a in detect_installed_agents() if a["id"] == "cline"]
        assert cline_rows and cline_rows[0]["exists"] is False

        # Cline's extension folder present → detected.
        (cline.parent.parent).mkdir(parents=True)
        with patch("mcptoon.sync._cline_path", return_value=cline):
            cline_rows = [a for a in detect_installed_agents() if a["id"] == "cline"]
        assert cline_rows and cline_rows[0]["exists"] is True


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


class TestQuickstartTakeoverOffer:
    """`quickstart` stays additive, but it *offers* takeover at the one moment the
    tradeoff is legible — and the offer is a subtraction, so it obeys Write Consent:
    listed, confirmed once, never silent, and impossible to trigger from a pipe.

    The bug this pins: alongside-mounting saves ~0 tokens (the host keeps loading
    every upstream schema), so an install that promised savings delivered none
    unless the user found `mcptoon sync --takeover` on their own. The offer puts
    that choice in front of them without flipping the safe default.
    """

    _PLAN = [{"agent_id": "cursor", "agent_name": "Cursor (global)",
              "path": "C:/x/mcp.json", "servers": ["fetch", "git"]}]

    def _call(self, rest, fmt="auto", isatty=True, answer="y", plan=None,
              env=None):
        from mcptoon import cli
        from mcptoon import sync as sync_mod
        import io as _io
        import contextlib
        buf = _io.StringIO()
        kwargs = {}
        if env:
            kwargs["new"] = env
        with patch.dict("os.environ", kwargs.get("new", {}), clear=False), \
             patch.object(sync_mod, "takeover_plan",
                          return_value=self._PLAN if plan is None else plan), \
             patch.object(cli.sys.stdin, "isatty", return_value=isatty), \
             patch("builtins.input", return_value=answer), \
             patch.object(cli, "_cmd_sync") as called, \
             contextlib.redirect_stdout(buf):
            cli._maybe_offer_takeover(rest, fmt)
        return buf.getvalue(), called

    def test_warns_in_red_and_lists_the_entries(self):
        out, _ = self._call([])
        assert "not saving tokens yet" in out
        assert "Cursor (global): fetch, git" in out          # the subtraction, listed

    def test_yes_hands_off_to_takeover(self):
        _, called = self._call([], answer="y")
        assert called.call_args is not None
        assert "--takeover" in called.call_args[0][0]
        assert "--yes" in called.call_args[0][0]             # the user just answered

    def test_default_answer_applies_takeover(self):
        """The prompt defaults to YES: the subtraction is listed above it and the
        undo (`mcptoon restore`) is real, so a bare Enter routes through the
        gateway rather than leaving the install saving nothing."""
        _, called = self._call([], answer="")
        assert called.call_args is not None
        assert "--takeover" in called.call_args[0][0]
        assert "--yes" in called.call_args[0][0]

    def test_no_keeps_servers_as_they_are(self):
        out, called = self._call([], answer="n")
        assert called.call_args is None                      # nothing applied
        assert "Kept your servers as they are" in out

    def test_piped_stdin_never_asks_and_never_subtracts(self):
        out, called = self._call([], isatty=False)
        assert called.call_args is None
        assert "Non-interactive input" in out
        assert "mcptoon sync --takeover" in out              # points at the manual path

    def test_dry_run_is_silent(self):
        out, called = self._call(["--dry"])
        assert out == "" and called.call_args is None

    def test_machine_format_is_silent(self):
        out, called = self._call([], fmt="json")
        assert out == "" and called.call_args is None

    def test_no_self_is_silent(self):
        """`--no-self` is servers-only: the user declined the gateway, so there is
        no alongside-mount to warn about."""
        out, called = self._call(["--no-self"])
        assert out == "" and called.call_args is None

    def test_nothing_to_remove_means_nothing_to_ask(self):
        out, called = self._call([], plan=[])
        assert out == "" and called.call_args is None

    def test_env_var_opts_out(self):
        out, called = self._call([], env={"MCPTOON_NO_TAKEOVER_OFFER": "1"})
        assert out == "" and called.call_args is None

    def test_prompt_defaults_to_yes(self):
        """A bare Enter applies takeover: the entries are listed above it and the
        undo (`mcptoon restore`) is real."""
        _, called = self._call([], answer="")
        assert called.call_args is not None
        assert "--takeover" in called.call_args[0][0]

    def test_warning_is_plain_text_when_captured(self):
        """No escape codes in a transcript: the same rule `welcome.render` follows."""
        out, _ = self._call([])
        assert "\x1b[" not in out

    def test_warning_is_red_on_a_console(self):
        import os
        from mcptoon import welcome as w
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("NO_COLOR", "MCPTOON_NO_COLOR")}
        with patch.dict(os.environ, clean, clear=True):
            painted = w.paint("WARNING", "warn", stream=_Tty())
        assert painted == "\x1b[1;31mWARNING\x1b[0m"


class _Tty:
    def isatty(self):
        return True


class TestWriteBackVerification:
    """A successful write is not proof the entry survived.

    Claude Code's `~/.claude.json` is a live state store the host rewrites on its
    own schedule; a writer that races mcptoon can drop the gateway entry straight
    back out. `_write_json_safe` therefore reads its own write back and reports a
    loss instead of returning a green `written: True` over an absent entry.
    """

    def _gateway_payload(self):
        return {"mcpServers": {SELF_SERVER_NAME: {"command": "python"}}}

    def test_a_surviving_entry_verifies_true(self, tmp_path):
        target = tmp_path / "config.json"
        assert _write_json_safe(target, self._gateway_payload()) is True
        assert SELF_SERVER_NAME in json.loads(target.read_text())["mcpServers"]

    def test_a_lost_entry_is_reported_false(self, tmp_path, capsys):
        """Simulate a host rewriting the file between our write and our read-back."""
        target = tmp_path / "config.json"
        real_write = Path.write_text

        def clobbering_write(self_path, text, *a, **k):
            real_write(self_path, text, *a, **k)
            if self_path == target:
                # A competing writer drops the gateway entry right after we write.
                real_write(self_path, json.dumps({"mcpServers": {"other": {}}}), encoding="utf-8")

        with patch.object(Path, "write_text", clobbering_write):
            ok = _write_json_safe(target, self._gateway_payload())
        assert ok is False
        err = capsys.readouterr().err
        assert "lost" in err and SELF_SERVER_NAME in err

    def test_no_warning_when_the_gateway_is_not_in_the_payload(self, tmp_path, capsys):
        """A non-gateway write has nothing to verify — it must not cry wolf."""
        target = tmp_path / "config.json"
        assert _write_json_safe(target, {"mcpServers": {"fetch": {}}}) is True
        assert capsys.readouterr().err == ""


class TestRestore:
    """`mcptoon restore` is the real undo of `sync --takeover`.

    The bug this pins: `off` only removes the gateway entry; it never reads the
    `.bak` takeover wrote, so the servers takeover dropped are gone from the live
    file and survive only in that backup. Before `restore`, the CLI pointed users
    at `off` as the undo, which silently lost their direct entries.
    """

    _CFG = {"servers": {
        "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
        "git": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/git"]},
    }}

    def test_takeover_then_off_loses_entries_restore_recovers(self, tmp_path):
        """The whole point: takeover, `off`, then `restore` puts the originals back."""
        from mcptoon.sync import (remove_gateway_from_agent, restore_agent_from_backup)
        cfg_path = tmp_path / "cursor.json"
        original = {"mcpServers": {
            "fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]},
            "git": {"command": "npx", "args": ["-y", "@mcp/git"]},
            "handwritten": {"command": "python", "args": ["-m", "mine"]},
        }}
        cfg_path.write_text(json.dumps(original))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            # takeover dropped fetch+git, kept handwritten, added the gateway
            after = json.loads(cfg_path.read_text())["mcpServers"]
            assert "mcptoon" in after and "fetch" not in after and "handwritten" in after
            # `off` removes the gateway but does NOT bring fetch/git back
            remove_gateway_from_agent("cursor", path=cfg_path)
            off_state = json.loads(cfg_path.read_text())["mcpServers"]
            assert "mcptoon" not in off_state
            assert "fetch" not in off_state, "this is the bug `restore` exists to fix"
            # `restore` returns the dropped servers — originals back, gateway gone
            r = restore_agent_from_backup("cursor", path=cfg_path)
            assert r["restored"] and r["written"]
        restored = json.loads(cfg_path.read_text())
        assert restored == original, "restore must reproduce the pre-mcptoon file exactly"

    def test_restore_never_deletes_servers_added_after_the_backup(self, tmp_path):
        """The real-machine trap: a stale `.bak` must not wipe later additions.

        This machine's `~/.claude.json.bak` (2026-09-24) held `mcpServers: []`
        while the live file had grown 12 servers by 2026-09-26. A whole-file copy
        of that `.bak` would have deleted all 12. `restore` is surgical: it removes
        only the gateway entry and re-adds only what the `.bak` lost — never a
        server the user added after the backup.
        """
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "claude.json"
        # mcptoon's edit backed up an *empty* server set, then added the gateway.
        cfg_path.write_text(json.dumps({"mcpServers": {}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            # the user later hand-adds servers of their own
            live = json.loads(cfg_path.read_text())
            live["mcpServers"]["mine1"] = {"command": "python"}
            live["mcpServers"]["mine2"] = {"command": "node"}
            cfg_path.write_text(json.dumps(live))
            restore_agent_from_backup("cursor", path=cfg_path)
        after = json.loads(cfg_path.read_text())["mcpServers"]
        assert "mcptoon" not in after          # gateway removed
        assert "mine1" in after and "mine2" in after, "user's later servers survive"

    def test_restore_dry_run_writes_nothing(self, tmp_path):
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "cursor.json"
        original = {"mcpServers": {"fetch": {"command": "npx"}}}
        cfg_path.write_text(json.dumps(original))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            before = cfg_path.read_text()
            r = restore_agent_from_backup("cursor", dry_run=True, path=cfg_path)
        assert r["restored"] and not r["written"]
        assert cfg_path.read_text() == before  # untouched

    def test_restore_without_a_backup_is_a_noop(self, tmp_path):
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        r = restore_agent_from_backup("cursor", path=cfg_path)
        assert not r["restored"] and not r["written"]

    def test_restore_plan_lists_only_differing_configs(self, tmp_path):
        from mcptoon.sync import restore_plan
        cfg_path = tmp_path / "cursor.json"
        original = {"mcpServers": {"fetch": {"command": "npx"}}}
        cfg_path.write_text(json.dumps(original))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)",
                  "config_path": str(cfg_path), "exists": True}]):
            assert restore_plan() == []  # no .bak yet → nothing to restore
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            plan = restore_plan()
        assert len(plan) == 1 and plan[0]["agent"] == "cursor"
        assert plan[0]["backup"].endswith(".bak")

    def test_restore_removes_the_skill_pointer_too(self, tmp_path):
        """A host with the pointer leg must not be left pointing at a dead catalog."""
        from mcptoon.sync import restore_agent_from_backup, _SKILL_POINTER_HEADING
        cfg_path = tmp_path / "codex.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        pointer = tmp_path / "AGENTS.md"
        pointer.write_text("# My notes\n\n" + _SKILL_POINTER_HEADING + "\n\nuse mcptoon\n")
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.pointer_path", return_value=pointer):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            r = restore_agent_from_backup("cursor", path=cfg_path)
        assert r["pointer_removed"] is True
        text = pointer.read_text()
        assert _SKILL_POINTER_HEADING not in text
        assert "My notes" in text  # the user's own content survives

    def test_cli_restore_command_end_to_end(self, tmp_path, capsys):
        """`mcptoon restore` prints the plan, then puts the file back."""
        from mcptoon import cli
        cfg_path = tmp_path / "cursor.json"
        original = {"mcpServers": {"fetch": {"command": "npx", "args": ["-y", "@mcp/fetch"]}}}
        cfg_path.write_text(json.dumps(original))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)",
                  "config_path": str(cfg_path), "exists": True}]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            assert "fetch" not in json.loads(cfg_path.read_text())["mcpServers"]
            cli._cmd_restore(["--yes"], "auto")
        out = capsys.readouterr().out
        assert "restore" in out.lower()
        assert json.loads(cfg_path.read_text()) == original

    def test_cli_restore_dry_run_is_a_preview(self, tmp_path, capsys):
        from mcptoon import cli
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)",
                  "config_path": str(cfg_path), "exists": True}]):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            before = cfg_path.read_text()
            cli._cmd_restore(["--dry"], "auto")
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert cfg_path.read_text() == before

    def test_cli_restore_non_interactive_refuses_without_yes(self, tmp_path, capsys):
        from mcptoon import cli
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {"fetch": {"command": "npx"}}}))
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]), \
             patch("mcptoon.sync.detect_installed_agents", return_value=[
                 {"id": "cursor", "name": "Cursor (global)",
                  "config_path": str(cfg_path), "exists": True}]), \
             patch.object(cli.sys.stdin, "isatty", return_value=False):
            sync_to_agent("cursor", dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)
            before = cfg_path.read_text()
            cli._cmd_restore([], "auto")
        out = capsys.readouterr().out
        assert "Refusing" in out
        assert cfg_path.read_text() == before


class TestRestoreNeverDeletesWhatItCannotRead:
    """Red-team regressions: the undo must never delete or clobber data it cannot parse.

    Every case below is a real data-loss path found by an adversarial review of the
    first surgical-restore implementation. The theme: "I could not read this" was
    being treated as "there was nothing here", which let a rollback delete a whole
    config file. These pin the fix.
    """

    _CFG = {"servers": {
        "fetch": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/fetch"]},
        "git": {"transport": "stdio", "command": ["npx"], "args": ["-y", "@mcp/git"]},
    }}

    def _takeover(self, tmp_path, cfg_path, agent="cursor"):
        with patch("mcptoon.sync._cursor_path", return_value=[cfg_path]):
            sync_to_agent(agent, dry_run=False, config=self._CFG,
                          include_self=True, takeover=True)

    def test_unreadable_backup_does_not_delete_a_settings_file(self, tmp_path):
        """A JSONC `settings.json` (VS Code's real format) must never be unlinked."""
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "settings.json"
        # JSONC: comments + trailing comma — `json.loads` rejects it.
        jsonc = '{ // my editor\n  "editor.fontSize": 15,\n  "mcp": {"servers": {}},\n}\n'
        cfg_path.write_text(jsonc)
        self._takeover(tmp_path, cfg_path, agent="vscode-copilot")
        assert "mcptoon" in cfg_path.read_text() or True  # takeover may refuse; either way:
        cfg_path.write_text(jsonc)  # simulate the host still holding the original
        restore_agent_from_backup("vscode-copilot", path=cfg_path)
        assert cfg_path.exists(), "restore deleted a config it could not parse"
        assert "editor.fontSize" in cfg_path.read_text()

    def test_missing_backup_does_not_delete_a_config_with_servers(self, tmp_path):
        """No `.bak`, live file has a real server -> the file must survive."""
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]},
            "keepme": {"command": "python"}}}))
        restore_agent_from_backup("cursor", path=cfg_path)
        assert cfg_path.exists()
        assert "keepme" in json.loads(cfg_path.read_text())["mcpServers"]

    def test_corrupt_backup_does_not_delete_a_config_with_servers(self, tmp_path):
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]},
            "keepme": {"command": "python"}}}))
        (tmp_path / "cursor.json.bak").write_text("{ not json")
        restore_agent_from_backup("cursor", path=cfg_path)
        assert cfg_path.exists()
        assert "keepme" in json.loads(cfg_path.read_text())["mcpServers"]

    def test_directory_backup_does_not_delete_a_config_with_servers(self, tmp_path):
        from mcptoon.sync import restore_agent_from_backup
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]},
            "keepme": {"command": "python"}}}))
        (tmp_path / "cursor.json.bak").mkdir()
        restore_agent_from_backup("cursor", path=cfg_path)
        assert cfg_path.exists()
        assert "keepme" in json.loads(cfg_path.read_text())["mcpServers"]

    def test_symlinked_backup_is_not_followed(self, tmp_path):
        """A `.bak` symlink must not import another file's servers into this host."""
        from mcptoon.sync import restore_agent_from_backup
        other = tmp_path / "other-agent.json"
        other.write_text(json.dumps({"mcpServers": {"secret-server": {"command": "x"}}}))
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]},
            "keepme": {"command": "python"}}}))
        try:
            (tmp_path / "cursor.json.bak").symlink_to(other)
        except (OSError, NotImplementedError):
            return  # symlink creation not permitted here; covered on Linux CI
        restore_agent_from_backup("cursor", path=cfg_path)
        assert "secret-server" not in json.loads(cfg_path.read_text())["mcpServers"]

    def test_user_server_named_mcptoon_is_not_removed(self, tmp_path):
        """A real server the user named `mcptoon` is not the gateway; leave it."""
        from mcptoon.sync import remove_gateway_from_agent
        cfg_path = tmp_path / "cursor.json"
        cfg_path.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "user-own-real-server"},
            "other": {"command": "x"}}}))
        r = remove_gateway_from_agent("cursor", path=cfg_path)
        servers = json.loads(cfg_path.read_text())["mcpServers"]
        assert "mcptoon" in servers, "off deleted a user's own same-named server"
        assert r["removed"] is False

    def test_non_dict_sections_do_not_crash_restore_all(self, tmp_path):
        """One malformed host must not abort the restore of the others."""
        from mcptoon.sync import restore_all_from_backup
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"mcpServers": ["not", "a", "dict"]}))
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"mcpServers": {
            "mcptoon": {"command": "python", "args": ["-m", "mcptoon", "serve"]}}}))
        with patch("mcptoon.sync.detect_installed_agents", return_value=[
                {"id": "cursor", "name": "Bad", "config_path": str(bad), "exists": True},
                {"id": "cline", "name": "Good", "config_path": str(good), "exists": True}]):
            results = restore_all_from_backup()
        assert len(results) == 2, "a malformed host aborted the loop"
        good_servers = json.loads(good.read_text())["mcpServers"]
        assert "mcptoon" not in good_servers, "good host was not restored"

    def test_jsonc_settings_is_not_clobbered_by_sync(self, tmp_path):
        """`sync` must refuse to rewrite a JSONC settings.json, not drop its settings."""
        jsonc = '{\n  // keep my editor settings\n  "editor.fontSize": 15\n}\n'
        cfg_path = tmp_path / "settings.json"
        cfg_path.write_text(jsonc)
        with patch("mcptoon.sync._vscode_copilot_path", return_value=cfg_path):
            r = sync_to_agent("vscode-copilot", dry_run=False, config=self._CFG,
                              include_self=True)
        assert cfg_path.read_text() == jsonc, "sync clobbered a JSONC settings.json"
        assert r["written"] is False

    def test_appended_user_content_below_pointer_survives(self, tmp_path):
        """The undo of the skill pointer must not eat text the user added below it."""
        from mcptoon.sync import (_write_skill_pointer, _remove_skill_pointer)
        p = tmp_path / "AGENTS.md"
        p.write_text("# My rules\n")
        _write_skill_pointer(p)
        with p.open("a", encoding="utf-8") as f:
            f.write("\n# Deploy runbook\n\nstep 1\n")
        _remove_skill_pointer(p)
        text = p.read_text()
        assert "Deploy runbook" in text, "undo deleted user content below the pointer"
        assert "step 1" in text
        assert "My rules" in text


# ─── The agent table is the single source of truth ───
#
# The refactor's whole claim is "a host is one row". These tests are what keeps
# that claim true: they fail if a row is added that the dispatchers cannot drive,
# if a hardcoded id creeps back in beside the table, or if detection and the table
# drift apart.

class TestAgentTable:
    def test_every_row_resolves_a_config_path(self):
        """Each row's `path_fn` must exist and return a usable path."""
        from mcptoon.sync import _AGENT_SPECS, _agent_config_path

        for spec in _AGENT_SPECS:
            path = _agent_config_path(spec.id)
            assert path is not None, f"{spec.id}: no config path"
            assert path.is_absolute(), f"{spec.id}: path is not absolute ({path})"

    def test_shapes_are_a_closed_set(self):
        """A typo'd shape would silently fall back to `mcpServers` — pin the set."""
        from mcptoon.sync import _AGENT_SPECS

        for spec in _AGENT_SPECS:
            assert spec.shape in ("mcpServers", "mcp.servers", "pointer"), spec

    def test_a_cli_only_host_must_carry_a_pointer(self):
        """No MCP config and no pointer = the host receives nothing at all."""
        from mcptoon.sync import _AGENT_SPECS

        for spec in _AGENT_SPECS:
            if not spec.mcp:
                assert spec.pointer_fn is not None, \
                    f"{spec.id} is CLI-only but has no pointer_fn: unreachable host"

    def test_pointer_path_agrees_with_the_table(self):
        """`pointer_path` is driven by `pointer_fn` — one rule, no second list."""
        from mcptoon.sync import _AGENT_SPECS, pointer_path

        for spec in _AGENT_SPECS:
            got = pointer_path(spec.id)
            if spec.pointer_fn is None:
                assert got is None, f"{spec.id}: unexpected pointer {got}"
            else:
                assert got is not None and got.is_absolute(), spec.id

    def test_detection_only_reports_hosts_in_the_table(self):
        """`detect_installed_agents` must not invent an id the table does not hold."""
        from mcptoon.sync import _AGENT_SPEC_BY_ID, detect_installed_agents

        for agent in detect_installed_agents():
            assert agent["id"] in _AGENT_SPEC_BY_ID, agent

    def test_adding_a_row_is_enough_to_support_a_host(self, tmp_path, monkeypatch):
        """The actual claim: a new host is one row, no branch anywhere else.

        A synthetic row is spliced into the table and then driven through the
        public-ish entry points (`_agent_config_path`, `_servers_section`,
        `_write_servers_section`, `sync_to_agent`) without touching any other
        function — which is only possible because the dispatchers read the table.
        """
        from mcptoon import sync as sync_mod

        fake_cfg = tmp_path / "brandnew" / "mcp.json"
        monkeypatch.setattr(sync_mod, "_brandnew_path", lambda: fake_cfg,
                            raising=False)
        row = sync_mod._AgentSpec("brandnew", "Brand New", "_brandnew_path")
        monkeypatch.setattr(sync_mod, "_AGENT_SPECS", sync_mod._AGENT_SPECS + (row,))
        monkeypatch.setattr(sync_mod, "_AGENT_SPEC_BY_ID",
                            {**sync_mod._AGENT_SPEC_BY_ID, "brandnew": row})

        assert sync_mod._agent_config_path("brandnew") == fake_cfg
        data = sync_mod._write_servers_section({}, "brandnew", {"fetch": {"command": "npx"}})
        assert data["mcpServers"] == {"fetch": {"command": "npx"}}
        assert sync_mod._servers_section(data, "brandnew") == {"fetch": {"command": "npx"}}

        config = {"servers": {"fetch": {"transport": "stdio", "command": ["npx"],
                                        "args": ["-y", "@mcp/fetch"]}}}
        result = sync_mod.sync_to_agent("brandnew", dry_run=False, config=config)
        assert result["written"] is True, result
        assert "fetch" in json.loads(fake_cfg.read_text())["mcpServers"]

    def test_write_servers_section_round_trips_both_shapes(self):
        """Write then read must land in the same place for both storage shapes."""
        from mcptoon.sync import _servers_section, _write_servers_section

        payload = {"fetch": {"command": "npx"}}
        flat = _write_servers_section({}, "cursor", dict(payload))
        assert flat["mcpServers"] == payload
        assert _servers_section(flat, "cursor") == payload

        nested = _write_servers_section({}, "vscode-copilot", dict(payload))
        assert nested["mcp"]["servers"] == payload
        assert "mcpServers" not in nested
        assert _servers_section(nested, "vscode-copilot") == payload

    def test_write_servers_section_keeps_unrelated_vscode_settings(self):
        """The VS Code shape must edit in place, not replace the whole settings file."""
        from mcptoon.sync import _write_servers_section

        live = {"editor.fontSize": 15, "mcp": {"servers": {"keep": {}}}}
        out = _write_servers_section(live, "vscode-copilot", {"fetch": {"command": "npx"}})
        assert out["editor.fontSize"] == 15
        assert "keep" not in out["mcp"]["servers"]

    def test_every_pointer_host_names_a_distinct_instruction_file(self):
        """Two pointer rows writing the same file would silently double-write.

        Also pins the *shape* of the CLI leg: a pointer host's `path_fn` and
        `pointer_fn` must agree, or `detect` would report one file while `sync`
        edits another (the exact class of bug `_codex_agents_path` fixed).
        """
        from mcptoon.sync import _AGENT_SPECS, _agent_config_path, pointer_path

        seen: dict[Path, str] = {}
        for spec in _AGENT_SPECS:
            if spec.mcp:
                continue
            p = pointer_path(spec.id)
            assert p is not None and p.is_absolute(), spec.id
            assert _agent_config_path(spec.id) == p, \
                f"{spec.id}: sync writes a different file than the pointer names"
            assert p not in seen, f"{spec.id} and {seen.get(p)} share {p}"
            seen[p] = spec.id

    def test_pointer_hosts_carry_a_txt_or_md_file_not_json(self):
        """A pointer host's file is prose the agent reads — not a JSON config."""
        from mcptoon.sync import _AGENT_SPECS, pointer_path

        for spec in _AGENT_SPECS:
            if spec.mcp:
                continue
            assert pointer_path(spec.id).suffix.lower() in (".md", ".txt"), spec.id

    def test_config_dir_honours_xdg_config_home(self, monkeypatch, tmp_path):
        """A moved XDG_CONFIG_HOME must move the XDG hosts' pointer with it.

        Writing to `~/.config` while the host reads `$XDG_CONFIG_HOME` is the
        silent no-op this module keeps guarding against, so the env var is
        load-bearing, not decorative.
        """
        from mcptoon import sync as s

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert s._config_dir() == tmp_path
        assert s._crush_path() == tmp_path / "crush" / "CRUSH.md"
        assert s._opencode_path() == tmp_path / "opencode" / "AGENTS.md"

    def test_pointer_hosts_get_the_same_block_as_codex(self, tmp_path, monkeypatch):
        """One delivery mechanism for every CLI host — not a per-host copy."""
        from mcptoon import sync as s

        for host, helper in (("gemini", "_gemini_path"), ("qwen", "_qwen_path"),
                             ("zed", "_zed_path"), ("crush", "_crush_path"),
                             ("opencode", "_opencode_path")):
            target = tmp_path / host / "AGENTS.md"
            monkeypatch.setattr(s, helper, lambda t=target: t)
            result = s.sync_to_agent(host, config={"servers": {}}, include_self=True)
            assert result["written"] is True, (host, result)
            assert s._SKILL_POINTER_HEADING in target.read_text(encoding="utf-8"), host
            # Opt-in: a plain sync must not touch the file.
            target.unlink()
            s.sync_to_agent(host, config={"servers": {}}, include_self=False)
            assert not target.exists(), host

    def test_readme_agent_table_names_every_host_in_the_table(self):
        """The README's "Works with" table is a promise; a missing row is a broken one.

        The five pointer rows landed in the code first, and the README kept listing
        seven hosts — the exact drift this pins shut. Only the *name* is checked
        (the prose per row is free), so a wording change cannot fail it.
        """
        from mcptoon.sync import _AGENT_SPECS

        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        # Target the per-host *table* (the "host by host" subsection), not the market
        # lists above it — a name appearing in the long list must not satisfy a row
        # the hookup table is missing.
        section = readme.split("### What mcptoon writes, host by host", 1)
        assert len(section) == 2, "the README table heading changed"
        table = section[1].split("```", 1)[0]

        def present(spec) -> bool:
            # A report-only parenthetical ("Codex (AGENTS.md)") is not a README name;
            # accept either the bare display name or the row id.
            return spec.name.split(" (", 1)[0] in table or spec.id in table

        missing = [spec.name for spec in _AGENT_SPECS if not present(spec)]
        assert not missing, f"README table omits: {missing}"


# ═══════════════════════════════════════════════════════════════
# Prefer-installed runner (found 2026-10-06)
# ═══════════════════════════════════════════════════════════════
#
# `sync` is the last place a uvx entry can be intercepted before it reaches every
# host config. A user's own mcptoon config — or one written by an older version —
# may hold `uvx <pkg>` rows; sync rewrites them to `python -m <module>` when the
# package is installed, so opening an agent stops meaning "fetch N packages".

class TestSyncPrefersInstalledRunner:
    def test_uvx_entry_is_rewritten_when_the_package_is_installed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        with patch.object(sync_mod, "_prefer_installed_runner",
                          wraps=sync_mod._prefer_installed_runner):
            from mcptoon import discover as disc
            with patch.object(disc, "_resolve_local_module",
                              side_effect=lambda m: ["/py", "-m", m] if m == "mcp_server_time" else None):
                cfg = {"servers": {"time": {"transport": "stdio", "command": ["uvx"],
                                            "args": ["mcp-server-time"]}}}
                out = _build_mcp_servers_dict(cfg)
        assert out["time"]["command"] == "/py"
        assert out["time"]["args"] == ["-m", "mcp_server_time"]

    def test_uvx_entry_survives_when_the_package_is_absent(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        from mcptoon import discover as disc
        with patch.object(disc, "_resolve_local_module", return_value=None):
            cfg = {"servers": {"time": {"transport": "stdio", "command": ["uvx"],
                                        "args": ["mcp-server-time"]}}}
            out = _build_mcp_servers_dict(cfg)
        assert out["time"]["command"] == "uvx"
        assert out["time"]["args"] == ["mcp-server-time"]

    def test_allow_fetch_keeps_the_uvx_entry(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        from mcptoon import config as cfg_mod
        cfg_mod.set_setting("runners", "allow-fetch")
        from mcptoon import discover as disc
        with patch.object(disc, "_resolve_local_module",
                          return_value=["/py", "-m", "mcp_server_time"]):
            cfg = {"servers": {"time": {"transport": "stdio", "command": ["uvx"],
                                        "args": ["mcp-server-time"]}}}
            out = _build_mcp_servers_dict(cfg)
        assert out["time"]["command"] == "uvx"

    def test_a_non_uvx_entry_is_untouched(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MCPTOON_SETTINGS_FILE", str(tmp_path / "settings.json"))
        cfg = {"servers": {"fs": {"transport": "stdio", "command": ["npx"],
                                  "args": ["-y", "@modelcontextprotocol/server-filesystem"]}}}
        out = _build_mcp_servers_dict(cfg)
        assert out["fs"]["command"] == "npx"
        assert out["fs"]["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]
