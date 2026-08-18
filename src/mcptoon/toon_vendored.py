# Copyright 2025-2026 cxh (mcptoon wrapper)
# Original TOON encoder/decoder: Copyright (c) 2025 Xavi Vinaixa (xaviviro)
# Source: https://github.com/xaviviro/python-toon (MIT License)
# Vendored under MIT License — see NOTICE for full attribution.
#
# This is a vendored copy of python-toon v0.1.1, providing spec-compliant
# TOON encoding/decoding per toon-format/toon spec v4.1.
# https://github.com/toon-format/toon — 25K stars, official TypeScript reference.
#
# Changes from upstream:
#   - Consolidated into a single file for easy vendoring
#   - Non-strict decode by default (mcptoon needs lenient parsing)
#   - Empty input returns {} instead of raising (mcptoon compat)

"""
Vendored TOON (Token-Oriented Object Notation) encoder/decoder.

Implements the TOON spec v4.1 (toon-format/toon).
- encode(): JSON → TOON (spec-compliant, round-trip safe)
- decode(): TOON → JSON (strict and non-strict modes)

Source: python-toon v0.1.1 by Xavi Vinaixa (MIT License)
"""

import re
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

LIST_ITEM_MARKER = "-"
LIST_ITEM_PREFIX = "- "

COMMA = ","
COLON = ":"
SPACE = " "
PIPE = "|"

OPEN_BRACKET = "["
CLOSE_BRACKET = "]"
OPEN_BRACE = "{"
CLOSE_BRACE = "}"

NULL_LITERAL = "null"
TRUE_LITERAL = "true"
FALSE_LITERAL = "false"

BACKSLASH = "\\"
DOUBLE_QUOTE = '"'
NEWLINE = "\n"
CARRIAGE_RETURN = "\r"
TAB = "\t"

DELIMITERS = {"comma": ",", "tab": "\t", "pipe": "|"}
DEFAULT_DELIMITER = DELIMITERS["comma"]

# ═══════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════

JsonPrimitive = str | int | float | bool | None
JsonObject = dict[str, Any]
JsonArray = list[Any]
JsonValue = JsonPrimitive | JsonArray | JsonObject

Delimiter = str
Depth = int


class EncodeOptions(dict):
    """Options for TOON encoding."""
    pass


class ResolvedEncodeOptions:
    def __init__(self, indent=2, delimiter=",", length_marker=False):
        self.indent = indent
        self.delimiter = delimiter
        self.lengthMarker = length_marker


class DecodeOptions:
    def __init__(self, indent=2, strict=True):
        self.indent = indent
        self.strict = strict


# ═══════════════════════════════════════════════════════════════
# Normalize
# ═══════════════════════════════════════════════════════════════

def normalize_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 0:
            return 0
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    if isinstance(value, set):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(val) for key, val in value.items()}
    if callable(value):
        return None
    try:
        if hasattr(value, "__dict__"):
            return None
        return str(value)
    except Exception:
        return None


def is_json_primitive(value):
    return value is None or isinstance(value, (bool, int, float, str))


def is_json_array(value):
    return isinstance(value, list)


def is_json_object(value):
    return isinstance(value, dict) and not isinstance(value, list)


def is_array_of_primitives(arr):
    return all(is_json_primitive(item) for item in arr)


def is_array_of_arrays(arr):
    return all(is_json_array(item) for item in arr)


def is_array_of_objects(arr):
    return all(is_json_object(item) for item in arr)


# ═══════════════════════════════════════════════════════════════
# Primitives
# ═══════════════════════════════════════════════════════════════

def encode_primitive(value, delimiter=COMMA):
    if value is None:
        return NULL_LITERAL
    if isinstance(value, bool):
        return TRUE_LITERAL if value else FALSE_LITERAL
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return encode_string_literal(value, delimiter)
    return str(value)


def escape_string(value):
    result = value
    result = result.replace(BACKSLASH, BACKSLASH + BACKSLASH)
    result = result.replace(DOUBLE_QUOTE, BACKSLASH + DOUBLE_QUOTE)
    result = result.replace(NEWLINE, BACKSLASH + "n")
    result = result.replace(CARRIAGE_RETURN, BACKSLASH + "r")
    result = result.replace(TAB, BACKSLASH + "t")
    return result


