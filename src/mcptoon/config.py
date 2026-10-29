# Copyright 2025 activeing123
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
import tempfile
from pathlib import Path


# ─── Paths ───

HOME_DIR = Path.home()

# ─── XDG Base Directory support (issue #25) ───
#
# mcptoon used to hardcode `~/.mcptoon` and `mkdir` it unconditionally, which
# cluttered `$HOME` on Linux and left no way to relocate the directory without
# faking `$HOME` (issue #25). The rules below implement what that issue asked
# for, in this order of precedence:
#
#   1. `MCPTOON_HOME` (env) or `--dir` (CLI) — an explicit root. One directory
#      for everything, cache underneath it, because that is what "put my
#      mcptoon files *here*" means to the person typing it.
#   2. XDG — but only when the variables are actually set. `XDG_CONFIG_HOME`
#      etc. are absent on a stock Windows box and on plenty of Linux setups;
#      inventing a default for them would move files nobody asked to move.
#   3. Legacy `~/.mcptoon` (+ `~/.cache/mcptoon`) — the pre-XDG layout.
#
# The subtle rule, and the one that protects existing installs: if the XDG
# location does not exist yet but the legacy directory does, keep using legacy
# and do NOT create the XDG directory. Without it, a Linux user upgrading from
# 0.8.15 would watch their configured servers vanish — the worst kind of bug,
# because the data is still on disk and nothing says where it went.
def _xdg_dir(env_var: str) -> "Path | None":
    """`$<env_var>/mcptoon` when the variable is set and non-empty, else None.

    Returning None (rather than a default) matters: "the variable is unset" and
    "the variable points at the default" are different states, and only the
    first one should fall through to the legacy directory. Conflating them is
    what makes an unset `XDG_CONFIG_HOME` resolve to `~/.config` — an XDG
    location the user never asked for.
    """
    val = os.environ.get(env_var, "").strip()
    return Path(val) / "mcptoon" if val else None


def _legacy_root() -> Path:
    return HOME_DIR / ".mcptoon"


def _resolve_root(env_var: str) -> Path:
    """Config root: explicit > XDG-if-present > legacy-if-present > XDG-if-set."""
    explicit = os.environ.get("MCPTOON_HOME", "").strip()
    if explicit:
        return Path(explicit)
    xdg = _xdg_dir(env_var)
    if xdg is None:
        return _legacy_root()
    if xdg.exists() or not _legacy_root().exists():
        return xdg
    return _legacy_root()


def _resolve_cache_root() -> Path:
    explicit = os.environ.get("MCPTOON_HOME", "").strip()
    if explicit:
        return Path(explicit) / "cache"
    legacy = HOME_DIR / ".cache" / "mcptoon"
    xdg = _xdg_dir("XDG_CACHE_HOME")
    if xdg is None:
        return legacy
    if xdg.exists() or not legacy.exists():
        return xdg
    return legacy


def _xdg_state_dir() -> "Path | None":
    return _xdg_dir("XDG_STATE_HOME")


CONFIG_DIR = _resolve_root("XDG_CONFIG_HOME")
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
CACHE_DIR = _resolve_cache_root()


def _resolve_state_dir(config_dir: Path) -> Path:
    """Where logs and toggles live.

    Three cases, and only the middle one moves:

    * legacy `~/.mcptoon` — everything stays inside it, exactly as before.
    * the XDG config root — state follows `XDG_STATE_HOME`, which is the whole
      point of the spec: logs and toggles are state, not configuration.
    * an explicit `MCPTOON_HOME` / `--dir` — everything under that one root.
      "Put my mcptoon files here" must not scatter half of them into
      `~/.local/state`, which is what an unconditional XDG_STATE_HOME lookup
      would do.
    """
    if config_dir == _legacy_root():
        return config_dir
    if config_dir == _xdg_dir("XDG_CONFIG_HOME"):
        return _xdg_state_dir() or config_dir
    return config_dir


STATE_DIR = _resolve_state_dir(CONFIG_DIR)
LOG_DIR = STATE_DIR / "logs"
TOGGLE_FILE = STATE_DIR / "toggles.json"


def _cache_dir() -> Path:
    return Path(os.environ.get("MCPTOON_CACHE_DIR", str(CACHE_DIR)))


def _toggle_file() -> Path:
    return Path(os.environ.get("MCPTOON_TOGGLE_FILE", str(TOGGLE_FILE)))


