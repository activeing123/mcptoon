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

"""mcptoon's own tools — the gateway's first-party surface.

Why these exist
---------------
Until now ``serve`` published *only* what the configured upstream servers
expose. That is the right call for pass-through, but it means a gateway with an
empty config reports an empty ``tools/list`` — so any client (or directory
crawler) that launches it in a clean environment sees a tool-less server and
has nothing to evaluate. The upstream count depends entirely on someone else's
config file.

These tools are the gateway describing itself. They need no upstream
servers, no API keys, no network, and start no subprocesses: they read state
the bridge already holds. They are read-only, and they are namespaced with the
``mcptoon_`` prefix so they never shadow an upstream tool — on a name collision
the upstream definition wins (see :func:`native_names`).

Two of them — ``mcptoon_skills`` and ``mcptoon_resolve_skills`` — expose the
skill catalog that ``mcptoon skills`` already keeps on disk. They exist so a
connected agent can reach the catalog *over MCP* instead of shelling out: the
gateway is then a skill router as well as a tool gateway, and an agent that
never sees a skill list in its prompt can still resolve one by task. Both are
read-only; ``resolve`` records the same usage counts the CLI does.

Keep the wording inside the budget enforced by ``schema_simplifier`` (descriptions
<= 360 chars / 3 sentences, parameter docs <= 200 chars / 2 sentences) so this
project's own gateway never truncates its own catalog. ``tests/test_native_tools.py``
pins that.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .schema_simplifier import namespaced_tool_name, simplify_tool_def

# Names of the first-party tools, in listing order.
NATIVE_NAMES = (
    "mcptoon_manifest",
    "mcptoon_servers",
    "mcptoon_health",
    "mcptoon_usage",
    "mcptoon_skills",
    "mcptoon_resolve_skills",
    "mcptoon_inspect",
    "mcptoon_call",
)


def native_tools() -> list[dict]:
    """Full MCP tool definitions for the gateway's own tools."""
    return [
        {
            "name": "mcptoon_manifest",
            "title": "Tool manifest",
            "description": (
                "List the upstream tools this gateway currently exposes, grouped by server. "
                "Returns names by default; that compact view is what an agent should read "
                "instead of pulling every full schema. Pass include_descriptions for a "
                "one-line summary per tool."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": (
                            "Restrict the listing to one server name. Omit to list every "
                            "server the gateway has loaded."
                        ),
                    },
                    "include_descriptions": {
                        "type": "boolean",
                        "description": (
                            "Attach each tool's first description sentence to the listing. "
                            "Costs tokens; the default false keeps the manifest small."
                        ),
                    },
                },
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "servers": {
                        "type": "array",
                        "description": "One entry per server that contributed tools.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "toolCount": {"type": "integer"},
                                "tools": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {
                                                "type": "string",
                                                "description": (
                                                    "Only present when include_descriptions "
                                                    "was set; omitted to keep the manifest small."
                                                ),
                                            },
                                        },
                                        "required": ["name"],
                                    },
                                },
                            },
                            "required": ["name", "toolCount", "tools"],
                        },
                    },
                    "totalServers": {"type": "integer"},
                    "totalTools": {"type": "integer"},
                },
                "required": ["servers", "totalServers", "totalTools"],
            },
            "annotations": {
                "title": "Tool manifest",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_servers",
            "title": "Configured servers",
            "description": (
                "Report the MCP servers configured behind this gateway: transport, tool "
                "count and whether their tools loaded. Use it to see what is actually "
                "reachable before calling a tool, and to spot a server that configured "
                "but published nothing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": (
                            "Report one server by name instead of all of them. Aliases "
                            "resolve to the canonical server name."
                        ),
                    },
                },
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "servers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "transport": {
                                    "type": "string",
                                    "description": "stdio, http or unknown.",
                                },
                                "toolCount": {"type": "integer"},
                                "loaded": {
                                    "type": "boolean",
                                    "description": "True if the gateway indexed its tools.",
                                },
                            },
                            "required": ["name", "transport", "toolCount", "loaded"],
                        },
                    },
                    "configured": {"type": "integer"},
                },
                "required": ["servers", "configured"],
            },
            "annotations": {
                "title": "Configured servers",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_health",
            "title": "Gateway self-check",
            "description": (
                "Self-check of this gateway process: version, config path, servers "
                "configured, tools indexed and uptime. Read this first when a tool you "
                "expect is missing; it distinguishes an empty config from a server that "
                "failed to load."
            ),
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "ok, degraded, error or starting.",
                    },
                    "version": {"type": "string"},
                    "python": {"type": "string"},
                    "configPath": {"type": "string"},
                    "serversConfigured": {"type": "integer"},
                    "toolsIndexed": {"type": "integer"},
                    "failedServers": {"type": "integer"},
                    "outputFormat": {"type": "string"},
                    "uptimeSeconds": {"type": "number"},
                },
                "required": ["status", "version", "serversConfigured", "toolsIndexed"],
            },
            "annotations": {
                "title": "Gateway self-check",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_usage",
            "title": "Token savings so far",
            "description": (
                "How much this gateway has saved: tools compressed, tokens saved and the "
                "session call count. Call this when you want to tell the user what mcptoon "
                "did. Report these numbers verbatim; never estimate them yourself."
            ),
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {
                "type": "object",
                "properties": {
                    "toolsCompressed": {"type": "integer"},
                    "tokensSaved": {"type": "integer"},
                    "savingsPct": {"type": "number"},
                    "callsRecorded": {
                        "type": "integer",
                        "description": "Calls mcptoon has recorded, cumulative across sessions.",
                    },
                    "footerEnabled": {
                        "type": "boolean",
                        "description": "False when the user turned the disclosure off.",
                    },
                },
                "required": ["toolsCompressed", "tokensSaved", "savingsPct", "footerEnabled"],
            },
            "annotations": {
                "title": "Token savings so far",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_skills",
            "title": "Skill catalog",
            "description": (
                "List the skills mcptoon indexes on this machine: slug and one-line "
                "description per skill. Read it once to learn what skills exist, then "
                "resolve the one you need with mcptoon_resolve_skills. Offline and "
                "read-only; pass include_aliases to also see alias cards."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include_aliases": {
                        "type": "boolean",
                        "description": (
                            "Include alias cards, not only canonical skills. The "
                            "default false keeps one row per real skill."
                        ),
                    },
                },
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "skills": {
                        "type": "array",
                        "description": "One entry per skill, sorted by slug.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slug": {"type": "string"},
                                "desc": {"type": "string"},
                            },
                            "required": ["slug", "desc"],
                        },
                    },
                    "totalSkills": {"type": "integer"},
                },
                "required": ["skills", "totalSkills"],
            },
            "annotations": {
                "title": "Skill catalog",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_resolve_skills",
            "title": "Resolve skills for a task",
            "description": (
                "Return the skills that best match a task description, best first. "
                "Call this with the user's request before acting, then read the chosen "
                "skill's SKILL.md. Offline BM25 ranking, no LLM."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "What the user wants to do, in their own words. More detail "
                            "ranks better than a single keyword."
                        ),
                    },
                    "k": {
                        "type": "integer",
                        "description": (
                            "How many candidates to return. The default 5 is enough to "
                            "pick from; larger only when the top few look wrong."
                        ),
                    },
                },
                "required": ["task"],
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer"},
                    "shortlist": {
                        "type": "array",
                        "description": "Best matches first, each with its BM25 score.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slug": {"type": "string"},
                                "score": {"type": "number"},
                                "desc": {"type": "string"},
                            },
                            "required": ["slug", "score"],
                        },
                    },
                },
                "required": ["query", "k", "shortlist"],
            },
            "annotations": {
                "title": "Resolve skills for a task",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_inspect",
            "title": "Inspect one tool's parameters",
            "description": (
                "Show one upstream tool's full input schema — the parameters to call it "
                "with. Read-only; nothing runs. Use it after mcptoon_manifest names a tool."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": (
                            "Namespaced name from mcptoon_manifest, e.g. fetch_fetch. A "
                            "bare name works when only one server owns it."
                        ),
                    },
                    "server": {
                        "type": "string",
                        "description": (
                            "Server that owns the tool; disambiguates a shared bare name."
                        ),
                    },
                },
                "required": ["tool"],
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "server": {"type": "string"},
                    "inputSchema": {"type": "object"},
                },
                "required": ["tool", "server", "inputSchema"],
            },
            "annotations": {
                "title": "Inspect one tool's parameters",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "mcptoon_call",
            "title": "Call any upstream tool",
            "description": (
                "Run any upstream tool by its namespaced name (server_tool). Under the "
                "default compact exposure the tool list is withheld, so this is how you "
                "run one found via mcptoon_manifest. Arguments are validated first."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Namespaced name in server_tool form, e.g. fetch_fetch.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Arguments object for the tool; see mcptoon_inspect.",
                    },
                },
                "required": ["name"],
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "server": {"type": "string"},
                    "result": {},
                },
                "required": ["tool", "server"],
            },
            "annotations": {
                "title": "Call any upstream tool",
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": True,
            },
        },
    ]


