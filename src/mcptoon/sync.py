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
  - Codex, Claude Code, Gemini CLI, Qwen Code, Zed, Crush, opencode
    (no MCP mount: a skill pointer in the instruction file each reads every
     session — see `_AGENT_SPECS`)

Usage:
    from mcptoon.sync import sync_to_all, sync_to_agent
    result = sync_to_all(dry_run=True)
    result = sync_to_agent("cursor", dry_run=False)
"""
import json
import os
import sys
from pathlib import Path
from typing import NamedTuple

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


def _config_dir() -> Path:
    """The XDG-style config root: `$XDG_CONFIG_HOME`, else `~/.config`.

    Used by the hosts that follow the XDG Base Directory spec (Crush, opencode,
    Zed on Linux). Honouring `XDG_CONFIG_HOME` is not optional: a user who moved
    it gets their pointer written to a directory the host never reads — the
    silent no-op this module keeps having to guard against.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return _home() / ".config"


# ─── The agent table (one row per supported host) ───
#
# Every supported host is one row here instead of one `if agent_id == ...` per
# call site. The old shape hardcoded the same id in up to ten places (vscode-copilot
# nine times, codex ten), so adding a host meant finding all of them; a row is now
# the whole definition, and the dispatchers below read it.
#
# `path_fn`/`pointer_fn` are **function names, not function objects**, on purpose:
# a table built at import time would capture the original functions, so a test that
# patches `_claude_code_path` would silently keep writing to the real home directory.
# `_resolve` looks the name up at call time so patching keeps working.

class _AgentSpec(NamedTuple):
    """One supported host. See `_AGENT_SPECS` for the rows."""

    id: str
    name: str
    path_fn: str                  # module-level fn returning its config Path
    shape: str = "mcpServers"     # how servers are stored: mcpServers | mcp.servers | pointer
    detected_by: str = "parent"   # which path proves it is installed (see _detect_exists)
    multi: bool = False           # path_fn returns a list of paths, not one
    only_when_present: bool = False  # hidden entirely when not installed (no exists:False row)
    pointer_fn: str | None = None  # fn returning its per-session instruction file, if it has one

    @property
    def mcp(self) -> bool:
        """True when this host carries MCP servers (False for CLI-only hosts)."""
        return self.shape != "pointer"


_AGENT_SPECS: tuple[_AgentSpec, ...] = (
    _AgentSpec("claude-desktop", "Claude Desktop", "_claude_desktop_path"),
    _AgentSpec("cursor", "Cursor", "_cursor_path", multi=True,
               detected_by="parent_or_file"),
    _AgentSpec("cline", "Cline", "_cline_path", detected_by="grandparent"),
    _AgentSpec("windsurf", "Windsurf", "_windsurf_path"),
    _AgentSpec("vscode-copilot", "VS Code Copilot", "_vscode_copilot_path",
               shape="mcp.servers"),
    _AgentSpec("claude-code", "Claude Code", "_claude_code_path",
               detected_by="file", only_when_present=True,
               pointer_fn="_claude_code_memory_path"),
    _AgentSpec("codex", "Codex (AGENTS.md)", "_codex_agents_path",
               shape="pointer", detected_by="file", only_when_present=True,
               pointer_fn="_codex_agents_path"),
    # CLI-leg hosts: no MCP mount at all. Each reads one machine-wide instruction
    # file on every session, so a pointer there is the whole delivery. Paths are
    # vendor-doc-confirmed, not guessed — a pointer into a file the host never
    # reads is a silent no-op (see the note above `pointer_path`). `detected_by`
    # is `parent` because the config *directory* existing proves the host has run
    # on this machine, while the instruction file itself is what we create.
    _AgentSpec("gemini", "Gemini CLI", "_gemini_path",
               shape="pointer", detected_by="parent", only_when_present=True,
               pointer_fn="_gemini_path"),
    _AgentSpec("qwen", "Qwen Code", "_qwen_path",
               shape="pointer", detected_by="parent", only_when_present=True,
               pointer_fn="_qwen_path"),
    _AgentSpec("zed", "Zed", "_zed_path",
               shape="pointer", detected_by="parent", only_when_present=True,
               pointer_fn="_zed_path"),
    _AgentSpec("crush", "Crush", "_crush_path",
               shape="pointer", detected_by="parent", only_when_present=True,
               pointer_fn="_crush_path"),
    _AgentSpec("opencode", "opencode", "_opencode_path",
               shape="pointer", detected_by="parent", only_when_present=True,
               pointer_fn="_opencode_path"),
)

_AGENT_SPEC_BY_ID: dict[str, _AgentSpec] = {spec.id: spec for spec in _AGENT_SPECS}