def state_paths() -> dict:
    """Every path mcptoon owns, resolved at CALL time (env overrides respected).

    Split into three groups because `mcptoon uninstall` treats them differently:

      - ``bookkeeping`` — mcptoon's own state (settings, first-run marker,
        toggles, compression policy, the installed-server registry). Safe to
        delete; deleting it is what "uninstall" means.
      - ``servers``     — the MCP server definitions the *user* configured.
        Preserved by default: silently deleting someone's server list while
        claiming to clean up would be the worst kind of surprise.
      - ``cache``       — regenerable (manifest + usage). Always safe to delete.

    The installed-server registry (`pro_installed.json`) is in ``bookkeeping`` as
    of 2026-10-02: it was absent, so `mcptoon uninstall` left it behind even
    though it is state mcptoon created. Its location is not spelled out here —
    ``_installed_registry_file()`` is the one place that decides it, because the
    path moved (2026-10-29) off a hardcoded `~/.mcp-cli/` and a second copy of
    that decision is how `uninstall` and `install` drift apart.
    """
    return {
        "bookkeeping": [_settings_file(), _welcome_file(), _footer_state_file(),
                        _selfheal_file(), _toggle_file(), _policy_file(),
                        _cli_aha_file(), _installed_registry_file(),
                        _handlers_state_dir()],
        "servers": [_config_file(), _config_file_toml()],
        "cache": [_cache_dir()],
    }


def _handlers_state_dir() -> Path:
    """`STATE_DIR/handlers` — generated handler files (see ``installer._handlers_dir``).

    Kept here so ``uninstall`` removes it: the generated handlers are mcptoon's own
    state, and they used to live inside the package (issue #35), where a read-only
    install could not write them at all. Resolved at CALL time from
    ``MCPTOON_HANDLERS_DIR`` (same isolation pattern as the other state paths), so a
    test process can redirect it after import.
    """
    return Path(os.environ.get(
        "MCPTOON_HANDLERS_DIR", str(STATE_DIR / "handlers")))


# Where the registry lived before it honoured the root. A real `Path`, not a
# string, because the migration guard below asks it `.exists()`.
LEGACY_INSTALLED_FILE = HOME_DIR / ".mcp-cli" / "pro_installed.json"


def _installed_registry_file() -> Path:
    """`pro_installed.json` — mcptoon's registry of installed servers.

    Three tiers, the same shape as `_resolve_root`:

      1. `MCPTOON_INSTALLED_FILE` — explicit; always wins (tests, `uninstall`).
      2. an existing legacy `~/.mcp-cli/pro_installed.json` — kept, never
         orphaned, for the same reason an existing `~/.mcptoon` is kept: moving
         a default must not make a user's installed servers look uninstalled.
      3. `STATE_DIR/pro_installed.json` — the root every other state file uses
         (`handlers/`, `toggles.json`), which is what makes `--dir`,
         `MCPTOON_HOME` and the XDG variables reach it at all.

    Before 2026-10-29 this was hardcoded to `~/.mcp-cli/` — a directory named
    after a *different* tool — so `--dir X` wrote handlers under X and the
    registry under `$HOME` (issue #25, re-raised by the original reporter).

    Resolved at CALL time and only here, because `installer._installed_path()`
    delegates to this function: a second copy of the precedence order is exactly
    how the writer and `uninstall` end up disagreeing about which file is the
    registry.
    """
    explicit = os.environ.get("MCPTOON_INSTALLED_FILE", "").strip()
    if explicit:
        return Path(explicit)
    if LEGACY_INSTALLED_FILE.exists():
        return LEGACY_INSTALLED_FILE
    return STATE_DIR / "pro_installed.json"

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

# First-CLI-call "aha" marker. The very first `mcptoon call` on a machine gets one
# extra line spelling out what the CLI path just avoided loading (the whole tool
# catalog). It fires once and never again — the point is to make the saving
# legible at the moment it happens, not to nag every call. Its own marker, not the
# welcome's: the welcome can be off while a user still deserves the one-time
# receipt, and vice versa. Resolved at CALL time for test isolation.
CLI_AHA_FILE = Path(os.environ.get(
    "MCPTOON_CLI_AHA_FILE", str(CONFIG_DIR / ".cli-aha")))

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
                    "exposure": "compact", "compress": "smart",
                    "runners": "prefer-installed", "select.engine": "lexical",
                    "select.command": "", "presence": "on", "receipt": "on",
                    "activity_keep": "2000"}