def is_native(name: str) -> bool:
    return name in NATIVE_NAMES


def _transport_of(cfg: Any) -> str:
    """Best-effort transport label from a server config entry."""
    if not isinstance(cfg, dict):
        return "unknown"
    if cfg.get("command"):
        return "stdio"
    if cfg.get("url") or cfg.get("serverUrl"):
        return "http"
    return "unknown"


def _first_sentence(text: str) -> str:
    for sep in (". ", "! ", "? "):
        i = text.find(sep)
        if i != -1:
            return text[: i + 1].strip()
    return text.strip()


def _as_str(value: Any) -> str:
    """Tolerate junk from a client: only strings are usable as filters."""
    return value.strip() if isinstance(value, str) else ""


def _as_bool(value: Any) -> bool:
    """Accept the shapes agents actually send, without crashing on any of them."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def _as_int(value: Any, default: int, minimum: int = 1) -> int:
    """Coerce a client-supplied count, falling back rather than raising.

    Agents send ``k`` as a string or a float often enough that a strict read
    would turn a usable call into an error; a bad value is simply ignored.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            return default
    if not isinstance(value, int) or value < minimum:
        return default
    return value


def _manifest(arguments: dict, state: dict) -> dict:
    want_server = _as_str(arguments.get("server"))
    with_desc = _as_bool(arguments.get("include_descriptions"))
    index = state["tool_index"]

    by_server: dict[str, list[str]] = {}
    for ns_name, info in index.items():
        server = info.get("server", "")
        if want_server and server != want_server:
            continue
        by_server.setdefault(server, []).append(info.get("tool", ns_name))

    servers = []
    for name in sorted(by_server):
        tools = sorted(by_server[name])
        entries = []
        for tool in tools:
            entry = {"name": tool}
            if with_desc:
                full = index.get(namespaced_tool_name(name, tool), {}).get("full_def", {})
                entry["description"] = _first_sentence(full.get("description", "") or "")
            entries.append(entry)
        servers.append({"name": name, "toolCount": len(tools), "tools": entries})

    total_tools = sum(s["toolCount"] for s in servers)
    payload = {
        "servers": servers,
        "totalServers": len(servers),
        "totalTools": total_tools,
    }
    if not servers:
        hint = (
            "No upstream tools indexed. This gateway publishes only what your configured "
            "servers expose; run `mcptoon add <name> --stdio <command>` (or `mcptoon demo-server` "
            "for a local test bed) and then `mcptoon manifest` on the CLI."
        )
        payload["notice"] = hint
    return payload


