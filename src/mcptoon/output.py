# -*- coding: utf-8 -*-
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
mcptoon output — multi-format output rendering

Modes:
  --json       Machine-readable JSON (default for piped output)
  --compact    Space-separated names only (~20 tokens for 96 tools)
  --toon       Token-efficient notation for LLMs (20-40% fewer tokens than JSON, tiktoken-verified)
  --head N     Limit array output to first N records
  --raw        Raw response body (no JSON parsing)
  --max-chars N  Truncate output to N chars (default: 4000, use --full for unlimited)
  --full       Disable truncation

Adaptive format: set MCPTOON_AGENT_TYPE env var
  claude  → --toon (省 token)
  openai  → --json
  script  → --json
  human   → auto

Export formats (--format flag):
  openai  → OpenAI function calling definitions
  openapi → OpenAPI 3.0 spec
  mcp     → MCP tools/list format
  json    → Raw JSON
  human   → Human-readable

TOON Format Spec:
  dict  → k1:v1|k2:v2           (pipe-separated key:value pairs)
  list  → v1 v2 v3              (space-separated values)
  bool  → true / false         (kept as-is, 1 token either way)
  null  → null                 (kept as-is, ∅ costs 2 tokens)
  str   → literal (colons → _, truncated to 200 chars)
  num   → literal

  Token savings come from STRUCTURAL compression (removing JSON braces,
  quotes, type wrappers), not scalar substitution.
  Verified with tiktoken (o200k_base + cl100k_base).

  Example:
    JSON:   {"name": "search", "params": {"query": "AI", "num": 5}, "cached": true, "error": null}
    TOON:   name:search|params:query:AI|num:5|cached:true|error:null
"""
import json
import os


# ─── TOON Encoder ───

def _toon_value(val):
    """Recursively encode a value as TOON."""
    if isinstance(val, dict):
        if not val:
            return "{}"
        parts = []
        for k, v in val.items():
            ks = str(k).replace(":", "＿").replace(" ", "_")
            vs = _toon_value(v)
            parts.append(f"{ks}:{vs}")
        return "|".join(parts)
    elif isinstance(val, list):
        if not val:
            return "[]"
        if all(isinstance(v, (str, int, float, bool)) or v is None for v in val):
            return " ".join(_toon_scalar(v) for v in val)
        return " ".join(_toon_value(v) for v in val)
    return _toon_scalar(val)


def _toon_scalar(val):
    """Encode a scalar value as TOON.

    Only substitutions that tiktoken-verify as ≤ original token count.
    - bool: kept as true/false (1 token either way, no benefit to T/F)
    - null: kept as null (∅ costs 2 tokens, worse)
    - newlines: kept as-is (↲ costs 2 tokens, worse)
    """
    if isinstance(val, bool):
        return "true" if val else "false"
    elif val is None:
        return "null"
    elif isinstance(val, (int, float)):
        return str(val)
    else:
        s = str(val)[:200]
        return s.replace(":", "_")


def toon(obj):
    """Encode obj as TOON string (token-efficient for LLMs).

    >>> toon({"name": "search", "count": 3})
    'name:search|count:3'
    >>> toon([1, 2, 3])
    '1 2 3'
    >>> toon({"ok": True, "err": None})
    'ok:true|err:null'
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(_toon_value(item) for item in obj)
    return _toon_value(obj)


# ─── Slim TOON Encoder (for tool manifests) ───

_TYPE_MAP = {
    "string": "s", "number": "n", "integer": "n",
    "boolean": "b", "array": "a", "object": "o", "null": "_",
}


def slim_toon(obj):
    """Encode tool manifest as ultra-compact TOON.

    Format: tool_name|p1:type*|p2:type|p3:a[item_type]
    - * marks required params
    - types: s=string n=number b=boolean a=array o=object
    - descriptions and schema wrappers stripped

    Example:
        >>> slim_toon([{"name": "search", "inputSchema": {
        ...     "properties": {"q": {"type": "string"}, "n": {"type": "number"}},
        ...     "required": ["q"]}}])
        'search|q:s*|n:n'
    """
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, dict) and "name" in item:
                lines.append(_slim_tool(item))
            else:
                lines.append(_toon_value(item))
        return "\n".join(lines)
    if isinstance(obj, dict) and "name" in obj:
        return _slim_tool(obj)
    return _toon_value(obj)