# `activity_keep` is the one numeric setting: how many activity-ledger lines to
# keep before old ones roll off. It is a plain count, not an on/off or a fixed
# choice, so it validates by range rather than against SETTING_CHOICES. The floor
# keeps it useful (a handful of lines is not a history); the ceiling keeps a typo
# like "20000" from quietly pinning megabytes of ledger. Both bounds are generous
# on purpose — this is a preference, not a policy.
ACTIVITY_KEEP_MIN = 50
ACTIVITY_KEEP_MAX = 100000
ACTIVITY_KEEP_DEFAULT = 2000

# How mcptoon ranks candidate tools for a query ("which tools should the agent
# look at for this task?").
#
#   lexical — the built-in scorer (exact > prefix > substring > token overlap >
#             fuzzy), pure stdlib, no network, no model. This is the default and
#             the only engine that is guaranteed to exist.
#   command — call an external program the user supplies, so a machine that
#             already runs an embedding or LLM ranker can use it without mcptoon
#             taking a dependency. The contract is one JSON object on stdin, one
#             JSON array on stdout (see `manifest.rank_tools`).
#
# Why an opt-in command instead of a built-in model (the user's decision,
# 2026-10-09): zero dependencies is one of the four things mcptoon sells
# (`dependencies = []`, enforced by `scripts/check_zero_deps.py`), and the
# honest way to keep that while still letting a power user rank semantically is
# to shell out. Same shape as the optional `tiktoken` in `bench`: the default
# path is pure stdlib, the better path is a thing you install yourself.
SELECT_ENGINES = ("lexical", "command")

# How mcptoon picks the launcher it writes for a discovered or installed server.
#
#   prefer-installed — when the package a server needs is already importable,
#                      write `python -m <module>`; only reach for `uvx`/`npx`
#                      when nothing local can run it. This is the default.
#   allow-fetch      — always write `uvx`/`npx` (fetch-on-first-run). The old
#                      behavior, kept as an explicit opt-in.
#
# Why the default flipped (2026-10-06 incident): `uvx <pkg>` starts a second
# interpreter that resolves and unpacks the package into a *fresh temp
# environment* on every cold run. A config full of `uvx` entries — which is what
# `sync` propagates to every host — therefore turns "open my agent" into "fetch
# N packages at once", and the 2026-10-06 freeze was a wave of those cold uv
# environments landing while the machine was already short on commit. Preferring
# a locally installed module removes the fetch entirely: same tools, no download,
# no second interpreter, nothing to storm.
RUNNER_MODES = ("prefer-installed", "allow-fetch")

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

# Result-compression modes — what happens to a tool *result* on its way back.
#
#   smart — structure-aware compression on by default (compressor.py): redundant
#           shapes (search results, directory trees, repeated logs) are shrunk
#           with every key kept, and the untruncated original is cached so
#           `mcptoon_retrieve` can hand it back. Unsafe shapes (a lone source
#           file, one long prose answer, binary) are passed through untouched —
#           see compressor.is_compressible. This is the default because the
#           whole point of the gateway is to cost less without being asked.
#   off   — results pass through verbatim. The pre-feature behavior, and the
#           escape hatch for anyone who wants byte-identical output.
#   toon  — the older, lossless re-encoding (JSON→TOON; the saving is shape-dependent,
#           1.8%-48.6% on call results, 11.8% on schemas — never quote a flat number).
COMPRESS_MODES = ("smart", "off", "toon")

# Settings that are a plain on/off switch.
BOOL_MODES = ("on", "off")

# The "am I being used?" presence channel, separate from the savings `footer`.
#
#   on    — after a command that actually routed a call, print one short line to
#           stderr saying so ("▸ mcptoon routed 3 calls"). The point is that the
#           user sees mcptoon *working*, not only what it saved.
#   brief — the same signal, but only when the activity ledger has not been shown
#           recently; quieter, for people who mostly trust it.
#   off   — never print it.
#
# Why its own switch and not folded into `footer`: `footer` is the token-savings
# broadcast. Someone may want to be told "mcptoon is being used" while turning the
# big savings card off, or the reverse. One switch for two different questions
# forced all-or-nothing. Default on — a tool nobody notices is the problem this
# whole channel exists to fix.
PRESENCE_MODES = ("on", "brief", "off")

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
# `welcome` joined on 2026-09-29. It was validated nowhere: the CLI checked
# `footer` and `lang` by hand but not `welcome`, so `config set welcome maybe`
# stored "maybe" and exited 0 — the same silent-acceptance bug the exposure note
# describes, on the one switch whose reader (`welcome_enabled`) treats anything
# not in ("off", "0", "false", "no") as *on*. A typo therefore left the welcome
# banner showing while the user believed they had turned it off.
SETTING_CHOICES = {"exposure": EXPOSURE_MODES, "compress": COMPRESS_MODES,
                   "footer": BOOL_MODES, "welcome": BOOL_MODES,
                   "runners": RUNNER_MODES, "select.engine": SELECT_ENGINES,
                   "presence": PRESENCE_MODES, "receipt": BOOL_MODES}