def _resolve(fn_name: str):
    """Look a table-named function up at call time (so tests can patch it)."""
    return globals()[fn_name]


def _detect_exists(path: Path, how: str) -> bool:
    """Does `path` prove its host is installed? One rule per `detected_by` value."""
    if how == "file":
        return path.exists()
    if how == "parent_or_file":
        return path.parent.exists() or path.exists()
    if how == "grandparent":
        return path.parent.parent.exists() if path.parts else False
    return path.parent.exists()  # "parent"


def _shape_of(agent_id: str) -> str:
    """The config shape for an id, defaulting to the common `mcpServers` one."""
    spec = _AGENT_SPEC_BY_ID.get(agent_id)
    return spec.shape if spec is not None else "mcpServers"


def _paths_for(agent_id: str) -> list[Path]:
    """Every config path a host reads (Cursor has a global and a project one)."""
    spec = _AGENT_SPEC_BY_ID[agent_id]
    out = _resolve(spec.path_fn)()
    return list(out) if spec.multi else [out]


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


# ─── The CLI-leg hosts' instruction files ───
#
# Each of these hosts loads one machine-wide file on every session, so the skill
# pointer is the whole delivery. Every path below is taken verbatim from the
# vendor's own documentation (not inferred from the tool's name), because writing
# a pointer into a file the host does not read produces no error and no effect.
# The vendor and the doc each came from are named in the docstring.

def _gemini_path() -> Path:
    """Gemini CLI's global context file.

    `docs/cli/gemini-md.md`: "Global context file ... `~/.gemini/GEMINI.md` (in
    your user home directory). Scope: provides default instructions for all your
    projects." `GEMINI_DIR` is the constant `.gemini` in `utils/paths.ts`.
    """
    return _home() / ".gemini" / "GEMINI.md"


def _qwen_path() -> Path:
    """Qwen Code's global context file.

    `docs/users/features/memory.md` lists `~/.qwen/QWEN.md` as the file that
    "applies to you, across all your projects"; `QWEN_DIR = '.qwen'` in
    `packages/core/src/utils/paths.ts`.
    """
    return _home() / ".qwen" / "QWEN.md"


def _zed_path() -> Path:
    """Zed's global rules file.

    `docs/src/ai/rules.md`: "Default Rules are appended to your global `AGENTS.md`
    file (`~/.config/zed/AGENTS.md` on macOS and Linux, `%APPDATA%\\Zed\\AGENTS.md`
    on Windows)." `crates/paths/src/paths.rs` confirms `%APPDATA%\\Zed` is the
    Windows config dir. Zed keeps rules as Skills by default now, but the global
    `AGENTS.md` is still read, which is what a pointer needs.
    """
    if sys.platform == "win32":
        return _appdata() / "Zed" / "AGENTS.md"
    return _config_dir() / "zed" / "AGENTS.md"


def _crush_path() -> Path:
    """Crush's global context file.

    `README.md` ("Global context files"): "`~/.config/crush/CRUSH.md`: Crush-specific
    rules ... If you only use Crush, this is the only one you need to edit." Crush
    honours the XDG spec, so `$XDG_CONFIG_HOME` wins when set (same README).
    """
    return _config_dir() / "crush" / "CRUSH.md"


def _opencode_path() -> Path:
    """opencode's global rules file.

    `packages/web/src/content/docs/rules.mdx`: "You can also have global rules in a
    `~/.config/opencode/AGENTS.md` file. This gets applied across all opencode
    sessions." The same doc notes opencode falls back to `~/.claude/CLAUDE.md` when
    this file is absent — which is exactly the file `claude-code`'s row writes, so
    the two legs reinforce rather than fight.
    """
    return _config_dir() / "opencode" / "AGENTS.md"


# Hosts whose agent reads a machine-wide instruction file every session: the hosts
# the CLI leg can actually reach (CONTEXT.md: Two Legs Always On). Every other host
# reaches mcptoon through MCP alone.
#
# The list is evidence-based rather than aspirational, and it now spans two kinds
# of host:
# * `codex` — AGENTS.md is Codex's documented channel, and mcptoon already used it.
# * `claude-code` — CLAUDE.md, evidenced by Claude Code's own config state.
# * `gemini`, `qwen`, `zed`, `crush`, `opencode` — each vendor documents one global
#   instruction file by exact path; see the `_<host>_path` docstrings for the file
#   each claim came from.
# * Cursor is NOT here on purpose. `~/.cursorrules` exists on some machines but is
#   the legacy form (current Cursor uses `.cursor/rules`), so writing there risks a
#   pointer into a file the host no longer reads — a silent no-op, which is worse
#   than not writing at all.
# * Windsurf, Cline and VS Code Copilot expose no dedicated global instruction file
#   (Cline's instructions live inside the shared VS Code settings JSON), so they
#   stay MCP-only rather than risk editing a file the user shares with everything
#   else on the machine.
#
# Which hosts those are is now the `pointer_fn` column of `_AGENT_SPECS`, so the
# list cannot drift from the table. `pointer_path` resolves the function *by name*
# at call time: a table of function objects built at import would capture the
# original functions, so a test (or a future refactor) patching
# `_claude_code_memory_path` would silently keep writing to the real home
# directory. This repo has already been bitten once by a pointer landing somewhere
# unexpected — see the note on `_codex_agents_path`.


