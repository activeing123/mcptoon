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

"""
mcptoon sync — Sync MCP server config to AI agent config files.

Reads mcptoon's unified config (~/.mcptoon/config.json) and writes
to each agent's native config format. This is the reverse of discover:
  - discover: read from agents → mcptoon config
  - sync:     write from mcptoon config → agents

Supported targets:
  - Claude Desktop (claude_desktop_config.json)
  - Cursor (.cursor/mcp.json)
  - Cline (.cline/mcp_config.json or VS Code settings)
  - Windsurf (.codeium/windsurf/mcp_config.json)
  - VS Code Copilot (settings.json → mcp.servers)
  - Codex (AGENTS.md — mentions mcptoon as the tool manager)

Usage:
    from mcptoon.sync import sync_to_all, sync_to_agent
    result = sync_to_all(dry_run=True)
    result = sync_to_agent("cursor", dry_run=False)
"""
import json
import os
import sys
from pathlib import Path

from .config import load_config


# ─── Path helpers (mirrors discover.py) ───

def _home() -> Path:
    """Get home directory, Windows-compatible."""
    return Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))


def _appdata() -> Path:
    """Get Windows AppData path, or fallback to home."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(_home() / "AppData" / "Roaming")))
    return _home()


# ─── Agent config file paths ───

def _claude_desktop_path() -> Path:
    """Claude Desktop config file path."""
    if sys.platform == "win32":
        return _appdata() / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        return _home() / ".config" / "Claude" / "claude_desktop_config.json"


def _cursor_path() -> list[Path]:
    """Cursor config file paths (global + project-level)."""
    return [
        _home() / ".cursor" / "mcp.json",
        Path.cwd() / ".cursor" / "mcp.json",
    ]


def _cline_path() -> Path:
    """Cline config file path (VS Code extension)."""
    # Cline stores in VS Code globalStorage on Windows
    if sys.platform == "win32":
        return _appdata() / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    else:
        return _home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"


def _windsurf_path() -> Path:
    """Windsurf config file path."""
    return _home() / ".codeium" / "windsurf" / "mcp_config.json"


def _vscode_copilot_path() -> Path:
    """VS Code Copilot settings.json path."""
    if sys.platform == "win32":
        return _appdata() / "Code" / "User" / "settings.json"
    elif sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    else:
        return _home() / ".config" / "Code" / "User" / "settings.json"


# ─── Config conversion ───

def _mcptoon_to_agent_format(server_name: str, server_cfg: dict) -> dict:
    """Convert mcptoon server config to agent-native format.

    Agent format (Claude Desktop / Cursor / Cline / Windsurf) is:
        {
            "command": "npx",
            "args": ["-y", "@mcp/server-fetch"],
            "env": {"KEY": "value"}
        }

    For HTTP servers:
        {
            "url": "http://localhost:8080/mcp",
            "headers": {"Authorization": "Bearer xxx"}
        }
    """
    transport = server_cfg.get("transport", "stdio")

    if transport == "http":
        result = {"url": server_cfg.get("url", "")}
        headers = server_cfg.get("headers")
        if headers:
            result["headers"] = headers
        return result

    # stdio
    command = server_cfg.get("command", [])
    args = server_cfg.get("args", [])
    env = server_cfg.get("env", {})

    # Flatten command+args into agent format
    if isinstance(command, list):
        if len(command) == 1:
            cmd_str = command[0]
            all_args = list(args)
        else:
            cmd_str = command[0] if command else ""
            all_args = list(command[1:]) + list(args)
    else:
        cmd_str = command
        all_args = list(args)

    result = {}
    if cmd_str:
        result["command"] = cmd_str
    if all_args:
        result["args"] = all_args
    if env:
        result["env"] = env
    # Agent Plugins (v0.7.1): plugins may pin a working directory; the
    # value is already an absolute expanded path set at install time.
    if server_cfg.get("cwd"):
        result["cwd"] = server_cfg["cwd"]

    return result


def _build_mcp_servers_dict(config: dict) -> dict:
    """Build {name: agent_format} from mcptoon config's servers."""
    servers = config.get("servers", {})
    if not servers:
        # Try flat format (server names at top level)
        servers = {k: v for k, v in config.items()
                   if isinstance(v, dict) and ("transport" in v or "command" in v or "url" in v)}

    result = {}
    for name, cfg in servers.items():
        agent_cfg = _mcptoon_to_agent_format(name, cfg)
        if agent_cfg:
            result[name] = agent_cfg
    return result