# Windows LANGID primary-language ids worth naming. Anything unnamed falls back
# to the locale string and then to English, so an unlisted language degrades to
# a correct-but-foreign line rather than to a crash.
_WIN_PRIMARY_LANGS = {0x04: "zh", 0x09: "en"}


def _settings_file() -> Path:
    return Path(os.environ.get("MCPTOON_SETTINGS_FILE", str(SETTINGS_FILE)))


def _welcome_file() -> Path:
    return Path(os.environ.get("MCPTOON_WELCOME_FILE", str(WELCOME_FILE)))


def _cli_aha_file() -> Path:
    return Path(os.environ.get("MCPTOON_CLI_AHA_FILE", str(CLI_AHA_FILE)))


def _selfheal_file() -> Path:
    return Path(os.environ.get("MCPTOON_SELFHEAL_FILE", str(SELFHEAL_FILE)))


def _footer_state_file() -> Path:
    return Path(os.environ.get(
        "MCPTOON_FOOTER_STATE_FILE", str(FOOTER_STATE_FILE)))

# Ensure dirs exist.
#
# Guarded on purpose (issue #25): the old code `mkdir`'d `~/.mcptoon`
# unconditionally, so a user who had moved every path elsewhere still got an
# empty directory in their `$HOME`. Create the directory we are actually going
# to use, and only that one — but always create it, because a missing config
# root is how "mcptoon forgot my servers" starts.
#
# `_AUTO_CREATED` records every directory this process created. `--dir` cannot be
# honoured until argv is read, which is after this module is imported, so on a
# `mcptoon --dir X …` run the legacy directory is created here and only then
# superseded. Remembering what we made lets `apply_home` undo exactly that much.
_AUTO_CREATED: list = []


def _mkdir_tracked(d: Path) -> None:
    """`mkdir -p`, remembering every level this call actually created.

    Two details that are load-bearing, both learned the hard way:

    * `parents=True` can create more than one level (`~/.config/mcptoon` needs
      `~/.config` first), so all of them are recorded, not just the leaf.
    * the recorded order is **deepest first**, and `apply_home` sorts by depth
      again before removing. Removing `~/.mcptoon` before `~/.mcptoon/logs`
      fails with `ENOTEMPTY`, and because the cleanup is best-effort that
      failure is silent — the directory just survives, which is the exact bug
      issue #25 was filed about.
    """
    missing = []
    p = Path(d)
    while not p.exists() and p.parent != p:
        missing.append(p)
        p = p.parent
    Path(d).mkdir(parents=True, exist_ok=True)
    _AUTO_CREATED.extend(missing)


for _d in (CONFIG_DIR, CACHE_DIR, LOG_DIR):
    _mkdir_tracked(_d)
del _d


