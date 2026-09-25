# Copyright 2025 cxh
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
mcptoon config — Server configuration management

Reads server definitions from:
  1. ~/.mcptoon/config.json  (user config)
  2. ./.mcptoon.json          (project config, overrides user)
  3. MCPTOON_SERVERS env var   (JSON string, highest priority)

Config format:
{
  "servers": {
    "exa": {
      "transport": "stdio",
      "command": ["npx", "-y"],
      "args": ["@anthropic/mcp-exa"],
      "env": {"EXA_API_KEY": "..."}
    },
    "github": {
      "transport": "http",
      "url": "http://localhost:3001/mcp",
      "headers": {"Authorization": "Bearer ghp_xxx"}
    }
  }
}
"""
import json
import locale
import os
import sys
from pathlib import Path


# ─── Paths ───

HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".mcptoon"
# Env overrides let CI/tests redirect all config I/O without touching the
# real ~/.mcptoon (same isolation pattern as MCPTOON_SERVERS). Resolved at
# CALL time (not import time) so test processes can retarget safely.
CONFIG_FILE = Path(os.environ.get(
    "MCPTOON_CONFIG_FILE", str(CONFIG_DIR / "config.json")))
CONFIG_FILE_TOML = Path(os.environ.get(
    "MCPTOON_CONFIG_FILE_TOML", str(CONFIG_DIR / "config.toml")))


def _config_file() -> Path:
    return Path(os.environ.get("MCPTOON_CONFIG_FILE", str(CONFIG_FILE)))


def _config_file_toml() -> Path:
    return Path(os.environ.get("MCPTOON_CONFIG_FILE_TOML", str(CONFIG_FILE_TOML)))
CACHE_DIR = HOME_DIR / ".cache" / "mcptoon"
LOG_DIR = CONFIG_DIR / "logs"
TOGGLE_FILE = CONFIG_DIR / "toggles.json"


def _cache_dir() -> Path:
    return Path(os.environ.get("MCPTOON_CACHE_DIR", str(CACHE_DIR)))


def _toggle_file() -> Path:
    return Path(os.environ.get("MCPTOON_TOGGLE_FILE", str(TOGGLE_FILE)))


def state_paths() -> dict:
    """Every path mcptoon owns, resolved at CALL time (env overrides respected).

    Split into three groups because `mcptoon uninstall` treats them differently:

      - ``bookkeeping`` — mcptoon's own state (settings, first-run marker,
        toggles, compression policy). Safe to delete; deleting it is what
        "uninstall" means.
      - ``servers``     — the MCP server definitions the *user* configured.
        Preserved by default: silently deleting someone's server list while
        claiming to clean up would be the worst kind of surprise.
      - ``cache``       — regenerable (manifest + usage). Always safe to delete.
    """
    return {
        "bookkeeping": [_settings_file(), _welcome_file(), _footer_state_file(),
                        _selfheal_file(), _toggle_file(), _policy_file()],
        "servers": [_config_file(), _config_file_toml()],
        "cache": [_cache_dir()],
    }

# Gateway preferences that are not per-server (footer on/off, ...). Kept apart
# from config.json so a settings write can never corrupt a server definition.
# Like _config_file(), the path is resolved at CALL time so a test process can
# redirect it after import (module-level env reads would freeze the real path).
SETTINGS_FILE = Path(os.environ.get(
    "MCPTOON_SETTINGS_FILE", str(CONFIG_DIR / "settings.json")))

# First-run marker. Absent means mcptoon has never introduced itself on this
# machine — the one moment it is allowed to speak unprompted (see
# cli._maybe_welcome). Resolved at CALL time for the same test-isolation reason.
WELCOME_FILE = Path(os.environ.get(
    "MCPTOON_WELCOME_FILE", str(CONFIG_DIR / ".welcome")))

# First-run self-heal marker, deliberately separate from the welcome marker: the
# self-heal (install the agent-visible skill + build the skill index) must run
# once even when the welcome is turned off, and the welcome must still show on a
# machine where the self-heal already ran. One marker cannot serve both without
# coupling them. Cleared by `uninstall`, so a clean reinstall self-heals again —
# correct, since the skill views may have been cleaned too. Call-time resolution
# for the same test-isolation reason as the other state files.
SELFHEAL_FILE = Path(os.environ.get(
    "MCPTOON_SELFHEAL_FILE", str(CONFIG_DIR / ".selfheal")))

# What the savings line said the last time it was shown. The per-turn footer
# compares against this so an unchanged line is not repeated verbatim every turn
# — the "why is it reciting the same number" complaint. Absent means nothing has
# been shown yet, so the first line always prints. Resolved at CALL time for the
# same test-isolation reason as the other state files.
FOOTER_STATE_FILE = Path(os.environ.get(
    "MCPTOON_FOOTER_STATE_FILE", str(CONFIG_DIR / "footer-state.json")))

# Recognized settings and their defaults. The CLI validates against this map, so
# a typo fails loudly instead of silently writing a key nothing reads.
#
# `lang` is not a boolean like the other two: the strings mcptoon prints (the
# savings line and its caveat) speak one human language, and on a real machine
# the signals for "which one" disagree — measured on the author's box, the
# Windows UI language is Chinese (LANGID 0x804) while the shell exports
# `LANG=en_US.UTF-8`. "auto" therefore means "ask the machine, in a fixed
# order"; see `resolve_lang` for the order and for why an order — not a guess —
# is what makes the answer stable.
SETTING_DEFAULTS = {"footer": "on", "welcome": "on", "lang": "auto",
                    "exposure": "compact"}

# Languages the human-facing strings can be written in. "auto" is not a language:
# it is the request to detect one.
VALID_LANGS = ("auto", "zh", "en")
DEFAULT_LANG = "en"

# Tool-exposure presets — how much of the tool catalog the gateway lists in
# `tools/list` (CONTEXT.md: "Tool Exposure Preset").
#
#   compact — list only mcptoon's own tools. Upstream tools are reachable
#             (mcptoon_manifest names them, mcptoon_call runs them) but are not
#             enumerated, which is what keeps the per-turn cost near zero.
#   full    — also list every upstream tool with a simplified schema. This is
#             the pre-2026-09-25 behavior and the fallback: a host whose UI
#             reads `tools/list` to draw a tool panel shows nothing to pick from
#             under `compact`, and a weak model may decide a tool "does not
#             exist" instead of asking for the manifest.
#
# `compact` is the default because the tool exists to cut per-turn context, and
# the fallback is one command away; see the `mcptoon` skill for when to use it.
EXPOSURE_MODES = ("compact", "full")

# Settings whose value must be one of a fixed set. Validated in `set_setting`,
# so a typo fails loudly instead of silently persisting a value nothing honours.
#
# `exposure` is here and `lang` deliberately is not, because the two failures are
# not equally bad:
#   * a bad `lang` only affects which language one printed line speaks, and
#     `resolve_lang` already falls through to detection — raising at write time
#     would block a command that was going to work anyway (pinned by
#     tests/test_lang.py::test_an_unrecognised_setting_falls_through_instead_of_raising).
#   * a bad `exposure` silently changes what the gateway lists. Someone who types
#     `full` and gets `compact` is told their tools are visible when they are not
#     — a silent downgrade of exactly the kind this repo treats as a bug, so it
#     has to fail at the keyboard instead.
SETTING_CHOICES = {"exposure": EXPOSURE_MODES}

# Windows LANGID primary-language ids worth naming. Anything unnamed falls back
# to the locale string and then to English, so an unlisted language degrades to
# a correct-but-foreign line rather than to a crash.
_WIN_PRIMARY_LANGS = {0x04: "zh", 0x09: "en"}


def _settings_file() -> Path:
    return Path(os.environ.get("MCPTOON_SETTINGS_FILE", str(SETTINGS_FILE)))


def _welcome_file() -> Path:
    return Path(os.environ.get("MCPTOON_WELCOME_FILE", str(WELCOME_FILE)))


def _selfheal_file() -> Path:
    return Path(os.environ.get("MCPTOON_SELFHEAL_FILE", str(SELFHEAL_FILE)))


def _footer_state_file() -> Path:
    return Path(os.environ.get(
        "MCPTOON_FOOTER_STATE_FILE", str(FOOTER_STATE_FILE)))

# Ensure dirs exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ─── Server name aliases ───

# Users can use short names; we map to canonical names
SERVER_ALIASES = {
    "exa": "exa",
    "fetch": "fetch",
    "github": "github",
    "fs": "filesystem",
    "filesystem": "filesystem",
}


def resolve_server_name(name: str) -> str:
    """Resolve short name to canonical server name.

    Checks static aliases first, then dynamically checks if 'name'
    is a prefix of any configured server name (e.g. 'fs' → 'filesystem').
    """
    # 1. Static aliases (backward compat)
    if name in SERVER_ALIASES:
        return SERVER_ALIASES[name]

    # 2. Check if exact name exists in config (no resolution needed)
    servers = load_config()
    if name in servers:
        return name

    # 3. Dynamic prefix matching (e.g. 'fs' → 'filesystem')
    for sname in servers:
        if sname.lower() == name.lower():
            return sname

    # 4. Return as-is (let caller handle unknown server)
    return name


# ─── Config loading ───

def load_config() -> dict:
    """Load merged server configuration.

    Priority (highest wins):
      1. MCPTOON_SERVERS env var (JSON string)
      2. ./.mcptoon.json (project local)
      3. ./.mcptoon.toml (project local, TOML)
      4. ~/.mcptoon/config.toml (user global, TOML)
      5. ~/.mcptoon/config.json (user global, JSON)

    Supports both JSON and TOML config files.
    TOML is preferred for hand-editing (comments, cleaner syntax).
    """
    servers = {}

    # 1. User global config — try TOML first, then JSON
    toml_file = _config_file_toml()
    json_file = _config_file()
    if toml_file.exists():
        try:
            data = _parse_toml(toml_file.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (OSError, ValueError):
            pass
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Project local config (overrides user) — try TOML first, then JSON
    local_toml = Path(".mcptoon.toml")
    if local_toml.exists():
        try:
            data = _parse_toml(local_toml.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (OSError, ValueError):
            pass
    local = Path(".mcptoon.json")
    if local.exists():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            servers.update(data.get("servers", {}))
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Environment variable (highest priority)
    env_servers = os.environ.get("MCPTOON_SERVERS", "")
    if env_servers:
        try:
            data = json.loads(env_servers)
            servers.update(data.get("servers", {}))
        except json.JSONDecodeError:
            pass

    return servers


def save_config(servers: dict, fmt: str = ""):
    """Save server configuration to user config file.

    Args:
        servers: Server config dict
        fmt: "json" or "toml". If empty, preserves existing format,
              defaults to JSON for new configs.
    """
    # Determine format: explicit > existing file > default JSON
    json_file = _config_file()
    toml_file = _config_file_toml()
    if not fmt:
        if toml_file.exists() and not json_file.exists():
            fmt = "toml"
        else:
            fmt = "json"

    if fmt == "toml":
        toml_file.write_text(
            _dump_toml(servers),
            encoding="utf-8",
        )
    else:
        json_file.write_text(
            json.dumps({"servers": servers}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def add_server(name: str, config: dict):
    """Add or update a server in config."""
    servers = load_config()
    servers[name] = config
    save_config(servers)


def merge_servers(new_servers: dict, overwrite: bool = False) -> tuple:
    """Merge new servers into existing config.

    Args:
        new_servers: {name: config} to merge in
        overwrite: If True, overwrite existing servers. If False, skip existing.

    Returns:
        (added_count, skipped_count, overwritten_count)
    """
    existing = load_config()
    added = 0
    skipped = 0
    overwritten = 0

    for name, cfg in new_servers.items():
        if name in existing and not overwrite:
            skipped += 1
        elif name in existing and overwrite:
            existing[name] = cfg
            overwritten += 1
        else:
            existing[name] = cfg
            added += 1

    save_config(existing)
    return (added, skipped, overwritten)


def remove_server(name: str) -> bool:
    """Remove a server from config. Returns True if existed."""
    servers = load_config()
    if name in servers:
        del servers[name]
        save_config(servers)
        return True
    return False


def list_servers() -> list[str]:
    """List configured server names."""
    return sorted(load_config().keys())


def get_server_config(name: str) -> dict | None:
    """Get config for a specific server."""
    return load_config().get(name)


# ─── Gateway settings (not per-server) ───

def load_settings() -> dict:
    """Gateway preferences merged over defaults. A missing file is not an error."""
    values = dict(SETTING_DEFAULTS)
    path = _settings_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in SETTING_DEFAULTS:
                    if key in data:
                        values[key] = data[key]
        except (json.JSONDecodeError, OSError):
            pass
    return values


def get_setting(key: str) -> str:
    """One setting's current value (default when unset)."""
    return str(load_settings().get(key, SETTING_DEFAULTS.get(key, "")))