# Reserved name for the gateway's own entry. It cannot collide with a real MCP
# server in practice: `mcptoon` is this package, and a config that shadowed it
# would already be broken.
SELF_SERVER_NAME = "mcptoon"


def _self_serve_entry() -> dict:
    """The agent-format entry that puts `mcptoon serve` in an agent's config.

    Why this exists: `mcptoon serve` is the only surface where mcptoon speaks to
    the *model* (the MCP `instructions` field of the initialize handshake). But
    nothing ever wrote that entry into an agent's config — `sync` deliberately
    carried only the user's servers — so the gateway's voice was never heard on
    any machine. Registering it is what turns "installed silently" into "the
    agent knows mcptoon is here".

    Uses `sys.executable -m mcptoon` rather than a bare `mcptoon`, because an
    agent process may launch with a PATH that lacks the user Scripts dir; the
    interpreter running this code always exists.
    """
    return {"command": sys.executable, "args": ["-m", "mcptoon", "serve"]}


def _merge_self_entry(mcp_servers: dict) -> dict:
    """Add the gateway's own `serve` entry (never clobbering a user server)."""
    merged = dict(mcp_servers)
    merged.setdefault(SELF_SERVER_NAME, _self_serve_entry())
    return merged


# ─── Removing the gateway (the undo side of `sync --self`) ───
# A tool the user cannot switch off is indistinguishable from one that never
# asked. `mcptoon off` and `mcptoon uninstall` are the answers to "how do I get
# rid of this?" — they remove ONLY the gateway entry, leaving every other server
# in the user's config untouched.

def _agent_config_path(agent_id: str) -> Path | None:
    """The config file a given agent id writes to (None when unknown)."""
    if agent_id == "claude-desktop":
        return _claude_desktop_path()
    if agent_id == "cursor":
        return _cursor_path()[0]
    if agent_id == "cline":
        return _cline_path()
    if agent_id == "windsurf":
        return _windsurf_path()
    if agent_id == "vscode-copilot":
        return _vscode_copilot_path()
    return None


def _servers_section(data: dict, agent_id: str) -> dict:
    """The mcpServers-shaped mapping inside an agent's config (read-only view).

    Cursor/Claude/Cline/Windsurf keep servers at ``mcpServers``; VS Code keeps
    them at ``mcp.servers`` inside its shared settings.json.
    """
    if agent_id == "vscode-copilot":
        return (data.get("mcp") or {}).get("servers", {}) or {}
    return data.get("mcpServers", {}) or {}


def gateway_present_in(agent_id: str) -> bool:
    """True if the gateway entry exists in this agent's config (read-only)."""
    path = _agent_config_path(agent_id)
    if path is None or not path.exists():
        return False
    section = _servers_section(_read_json_safe(path), agent_id)
    return isinstance(section, dict) and SELF_SERVER_NAME in section


def remove_gateway_from_agent(agent_id: str, dry_run: bool = False,
                              path: Path | None = None) -> dict:
    """Remove ONLY the gateway entry from an agent's config, servers left intact.

    The inverse of `sync --self`. Returns a sync-shaped result; ``removed`` is
    True when the entry was actually there (so callers can report a real count).

    ``path`` overrides the file to edit. It exists because an agent id does not
    always map to one file: Cursor keeps a project-level `.cursor/mcp.json` next to
    its global one, and `_agent_config_path("cursor")` only ever names the global
    file — so without an override the project-level copy silently kept the gateway
    entry that `mcptoon off` had just claimed to remove.
    """
    target = path if path is not None else _agent_config_path(agent_id)
    if target is None:
        return {"agent": agent_id, "path": "", "removed": False, "written": False,
                "error": f"Unknown agent: {agent_id}"}
    path = target
    if not path.exists():
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    data = _read_json_safe(path)
    if not data:
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    if agent_id == "vscode-copilot":
        section = (data.get("mcp") or {}).get("servers")
    else:
        section = data.get("mcpServers")
    if not isinstance(section, dict) or SELF_SERVER_NAME not in section:
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    section.pop(SELF_SERVER_NAME, None)
    if dry_run:
        return {"agent": agent_id, "path": str(path), "removed": True,
                "written": False, "error": None}
    ok = _write_json_safe(path, data)
    return {"agent": agent_id, "path": str(path), "removed": True, "written": ok,
            "error": None if ok else "Write failed"}