def pointer_path(agent_id: str) -> Path | None:
    """The instruction file `agent_id` reads every session, if it has one."""
    spec = _AGENT_SPEC_BY_ID.get(agent_id)
    if spec is None or spec.pointer_fn is None:
        return None
    return _resolve(spec.pointer_fn)()


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


# Reserved name for the gateway's own entry.
SELF_SERVER_NAME = "mcptoon"


def _is_gateway_entry(cfg: object) -> bool:
    """True if this server entry is (or could be) mcptoon's own gateway.

    The entry mcptoon writes is ``<python> -m mcptoon serve``. Removal is gated on
    the entry not looking like some *other* server the user happens to have named
    ``mcptoon`` — the name is not magic to any host, and a user's own server under
    that name must not be deleted by `off`/`restore`.

    Lenient by design, so it stays compatible with entries mcptoon has written in
    the past (a different interpreter path, or an empty stub): only an entry that
    clearly declares a non-gateway command (or an HTTP URL) is refused. ``{}`` and
    anything without a command/url is treated as the gateway.
    """
    if not isinstance(cfg, dict):
        return False
    if not cfg:
        return True  # empty entry: no evidence it is anything else
    command = cfg.get("command")
    args = cfg.get("args")
    if isinstance(command, list):
        words = [str(p) for p in command] + ([str(a) for a in args] if isinstance(args, list) else [])
    else:
        words = ([str(command)] if command is not None else []) + \
                ([str(a) for a in args] if isinstance(args, list) else [])
    if any("mcptoon" in w for w in words) and "serve" in words:
        return True
    if command or cfg.get("url"):
        return False  # a real command/url that is not `mcptoon ... serve`
    return True

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

    Two cases:

    1. The block's exact text is present (the writer appends it verbatim) — remove
       that span plus the one blank-line separator before it. Anything the user
       wrote *after* the block survives, because only the block itself is cut.
       This is what makes `off`/`restore` safe when the user appends their own
       content below the pointer.
    2. The heading is present but the body has drifted (an older block format):
       fall back to cutting from the heading to the next ``## `` heading (or EOF) —
       never mid-line. Case 1 already covers the real, current block, so this only
       fires for a block this code did not write.

    Deliberately **not** "cut until the next `## ` heading" as the *primary* rule:
    the user may append `## `-less content (a paragraph, a `#` heading) below the
    pointer after install, and a next-heading scan would swallow it. Byte-
    reversible for `_write_skill_pointer`; used by the undo path (`off`/`restore`).
    """
    if _SKILL_POINTER_BLOCK in text:
        idx = text.find(_SKILL_POINTER_BLOCK)
        before = text[:idx]
        after = text[idx + len(_SKILL_POINTER_BLOCK):]
        # Drop the one blank-line separator the writer inserted before the heading.
        # `after` is kept verbatim: anything the user wrote below the block comes
        # back exactly.
        if before.endswith("\n\n"):
            before = before[:-1]
        return before + after

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        if not skipping and line.strip() == _SKILL_POINTER_HEADING:
            skipping = True
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
    if agent_id not in _AGENT_SPEC_BY_ID:
        return None
    return _paths_for(agent_id)[0]


def _servers_section(data: dict, agent_id: str) -> dict:
    """The mcpServers-shaped mapping inside an agent's config (read-only view).

    Cursor/Claude/Cline/Windsurf keep servers at ``mcpServers``; VS Code keeps
    them at ``mcp.servers`` inside its shared settings.json. Which one is the
    ``shape`` column of `_AGENT_SPECS` — a host's shape is declared once, not
    re-derived at each read site.

    Type-safe by construction: a config whose ``mcpServers`` / ``mcp`` / ``servers``
    is not a mapping (a list, a string, ``null``) yields ``{}`` rather than raising
    — a hand-edited or third-party file must never crash discovery or the undo.
    """
    if not isinstance(data, dict):
        return {}
    if _shape_of(agent_id) == "mcp.servers":
        mcp = data.get("mcp")
        if not isinstance(mcp, dict):
            return {}
        servers = mcp.get("servers")
        return servers if isinstance(servers, dict) else {}
    servers = data.get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def _write_servers_section(data: dict, agent_id: str, section: dict) -> dict:
    """Put ``section`` back where `_servers_section` reads it from.

    The write-side twin of `_servers_section`, and the one place that knows VS
    Code's servers live under ``mcp.servers`` while every other host's live at
    the root ``mcpServers``. Returns the mutated config.
    """
    if _shape_of(agent_id) == "mcp.servers":
        mcp = data.get("mcp")
        if not isinstance(mcp, dict):
            mcp = {}
        mcp["servers"] = section
        data["mcp"] = mcp
    else:
        data["mcpServers"] = section
    return data


def _is_cli_only(agent_id: str) -> bool:
    """True for hosts with no MCP config at all (their delivery is the pointer)."""
    return _shape_of(agent_id) == "pointer"


def gateway_present_in(agent_id: str) -> bool:
    """True if the gateway entry exists in this agent's config (read-only).

    Codex has no JSON config; "present" there means the skill pointer is in its
    AGENTS.md, which is the thing `sync --self` writes for it.
    """
    path = _agent_config_path(agent_id)
    if path is None or not path.exists():
        return False
    if _is_cli_only(agent_id):
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
    if _is_cli_only(agent_id):
        if dry_run:
            if path.exists() and _SKILL_POINTER_HEADING in path.read_text(encoding="utf-8"):
                return {"agent": agent_id, "path": str(path), "removed": True,
                        "written": False, "error": None}
            return {"agent": agent_id, "path": str(path), "removed": False,
                    "written": False, "error": None}
        out = _remove_skill_pointer(path)
        return {"agent": agent_id, "path": out["path"], "removed": out["removed"],
                "written": out["written"], "error": out["error"]}

    data = _read_json_obj(path)
    if not data:
        return {"agent": agent_id, "path": str(path), "removed": False,
                "written": False, "error": None}

    section = _servers_section(data, agent_id)
    has_gateway = (isinstance(section, dict) and SELF_SERVER_NAME in section
                   and _is_gateway_entry(section.get(SELF_SERVER_NAME)))

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


# ─── Restore (put a config back to the state before mcptoon touched it) ───
#
# `sync --takeover` is a subtraction: it removes the host entries mcptoon now
# serves itself and writes a `<config>.bak` holding the pre-mcptoon original
# first. `mcptoon off` removes the *gateway* entry but never reads that backup,
# so a user who takes over and then runs `off` ends up with neither the original
# servers nor the gateway — the entries takeover dropped are gone from the live
# file and survive only in the `.bak`. The CLI used to print "Undo any time:
# mcptoon off, or restore the `<config>.bak`", which implied `off` was enough.
# It is not. This is the missing verb.
#
# It is *surgical*, not a file copy: it drops the gateway entry and puts back only
# the servers the `.bak` holds that the live file has lost. The `.bak` is the
# pre-mcptoon file, but the user keeps editing their config afterwards — a byte
# copy of the `.bak` would silently revert (or delete) everything they added
# since, which is exactly the data loss this command exists to prevent. The
# reverse of a subtraction is to re-add what was removed, nothing more.

def _backup_path(path: Path) -> Path:
    """The `.bak` mcptoon writes alongside a config before changing its content."""
    return path.with_suffix(path.suffix + ".bak")


def _restore_view(agent_id: str, path: Path) -> dict | None:
    """What `restore` would do to one config — computed read-only. None = nothing.

    A host needs undoing when the gateway entry is present (the alongside-mount, or
    a takeover whose gateway is still there) **or** when the `.bak` holds servers
    the live file has lost (a takeover followed by `off`, which removed the gateway
    but not the dropped servers). ``add_back`` names the servers the `.bak` can
    return; ``remove`` is the gateway entry; ``pointer`` is the skill-pointer leg
    for codex/claude-code.

    ``add_back`` is derived from the ``.bak`` itself — the servers it holds that the
    live file no longer has, minus the gateway — not from the current mcptoon
    config. The ``.bak`` *is* "your original servers", so this is purely additive:
    it can only put entries back, never take one away. (Deriving it from the live
    config instead would make restore a no-op the moment a user tidied their mcptoon
    config, and a whole-file copy of the ``.bak`` would be far worse — see the
    delete-stub guard in ``restore_agent_from_backup``.)

    Deliberately NOT a whole-file comparison: the ``.bak`` is the *pre-mcptoon*
    file, but the user keeps editing their config afterwards, so a byte copy would
    also revert (or delete) everything they added since. Only the two edits mcptoon
    made are undone.
    """
    live = _read_json_obj(path)
    if live is None:
        # Unreadable / not an object: we cannot safely compute or perform an undo.
        return None
    section = _servers_section(live, agent_id)
    gateway = (not _is_cli_only(agent_id)
               and SELF_SERVER_NAME in section
               and _is_gateway_entry(section.get(SELF_SERVER_NAME)))

    pointer = False
    ppath = pointer_path(agent_id)
    if ppath is not None:
        ptxt = _read_text_safe(ppath)
        pointer = bool(ptxt and _SKILL_POINTER_HEADING in ptxt)

    add_back: list[str] = []
    bak = _backup_path(path)
    # A `.bak` that is a symlink or not a regular file is not one mcptoon wrote —
    # refuse it rather than import another file's servers into this config.
    if bak.is_file() and not bak.is_symlink():
        bak_section = _servers_section(_read_json_obj(bak) or {}, agent_id)
        add_back = sorted(n for n in bak_section
                          if n != SELF_SERVER_NAME and n not in section)

    if not gateway and not add_back and not pointer:
        return None
    return {"agent": agent_id, "path": str(path), "backup": str(bak),
            "remove": SELF_SERVER_NAME if gateway else None,
            "add_back": add_back, "pointer": pointer}


def _restore_candidates(agent_id: str | None = None) -> list[dict]:
    """Every host config that `restore` would change, de-duplicated.

    De-duplicated on the *resolved* path for the same reason
    ``remove_gateway_from_all`` is: Cursor lists a global and a project-level
    config that can resolve to one file. ``agent_id`` narrows to one host; ``None``
    walks every installed host.
    """
    if agent_id is not None:
        target = _agent_config_path(agent_id)
        hosts = [{"id": agent_id, "name": agent_id,
                  "config_path": str(target) if target is not None else ""}]
    else:
        hosts = detect_installed_agents()

    out: list[dict] = []
    seen: set[str] = set()
    for host in hosts:
        raw = host.get("config_path") or ""
        if not raw:
            continue
        target = Path(raw)
        try:
            key = str(target.resolve()).lower()
        except OSError:  # unreachable drive, malformed path
            key = str(target).lower()
        if key in seen:
            continue
        seen.add(key)
        view = _restore_view(host.get("id", ""), target)
        if view is None:
            continue
        out.append({"agent": host.get("id", ""),
                    "agent_name": host.get("name", host.get("id", "")),
                    "path": str(target), "backup": view["backup"],
                    "remove": view["remove"], "add_back": view["add_back"],
                    "pointer": view["pointer"]})
    return out


def restore_plan(agent_id: str | None = None) -> list[dict]:
    """Read-only preview of what `mcptoon restore` would put back, per host.

    One row per config file `restore` would change — a host mcptoon edited and has
    not been restored since. An empty list means there is nothing to restore.
    Nothing is written; this is the plan, not the result.
    """
    return _restore_candidates(agent_id)


def restore_agent_from_backup(agent_id: str, dry_run: bool = False,
                              path: Path | None = None) -> dict:
    """Undo mcptoon's edits to one host: drop the gateway, return its servers.

    Surgical, not a file copy. It removes only the ``mcptoon`` gateway entry and
    re-adds only the servers the `.bak` holds that mcptoon manages and the live
    file has lost. Everything the user added to their config after mcptoon's edit
    is left exactly where it is — a byte-for-byte copy of the `.bak` would silently
    delete those, which is the failure this command exists to prevent.

    ``path`` overrides the file to restore (same reason ``remove_gateway_from_agent``
    takes one: a host id does not always map to a single file — Cursor keeps a
    project-level config next to its global one).

    A host that also carries the skill-pointer leg (Claude Code's ``CLAUDE.md``,
    Codex's ``AGENTS.md``) has that block removed too: restoring the original means
    the pointer must go as well, or the restored file still tells an agent to use a
    catalog that is no longer mounted. The pointer removal is the same
    byte-reversible ``_remove_skill_pointer`` `off` uses, so the user's own content
    in that file is untouched.

    Returns a sync-shaped result; ``restored`` is True when there was something to
    undo, ``written`` when a file actually changed.
    """
    target = path if path is not None else _agent_config_path(agent_id)
    if target is None:
        return {"agent": agent_id, "path": "", "restored": False, "written": False,
                "error": f"Unknown agent: {agent_id}"}
    view = _restore_view(agent_id, target)
    if view is None:
        return {"agent": agent_id, "path": str(target), "restored": False,
                "written": False, "error": None}

    if dry_run:
        return {"agent": agent_id, "path": str(target), "restored": True,
                "written": False, "error": None, "removed": view["remove"],
                "add_back": view["add_back"], "pointer_removed": view["pointer"]}

    changed = False
    if not _is_cli_only(agent_id) and (view["remove"] or view["add_back"]):
        live = _read_json_obj(target)
        if live is None:
            # Between the plan and the write the file became unreadable. Do not
            # guess — report nothing written rather than risk clobbering it.
            return {"agent": agent_id, "path": str(target), "restored": True,
                    "written": False, "error": "config unreadable; left unchanged",
                    "removed": None, "add_back": [], "pointer_removed": False}
        section = dict(_servers_section(live, agent_id))
        if view["remove"]:
            section.pop(view["remove"], None)
        if view["add_back"]:
            bak = _backup_path(target)
            bak_section = _servers_section(_read_json_obj(bak) or {}, agent_id)
            for name in view["add_back"]:
                if name not in section and name in bak_section:
                    section[name] = bak_section[name]
        _write_servers_section(live, agent_id, section)

        # Delete an empty stub ONLY when the file was mcptoon's own creation: the
        # `.bak` must be a readable object whose server section is empty, proving
        # the file had no servers before mcptoon added the gateway. An *unreadable*
        # `.bak` (missing / corrupt / JSONC / a directory) proves nothing, so it is
        # never grounds for deletion — that is how a rollback would otherwise
        # delete a config it failed to parse. The live file must also have nothing
        # but the (now-empty) server section.
        bak_obj = _read_json_obj(_backup_path(target))
        bak_was_empty = isinstance(bak_obj, dict) and not _servers_section(bak_obj, agent_id)
        if not section and bak_was_empty and set(live.keys()) <= {"mcpServers", "mcp"}:
            try:
                target.unlink(missing_ok=True)
                changed = True
            except OSError:
                changed = False
        else:
            changed = _write_json_safe(target, live)

    pointer_removed = False
    if view["pointer"]:
        ppath = pointer_path(agent_id)
        if ppath is not None and ppath.exists():
            res = _remove_skill_pointer(ppath)
            pointer_removed = bool(res.get("removed"))
    return {"agent": agent_id, "path": str(target), "restored": True,
            "written": bool(changed) or pointer_removed, "error": None,
            "removed": view["remove"], "add_back": view["add_back"],
            "pointer_removed": pointer_removed}


def restore_all_from_backup(dry_run: bool = False) -> list[dict]:
    """Restore every detected host that has an mcptoon edit to undo.

    Each host is restored independently and wrapped: a single malformed config
    (a non-dict section, an unreadable file, a hostile `.bak`) must not abort the
    others — otherwise one bad file would leave the gateway on every remaining
    host and print a traceback. A failing host is reported with ``error`` set.
    """
    agents = detect_installed_agents()
    results = []
    seen: set[str] = set()
    for agent in agents:
        target = Path(agent["config_path"])
        try:
            key = str(target.resolve()).lower()
        except OSError:
            key = str(target).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            r = restore_agent_from_backup(agent["id"], dry_run=dry_run, path=target)
        except Exception as e:  # never let one host abort the whole restore
            r = {"agent": agent["id"], "path": str(target), "restored": False,
                 "written": False, "error": f"{type(e).__name__}: {e}"}
        r["agent_name"] = agent["name"]
        r["config_exists"] = agent["exists"]
        results.append(r)
    return results


# ─── Detection (which agents are installed) ───

def detect_installed_agents() -> list[dict]:
    """Detect which AI agents are installed on this machine.

    Returns list of {id, name, config_path, exists}.

    Driven by `_AGENT_SPECS`: each row declares how its install is proven
    (``detected_by``) and whether it is listed at all when absent
    (``only_when_present``). Two rules that used to live only in prose here:

    * Claude Code is detected by its config *file* — the binary may be on PATH
      without any dotted folder existing yet, and a machine that runs `claude`
      has `.claude.json`, so the file is the evidence.
    * Codex is listed only when `~/.codex/AGENTS.md` already exists: creating it
      out of nothing would be an unasked-for write into a home the user may not
      use for Codex at all.

    Cline is proved by its own extension folder (`saoudrizwan.claude-dev`), not
    by VS Code's *User* directory — that check was true on every machine with VS
    Code installed, so `quickstart` wrote a Cline config for hosts that never had
    Cline. That is the ``grandparent`` rule.
    """
    agents = []
    for spec in _AGENT_SPECS:
        paths = _paths_for(spec.id)
        for path in paths:
            exists = _detect_exists(path, spec.detected_by)
            if spec.only_when_present and not exists:
                continue
            name = spec.name
            if spec.multi:
                # Cursor lists a global and a project-level config; label which
                # is which so a user reading `status` can tell them apart.
                name = f"{spec.name} ({'project' if path == paths[-1] else 'global'})"
            agents.append({
                "id": spec.id,
                "name": name,
                "config_path": str(path),
                "exists": exists,
            })
    return agents


# ─── Sync functions ───

def _read_text_safe(path: Path) -> str | None:
    """File text, or None if it cannot be read as a regular file.

    ``None`` is deliberately distinct from ``""``: a missing, unreadable, or
    non-file path (a directory, a broken symlink) is *unknown*, not *empty*. The
    undo path must never treat "I could not read this" as "there was nothing
    here" — that is how a rollback deletes a config it failed to parse.
    """
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _parse_json(text: str | None) -> object | None:
    """Parse JSON text; ``None`` means *could not parse* (missing or malformed).

    Used where the difference between "empty object" and "unparseable" changes a
    decision. Note the ``None`` return also covers JSONC (VS Code's real
    ``settings.json`` has comments and trailing commas, which ``json`` rejects) —
    an unparseable file is treated as *opaque*, never as empty.
    """
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _read_json_obj(path: Path) -> dict | None:
    """Read a config file as a dict, or ``None`` if absent/unparseable/not an object."""
    data = _parse_json(_read_text_safe(path))
    return data if isinstance(data, dict) else None


def _read_json_safe(path: Path) -> dict:
    """Read JSON file, return empty dict on error.

    Convenience wrapper for the *non-destructive* read paths (discovery, status,
    dry-run previews) where a missing or malformed file should simply read as "no
    data". Code that *writes* or *deletes* must use ``_read_json_obj`` /
    ``_read_text_safe`` instead, so it can tell "empty" from "could not read".
    """
    data = _read_json_obj(path)
    return data if data is not None else {}


def _write_json_safe(path: Path, data: dict) -> bool:
    """Write JSON file, creating parent dirs. Returns True on success.

    Writing into someone's agent config is destructive, so a first `.bak` copy is
    taken *only when the content actually changes* — that keeps the backup
    meaningful (it is the pre-mcptoon state) instead of littering one file per
    routine sync, and it means the very first `sync` that adds the gateway leaves
    a real undo: `mcptoon restore` reads the `.bak` and puts the servers back.
    A failed backup does not block the write; the write is what the user asked for.

    A file that is not a plain JSON object (JSONC, a syntax error, a non-object
    root) is refused rather than overwritten — the caller merged into an empty dict
    for such a file, so writing would silently drop its contents.

    A successful `write_text` is not proof the entry survived: some host state
    files (Claude Code's `~/.claude.json` is one) are rewritten by the host
    process itself, and a writer that races us can drop the entry back out. So
    the write is read back and the gateway's own entry is looked for. Returns
    False when the entry is gone, and reports that on stderr — a silent loss
    would otherwise only surface when a user notices their tools vanished.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_text = json.dumps(data, indent=2, ensure_ascii=False)
        if path.exists():
            try:
                old_text = path.read_text(encoding="utf-8")
            except OSError:
                old_text = None
            # Refuse to overwrite a file we could not parse, or whose top level is
            # not a JSON object (JSONC with comments, a hand-edited file with a
            # trailing comma, a partial write, a bare list). The caller merged into
            # an *empty* dict in that case, so writing would silently drop whatever
            # is already in the file — VS Code's settings.json is JSONC by default,
            # which makes this the likeliest real-world loss.
            if old_text:
                parsed = _parse_json(old_text)
                if not isinstance(parsed, dict):
                    print(
                        f"warning: {path} is not a plain JSON object (comments, a syntax "
                        f"issue, or a non-object root); leaving it unchanged rather than "
                        f"risk dropping settings mcptoon cannot parse. Add the mcptoon "
                        f"entry by hand, or convert the file to JSON first.",
                        file=sys.stderr,
                    )
                    return False
            if old_text is not None and old_text != new_text:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():  # never overwrite an existing backup
                    try:
                        bak.write_text(old_text, encoding="utf-8")
                    except OSError:
                        pass
        path.write_text(new_text, encoding="utf-8")
    except OSError:
        return False

    # Read-back verification (only meaningful when we wrote the gateway entry).
    # Check both config shapes, not just the Claude Code one — a clobbered VS Code
    # `mcp.servers` write must be caught too, or it is reported as success.
    wrote_gateway = (SELF_SERVER_NAME in _servers_section(data, "claude-code")
                     or SELF_SERVER_NAME in _servers_section(data, "vscode-copilot"))
    if wrote_gateway:
        try:
            written_back = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            written_back = None  # cannot tell — do not cry wolf
        if isinstance(written_back, dict):
            survived = (SELF_SERVER_NAME in _servers_section(written_back, "claude-code")
                        or SELF_SERVER_NAME in _servers_section(written_back, "vscode-copilot"))
            if not survived:
                print(
                    f"warning: {path} lost the '{SELF_SERVER_NAME}' entry right after it was "
                    f"written. Another program is rewriting this file; re-run the sync, or add "
                    f"the entry by hand.",
                    file=sys.stderr,
                )
                return False
    return True


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
                       takeover: bool = False, agent_id: str = "") -> dict:
    """Merge new servers into existing config's server section.

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

    ``agent_id`` selects the write location via `_write_servers_section`
    (``mcp.servers`` for VS Code, root ``mcpServers`` for everyone else). It
    defaults to the common shape so the function stays usable standalone.
    """
    result = dict(existing)
    current_servers = dict(_servers_section(result, agent_id))
    if takeover:
        _drop_managed_servers(current_servers, new_servers)
        # Under takeover the gateway replaces the direct entries — re-adding the
        # managed servers here would undo the whole point. Only the gateway's own
        # entry is written back.
        if SELF_SERVER_NAME in new_servers:
            current_servers[SELF_SERVER_NAME] = new_servers[SELF_SERVER_NAME]
    else:
        current_servers.update(new_servers)
    return _write_servers_section(result, agent_id, current_servers)


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

    if not mcp_servers and not _is_cli_only(agent_id):
        # A CLI-only host writes a skill pointer, not a server list, so an empty
        # config is not a reason to skip it — that is exactly the first-run case
        # where the pointer matters most.
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
    if agent_id in _AGENT_SPEC_BY_ID and not _is_cli_only(agent_id):
        path = _agent_config_path(agent_id)
        existing = _read_json_safe(path)
        before = set(_servers_section(existing, agent_id))
        merged = _merge_mcp_servers(existing, mcp_servers, takeover=takeover,
                                    agent_id=agent_id)
        taken_over = len(before - set(_servers_section(merged, agent_id)))
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

    elif _is_cli_only(agent_id):
        # A CLI-only host has no MCP mount; its agent context comes from a
        # machine-wide instruction file. So this branch does not sync *servers* —
        # it writes the skill pointer, which is the only thing that makes such a
        # host able to find a skill at all.
        #
        # Three things the old codex writer got wrong: it targeted `Path.cwd()`
        # (the pointer landed in a random project, or nowhere), its text named only
        # `mcptoon manifest` and never the catalog, and it fired on every `sync`
        # rather than behind `--self`. Now: the path comes from the table row
        # (`_agent_config_path`, so codex/gemini/qwen/zed/crush/opencode each get
        # their own documented file), the skill pointer is included, and it is
        # written only when `include_self` is set — the same opt-in the MCP gateway
        # registration uses, because both are "let this host see mcptoon".
        path = _agent_config_path(agent_id)
        if path is None:
            return {"agent": agent_id, "path": "", "servers_synced": 0,
                    "taken_over": 0, "written": False,
                    "error": f"Unknown agent: {agent_id}"}
        if not include_self:
            return {"agent": agent_id, "path": str(path), "servers_synced": 0,
                    "taken_over": 0, "written": False, "error": None}
        if dry_run:
            # Report the pointer honestly in a preview: a CLI-only host's whole
            # delivery *is* the pointer, so "nothing to write" would be a lie about
            # the one host this branch exists for.
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
        # Only write where the agent is actually installed. `detect_installed_agents`
        # already answers that per agent; until 2026-10-02 the answer was only *stored*
        # (`config_exists`) and never acted on, so `quickstart` created a config file
        # for all five hosts on a machine that had none of them — including
        # `%APPDATA%\Code\User\settings.json`, which a user may later open in a real
        # VS Code and find an `mcp` block they never wrote. Skipping keeps the promise
        # the output makes ("every agent it detects"); `not installed` is already the
        # right row to print.
        if agent.get("exists") is False:
            results.append({
                "agent": agent["id"], "agent_name": agent["name"],
                "path": str(_agent_config_path(agent["id"]) or ""),
                "servers_synced": 0, "taken_over": 0, "written": False,
                "error": None, "config_exists": False, "skipped_not_installed": True,
            })
            continue
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