def _servers(arguments: dict, state: dict) -> dict:
    want_server = _as_str(arguments.get("server"))
    configured = state["servers"]
    index = state["tool_index"]

    counts: dict[str, int] = {}
    for info in index.values():
        counts[info.get("server", "")] = counts.get(info.get("server", ""), 0) + 1

    rows = []
    for name in sorted(configured):
        if want_server and name != want_server:
            continue
        rows.append({
            "name": name,
            "transport": _transport_of(configured[name]),
            "toolCount": counts.get(name, 0),
            "loaded": counts.get(name, 0) > 0,
        })
    if want_server and not rows:
        rows.append({"name": want_server, "transport": "unknown", "toolCount": 0, "loaded": False})
    out = {"servers": rows, "configured": len(configured)}
    if not configured:
        out["notice"] = (
            "No servers configured yet. The gateway is running; add one with "
            "`mcptoon add <name> --stdio <command>` or point MCPTOON_CONFIG at a config file."
        )
    return out


def _health(arguments: dict, state: dict) -> dict:  # noqa: ARG001 - uniform signature
    from . import __version__
    from .config import _config_file

    configured = state["servers"]
    index = state["tool_index"]
    loaded = {info.get("server") for info in index.values()}
    failed = sum(1 for name in configured if name not in loaded)

    if not state.get("initialized"):
        status = "starting"
    elif configured and failed == len(configured):
        status = "error"
    elif failed:
        status = "degraded"
    else:
        status = "ok"

    try:
        cfg_path = str(_config_file())
    except Exception:  # pragma: no cover - defensive
        cfg_path = ""

    return {
        "status": status,
        "version": __version__,
        "python": os.sys.version.split()[0],
        "configPath": cfg_path,
        "serversConfigured": len(configured),
        "toolsIndexed": len(index),
        "failedServers": failed,
        "outputFormat": state.get("output_format", "auto"),
        "uptimeSeconds": round(state.get("uptime", 0.0), 1),
        "nativeTools": list(NATIVE_NAMES),
    }