def set_setting(key: str, value: str) -> None:
    """Persist one setting. Unknown keys raise ValueError so typos fail loudly."""
    if key not in SETTING_DEFAULTS:
        raise ValueError(
            f"unknown setting {key!r}; known: {', '.join(sorted(SETTING_DEFAULTS))}")
    choices = SETTING_CHOICES.get(key)
    if choices and value not in choices:
        raise ValueError(
            f"{key}={value!r} is not one of {', '.join(choices)}")
    path = _settings_file()
    current = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                current = data
        except (json.JSONDecodeError, OSError):
            current = {}
    current[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def footer_enabled() -> bool:
    """Whether the end-of-turn disclosure is on. Default: on."""
    return get_setting("footer").strip().lower() not in ("off", "0", "false", "no")


def exposure_mode() -> str:
    """Which tools `serve` lists: "compact" (default) or "full".

    An unrecognized stored value falls back to the default rather than raising:
    a settings file edited by hand must not be able to break the gateway, and
    "list fewer tools" is the safe direction to fail in.
    """
    value = get_setting("exposure").strip().lower()
    return value if value in EXPOSURE_MODES else EXPOSURE_MODES[0]


def compact_exposure() -> bool:
    """True when the gateway should withhold the upstream tool list."""
    return exposure_mode() == "compact"


def welcome_enabled() -> bool:
    """Whether the one-time first-run welcome may print. Default: on."""
    return get_setting("welcome").strip().lower() not in ("off", "0", "false", "no")


def welcome_seen() -> bool:
    """True once the first-run welcome has been shown (marker file exists)."""
    return _welcome_file().exists()


def mark_welcome_seen() -> None:
    """Drop the first-run marker so the welcome never prints again.

    Best-effort: a read-only home directory must not turn a normal command into
    a crash, and the worst case (welcome repeats) is harmless.
    """
    try:
        path = _welcome_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    except OSError:
        pass


def selfheal_done(fingerprint: str = "") -> bool:
    """True when the first-run self-heal has nothing left to do on this machine.

    The marker records the fingerprint of the skill that was installed, not merely
    that *a* self-heal ran. That distinction is the whole point: a plain "done" flag
    would make an upgrade a no-op — the marker from the previous release would
    suppress the refresh, and the agent would keep reading an outdated explanation
    of the defaults forever. So a marker whose fingerprint no longer matches the
    packaged skill reads as *not* done, and the next command heals again.

    ``fingerprint=""`` keeps the lenient form (any marker counts as done), which is
    what callers that only need "has this ever run" want.
    """
    try:
        path = _selfheal_file()
        if not path.exists():
            return False
        if not fingerprint:
            return True
        return path.read_text(encoding="utf-8").strip() == fingerprint
    except OSError:
        # An unreadable marker must not crash a normal command. Assume done: the
        # cost of being wrong is one skipped refresh, versus re-healing on every
        # single run if we assumed the opposite.
        return True


def mark_selfheal_done(fingerprint: str = "") -> None:
    """Record that the first-run self-heal ran, and for which skill.

    Best-effort for the same reason `mark_welcome_seen` is: a read-only home must
    not turn a normal command into a crash, and the worst case (the self-heal
    repeats) is a harmless no-op write of an already-present file.
    """
    try:
        path = _selfheal_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fingerprint, encoding="utf-8")
    except OSError:
        pass