def _slim_tool(tool):
    """Encode a single tool definition as slim TOON."""
    name = tool.get("name", "?")
    schema = tool.get("inputSchema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not props:
        return name

    params = []
    for pname, pdef in props.items():
        ptype = pdef.get("type", "any")
        # Handle union types (type is a list)
        if isinstance(ptype, list):
            ptype = ptype[0] if ptype else "any"
        short = _TYPE_MAP.get(ptype, ptype[:1] if isinstance(ptype, str) and ptype else "?")
        # Array with item type
        if ptype == "array":
            items = pdef.get("items", {})
            item_type_raw = items.get("type", "?")
            if isinstance(item_type_raw, list):
                item_type_raw = item_type_raw[0] if item_type_raw else "?"
            item_type = _TYPE_MAP.get(item_type_raw, item_type_raw[:1] if isinstance(item_type_raw, str) and item_type_raw else "?")
            short = f"a[{item_type}]"
        # Object with known properties — show nested keys
        elif ptype == "object" and "properties" in pdef:
            nested = ",".join(pdef["properties"].keys())
            short = f"o{{{nested}}}"
        # Mark required
        marker = "*" if pname in required else ""
        params.append(f"{pname}:{short}{marker}")

    return f"{name}|{'|'.join(params)}"


# ─── Compact Encoder ───

def compact(obj, max_items=30):
    """Extract name/id strings only, space-separated."""
    if isinstance(obj, list):
        names = []
        for item in obj:
            if isinstance(item, dict):
                n = item.get("name") or item.get("id") or item.get("title") or ""
                if n:
                    names.append(str(n))
            elif isinstance(item, str):
                names.append(item)
        return " ".join(names[:max_items])
    if isinstance(obj, dict):
        n = obj.get("name") or obj.get("id") or obj.get("title") or ""
        return str(n) if n else json.dumps(obj, ensure_ascii=False)[:200]
    return str(obj)[:200]


# ─── Head (array limiter) ───

def head(obj, n=10):
    """Limit output to first N items (for lists)."""
    if isinstance(obj, list):
        return obj[:n]
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if isinstance(obj[k], list) and len(obj[k]) > n:
                obj[k] = obj[k][:n]
    return obj


# ─── Adaptive format ───

_DEFAULT_MAX_CHARS = 4000  # default truncation threshold


def _auto_format():
    """Auto-select format based on MCPTOON_AGENT_TYPE env var."""
    agent_type = os.environ.get("MCPTOON_AGENT_TYPE", "").lower()
    if agent_type == "claude":
        return "toon"
    elif agent_type in ("openai", "script", "mcp"):
        return "json"
    elif agent_type == "human":
        return "auto"
    return "auto"


def _truncate(text, max_chars):
    """Truncate text to max_chars, append notice."""
    if max_chars <= 0 or not isinstance(text, str):
        return text
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text)} chars total, use --full]"


def render(obj, fmt="auto", compact_mode=False, head_n=0, max_chars=0, full=False):
    """Render obj in requested format.

    Args:
        obj: Any Python object to render
        fmt: "json" | "compact" | "toon" | "slim" | "auto" | "raw"
        compact_mode: Use compact JSON (no indent) when fmt=json
        head_n: Take first N items of arrays
        max_chars: Truncate output to N chars (0 = use default 4000)
        full: If True, disable truncation entirely
    """
    if fmt == "auto":
        fmt = _auto_format()

    # Truncation threshold
    if full:
        effective_max = 0
    elif max_chars > 0:
        effective_max = max_chars
    else:
        effective_max = _DEFAULT_MAX_CHARS

    if head_n > 0 and isinstance(obj, (list, dict)):
        obj = head(obj, head_n)

    if fmt == "compact":
        result = compact(obj)
        return _truncate(result, effective_max) if effective_max else result

    if fmt == "toon":
        result = toon(obj)
        return _truncate(result, effective_max) if effective_max else result

    if fmt == "slim":
        result = slim_toon(obj)
        return _truncate(result, effective_max) if effective_max else result

    if fmt == "raw":
        if isinstance(obj, str):
            result = obj[:50000]
        else:
            result = json.dumps(obj, ensure_ascii=False)[:50000]
        return _truncate(result, effective_max) if effective_max else result

    # json or auto
    if isinstance(obj, str):
        return _truncate(obj, effective_max) if effective_max else obj

    opts = {"ensure_ascii": False}
    if compact_mode:
        opts["separators"] = (",", ":")
    else:
        opts["indent"] = 2

    result = json.dumps(obj, **opts)
    return _truncate(result, effective_max) if effective_max else result