def _usage(arguments: dict, state: dict) -> dict:  # noqa: ARG001 - uniform signature
    """Real savings numbers. The disclosure footer reads these, never an estimate.

    Tokens are a static property of the catalog (raw JSON vs the compressed
    manifest), so they are stable for a given tool set; calls are the cumulative
    ledger. Both come from the same code path the ``mcptoon stats`` CLI uses, so
    the CLI and the footer can never disagree.
    """
    from . import usage as usage_mod
    from .config import footer_enabled

    index = state["tool_index"]
    full_tokens = 0
    slim_tokens = 0
    for info in index.values():
        full_def = info.get("full_def") or {}
        if not full_def or "error" in full_def:
            continue
        full_tokens += len(json.dumps(full_def, ensure_ascii=False)) // 4
        slim_tokens += len(json.dumps(simplify_tool_def(full_def), ensure_ascii=False)) // 4

    saved = max(0, full_tokens - slim_tokens)
    pct = round(saved / full_tokens * 100, 1) if full_tokens else 0.0

    try:
        stats = usage_mod.get_usage_stats()
        calls = int(stats.get("total_calls", 0))
    except Exception:  # pragma: no cover - defensive
        calls = 0

    return {
        "toolsCompressed": len(index),
        "tokensSaved": saved,
        "savingsPct": pct,
        "callsRecorded": calls,
        "footerEnabled": footer_enabled(),
    }


def _skills(arguments: dict, state: dict) -> dict:  # noqa: ARG001 - uniform signature
    """The skill catalog the CLI already keeps, exposed over MCP.

    Read-only. Delegates the projection to :func:`skills.catalog_rows` so this
    tool and `mcptoon skills list` can never disagree.
    """
    from . import skills as skills_mod

    skills_mod.ensure_index()  # first call builds it; a stale one is refreshed
    rows = skills_mod.catalog_rows(
        skills_mod.load_index(), include_aliases=_as_bool(arguments.get("include_aliases")))
    payload = {"skills": rows, "totalSkills": len(rows)}
    if not rows:
        payload["notice"] = (
            "No skill index yet, and no skill roots were found to build one. "
            "Set MCPTOON_SKILLS_ROOTS or run `mcptoon skills index <path>`."
        )
    return payload