def apply_home(root) -> None:
    """Rebind every path constant to `root` — the implementation of `--dir`.

    `--dir` arrives on the command line, long after this module was imported and
    its constants computed, so the flag cannot work by setting an environment
    variable: by then the values are already bound. This re-runs the same
    resolution with `MCPTOON_HOME` pinned to `root` and writes the results back
    into the module namespace.

    Two readers have to be re-pointed by hand because they captured the value at
    import time: `usage._USAGE_FILE` (bound from `CACHE_DIR`) and this module's
    own `POLICY_FILE`. `usage` is looked up in `sys.modules` rather than
    imported, because `usage` imports this module — importing it back would be a
    cycle.
    """
    global CONFIG_DIR, CACHE_DIR, STATE_DIR, LOG_DIR, TOGGLE_FILE, POLICY_FILE
    global CONFIG_FILE, CONFIG_FILE_TOML, SETTINGS_FILE, WELCOME_FILE
    global SELFHEAL_FILE, FOOTER_STATE_FILE, CLI_AHA_FILE

    os.environ["MCPTOON_HOME"] = str(root)
    CONFIG_DIR = _resolve_root("XDG_CONFIG_HOME")
    CACHE_DIR = _resolve_cache_root()
    # `cache._cache_dir()` reads `config.CACHE_DIR` live now, but pin the env too:
    # any code (or a future module) that resolves the cache root from the
    # environment must stay inside `--dir X` rather than the real `~/.cache`.
    os.environ["MCPTOON_CACHE_DIR"] = str(CACHE_DIR)
    STATE_DIR = _resolve_state_dir(CONFIG_DIR)
    LOG_DIR = STATE_DIR / "logs"
    TOGGLE_FILE = STATE_DIR / "toggles.json"
    POLICY_FILE = CONFIG_DIR / "compression.json"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    CONFIG_FILE_TOML = CONFIG_DIR / "config.toml"
    SETTINGS_FILE = CONFIG_DIR / "settings.json"
    WELCOME_FILE = CONFIG_DIR / ".welcome"
    SELFHEAL_FILE = CONFIG_DIR / ".selfheal"
    FOOTER_STATE_FILE = CONFIG_DIR / "footer-state.json"
    CLI_AHA_FILE = CONFIG_DIR / ".cli-aha"

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Undo the directories this module created at import time, but only where we
    # made them *and* they are still empty. This is what keeps the promise in
    # issue #25 for the `--dir` path: on `mcptoon --dir X …` the legacy
    # `~/.mcptoon` appears during import, before argv is readable, and would
    # otherwise survive as the empty clutter the report was about. Never removes
    # a directory that holds anything — the emptiness check is the whole safety.
    keep = {CONFIG_DIR, CACHE_DIR, LOG_DIR}
    for d in sorted(_AUTO_CREATED, key=lambda p: len(p.parts), reverse=True):
        if d in keep:
            continue
        try:
            d.rmdir()
        except OSError:
            pass
    _AUTO_CREATED.clear()

    usage_mod = sys.modules.get("mcptoon.usage")
    if usage_mod is not None:
        usage_mod._USAGE_FILE = CACHE_DIR / "usage.json"


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


# ─── Self-reference guard ───
#
# `mcptoon serve` is the gateway itself. `mcptoon sync --self` deliberately
# writes a `mcptoon` entry into an *agent's* config so the model can see the
# gateway. That entry must NEVER end up in mcptoon's OWN server list, because
# `serve` loads that list and would launch a second `mcptoon serve`, which
# loads the same list again — an unbounded fork bomb with no error and no log.
#
# Measured 2026-10-12: 294 live `mcptoon serve` processes, 10.4 GB RAM, count
# still climbing. It arrived via `mcptoon import` / `init --auto`, whose
# scanners read the agent configs that `sync` had (correctly) written.

#: Reserved server name for the gateway's own entry.
SELF_SERVER_NAME = "mcptoon"


def _looks_like_self_command(cfg) -> bool:
    """True when this server entry's argv would launch `mcptoon serve`.

    Compares whole argv *tokens*, never substrings: `python -m mcptoon
    demo-server` runs a different program, and a substring test on "serve"
    would match "demo-**serve**r" and wrongly drop it (a real test,
    `test_self_entry_is_written_and_the_handshake_succeeds`, caught exactly
    that false positive).

    Checks the argv, not just the name, so a self-entry that was renamed still
    gets caught. Both `command` and `args` are accepted as str or list, which
    are the two shapes seen in the wild.
    """
    if not isinstance(cfg, dict):
        return False
    cmd = cfg.get("command")
    if isinstance(cmd, str):
        parts = cmd.split()
    elif isinstance(cmd, list):
        parts = [str(x) for x in cmd]
    else:
        return False
    args = cfg.get("args") or []
    if isinstance(args, list):
        parts += [str(a) for a in args if isinstance(a, (str, int))]
    elif isinstance(args, str):
        parts += args.split()

    def _is_mcptoon_token(tok: str) -> bool:
        base = tok.replace("\\", "/").rsplit("/", 1)[-1].lower()
        for ext in (".exe", ".cmd", ".bat", ".py"):
            if base.endswith(ext):
                base = base[: -len(ext)]
        return base == "mcptoon"

    has_mcptoon = any(_is_mcptoon_token(t) for t in parts)
    has_serve = any(t.replace("\\", "/").rsplit("/", 1)[-1].lower() == "serve"
                    for t in parts)
    return has_mcptoon and has_serve


def _is_self_entry(name, cfg) -> bool:
    """True when this entry would make the gateway launch itself.

    Two independent signals — the reserved name, or a self-launching argv.
    Either one is enough to be a fork bomb.
    """
    if str(name).strip().lower() == SELF_SERVER_NAME:
        return True
    return _looks_like_self_command(cfg)


