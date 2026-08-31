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

"""Agent Plugins Specification 1.0.0 support.

The Agent Plugins spec (https://agent-plugins.org/specification) defines how
an AI agent plugin is PACKAGED: a folder with plugin.json (identity) +
skills/ (SKILL.md) + mcp.json (MCP server configs). It deliberately leaves
installation, distribution and cross-agent sync undefined — that is exactly
mcptoon's job: install once, every agent can use it.

This module implements the read-only validator (scan) and the installer
(install / list / remove). Only spec 1.0.0 is anchored; draft versions
(1.1.0+) are rejected loudly. Zero third-party dependencies, per repo policy.

Installer design (the pivot): mcptoon IS the installer, so it owns the paths.
${PLUGIN_ROOT} / ${PLUGIN_DATA} are pre-expanded into absolute paths at merge
time and written into ~/.mcptoon/config.json, from where the existing sync
flow carries them into every agent's native config — no client cooperation
required.
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

from .config import CONFIG_DIR

PLUGIN_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

PLUGIN_ROOT_VAR = "${PLUGIN_ROOT}"
PLUGIN_DATA_VAR = "${PLUGIN_DATA}"

# plugin.json top-level: closed list. Unknown keys → warning (ignored).
_PLUGIN_TOP_KEYS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
}

# author sub-object: closed list per spec; unknown nested keys → warning.
_AUTHOR_KEYS = {"name", "email", "url"}

# Valid plugin name: 1-64 chars, a-z 0-9 - . only, first/last alphanumeric,
# no consecutive "--" or "..".
_NAME_RE = re.compile(r"^(?:[a-z0-9]|[a-z0-9][a-z0-9.-]{0,62}[a-z0-9])$")

# Bare command token: a single executable name. No slashes, no whitespace,
# no shell metacharacters, no "$" (commands are never expanded).
_BARE_COMMAND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_SHELL_META_CHARS = set('|&;<>()$`"\'' + '\n\r\t')

# Header names that must never appear in mcp.json headers (spec: config
# files must not hold credentials).
_CREDENTIAL_HEADER_PARTS = (
    "password", "passwd", "secret", "token", "apikey", "api-key",
    "authorization", "private-key", "privatekey",
)


# ═══════════════════════════════════════════════════
# Placeholder expansion (spec §variables)
# ═══════════════════════════════════════════════════

def expand_placeholders(text: str, plugin_root: str, plugin_data: str) -> str:
    """Expand ${PLUGIN_ROOT} / ${PLUGIN_DATA} — single, non-recursive pass.

    One regex substitution pass: replacement text is never rescanned, so a
    root path that literally contains "${PLUGIN_DATA}" stays as-is after
    expansion. Callers must only apply this to args elements, env values and
    cwd — never to command, env keys, url or headers (spec forbids it there).
    """
    values = {"PLUGIN_ROOT": plugin_root, "PLUGIN_DATA": plugin_data}
    return _VAR_RE.sub(lambda m: values[m.group(1)], text)


_VAR_RE = re.compile(r"\$\{(PLUGIN_ROOT|PLUGIN_DATA)\}")


def _unknown_placeholder(text: str) -> str | None:
    """Return the first ${...} token that is NOT one of the two known vars."""
    for m in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text):
        if m.group(0) not in (PLUGIN_ROOT_VAR, PLUGIN_DATA_VAR):
            return m.group(0)
    return None


# ═══════════════════════════════════════════════════
# Scan
# ═══════════════════════════════════════════════════

def scan_plugin(plugin_dir: str) -> dict:
    """Validate a plugin directory against spec 1.0.0.

    Returns a report dict:
      ok              True when no fatal problems (plugin is installable)
      dir             the scanned directory
      plugin          {name, version, description}
      skills          [skill names]  (skills/*/SKILL.md, one level)
      servers         [{name, type}] — valid mcp.json entries only
      skipped_servers [{name, reason}] — invalid entries (skippable, non-fatal)
      fatal           [{code, message, path}] — reject the whole plugin
      warnings        [{code, message, path}] — report + ignore / skipped

    Failure classification follows the spec's failure boundaries:
    structural problems in plugin.json / mcp.json are fatal; problems in a
    single mcpServers entry skip that entry but keep the plugin loadable.
    """
    root = Path(plugin_dir)
    report = {
        "ok": True,
        "dir": str(root),
        "plugin": {"name": None, "version": None, "description": None},
        "skills": [],
        "servers": [],
        "skipped_servers": [],
        "fatal": [],
        "warnings": [],
    }

    def fatal(code, message, path):
        report["fatal"].append({"code": code, "message": message, "path": path})

    def warn(code, message, path):
        report["warnings"].append({"code": code, "message": message, "path": path})

    if not root.is_dir():
        fatal("PLUGIN_DIR_MISSING", f"plugin directory not found: {root}", str(root))
        report["ok"] = False
        return report

    _scan_manifest(root, report, fatal, warn)
    if report["fatal"]:
        report["ok"] = False
        return report

    _scan_mcp_json(root, report, fatal, warn)
    _scan_skills(root, report)
    report["ok"] = not report["fatal"]
    return report


# ─── plugin.json ───

def _load_json_file(path: Path) -> tuple[dict | None, str | None]:
    """Load a JSON file. Returns (data, error_message)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"cannot read {path.name}: {e}"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"{path.name} is not valid JSON: {e}"
    if not isinstance(data, dict):
        return None, f"{path.name} must be a JSON object"
    return data, None


def _scan_manifest(root: Path, report, fatal, warn):
    mf_path = root / "plugin.json"
    if not mf_path.is_file():
        fatal("MANIFEST_MISSING", "plugin.json not found", str(mf_path))
        return

    manifest, err = _load_json_file(mf_path)
    if err:
        fatal("MANIFEST_INVALID", err, str(mf_path))
        return

    # $schema: exact match to 1.0.0 (we anchor 1.0.0 only)
    schema = manifest.get("$schema")
    if schema != PLUGIN_SCHEMA_URL:
        fatal(
            "SCHEMA_MISMATCH",
            f'plugin.json $schema must be exactly "{PLUGIN_SCHEMA_URL}" '
            f"(got {schema!r}; only spec 1.0.0 is supported)",
            str(mf_path),
        )

    # name: required, strict pattern
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        fatal("NAME_MISSING", "plugin.json name is required", str(mf_path))
    elif len(name) > 64 or not _NAME_RE.match(name) or "--" in name or ".." in name:
        fatal(
            "NAME_INVALID",
            f'plugin name {name!r} violates spec rules (1-64 chars, a-z 0-9 - . '
            "only, starts/ends alphanumeric, no -- or ..)",
            str(mf_path),
        )
    else:
        report["plugin"]["name"] = name

    # Optional top-level fields: closed list, unknown → warning
    for key in manifest:
        if key not in _PLUGIN_TOP_KEYS:
            warn("UNKNOWN_FIELD", f'unknown top-level field "{key}" (ignored)', str(mf_path))

    # Typed optional fields — violations here are schema violations → fatal
    version = manifest.get("version")
    if version is not None and not isinstance(version, str):
        fatal("VERSION_INVALID", "version must be a string", str(mf_path))
    else:
        report["plugin"]["version"] = version

    description = manifest.get("description")
    if description is not None and not isinstance(description, str):
        fatal("DESCRIPTION_INVALID", "description must be a string", str(mf_path))
    else:
        report["plugin"]["description"] = description

    for key in ("homepage", "repository", "license"):
        val = manifest.get(key)
        if val is not None and not isinstance(val, str):
            fatal(f"{key.upper()}_INVALID", f"{key} must be a string", str(mf_path))

    keywords = manifest.get("keywords")
    if keywords is not None:
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            fatal("KEYWORDS_INVALID", "keywords must be a list of strings", str(mf_path))

    extensions = manifest.get("extensions")
    if extensions is not None and not isinstance(extensions, dict):
        fatal("EXTENSIONS_INVALID", "extensions must be an object", str(mf_path))

    author = manifest.get("author")
    if author is not None:
        if not isinstance(author, dict):
            fatal("AUTHOR_INVALID", "author must be an object", str(mf_path))
        else:
            for k in author:
                if k not in _AUTHOR_KEYS:
                    warn("UNKNOWN_FIELD", f'unknown author field "{k}" (ignored)', str(mf_path))
            for k in ("name", "email", "url"):
                if k in author and not isinstance(author[k], str):
                    fatal("AUTHOR_INVALID", f"author.{k} must be a string", str(mf_path))


# ─── mcp.json ───

def _scan_mcp_json(root: Path, report, fatal, warn):
    mcp_path = root / "mcp.json"
    if not mcp_path.is_file():
        return  # optional per spec (skills-only plugins are valid)

    data, err = _load_json_file(mcp_path)
    if err:
        fatal("MCP_JSON_INVALID", err, str(mcp_path))
        return

    if data.get("$schema") != MCP_SCHEMA_URL:
        fatal(
            "SCHEMA_MISMATCH",
            f'mcp.json $schema must be exactly "{MCP_SCHEMA_URL}" '
            f"(got {data.get('$schema')!r})",
            str(mcp_path),
        )

    for key in data:
        if key not in ("$schema", "mcpServers"):
            fatal(
                "MCP_JSON_UNKNOWN_FIELD",
                f'mcp.json top-level field "{key}" is not allowed (closed schema)',
                str(mcp_path),
            )

    mcp_servers = data.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        fatal("MCPSERVERS_INVALID", "mcpServers must be an object", str(mcp_path))
        return

    for server_name, entry in mcp_servers.items():
        _scan_server_entry(str(server_name), entry, root, report, warn)


def _scan_server_entry(server_name, entry, root: Path, report, warn):
    """Validate one mcpServers entry. Entry-level problems are skippable
    (non-fatal) per the spec's failure boundaries."""
    mcp_path = str(root / "mcp.json")
    where = f"mcp.json:mcpServers.{server_name}"

    def skip(reason, code="ENTRY_INVALID"):
        report["skipped_servers"].append({"name": server_name, "reason": reason})
        warn(code, f"{where}: {reason}", mcp_path)

    if not isinstance(server_name, str) or not server_name:
        skip("server name must be a non-empty string")
        return
    if not isinstance(entry, dict):
        skip("entry must be an object")
        return

    entry_type = entry.get("type")
    if entry_type == "stdio":
        _scan_stdio(server_name, entry, root, report, skip)
    elif entry_type in ("streamable-http", "sse"):
        _scan_remote(server_name, entry, report, skip)
    else:
        skip(f'unknown or missing type: {entry_type!r} (expected stdio, streamable-http or sse)')


def _scan_stdio(server_name, entry, root: Path, report, skip):
    # Closed union: only stdio's own fields allowed
    allowed = {"type", "command", "args", "env", "cwd"}
    for key in entry:
        if key not in allowed:
            skip(f'unknown field "{key}" in stdio entry (closed union)')
            return

    command = entry.get("command")
    if not isinstance(command, str) or not command:
        skip("stdio command is required and must be a string")
        return

    # Command must be a single token: bare name or ./ relative path.
    # Never a shell string, never expanded.
    if "$" in command or any(c in _SHELL_META_CHARS for c in command) or " " in command:
        skip(
            f'command {command!r} is not a single executable token '
            "(shell strings and placeholder expansion are forbidden in command)"
        )
        return

    if command.startswith("./"):
        rel = command[2:]
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            skip(f"command path {command!r} must stay inside the plugin")
            return
        target = root / rel
        try:
            resolved = Path(os.path.realpath(target))
            allowed_root = Path(os.path.realpath(root))
            if os.name == "nt" and resolved.drive != allowed_root.drive:
                skip(f"command path {command!r} resolves outside the plugin drive")
                return
            if not str(resolved).startswith(str(allowed_root)):
                skip(f"command path {command!r} resolves outside the plugin root (path escape)")
                return
        except OSError as e:
            skip(f"command path {command!r} cannot be resolved: {e}")
            return
    elif command.startswith(("/", "~", ".\\", "C:", "\\")) or (len(command) > 1 and command[1] == ":"):
        skip(
            f"command {command!r} must be a bare executable name or a './' "
            "plugin-relative path (absolute paths are forbidden)"
        )
        return
    elif not _BARE_COMMAND_RE.match(command):
        skip(f"command {command!r} is not a valid bare executable token")
        return

    # args: optional list of strings; placeholders allowed here
    args = entry.get("args")
    if args is not None:
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            skip("args must be a list of strings")
            return
        for a in args:
            unknown = _unknown_placeholder(a)
            if unknown:
                report["warnings"].append({
                    "code": "UNKNOWN_PLACEHOLDER",
                    "message": f"mcp.json:mcpServers.{server_name}: "
                               f'unknown placeholder ${{{unknown}}} in args (left as-is)',
                    "path": str(root / "mcp.json"),
                })

    # env: optional dict[str, str]; reserved keys forbidden; only values expand
    env = entry.get("env")
    if env is not None:
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()
        ):
            skip("env must be an object of string keys and string values")
            return
        for k in env:
            if k in ("PLUGIN_ROOT", "PLUGIN_DATA"):
                skip(
                    f'env entry "{k}" uses a reserved variable name — '
                    "the client injects these automatically"
                )
                return
            unknown = _unknown_placeholder(env[k])
            if unknown:
                report["warnings"].append({
                    "code": "UNKNOWN_PLACEHOLDER",
                    "message": f"mcp.json:mcpServers.{server_name}: "
                               f'unknown placeholder ${{{unknown}}} in env "{k}" (left as-is)',
                    "path": str(root / "mcp.json"),
                })

    # cwd: only ./relative, ${PLUGIN_ROOT}[/...], ${PLUGIN_DATA}[/...]
    cwd = entry.get("cwd")
    if cwd is not None:
        if not isinstance(cwd, str) or not _cwd_allowed(cwd):
            skip(
                f"cwd {cwd!r} is not allowed (only ./relative, "
                "${PLUGIN_ROOT}[/...] or ${PLUGIN_DATA}[/...])"
            )
            return
        unknown = _unknown_placeholder(cwd)
        if unknown:
            report["warnings"].append({
                "code": "UNKNOWN_PLACEHOLDER",
                "message": f"mcp.json:mcpServers.{server_name}: "
                           f'unknown placeholder ${{{unknown}}} in cwd (left as-is)',
                "path": str(root / "mcp.json"),
            })

    report["servers"].append({"name": server_name, "type": "stdio"})


def _cwd_allowed(cwd: str) -> bool:
    if cwd.startswith("./"):
        return ".." not in Path(cwd[2:]).parts
    for var in (PLUGIN_ROOT_VAR, PLUGIN_DATA_VAR):
        if cwd == var:
            return True
        if cwd.startswith(var + "/") and ".." not in Path(cwd[len(var) + 1:]).parts:
            return True
    return False


def _scan_remote(server_name, entry, report, skip):
    allowed = {"type", "url", "headers"}
    for key in entry:
        if key not in allowed:
            skip(f'unknown field "{key}" in {entry.get("type")} entry (closed union)')
            return

    url = entry.get("url")
    if not isinstance(url, str) or not url:
        skip("url is required and must be a string")
        return

    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        skip(f"url {url!r} must be absolute http/https")
        return
    if parsed.fragment:
        skip(f"url {url!r} must not contain a fragment")
        return
    if parsed.username or parsed.password:
        skip(f"url {url!r} must not contain user info")
        return

    host = parsed.hostname or ""
    loopback = host in ("localhost", "::1") or (
        host.startswith("127.") and all(p.isdigit() and 0 <= int(p) <= 255 for p in host.split("."))
    )
    if parsed.scheme != "https" and not loopback:
        skip(f"url {url!r} is non-loopback and must use HTTPS")
        return

    headers = entry.get("headers")
    if headers is not None:
        if not isinstance(headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
        ):
            skip("headers must be an object of string keys and string values")
            return
        for k in headers:
            kl = k.lower()
            if any(part in kl for part in _CREDENTIAL_HEADER_PARTS):
                skip(
                    f'header "{k}" looks like a credential — the spec forbids '
                    "storing credentials in plugin config files"
                )
                return

    report["servers"].append({"name": server_name, "type": entry.get("type")})


# ─── skills ───

def _scan_skills(root: Path, report):
    """skills/*/SKILL.md — one level, never recursive."""
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        return
    try:
        children = sorted(p for p in skills_dir.iterdir() if p.is_dir())
    except OSError:
        return
    for child in children:
        if (child / "SKILL.md").is_file():
            report["skills"].append(child.name)
        else:
            report["warnings"].append({
                "code": "SKILL_INCOMPLETE",
                "message": f'skills/{child.name} has no SKILL.md — skipped',
                "path": str(child),
            })


# ═══════════════════════════════════════════════════
# Installer (phase 2): install / list / remove
# ═══════════════════════════════════════════════════

# Paths are env-overridable so tests and CI never touch the real ~/.mcptoon
def _plugins_dir() -> Path:
    return Path(os.environ.get(
        "MCPTOON_PLUGINS_DIR", str(CONFIG_DIR / "plugins")))


def _plugins_data_dir() -> Path:
    return Path(os.environ.get(
        "MCPTOON_PLUGINS_DATA_DIR", str(CONFIG_DIR / "plugins-data")))


def _registry_file() -> Path:
    return Path(os.environ.get(
        "MCPTOON_PLUGINS_REGISTRY", str(CONFIG_DIR / "plugins.json")))


def _load_registry() -> dict:
    """Registry: {plugin_name: {version, installed_at, servers, source}}"""
    path = _registry_file()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(reg: dict):
    path = _registry_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_server_entry(server_name: str, entry: dict,
                        plugin_root: Path, plugin_data: Path) -> dict | None:
    """Convert a plugin mcpServers entry into a mcptoon config entry.

    Pre-expands ${PLUGIN_ROOT} / ${PLUGIN_DATA} (args elements, env values,
    cwd only — never command / env keys / url / headers) into absolute paths,
    and records both paths so the pool can inject the env vars the spec
    requires at server start.
    """
    root_s = str(plugin_root)
    data_s = str(plugin_data)

    def xp(text: str) -> str:
        """Expand placeholders and normalize separators for the host OS."""
        return os.path.normpath(expand_placeholders(text, root_s, data_s))

    etype = entry.get("type")
    if etype == "stdio":
        cfg: dict = {
            "transport": "stdio",
            "command": [entry["command"]],
            "args": [xp(a) for a in entry.get("args", [])],
            "plugin_root": root_s,
            "plugin_data": data_s,
        }
        if entry.get("env"):
            cfg["env"] = {k: xp(v) for k, v in entry["env"].items()}
        if entry.get("cwd"):
            cfg["cwd"] = xp(entry["cwd"])
        return cfg
    if etype in ("streamable-http", "sse"):
        cfg = {
            "transport": "http",
            "url": entry["url"],
            "plugin_root": root_s,
            "plugin_data": data_s,
        }
        if entry.get("headers"):
            cfg["headers"] = dict(entry["headers"])
        return cfg
    return None  # unreachable: scan filtered types already


def install_plugin(source: str, force: bool = False,
                   sync_agents: bool = True) -> dict:
    """Install an Agent Plugin into mcptoon and every synced agent.

    Steps: scan (reject invalid) → copy to ~/.mcptoon/plugins/<name>/
    (create persistent data dir) → merge mcpServers into config.json under
    "<plugin>:<server>" namespaces with pre-expanded paths → trigger sync.

    The plugin data directory survives `--force` upgrades (spec §PLUGIN_DATA).
    """
    source_path = Path(source)
    report = scan_plugin(str(source_path))
    if not report["ok"]:
        return {"ok": False, "stage": "scan", "fatal": report["fatal"]}

    name = report["plugin"]["name"]
    version = report["plugin"].get("version", "")
    dest = _plugins_dir() / name
    data_dir = _plugins_data_dir() / name

    if dest.exists():
        if not force:
            return {
                "ok": False, "stage": "conflict",
                "message": f'plugin "{name}" is already installed '
                           f"at {dest} — use --force to upgrade",
            }
        shutil.rmtree(dest)

    try:
        shutil.copytree(source_path, dest)
    except (shutil.Error, OSError) as e:
        return {"ok": False, "stage": "copy", "message": f"copy failed: {e}"}

    # Persistent data dir: created if missing, NEVER deleted on upgrade
    data_dir.mkdir(parents=True, exist_ok=True)

    # Merge the plugin's servers into config.json under namespace
    from .config import load_config, save_config

    dest_report = scan_plugin(str(dest))
    installed_servers: list[str] = []
    servers = load_config()
    mcp_data, _ = _load_json_file(dest / "mcp.json")
    mcp_servers = (mcp_data or {}).get("mcpServers", {})
    for s in dest_report["servers"]:
        sname = s["name"]
        entry = _build_server_entry(
            sname, mcp_servers[sname], dest, data_dir)
        if entry is None:
            continue
        ns = f"{name}:{sname}"
        servers[ns] = entry
        installed_servers.append(ns)
    save_config(servers)

    reg = _load_registry()
    reg[name] = {
        "version": version,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "servers": installed_servers,
        "source": str(source_path),
    }
    _save_registry(reg)

    result = {
        "ok": True,
        "name": name,
        "version": version,
        "dest": str(dest),
        "data_dir": str(data_dir),
        "servers": installed_servers,
        "skills": dest_report["skills"],
    }

    if sync_agents:
        result["sync"] = _trigger_sync()
    return result


def _trigger_sync() -> dict:
    """Run the existing sync flow so every agent picks up the new servers."""
    try:
        from .sync import sync_to_all
        results = sync_to_all(dry_run=False)
        ok = sum(1 for r in results if r.get("ok"))
        return {"synced_agents": ok, "total_agents": len(results)}
    except Exception as e:  # sync must never break an install
        return {"error": str(e)[:200]}


def list_plugins() -> list[dict]:
    """List installed plugins from the registry."""
    reg = _load_registry()
    out = []
    for name in sorted(reg):
        info = reg[name]
        out.append({
            "name": name,
            "version": info.get("version", ""),
            "installed_at": info.get("installed_at", ""),
            "servers": info.get("servers", []),
        })
    return out


def _prune_from_agents(names: list[str]) -> dict:
    """Remove namespaced entries from every detected agent's native config.

    sync() merges — it never deletes — so removals would otherwise linger in
    agent configs forever. This prunes exactly the removed "<plugin>:<server>"
    entries, touching nothing else (manual servers stay put)."""
    from .sync import (
        _read_json_safe,
        _write_json_safe,
        detect_installed_agents,
    )

    pruned = 0
    for agent in detect_installed_agents():
        path = Path(agent["config_path"])
        if not path.exists():
            continue
        data = _read_json_safe(path)
        changed = False
        if isinstance(data.get("mcpServers"), dict):
            for n in names:
                if data["mcpServers"].pop(n, None) is not None:
                    changed = True
        elif isinstance(data.get("mcp"), dict) and isinstance(
                data["mcp"].get("servers"), dict):
            for n in names:
                if data["mcp"]["servers"].pop(n, None) is not None:
                    changed = True
        if changed:
            if _write_json_safe(path, data):
                pruned += 1
    return {"pruned_agents": pruned}


def remove_plugin(name: str, sync_agents: bool = True) -> dict:
    """Remove a plugin: namespace entries in config.json, the plugin
    directory, and re-sync agents. The persistent data directory is KEPT
    (spec treats ${PLUGIN_DATA} as client-managed persistent storage)."""
    reg = _load_registry()
    if name not in reg:
        return {"ok": False, "message": f'plugin "{name}" is not installed'}

    ns_servers = list(reg[name].get("servers", []))
    from .config import load_config, save_config

    servers = load_config()
    removed = []
    for key in ns_servers:
        if key in servers:
            del servers[key]
            removed.append(key)
    # Defensive: also drop any namespace entries missing from the registry
    prefix = f"{name}:"
    for key in [k for k in servers if k.startswith(prefix)]:
        del servers[key]
        removed.append(key)
    save_config(servers)

    plugin_dir = _plugins_dir() / name
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir, ignore_errors=True)

    data_dir = _plugins_data_dir() / name
    del reg[name]
    _save_registry(reg)

    result = {
        "ok": True,
        "name": name,
        "removed_servers": removed,
        "data_dir_kept": str(data_dir) if data_dir.exists() else None,
    }
    if sync_agents:
        result["sync"] = _prune_from_agents(removed)
    return result
