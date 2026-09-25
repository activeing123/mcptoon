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

def _claude_code_path() -> Path:
    """Claude Code's user config. Same shape as the others (`mcpServers`), but the
    file is `.claude.json` in the home dir, not a dotted config folder."""
    return _home() / ".claude.json"


def _codex_agents_path() -> Path:
    """Codex's global instruction file.

    Global, not `Path.cwd()`: the old writer appended to whatever directory the
    user happened to run `sync` from, so the pointer landed in a random project's
    AGENTS.md — or nowhere, if that directory was not a project. Codex reads
    `$HOME/.codex/AGENTS.md` on every session, which is where a machine-wide
    pointer belongs.
    """
    return _home() / ".codex" / "AGENTS.md"


def _claude_code_memory_path() -> Path:
    """Claude Code's global memory file.

    `~/.claude/CLAUDE.md` is what Claude Code loads as machine-wide context on
    every session — its own state keys in `~/.claude.json` (e.g.
    `hasClaudeMdExternalIncludesApproved`) are about exactly this file's handling.
    That is what makes it a valid CLI-leg channel: a pointer nobody reads
    unprompted is not a channel at all.
    """
    return _home() / ".claude" / "CLAUDE.md"


# Hosts whose agent reads a machine-wide instruction file every session: the hosts
# the CLI leg can actually reach (CONTEXT.md: Two Legs Always On). Every other host
# reaches mcptoon through MCP alone.
#
# The list is short and evidence-based rather than aspirational:
# * `codex` — AGENTS.md is Codex's documented channel, and mcptoon already used it.
# * `claude-code` — CLAUDE.md, evidenced by Claude Code's own config state.
# * Cursor is NOT here on purpose. `~/.cursorrules` exists on some machines but is
#   the legacy form (current Cursor uses `.cursor/rules`), so writing there risks a
#   pointer into a file the host no longer reads — a silent no-op, which is worse
#   than not writing at all.
# * Windsurf, Cline and VS Code Copilot expose no dedicated global instruction file
#   (Cline's instructions live inside the shared VS Code settings JSON), so they
#   stay MCP-only rather than risk editing a file the user shares with everything
#   else on the machine.
#
# `pointer_path` dispatches by name rather than holding a table of function objects:
# that table would capture the *original* functions at import time, so a test (or a
# future refactor) patching `_claude_code_memory_path` would silently keep writing
# to the real home directory. This repo has already been bitten once by a pointer
# landing somewhere unexpected — see the note on `_codex_agents_path`.
_SKILL_POINTER_HOSTS = ("codex", "claude-code")


def pointer_path(agent_id: str) -> Path | None:
    """The instruction file `agent_id` reads every session, if it has one."""
    if agent_id == "codex":
        return _codex_agents_path()
    if agent_id == "claude-code":
        return _claude_code_memory_path()
    return None


def _write_skill_pointer(path: Path) -> dict:
    """Append the skill-pointer block to a host's global instruction file.

    Idempotent and byte-reversible: the block is anchored on its heading and cut at
    the next ``## `` heading by `_strip_skill_pointer`, so the user's own content
    above and below survives unchanged and `mcptoon off` puts the file back as it
    found it. Returns ``{"path", "written", "error"}``.
    """
    try:
        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as e:
        return {"path": str(path), "written": False, "error": str(e)}
    if _SKILL_POINTER_HEADING in existing_content:
        return {"path": str(path), "written": False, "error": None}  # already there
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Always a blank line before the heading, so the pointer reads as its own
        # section instead of being glued to the user's last paragraph.
        if not existing_content or existing_content.endswith("\n\n"):
            sep = ""
        elif existing_content.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        path.write_text(existing_content + sep + _SKILL_POINTER_BLOCK,
                        encoding="utf-8")
        return {"path": str(path), "written": True, "error": None}
    except OSError as e:
        return {"path": str(path), "written": False, "error": str(e)}


def _remove_skill_pointer(path: Path) -> dict:
    """Remove exactly the block `_write_skill_pointer` inserted, nothing else."""
    if not path.exists():
        return {"path": str(path), "removed": False, "written": False, "error": None}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"path": str(path), "removed": False, "written": False, "error": None}
    if _SKILL_POINTER_HEADING not in text:
        return {"path": str(path), "removed": False, "written": False, "error": None}
    try:
        path.write_text(_strip_skill_pointer(text), encoding="utf-8")
    except OSError as e:
        return {"path": str(path), "removed": True, "written": False, "error": str(e)}
    return {"path": str(path), "removed": True, "written": True, "error": None}


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

