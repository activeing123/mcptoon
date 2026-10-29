"""
mcptoon installer — MCP tool installer.

Features:
  1. Search MCP registry for available servers
  2. Install npm/pip MCP packages
  3. Auto-generate handler files
  4. Verify installation (test connection via MCPClient)

CLI:
  mcptoon install <server-name>          # Install from registry
  mcptoon install --search <keyword>      # Search registries, install nothing
  mcptoon install --npm <package>         # Install from npm
  mcptoon install --pip <package>         # Install from pip
  mcptoon install --url <url>             # Install HTTP/SSE MCP
  mcptoon install --list                  # List installed servers
  mcptoon install --remove <name>          # Remove an installed server
"""
import json
import os
import sys
import subprocess
import re

from .errors import make_error
from .client import MCPClient, MCPError

# MCP Registry URLs — multiple sources for resilience.
#
# Verified live 2026-09-24. The previous values had rotted: ``smithery.ai/api`` answered
# 404 and ``registry.modelcontextprotocol.org`` no longer resolved (NXDOMAIN), and the
# bare ``except Exception: return []`` below turned both into "no results found" — so
# ``mcptoon install <name>`` silently stopped working and nobody noticed. Anything that
# touches these URLs must report failure instead of swallowing it, and
# ``scripts/check_registry_sources.py`` pings them in CI so they cannot rot unseen again.
SMITHERY_API_URL = "https://registry.smithery.ai"
MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0"
# Dropped: ``mcp.so/api`` (500, no public API), Glama (401, needs auth), PulseMCP (403/410).

# Default npx command
_NPX_CMD = "npx"
if os.name == "nt":
    _default_npx = "C:/Program Files/nodejs/npx.cmd"
    if os.path.exists(_default_npx):
        _NPX_CMD = _default_npx

INSTALL_TIMEOUT = 120

# Simple logging fallback
_log_enabled = os.environ.get("MCPTOON_DEBUG", "") != ""
class _Log:
    def info(self, component, msg):
        if _log_enabled:
            sys.stderr.write(f"[{component}] {msg}\n")
    def error(self, component, msg):
        sys.stderr.write(f"[{component}] ERROR: {msg}\n")
log = _Log()

# ─── Installed MCP servers config file ───
# `None` means "ask `config` where the registry lives, on every call". It is
# deliberately not a path constant: `config._installed_registry_file()` owns the
# precedence (explicit env > an existing legacy file > the state dir, which
# follows `MCPTOON_HOME` / `--dir` / XDG — issue #25). A value assigned here
# still wins, which is what lets tests and `mcptoon uninstall` name one path.
#
# Capturing a path at import time was the bug: `--dir X` runs after this module
# is imported, so handlers landed under X while the registry kept being written
# to `$HOME/.mcp-cli/`.
_INSTALLED_FILE = None


def _installed_path() -> str:
    """Where the installed-server registry lives, resolved on every call.

    `config._installed_registry_file()` is the single source of truth: the same
    function `config.state_paths()` reports to `uninstall`, so the two cannot
    disagree about which file is being written and which is being cleaned up.
    """
    if _INSTALLED_FILE is not None:
        return str(_INSTALLED_FILE)
    from . import config
    return str(config._installed_registry_file())