def strip_self_entries(servers: dict) -> dict:
    """Drop every entry that would make the gateway launch itself.

    Applied on the read path (`load_config`) as well as the write paths, so a
    hand-edited or imported self-entry can never reach a running `serve`.
    """
    if not isinstance(servers, dict):
        return {}
    return {k: v for k, v in servers.items() if not _is_self_entry(k, v)}


# ─── Config loading ───

def _servers_section(data) -> dict:
    """The `servers` mapping of a parsed config document, or {} if it is not one.

    The config file is hand-editable, so it can be *valid* JSON/TOML that is not
    the shape we expect: a top-level list, or `servers` set to a list. `load_config`
    catches parse errors but assumed the parsed value was a dict, so `[1,2,3]` (or
    `{"servers": [1,2]}`) crashed every command that reads the config with
    `AttributeError: 'list' object has no attribute 'get'` instead of being ignored
    the way a syntax error is. This mirrors the `isinstance(data, dict)` guard
    `load_settings` already applies to the same class of hand-edit.
    """
    if not isinstance(data, dict):
        return {}
    section = data.get("servers", {})
    return section if isinstance(section, dict) else {}


def _preserve_unreadable(path: Path, raw: str) -> None:
    """Copy a config file we are about to ignore to `<path>.bak`, once.

    `load_config` used to drop a file it could not honor (bad syntax, or valid
    JSON/TOML that is not the expected shape) and carry on with defaults. That is
    the right *read* behavior — one bad file must not break every command — but it
    is silent data loss: the next `save_config` (any `add`/`remove`/`import
    --write`) rewrites the file from the merged defaults, so the user's hand-edit
    vanishes with no trace. Keeping a `.bak` means the original is recoverable.

    Never clobbers an existing `.bak` — the first snapshot is the one closest to
    the original. Best-effort: a write failure is not worth breaking the read.
    """
    bak = path.with_suffix(path.suffix + ".bak")
    try:
        if not bak.exists():
            bak.write_text(raw, encoding="utf-8")
    except OSError:
        pass


