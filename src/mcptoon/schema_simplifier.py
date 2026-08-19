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
(80-90% fewer tokens) while call_tool validates with the full schema.

Strategy:
  - Keep standard JSON Schema structure (type, properties, required)
  - Truncate long descriptions to 1 sentence (< 100 chars)
  - Remove: examples, $ref, $schema, additionalProperties, pattern, format,
    default, enum (unless < 5 items), title, $comment, deprecated, readOnly, writeOnly
  - Flatten one level of nested properties
"""

from __future__ import annotations

import json
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

# Max description length (characters)
_MAX_DESC_LEN = 120

# Max enum items to keep (larger enums are removed to save tokens)
_MAX_ENUM_KEEP = 5


def _truncate_desc(desc: str | None) -> str | None:
    """Truncate a description string to one sentence, max _MAX_DESC_LEN chars."""
    if not desc:
        return None
    desc = desc.strip()
    # Take first sentence (up to period, question mark, or newline)
    for sep in (". ", ".\n", "? ", "!\n", "\n"):
        idx = desc.find(sep)
        if idx > 0:
            desc = desc[:idx + 1]
            break
    if len(desc) > _MAX_DESC_LEN:
        desc = desc[:_MAX_DESC_LEN - 3] + "..."
    return desc


def _simplify_property(prop: dict) -> dict:
    """Simplify a single property definition."""
    if not isinstance(prop, dict):
        return prop

    result: dict[str, Any] = {}

    # Keep type (most important for agent to know how to call)
    if "type" in prop:
        result["type"] = prop["type"]

    # Keep description (truncated)
    desc = _truncate_desc(prop.get("description"))
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
        A simplified schema with 80-90% fewer tokens, but still valid
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

    # Keep annotations if present (MCP spec optional field)
    if "annotations" in tool_def and isinstance(tool_def["annotations"], dict):
        annotations = {}
        for key in ("title", "destructiveHint", "readOnlyHint", "idempotentHint"):
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
      - Does NOT check: pattern, format, enum, additionalProperties
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