def is_safe_unquoted(value, delimiter=COMMA):
    if not value:
        return False
    if value != value.strip():
        return False
    if value in (NULL_LITERAL, TRUE_LITERAL, FALSE_LITERAL):
        return False
    try:
        float(value)
        return False
    except ValueError:
        pass
    if value.startswith(LIST_ITEM_MARKER):
        return False
    unsafe_chars = [COLON, delimiter, OPEN_BRACKET, CLOSE_BRACKET,
                    OPEN_BRACE, CLOSE_BRACE, DOUBLE_QUOTE, BACKSLASH,
                    NEWLINE, CARRIAGE_RETURN, TAB]
    if any(char in value for char in unsafe_chars):
        return False
    return True


def encode_string_literal(value, delimiter=COMMA):
    if is_safe_unquoted(value, delimiter):
        return value
    return f'{DOUBLE_QUOTE}{escape_string(value)}{DOUBLE_QUOTE}'


def encode_key(key):
    if re.match(r"^[A-Z_][\w.]*$", key, re.IGNORECASE):
        return key
    return f'{DOUBLE_QUOTE}{escape_string(key)}{DOUBLE_QUOTE}'


def join_encoded_values(values, delimiter):
    return delimiter.join(values)


def format_header(key, length, fields, delimiter, length_marker):
    marker_prefix = length_marker if length_marker else ""
    fields_str = ""
    if fields:
        fields_str = f"{OPEN_BRACE}{delimiter.join(fields)}{CLOSE_BRACE}"
    if fields or delimiter != COMMA:
        length_str = f"{OPEN_BRACKET}{marker_prefix}{length}{delimiter}{CLOSE_BRACKET}"
    else:
        length_str = f"{OPEN_BRACKET}{marker_prefix}{length}{CLOSE_BRACKET}"
    if key:
        return f"{encode_key(key)}{length_str}{fields_str}{COLON}"
    return f"{length_str}{fields_str}{COLON}"


# ═══════════════════════════════════════════════════════════════
# Line Writer
# ═══════════════════════════════════════════════════════════════

class LineWriter:
    def __init__(self, indent_size):
        self._lines = []
        self._indentation_string = " " * indent_size

    def push(self, depth, content):
        indent = self._indentation_string * depth
        self._lines.append(f"{indent}{content}")

    def to_string(self):
        return "\n".join(self._lines)


# ═══════════════════════════════════════════════════════════════
# Encoders
# ═══════════════════════════════════════════════════════════════

def encode_value(value, options, writer, depth=0):
    if is_json_primitive(value):
        writer.push(depth, encode_primitive(value, options.delimiter))
    elif is_json_array(value):
        encode_array(value, options, writer, depth, None)
    elif is_json_object(value):
        encode_object(value, options, writer, depth, None)


def encode_object(obj, options, writer, depth, key):
    if key:
        writer.push(depth, f"{encode_key(key)}:")
    for obj_key, obj_value in obj.items():
        encode_key_value_pair(obj_key, obj_value, options, writer,
                              depth if not key else depth + 1)


def encode_key_value_pair(key, value, options, writer, depth):
    if is_json_primitive(value):
        writer.push(depth, f"{encode_key(key)}: {encode_primitive(value, options.delimiter)}")
    elif is_json_array(value):
        encode_array(value, options, writer, depth, key)
    elif is_json_object(value):
        encode_object(value, options, writer, depth, key)


def encode_array(arr, options, writer, depth, key):
    if not arr:
        header = format_header(key, 0, None, options.delimiter, options.lengthMarker)
        writer.push(depth, header)
        return
    if is_array_of_primitives(arr):
        encode_inline_primitive_array(arr, options, writer, depth, key)
    elif is_array_of_arrays(arr):
        encode_array_of_arrays(arr, options, writer, depth, key)
    elif is_array_of_objects(arr):
        tabular_header = detect_tabular_header(arr, options.delimiter)
        if tabular_header:
            encode_array_of_objects_as_tabular(arr, tabular_header, options, writer, depth, key)
        else:
            encode_mixed_array_as_list_items(arr, options, writer, depth, key)
    else:
        encode_mixed_array_as_list_items(arr, options, writer, depth, key)


def encode_inline_primitive_array(arr, options, writer, depth, key):
    encoded_values = [encode_primitive(item, options.delimiter) for item in arr]
    joined = join_encoded_values(encoded_values, options.delimiter)
    header = format_header(key, len(arr), None, options.delimiter, options.lengthMarker)
    writer.push(depth, f"{header} {joined}")


