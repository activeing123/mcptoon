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

"""`mcptoon update` — refresh the tool surface mcptoon captured from each server.

MCP servers move underneath you: a tool gains a required argument, a server adds
or retires a tool, an ``npx`` package cuts a release. mcptoon keeps a snapshot of
each server's tool surface in two places — the schema cache (`cache.py`, what
`manifest`/`call` serve) and, for installed servers, the generated handler plus
`pro_installed.json`. When the server moves, those snapshots go stale: an agent
then calls a tool with the wrong arguments, or cannot see a tool that now exists.

``mcptoon update`` re-reads every configured server's live tool list, diffs it
against the snapshot mcptoon is currently trusting, writes the fresh surface back
(both cache and, when present, the installed record + handler), and reports
exactly what moved: ``+added`` / ``-removed`` / ``~changed``.

Deliberately NOT a pip package upgrade. mcptoon's runners are not pinned
(``npx -y <pkg>``, ``uvx <pkg>``), so they already fetch the current release on
the next start — the version is not what rots. The *snapshot mcptoon took* is.
That is the thing this command repairs.

CLI:
    mcptoon update              Refresh every configured server, report the drift
    mcptoon update --check      Report only; write nothing; exit 1 if anything moved
    mcptoon update <name>       Refresh one server
    mcptoon update --json       Machine-readable result
"""

from __future__ import annotations

import json
import sys

from . import cache as cache_mod
from .config import load_config
from .client import MCPClientPool

__all__ = ["diff", "probe", "run"]


def _sig(tool) -> tuple:
    """A tool's callable signature: name + required args + property names.

    Exactly the fields whose change makes a previously-valid call wrong, so a
    server that renames a parameter or starts requiring one shows up as
    ``changed`` rather than being silently missed.
    """
    if not isinstance(tool, dict):
        return ("?", (), ())
    schema = tool.get("inputSchema") or {}
    req = tuple(sorted(schema.get("required") or []))
    props = tuple(sorted((schema.get("properties") or {}).keys()))
    return (tool.get("name", "?"), req, props)


def _named(tools) -> dict:
    """{name: signature} for a tool list, dropping error placeholders."""
    out = {}
    for t in tools or []:
        if isinstance(t, dict) and "error" not in t:
            out[t.get("name", "?")] = _sig(t)
    return out


def diff(old_tools, new_tools) -> tuple:
    """(added, removed, changed) tool names between two surfaces.

    Pure and order-independent, so the CLI and the tests agree on what "moved"
    means without spawning a server.
    """
    old, new = _named(old_tools), _named(new_tools)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(n for n in set(old) & set(new) if old[n] != new[n])
    return added, removed, changed


def probe(servers: dict, name: str) -> tuple:
    """Read one server's live tool list. Returns (tools, error_message).

    Each server gets its own pool so one dead server cannot abort the sweep —
    updating a fleet must report the broken member, not stop at it.
    """
    if name not in servers:
        return None, f"'{name}' is not in the config"
    pool = MCPClientPool({name: servers[name]})
    try:
        return pool.list_tools(name), None
    except Exception as e:  # MCPError and anything a bad server can raise
        return None, str(e)[:200]
    finally:
        pool.close()


def _refresh_installed(name: str, tools: list, write: bool) -> bool:
    """Refresh the installed record + generated handler for ``name`` if it exists.

    Returns True when a record was found (and updated, if ``write``). The handler
    carries a baked SCHEMA, so a server that gained a tool leaves the handler
    advertising the old set until it is regenerated — this is that regeneration.
    """
    from . import installer

    installed = installer._load_installed()
    rec = installed.get(name)
    if not rec:
        return False
    if not write:
        return True

    tools_with_schema = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "inputSchema": t.get("inputSchema", {})}
        for t in tools
    ]
    rec["tools"] = [t.get("name", "") for t in tools]
    rec["tools_with_schema"] = tools_with_schema
    rec["tool_count"] = len(tools)
    rec["updated_at"] = installer._now_iso()

    if rec.get("url"):
        installer._generate_http_handler_file(
            name, tools, rec["url"], rec.get("transport", "auto"),
            rec.get("headers") or {})
    else:
        command = rec.get("command", "")
        installer._generate_handler_file(
            name, tools, command, rec.get("args", []), rec.get("env", []),
            rec.get("source", "custom"))

    installer._save_installed(installed)
    return True