def _write_text_atomic(path, text: str) -> None:
    """Write text to `path` atomically (unique temp + os.replace).

    Generated handler files are regenerable, but a crash mid-write would leave a
    truncated .py that fails to import until the next install. Temp+replace keeps
    the on-disk handler always whole.
    """
    import tempfile

    d = os.path.dirname(str(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".handler-", suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_installed():
    """Load installed MCP servers list."""
    try:
        with open(_installed_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_installed(data):
    """Save installed MCP servers list — atomically.

    A plain open("w") truncates first, so a crash/disk-full mid-write leaves a
    truncated pro_installed.json that `_load_installed` silently reads back as
    {} — total, silent loss of every installed-server record. Write to a unique
    temp file and os.replace instead (same discipline as cache._atomic_write).
    """
    import tempfile

    target = _installed_path()
    d = os.path.dirname(target) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".installed-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class RegistryError(Exception):
    """Every configured registry source failed. Distinct from "no matches"."""


# Words too generic to prove relevance ("mcp server" matches everything).
_RELEVANCE_STOPWORDS = frozenset(
    {"mcp", "server", "servers", "tool", "tools", "the", "and", "for", "with", "api"}
)


def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower())
            if len(t) >= 3 and t not in _RELEVANCE_STOPWORDS]


def _token_matches(a, b):
    """Equal, or one is a prefix of the other ("postgres" ~ "postgresql")."""
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4:
        return a.startswith(b) or b.startswith(a)
    return False


def _relevant(keyword, item):
    """Does ``item`` actually look like a match for ``keyword``?

    Needed because Smithery's search is fuzzy-fallback: it answers *any* query with
    *some* servers, so a typo like ``mcptoon install githbu`` returns five unrelated
    entries instead of nothing — and the old code would then install one of them.
    Requiring a shared significant token keeps fuzzy good matches ("postgres" ->
    "PostgreSQL") while turning genuine non-matches into an honest empty result.
    """
    wanted = _tokens(keyword)
    if not wanted:
        return True  # a query made only of stopwords is a browse, not a search
    hay = _tokens(item.get("name", "")) + _tokens(item.get("description", ""))
    return any(_token_matches(w, h) for w in wanted for h in hay)


def _relevance_score(keyword, item):
    """Rank a match: exact name > name contains > token overlap only."""
    kw = (keyword or "").lower().strip()
    name = (item.get("name") or "").lower()
    tail = name.rstrip("/").split("/")[-1]
    if name == kw or tail == kw:
        return 3
    if kw and kw in name:
        return 2
    return 1


def search_registry(keyword, limit=10, strict=False):
    """Search MCP registries for available servers.

    Queries both sources and merges them, best matches first — Smithery holds the
    hosted half, the official registry the installable-package half, and a query
    like "filesystem" has good answers in both.

    Returns:
        list: [{name, description, command, args, env, source, url}, ...]

    Raises:
        RegistryError: only when *every* source failed at the network level
            (DNS, TLS, timeout, 5xx). A genuine "no matches" still returns [].
            The distinction matters: the old code returned [] for both, so a dead
            registry was indistinguishable from an empty result.
    """
    errors = []
    merged, seen = [], set()

    for label, fn in (("smithery", _search_smithery),
                      ("registry", _search_mcp_registry)):
        try:
            results = fn(keyword, limit)
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}: {str(e)[:120]}")
            continue
        for r in results:
            key = (r.get("name") or "").lower()
            if not key or key in seen or not _relevant(keyword, r):
                continue
            seen.add(key)
            merged.append(r)

    if merged:
        merged.sort(key=lambda r: _relevance_score(keyword, r), reverse=True)
        return merged[:limit]

    # Nothing relevant. If some source was reachable, this is a real empty result;
    # if none was, the network is the problem and we say so.
    if len(errors) == 2:
        raise RegistryError(
            "No MCP registry reachable (" + "; ".join(errors) + "). "
            "Check your connection, or install directly with "
            "`mcptoon install <name> --npm <pkg>`."
        )
    return []


def _fetch_json(url, timeout=10):
    """GET a JSON document. Raises on any failure — never returns a sentinel."""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "mcptoon-installer/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search_smithery(keyword, limit=10):
    """Search the Smithery registry (hosted servers + their tool schemas)."""
    import urllib.parse
    params = urllib.parse.urlencode({"q": keyword, "pageSize": min(limit, 100)})
    data = _fetch_json(f"{SMITHERY_API_URL}/servers?{params}")

    # {"servers": [{id, qualifiedName, displayName, description, verified, useCount, ...}], ...}
    servers = data.get("servers", []) if isinstance(data, dict) else []
    out = []
    for s in servers:
        name = s.get("qualifiedName") or s.get("displayName") or s.get("id", "")
        if not name:
            continue
        out.append({
            "name": name,
            "description": (s.get("description") or "")[:200],
            # Smithery entries are hosted HTTP servers, not local packages: leave the
            # launch command empty so the caller routes to the URL instead of npx.
            # The URL is not in the list payload — ``_smithery_url`` fetches it on demand.
            "command": "",
            "args": [],
            "env": {},
            "source": "smithery",
            "url": "",
            "verified": bool(s.get("verified")),
            "uses": s.get("useCount") or 0,
        })
    return out