def _resolve_skills(arguments: dict, state: dict) -> dict:  # noqa: ARG001 - uniform signature
    """Best skills for a task, ranked by the same BM25 the CLI uses.

    Offline and instant; records usage so `mcptoon skills list --usage` counts
    MCP resolutions too.
    """
    from . import skills as skills_mod

    task = _as_str(arguments.get("task"))
    k = _as_int(arguments.get("k"), 5, minimum=1)
    if not task:
        return {"query": "", "k": k, "shortlist": [],
                "notice": "Pass a non-empty `task` describing what the user wants to do."}
    skills_mod.ensure_index()  # a fresh install answers instead of erroring
    shortlist = skills_mod.resolve_shortlist(task, k)
    payload = {"query": task, "k": k, "shortlist": shortlist}
    if not shortlist:
        payload["notice"] = (
            "No skill matched. The catalog may be empty (`mcptoon skills index`) or the "
            "wording may not match; try the user's own words, or mcptoon_skills to list."
        )
    return payload


def _inspect(arguments: dict, state: dict) -> dict:
    """One upstream tool's real input schema — the parameters to call it with.

    The discovery half of the compact-exposure contract: `mcptoon_manifest` gives
    names, this gives the arguments, and the tool is then called by its namespaced
    name. Read-only — nothing is executed here.
    """
    index = state["tool_index"]
    want_server = _as_str(arguments.get("server"))
    want_tool = _as_str(arguments.get("tool"))

    if not want_tool:
        return {"tool": "", "server": "", "inputSchema": {},
                "notice": "Pass `tool` — a namespaced name like fetch_fetch, or a bare "
                          "tool name when only one server owns it."}

    def _resolve() -> tuple[str, str]:
        if want_tool in index:  # exact namespaced hit
            return want_tool, index[want_tool].get("server", "")
        if want_server:
            ns = namespaced_tool_name(want_server, want_tool)
            if ns in index:
                return ns, want_server
        matches = [ns for ns, info in index.items()
                   if info.get("tool") == want_tool and (not want_server or info.get("server") == want_server)]
        if len(matches) == 1:
            return matches[0], index[matches[0]].get("server", "")
        return "", ""

    ns_name, server = _resolve()
    if not ns_name:
        known = [ns for ns in index][:10]
        return {"tool": want_tool, "server": want_server, "inputSchema": {},
                "notice": f"Unknown tool: '{want_tool}'. Call mcptoon_manifest to list what "
                          f"is loaded" + (f". A few: {', '.join(known)}" if known else ".")}

    info = index[ns_name]
    full_def = info.get("full_def") or {}
    schema = info.get("full_schema") or full_def.get("inputSchema") or {}
    return {
        "tool": ns_name,
        "server": server,
        "description": _first_sentence(full_def.get("description", "") or ""),
        "inputSchema": schema,
    }


_HANDLERS = {
    "mcptoon_manifest": _manifest,
    "mcptoon_servers": _servers,
    "mcptoon_health": _health,
    "mcptoon_usage": _usage,
    "mcptoon_skills": _skills,
    "mcptoon_resolve_skills": _resolve_skills,
    "mcptoon_inspect": _inspect,
    # "mcptoon_call" is routed by the bridge to the upstream tool; it has no
    # handler here because it must reuse the bridge's pool, validation and
    # compression rather than duplicate them (see serve._handle_call_tool).
}


def call_native(name: str, arguments: dict, state: dict) -> dict:
    """Run a first-party tool and return an MCP tool result.

    ``state`` is assembled by the bridge: ``servers`` (config dict), ``tool_index``
    (namespaced index), ``output_format``, ``initialized``, ``uptime``. Unknown
    names raise KeyError — the caller checks :func:`is_native` first.
    """
    arguments = arguments if isinstance(arguments, dict) else {}
    payload = _HANDLERS[name](arguments, state)
    text = json.dumps(payload, ensure_ascii=False, indent=None)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
        "resultType": "complete",
    }