def _sweep(servers: dict, names: list, *, write: bool) -> list:
    """Probe each server, diff against the cache, optionally write the new surface."""
    results = []
    for name in names:
        tools, err = probe(servers, name)
        if err:
            results.append({"server": name, "status": "error", "error": err,
                            "added": [], "removed": [], "changed": [], "tools": 0})
            continue

        old_tools, _age = cache_mod.get_cached_tools_any_age(name)
        if old_tools is None:
            results.append({"server": name, "status": "seeded", "tools": len(tools),
                            "added": [], "removed": [], "changed": []})
        else:
            added, removed, changed = diff(old_tools, tools)
            status = "unchanged" if not (added or removed or changed) else "updated"
            results.append({"server": name, "status": status, "tools": len(tools),
                            "added": added, "removed": removed, "changed": changed})

        if write:
            cache_mod.set_cached_tools(name, tools)
            _refresh_installed(name, tools, write=True)
    return results


def _render(results: list, *, checked: bool) -> str:
    """Human report. One line per server, with the moved names spelled out."""
    lines = []
    moved = 0
    for r in results:
        name, status = r["server"], r["status"]
        if status == "error":
            lines.append(f"  ✗ {name:20s} unreachable — {r['error']}")
            continue
        if status == "seeded":
            lines.append(f"  + {name:20s} cached ({r['tools']} tools)")
            continue
        if status == "unchanged":
            lines.append(f"  ✓ {name:20s} unchanged ({r['tools']} tools)")
            continue
        moved += 1
        bits = []
        if r["added"]:
            bits.append("+" + ",".join(r["added"]))
        if r["removed"]:
            bits.append("-" + ",".join(r["removed"]))
        if r["changed"]:
            bits.append("~" + ",".join(r["changed"]))
        lines.append(f"  ! {name:20s} changed ({r['tools']} tools): {' '.join(bits)}")

    errors = sum(1 for r in results if r["status"] == "error")
    seeded = sum(1 for r in results if r["status"] == "seeded")
    if moved:
        verb = "would refresh" if checked else "refreshed"
        lines.append(f"\n  {moved} server(s) {verb}; "
                     f"{'run without --check to apply' if checked else 'cache + handlers up to date'}")
    elif seeded:
        lines.append(f"\n  {seeded} server(s) cached for the first time.")
    else:
        lines.append("\n  Everything up to date.")
    if errors:
        lines.append(f"  {errors} server(s) unreachable — see above.")
    return "\n".join(lines)


def run(rest: list, fmt: str = "auto") -> None:
    """CLI entry: ``mcptoon update [<name>] [--check] [--json]``."""
    check = any(a in ("--check", "--dry", "--dry-run") for a in rest)
    only = next((a for a in rest if not a.startswith("-")), None)

    servers = load_config()
    if not servers:
        print("No servers configured. Run: mcptoon quickstart")
        return

    if only and only not in servers:
        print(f"Server not found: {only}")
        print(f"Configured: {', '.join(sorted(servers))}")
        sys.exit(1)

    names = [only] if only else sorted(servers)
    results = _sweep(servers, names, write=not check)

    if fmt == "json":
        print(json.dumps({"checked": check, "servers": results}, indent=2,
                         ensure_ascii=False))
    else:
        print(_render(results, checked=check))

    drifted = any(r["status"] == "updated" for r in results)
    errored = any(r["status"] == "error" for r in results)
    if errored or (check and drifted):
        sys.exit(1)