# ─── Remembering the last savings line ───

def last_footer_line() -> str | None:
    """The savings line shown last time, or None when nothing has been shown.

    Best-effort: a corrupt or unreadable state file degrades to "nothing shown",
    which only means the next line prints once more — never a crash.
    """
    try:
        return json.loads(_footer_state_file().read_text(encoding="utf-8")).get("line")
    except (OSError, ValueError, AttributeError):
        return None


def remember_footer_line(line: str) -> None:
    """Record the savings line just shown, so an identical one can be suppressed.

    Best-effort for the same reason `mark_welcome_seen` is: a read-only home
    directory must not turn a normal command into a crash, and the worst case
    (the line repeats) is exactly the behavior this is trying to reduce.
    """
    try:
        path = _footer_state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"line": line}), encoding="utf-8")
    except OSError:
        pass


# ─── Language of the human-facing strings ───

def _lang_from_tag(tag: str | None) -> str | None:
    """Map a locale string to 'zh' / 'en', or None when it is neither.

    Two shapes arrive here: POSIX tags ('zh_CN', 'en_US.UTF-8') and the Windows
    display names `locale.getlocale()` returns ('Chinese (Simplified)_China').
    Both are matched by prefix, case-insensitively — a full table of every
    locale would be a dependency on the CLDR, and the only decision this feeds
    is which of two languages to print.
    """
    if not tag:
        return None
    text = tag.strip().lower()
    if text.startswith("zh") or text.startswith("chinese"):
        return "zh"
    if text.startswith("en") or text.startswith("english"):
        return "en"
    return None


