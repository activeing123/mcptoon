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

"""Tests for `mcptoon demo-server` — the built-in, self-contained MCP server.

Why these tests go beyond "it answers": the server exists because Glama's TDQS
scorer runs `tools/list` inside a Python container with no Node, and the previous
demo seed (`npx -y @modelcontextprotocol/server-everything`) resolves to zero tools
there — a zero-tool listing is never scored at all (measured 2026-09-14). So the
properties worth pinning are:

  1. it always answers with a non-empty, well-formed tool list, over the real CLI,
  2. it does that with nothing installed, nothing configured and no network,
  3. the definitions are good enough to be *graded*, not merely listed: the rubric
     at https://tdqs.dev/spec is public, so its hard gates (missing or tautological
     description, annotation contradiction, priority-manipulation phrasing) are
     checkable mechanically, and the heavily weighted dimensions are checkable by
     proxy (verb first, a named sibling as boundary, parameters described),
  4. every tool actually runs, and reports what it cannot do.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcptoon import demo_server as ds  # noqa: E402
from mcptoon import schema_simplifier  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE = os.path.join(ROOT, "src", "mcptoon", "demo_server.py")

VALID_CALLS = {
    "echo_message": {"message": "ping"},
    "compare_formats": {"payload": json.dumps({"a": 1, "b": ["x", "y"]})},
    "encode_toon": {"payload": json.dumps({"k": "v"})},
    "decode_toon": {"toon": "k: v"},
    "estimate_tokens": {"text": "some text to count" * 3},
    "simplify_tool_schema": {"tool": json.dumps({
        "name": "get_weather",
        "description": "Get current weather. Supports metric and imperial units.",
        "inputSchema": {"type": "object", "properties": {
            "city": {"type": "string", "description": "City name"}},
            "required": ["city"], "title": "Weather", "examples": [1]}})},
    "build_tool_manifest": {"manifest": json.dumps({"demo": [
        {"name": "a", "description": "does a", "inputSchema": {}},
        {"name": "b", "description": "does b", "inputSchema": {}}]})},
    "report_benchmark_rows": {},
    "list_supported_agents": {},
    "validate_config_draft": {"config": json.dumps({"mcpServers": {
        "ok": {"command": "python", "args": ["-m", "mcptoon", "demo-server"]}}})},
    "describe_runtime": {},
}


def drive(requests):
    """Feed JSON-RPC requests to a DemoServer in-process; return the responses."""
    server = ds.DemoServer()
    responses = []
    with mock.patch.object(ds, "_log", lambda msg: None), \
            redirect_stdout(io.StringIO()):
        for request in requests:
            reply = server.handle_request(request)
            if reply is not None:
                responses.append(reply)
    return responses


def call(name, arguments):
    """One tools/call, returning the MCP result object."""
    return drive([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}])[0]["result"]


def payload_of(result):
    return json.loads(result["content"][0]["text"])


class TestHandshake(unittest.TestCase):
    def test_initialize_negotiates_supported_version(self):
        result = drive([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}}}])[0]["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "mcptoon-demo")
        self.assertIn("tools", result["capabilities"])

    def test_unknown_protocol_version_falls_back(self):
        result = drive([{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "1999-01-01"}}])[0]["result"]
        self.assertEqual(result["protocolVersion"], ds.PROTOCOL_VERSION)

    def test_unsupported_version_announced_in_meta_is_rejected(self):
        reply = drive([{"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                        "params": {"_meta": {"protocolVersion": "nope"}}}])[0]
        self.assertEqual(reply["error"]["code"], -32022)

    def test_notifications_get_no_response(self):
        self.assertEqual(drive([
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}},
        ]), [])

    def test_unknown_method_is_minus_32601(self):
        reply = drive([{"jsonrpc": "2.0", "id": 7, "method": "tools/nope", "params": {}}])[0]
        self.assertEqual(reply["error"]["code"], -32601)

    def test_ping_works_without_initialize(self):
        result = drive([{"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}])[0]["result"]
        self.assertEqual(result, {"resultType": "complete"})

    def test_stateless_list_before_initialize(self):
        """ADR 0010: a client that never calls initialize still gets the tools."""
        result = drive([{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}])[0]["result"]
        self.assertEqual(len(result["tools"]), 11)

    def test_empty_result_sections(self):
        replies = drive([
            {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "prompts/list", "params": {}},
        ])
        self.assertEqual(replies[0]["result"]["resources"], [])
        self.assertEqual(replies[1]["result"]["prompts"], [])
        for reply in replies:
            self.assertIn("ttlMs", reply["result"])


class TestToolList(unittest.TestCase):
    def test_names_are_exactly_the_handled_set(self):
        self.assertEqual(sorted(ds.tool_names()), sorted(ds.HANDLERS))
        self.assertEqual(len(ds.TOOLS), 11)

    def test_every_tool_shape(self):
        for tool in ds.TOOLS:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["description"].strip())
                self.assertTrue(tool["title"].strip())
                schema = tool["inputSchema"]
                self.assertEqual(schema["type"], "object")
                self.assertIsInstance(schema["required"], list)
                for prop in schema["properties"].values():
                    self.assertIn("type", prop)
                    self.assertTrue(prop.get("description"), "every parameter is described")

    def test_annotations_say_pure_and_the_prose_agrees(self):
        effect_verbs = ("writes", "installs", "deletes", "creates", "sends", "modifies", "stores")
        denials = ("no ", "not ", "none", "never", "nothing", "cannot", "without")
        for tool in ds.TOOLS:
            with self.subTest(tool=tool["name"]):
                ann = tool["annotations"]
                self.assertTrue(ann["readOnlyHint"])
                self.assertFalse(ann["destructiveHint"])
                self.assertTrue(ann["idempotentHint"])
                self.assertFalse(ann["openWorldHint"])
                # TDQS raises Annotation Contradiction and zeroes the dimension when
                # the prose claims an effect the hints deny. Word boundaries matter:
                # "Rewrites one tool definition" is not a claim of disk activity.
                lowered = tool["description"].lower()
                for verb in effect_verbs:
                    for match in re.finditer(rf"\b{verb}\b", lowered):
                        window = lowered[max(0, match.start() - 15):match.end() + 15]
                        self.assertTrue(any(d in window for d in denials),
                                        f"'{verb}' asserts an effect readOnlyHint denies")

    def test_contradiction_guard_actually_fires(self):
        """Negative control: the guard above is not a tautology."""
        tool = dict(ds.TOOLS[0])
        tool["description"] = "Returns the message. It writes the text to a log file on disk."
        lowered = tool["description"].lower()
        hits = [m for m in re.finditer(r"\bwrites\b", lowered)
                if not any(d in lowered[max(0, m.start() - 15):m.end() + 15]
                           for d in ("no ", "not ", "none", "never", "nothing", "cannot", "without"))]
        self.assertEqual(len(hits), 1, "an unhedged 'writes' must be caught")


def _walk_fields(properties: dict, path: str = ""):
    """Yield (path, field) for every property declaration, nested ones included."""
    for key, field in properties.items():
        here = f"{path}.{key}" if path else key
        yield here, field
        if isinstance(field, dict):
            nested = field.get("properties")
            if isinstance(nested, dict):
                yield from _walk_fields(nested, here)
            items = field.get("items")
            if isinstance(items, dict) and isinstance(items.get("properties"), dict):
                yield from _walk_fields(items["properties"], f"{here}[]")


class TestReturnContract(unittest.TestCase):
    """The output half of a definition: the `outputSchema` and the `structuredContent`
    that has to back it.

    Glama's TDQS v1.3 reads the output schema itself and grades it by *what it
    documents* — a bare `{"type": "object"}` relieves a description of nothing — so
    the shapes below are scored, not decorative. Which also makes them a promise: a
    field named here that a handler stopped returning would be a lie on the wire.
    """

    def test_every_tool_declares_its_output_schema(self):
        for tool in ds.TOOLS:
            with self.subTest(tool=tool["name"]):
                schema = tool.get("outputSchema")
                self.assertIsInstance(schema, dict, "the return shape must be declared")
                self.assertEqual(schema["type"], "object")
                self.assertTrue(schema["properties"], "an empty schema documents nothing")
                for key in schema["required"]:
                    self.assertIn(key, schema["properties"], f"'{key}' is not a field")

    def test_every_returned_field_is_documented(self):
        for tool in ds.TOOLS:
            with self.subTest(tool=tool["name"]):
                for where, field in _walk_fields(tool["outputSchema"]["properties"]):
                    self.assertIsInstance(field, dict)
                    self.assertTrue(field.get("description"), f"{where} is undocumented")

    def test_field_notes_survive_compaction_untouched(self):
        """The gateway budgets a parameter's description at two sentences / 200
        characters and reflows anything longer, so a note that overruns it is exactly
        what a client downstream never sees. Anything cut here is cut in transit."""

        for tool in ds.TOOLS:
            for where, field in _walk_fields(tool["outputSchema"]["properties"]):
                note = field["description"]
                with self.subTest(tool=tool["name"], field=where):
                    self.assertEqual(note, schema_simplifier._truncate_desc(note),
                                     "the compactor rewrote this note — front-load it")

    def test_handlers_return_what_the_schema_promises(self):
        for tool in ds.TOOLS:
            name = tool["name"]
            with self.subTest(tool=name):
                result = call(name, VALID_CALLS[name])
                payload = result.get("structuredContent")
                self.assertIsInstance(
                    payload, dict,
                    "a declared outputSchema must be backed by structuredContent")
                declared = set(tool["outputSchema"]["properties"])
                for key in tool["outputSchema"]["required"]:
                    self.assertIn(key, payload, f"promised '{key}', did not return it")
                undeclared = set(payload) - declared
                self.assertFalse(undeclared, f"returns undeclared fields {sorted(undeclared)}")

    def test_structured_content_agrees_with_the_text_block(self):
        """The legacy text block and the structured one must not disagree."""
        for name, arguments in VALID_CALLS.items():
            with self.subTest(tool=name):
                result = call(name, arguments)
                self.assertEqual(json.loads(result["content"][0]["text"]),
                                 result["structuredContent"])

    def test_the_contract_survives_the_gateway_compactor(self):
        """`serve` relays these definitions through `simplify_tool_def`, and an agent
        — or a registry scoring the hosted instance — reads the relayed copy. If the
        compactor dropped title, outputSchema or its field notes, the published
        promise would be invisible exactly where it counts."""
        for tool in ds.TOOLS:
            slim = schema_simplifier.simplify_tool_def(tool)
            with self.subTest(tool=tool["name"]):
                self.assertEqual(slim["title"], tool["title"])
                self.assertIn("outputSchema", slim)
                self.assertEqual(slim["annotations"]["openWorldHint"], False)
                for where, field in _walk_fields(slim["outputSchema"]["properties"]):
                    self.assertTrue(field.get("description"), f"{where} lost its note")


class TestDefinitionsAreGradeable(unittest.TestCase):
    """Mechanical mirrors of the published TDQS gates and heavy-weight dimensions."""

    VERB_FIRST = ("returns", "encodes", "converts", "parses", "counts", "rewrites",
                  "reduces", "reports", "lists", "checks", "describes")

    def setUp(self):
        self.tools = {t["name"]: t for t in ds.TOOLS}

    def test_no_hard_gate_trips(self):
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                desc = tool["description"]
                self.assertTrue(desc.strip(), "an empty description scores TDQS 1.0, tier D")
                self.assertNotEqual(desc.lower().strip(), name, "tautology caps Purpose Clarity at 2")
                self.assertNotEqual(desc.lower().strip(), tool["title"].lower().strip())

    def test_purpose_is_front_loaded_with_a_verb(self):
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                opening = tool["description"].split(" ", 1)[0].lower()
                self.assertIn(opening, self.VERB_FIRST, "graders weigh the first words")

    def test_size_band_is_dense_not_stuffed(self):
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                length = len(tool["description"])
                self.assertGreater(length, 240, "too thin to cover six dimensions")
                self.assertLess(length, 900, "density beats length in Conciseness")
                self.assertLessEqual(tool["description"].count(". "), 5)

    def test_every_description_draws_a_boundary_against_a_sibling(self):
        """Usage Guidelines is 20% of the score and wants a named alternative."""
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                named = [other for other in self.tools
                         if other != name and other in tool["description"]]
                self.assertGreaterEqual(len(named), 1,
                                        "must name the sibling that covers the excluded case")
                self.assertLessEqual(len(named), 3, "listing every sibling is not a boundary")

    def test_no_priority_manipulation(self):
        banned = ("always call this first", "do not call other", "must be called before",
                  "never use another", "highest priority")
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                lowered = tool["description"].lower()
                for phrase in banned:
                    self.assertNotIn(phrase, lowered, f"'{phrase}' is priority enforcement")

    def test_discloses_its_own_limits(self):
        """Where a tool cannot help, the description has to say so."""
        for name, tool in self.tools.items():
            with self.subTest(tool=name):
                lowered = tool["description"].lower()
                self.assertTrue(any(mark in lowered for mark in
                                    ("not ", "no ", "never", "nothing", "absent", "cannot",
                                     "does not", "rather than", "only ")),
                                "a definition with no stated limit reads as a promise")

    def test_every_tool_documented_in_the_handler_table(self):
        self.assertEqual(set(self.tools), set(VALID_CALLS),
                         "a new tool needs a valid-call sample here")


class TestToolBehaviour(unittest.TestCase):
    def test_every_tool_returns_a_payload(self):
        for name, arguments in VALID_CALLS.items():
            with self.subTest(tool=name):
                result = call(name, arguments)
                self.assertFalse(result["isError"], result["content"][0]["text"][:200])
                self.assertIsInstance(payload_of(result), dict)

    def test_echo_is_verbatim_including_non_ascii(self):
        payload = payload_of(call("echo_message", {"message": "héllo 世界 ✓\ttab"}))
        self.assertEqual(payload["echo"], "héllo 世界 ✓\ttab")
        self.assertFalse(payload["transformed"])

    def test_round_trip_is_lossless(self):
        original = {"name": "svc", "items": [1, 2, 3], "nested": {"ok": True, "none": None}}
        encoded = payload_of(call("encode_toon", {"payload": json.dumps(original)}))
        back = payload_of(call("decode_toon", {"toon": encoded["toon"]}))
        self.assertEqual(back["decoded"], original)

    def test_compare_formats_reports_three_forms(self):
        payload = json.dumps({"rows": [{"a": i, "b": f"v{i}"} for i in range(40)]})
        out = payload_of(call("compare_formats", {"payload": payload}))
        forms = out["formats"]
        self.assertEqual(sorted(forms), ["compact", "json", "toon"])
        self.assertEqual(forms["json"]["char_savings_pct"], 0.0)
        self.assertGreater(forms["compact"]["char_savings_pct"],
                           forms["toon"]["char_savings_pct"])
        self.assertIn("SLIM", out["slim_note"], "the absent fourth form is explained")

    def test_preview_truncates_and_says_so(self):
        out = payload_of(call("encode_toon", {"payload": json.dumps({"k": "x" * 4000})}))
        self.assertTrue(out["truncated"])
        self.assertLess(len(out["toon"]), 600)

    def test_simplify_reports_the_rules_it_applied(self):
        out = payload_of(call("simplify_tool_schema", VALID_CALLS["simplify_tool_schema"]))
        self.assertLess(out["simplified_tokens"], out["full_tokens"])
        rules = out["rules_applied"]
        # Pinned by content, not by repeating the sentence: the numbers are the
        # contract, the wording around them is allowed to improve.
        self.assertIn(str(schema_simplifier._MAX_DESC_LEN), rules["description"])
        self.assertIn(str(schema_simplifier._MAX_PARAM_DESC_LEN), rules["description"])
        self.assertIn("sentences", rules["description"])


        self.assertEqual(rules["enum_values_kept"], schema_simplifier._MAX_ENUM_KEEP)
        self.assertIn("title", rules["schema_keys_dropped"])
        self.assertNotIn("title", out["slim_tool"]["inputSchema"])

    def test_manifest_names_only_and_flags_bad_entries(self):
        manifest = {"s1": [{"name": "alpha"}, {"description": "no name"}, "beta"], "s2": []}
        out = payload_of(call("build_tool_manifest", {"manifest": json.dumps(manifest)}))
        self.assertEqual(out["name_index"], "s1: alpha, beta")
        self.assertEqual(out["skipped_entries"], ["s1[1]"])
        self.assertEqual(out["empty_servers"], ["s2"])
        self.assertLess(out["simplified_tokens"], out["full_tokens"])

    def test_manifest_with_nothing_indexed_claims_no_saving(self):
        out = payload_of(call("build_tool_manifest",
                              {"manifest": json.dumps({"s": [{"x": 1}]})}))
        self.assertEqual(out["name_index"], "")
        self.assertEqual(out["reduction_pct"], 0.0)
        self.assertEqual(out["simplified_tokens"], 0)

    def test_validate_config_names_problems_and_denies_workingness(self):
        draft = {"mcpServers": {
            "both": {"command": "x", "url": "http://y"},
            "neither": {"env": {}},
            "badargs": {"command": "x", "args": "nope"},
            "junk": {"command": "x", "bogusKey": 1},
            "notobject": "string"}}
        out = payload_of(call("validate_config_draft", {"config": json.dumps(draft)}))
        problems = {entry["name"]: entry["problems"] for entry in out["entries"]}
        self.assertEqual(out["entry_count"], 5)
        self.assertTrue(any("stdio" in p for p in problems["both"]))
        self.assertTrue(any("unusable" in p for p in problems["neither"]))
        self.assertTrue(any("args" in p for p in problems["badargs"]))
        self.assertTrue(any("bogusKey" in p for p in problems["junk"]))
        self.assertEqual(problems["notobject"], ["entry is not an object"])
        self.assertIn("whether the command exists on PATH", out["not_checked"])

    def test_agents_are_resolved_paths_not_a_disk_scan(self):
        out = payload_of(call("list_supported_agents", {}))
        self.assertEqual(out["installed_check"], "not performed")
        ids = [agent["id"] for agent in out["agents"]]
        self.assertIn("claude-desktop", ids)
        self.assertEqual(len(ids), len(ds.AGENT_PATH_HELPERS))
        for agent in out["agents"]:
            self.assertTrue(agent["config_paths"])

    def test_runtime_reports_dependency_truth(self):
        out = payload_of(call("describe_runtime", {}))
        self.assertEqual(out["mcptoon_version"], __import__("mcptoon").__version__)
        self.assertEqual(out["tool_count"], len(ds.TOOLS))
        self.assertIn("2025-06-18", out["supported_protocol_versions"])
        deps = out["third_party_runtime_dependencies"]
        if isinstance(deps, list):
            self.assertEqual(deps, [d for d in deps if "extra" not in d.lower()])

    def test_errors_come_back_as_tool_errors_not_rpc_errors(self):
        cases = (
            ("echo_message", {}, "Missing required parameter"),
            ("estimate_tokens", {"text": 5}, "expected string"),
            ("compare_formats", {"payload": "{not json"}, "not valid JSON"),
            ("validate_config_draft", {"config": "[]"}, "must be a JSON object"),
            ("simplify_tool_schema", {"tool": json.dumps({"description": "x"})}, "'name'"),
        )
        for name, arguments, fragment in cases:
            with self.subTest(tool=name):
                result = call(name, arguments)
                self.assertTrue(result["isError"])
                self.assertIn(fragment, result["content"][0]["text"])

    def test_unknown_tool_lists_what_exists(self):
        result = call("no_such_tool", {})
        self.assertTrue(result["isError"])
        for name in list(ds.HANDLERS)[:3]:
            self.assertIn(name, result["content"][0]["text"])


class TestBenchmarkConstantsMatchTheArchive(unittest.TestCase):
    """The rows are inlined because assets/ is not packaged into the wheel — so pin them."""

    def test_rows_equal_the_committed_json(self):
        path = os.path.join(ROOT, "assets", "benchmark_tiktoken.json")
        with open(path, encoding="utf-8") as handle:
            archived = json.load(handle)
        self.assertEqual(len(ds.BENCHMARK_ROWS), len(archived))
        for row, stored in zip(ds.BENCHMARK_ROWS, archived):
            for key in ("tools", "json", "toon", "slim", "compact"):
                self.assertEqual(row[key], stored[key], f"{key} drifted at {stored['tools']} tools")
            self.assertEqual(row["compact_save_pct"], stored["compact_save"])

    def test_demo_and_readme_quote_the_same_headline_numbers(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        top = ds.BENCHMARK_ROWS[-1]
        self.assertEqual(top["tools"], 255)
        for number in (top["json"], top["compact"]):
            self.assertIn(f"{number:,}", readme)


class TestNothingIsTouched(unittest.TestCase):
    """The promise that makes this scoreable anywhere: no I/O, no processes, no config."""

    def test_no_io_or_process_imports_in_the_module(self):
        with open(SOURCE, encoding="utf-8") as handle:
            source = handle.read()
        for banned in ("import subprocess", "import socket", "import urllib", "import http",
                       "import requests", "open(", "save_config", "load_config",
                       "os.environ", "Path("):
            self.assertNotIn(banned, source, f"'{banned}' would break the self-contained promise")

    def test_calling_every_tool_leaves_user_config_alone(self):
        config_path = os.path.join(os.path.expanduser("~"), ".mcptoon", "config.json")

        def snapshot():
            if not os.path.exists(config_path):
                return None
            with open(config_path, "rb") as handle:
                return handle.read()

        before = snapshot()
        for name, arguments in VALID_CALLS.items():
            call(name, arguments)
        self.assertEqual(before, snapshot(), "demo-server must not write user configuration")

    def test_serve_does_not_borrow_these_tools(self):
        """The bridge stays a proxy: mcptoon still bundles no tools into `serve`."""
        for module in ("serve.py", "manifest.py", "config.py", "discover.py", "router.py"):
            with open(os.path.join(ROOT, "src", "mcptoon", module), encoding="utf-8") as f:
                self.assertNotIn("demo_server", f.read(),
                                 f"{module} must not import the demo server")


class TestLogResilience(unittest.TestCase):
    """A diagnostic must never be the reason the server stops answering."""

    def test_log_survives_a_console_that_cannot_encode_it(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        with mock.patch.object(sys, "stderr", stream):
            ds._log("started — 11 tools, 世界")
        self.assertIn(b"started", stream.buffer.getvalue())

    def test_log_texts_are_pure_ascii(self):
        """Python can be left with an ASCII stderr in a bare container; the startup
        line in particular runs before anything is served."""
        with open(SOURCE, encoding="utf-8") as handle:
            source = handle.read()
        literals = re.findall(r'_log\(f?"([^"]*)"', source)
        self.assertGreaterEqual(len(literals), 3, "pattern should find the log call sites")
        for literal in literals:
            self.assertTrue(literal.isascii(), f"log text {literal!r} is not ASCII")


class TestRealProcess(unittest.TestCase):
    """End to end through the CLI, the way a hosted sandbox drives it."""

    def _drive(self, requests, stdin_text=None, timeout=120):
        payload = stdin_text if stdin_text is not None else \
            "".join(json.dumps(m) + "\n" for m in requests)
        proc = subprocess.run(
            [sys.executable, "-m", "mcptoon", "demo-server"],
            input=payload.encode("utf-8"), capture_output=True, timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        # stdout is the protocol stream: UTF-8 by contract, so it is decoded strictly —
        # a console that claims cp1252 must not leak into the wire. stderr carries
        # diagnostics in whatever the console encoding is, so that one is lenient.
        return (proc.returncode,
                proc.stdout.decode("utf-8"),
                proc.stderr.decode("cp1252", errors="replace"))

    def test_stdio_session_lists_eleven_tools(self):
        code, out, err = self._drive([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ])
        self.assertEqual(code, 0)
        responses = [json.loads(line) for line in out.splitlines() if line.strip()]
        listing = next(r for r in responses if r.get("id") == 2)
        self.assertEqual(len(listing["result"]["tools"]), 11)
        self.assertEqual(err.count("[mcptoon mcptoon-demo] started"), 1)

    def test_non_ascii_survives_a_cp1252_console(self):
        code, out, err = self._drive([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "echo_message", "arguments": {"message": "世界 ✓"}}}])
        self.assertEqual(code, 0)
        self.assertIn("世界", out, "the wire is UTF-8 whatever the code page claims")

    def test_garbage_line_is_answered_and_the_loop_survives(self):
        code, out, err = self._drive([], stdin_text="this is not json\n"
                                     + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping",
                                                   "params": {}}) + "\n")
        self.assertEqual(code, 0)
        self.assertIn("-32700", out)
        self.assertIn('"id": 3', out)

    def test_help_does_not_start_the_server(self):
        """Would hang on stdin and time out if --help were ignored (the 0.7.11 bug)."""
        proc = subprocess.run([sys.executable, "-m", "mcptoon", "demo-server", "--help"],
                              input="", capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("demo-server", proc.stdout)
        self.assertIn("echo_message", proc.stdout)
        self.assertIn("no network", proc.stdout.lower())

    def test_general_help_advertises_the_command(self):
        proc = subprocess.run([sys.executable, "-m", "mcptoon", "--help"],
                              input="", capture_output=True, text=True, timeout=30)
        self.assertIn("mcptoon demo-server", proc.stdout)

    def test_shell_completions_offer_the_command(self):
        from mcptoon import cli
        for block in (cli._BASH_COMPLETION, cli._ZSH_COMPLETION,
                      cli._FISH_COMPLETION, cli._PS_COMPLETION):
            self.assertIn("demo-server", block)


if __name__ == "__main__":
    unittest.main()