def encode_array_of_arrays(arr, options, writer, depth, key):
    header = format_header(key, len(arr), None, options.delimiter, options.lengthMarker)
    writer.push(depth, header)
    for item in arr:
        if is_array_of_primitives(item):
            encoded_values = [encode_primitive(v, options.delimiter) for v in item]
            joined = join_encoded_values(encoded_values, options.delimiter)
            length_marker = options.lengthMarker if options.lengthMarker else ""
            writer.push(depth + 1,
                        f"{LIST_ITEM_PREFIX}[{length_marker}{len(item)}{options.delimiter}]: {joined}")
        else:
            encode_array(item, options, writer, depth + 1, None)


def detect_tabular_header(arr, delimiter):
    if not arr:
        return None
    first_keys = list(arr[0].keys())
    for obj in arr:
        if list(obj.keys()) != first_keys:
            return None
        if not all(is_json_primitive(value) for value in obj.values()):
            return None
    return first_keys


def encode_array_of_objects_as_tabular(arr, fields, options, writer, depth, key):
    header = format_header(key, len(arr), fields, options.delimiter, options.lengthMarker)
    writer.push(depth, header)
    for obj in arr:
        row_values = [encode_primitive(obj[field], options.delimiter) for field in fields]
        row = join_encoded_values(row_values, options.delimiter)
        writer.push(depth + 1, row)


def encode_mixed_array_as_list_items(arr, options, writer, depth, key):
    header = format_header(key, len(arr), None, options.delimiter, options.lengthMarker)
    writer.push(depth, header)
    for item in arr:
        if is_json_primitive(item):
            writer.push(depth + 1, f"{LIST_ITEM_PREFIX}{encode_primitive(item, options.delimiter)}")
        elif is_json_object(item):
            encode_object_as_list_item(item, options, writer, depth + 1)
        elif is_json_array(item):
            encode_array(item, options, writer, depth + 1, None)


def encode_object_as_list_item(obj, options, writer, depth):
    keys = list(obj.items())
    if not keys:
        writer.push(depth, LIST_ITEM_PREFIX.rstrip())
        return
    first_key, first_value = keys[0]
    if is_json_primitive(first_value):
        encoded_val = encode_primitive(first_value, options.delimiter)
        writer.push(depth, f"{LIST_ITEM_PREFIX}{encode_key(first_key)}: {encoded_val}")
    else:
        writer.push(depth, LIST_ITEM_PREFIX.rstrip())
        encode_key_value_pair(first_key, first_value, options, writer, depth + 1)
    for key, value in keys[1:]:
        encode_key_value_pair(key, value, options, writer, depth + 1)


# ═══════════════════════════════════════════════════════════════
# Encoder entry point
# ═══════════════════════════════════════════════════════════════

def encode(value, options=None):
    """Encode a value into TOON format (spec v4.1 compliant)."""
    normalized = normalize_value(value)
    resolved_options = _resolve_options(options)
    writer = LineWriter(resolved_options.indent)
    encode_value(normalized, resolved_options, writer, 0)
    return writer.to_string()


def _resolve_options(options):
    if options is None:
        return ResolvedEncodeOptions()
    indent = options.get("indent", 2)
    delimiter = options.get("delimiter", DEFAULT_DELIMITER)
    length_marker = options.get("lengthMarker", False)
    if delimiter in DELIMITERS:
        delimiter = DELIMITERS[delimiter]
    return ResolvedEncodeOptions(indent=indent, delimiter=delimiter, length_marker=length_marker)


# ═══════════════════════════════════════════════════════════════
# Decoder
# ═══════════════════════════════════════════════════════════════

class ToonDecodeError(Exception):
    """TOON decoding error."""
    pass


class _Line:
    def __init__(self, content, depth, line_number):
        self.content = content
        self.depth = depth
        self.line_number = line_number
        self.is_blank = not content.strip()


def _compute_depth(line, indent_size, strict):
    if not line:
        return 0
    leading_spaces = len(line) - len(line.lstrip(' '))
    if strict and '\t' in line[:leading_spaces]:
        raise ToonDecodeError("Tabs are not allowed in indentation")
    if strict:
        if leading_spaces % indent_size != 0:
            raise ToonDecodeError(f"Indentation must be an exact multiple of {indent_size} spaces")
        return leading_spaces // indent_size
    return leading_spaces // indent_size