def _smithery_url(qualified_name):
    """Fetch the hosted deployment URL for one Smithery server, or "" on failure."""
    try:
        d = _fetch_json(f"{SMITHERY_API_URL}/servers/{qualified_name}")
    except Exception:
        return ""
    return d.get("deploymentUrl") or ""


def _search_mcp_registry(keyword, limit=10):
    """Search the official MCP Registry (the half that ships installable packages)."""
    import urllib.parse
    # The registry's filter parameter is ``search`` — ``q`` is silently ignored and
    # returns the unfiltered list, which looks like a match but is not.
    params = urllib.parse.urlencode({"search": keyword, "limit": min(max(limit * 3, 20), 100)})
    data = _fetch_json(f"{MCP_REGISTRY_URL}/servers?{params}")

    # {"servers": [{"server": {name, description, packages[], remotes[]}, "_meta": {...}}]}
    out, seen = [], set()
    for entry in data.get("servers", []):
        srv = entry.get("server", entry)
        name = srv.get("name", "")
        if not name or name in seen:
            continue
        # The registry lists one row per published version; keep only the latest.
        meta = (entry.get("_meta") or {}).get(
            "io.modelcontextprotocol.registry/official", {})
        if meta and meta.get("isLatest") is False:
            continue
        seen.add(name)

        # Prefer a local package (npm/pypi) so `install` can actually run it; fall
        # back to a hosted remote otherwise.
        packages = srv.get("packages") or []
        command, args, pkg_kind = "", [], ""
        for p in packages:
            rt = (p.get("registryType") or "").lower()
            ident = p.get("identifier", "")
            if not ident:
                continue
            if rt == "npm":
                command, args, pkg_kind = "npx", ["-y", ident], "npm"
                break
            if rt in ("pypi", "python"):
                command, args, pkg_kind = "uvx", [ident], "pypi"
                break

        url = ""
        for r in (srv.get("remotes") or []):
            url = r.get("url", "")
            if url:
                break

        out.append({
            "name": name,
            "description": (srv.get("description") or "")[:200],
            "command": command,
            "args": args,
            "env": {},
            "source": "registry",
            "url": url,
            "kind": pkg_kind,
        })
        if len(out) >= limit:
            break
    return out


def _slug(name):
    """Turn a registry name into a safe config key.

    ``ai.adeu/adeu`` -> ``adeu``; ``@scope/pkg`` -> ``pkg``; ``GitHub`` -> ``github``.
    """
    tail = name.rstrip("/").split("/")[-1] or name
    return re.sub(r"[^a-z0-9_]", "_", tail.lower()).strip("_") or "server"


def _resolve_runner(command):
    """Turn a bare runner name into something a subprocess can actually launch.

    Registry entries say ``npx`` / ``uvx``, but on Windows a bare ``npx`` is often not
    on the PATH a subprocess inherits — which is exactly why ``install_npm`` already
    special-cases the full npx path. Routing must do the same, or a registry install
    fails on Windows while ``--npm`` succeeds.
    """
    import shutil
    if command == "npx":
        return _NPX_CMD if os.path.exists(_NPX_CMD) else (shutil.which("npx") or "npx")
    if command == "uvx":
        return shutil.which("uvx") or "uvx"
    return command


def _prefer_local_package(command, args):
    """Rewrite ``uvx <pkg>`` to ``python -m <module>`` when the package is installed.

    A registry row that ships a PyPI package is launched with ``uvx <pkg>``, which
    fetches and unpacks into a fresh temp environment on every cold run. When that
    package is *already* importable in the interpreter running mcptoon, the same
    server runs with no download and no second interpreter — see
    ``discover._resolve_local_module`` for the freeze that motivates this.

    Returns ``(command, args)`` unchanged when the package is not installed, when
    the user opted out via ``runners=allow-fetch``, or when the row is not a uvx
    row at all. Never raises: a package name that is not a valid module is just
    "not installed locally".
    """
    from .config import prefer_installed_runners
    if command != "uvx" or not prefer_installed_runners():
        return command, args
    args = list(args or [])
    if not args:
        return command, args
    from .discover import _resolve_local_module
    local = _resolve_local_module(str(args[0]).strip().replace("-", "_"))
    if local is None:
        return command, args
    # Anything after the package name is a real argument to the server (a path,
    # a flag) and must survive the runner swap.
    return local[0], list(local[1:]) + [str(a) for a in args[1:]]


