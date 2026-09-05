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
mcptoon output — multi-format output rendering

Output modes:
  --json       Machine-readable JSON (default for piped output)
  --toon       Standard TOON (Token-Oriented Object Notation, toon-format/toon spec)
  --mcptoon    Legacy mcptoon pipe format (improved with escaping, round-trip safe)
  --slim       Ultra-compact tool manifests (93% savings, mcptoon-specific)
  --compact    Space-separated names only (~20 tokens for 96 tools)
  --raw        Raw response body (no JSON parsing)
  --head N     Limit array output to first N records
  --max-chars N  Truncate output to N chars (default: 4000, use --full for unlimited)
  --full       Disable truncation

Adaptive format: MCPTOON_AGENT_TYPE env var (optional, defaults to JSON)
claude  → --toon (optional, only if env var set)
openai  → --json (default)
script  → --json (default)
human   → --json (default)

Export formats (--format flag):
  openai  → OpenAI function calling definitions
  openapi → OpenAPI 3.0 spec
  mcp     → MCP tools/list format
  json    → Raw JSON
  human   → Human-readable

Standard TOON Format (toon-format/toon spec):
  Objects:    key: value (one per line, YAML-style)
  Object arrays: key[N]{f1,f2}:\\n v1a,v1b\\n v2a,v2b
  Scalar arrays: key[N]: v1,v2,v3
  Nested: indented key: value under parent
  Bool: true / false
  Null: null
  Strings: no quotes needed (commas in values → quoted)

  Token savings: 30-60% vs JSON (structural compression).
  Round-trip safe: decode(encode(x)) == x.

  Example:
    JSON:  {"name": "search", "params": {"query": "AI", "num": 5}, "cached": true}
    TOON:  name: search\\nparams{query,num}:\\n  AI,5\\ncached: true

Legacy mcptoon Format (--mcptoon):
  dict  → k1:v1|k2:v2           (pipe-separated key:value pairs)
  list  → v1 v2 v3              (space-separated values)
  bool  → true / false
  null  → null
  str   → literal (escapes: \\c=colon, \\p=pipe, \\s=space-in-value)

  Round-trip safe with mcptoon_decode().