def _unescape_string(value):
    result = []
    i = 0
    while i < len(value):
        if value[i] == BACKSLASH:
            if i + 1 >= len(value):
                raise ToonDecodeError("Unterminated string: missing closing quote")
            next_char = value[i + 1]
            if next_char == BACKSLASH:
                result.append(BACKSLASH)
            elif next_char == DOUBLE_QUOTE:
                result.append(DOUBLE_QUOTE)
            elif next_char == 'n':
                result.append(NEWLINE)
            elif next_char == 'r':
                result.append(CARRIAGE_RETURN)
            elif next_char == 't':
                result.append(TAB)
            else:
                raise ToonDecodeError(f"Invalid escape sequence: \\{next_char}")
            i += 2
        else:
            result.append(value[i])
            i += 1
    return ''.join(result)


def _parse_primitive(token):
    token = token.strip()
    if token.startswith(DOUBLE_QUOTE):
        if not token.endswith(DOUBLE_QUOTE) or len(token) < 2:
            raise ToonDecodeError("Unterminated string: missing closing quote")
        return _unescape_string(token[1:-1])
    if token == TRUE_LITERAL:
        return True
    if token == FALSE_LITERAL:
        return False
    if token == NULL_LITERAL:
        return None
    if token:
        if re.match(r'^0\d+$', token):
            return token
        try:
            if '.' not in token and 'e' not in token.lower():
                return int(token)
            return float(token)
        except ValueError:
            pass
    return token


def _parse_delimited_values(line, delimiter):
    tokens = []
    current = []
    in_quotes = False
    i = 0
    while i < len(line):
        char = line[i]
        if char == DOUBLE_QUOTE:
            in_quotes = not in_quotes
            current.append(char)
        elif char == BACKSLASH and i + 1 < len(line) and in_quotes:
            current.append(char)
            current.append(line[i + 1])
            i += 1
        elif char == delimiter and not in_quotes:
            tokens.append(''.join(current))
            current = []
            i += 1
            continue
        else:
            current.append(char)
        i += 1
    if current or tokens:
        tokens.append(''.join(current))
    return tokens


def _parse_header(line):
    line = line.strip()
    bracket_start = line.find(OPEN_BRACKET)
    if bracket_start == -1:
        return None
    key = None
    if bracket_start > 0:
        key_part = line[:bracket_start].strip()
        key = _parse_key(key_part) if key_part else None
    bracket_end = line.find(CLOSE_BRACKET, bracket_start)
    if bracket_end == -1:
        return None
    bracket_content = line[bracket_start + 1:bracket_end]
    if bracket_content.startswith('#'):
        bracket_content = bracket_content[1:]
    delimiter = COMMA
    length_str = bracket_content
    if bracket_content.endswith(TAB):
        delimiter = TAB
        length_str = bracket_content[:-1]
    elif bracket_content.endswith(PIPE):
        delimiter = PIPE
        length_str = bracket_content[:-1]
    elif bracket_content.endswith(COMMA):
        delimiter = COMMA
        length_str = bracket_content[:-1]
    try:
        length = int(length_str)
    except ValueError:
        return None
    fields = None
    after_bracket = line[bracket_end + 1:].strip()
    if after_bracket.startswith(OPEN_BRACE):
        brace_end = after_bracket.find(CLOSE_BRACE)
        if brace_end == -1:
            raise ToonDecodeError("Unterminated fields segment")
        fields_content = after_bracket[1:brace_end]
        field_tokens = _parse_delimited_values(fields_content, delimiter)
        fields = [_parse_key(f.strip()) for f in field_tokens]
        after_bracket = after_bracket[brace_end + 1:].strip()
    if not after_bracket.startswith(COLON):
        return None
    return (key, length, delimiter, fields)


def _parse_key(key_str):
    key_str = key_str.strip()
    if key_str.startswith(DOUBLE_QUOTE):
        if not key_str.endswith(DOUBLE_QUOTE) or len(key_str) < 2:
            raise ToonDecodeError("Unterminated quoted key")
        return _unescape_string(key_str[1:-1])
    return key_str


def _split_key_value(line):
    in_quotes = False
    i = 0
    while i < len(line):
        char = line[i]
        if char == DOUBLE_QUOTE:
            in_quotes = not in_quotes
        elif char == BACKSLASH and i + 1 < len(line) and in_quotes:
            i += 1
        elif char == COLON and not in_quotes:
            key = line[:i].strip()
            value = line[i + 1:].strip()
            return (key, value)
        i += 1
    raise ToonDecodeError("Missing colon after key")