def _load_one_config_file(path: Path, parse) -> dict:
    """The `servers` mapping of one config file, preserving the file if we ignore it."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = parse(raw)
    except ValueError:  # json.JSONDecodeError is a ValueError; _parse_toml raises it too
        _preserve_unreadable(path, raw)
        return {}
    if isinstance(data, dict) and isinstance(data.get("servers", {}), dict):
        return dict(data.get("servers", {}))
    # Parsed, but not the shape we read (e.g. a top-level list, or `servers` a list).
    _preserve_unreadable(path, raw)
    return {}


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
        servers.update(_load_one_config_file(toml_file, _parse_toml))
    if json_file.exists():
        servers.update(_load_one_config_file(json_file, json.loads))

    # 2. Project local config (overrides user) — try TOML first, then JSON
    local_toml = Path(".mcptoon.toml")
    if local_toml.exists():
        servers.update(_load_one_config_file(local_toml, _parse_toml))
    local = Path(".mcptoon.json")
    if local.exists():
        servers.update(_load_one_config_file(local, json.loads))

    # 3. Environment variable (highest priority)
    env_servers = os.environ.get("MCPTOON_SERVERS", "")
    if env_servers:
        try:
            data = json.loads(env_servers)
            servers.update(_servers_section(data))
        except json.JSONDecodeError:
            pass

    # Never hand the gateway its own entry: `serve` would launch itself (fork
    # bomb, measured 2026-10-12). Guard on the read path so it holds for every
    # caller, including a hand-edited config file.
    return strip_self_entries(servers)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` atomically via a unique temp file + os.replace.

    The config is the user's server list — the one thing a bad write destroys for
    good. `save_config` used to call `path.write_text(...)` directly, so a crash,
    a full disk, or a reader landing mid-write could leave a truncated or empty
    `config.json` (the same class of bug the schema cache had; the config is worse
    because it is not regenerable). A unique temp name (mkstemp) also means two
    concurrent writers never share a scratch file, and `os.replace` swaps the whole
    file in one step on both Windows and POSIX.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-cfg-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _backup_before_overwrite(path: Path) -> None:
    """Copy the current config to `<path>.bak` once, before `save_config` replaces it.

    `_preserve_unreadable` only snapshots a file we *could not parse*. The other
    loss path is a perfectly good file being overwritten by a `save_config` that
    wrote the wrong thing — exactly the 2026-10-02 incident where a whole server
    list was replaced by only the new servers "with no `.bak`". Snapshot the last
    good config here too. Never clobbers an existing `.bak`: the first snapshot is
    the one closest to the original, and re-copying on every add would erase the
    pre-edit state. Best-effort — a failed backup must not block the save.
    """
    try:
        if not path.exists():
            return
        bak = path.with_suffix(path.suffix + ".bak")
        if bak.exists():
            return
        raw = path.read_text(encoding="utf-8")
        bak.write_text(raw, encoding="utf-8")
    except OSError:
        pass


def save_config(servers: dict, fmt: str = ""):
    """Save server configuration to user config file.

    Args:
        servers: Server config dict
        fmt: "json" or "toml". If empty, preserves existing format,
              defaults to JSON for new configs.
    """
    # Refuse to persist a self-entry: writing one is what creates the fork bomb
    # on the next `serve` (see `strip_self_entries`).
    servers = strip_self_entries(servers)
    # Determine format: explicit > existing file > default JSON
    json_file = _config_file()
    toml_file = _config_file_toml()
    if not fmt:
        if toml_file.exists() and not json_file.exists():
            fmt = "toml"
        else:
            fmt = "json"

    if fmt == "toml":
        _backup_before_overwrite(toml_file)
        _atomic_write_text(toml_file, _dump_toml(servers))
    else:
        _backup_before_overwrite(json_file)
        _atomic_write_text(
            json_file,
            json.dumps({"servers": servers}, indent=2, ensure_ascii=False),
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


def _coerce_activity_keep(value) -> "int | None":
    """Parse `activity_keep` to an int in range, or None when invalid.

    Accepts an int or a numeric string; rejects bools (True is not 1 here),
    non-numbers, and anything outside [MIN, MAX]. Used both by `set_setting` (to
    validate a write) and `activity_keep` (to guard a hand-edited settings file).
    """
    if isinstance(value, bool):
        return None
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if ACTIVITY_KEEP_MIN <= n <= ACTIVITY_KEEP_MAX:
        return n
    return None


def activity_keep() -> int:
    """How many activity-ledger lines to keep (default 2000, clamped to range).

    Read by `usage._activity_keep()` on every trim. A hand-edited or out-of-range
    value falls back to the default rather than breaking the trimmer — the ledger
    is bookkeeping and must never crash a command.
    """
    n = _coerce_activity_keep(load_settings().get("activity_keep"))
    return n if n is not None else ACTIVITY_KEEP_DEFAULT


def set_setting(key: str, value: str) -> None:
    """Persist one setting. Unknown keys raise ValueError so typos fail loudly."""
    if key not in SETTING_DEFAULTS:
        raise ValueError(
            f"unknown setting {key!r}; known: {', '.join(sorted(SETTING_DEFAULTS))}")
    choices = SETTING_CHOICES.get(key)
    if choices and value not in choices:
        raise ValueError(
            f"{key}={value!r} is not one of {', '.join(choices)}")
    # `activity_keep` is numeric, validated by range rather than a fixed set: a
    # non-number or an out-of-range count is a typo, and failing loudly here is
    # better than writing a value the ledger trimmer silently ignores.
    if key == "activity_keep":
        n = _coerce_activity_keep(value)
        if n is None:
            raise ValueError(
                f"activity_keep={value!r} must be a whole number between "
                f"{ACTIVITY_KEEP_MIN} and {ACTIVITY_KEEP_MAX}")
        value = str(n)
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
    _atomic_write_text(
        path, json.dumps(current, indent=2, ensure_ascii=False))


def _read_settings_raw() -> dict:
    """The settings file as a dict, or {} if missing/unreadable/non-dict."""
    path = _settings_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def unset_setting(key: str) -> str:
    """Remove one setting so it falls back to its default. Returns the default.

    `config set` had no inverse: once you set `lang=en` there was no supported way
    to go back to `auto` short of hand-editing `~/.mcptoon/settings.json`. Unknown
    keys raise ValueError so a typo fails loudly (mirrors `set_setting`). Removing a
    key that is already absent is a no-op success — the effective value is the
    default either way.
    """
    if key not in SETTING_DEFAULTS:
        raise ValueError(
            f"unknown setting {key!r}; known: {', '.join(sorted(SETTING_DEFAULTS))}")
    current = _read_settings_raw()
    if key in current:
        del current[key]
        path = _settings_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(path, json.dumps(current, indent=2, ensure_ascii=False))
    return SETTING_DEFAULTS[key]


def reset_settings() -> None:
    """Reset every setting to its default by clearing the settings file.

    The whole-file inverse of `config set`. We delete the stored overrides rather
    than writing the defaults out, so a future default change is picked up on the
    next run instead of being frozen at today's values.
    """
    path = _settings_file()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def footer_enabled() -> bool:
    """Whether the end-of-turn disclosure is on. Default: on."""
    return get_setting("footer").strip().lower() not in ("off", "0", "false", "no")


def prefer_installed_runners() -> bool:
    """Whether discovery/install should prefer a locally installed module over uvx/npx.

    Default: True (see ``RUNNER_MODES`` for why). A machine that genuinely wants
    the fetch-on-first-run behavior — or one whose packages are installed in an
    interpreter mcptoon cannot see — flips this with
    ``mcptoon config set runners allow-fetch``.
    """
    return get_setting("runners").strip().lower() != "allow-fetch"


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


def compression_mode() -> str:
    """How tool results are compressed by default: "smart" (default) or "off".

    An unrecognized stored value falls back to the default rather than raising —
    a hand-edited settings file must not break the gateway, and "compress the
    redundant shapes" is the intended default.
    """
    value = get_setting("compress").strip().lower()
    return value if value in COMPRESS_MODES else COMPRESS_MODES[0]


def auto_smart_enabled() -> bool:
    """True when results should be compressed without being asked (`--smart`).

    The "install and it just works" half: a fresh install compresses redundant
    results by default. A per-tool policy still overrides this either way, and
    `mcptoon config set compress off` turns it off entirely.
    """
    return compression_mode() == "smart"


def welcome_enabled() -> bool:
    """Whether the one-time first-run welcome may print. Default: on."""
    return get_setting("welcome").strip().lower() not in ("off", "0", "false", "no")


def presence_mode() -> str:
    """The presence channel's level: "on" (default), "brief", or "off".

    An unrecognized stored value falls back to "on" — the safe direction for a
    channel whose whole purpose is being noticed is to keep showing, not to
    silently vanish on a hand-edited typo.
    """
    value = get_setting("presence").strip().lower()
    return value if value in PRESENCE_MODES else PRESENCE_MODES[0]


def presence_enabled() -> bool:
    """Whether the routed-a-call presence line may print at all."""
    return presence_mode() != "off"


def receipt_enabled() -> bool:
    """Whether the per-call CLI receipt (one stderr line after `mcptoon call`) may print.

    On by default — the receipt is the whole point of the CLI-credit work: a call
    that saves something should say so at the moment it happens. `config set
    receipt off` silences it for anyone piping stderr into a log. Kept separate
    from `footer` because the receipt is per-call and specific, while the footer is
    a cumulative block; a user may want one and not the other.
    """
    return get_setting("receipt").strip().lower() not in ("off", "0", "false", "no")


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


def cli_aha_seen() -> bool:
    """True once the one-time first-CLI-call receipt has been shown."""
    try:
        return _cli_aha_file().exists()
    except OSError:
        return False


def mark_cli_aha_seen() -> None:
    """Record that the first-CLI-call receipt has been shown.

    Best-effort, like every other marker: a read-only home must not fail a call,
    and the worst case (the receipt repeats once more) is harmless.
    """
    try:
        path = _cli_aha_file()
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

VALID_POLICIES = ("raw", "json", "auto", "toon", "compact", "slim", "smart")
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

    When nothing pins a format and the caller asked for the default
    (``base_fmt == "auto"``), the result-compression setting decides: a fresh
    install resolves to ``smart`` so results are compressed without anyone
    typing a flag, and ``config set compress off`` restores verbatim output.
    Explicit formats (``--json``, ``--toon``) always win, so this only changes
    the *default*, never a deliberate choice.
    """
    policy = get_compression_policy(server, tool)
    if policy is not None and policy != "auto":
        return policy
    if base_fmt == "auto" and auto_smart_enabled():
        return "smart"
    return base_fmt


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


def has_config_file() -> bool:
    """True when a config exists in **either** supported format.

    `load_config()` reads both `config.toml` and `config.json` (and the
    `config.local.*` overlays), but callers kept gating on `CONFIG_FILE.exists()`
    — the JSON path alone. On a machine whose servers live in `config.toml` that
    made `quickstart` / `init --auto` take the "no config yet" branch and call
    `save_config()`, which sees the TOML file and rewrites it with *only* the new
    servers: the user's whole list was deleted, with no `.bak` (reproduced
    2026-10-02). `doctor` was wrong the other way, reporting "No config found" on
    a machine that had one. Use this instead of `CONFIG_FILE.exists()`.
    """
    return _config_file().exists() or _config_file_toml().exists()


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