def install_by_name(name, server_name=None):
    """Install a server by name from a registry (auto-discover source).

    Usage:
        install_by_name("github")      # searches registries, installs best match
        install_by_name("filesystem")  # same pattern

    Returns:
        dict: Installation result, or an error envelope (see ``make_error``).
    """
    # 1. Search for the server. A RegistryError means the network is down, which
    #    must not be reported as "no such server" — that was the old silent bug.
    try:
        results = search_registry(name)
    except RegistryError as e:
        return make_error("REGISTRY_UNREACHABLE", str(e), "installer")

    if not results:
        return make_error("NOT_FOUND",
            f"No MCP server found matching '{name}'. "
            f"Try: mcptoon install {name} --npm <package>",
            "installer")

    # 2. Prefer an exact name match, else the first result.
    match = next((r for r in results if r.get("name", "").lower() == name.lower()),
                 results[0])

    key = server_name or _slug(match.get("name") or name)
    command = match.get("command") or ""
    args = match.get("args") or []
    url = match.get("url") or ""

    # Smithery's list payload omits the deployment URL, so fetch it — but only now
    # that we know this is the entry being installed, not for every search hit.
    if not command and not url and match.get("source") == "smithery":
        url = _smithery_url(match.get("name") or name)

    # 3. Route to the right installer.
    #    Hosted server (Smithery and many registry remotes): no local package, just a URL.
    if url and not command:
        return install_http(url, key)
    #    Local package: npx for npm, uvx for pypi (both fetch-on-first-run, no install).
    if command:
        resolved = _resolve_runner(command)
        resolved, args = _prefer_local_package(resolved, args)
        return install_custom(key, resolved, args, match.get("env", {}))
    #    Nothing runnable: refuse rather than write a broken config.
    return make_error("NOT_INSTALLABLE",
        f"'{match.get('name')}' is listed but ships no package or URL, so it cannot "
        f"be installed automatically. Add it by hand with "
        f"`mcptoon add {key} --stdio <command>`.",
        "installer")


def install_npm(package, server_name=None):
    """Install MCP server from npm.

    Args:
        package: npm package name (e.g. "@anthropic/mcp-fetch")
        server_name: Custom server name (defaults to last segment of package)

    Returns:
        dict: Installation result
    """
    if not server_name:
        # Extract server_name from package name
        parts = package.split("/")
        server_name = parts[-1].replace("mcp-", "").replace("-", "_")

    # npx -y <package> as launch command
    command = _NPX_CMD if os.path.exists(_NPX_CMD) else "npx"
    args_list = ["-y", package]

    # Verify installation: try to connect
    result = _verify_and_generate(server_name, command, args_list, {}, package)
    return result


def install_pip(package, server_name=None):
    """Install MCP server from pip.

    Args:
        package: pip package name
        server_name: Custom server name

    Returns:
        dict: Installation result
    """
    if not server_name:
        server_name = package.replace("mcp-", "").replace("-", "_")

    # First: pip install
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, timeout=INSTALL_TIMEOUT,
            encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return make_error("INSTALL_FAILED",
                f"pip install failed: {r.stderr[:200]}", "installer")
    except subprocess.TimeoutExpired:
        return make_error("TIMEOUT", f"pip install timeout ({INSTALL_TIMEOUT}s)", "installer")

    # Find executable entry point
    # Most MCP pip packages provide a <name> CLI entry point
    entry_point = package.replace("-", "_").replace("mcp_", "")
    command = sys.executable
    args_list = ["-m", entry_point]

    result = _verify_and_generate(server_name, command, args_list, {}, package)
    return result


def install_custom(server_name, command, args_list, env=None):
    """Install custom MCP server.

    Args:
        server_name: Server name
        command: Launch command
        args_list: Launch arguments
        env: Environment variables

    Returns:
        dict: Installation result
    """
    return _verify_and_generate(server_name, command, args_list, env or {}, "custom")


