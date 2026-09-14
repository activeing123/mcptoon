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
mcptoon schema_simplifier — Reduce MCP tool JSON schemas to compact form.

Used by serve mode (ADR 0006): tools/list returns simplified schemas
(fewer tokens in tools/list) while call_tool validates with the full schema.

Strategy:
  - Keep standard JSON Schema structure (type, properties, required)
  - Keep as much description as the budget allows, whole sentences only
    (3 sentences / 360 chars for a tool, 2 / 200 for a parameter)
  - Remove: examples, $ref, $schema, additionalProperties, pattern, format,
    default, enum (unless < 5 items), title, $comment, deprecated, readOnly, writeOnly
  - Flatten one level of nested properties
"""

from __future__ import annotations

import re
from typing import Any

# Fields to strip from individual property definitions
_STRIP_PROPERTY_KEYS = {
    "$ref", "$schema", "$comment", "title", "default",
    "additionalProperties", "pattern", "format",
    "deprecated", "readOnly", "writeOnly",
    "examples", "example",
}

# Fields to strip from top-level schema
_STRIP_TOP_KEYS = {
    "$ref", "$schema", "$comment", "title",
    "additionalProperties", "pattern", "format",
    "examples", "example",
}

# Description budget, in two tiers.
#
# A tool has one description; a schema has one per property. Applying the same budget
# to both multiplies a modest allowance into noise, so the tiers are separate. Both
# exist because the previous rule — keep the first sentence, hard-cut at 120 chars —
# deleted the part that agents select tools with. "Use this when you need X", "it will
# not tell you Y", "call Z instead" are never the first sentence, and on a description
# over 120 characters the cut landed mid-word, so the surviving text was not even a
# complete claim. Measured on this repo's own demo server: 6764 characters of tool
# description reached clients as 1320, and the public scorer's description mark fell
# from 4.8 to 3.1 on exactly that text (2026-09-14).
_MAX_DESC_LEN = 360
_MAX_DESC_SENTENCES = 3
_MAX_PARAM_DESC_LEN = 200
_MAX_PARAM_DESC_SENTENCES = 2

# Marks that text was dropped. The budget below is reduced by its width first, so a
# compacted description never exceeds its stated limit — the number is a promise.
_TRUNCATION_MARK = "..."

# Max enum items to keep (larger enums are removed to save tokens)
_MAX_ENUM_KEEP = 5

# A sentence end: terminal punctuation plus any closing quote/bracket.
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*")

# Things that look like sentence ends and are not.
_ABBREVIATIONS = frozenset({"e.g", "i.e", "etc", "vs", "cf", "approx", "al"})


def _split_sentences(text: str) -> list[str]:
    """Split a description into sentences, terminators included.

    No keyword scoring, no "importance" ranking: the server's own order is the only
    signal trusted about what it wrote first, and scoring on English words would
    quietly rank non-English descriptions below it. Line breaks end sentences too,
    because server descriptions are often written as short lines.
    """
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("#*>- \t")
        if not line:
            continue
        start = 0
        for match in _SENTENCE_END.finditer(line):
            end = match.end()
            if end < len(line) and not line[end].isspace():
                continue  # "3.5", "mcptoon.io" — a decimal or a domain, not an end
            head = line[start:end].strip()
            if not head:
                continue
            last = head.split()[-1].rstrip(".!?").lower()
            if last in _ABBREVIATIONS or (len(last) == 1 and last.isalpha()):
                continue  # "e.g." and single-letter initials do not end a sentence
            parts.append(head)
            start = end
        tail = line[start:].strip()
        if tail:
            parts.append(tail)
    return parts


def _truncate_desc(desc: str | None, budget: int = _MAX_DESC_LEN,
                   max_sentences: int = _MAX_DESC_SENTENCES) -> str | None:
    """Keep as much of a description as the budget allows, whole sentences only.

    Two limits, whichever binds first: a character budget and a sentence cap. The cap
    earns its place with descriptions written as many short lines — those fit the
    budget and still turn a listing into a wall of text.

    Sentences are taken in the order the server wrote them. The first one that does not
    fit stops the run; nothing is skipped over to grab a shorter later sentence, so the
    result is always a prefix of the original. A first sentence too long for the budget
    on its own is cut at a word boundary, never mid-word. Text that stays within both
    limits passes through byte-identical, which makes this safe to apply twice.
    """
    if not desc:
        return None
    original = desc.strip()
    if not original:
        return None

    sentences = _split_sentences(original) or [original]
    if len(original) <= budget and len(sentences) <= max_sentences:
        return original

    limit = budget - len(_TRUNCATION_MARK) - 1
    kept: list[str] = []
    used = 0
    for sentence in sentences:
        if len(kept) >= max_sentences:
            break
        cost = len(sentence) + (1 if kept else 0)
        if used + cost > limit:
            break
        kept.append(sentence)
        used += cost

    if not kept:
        # Even the first sentence is over budget: cut at whitespace, not mid-word.
        head = original[:limit]
        if " " in head:
            head = head.rsplit(" ", 1)[0]
        return f"{head.rstrip(' ,;:')} {_TRUNCATION_MARK}"

    result = " ".join(kept)
    if len(kept) < len(sentences):
        result = f"{result} {_TRUNCATION_MARK}"
    return result



def _simplify_property(prop: dict) -> dict:
    """Simplify a single property definition."""
    if not isinstance(prop, dict):
        return prop

    result: dict[str, Any] = {}

    # Keep type (most important for agent to know how to call)
    if "type" in prop:
        result["type"] = prop["type"]

    # Keep description (truncated to the parameter-tier budget: a schema repeats this
    # once per property, so its allowance is deliberately smaller than a tool's)
    desc = _truncate_desc(prop.get("description"), _MAX_PARAM_DESC_LEN,
                          _MAX_PARAM_DESC_SENTENCES)

    if desc:
        result["description"] = desc

    # Keep enum if small
    if "enum" in prop:
        enum_val = prop["enum"]
        if isinstance(enum_val, list) and len(enum_val) <= _MAX_ENUM_KEEP:
            result["enum"] = enum_val

    # Recurse into properties (one level of nesting)
    if "properties" in prop and isinstance(prop["properties"], dict):
        result["properties"] = {
            k: _simplify_property(v) for k, v in prop["properties"].items()
        }

    # Keep items schema for arrays (simplified)
    if prop.get("type") == "array" and "items" in prop:
        result["items"] = _simplify_property(prop["items"])

    # Keep required for nested objects
    if "required" in prop and isinstance(prop["required"], list):
        result["required"] = prop["required"]

    return result


def simplify_schema(full_schema: dict | None) -> dict:
    """Simplify a full MCP tool inputSchema.

    Args:
        full_schema: The original JSON Schema from MCP server's tools/list

    Returns:
        A simplified schema with fewer tokens, but still valid
        JSON Schema that agents (Claude Code, Cursor) can understand.

    Example:
        Input:  {"type": "object", "properties": {"url": {"type": "string",
                 "description": "The URL to fetch. Must be a valid HTTP(S) URL.
                 Supports redirects, SSL, etc. Example: https://example.com",
                 "pattern": "^https?://", "format": "uri", "default": "https://"}},
                 "required": ["url"], "additionalProperties": False,
                 "$schema": "http://json-schema.org/draft-07/schema#"}
        Output: {"type": "object", "properties": {"url": {"type": "string",
                 "description": "The URL to fetch."}}, "required": ["url"]}
    """
    if not full_schema or not isinstance(full_schema, dict):
        return {"type": "object", "properties": {}}

    result: dict[str, Any] = {}

    # Keep type
    if "type" in full_schema:
        result["type"] = full_schema["type"]

    # Simplify properties
    if "properties" in full_schema and isinstance(full_schema["properties"], dict):
        result["properties"] = {
            k: _simplify_property(v)
            for k, v in full_schema["properties"].items()
        }

    # Keep required
    if "required" in full_schema and isinstance(full_schema["required"], list):
        result["required"] = full_schema["required"]

    return result


def simplify_tool_def(tool_def: dict) -> dict:
    """Simplify a full MCP tool definition for tools/list response.

    Args:
        tool_def: Original tool definition from MCP server
            {"name": "fetch", "description": "...", "inputSchema": {...}}

    Returns:
        Simplified tool definition with compact schema.
    """
    if not isinstance(tool_def, dict):
        return tool_def

    result = {
        "name": tool_def.get("name", ""),
        "description": _truncate_desc(tool_def.get("description")),
        "inputSchema": simplify_schema(tool_def.get("inputSchema")),
    }

    # `title` and `outputSchema` are MCP-spec fields a client reads off tools/list.
    # This function compacts schemas; it has no business deleting declared metadata.
    # Dropping them cost something real: the return contract vanished from the agent's
    # view, leaving the prose as the only place a tool's output was explained — so the
    # description had to spend tokens re-stating a shape the server already published.
    title = tool_def.get("title")
    if isinstance(title, str) and title.strip():
        result["title"] = title.strip()

    output_schema = tool_def.get("outputSchema")
    if isinstance(output_schema, dict) and output_schema:
        result["outputSchema"] = simplify_schema(output_schema)

    # Keep annotations if present (MCP spec optional field)
    if "annotations" in tool_def and isinstance(tool_def["annotations"], dict):
        annotations = {}
        for key in ("title", "destructiveHint", "readOnlyHint", "idempotentHint",
                    "openWorldHint"):
            if key in tool_def["annotations"]:
                annotations[key] = tool_def["annotations"][key]
        if annotations:
            result["annotations"] = annotations

    return result


def estimate_token_reduction(full: str, simplified: str) -> float:
    """Estimate token reduction ratio.

    Uses chars/4 as rough token approximation (matching the old benchmark approach).
    """
    full_tokens = max(len(full) // 4, 1)
    slim_tokens = max(len(simplified) // 4, 1)
    return 1.0 - (slim_tokens / full_tokens)


def validate_args(args: dict | None, full_schema: dict | None) -> list[str]:
    """Validate arguments against the FULL (unsimplified) schema.

    Used by serve mode's call_tool to validate agent-provided arguments
    before forwarding to the underlying MCP server.

    Returns a list of error messages (empty if valid).

    Note: This is a lightweight validator, not a full JSON Schema validator.
    It checks:
      - Required fields are present
      - Type matches (string, number, boolean, array, object)
      - Enum membership for scalar values (when the schema lists an enum)
      - Does NOT check: pattern, format, additionalProperties
    """
    errors: list[str] = []

    if not args:
        args = {}
    if not full_schema:
        return errors

    properties = full_schema.get("properties", {})
    required = full_schema.get("required", [])

    # Check required fields
    for field in required:
        if field not in args:
            errors.append(f"Missing required parameter: '{field}'")

    # Check types
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for key, val in args.items():
        if key not in properties:
            continue  # Don't reject unknown fields (server may accept them)
        expected_type = properties.get(key, {}).get("type")
        if not expected_type:
            continue
        # Special case: bool is subclass of int in Python
        if expected_type == "integer" and isinstance(val, bool):
            errors.append(f"Parameter '{key}': expected integer, got boolean")
            continue
        if expected_type == "number" and isinstance(val, bool):
            errors.append(f"Parameter '{key}': expected number, got boolean")
            continue
        python_type = type_map.get(expected_type)
        if python_type and not isinstance(val, python_type):
            errors.append(
                f"Parameter '{key}': expected {expected_type}, "
                f"got {type(val).__name__}"
            )
            continue
        # Enum membership: a wrong discriminator (e.g. colorScheme="PINK",
        # type="go") passes type checks but is a silent no-op or server error.
        # Only enforce for scalar values so nested objects/arrays are skipped.
        enum_val = properties.get(key, {}).get("enum")
        if (
            isinstance(enum_val, list)
            and enum_val
            and isinstance(val, (str, int, float, bool))
            and val not in enum_val
        ):
            errors.append(
                f"Parameter '{key}': {val!r} is not one of "
                f"{enum_val}"
            )

    return errors


def namespaced_tool_name(server: str, tool: str) -> str:
    """Generate namespaced tool name: {server}_{tool} (ADR 0007)."""
    return f"{server}_{tool}"


def split_namespaced(name: str, known_servers: list[str]) -> tuple[str, str]:
    """Split a namespaced tool name back into (server, tool).

    Uses longest-match against known server names to handle
    server names that contain underscores.
    """
    # Try exact match first (name might be just the server)
    for srv in sorted(known_servers, key=len, reverse=True):
        prefix = f"{srv}_"
        if name.startswith(prefix):
            tool = name[len(prefix):]
            return srv, tool
    # Fallback: split on first underscore
    if "_" in name:
        server, tool = name.split("_", 1)
        return server, tool
    return "", name


def compute_token_stats(full_json: str, simplified_json: str) -> dict:
    """Compute token statistics for display."""
    full_tokens = max(len(full_json) // 4, 1)
    slim_tokens = max(len(simplified_json) // 4, 1)
    reduction = (1 - slim_tokens / full_tokens) * 100
    return {
        "full_tokens": full_tokens,
        "simplified_tokens": slim_tokens,
        "reduction_pct": round(reduction, 1),
    }