def _os_ui_lang() -> str | None:
    """The operating system's own UI language, or None when it cannot be read.

    On Windows this asks the OS directly rather than `locale.getlocale()`: the
    console locale is trivially overridden by LC_*/LANG, and that override is
    exactly the signal this function has to outrank.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            langid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        except (AttributeError, OSError, ValueError):
            langid = 0
        named = _WIN_PRIMARY_LANGS.get(langid & 0x3FF) if langid else None
        if named:
            return named
    try:
        name = locale.getlocale()[0]
    except (ValueError, TypeError):
        name = None
    return _lang_from_tag(name)


def _env_lang() -> str | None:
    """The language the environment asks for, in locale precedence order."""
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        found = _lang_from_tag(os.environ.get(key))
        if found:
            return found
    return None


def resolve_lang(setting: str | None = None) -> str:
    """Which language the human-facing strings speak: 'zh' or 'en'.

    Priority, highest first. It is an explicit order rather than a guess because
    the sources genuinely disagree — on the author's machine the OS UI language
    is Chinese while `LANG=en_US.UTF-8` says English, so "just detect it" is a
    coin flip that changes between a terminal and a service:

      1. the explicit `lang` setting (`mcptoon config set lang zh`)
      2. `MCPTOON_LANG` in the environment — the same escape hatch as
         `MCPTOON_CACHE_DIR`, so a caller can pin the language without writing a
         settings file
      3. the operating system's UI language
      4. `LC_ALL` / `LC_MESSAGES` / `LANG`
      5. English — the language this project writes its documentation in

    An unrecognised value (a hand-edited settings file, a typo) falls through to
    the machine's answer instead of raising: a settings typo must not break a
    command whose whole job is to print one line.
    """
    chosen = (setting if setting is not None else get_setting("lang")).strip().lower()
    if chosen != "auto" and chosen in VALID_LANGS:
        return chosen
    return (
        _lang_from_tag(os.environ.get("MCPTOON_LANG"))
        or _os_ui_lang()
        or _env_lang()
        or DEFAULT_LANG
    )


# ─── Toggle management (per-tool enable/disable) ───

def load_toggles() -> dict:
    """Load tool toggle state. Format: {"server:tool": true/false}."""
    if not TOGGLE_FILE.exists():
        return {}
    try:
        return json.loads(TOGGLE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_toggles(toggles: dict):
    """Save tool toggle state."""
    TOGGLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOGGLE_FILE.write_text(
        json.dumps(toggles, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_tool_enabled(server: str, tool: str) -> bool:
    """Check if a tool is enabled (default: True)."""
    toggles = load_toggles()
    key = f"{server}:{tool}"
    return toggles.get(key, True)


def toggle_tool(server: str, tool: str) -> bool:
    """Toggle a tool on/off. Returns new state (True=enabled, False=disabled)."""
    toggles = load_toggles()
    key = f"{server}:{tool}"
    current = toggles.get(key, True)
    toggles[key] = not current
    save_toggles(toggles)
    return not current


def list_disabled_tools() -> list[str]:
    """List all disabled tool keys."""
    toggles = load_toggles()
    return [k for k, v in toggles.items() if not v]


# ─── Per-tool compression policy ───
# Same granularity as toggles ("server:tool"), stored in its own file so a
# compression decision never fights an on/off toggle. Policies answer one
# question MuleSoft's gateway made table stakes: *this* tool's results must
# not be compressed (raw) or must always arrive as a specific shape.

VALID_POLICIES = ("raw", "json", "auto", "toon", "compact", "slim")
POLICY_FILE = CONFIG_DIR / "compression.json"


def _policy_file() -> Path:
    # Env override lets CI/tests redirect policy I/O without touching the
    # real ~/.mcptoon (same isolation pattern as MCPTOON_CONFIG_FILE).
    return Path(os.environ.get("MCPTOON_COMPRESSION_FILE", str(POLICY_FILE)))


def load_policies() -> dict:
    """Load per-tool compression policies. Format: {"server:tool": "<policy>"}."""
    if not _policy_file().exists():
        return {}
    try:
        data = json.loads(_policy_file().read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, dict):
        policies = data.get("policies", data)
        return policies if isinstance(policies, dict) else {}
    return {}


def save_policies(policies: dict):
    f = _policy_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps({"policies": policies}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_compression_policy(server: str, tool: str) -> str | None:
    """Resolve the compression policy for a tool.

    Exact `server:tool` wins over the server-wide `server:*` wildcard.
    Returns None when no valid policy is configured.
    """
    policies = load_policies()
    value = policies.get(f"{server}:{tool}")
    if value is None:
        value = policies.get(f"{server}:*")
    if value in VALID_POLICIES:
        return value
    return None


def resolve_output_format(server: str, tool: str, base_fmt: str) -> str:
    """Effective output format: the tool's policy if configured, else base_fmt.

    A policy of "auto" means "default behaviour" — identical to no policy.
    """
    policy = get_compression_policy(server, tool)
    if policy is None or policy == "auto":
        return base_fmt
    return policy


def set_compression_policy(server: str, tool: str, policy: str | None) -> bool:
    """Set a policy; None or "auto" clears it. Returns False on unknown policy."""
    policies = load_policies()
    key = f"{server}:{tool}"
    if policy is None or policy == "auto":
        policies.pop(key, None)
        save_policies(policies)
        return True
    if policy not in VALID_POLICIES:
        return False
    policies[key] = policy
    save_policies(policies)
    return True


def list_policies() -> dict:
    """All configured policies, sorted for stable output."""
    return dict(sorted(load_policies().items()))


# ─── Sample config for first-time users ───

SAMPLE_CONFIG = {
    "servers": {
        "memory": {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-memory"],
        },
        "filesystem": {
            "transport": "stdio",
            "command": ["npx", "-y"],
            "args": ["@modelcontextprotocol/server-filesystem", "."],
        },
    }
}


def init_sample_config():
    """Create a sample config if none exists."""
    if not _config_file().exists() and not _config_file_toml().exists():
        save_config(SAMPLE_CONFIG["servers"])
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# TOML support (zero-dependency, pure stdlib)
# ═══════════════════════════════════════════════════════════════

def _parse_toml(text: str) -> dict:
    """Parse a TOML string into a dict.

    Uses Python 3.11+ tomllib when available. Falls back to a
    minimal built-in parser that handles the mcptoon config subset
    (tables, strings, arrays, booleans).

    Raises ValueError on parse error.
    """
    # Try stdlib tomllib (Python 3.11+)
    try:
        import tomllib
        return tomllib.loads(text)
    except ImportError:
        pass

    # Fallback: minimal parser for mcptoon config format
    return _toml_lite_parse(text)


def _toml_lite_parse(text: str) -> dict:
    """Minimal TOML parser for mcptoon config files.

    Supports:
      - [section.subsection] tables
      - key = "string"
      - key = ["a", "b"] arrays
      - key = true/false
      - # comments

    Not supported (not needed for mcptoon config):
      - Inline tables, multiline strings, dates, floats, hex
    """
    result = {}
    current_table = result

    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Table header: [section] or [section.subsection]
        # Strip inline comments from table headers first
        if line.startswith("["):
            # Find the closing bracket, ignore anything after it (inline comment)
            close = line.find("]")
            if close >= 0:
                line = line[:close + 1]
        if line.startswith("[") and line.endswith("]"):
            table_path = line[1:-1].strip()
            parts = [p.strip() for p in table_path.split(".")]
            current_table = result
            for part in parts:
                if part not in current_table:
                    current_table[part] = {}
                current_table = current_table[part]
            continue

        # key = value
        if "=" not in line:
            raise ValueError(f"TOML parse error at line {line_num}: no '=' found")

        eq_pos = line.index("=")
        key = line[:eq_pos].strip()
        value_str = line[eq_pos + 1:].strip()

        # Strip inline comments (but not inside strings)
        if value_str.startswith('"'):
            # String value — find closing quote, then strip comment after it
            i = 1
            while i < len(value_str):
                if value_str[i] == '\\':
                    i += 2  # Skip escaped char
                    continue
                if value_str[i] == '"':
                    break
                i += 1
            if i < len(value_str):
                # Found closing quote at position i
                # Keep the quoted string, strip everything after (inline comment)
                value_str = value_str[:i + 1]
        elif "#" in value_str:
            value_str = value_str[:value_str.index("#")].strip()

        value = _toml_parse_value(value_str, line_num)
        current_table[key] = value

    return result


def _toml_parse_value(s: str, line_num: int = 0):
    """Parse a TOML value string."""
    s = s.strip()

    # String
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")

    # Array
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = []
        # Simple split by comma (handles typical config arrays)
        parts = _split_array_items(inner)
        for part in parts:
            part = part.strip()
            if part:
                items.append(_toml_parse_value(part, line_num))
        return items

    # Boolean
    if s == "true":
        return True
    if s == "false":
        return False

    # Integer
    try:
        return int(s)
    except ValueError:
        pass

    # Float
    try:
        return float(s)
    except ValueError:
        pass

    # Bare string (TOML doesn't officially support this, but be lenient)
    return s


def _split_array_items(s: str) -> list[str]:
    """Split array items by comma, respecting quoted strings."""
    items = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            in_quotes = not in_quotes
            current += c
        elif c == "," and not in_quotes:
            items.append(current)
            current = ""
        else:
            current += c
        i += 1
    if current.strip():
        items.append(current)
    return items


def _dump_toml(servers: dict) -> str:
    """Serialize servers config as TOML string.

    Produces clean, human-readable TOML with comments.

    Example output:
        # mcptoon configuration
        # See: https://github.com/activeing123/mcptoon

        [servers.memory]
        transport = "stdio"
        command = ["npx", "-y"]
        args = ["@modelcontextprotocol/server-memory"]

        [servers.filesystem]
        transport = "stdio"
        command = ["npx", "-y"]
        args = ["@modelcontextprotocol/server-filesystem", "."]
    """
    lines = [
        "# mcptoon configuration",
        "# Format: TOML (easier to hand-edit than JSON)",
        "# Run: mcptoon manifest  to see your tools",
        "",
    ]

    for name in sorted(servers.keys()):
        cfg = servers[name]
        lines.append(f"[servers.{name}]")

        # Transport
        transport = cfg.get("transport", "stdio")
        lines.append(f'transport = "{transport}"')

        # stdio fields
        if transport == "stdio":
            command = cfg.get("command", [])
            if isinstance(command, list):
                lines.append(f"command = {_toml_array(command)}")
            else:
                lines.append(f'command = ["{command}"]')

            args = cfg.get("args", [])
            if args:
                lines.append(f"args = {_toml_array(args)}")

            env = cfg.get("env", {})
            if env:
                lines.append("")
                lines.append(f"[servers.{name}.env]")
                for k, v in sorted(env.items()):
                    lines.append(f'{k} = "{v}"')
                lines.append("")

        # http fields
        elif transport == "http":
            url = cfg.get("url", "")
            lines.append(f'url = "{url}"')
            headers = cfg.get("headers", {})
            if headers:
                lines.append("")
                lines.append(f"[servers.{name}.headers]")
                for k, v in sorted(headers.items()):
                    lines.append(f'{k} = "{v}"')
                lines.append("")

        lines.append("")

    return "\n".join(lines)


def _toml_array(items: list) -> str:
    """Format a list as a TOML array string."""
    parts = []
    for item in items:
        if isinstance(item, str):
            parts.append(f'"{item}"')
        elif isinstance(item, bool):
            parts.append("true" if item else "false")
        elif item is None:
            parts.append('""')
        else:
            parts.append(str(item))
    return "[" + ", ".join(parts) + "]"