def install_http(url, server_name=None, transport="auto", headers=None):
    """Install HTTP/SSE MCP server.

    Args:
        url: MCP server URL (e.g. https://example.com/sse)
        server_name: Custom server name
        transport: Transport mode (auto / sse / http)
        headers: HTTP headers for the server. Values may name environment
            variables as ``${NAME}``; they are resolved at request time (issue
            #24), so the token is never written into the config, the generated
            handler or any output.

    Returns:
        dict: Installation result
    """
    if not server_name:
        # Extract server name from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        server_name = parsed.path.rstrip("/").split("/")[-1] or parsed.hostname
        server_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())

    headers = dict(headers or {})

    # Verify connection. The client resolves any `${NAME}` at request time, so
    # this proves the same header mapping the later calls will use — the
    # install-then-401 split the issue asks us to avoid.
    #
    # A failed handshake must come back as an error envelope, never as a Python
    # traceback: this is the first command a new user runs against a remote
    # endpoint, and `MCPClient.initialize` raises `MCPError` for the common
    # cases (connection refused, HTTP 405, a missing `${NAME}`). The sibling
    # stdio path (`_verify_and_generate`) already caught it; this one did not,
    # so `install --url <bad endpoint>` printed a full stack instead of a
    # sentence (found in the 2026-09-26 audit).
    client = MCPClient(http=url, headers=headers)
    try:
        init_result = client.initialize()
    except MCPError as e:
        client.close()
        return make_error("VERIFY_FAILED",
            f"HTTP/SSE MCP server '{server_name}' connection failed: {str(e)[:200]}",
            "installer")

    if isinstance(init_result, Exception):
        client.close()
        return make_error("VERIFY_FAILED",
            f"HTTP/SSE MCP server '{server_name}' connection failed: {str(init_result)[:200]}",
            "installer")

    # Get tool list
    try:
        tools = client.list_tools()
    except Exception:
        tools = []

    client.close()

    # Register the server in the user's config — this is what makes it reachable
    # (issue #36). `install` used to write only a generated handler module into the
    # state dir, and nothing ever imported that module, so `router._HANDLERS`
    # stayed empty: the command reported success while `mcptoon list` did not show
    # the server and `mcptoon call <server>` answered UNKNOWN_SERVER. Config is the
    # one registry `list`/`call` actually read.
    #
    # `transport` is written as "http", not the caller's "auto": the config reader
    # (`client.MCPClient._make_client`) knows only "stdio" and "http" and raises
    # BAD_CONFIG for anything else, and its http branch already negotiates SSE vs
    # streamable HTTP via `http_transport` (default "auto") — which is exactly what
    # "auto" meant here. Writing the raw value would have produced a server that
    # lists and then refuses to start.
    #
    # Header values may be `${NAME}` templates; they stay templates on disk and are
    # resolved at request time (issue #24), so no token is written by this.
    from . import config as _config
    server_cfg = {"transport": "http", "url": url}
    if headers:
        server_cfg["headers"] = dict(headers)
    replaced_existing = server_name in _config.list_servers()
    _config.add_server(server_name, server_cfg)

    # Record to installed.json. This is the schema cache plus install metadata, and
    # it is a separate store on purpose: `install --list`, `install --remove`,
    # `update` and `doctor` read it, while `list`/`call` read the config.
    tools_with_schema = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "inputSchema": t.get("inputSchema", {})}
        for t in tools
    ]
    installed = _load_installed()
    installed[server_name] = {
        "url": url,
        "transport": transport,
        "source": "http",
        "headers": headers,
        "tools": [t.get("name", "") for t in tools],
        "tools_with_schema": tools_with_schema,
        "tool_count": len(tools),
        "installed_at": _now_iso(),
    }
    _save_installed(installed)

    return {
        "status": "installed",
        "server": server_name,
        "tools": len(tools),
        "tool_names": [t.get("name", "") for t in tools][:20],
        "source": "http",
        "url": url,
        "transport": transport,
        "header_names": sorted(headers),
        "replaced_existing": replaced_existing,
    }