def _is_row_line(line, delimiter):
    first_delim_pos = None
    first_colon_pos = None
    in_quotes = False
    i = 0
    while i < len(line):
        char = line[i]
        if char == DOUBLE_QUOTE:
            in_quotes = not in_quotes
        elif char == BACKSLASH and i + 1 < len(line) and in_quotes:
            i += 1
        elif not in_quotes:
            if char == delimiter and first_delim_pos is None:
                first_delim_pos = i
            if char == COLON and first_colon_pos is None:
                first_colon_pos = i
        i += 1
    if first_colon_pos is None:
        return True
    if first_delim_pos is not None and first_delim_pos < first_colon_pos:
        return True
    return False


# ─── Decode functions ───

def _decode_object(lines, start_idx, parent_depth, strict):
    result = {}
    i = start_idx
    expected_depth = parent_depth if start_idx == 0 else parent_depth + 1
    while i < len(lines):
        line = lines[i]
        if line.is_blank:
            i += 1
            continue
        if line.depth < expected_depth:
            break
        if line.depth > expected_depth:
            i += 1
            continue
        content = line.content
        header_info = _parse_header(content)
        if header_info is not None:
            key, length, delimiter, fields = header_info
            if key is not None:
                array_val, next_i = _decode_array_from_header(lines, i, line.depth, header_info, strict)
                result[key] = array_val
                i = next_i
                continue
        try:
            key_str, value_str = _split_key_value(content)
        except ToonDecodeError:
            if strict:
                raise
            i += 1
            continue
        key = _parse_key(key_str)
        if not value_str:
            result[key] = _decode_object(lines, i + 1, line.depth, strict)
            i += 1
            while i < len(lines) and lines[i].depth > line.depth:
                i += 1
        else:
            result[key] = _parse_primitive(value_str)
            i += 1
    return result


def _decode_array_from_header(lines, header_idx, header_depth, header_info, strict):
    key, length, delimiter, fields = header_info
    header_line = lines[header_idx].content
    colon_idx = header_line.rfind(COLON)
    inline_content = header_line[colon_idx + 1:].strip()
    if inline_content:
        return _decode_inline_array(inline_content, delimiter, length, strict), header_idx + 1
    if fields is not None:
        return _decode_tabular_array(lines, header_idx + 1, header_depth, fields, delimiter, length, strict)
    return _decode_list_array(lines, header_idx + 1, header_depth, delimiter, length, strict)


def _decode_inline_array(content, delimiter, expected_length, strict):
    if not content and expected_length == 0:
        return []
    tokens = _parse_delimited_values(content, delimiter)
    values = [_parse_primitive(token) for token in tokens]
    if strict and len(values) != expected_length:
        raise ToonDecodeError(f"Expected {expected_length} values, but got {len(values)}")
    return values


def _decode_tabular_array(lines, start_idx, header_depth, fields, delimiter, expected_length, strict):
    result = []
    i = start_idx
    row_depth = header_depth + 1
    while i < len(lines):
        line = lines[i]
        if line.is_blank:
            if strict:
                raise ToonDecodeError("Blank lines not allowed inside arrays")
            i += 1
            continue
        if line.depth < row_depth:
            break
        if line.depth > row_depth:
            break
        content = line.content
        if _is_row_line(content, delimiter):
            tokens = _parse_delimited_values(content, delimiter)
            values = [_parse_primitive(token) for token in tokens]
            if strict and len(values) != len(fields):
                raise ToonDecodeError(f"Expected {len(fields)} values in row, but got {len(values)}")
            obj = {fields[j]: values[j] for j in range(min(len(fields), len(values)))}
            result.append(obj)
            i += 1
        else:
            break
    if strict and len(result) != expected_length:
        raise ToonDecodeError(f"Expected {expected_length} rows, but got {len(result)}")
    return result, i