# The skill pointer written into a CLI-only host's global instruction file. Codex
# (and DSH) mount no MCP, so the handshake `instructions` channel never reaches
# them; a line in the file they already read on every session is the only way the
# catalog becomes discoverable. Kept to one heading + a few lines so it is cheap
# to carry on every turn, and heading-anchored so the write is idempotent.
_SKILL_POINTER_HEADING = "## Skill catalog (mcptoon)"
_SKILL_POINTER_BLOCK = f"""{_SKILL_POINTER_HEADING}

This machine has a skill catalog managed by mcptoon. Before acting on a task,
find the right skill first — do not guess, and do not read the whole catalog:

    mcptoon skills resolve "<the user request>" --k 5

Read only the SKILL.md files it returns. If it finds nothing, rephrase and try
again, or run `mcptoon skills list` to pick a name by eye. Tools live behind the
same gateway: `mcptoon manifest` lists them.
"""


def _strip_skill_pointer(text: str) -> str:
    """Remove exactly the block `_SKILL_POINTER_BLOCK` inserted, nothing else.

    Anchored on the heading and cut at the next ``## `` heading, so a user's own
    content above and below the block survives byte-for-byte. Used by the undo
    path (`mcptoon off`), which must leave the file as it found it.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        if not skipping and line.strip() == _SKILL_POINTER_HEADING:
            skipping = True
            # drop the blank line the writer put before the heading, if present
            while out and out[-1].strip() == "":
                out.pop()
            continue
        if skipping:
            if line.startswith("## "):
                skipping = False
            else:
                continue
        out.append(line)
    return "".join(out).rstrip("\n") + ("\n" if text.endswith("\n") else "")


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
    if agent_id == "claude-code":
        return _claude_code_path()
    if agent_id == "codex":
        return _codex_agents_path()
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
    """True if the gateway entry exists in this agent's config (read-only).

    Codex has no JSON config; "present" there means the skill pointer is in its
    AGENTS.md, which is the thing `sync --self` writes for it.
    """
    path = _agent_config_path(agent_id)
    if path is None or not path.exists():
        return False
    if agent_id == "codex":
        try:
            return _SKILL_POINTER_HEADING in path.read_text(encoding="utf-8")
        except OSError:
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

    # Codex: the undo is removing the skill-pointer block, not a JSON key. Kept
    # to exactly the block `sync --self` wrote, so nothing else in the file moves.
    if agent_id == "codex":
        if dry_run:
            if path.exists() and _SKILL_POINTER_HEADING in path.read_text(encoding="utf-8"):
                return {"agent": agent_id, "path": str(path), "removed": True,
                        "written": False, "error": None}
            return {"agent": agent_id, "path": str(path), "removed": False,
                    "written": False, "error": None}
        out = _remove_skill_pointer(path)
        return {"agent": agent_id, "path": out["path"], "removed": out["removed"],
                "written": out["written"], "error": out["error"]}

    data = _read_json_safe(path)
    if not data:
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    if agent_id == "vscode-copilot":
        section = (data.get("mcp") or {}).get("servers")
    else:
        section = data.get("mcpServers")
    has_gateway = isinstance(section, dict) and SELF_SERVER_NAME in section

    # A host can carry both legs, so `off` has to undo both or it leaves a pointer
    # telling an agent to use a catalog that is no longer mounted. Claude Code is
    # the case that exists today: an entry in `~/.claude.json` and a block in
    # `~/.claude/CLAUDE.md`. Codex is handled above because it has no JSON entry.
    ppath = pointer_path(agent_id)
    pointer_removed = False
    if ppath is not None and ppath.exists():
        try:
            pointer_removed = _SKILL_POINTER_HEADING in ppath.read_text(encoding="utf-8")
        except OSError:
            pointer_removed = False

    if not has_gateway and not pointer_removed:
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    if dry_run:
        return {"agent": agent_id, "path": str(path), "removed": True,
                "written": False, "error": None,
                "pointer_removed": pointer_removed}

    ok = True
    if has_gateway:
        section.pop(SELF_SERVER_NAME, None)
        ok = _write_json_safe(path, data)
    if pointer_removed and ppath is not None:
        _remove_skill_pointer(ppath)
    return {"agent": agent_id, "path": str(path), "removed": True, "written": ok,
            "error": None if ok else "Write failed",
            "pointer_removed": pointer_removed}


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

    # Claude Code — detected by the config file itself, since the binary may be
    # on PATH without any dotted folder existing yet. A machine that runs
    # `claude` has `.claude.json`; the file is the evidence.
    path = _claude_code_path()
    if path.exists():
        agents.append({
            "id": "claude-code",
            "name": "Claude Code",
            "config_path": str(path),
            "exists": True,
        })

    # Codex — the global instruction file, so a machine-wide pointer is possible.
    # Only when the file already exists: creating `~/.codex/AGENTS.md` out of
    # nothing would be an unasked-for write into a home the user may not use for
    # Codex at all.
    path = _codex_agents_path()
    if path.exists():
        agents.append({
            "id": "codex",
            "name": "Codex (AGENTS.md)",
            "config_path": str(path),
            "exists": True,
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


def _drop_managed_servers(section: dict, new_servers: dict) -> list[str]:
    """Takeover helper: remove the host entries mcptoon now serves itself.

    Only servers mcptoon manages (i.e. present in ``new_servers``) are dropped.
    A host-only server mcptoon does not know about is left alone — the gateway
    cannot serve it, so removing it would silently lose a tool the user still
    has. Returns the names removed, so a caller can report a real count.
    """
    managed = set(new_servers) - {SELF_SERVER_NAME}
    removed = [name for name in list(section) if name in managed]
    for name in removed:
        section.pop(name, None)
    return removed


def _merge_mcp_servers(existing: dict, new_servers: dict,
                       takeover: bool = False) -> dict:
    """Merge new servers into existing config's mcpServers.

    Default (``takeover=False``): preserves existing servers not in mcptoon,
    updates existing ones that are in mcptoon, and adds new ones. The gateway,
    when included, is added *alongside* the upstreams.

    ``takeover=True`` flips the default from "add the gateway alongside the
    upstreams" to "the gateway *is* the connection". Without it the host keeps
    every upstream server entry it already had and simply gains one more
    (``mcptoon``), so it still loads all the upstream tool schemas directly and
    the gateway saves nothing — it only adds a line. With it, each server
    mcptoon manages is removed from the host config and reached through the
    gateway instead (only the gateway entry is written, never the upstreams
    again), which is the only way the compressed schema actually reaches the
    host. Servers mcptoon does not manage are left alone. The pre-change file is
    preserved as ``<config>.bak`` by ``_write_json_safe``; that backup is the
    undo.
    """
    result = dict(existing)
    current_servers = dict(result.get("mcpServers", {}))
    if takeover:
        _drop_managed_servers(current_servers, new_servers)
        # Under takeover the gateway replaces the direct entries — re-adding the
        # managed servers here would undo the whole point. Only the gateway's own
        # entry is written back.
        if SELF_SERVER_NAME in new_servers:
            current_servers[SELF_SERVER_NAME] = new_servers[SELF_SERVER_NAME]
    else:
        current_servers.update(new_servers)
    result["mcpServers"] = current_servers
    return result


def takeover_plan(agent_id: str | None = None, config: dict | None = None) -> list[dict]:
    """Read-only preview of what `sync --takeover` would remove, per host.

    Write Consent (CONTEXT.md) splits mcptoon's config edits in two: the additions
    (writing our own entry, a pointer, a skill) may be silent, but the subtraction —
    takeover dropping server entries the user wrote into a host config — must be
    listed and confirmed once first. A wrong call there loses a tool for real.

    This computes exactly the names `_merge_mcp_servers(..., takeover=True)` would
    drop, without writing anything: only servers mcptoon manages (present in the
    config) are candidates, so a host-only server the gateway cannot serve is never
    listed. Returns one row per config file that actually has something to drop —
    an empty list means takeover would remove nothing and there is nothing to ask.

    ``agent_id`` limits the preview to one host; ``None`` walks every installed host,
    de-duplicated on the file that would really be written (the same rule
    ``sync_to_all`` uses, so Cursor's global/project rows do not double-count).
    """
    if config is None:
        config = load_config()
    managed = set(_build_mcp_servers_dict(config)) - {SELF_SERVER_NAME}
    if not managed:
        return []

    hosts = ([{"id": agent_id, "name": agent_id}] if agent_id is not None
             else detect_installed_agents())
    plan: list[dict] = []
    seen_paths: set[str] = set()
    for host in hosts:
        target = _agent_config_path(host["id"])
        if target is None or not target.exists():
            continue
        try:
            key = str(target.resolve()).lower()
        except OSError:  # unreachable drive, malformed path
            key = str(target).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        section = _servers_section(_read_json_safe(target), host["id"])
        servers = sorted(name for name in section if name in managed)
        if servers:
            plan.append({"agent": host["id"], "agent_name": host.get("name", host["id"]),
                         "path": str(target), "servers": servers})
    return plan


def sync_to_agent(agent_id: str, dry_run: bool = False, config: dict | None = None,
                  include_self: bool = False, takeover: bool = False) -> dict:
    """Sync mcptoon config to a specific agent.

    Args:
        agent_id: One of 'claude-desktop', 'cursor', 'cline', 'windsurf', 'vscode-copilot', 'codex'
        dry_run: If True, return what would be written without writing
        config: Override config (for testing). If None, loads from default.
        include_self: Also register `mcptoon serve` (the gateway's own entry) so
            the agent can see mcptoon itself, not just the servers it manages.
        takeover: Remove the upstream server entries mcptoon manages and route
            them through the gateway, instead of adding the gateway alongside
            them. Without this the host keeps loading every upstream schema
            directly and the gateway saves nothing; see `_merge_mcp_servers`.

    Returns:
        {
            "agent": agent_id,
            "path": str,
            "servers_synced": int,
            "taken_over": int,   # upstream entries the gateway replaced
            "written": bool,
            "error": str | None,
        }
    """
    if config is None:
        config = load_config()

    # Takeover only makes sense with the gateway present — dropping the direct
    # entries without writing the one that replaces them would leave the host with
    # nothing. Coupling them here means an API caller cannot ask for the footgun.
    if takeover:
        include_self = True

    mcp_servers = _build_mcp_servers_dict(config)

    if not mcp_servers and agent_id != "codex":
        # Codex writes a skill pointer, not a server list, so an empty config is
        # not a reason to skip it — that is exactly the first-run case where the
        # pointer matters most.
        return {
            "agent": agent_id,
            "path": "",
            "servers_synced": 0,
            "taken_over": 0,
            "written": False,
            "error": "No servers in mcptoon config. Run: mcptoon add <name> ...",
        }

    if include_self:
        mcp_servers = _merge_self_entry(mcp_servers)

    # Every JSON-config host stores servers at `mcpServers` (VS Code at
    # `mcp.servers`) and differs only in *which file* — so one branch drives them
    # all. `_merge_mcp_servers` already knows how to update, add, and (under
    # takeover) drop entries; the old per-agent copies of that logic had drifted.
    _path_fns = {
        "claude-desktop": _claude_desktop_path,
        "cursor": lambda: _cursor_path()[0],
        "claude-code": _claude_code_path,
        "cline": _cline_path,
        "windsurf": _windsurf_path,
    }

    if agent_id in _path_fns:
        path = _path_fns[agent_id]()
        existing = _read_json_safe(path)
        before = set((existing.get("mcpServers") or {}).keys())
        merged = _merge_mcp_servers(existing, mcp_servers, takeover=takeover)
        taken_over = len(before - set((merged.get("mcpServers") or {}).keys()))
        # The MCP leg and the CLI leg are independent, and this host can carry
        # both: Claude Code reads `~/.claude/CLAUDE.md` every session, so it can be
        # told about the catalog in words as well as handed a gateway to mount.
        # Non-destructive and idempotent, so a routine `sync --self` is safe.
        pointer = None
        ppath = pointer_path(agent_id)
        if include_self and ppath is not None:
            if dry_run:
                pointer = {"path": str(ppath), "written": False, "error": None,
                           "would_write": True}
            else:
                pointer = _write_skill_pointer(ppath)
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers),
                    "taken_over": taken_over, "written": False, "error": None,
                    "pointer": pointer}
        ok = _write_json_safe(path, merged)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers),
                "taken_over": taken_over, "written": ok,
                "error": None if ok else "Write failed", "pointer": pointer}

    elif agent_id == "vscode-copilot":
        path = _vscode_copilot_path()
        existing = _read_json_safe(path)
        # VS Code stores MCP servers under "mcp.servers" in settings.json.
        # The user's settings.json is a large shared file, so this one is edited
        # in place rather than rewritten: a full re-serialisation would reorder
        # keys and reformat comments. An existing backup is left untouched.
        mcp_section = existing.get("mcp", {})
        current_servers = dict(mcp_section.get("servers", {}))
        before = set(current_servers)
        if takeover:
            _drop_managed_servers(current_servers, mcp_servers)
            if SELF_SERVER_NAME in mcp_servers:
                current_servers[SELF_SERVER_NAME] = mcp_servers[SELF_SERVER_NAME]
        else:
            current_servers.update(mcp_servers)
        taken_over = len(before - set(current_servers))
        mcp_section["servers"] = current_servers
        existing["mcp"] = mcp_section
        if dry_run:
            return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers),
                    "taken_over": taken_over, "written": False, "error": None}
        ok = _write_json_safe(path, existing)
        return {"agent": agent_id, "path": str(path), "servers_synced": len(mcp_servers),
                "taken_over": taken_over, "written": ok, "error": None if ok else "Write failed"}

    elif agent_id == "codex":
        # Codex has no MCP mount; its agent context comes from AGENTS.md. So this
        # branch does not sync *servers* — it writes the skill pointer, which is
        # the only thing that makes a CLI-only host able to find a skill at all.
        #
        # Three things the old writer got wrong: it targeted `Path.cwd()` (the
        # pointer landed in a random project, or nowhere), its text named only
        # `mcptoon manifest` and never the catalog, and it fired on every `sync`
        # rather than behind `--self`. Now: global path, skill pointer included,
        # and written only when `include_self` is set — the same opt-in the MCP
        # gateway registration uses, because both are "let this host see mcptoon".
        path = _codex_agents_path()
        if not include_self:
            return {"agent": agent_id, "path": str(path), "servers_synced": 0,
                    "taken_over": 0, "written": False, "error": None}
        if dry_run:
            # Report the pointer honestly in a preview: Codex's whole delivery *is*
            # the pointer, so "nothing to write" would be a lie about the one host
            # this branch exists for.
            try:
                already = (path.exists() and
                           _SKILL_POINTER_HEADING in path.read_text(encoding="utf-8"))
            except OSError:
                already = False
            return {"agent": agent_id, "path": str(path), "servers_synced": 0,
                    "taken_over": 0, "written": False, "error": None,
                    "pointer": {"path": str(path), "written": False,
                                "would_write": not already, "error": None}}
        pointer = _write_skill_pointer(path)
        return {"agent": agent_id, "path": str(path), "servers_synced": 0,
                "taken_over": 0, "written": pointer["written"],
                "error": pointer["error"], "pointer": pointer}

    else:
        return {"agent": agent_id, "path": "", "servers_synced": 0, "taken_over": 0,
                "written": False, "error": f"Unknown agent: {agent_id}"}


def sync_to_all(dry_run: bool = False, config: dict | None = None,
                include_self: bool = False, takeover: bool = False) -> list[dict]:
    """Sync mcptoon config to all installed agents.

    Args:
        dry_run: If True, preview without writing
        config: Override config (for testing)
        include_self: Also register `mcptoon serve` in each agent (see sync_to_agent).
        takeover: Route each managed server through the gateway instead of
            leaving the host connected to it directly (see sync_to_agent).

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
                               include_self=include_self, takeover=takeover)
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
    pointer_count = sum(1 for r in results
                        if (r.get("pointer") or {}).get("written")
                        or (r.get("pointer") or {}).get("would_write"))

    for r in results:
        icon = "✓" if r.get("written") else ("→" if dry_run and r.get("servers_synced", 0) > 0 else "·")
        name = r.get("agent_name", r.get("agent", ""))
        count = r.get("servers_synced", 0)
        path = r.get("path", "")
        err = r.get("error", "")
        pointer = r.get("pointer") or {}

        if count > 0:
            # Under takeover the host no longer loads the upstream servers
            # directly; naming that count is the difference between "added one
            # more server" and "replaced N servers with the gateway".
            taken = r.get("taken_over", 0)
            extra = f"  (−{taken} direct, now via gateway)" if taken else ""
            lines.append(f"  {icon} {name:25s} {count:3d} servers  {path}{extra}")
            if pointer.get("written") or pointer.get("would_write"):
                # Both legs on one host: the mount above, plus a pointer in the
                # file this agent reads every session.
                lines.append(f"      + skill pointer  {pointer.get('path', '')}")
        elif pointer.get("written") or pointer.get("would_write"):
            # Codex: no MCP mount at all, the pointer is the whole delivery.
            lines.append(f"  {icon} {name:25s} skill pointer  {pointer.get('path', '')}")
        elif err:
            lines.append(f"  ! {name:25s} skip ({err})")
        elif r.get("config_exists") is False:
            lines.append(f"  · {name:25s} not installed")
        elif path:
            # Found the host, but nothing to write (codex's pointer is opt-in via
            # --self, or a dry run). Saying "not installed" here was wrong and
            # confusing: the host *is* installed, we simply did not touch it.
            lines.append(f"  · {name:25s} found, nothing to write  {path}")
        else:
            lines.append(f"  · {name:25s} not installed")

    lines.append("")
    suffix = f", {pointer_count} skill pointer(s)" if pointer_count else ""
    if dry_run:
        lines.append(f"  Preview: {written_count + sum(1 for r in results if r.get('servers_synced', 0) > 0)} agents would be updated, {total_servers} servers total{suffix}")
    else:
        lines.append(f"  Done: {written_count} agents updated, {total_servers} servers synced, {error_count} errors{suffix}")

    return "\n".join(lines)