def _verify_and_generate(server_name, command, args_list, env, source):
    """Verify installation + auto-generate handler file.

    1. Connect via MCPClient
    2. Call tools/list to get tool list
    3. Generate handler file
    4. Record to installed.json
    """
    # 1. Try to connect
    client = MCPClient(stdio=[command] + (args_list or []))
    try:
        client.initialize()
    except MCPError as e:
        client.close()
        return make_error("VERIFY_FAILED",
            f"MCP server '{server_name}' connection failed: {str(e)[:200]}",
            "installer")

    # 2. Get tool list
    try:
        tools = client.list_tools()
    except Exception:
        tools = []

    client.close()

    # 3. Register in the user's config so the server is actually reachable (#36).
    #
    #    `env` is deliberately NOT written to disk. The child process inherits this
    #    process's environment — `client.MCPClient` starts it with
    #    `os.environ.copy()` and overrides only the names it is given — which is the
    #    same source the generated handler read at call time, so behaviour is
    #    unchanged while a registry-provided value can never be persisted as a
    #    secret.
    from . import config as _config
    server_cfg = {
        "transport": "stdio",
        "command": [command],
        "args": list(args_list or []),
    }
    replaced_existing = server_name in _config.list_servers()
    _config.add_server(server_name, server_cfg)

    # 4. Record to installed.json — preserve full inputSchema
    tools_with_schema = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "inputSchema": t.get("inputSchema", {})}
        for t in tools
    ]
    installed = _load_installed()
    installed[server_name] = {
        "command": command,
        "args": args_list,
        "env": list(env.keys()) if env else [],
        "source": source,
        "tools": [t.get("name", "") for t in tools],
        "tools_with_schema": tools_with_schema,
        "tool_count": len(tools),
        "installed_at": _now_iso(),
    }
    _save_installed(installed)

    return {
        "status": "installed",
        "server": server_name,
        "tools": len(tools),
        "tool_names": [t.get("name", "") for t in tools][:20],
        "source": source,
        "replaced_existing": replaced_existing,
    }


def _handlers_dir():
    """Where older versions wrote generated handler files; created on demand.

    **Nothing writes here any more.** Up to 0.8.31 `install` generated a handler
    module per server, but no code ever imported one (the package contains no
    loader), so ``router._HANDLERS`` was never populated from disk and the servers
    stayed unreachable — that is issue #36. `install` now registers the server in
    the user's config instead, which is the registry `list`/`call` actually read.

    The path is kept for one job: ``remove_installed`` deletes a leftover file here
    so a machine upgraded from ≤ 0.8.31 does not keep stale modules forever.

    It lives under the user's state dir (``config.STATE_DIR/handlers``), **not**
    inside the installed package. Writing into the package directory assumed it
    was writable, which is false for every read-only install: a Nix store path
    (issue #35 — ``PermissionError`` on ``site-packages/mcptoon/handlers``), a
    system-wide ``pip install``, a distro package, or a container image.

    ``MCPTOON_HANDLERS_DIR`` (or ``MCPTOON_HOME``) overrides the location, the same
    way the other state paths are overridable, so tests and CI never write into a
    real home.
    """
    from . import config as _config

    d = str(_config._handlers_state_dir())
    os.makedirs(d, exist_ok=True)
    return d


def list_installed():
    """List installed MCP servers."""
    return _load_installed()


def remove_installed(server_name):
    """Remove an installed MCP server.

    Undoes both halves of what ``install`` does: the config entry (what `list` and
    `call` read) and the ``installed.json`` record (the schema cache that
    `install --list`, `update` and `doctor` read). The two flags are reported
    independently because a server can have one without the other — a record written
    before 0.8.32 has no config entry, and a server added by hand with `mcptoon add`
    has a config entry but no record here.

    ``handler_removed`` covers a module left by a version ≤ 0.8.31, which generated
    one per server that nothing ever imported (issue #36). Nothing writes those now;
    deleting them just keeps an upgraded machine clean.
    """
    installed = _load_installed()
    if server_name not in installed:
        return make_error("NOT_FOUND", f"Server '{server_name}' not installed", "installer")

    # Delete a handler file left by <= 0.8.31
    safe_name = re.sub(r'[^a-z0-9_]', '_', server_name.lower())
    handler_file = os.path.join(_handlers_dir(), f"{safe_name}.py")
    handler_removed = False
    if os.path.exists(handler_file):
        os.remove(handler_file)
        handler_removed = True

    # Drop the config entry. Without this the server would still answer
    # `mcptoon list` and `mcptoon call`, so `--remove` would look like a no-op.
    from . import config as _config
    config_removed = _config.remove_server(server_name)

    # Remove from installed.json
    del installed[server_name]
    _save_installed(installed)

    return {"status": "removed", "server": server_name,
            "handler_removed": handler_removed,
            "config_removed": config_removed}


def _now_iso():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