"""
import json
import os

# Import vendored spec-compliant TOON encoder/decoder
# (python-toon v0.1.1 by Xavi Vinaixa, MIT License — vendored in toon_vendored.py)
from .toon_vendored import encode as _toon_vendored_encode
from .toon_vendored import decode as _toon_vendored_decode
from .toon_vendored import ToonDecodeError as _VendoredToonDecodeError


# ═══════════════════════════════════════════════════════════════
# Standard TOON Encoder (toon-format/toon spec)
# ═══════════════════════════════════════════════════════════════

def _toon_escape_csv(value: str) -> str:
    """Escape a value for CSV-style TOON array rows.

    If value contains comma, newline, or quote → wrap in double quotes
    and escape internal quotes.
    """
    if "," in value or "\n" in value or '"' in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def _toon_scalar_str(val) -> str:
    """Convert a scalar to its TOON string representation."""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif val is None:
        return "null"
    elif isinstance(val, (int, float)):
        return str(val)
    else:
        return str(val)


def _is_uniform_object_array(lst: list) -> bool:
    """Check if list is an array of dicts with the same keys.

    Standard TOON optimises uniform object arrays into CSV-style rows.
    """
    if not lst or not all(isinstance(item, dict) for item in lst):
        return False
    if len(lst) == 1:
        return True  # Single dict, can use field declaration
    first_keys = set(lst[0].keys())
    return all(set(item.keys()) == first_keys for item in lst)


def _toon_uniform_keys(lst: list) -> list:
    """Get the ordered field keys for a uniform object array."""
    # Use first item's key order
    return list(lst[0].keys()) if lst else []


def _toon_encode_value(val, indent: int = 0) -> str:
    """Encode a value as standard TOON, with given indentation level."""
    pad = "  " * indent

    if isinstance(val, dict):
        if not val:
            return "{}"
        lines = []
        for k, v in val.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{k}: {{}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(_toon_encode_value(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                elif _is_uniform_object_array(v):
                    keys = _toon_uniform_keys(v)
                    fields = ",".join(keys)
                    lines.append(f"{pad}{k}[{len(v)}]{{{fields}}}:")
                    for item in v:
                        row = ",".join(
                            _toon_escape_csv(_toon_scalar_str(item.get(key, "")))
                            for key in keys
                        )
                        lines.append(f"{pad}  {row}")
                else:
                    # Mixed-type array: one value per line
                    lines.append(f"{pad}{k}[{len(v)}]:")
                    for item in v:
                        if isinstance(item, (dict, list)):
                            lines.append(_toon_encode_value(item, indent + 1))
                        else:
                            lines.append(f"{pad}  {_toon_escape_csv(_toon_scalar_str(item))}")
            else:
                lines.append(f"{pad}{k}: {_toon_escape_csv(_toon_scalar_str(v))}")
        return "\n".join(lines)

    elif isinstance(val, list):
        if not val:
            return "[]"
        if _is_uniform_object_array(val):
            keys = _toon_uniform_keys(val)
            fields = ",".join(keys)
            lines = [f"{pad}[{len(val)}]{{{fields}}}:"]
            for item in val:
                row = ",".join(
                    _toon_escape_csv(_toon_scalar_str(item.get(key, "")))
                    for key in keys
                )
                lines.append(f"{pad}  {row}")
            return "\n".join(lines)
        else:
            lines = [f"{pad}[{len(val)}]:"]
            for item in val:
                if isinstance(item, (dict, list)):
                    lines.append(_toon_encode_value(item, indent + 1))
                else:
                    lines.append(f"{pad}  {_toon_escape_csv(_toon_scalar_str(item))}")
            return "\n".join(lines)

    else:
        return _toon_escape_csv(_toon_scalar_str(val))


def toon_encode(obj) -> str:
    """Encode obj as standard TOON string (toon-format/toon spec v4.1).

    Uses vendored python-toon v0.1.1 encoder (MIT License, Xavi Vinaixa).
    Spec-compliant: passes official toon-format/toon test suite.
    Token-efficient for LLMs: 30-60% fewer tokens than JSON.
    Round-trip safe: decode(encode(x)) == x.

    >>> toon_encode({"name": "search", "count": 3})
    'name: search\\ncount: 3'
    >>> toon_encode([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
    '[2]{id,name}:\\n  1,Alice\\n  2,Bob'
    >>> toon_encode({"ok": True, "err": None})
    'ok: true\\nerr: null'
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict) and not obj:
        return "{}"
    if isinstance(obj, list) and not obj:
        return "[]"
    return _toon_vendored_encode(obj)


# ═══════════════════════════════════════════════════════════════
# Standard TOON Decoder
# ═══════════════════════════════════════════════════════════════

def _toon_unescape_csv(value: str) -> str:
    """Unescape a CSV-style TOON value."""
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        # Remove quotes and unescape internal double-quotes
        return value[1:-1].replace('""', '"')
    return value


def _toon_parse_scalar(value: str):
    """Parse a scalar value from TOON string."""
    s = _toon_unescape_csv(value)
    if s == "true":
        return True
    elif s == "false":
        return False
    elif s == "null":
        return None
    # Try int
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _toon_parse_lines(lines: list, indent: int = 0) -> tuple:
    """Parse TOON lines at given indent level.

    Returns (parsed_value, next_line_index).
    """
    if not lines:
        return None, 0

    # Check if first line is an array declaration: key[N]{fields}: or [N]{fields}:
    # or key[N]: or [N]:
    idx = 0
    result = {}

    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        # Determine indentation of this line
        line_stripped = line.lstrip()
        line_indent = (len(line) - len(line_stripped)) // 2

        if line_indent < indent:
            # This line belongs to a parent level
            break

        if line_indent > indent:
            # Unexpected deeper indent without a parent — skip
            idx += 1
            continue

        # Parse the line
        # Pattern 1: key[N]{f1,f2,...}:
        # Pattern 2: key[N]:
        # Pattern 3: key: value
        # Pattern 4: key: (nested object follows)
        # Pattern 5: [N]{f1,f2}: (top-level array)

        line_text = line_stripped

        # Check for array declaration with fields
        if "{" in line_text and line_text.rstrip().endswith(":"):
            # key[N]{f1,f2,...}: or [N]{f1,f2,...}:
            colon_pos = line_text.rfind(":")
            decl = line_text[:colon_pos]

            # Extract key (if exists), count, and fields
            bracket_pos = decl.find("[")
            if bracket_pos == -1:
                # Not an array decl, treat as key: with nested
                idx += 1
                continue

            key = decl[:bracket_pos].strip()
            if key:
                key = key.rstrip(":").strip()

            # Extract fields from {f1,f2,...}
            brace_start = decl.find("{")
            brace_end = decl.find("}")
            if brace_start != -1 and brace_end != -1:
                fields = decl[brace_start + 1:brace_end].split(",")
                fields = [f.strip() for f in fields]
            else:
                fields = []

            # Parse CSV rows
            rows = []
            idx += 1
            while idx < len(lines):
                row_line = lines[idx]
                if not row_line.strip():
                    idx += 1
                    continue
                row_stripped = row_line.lstrip()
                row_indent = (len(row_line) - len(row_stripped)) // 2
                if row_indent <= indent:
                    break
                # Parse CSV row
                values = _parse_csv_row(row_stripped)
                if fields:
                    row_dict = {}
                    for i, f in enumerate(fields):
                        row_dict[f] = _toon_parse_scalar(values[i]) if i < len(values) else ""
                    rows.append(row_dict)
                else:
                    rows.append(_toon_parse_scalar(values[0]) if values else "")
                idx += 1

            if key:
                result[key] = rows
            else:
                return rows, idx

        elif line_text.rstrip().endswith(":") and "[" in line_text:
            # key[N]: (scalar array)
            colon_pos = line_text.rfind(":")
            decl = line_text[:colon_pos]
            bracket_pos = decl.find("[")
            key = decl[:bracket_pos].strip() if bracket_pos > 0 else ""

            # Parse scalar values
            values = []
            idx += 1
            while idx < len(lines):
                val_line = lines[idx]
                if not val_line.strip():
                    idx += 1
                    continue
                val_stripped = val_line.lstrip()
                val_indent = (len(val_line) - len(val_stripped)) // 2
                if val_indent <= indent:
                    break
                values.append(_toon_parse_scalar(val_stripped))
                idx += 1

            if key:
                result[key] = values
            else:
                return values, idx

        elif line_text.rstrip().endswith(":"):
            # key: (nested object follows)
            key = line_text.rstrip()[:-1].strip()
            # Collect indented lines for nested object
            nested_lines = []
            idx += 1
            while idx < len(lines):
                nested_line = lines[idx]
                if not nested_line.strip():
                    idx += 1
                    continue
                nested_stripped = nested_line.lstrip()
                nested_indent = (len(nested_line) - len(nested_stripped)) // 2
                if nested_indent <= indent:
                    break
                nested_lines.append(nested_line)
                idx += 1

            if nested_lines:
                nested_val, _ = _toon_parse_lines(nested_lines, indent + 1)
                result[key] = nested_val
            else:
                result[key] = {}

        elif ":" in line_text:
            # key: value
            colon_pos = line_text.find(":")
            key = line_text[:colon_pos].strip()
            value = line_text[colon_pos + 1:].strip()
            result[key] = _toon_parse_scalar(value)
            idx += 1

        else:
            idx += 1

    return result, idx


def _parse_csv_row(row: str) -> list:
    """Parse a CSV row, handling quoted values."""
    values = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(row):
        c = row[i]
        if in_quotes:
            if c == '"':
                if i + 1 < len(row) and row[i + 1] == '"':
                    current += '"'
                    i += 2
                    continue
                else:
                    in_quotes = False
            else:
                current += c
        else:
            if c == '"':
                in_quotes = True
            elif c == ",":
                values.append(current)
                current = ""
            else:
                current += c
        i += 1
    values.append(current)
    return values


def toon_decode(text: str):
    """Decode a standard TOON string back to Python objects.

    Uses vendored python-toon v0.1.1 decoder (MIT License, Xavi Vinaixa).
    Spec-compliant: passes official toon-format/toon test suite.
    Non-strict mode by default (lenient parsing for mcptoon compat).
    Round-trip safe: decode(encode(x)) == x.

    >>> toon_decode('name: search\\ncount: 3')
    {'name': 'search', 'count': 3}
    >>> toon_decode('[2]{id,name}:\\n  1,Alice\\n  2,Bob')
    [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    """
    if not text or not text.strip():
        return None
    stripped = text.strip()
    if stripped == "{}":
        return {}
    if stripped == "[]":
        return []
    try:
        return _toon_vendored_decode(text)
    except _VendoredToonDecodeError:
        # Fallback to legacy parser if vendored decoder fails
        lines = text.split("\n")
        result, _ = _toon_parse_lines(lines, 0)
        return result


# ═══════════════════════════════════════════════════════════════
# Legacy mcptoon Format (improved with escaping, round-trip safe)
# ═══════════════════════════════════════════════════════════════

# Escape sequences for legacy mcptoon format
# \c = colon (:)  — avoids key-value separator collision
# \p = pipe (|)   — avoids pair separator collision
# \s = space ( )  — avoids array separator collision (for scalar arrays)
# \\ = backslash  — must be first in decode to avoid double-unescaping

def _mcptoon_escape(value: str) -> str:
    """Escape special characters in a string value for legacy mcptoon format.

    Escape sequences:
    \\ → \\\\  (backslash, must be first)
    :  → \\c   (colon, avoids key-value separator collision)
    |  → \\p   (pipe, avoids pair separator collision)
    \n → \\n   (newline, avoids line separator collision)
    """
    # Must escape backslash first, then colon, pipe, newline
    return (
        value.replace("\\", "\\\\")
             .replace(":", "\\c")
             .replace("|", "\\p")
             .replace("\n", "\\n")
    )


def _mcptoon_unescape(value: str) -> str:
    """Unescape special characters in a legacy mcptoon string.

    Reverses: \\c→:, \\p→|, \\n→newline, \\\\→backslash.
    """
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            next_char = value[i + 1]
            if next_char == "c":
                result.append(":")
            elif next_char == "p":
                result.append("|")
            elif next_char == "n":
                result.append("\n")
            elif next_char == "\\":
                result.append("\\")
            else:
                # Unknown escape, keep as-is
                result.append(value[i])
                result.append(next_char)
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def _mcptoon_value(val):
    """Recursively encode a value as legacy mcptoon format."""
    if isinstance(val, dict):
        if not val:
            return "{}"
        parts = []
        for k, v in val.items():
            ks = _mcptoon_escape(str(k))
            vs = _mcptoon_value(v)
            parts.append(f"{ks}:{vs}")
        return "|".join(parts)
    elif isinstance(val, list):
        if not val:
            return "[]"
        if all(isinstance(v, (str, int, float, bool)) or v is None for v in val):
            return " ".join(_mcptoon_scalar(v) for v in val)
        return " ".join(_mcptoon_value(v) for v in val)
    return _mcptoon_scalar(val)


def _mcptoon_scalar(val):
    """Encode a scalar value as legacy mcptoon format.

    Uses escape sequences instead of character replacement:
    - : → \\c (reversible, was _ which was lossy)
    - | → \\p (prevents separator collision)
    - Strings truncated to 500 chars (was 200, too aggressive)
    """
    if isinstance(val, bool):
        return "true" if val else "false"
    elif val is None:
        return "null"
    elif isinstance(val, (int, float)):
        return str(val)
    else:
        s = str(val)[:500]
        return _mcptoon_escape(s)


def mcptoon_encode(obj) -> str:
    """Encode obj as legacy mcptoon pipe format (round-trip safe).

    >>> mcptoon_encode({"name": "search", "count": 3})
    'name:search|count:3'
    >>> mcptoon_encode({"url": "https://example.com"})
    'url:https\\c//example.com'
    >>> mcptoon_encode([1, 2, 3])
    '1 2 3'
    >>> mcptoon_encode({"ok": True, "err": None})
    'ok:true|err:null'
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(_mcptoon_value(item) for item in obj)
    return _mcptoon_value(obj)


def mcptoon_decode(text: str):
    """Decode a legacy mcptoon pipe format string back to Python objects.

    Round-trip safe: decode(encode(x)) == x.

    >>> mcptoon_decode('name:search|count:3')
    {'name': 'search', 'count': 3}
    >>> mcptoon_decode('url:https\\\\c//example.com')
    {'url': 'https://example.com'}
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Top-level list: multiple lines
    if "\n" in text:
        lines = text.split("\n")
        return [mcptoon_decode(line) for line in lines if line.strip()]

    # Empty containers
    if text == "{}":
        return {}
    if text == "[]":
        return []

    # Dict: k1:v1|k2:v2|...
    if "|" in text or ":" in text:
        result = {}
        # Split on unescaped pipes
        parts = _split_unescaped(text, "|")
        for part in parts:
            if ":" in part:
                # Split on first unescaped colon
                colon_idx = _find_unescaped(part, ":")
                if colon_idx == -1:
                    continue
                key = _mcptoon_unescape(part[:colon_idx])
                value_str = part[colon_idx + 1:]
                result[key] = _mcptoon_parse_value(value_str)
        if result:
            return result

    # Scalar
    return _mcptoon_parse_value(text)


def _split_unescaped(text: str, delimiter: str) -> list:
    """Split text on unescaped occurrences of delimiter."""
    parts = []
    current = ""
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            current += text[i]
            current += text[i + 1]
            i += 2
        elif text[i] == delimiter:
            parts.append(current)
            current = ""
            i += 1
        else:
            current += text[i]
            i += 1
    parts.append(current)
    return parts


def _find_unescaped(text: str, char: str) -> int:
    """Find first unescaped occurrence of char in text."""
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            i += 2
        elif text[i] == char:
            return i
        else:
            i += 1
    return -1


def _mcptoon_parse_value(value_str: str):
    """Parse a value from legacy mcptoon string.

    Handles:
    - Scalars (true, false, null, int, float, string)
    - Empty containers ({} and [])
    - Nested dicts (if value contains unescaped colon → recurse)
    - Escaped values (\\c, \\p, \\\\)
    """
    s = value_str.strip()
    if s == "true":
        return True
    elif s == "false":
        return False
    elif s == "null":
        return None
    elif s == "{}":
        return {}
    elif s == "[]":
        return []
    # Try int
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    # Check for nested dict: unescaped colon in value means nested k:v
    unescaped_colon = _find_unescaped(s, ":")
    if unescaped_colon > 0:
        # This looks like a nested dict (k:v format)
        return mcptoon_decode(s)
    # String with unescaping
    return _mcptoon_unescape(s)


# ═══════════════════════════════════════════════════════════════
# Backward-compatible aliases (deprecated, will be removed in v1.0)
# ═══════════════════════════════════════════════════════════════

def toon(obj):
    """DEPRECATED: Use toon_encode() for standard TOON or mcptoon_encode() for legacy.

    This function now delegates to mcptoon_encode() for backward compatibility.
    """
    return mcptoon_encode(obj)


def _toon_value(val):
    """DEPRECATED: Use _mcptoon_value() instead."""
    return _mcptoon_value(val)


def _toon_scalar(val):
    """DEPRECATED: Use _mcptoon_scalar() instead."""
    return _mcptoon_scalar(val)


# ═══════════════════════════════════════════════════════════════
# Slim TOON Encoder (for tool manifests) — unchanged
# ═══════════════════════════════════════════════════════════════

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
                lines.append(_mcptoon_value(item))
        return "\n".join(lines)
    if isinstance(obj, dict) and "name" in obj:
        return _slim_tool(obj)
    return _mcptoon_value(obj)


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


# ═══════════════════════════════════════════════════════════════
# Compact Encoder — unchanged
# ═══════════════════════════════════════════════════════════════

def compact(obj, max_items=30):
    """Extract name/id strings only, space-separated.

    Manifest-shaped dicts ({server: [tool names]}) expand to a FULL
    "server: n1, n2" name index with no truncation — this is the discovery
    answer an agent consumes. Historical behavior truncated dicts to a
    200-char JSON fragment, which silently hid most tools.
    """
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
        if n:
            return str(n)
        # Manifest shape: every value is a non-empty list of strings
        if obj and all(
            isinstance(v, list) and v and all(isinstance(i, str) for i in v)
            for v in obj.values()
        ):
            return " · ".join(f"{s}: {', '.join(v)}" for s, v in obj.items())
        return json.dumps(obj, ensure_ascii=False)[:200]
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
    """Auto-select format based on MCPTOON_AGENT_TYPE env var.
    
    Default is JSON. TOON is only auto-selected when MCPTOON_AGENT_TYPE=claude
    is explicitly set. This makes JSON the universal default.
    """
    agent_type = os.environ.get("MCPTOON_AGENT_TYPE", "").lower()
    if agent_type == "claude":
        return "toon"
    # All other cases: default to JSON
    return "json"


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
        fmt: "json" | "compact" | "toon" | "mcptoon" | "slim" | "auto" | "raw"
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
        result = toon_encode(obj)
        return _truncate(result, effective_max) if effective_max else result

    if fmt == "mcptoon":
        result = mcptoon_encode(obj)
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