def _decode_list_array(lines, start_idx, header_depth, delimiter, expected_length, strict):
    result = []
    i = start_idx
    item_depth = header_depth + 1
    while i < len(lines):
        line = lines[i]
        if line.is_blank:
            if strict:
                raise ToonDecodeError("Blank lines not allowed inside arrays")
            i += 1
            continue
        if line.depth < item_depth:
            break
        content = line.content
        if not content.startswith(LIST_ITEM_MARKER):
            break
        item_content = content[len(LIST_ITEM_MARKER):].strip()
        item_header = _parse_header(item_content)
        if item_header is not None:
            key, length, item_delim, fields = item_header
            if key is None:
                colon_idx = item_content.find(COLON)
                if colon_idx != -1:
                    inline_part = item_content[colon_idx + 1:].strip()
                    if inline_part:
                        item_val = _decode_inline_array(inline_part, item_delim, length, strict)
                        result.append(item_val)
                        i += 1
                        continue
            else:
                item_obj = {}
                array_val, next_i = _decode_array_from_header(lines, i, line.depth, item_header, strict)
                item_obj[key] = array_val
                i = next_i
                while i < len(lines) and lines[i].depth == line.depth + 1:
                    field_line = lines[i]
                    if field_line.is_blank:
                        i += 1
                        continue
                    field_content = field_line.content
                    field_header = _parse_header(field_content)
                    if field_header is not None and field_header[0] is not None:
                        field_key, field_length, field_delim, field_fields = field_header
                        field_val, next_i = _decode_array_from_header(lines, i, field_line.depth, field_header, strict)
                        item_obj[field_key] = field_val
                        i = next_i
                        continue
                    try:
                        field_key_str, field_value_str = _split_key_value(field_content)
                        field_key = _parse_key(field_key_str)
                        if not field_value_str:
                            item_obj[field_key] = _decode_object(lines, i + 1, field_line.depth, strict)
                            i += 1
                            while i < len(lines) and lines[i].depth > field_line.depth:
                                i += 1
                        else:
                            item_obj[field_key] = _parse_primitive(field_value_str)
                            i += 1
                    except ToonDecodeError:
                        break
                result.append(item_obj)
                continue
        try:
            key_str, value_str = _split_key_value(item_content)
            item_obj = {}
            key = _parse_key(key_str)
            if not value_str:
                nested = _decode_object(lines, i + 1, line.depth + 1, strict)
                item_obj[key] = nested
                i += 1
                while i < len(lines) and lines[i].depth > line.depth + 1:
                    i += 1
            else:
                item_obj[key] = _parse_primitive(value_str)
                i += 1
            while i < len(lines) and lines[i].depth == line.depth + 1:
                field_line = lines[i]
                if field_line.is_blank:
                    i += 1
                    continue
                field_content = field_line.content
                field_header = _parse_header(field_content)
                if field_header is not None and field_header[0] is not None:
                    field_key, field_length, field_delim, field_fields = field_header
                    field_val, next_i = _decode_array_from_header(lines, i, field_line.depth, field_header, strict)
                    item_obj[field_key] = field_val
                    i = next_i
                    continue
                try:
                    field_key_str, field_value_str = _split_key_value(field_content)
                    field_key = _parse_key(field_key_str)
                    if not field_value_str:
                        item_obj[field_key] = _decode_object(lines, i + 1, field_line.depth, strict)
                        i += 1
                        while i < len(lines) and lines[i].depth > field_line.depth:
                            i += 1
                    else:
                        item_obj[field_key] = _parse_primitive(field_value_str)
                        i += 1
                except ToonDecodeError:
                    break
            result.append(item_obj)
        except ToonDecodeError:
            result.append(_parse_primitive(item_content))
            i += 1
    if strict and len(result) != expected_length:
        raise ToonDecodeError(f"Expected {expected_length} items, but got {len(result)}")
    return result, i


# ═══════════════════════════════════════════════════════════════
# Decoder entry point
# ═══════════════════════════════════════════════════════════════

def decode(input_str, options=None):
    """Decode a TOON-formatted string to a Python value.

    Uses non-strict mode by default for lenient parsing (mcptoon compat).
    Empty input returns {} instead of raising.
    """
    if not input_str or not input_str.strip():
        return {}

    if options is None:
        options = DecodeOptions(strict=False)
    elif isinstance(options, dict):
        options = DecodeOptions(
            indent=options.get("indent", 2),
            strict=options.get("strict", False)
        )

    indent_size = options.indent
    strict = options.strict

    raw_lines = input_str.split('\n')
    lines = []
    for i, raw in enumerate(raw_lines):
        if i == len(raw_lines) - 1 and not raw.strip():
            continue
        depth = _compute_depth(raw, indent_size, strict)
        line = _Line(raw.strip(), depth, i + 1)
        if line.content or not strict:
            lines.append(line)

    non_blank_lines = [ln for ln in lines if not ln.is_blank]
    if not non_blank_lines:
        return {}

    first_line = non_blank_lines[0]
    header_info = _parse_header(first_line.content)
    if header_info is not None and header_info[0] is None:
        arr, _ = _decode_array_from_header(lines, 0, 0, header_info, strict)
        return arr

    if len(non_blank_lines) == 1:
        line_content = first_line.content
        try:
            _split_key_value(line_content)
        except ToonDecodeError:
            if header_info is None:
                return _parse_primitive(line_content)

    return _decode_object(lines, 0, 0, strict)
