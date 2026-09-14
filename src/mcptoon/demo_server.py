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
mcptoon demo-server — a self-contained MCP server, standard library only.

Why this module exists (2026-09-14). mcptoon is a gateway: `mcptoon serve`
answers `tools/list` by proxying upstream servers, so on a machine with no
configured servers it answers with an empty array. Every demo server we have
pointed at so far had to be fetched with `npx`, and hosted evaluation sandboxes
(Glama's TDQS scorer) run a Python image with no Node in it — so the listing they
grade is empty and the server is never scored at all. That is an unread exam, not
a bad one.

`demo-server` is the part of the answer that is guaranteed legible anywhere Python
runs: eleven tools built from this package's own pure functions, with no network
access, no subprocess, no user configuration and no third-party import, so it
returns the same tool set in a bare container as on a laptop.

It is still a remote control, not a runtime: nothing here registers itself.
`mcptoon serve` keeps proxying whatever you configure, and these eleven tools
appear only if you add this server explicitly:

Usage:
  mcptoon demo-server                       # stdio MCP server, 11 tools
  python -m mcptoon demo-server             # same, no PATH entry needed
  mcptoon add demo --stdio python -m mcptoon demo-server
  mcptoon demo --help                       # this help
"""

from __future__ import annotations

import json
import platform
import sys

from . import __version__
from . import output as output_mod
from . import schema_simplifier
from .client import ERR_UNSUPPORTED_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS
from .serve import (
    PROTOCOL_VERSION,
    _list_cache_fields,
    _make_error_response,
    _make_success,
    _make_tool_error,
    _make_tool_result,
)

SERVER_NAME = "mcptoon-demo"


class DemoToolError(Exception):
    """A tool-level failure: reported in the MCP result, not as a JSON-RPC error."""


# Archived measurements from assets/benchmark_tiktoken.json (tiktoken cl100k_base,
# full name index). Inlined because assets/ is not packaged into the wheel — see
# tests/test_demo_server.py, which fails if these constants drift from that file.
BENCHMARK_ROWS = [
    {"tools": 5, "json": 1519, "toon": 1003, "slim": 147, "compact": 11,
     "toon_save_pct": 34.0, "slim_save_pct": 90.3, "compact_save_pct": 99.3},
    {"tools": 50, "json": 14113, "toon": 9287, "slim": 1624, "compact": 114,
     "toon_save_pct": 34.2, "slim_save_pct": 88.5, "compact_save_pct": 99.2},
    {"tools": 255, "json": 71929, "toon": 47438, "slim": 8282, "compact": 581,
     "toon_save_pct": 34.0, "slim_save_pct": 88.5, "compact_save_pct": 99.2},
]

# The agent targets `mcptoon sync` knows about. Values are the path helpers in
# sync.py, which only read environment variables — nothing is opened or stat'd.
AGENT_PATH_HELPERS = (
    ("claude-desktop", "_claude_desktop_path"),
    ("cursor", "_cursor_path"),
    ("cline", "_cline_path"),
    ("windsurf", "_windsurf_path"),
    ("vscode-copilot", "_vscode_copilot_path"),
)

_PREVIEW_CHARS = 500


# ─── argument plumbing ───────────────────────────────────────────────────────

def _need(args: dict, key: str) -> str:
    value = (args or {}).get(key)
    if not isinstance(value, str) or not value.strip():
        raise DemoToolError(f"missing required string argument '{key}'")
    return value


def _need_json(args: dict, key: str):
    """Parse a JSON document handed over as a string.

    A string parameter keeps every tool's schema flat (one string, no nested
    objects), which is also what a client that re-serialises arguments survives.
    """
    raw = _need(args, key)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DemoToolError(
            f"argument '{key}' is not valid JSON ({exc.msg} at char {exc.pos}); "
            f"pass the document itself, not a path to it"
        ) from None


def _size(text: str) -> int:
    return max(len(text) // 4, 1)


def _preview(text: str) -> str:
    if len(text) <= _PREVIEW_CHARS:
        return text
    return text[:_PREVIEW_CHARS] + f" … [{len(text) - _PREVIEW_CHARS} more chars]"


# ─── tools ───────────────────────────────────────────────────────────────────

def _t_echo_message(args):
    message = _need(args, "message")
    return {
        "echo": message,
        "chars": len(message),
        "estimated_tokens": _size(message),
        "transformed": False,
    }


def _t_compare_formats(args):
    value = _need_json(args, "payload")
    forms = {
        "json": json.dumps(value, ensure_ascii=False),
        "toon": output_mod.toon_encode(value),
        "compact": output_mod.compact(value),
    }
    baseline = len(forms["json"])
    out = {}
    for name, text in forms.items():
        stats = schema_simplifier.compute_token_stats(forms["json"], text)
        out[name] = {
            "chars": len(text),
            "estimated_tokens": stats["full_tokens"] if name == "json" else stats["simplified_tokens"],
            "char_savings_pct": round(100.0 * (1 - len(text) / max(baseline, 1)), 1),
            "preview": _preview(text),
        }
    return {"formats": out, "slim_note": (
        "SLIM is a manifest-only encoding for MCP tool definitions; use "
        "simplify_tool_schema for that.")}


def _t_encode_toon(args):
    value = _need_json(args, "payload")
    text = output_mod.toon_encode(value)
    return {"toon": _preview(text), "chars": len(text), "truncated": len(text) > _PREVIEW_CHARS}


def _t_decode_toon(args):
    text = _need(args, "toon")
    try:
        decoded = output_mod.toon_decode(text)
    except Exception as exc:  # the vendored decoder raises on any malformed line
        raise DemoToolError(f"TOON decode failed: {exc}") from None
    return {"decoded": decoded, "round_trip": json.dumps(decoded, ensure_ascii=False, sort_keys=True)}


def _t_estimate_tokens(args):
    text = _need(args, "text")
    return {
        "chars": len(text),
        "estimated_tokens": _size(text),
        "method": "characters divided by four, floor",
        "bias": "undercounts CJK and other multi-byte text by roughly 2-4x; "
                "not a substitute for a real tokenizer",
    }


def _t_simplify_tool_schema(args):
    tool = _need_json(args, "tool")
    if not isinstance(tool, dict) or not tool.get("name"):
        raise DemoToolError("argument 'tool' must be one MCP tool definition object with a 'name'")
    full_json = json.dumps(tool, ensure_ascii=False)
    slim = schema_simplifier.simplify_tool_def(tool)
    slim_json = json.dumps(slim, ensure_ascii=False)
    return {
        "slim_tool": slim,
        **schema_simplifier.compute_token_stats(full_json, slim_json),
        "rules_applied": {
            "description": f"first sentence, max {schema_simplifier._MAX_DESC_LEN} chars",
            "enum_values_kept": schema_simplifier._MAX_ENUM_KEEP,
            "schema_keys_dropped": sorted(schema_simplifier._STRIP_TOP_KEYS),
        },
    }


def _t_build_tool_manifest(args):
    raw = _need_json(args, "manifest")
    groups: dict[str, list] = {}
    if isinstance(raw, dict):
        groups = {str(k): (v if isinstance(v, list) else [v]) for k, v in raw.items()}
    elif isinstance(raw, list):
        groups = {"default": raw}
    else:
        raise DemoToolError("argument 'manifest' must be {server: [tool]} or [tool, ...]")

    names_by_server: dict[str, list[str]] = {}
    skipped: list[str] = []
    for server, tools in groups.items():
        names = []
        for index, tool in enumerate(tools):
            if isinstance(tool, str) and tool.strip():
                names.append(tool.strip())
            elif isinstance(tool, dict) and tool.get("name"):
                names.append(str(tool["name"]))
            else:
                skipped.append(f"{server}[{index}]")
        names_by_server[server] = names

    indexed = {s: v for s, v in names_by_server.items() if v}
    empty_servers = [s for s, v in names_by_server.items() if not v]
    index_text = " · ".join(f"{s}: {', '.join(v)}" for s, v in indexed.items())
    full_json = json.dumps(raw, ensure_ascii=False)
    if indexed:
        stats = schema_simplifier.compute_token_stats(full_json, index_text)
    else:
        # No usable names at all: claiming a saving against an empty index would be
        # a number out of thin air, so report the input size and say nothing saved.
        stats = {"full_tokens": _size(full_json), "simplified_tokens": 0, "reduction_pct": 0.0}
    out = {
        "name_index": index_text,
        "tool_count": sum(len(v) for v in names_by_server.values()),
        "skipped_entries": skipped,
        "empty_servers": empty_servers,
        **stats,
    }
    if (args or {}).get("include_slim"):
        out["slim_tools"] = [
            schema_simplifier.simplify_tool_def(t)
            for tools in groups.values() for t in tools if isinstance(t, dict)
        ]
    return out


def _t_report_benchmark_rows(args):
    return {
        "encoding": "tiktoken cl100k_base",
        "source": "assets/benchmark_tiktoken.json, measured once on a fixed synthetic corpus",
        "measured_at_build_time": True,
        "rows": BENCHMARK_ROWS,
    }


def _t_list_supported_agents(args):
    from . import sync as sync_mod  # path helpers only; no files are read

    agents = []
    for agent_id, getter in AGENT_PATH_HELPERS:
        paths = getattr(sync_mod, getter)()
        agents.append({
            "id": agent_id,
            "config_paths": [str(p) for p in (paths if isinstance(paths, list) else [paths])],
        })
    return {"platform": sys.platform, "agents": agents, "installed_check": "not performed"}


def _t_validate_config_draft(args):
    draft = _need_json(args, "config")
    if not isinstance(draft, dict):
        raise DemoToolError("argument 'config' must be a JSON object")
    servers = draft.get("mcpServers") if "mcpServers" in draft else draft
    if not isinstance(servers, dict) or not servers:
        raise DemoToolError(
            "no server entries found: pass either {'mcpServers': {name: {...}}} "
            "or {name: {...}} directly")

    known = {"type", "command", "args", "env", "url", "headers", "disabled", "autoStart"}
    entries = []
    for name, cfg in servers.items():
        problems = []
        if not isinstance(cfg, dict):
            problems.append("entry is not an object")
            entries.append({"name": name, "transport": "unknown", "problems": problems})
            continue
        has_command = isinstance(cfg.get("command"), str) and cfg.get("command").strip()
        has_url = isinstance(cfg.get("url"), str) and cfg.get("url").strip()
        if has_command and has_url:
            problems.append("both 'command' and 'url' set; mcptoon would pick stdio")
        if not has_command and not has_url:
            problems.append("neither 'command' nor 'url' set; entry is unusable")
        if has_command and "args" in cfg and not isinstance(cfg["args"], list):
            problems.append("'args' must be an array of strings")
        if has_command and "args" in cfg and isinstance(cfg["args"], list):
            if any(not isinstance(a, str) for a in cfg["args"]):
                problems.append("'args' contains a non-string element")
        if "env" in cfg and not isinstance(cfg["env"], dict):
            problems.append("'env' must be an object of string keys to string values")
        unknown = sorted(set(cfg) - known)
        if unknown:
            problems.append(f"unrecognised keys ignored by mcptoon: {', '.join(unknown)}")
        entries.append({
            "name": name,
            "transport": "stdio" if has_command else ("http" if has_url else "none"),
            "problems": problems,
        })
    return {
        "entry_count": len(entries),
        "entries": entries,
        "not_checked": [
            "whether the command exists on PATH",
            "whether the server actually starts or answers",
            "whether the tools it exposes are valid",
        ],
    }


def _t_describe_runtime(args):
    try:
        from importlib import metadata
        requires = metadata.metadata("mcptoon").get_all("Requires-Dist") or []
    except Exception:
        requires = None  # running from a source tree: no installed metadata to read
    return {
        "mcptoon_version": __version__,
        "server_name": SERVER_NAME,
        "tool_count": len(TOOLS),
        "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "third_party_runtime_dependencies": (
            "metadata unavailable, running from a source tree" if requires is None
            else [r for r in requires if "extra" not in r.lower()]),
    }


HANDLERS = {
    "echo_message": _t_echo_message,
    "compare_formats": _t_compare_formats,
    "encode_toon": _t_encode_toon,
    "decode_toon": _t_decode_toon,
    "estimate_tokens": _t_estimate_tokens,
    "simplify_tool_schema": _t_simplify_tool_schema,
    "build_tool_manifest": _t_build_tool_manifest,
    "report_benchmark_rows": _t_report_benchmark_rows,
    "list_supported_agents": _t_list_supported_agents,
    "validate_config_draft": _t_validate_config_draft,
    "describe_runtime": _t_describe_runtime,
}


def _tool(name: str, title: str, description: str, properties: dict,
          required: list[str]) -> dict:
    """Build one tool definition; annotations are identical because every tool here
    is a pure function of its arguments."""
    schema = {"type": "object", "properties": properties, "required": required}
    if required:
        schema["additionalProperties"] = False
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "title": title,
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


def _prop(description: str) -> dict:
    return {"type": "string", "description": description}


TOOLS = [
    _tool(
        "echo_message",
        "Echo a message back unchanged",
        "Returns the submitted message text back unchanged, in one text content block, as a "
        "reachability probe for this server's stdio framing. Use it to confirm the MCP handshake "
        "and the transport work before testing anything else; it produces no analysis of its own, "
        "so for size comparisons call compare_formats and for a token figure call estimate_tokens. "
        "Pure function: no file, network or subprocess access, whitespace is preserved exactly, and "
        "the same input always returns the same result.",
        {"message": _prop("Text to send back verbatim; any characters are accepted, including "
                          "newlines and non-ASCII. Empty or blank text is rejected.")},
        ["message"],
    ),
    _tool(
        "compare_formats",
        "Compare JSON, TOON and Compact sizes",
        "Encodes one JSON document as JSON, TOON and Compact renderings and returns each form's "
        "character count, estimated token count and percentage saved against the JSON baseline — the "
        "way to measure mcptoon's output compression on a payload you actually have. Use it when "
        "choosing an output format for real data; to compress an MCP tool definition's schema use "
        "simplify_tool_schema, to index a whole tool set use build_tool_manifest, and for measured "
        "tiktoken figures use report_benchmark_rows. SLIM is deliberately absent because it only "
        "applies to tool definitions; renderings longer than 500 characters come back truncated with "
        "their true length reported, and nothing is written to disk.",
        {"payload": _prop("A complete JSON document (object, array, string, number, boolean or null) "
                          "serialised as text; must parse as JSON and is read as data, never executed.")},
        ["payload"],
    ),
    _tool(
        "encode_toon",
        "Encode a document to TOON",
        "Converts a JSON document into TOON, the line-oriented format mcptoon can serve in place of "
        "JSON, and returns the encoded text. Use it when you need the encoded form by itself; to see "
        "it next to the other formats with savings percentages use compare_formats, and to read such "
        "text back use decode_toon. Encoding is deterministic and lossless for JSON data — numbers, "
        "booleans, nulls and nesting survive, strings are escaped — and no value is truncated, though "
        "a response over 500 characters is previewed with its real length stated.",
        {"payload": _prop("A complete JSON document serialised as text; keys with embedded newlines or "
                          "unescaped quotes are escaped rather than rejected.")},
        ["payload"],
    ),
    _tool(
        "decode_toon",
        "Decode TOON back to JSON",
        "Parses TOON text into a JSON value and returns it, together with a canonical serialisation "
        "for comparing against the original — the way to prove an encode_toon round trip is lossless. "
        "Use it on text this server produced or on a stored TOON document; to produce such text use "
        "encode_toon, and to compare formats rather than parse use compare_formats. This decoder is "
        "permissive, not strict: text that is not valid TOON usually comes back as a scalar or as a "
        "value missing rows rather than as an error, so judge the result by comparing round_trip with "
        "what you expected. Nothing is written to disk.",
        {"toon": _prop("TOON-encoded text, one document per call, with its original indentation; tabs "
                       "are treated as indent levels.")},
        ["toon"],
    ),
    _tool(
        "estimate_tokens",
        "Estimate tokens by character count",
        "Counts the tokens in a text you supply using the estimator this package ships — character "
        "count divided by four, floored — so its numbers are directly comparable with the savings "
        "reported by build_tool_manifest and compare_formats. Use it for quick relative sizing; it is "
        "not a tokenizer: it undercounts CJK and other multi-byte text by roughly two to four times, "
        "so for authoritative cl100k_base figures use report_benchmark_rows instead. Runs entirely in "
        "memory on the text given, with no dictionary, model download or network call.",
        {"text": _prop("The exact text to measure; whitespace and characters outside ASCII count "
                       "toward the total like everything else.")},
        ["text"],
    ),
    _tool(
        "simplify_tool_schema",
        "Slim one MCP tool definition",
        "Rewrites a single MCP tool definition (name, description, inputSchema) into mcptoon's slim "
        "form, where each parameter keeps only its name, its type and its required marker, and returns "
        "the slim definition with the character and estimated-token delta against what you sent. Use it "
        "on one tool you are about to put in front of a model; to price a whole set at once use "
        "build_tool_manifest, and for the archived measurements on 255 real tools use "
        "report_benchmark_rows. The result lists the rules it applied: descriptions are cut to their "
        "first sentence at 120 characters, enums longer than five values are dropped, and $ref, title, "
        "format, pattern and examples are removed — so the slim form is a summary, not a schema you can "
        "validate arguments against, and the input is never stored.",
        {"tool": _prop("One MCP tool definition as a JSON object serialised to text, with a non-empty "
                       "'name'; a bare name string is rejected and reported as such.")},
        ["tool"],
    ),
    _tool(
        "build_tool_manifest",
        "Index a tool set by name only",
        "Reduces a set of MCP tool definitions, grouped by server or flat, to the names-only index "
        "mcptoon puts in front of an agent — one line per server listing its tool names, no schemas — "
        "with the estimated token drop against the text you supplied. Use it to price a tool set before "
        "loading any of it; to inspect or slim one definition in detail use simplify_tool_schema, and "
        "for the committed benchmark use report_benchmark_rows. Nothing is fetched: a server you do not "
        "include in the argument simply is not indexed, and any entry lacking a usable name shows up "
        "under skipped_entries with its server under empty_servers and no saving claimed for it, "
        "rather than being dropped silently.",
        {"manifest": _prop("Either {server_name: [tool_definition, ...]} or a flat "
                           "[tool_definition, ...] array, as JSON text; string entries are accepted as "
                           "bare tool names and put under their group's name."),
         "include_slim": {"type": "boolean",
                          "description": "When true, also returns each tool's slim definition under "
                                         "'slim_tools'; omitted or false returns the name index only. "
                                         "Has no effect on the reported token drop, which always "
                                         "measures the name index."}},
        ["manifest"],
    ),
    _tool(
        "report_benchmark_rows",
        "Report the archived token benchmark",
        "Returns this project's committed token measurements for 5, 50 and 255 MCP tool definitions "
        "encoded with tiktoken cl100k_base: raw JSON, TOON, SLIM and Compact token counts with each "
        "format's percentage saved. Use it when you need a citable figure with a stated corpus instead "
        "of a guess; to measure text you have in hand use estimate_tokens, and to price your own tool "
        "set use build_tool_manifest. These rows are constants compiled into the package from a "
        "one-off measurement run — this call does not re-benchmark, does not read files, and does not "
        "reach the network, so a stale corpus is the only error mode.",
        {},
        [],
    ),
    _tool(
        "list_supported_agents",
        "List agent config targets and paths",
        "Reports the AI agent configuration targets mcptoon's sync command knows how to write, each "
        "with the path it resolves to in this process's environment. Use it to check whether an agent "
        "is supported and where its file would live; it is not a discovery tool — it never opens, "
        "stats or scans those paths, so an entry here does not mean that agent is installed, and this "
        "server offers no file-system view (use mcptoon's own doctor command for that). It cannot "
        "change any agent's configuration either; to price what these agents would load into context, "
        "use build_tool_manifest.",
        {},
        [],
    ),
    _tool(
        "validate_config_draft",
        "Structurally check a config draft",
        "Checks a proposed mcptoon server configuration before you save it and reports problems per "
        "entry: an entry with neither command nor url, one that sets both, args or env of the wrong "
        "JSON type, keys mcptoon ignores, and which transport mcptoon would choose. Use it on a file "
        "assembled by hand or by a model; it accepts both {'mcpServers': {…}} and a bare {name: {…}} "
        "mapping, writes nothing, and explicitly does not check that the command exists on PATH or "
        "that the server starts, so a clean report is not proof of a working server; to price the "
        "payload a working entry would put in front of a model, use build_tool_manifest.",
        {"config": _prop("A mcptoon configuration draft as JSON text: server names mapping to entries "
                         "with command/args or url. Comments are unsupported and become unknown keys.")},
        ["config"],
    ),
    _tool(
        "describe_runtime",
        "Describe this server's runtime",
        "Describes the running demo server itself: mcptoon version, the MCP protocol versions it "
        "accepts, the interpreter and platform versions behind it, and whether it carries any "
        "third-party runtime dependency. Use it to check compatibility or to confirm you are talking "
        "to the self-demo rather than a proxy onto someone else's servers; the tool definitions "
        "themselves come from the standard tools/list response, not from this call, and no "
        "configuration, environment file or user directory is consulted. Version and platform values "
        "reflect this process at call time, so they change when the environment changes; for figures "
        "that do not move, use report_benchmark_rows.",
        {},
        [],
    ),
]


# ─── the server ──────────────────────────────────────────────────────────────

def _log(msg: str):
    """Log to stderr; stdout belongs to the JSON-RPC stream."""
    sys.stderr.write(f"[mcptoon {SERVER_NAME}] {msg}\n")
    sys.stderr.flush()


class DemoServer:
    """A minimal MCP server over line-delimited JSON-RPC, answering from TOOLS.

    Stateless after the pre-check, like the bridge in serve.py (ADR 0010):
    tools/list and tools/call work with or without a prior initialize.
    """

    def __init__(self):
        self._shutdown = False
        self._last_response: dict | None = None

    # -- response helpers ----------------------------------------------------
    def _respond(self, response: dict):
        self._last_response = response
        data = json.dumps(response, ensure_ascii=False)
        try:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()
        except UnicodeEncodeError:
            # A cp1252/cp437 console cannot encode non-ASCII; the wire is UTF-8
            # whatever the terminal's code page says, so bypass the text layer.
            sys.stdout.buffer.write((data + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
        except Exception as exc:  # a closed pipe means the client left
            _log(f"failed to send response: {exc}")

    def handle_request(self, request: dict) -> dict | None:
        self._last_response = None
        self._handle_request(request)
        return self._last_response

    def _handle_request(self, request: dict):
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}

        if req_id is None:  # notification: no response is permitted
            if method not in ("notifications/initialized", "notifications/cancelled"):
                _log(f"ignored unknown notification: {method}")
            return

        meta = params.get("_meta")
        if isinstance(meta, dict):
            announced = meta.get("io.modelcontextprotocol/protocolVersion") or meta.get("protocolVersion")
            if announced and announced not in SUPPORTED_PROTOCOL_VERSIONS:
                self._respond(_make_error_response(
                    req_id, ERR_UNSUPPORTED_PROTOCOL_VERSION,
                    f"Unsupported protocol version: {announced}"))
                return

        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {"resultType": "complete"}
            elif method == "tools/list":
                result = self._list_tools()
            elif method == "tools/call":
                result = self._call_tool(params)
            elif method == "resources/list":
                result = {"resources": [], **_list_cache_fields()}
            elif method == "prompts/list":
                result = {"prompts": [], **_list_cache_fields()}
            else:
                self._respond(_make_error_response(
                    req_id, -32601, f"Method not found: {method}"))
                if method == "shutdown":
                    self._shutdown = True
                return
            self._respond(_make_success(req_id, result))
        except Exception as exc:  # never kill the loop over one bad call
            _log(f"{method} failed: {exc}")
            self._respond(_make_error_response(req_id, -32603, str(exc)[:200]))

    # -- handlers ------------------------------------------------------------
    def _initialize(self, params: dict) -> dict:
        client_version = params.get("protocolVersion", PROTOCOL_VERSION)
        version = (client_version if client_version in SUPPORTED_PROTOCOL_VERSIONS
                   else PROTOCOL_VERSION)
        _log(f"initialize from {params.get('clientInfo', {}).get('name', 'unknown client')}")
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}, "extensions": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "resultType": "complete",
        }

    def _list_tools(self) -> dict:
        return {"tools": [dict(t) for t in TOOLS], "resultType": "complete",
                **_list_cache_fields()}

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name", "")
        handler = HANDLERS.get(name)
        if handler is None:
            return _make_tool_error(
                f"unknown tool '{name}'; this server offers "
                f"{', '.join(sorted(HANDLERS))}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _make_tool_error("arguments must be an object")
        definition = next(t for t in TOOLS if t["name"] == name)
        problems = schema_simplifier.validate_args(args, definition["inputSchema"])
        if problems:
            return _make_tool_error("; ".join(problems))
        try:
            payload = handler(args)
        except DemoToolError as exc:
            return _make_tool_error(str(exc))
        except Exception as exc:
            _log(f"{name} raised {type(exc).__name__}: {exc}")
            return _make_tool_error(f"{name} failed: {type(exc).__name__}: {exc}")
        return _make_tool_result(payload)

    # -- loop ----------------------------------------------------------------
    def run(self):
        # MCP's stdio transport is newline-delimited UTF-8, independent of the
        # console code page; reconfiguring here means one response containing a
        # Chinese tool argument cannot be lost on a cp1252 Windows terminal.
        for stream in (sys.stdout, sys.stdin):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                try:
                    reconfigure(encoding="utf-8")
                except (OSError, ValueError):
                    pass
        _log(f"started — {len(TOOLS)} tools, stdio, format-agnostic")
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self._respond({"jsonrpc": "2.0", "id": None,
                                   "error": {"code": -32700, "message": "Parse error"}})
                    continue
                if not isinstance(request, dict):
                    self._respond({"jsonrpc": "2.0", "id": None,
                                   "error": {"code": -32600, "message": "Invalid request"}})
                    continue
                self._handle_request(request)
                if self._shutdown:
                    break
        except KeyboardInterrupt:
            _log("interrupted")
        except EOFError:
            _log("stdin closed")
        finally:
            _log("stopped")


def tool_names() -> list[str]:
    return [t["name"] for t in TOOLS]


def _demo_server_help() -> str:
    return f"""mcptoon demo-server — self-contained MCP demo server (no third-party tools)

Eleven tools built from mcptoon's own pure functions. No network, no subprocess,
no user configuration, no API key, nothing installed at runtime — so it answers
tools/list identically on a bare Python container and on a laptop.

Usage:
    mcptoon demo-server                       serve over stdio
    python -m mcptoon demo-server             same, without a PATH entry
    mcptoon add demo --stdio python -m mcptoon demo-server
    mcptoon call demo echo_message '{{"message":"hi"}}'

It registers nothing by itself: `mcptoon serve` still exposes only the servers you
configure, and mcptoon still bundles no third-party tools. This is the demo, added
on purpose by you.

Tools: {", ".join(tool_names())}
"""


def run_demo_server(args: list[str]):
    """Entry point for `mcptoon demo-server`."""
    if any(a in ("-h", "--help") for a in args):
        print(_demo_server_help())
        return
    DemoServer().run()