def remove_gateway_from_all(dry_run: bool = False) -> list[dict]:
    """Remove the gateway entry from every detected agent's config file.

    De-duplicated by the *resolved* file, not by the reported path: Cursor lists a
    global and a project-level config, and on some setups those are the same file.
    Keying on the reported string missed that (so the same file was processed twice
    and "6 agents" was reported for five files), while keying on the resolved path
    also lets the project-level file be cleaned at all.
    """
    agents = detect_installed_agents()
    results = []
    seen_paths = set()
    for agent in agents:
        target = Path(agent["config_path"])
        try:
            key = str(target.resolve()).lower()
        except OSError:  # unreachable drive, malformed path
            key = str(target).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        r = remove_gateway_from_agent(agent["id"], dry_run=dry_run, path=target)
        r["agent_name"] = agent["name"]
        r["config_exists"] = agent["exists"]
        results.append(r)
    return results


# ─── Detection (which agents are installed) ───

def detect_installed_agents() -> list[dict]:
    """Detect which AI agents are installed on this machine.

    Returns list of {id, name, config_path, exists}.
    """
    agents = []

    # Claude Desktop
    path = _claude_desktop_path()
    agents.append({
        "id": "claude-desktop",
        "name": "Claude Desktop",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    # Cursor
    for p in _cursor_path():
        agents.append({
            "id": "cursor",
            "name": f"Cursor ({'project' if p == _cursor_path()[-1] else 'global'})",
            "config_path": str(p),
            "exists": p.parent.exists() or p.exists(),
        })

    # Cline
    path = _cline_path()
    agents.append({
        "id": "cline",
        "name": "Cline",
        "config_path": str(path),
        "exists": path.parent.parent.parent.parent.exists() if path.parts else False,
    })

    # Windsurf
    path = _windsurf_path()
    agents.append({
        "id": "windsurf",
        "name": "Windsurf",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    # VS Code Copilot
    path = _vscode_copilot_path()
    agents.append({
        "id": "vscode-copilot",
        "name": "VS Code Copilot",
        "config_path": str(path),
        "exists": path.parent.exists(),
    })

    return agents


# ─── Sync functions ───

def _read_json_safe(path: Path) -> dict:
    """Read JSON file, return empty dict on error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_safe(path: Path, data: dict) -> bool:
    """Write JSON file, creating parent dirs. Returns True on success.

    Writing into someone's agent config is destructive, so a first `.bak` copy is
    taken *only when the content actually changes* — that keeps the backup
    meaningful (it is the pre-mcptoon state) instead of littering one file per
    routine sync, and it means the very first `sync` that adds the gateway leaves
    a one-command undo: copy `<config>.bak` back, or delete the `mcptoon` entry.
    A failed backup does not block the write; the write is what the user asked for.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_text = json.dumps(data, indent=2, ensure_ascii=False)
        if path.exists():
            try:
                old_text = path.read_text(encoding="utf-8")
            except OSError:
                old_text = None
            if old_text is not None and old_text != new_text:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():  # never overwrite an existing backup
                    try:
                        bak.write_text(old_text, encoding="utf-8")
                    except OSError:
                        pass
        path.write_text(new_text, encoding="utf-8")
        return True
    except OSError:
        return False


def _merge_mcp_servers(existing: dict, new_servers: dict) -> dict:
    """Merge new servers into existing config's mcpServers.

    Preserves existing servers not in mcptoon, updates existing ones
    that are in mcptoon, and adds new ones.
    """
    result = dict(existing)
    current_servers = dict(result.get("mcpServers", {}))
    current_servers.update(new_servers)
    result["mcpServers"] = current_servers
    return result


def sync_to_agent(agent_id: str, dry_run: bool = False, config: dict | None = None,
                  include_self: bool = False) -> dict:
    """Sync mcptoon config to a specific agent.

    Args:
        agent_id: One of 'claude-desktop', 'cursor', 'cline', 'windsurf', 'vscode-copilot', 'codex'
        dry_run: If True, return what would be written without writing
        config: Override config (for testing). If None, loads from default.
        include_self: Also register `mcptoon serve` (the gateway's own entry) so
            the agent can see mcptoon itself, not just the servers it manages.

    Returns:
        {
            "agent": agent_id,
            "path": str,
            "servers_synced": int,
            "written": bool,
            "error": str | None,
        }
    """
    if config is None:
        config = load_config()

    mcp_servers = _build_mcp_servers_dict(config)

    if not mcp_servers:
        return {
            "agent": agent_id,
            "path": "",
            "servers_synced": 0,
            "written": False,
            "error": "No servers in mcptoon config. Run: mcptoon add <name> ...",
        }

    if include_self:
        mcp_servers = _merge_self_entry(mcp_servers)

    # Determine config file path and write logic
    if agent_id == "claude-desktop":
        path = _claude_desktop_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "cursor":
        # Write to global cursor config
        path = _cursor_path()[0]
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "cline":
        path = _cline_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "windsurf":
        path = _windsurf_path()
        existing = _read_json_safe(path)
        merged = _merge_mcp_servers(existing, mcp_servers)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "vscode-copilot":
        path = _vscode_copilot_path()
        existing = _read_json_safe(path)
        # VS Code stores MCP servers under "mcp.servers" in settings.json.
        # The user's settings.json is a large shared file, so this one is edited
        # in place rather than rewritten: a full re-serialisation would reorder
        # keys and reformat comments. An existing backup is left untouched.
        mcp_section = existing.get("mcp", {})
        current_servers = dict(mcp_section.get("servers", {}))
        current_servers.update(mcp_servers)
        mcp_section["servers"] = current_servers
        existing["mcp"] = mcp_section
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        ok = _write_json_safe(path, existing)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "codex":
        # Codex uses AGENTS.md — append a note about mcptoon
        path = Path.cwd() / "AGENTS.md"
        content = "\n## MCP Tools\n\nThis project uses [mcptoon](https://github.com/activeing123/mcptoon) for MCP tool management.\nRun `mcptoon manifest --compact` to see available tools.\n\n"
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": False, "error": None}
        try:
            existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
            if "mcptoon" not in existing_content:
                path.write_text(existing_content + content, encoding="utf-8")
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers), "written": True, "error": None}
        except OSError as e:
            return {"agent": agent_id, "path": str(path), "servers_synced": 0, "written": False, "error": str(e)}

    else:
        return {"agent": agent_id, "path": "", "servers_synced": 0, "written": False, "error": f"Unknown agent: {agent_id}"}


def sync_to_all(dry_run: bool = False, config: dict | None = None,
                include_self: bool = False) -> list[dict]:
    """Sync mcptoon config to all installed agents.

    Args:
        dry_run: If True, preview without writing
        config: Override config (for testing)
        include_self: Also register `mcptoon serve` in each agent (see sync_to_agent).

    Returns:
        List of sync results, one per *config file written*.
    """
    agents = detect_installed_agents()
    results = []
    seen_paths = set()
    for agent in agents:
        # Dedupe on the file `sync_to_agent` will actually write, not on the path the
        # agent row reports. Cursor lists a global and a project-level config, but
        # sync only ever writes the global one — so the project row used to produce a
        # second "✓ 13 servers" line for the same file, and "6 agents / 78 servers"
        # counted a write that never happened. Keying on the real target also keeps
        # sync off the project-level path entirely, which is deliberate: writing a
        # `.cursor/mcp.json` into whatever directory the user happens to be in is
        # exactly the kind of unasked-for side effect this command should not have.
        target = _agent_config_path(agent["id"])
        if target is None:
            key = f"id:{agent['id']}"
        else:
            try:
                key = str(target.resolve()).lower()
            except OSError:  # unreachable drive, malformed path
                key = str(target).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        result = sync_to_agent(agent["id"], dry_run=dry_run, config=config,
                               include_self=include_self)
        result["agent_name"] = agent["name"]
        result["config_exists"] = agent["exists"]
        results.append(result)
    return results


def format_sync_report(results: list[dict], dry_run: bool = False) -> str:
    """Format sync results as human-readable report."""
    mode = "DRY RUN (preview)" if dry_run else "SYNC COMPLETE"
    lines = [f"── mcptoon sync: {mode} ──", ""]

    written_count = sum(1 for r in results if r.get("written"))
    total_servers = sum(r.get("servers_synced", 0) for r in results)
    error_count = sum(1 for r in results if r.get("error"))

    for r in results:
        icon = "✓" if r.get("written") else ("→" if dry_run and r.get("servers_synced", 0) > 0 else "·")
        name = r.get("agent_name", r.get("agent", ""))
        count = r.get("servers_synced", 0)
        path = r.get("path", "")
        err = r.get("error", "")

        if count > 0:
            lines.append(f"  {icon} {name:25s} {count:3d} servers  {path}")
        elif err:
            lines.append(f"  ! {name:25s} skip ({err})")
        else:
            lines.append(f"  · {name:25s} not installed")

    lines.append("")
    if dry_run:
        lines.append(f"  Preview: {written_count + sum(1 for r in results if r.get('servers_synced', 0) > 0)} agents would be updated, {total_servers} servers total")
    else:
        lines.append(f"  Done: {written_count} agents updated, {total_servers} servers synced, {error_count} errors")

    return "\n".join(lines)
