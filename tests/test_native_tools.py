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

"""The gateway's own tools: published with zero config, read-only, never shadowing
an upstream tool.

These tests exist because ``serve`` used to publish *only* upstream tools. A
gateway started in a clean environment (no config file — which is exactly what a
directory crawler or a first-time user does) therefore reported an empty
``tools/list``: nothing to evaluate, nothing to score. See native_tools.py.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcptoon import __version__
from mcptoon import native_tools
from mcptoon import skills
from mcptoon.schema_simplifier import (
    _MAX_DESC_LEN,
    _MAX_DESC_SENTENCES,
    _MAX_PARAM_DESC_LEN,
    _MAX_PARAM_DESC_SENTENCES,
    _split_sentences,
    simplify_tool_def,
)


def _bridge(servers: dict | None = None, index: dict | None = None):
    """A bridge with the given config/index already loaded (no subprocesses)."""
    from mcptoon.serve import MCPServerBridge

    b = MCPServerBridge()
    b._servers = servers if servers is not None else {}
    b._pool = None
    b._tool_index = index or {}
    b._initialized = True
    return b


class TestCatalogAlwaysNonEmpty(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._old = {
            k: os.environ.get(k)
            for k in ("MCPTOON_CONFIG_FILE", "MCPTOON_CONFIG_FILE_TOML", "MCPTOON_PLUGINS_DIR")
        }
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")
        os.environ["MCPTOON_PLUGINS_DIR"] = str(base / "plugins")

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_empty_config_still_lists_the_native_tools(self):
        """The whole point: an empty gateway is not a tool-less gateway."""
        from mcptoon.config import load_config

        self.assertEqual(load_config(), {}, "precondition: sandbox has no config")
        b = _bridge()
        b._tool_index = {}
        tools = b._handle_list_tools({})["tools"]
        self.assertEqual([t["name"] for t in tools], list(native_tools.NATIVE_NAMES))
        self.assertGreaterEqual(len(native_tools.NATIVE_NAMES), 3,
                                "the gateway must always describe itself")

    def test_native_defs_survive_our_own_simplifier(self):
        """We gate our own catalog with simplify_tool_def; it must be a no-op here."""
        for defn in native_tools.native_tools():
            self.assertEqual(simplify_tool_def(defn), defn,
                             f"{defn['name']} would be truncated by our own gateway")

    def test_descriptions_fit_the_budget_we_enforce_on_others(self):
        for defn in native_tools.native_tools():
            self.assertLessEqual(len(defn["description"]), _MAX_DESC_LEN, defn["name"])
            self.assertLessEqual(len(_split_sentences(defn["description"])),
                                 _MAX_DESC_SENTENCES, defn["name"])
            for pname, pschema in (defn.get("inputSchema", {}).get("properties") or {}).items():
                desc = pschema.get("description", "")
                self.assertLessEqual(len(desc), _MAX_PARAM_DESC_LEN, f"{defn['name']}.{pname}")
                self.assertLessEqual(len(_split_sentences(desc)), _MAX_PARAM_DESC_SENTENCES,
                                     f"{defn['name']}.{pname}")

    def test_every_native_tool_declares_honest_annotations(self):
        """Every tool but the call bridge is read-only; the bridge must say it is not.

        `mcptoon_call` is the one first-party tool that runs an upstream tool, so
        claiming it read-only would be a lie a host could act on. The rest are pure
        reads and must say so.
        """
        for defn in native_tools.native_tools():
            ann = defn["annotations"]
            self.assertIn("outputSchema", defn)
            self.assertIn("title", defn)
            if defn["name"] == "mcptoon_call":
                self.assertFalse(ann["readOnlyHint"], defn["name"])
                self.assertTrue(ann["destructiveHint"], defn["name"])
                self.assertTrue(ann["openWorldHint"], defn["name"])
            else:
                self.assertTrue(ann["readOnlyHint"], defn["name"])
                self.assertFalse(ann["destructiveHint"], defn["name"])
                self.assertFalse(ann["openWorldHint"], defn["name"])

    def test_upstream_tool_with_same_name_wins(self):
        """A user's server must never be shadowed by our own naming.

        Pinned under `exposure=full`, which is where both sets are listed at once
        and a collision can actually be observed. Under the default
        `exposure=compact` the upstream tools are withheld, so there is nothing to
        shadow — that case is pinned by TestToolExposure.

        Patched rather than written through `set_setting`: this class does not
        isolate `MCPTOON_SETTINGS_FILE`, so a real write here would land in the
        developer's own `~/.mcptoon/settings.json`.
        """
        upstream = {"name": "mcptoon_health", "description": "Upstream server's own tool."}
        b = _bridge(index={"mcptoon_health": {
            "server": "clinic", "tool": "mcptoon_health", "full_schema": {}, "full_def": upstream}})
        with patch("mcptoon.serve.config.compact_exposure", return_value=False):
            tools = b._handle_list_tools({})["tools"]
        named = [t for t in tools if t["name"] == "mcptoon_health"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["description"], upstream["description"])
        # every native name is present exactly once, upstream's definition winning
        self.assertEqual(sorted(t["name"] for t in tools),
                         sorted(native_tools.NATIVE_NAMES))


class TestManifestTool(unittest.TestCase):
    def setUp(self):
        self.index = {
            "alpha_find": {"server": "alpha", "tool": "find", "full_schema": {},
                           "full_def": {"name": "find",
                                        "description": "Find files fast. Second sentence."}},
            "alpha_list": {"server": "alpha", "tool": "list", "full_schema": {},
                           "full_def": {"name": "list", "description": "List a directory."}},
            "beta_run": {"server": "beta", "tool": "run", "full_schema": {},
                         "full_def": {"name": "run", "description": "Run a command. Careful."}},
        }

    def _call(self, args: dict, servers=None, index=None):
        b = _bridge(servers={"alpha": {"command": "x"}, "beta": {"url": "http://y"}},
                    index=self.index if index is None else index)
        return b._handle_call_tool({"name": "mcptoon_manifest", "arguments": args})

    def _payload(self, args: dict, **kw):
        res = self._call(args, **kw)
        self.assertFalse(res["isError"])
        return res["structuredContent"]

    def test_groups_by_server_and_counts(self):
        p = self._payload({})
        self.assertEqual(p["totalServers"], 2)
        self.assertEqual(p["totalTools"], 3)
        self.assertEqual([s["name"] for s in p["servers"]], ["alpha", "beta"])
        self.assertEqual([t["name"] for t in p["servers"][0]["tools"]], ["find", "list"])

    def test_names_only_by_default(self):
        p = self._payload({})
        for s in p["servers"]:
            for t in s["tools"]:
                self.assertNotIn("description", t)

    def test_include_descriptions_adds_first_sentence_only(self):
        p = self._payload({"include_descriptions": True})
        descs = {t["name"]: t["description"] for t in p["servers"][0]["tools"]}
        self.assertEqual(descs["find"], "Find files fast.")
        self.assertEqual(descs["list"], "List a directory.")

    def test_server_filter(self):
        p = self._payload({"server": "beta"})
        self.assertEqual(p["totalServers"], 1)
        self.assertEqual(p["servers"][0]["tools"][0]["name"], "run")

    def test_unknown_filter_returns_empty_with_notice(self):
        p = self._payload({"server": "nope"})
        self.assertEqual(p["servers"], [])
        self.assertIn("notice", p)

    def test_empty_index_explains_how_to_add_a_server(self):
        p = self._payload({}, index={})
        self.assertEqual(p["totalTools"], 0)
        self.assertIn("mcptoon add", p["notice"])


class TestInspectTool(unittest.TestCase):
    """mcptoon_inspect: the arguments half of the compact-exposure contract.

    `mcptoon_manifest` gives names; this gives the parameters a withheld tool needs.
    It is read-only and must resolve both the namespaced form and a bare tool name.
    """

    def setUp(self):
        self.index = {
            "alpha_find": {"server": "alpha", "tool": "find",
                           "full_schema": {"type": "object",
                                           "properties": {"q": {"type": "string"}},
                                           "required": ["q"]},
                           "full_def": {"name": "find",
                                        "description": "Find files fast. Second sentence.",
                                        "inputSchema": {"type": "object",
                                                        "properties": {"q": {"type": "string"}}}}},
            "beta_find": {"server": "beta", "tool": "find", "full_schema": {},
                          "full_def": {"name": "find", "description": "Beta's own find."}},
        }

    def _call(self, args):
        b = _bridge(servers={"alpha": {"command": "x"}, "beta": {"url": "http://y"}},
                    index=self.index)
        return b._handle_call_tool({"name": "mcptoon_inspect", "arguments": args})

    def _payload(self, args):
        res = self._call(args)
        self.assertFalse(res["isError"])
        return res["structuredContent"]

    def test_returns_the_full_input_schema(self):
        p = self._payload({"tool": "alpha_find"})
        self.assertEqual(p["server"], "alpha")
        self.assertEqual(p["inputSchema"]["required"], ["q"])
        self.assertEqual(p["description"], "Find files fast.")  # first sentence only

    def test_bare_tool_name_resolves_when_unique(self):
        index = {"solo_greet": {"server": "solo", "tool": "greet", "full_schema": {},
                                "full_def": {"name": "greet", "description": "Hi."}}}
        b = _bridge(index=index)
        p = b._handle_call_tool({"name": "mcptoon_inspect",
                                 "arguments": {"tool": "greet"}})["structuredContent"]
        self.assertEqual(p["tool"], "solo_greet")
        self.assertEqual(p["server"], "solo")

    def test_ambiguous_bare_name_is_a_graceful_notice(self):
        p = self._payload({"tool": "find"})  # owned by alpha and beta
        self.assertIn("notice", p)
        self.assertEqual(p["inputSchema"], {})

    def test_server_disambiguates_a_bare_name(self):
        p = self._payload({"tool": "find", "server": "beta"})
        self.assertEqual(p["tool"], "beta_find")
        self.assertEqual(p["server"], "beta")

    def test_missing_tool_argument_asks_for_one(self):
        p = self._payload({})
        self.assertIn("notice", p)
        self.assertEqual(p["inputSchema"], {})


class TestCallBridge(unittest.TestCase):
    """mcptoon_call: the gateway's escape hatch for compact exposure.

    Its whole job is to route to an upstream tool by namespaced name and reuse the
    bridge's validation, danger checks and result shaping — not a parallel path
    that can drift. These pin that reuse, not just that a dict comes back.
    """

    def setUp(self):
        self.index = {
            "alpha_find": {"server": "alpha", "tool": "find",
                           "full_schema": {"type": "object",
                                           "properties": {"q": {"type": "string"}},
                                           "required": ["q"]},
                           "full_def": {"name": "find", "description": "Find files fast."}},
            "alpha_delete": {"server": "alpha", "tool": "delete", "full_schema": {},
                             "full_def": {"name": "delete", "description": "Delete things."}},
        }

    def _bridge_with_pool(self):
        b = _bridge(servers={"alpha": {"command": "x"}}, index=self.index)
        calls = []

        class FakePool:
            def call(self, server, tool, arguments):
                calls.append((server, tool, arguments))
                return {"ran": [server, tool]}

        b._pool = FakePool()
        return b, calls

    def test_routes_to_the_upstream_tool(self):
        b, calls = self._bridge_with_pool()
        res = b._handle_call_tool({"name": "mcptoon_call",
                                   "arguments": {"name": "alpha_find",
                                                 "arguments": {"q": "x"}}})
        self.assertFalse(res["isError"])
        self.assertEqual(calls, [("alpha", "find", {"q": "x"})])

    def test_validation_still_applies(self):
        """The bridge validates against the real schema — the escape hatch is not a bypass."""
        b, calls = self._bridge_with_pool()
        res = b._handle_call_tool({"name": "mcptoon_call",
                                   "arguments": {"name": "alpha_find", "arguments": {}}})
        self.assertTrue(res["isError"])
        self.assertIn("validation failed", res["content"][0]["text"])
        self.assertEqual(calls, [], "an invalid call must never reach the upstream")

    def test_dangerous_tools_are_still_blocked(self):
        b, calls = self._bridge_with_pool()
        res = b._handle_call_tool({"name": "mcptoon_call",
                                   "arguments": {"name": "alpha_delete", "arguments": {}}})
        self.assertTrue(res["isError"])
        self.assertIn("Blocked", res["content"][0]["text"])
        self.assertEqual(calls, [])


class TestServersAndHealth(unittest.TestCase):
    def _payload(self, name: str, args: dict, servers: dict, index: dict | None = None):
        b = _bridge(servers=servers, index=index or {})
        res = b._handle_call_tool({"name": name, "arguments": args})
        self.assertFalse(res["isError"])
        return res["structuredContent"]

    def test_servers_reports_transport_and_load_state(self):
        index = {"alpha_x": {"server": "alpha", "tool": "x", "full_schema": {},
                             "full_def": {"name": "x", "description": "d"}}}
        p = self._payload("mcptoon_servers", {},
                          {"alpha": {"command": "a", "args": []},
                           "beta": {"url": "http://h/sse"},
                           "ghost": {"command": "g"}},
                          index)
        rows = {s["name"]: s for s in p["servers"]}
        self.assertEqual(p["configured"], 3)
        self.assertEqual(rows["alpha"]["transport"], "stdio")
        self.assertEqual(rows["beta"]["transport"], "http")
        self.assertEqual(rows["alpha"]["toolCount"], 1)
        self.assertTrue(rows["alpha"]["loaded"])
        self.assertFalse(rows["ghost"]["loaded"])

    def test_servers_filter_resolves_single(self):
        p = self._payload("mcptoon_servers", {"server": "beta"}, {"beta": {"url": "u"}})
        self.assertEqual([s["name"] for s in p["servers"]], ["beta"])

    def test_health_status_is_ok_when_nothing_configured(self):
        p = self._payload("mcptoon_health", {}, {})
        self.assertEqual(p["status"], "ok")
        self.assertEqual(p["version"], __version__)
        self.assertEqual(p["serversConfigured"], 0)
        self.assertEqual(sorted(p["nativeTools"]), sorted(native_tools.NATIVE_NAMES))

    def test_health_status_is_error_when_every_server_published_nothing(self):
        p = self._payload("mcptoon_health", {}, {"dead": {"command": "x"}})
        self.assertEqual(p["status"], "error")
        self.assertEqual(p["failedServers"], 1)

    def test_health_status_is_degraded_for_partial_failure(self):
        index = {"live_x": {"server": "live", "tool": "x", "full_schema": {},
                            "full_def": {"name": "x", "description": "d"}}}
        p = self._payload("mcptoon_health", {}, {"live": {"command": "a"}, "dead": {"command": "b"}},
                          index)
        self.assertEqual(p["status"], "degraded")
        self.assertEqual(p["failedServers"], 1)
        self.assertEqual(p["toolsIndexed"], 1)

    def test_health_before_init_is_starting(self):
        """call_native used directly (the HTTP /health path) can see a cold bridge."""
        res = native_tools.call_native("mcptoon_health", {}, {
            "servers": {}, "tool_index": {}, "output_format": "auto",
            "initialized": False, "uptime": 0.0})
        self.assertEqual(res["structuredContent"]["status"], "starting")


class TestUsageTool(unittest.TestCase):
    """`mcptoon_usage` feeds the disclosure footer. Its numbers must be real."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._old = {k: os.environ.get(k) for k in
                     ("MCPTOON_SETTINGS_FILE", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML")}
        os.environ["MCPTOON_SETTINGS_FILE"] = str(base / "settings.json")
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _index(self, n=3):
        # Verbose on purpose: over the 360-char / 3-sentence budget the gateway
        # enforces, so simplify_tool_def actually trims and a saving exists.
        return {
            f"srv_tool{i}": {
                "server": "srv",
                "tool": f"tool{i}",
                "full_def": {
                    "name": f"tool{i}",
                    "description": (
                        "First sentence describing the tool in more detail than anyone "
                        "needs. Second sentence adding still more context that will be "
                        "trimmed. Third sentence that also goes on. Fourth sentence kept "
                        "only to push this well past the description budget so the "
                        "compressor has something real to remove. "
                    ) * 4,
                    "inputSchema": {"type": "object", "properties": {
                        "a": {"type": "string", "description": "x " * 200}}},
                },
            }
            for i in range(n)
        }

    def test_reports_compression_and_a_positive_saving(self):
        b = _bridge(index=self._index())
        payload = b._handle_call_tool({"name": "mcptoon_usage", "arguments": {}})["structuredContent"]
        self.assertEqual(payload["toolsCompressed"], 3)
        self.assertGreater(payload["tokensSaved"], 0,
                           "compressing verbose schemas must show a saving")
        self.assertGreater(payload["savingsPct"], 0)

    def test_footer_state_is_reflected(self):
        b = _bridge(index=self._index())
        self.assertTrue(b._handle_call_tool(
            {"name": "mcptoon_usage", "arguments": {}})["structuredContent"]["footerEnabled"])
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        self.assertFalse(b._handle_call_tool(
            {"name": "mcptoon_usage", "arguments": {}})["structuredContent"]["footerEnabled"])

    def test_empty_catalog_reports_zero_not_an_error(self):
        payload = native_tools.call_native("mcptoon_usage", {}, {
            "servers": {}, "tool_index": {}, "output_format": "auto",
            "initialized": True, "uptime": 0.0})["structuredContent"]
        self.assertEqual(payload["toolsCompressed"], 0)
        self.assertEqual(payload["tokensSaved"], 0)
        self.assertEqual(payload["savingsPct"], 0.0)


class TestFooterDisclosure(unittest.TestCase):
    """The `instructions` field is the gateway's one line of voice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._old = {k: os.environ.get(k) for k in
                     ("MCPTOON_SETTINGS_FILE", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML")}
        os.environ["MCPTOON_SETTINGS_FILE"] = str(base / "settings.json")
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_on_by_default(self):
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertIn("instructions", res)
        self.assertIn("mcptoon footer-facts", res["instructions"])

    def test_instructions_ask_for_the_line_when_it_has_changed(self):
        """The savings line is the whole point of the channel: it makes the tool's
        effect visible inside the conversation. Two softer phrasings failed before
        this one — "you may close" produced turns that silently dropped it, and
        "every turn that used tools" was worse: the gateway is injected into
        clients as an MCP server, and in a client that never routes a tool call
        through it, that condition is never true, so the line never appeared at
        all. The number describes the compressed catalog, not the turn, so the
        directive must not gate it on tool use.

        2026-09-24: the gate is now "the numbers changed since the line you last
        showed" — a property of the machine, not the turn, so it still cannot
        silence a client that never routes a call (the catalog figures move on
        their own). What it removes is the verbatim repeat that made the line read
        as spam."""
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res["instructions"]
        self.assertIn("only when the numbers have changed", text)
        self.assertNotIn("you may close", text, "a permissive phrasing is the old bug")
        self.assertNotIn("that used tools", text,
                         "gating the line on tool use silences it in clients that "
                         "never route a call through the gateway")

    def test_instructions_name_a_command_that_cannot_stall_the_turn(self):
        """The directive must name a command that is safe to run every turn.

        It used to say "read mcptoon_usage", which is not a command the model can
        run; then the natural substitute was `mcptoon status`, which refreshes a
        stale schema cache by spawning every configured server (~23s cold here).
        A footer that occasionally costs 23 seconds is worse than no footer, so
        the instructions point at `footer-facts` and say why not `status`.
        """
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res["instructions"]
        self.assertIn("mcptoon footer-facts", text)
        self.assertNotIn("read mcptoon_usage", text,
                         "the old text named a thing that is not a command")
        self.assertIn("do not substitute", text,
                      "the instructions must steer away from the slow command")
        self.assertIn("mcptoon status", text)

    def test_instructions_disclose_how_to_switch_the_line_off(self):
        """A line the user cannot silence is the reason it reads as spam. The off
        switch has to be stated in the same breath as the request for the line."""
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertIn("mcptoon config set footer off", res["instructions"])

    def test_instructions_point_at_the_skill_for_the_breakdown(self):
        """The one-line figure invites "saved compared to what?". The answer must be
        reachable without guessing, so the instructions name where it lives."""
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertIn("mcptoon` skill", res["instructions"])
        self.assertIn("mcptoon bench", res["instructions"])

    def test_instructions_never_license_inventing_numbers(self):
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertIn("never invent figures", res["instructions"])

    def test_instructions_point_at_the_skill_tool(self):
        """The model cannot discover *when* to reach for a skill from a tool list.

        `mcptoon_resolve_skills` appears in `tools/list` like any other tool, but a
        list of tools says nothing about the catalog behind them — an agent that
        never sees a skill list in its prompt has no reason to call a resolver. The
        handshake is the one channel that reaches the model with no action of its
        own, so the pointer lives here. It names the *tool*, not the shell command,
        because the reader always has this gateway mounted and may have no shell.
        """
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res["instructions"]
        self.assertIn("mcptoon_resolve_skills", text)
        self.assertIn("never load the whole catalog", text,
                      "the pointer must not invite a full-catalog dump")
        self.assertNotIn("mcptoon skills resolve", text,
                         "name the mounted tool, not the CLI the host may not have")

    def test_instructions_stay_within_their_context_budget(self):
        """This text rides in context on every turn — the cost mcptoon exists to cut.

        The two duties (name the skill tool, report savings honestly) both need
        room, so the budget is not tiny; it is a ceiling, not a target. Pinned so a
        later edit cannot grow the per-turn cost of every session by accident: a
        saving tool whose own overhead creeps is the complaint this repo was built
        to answer. 314 tokens on the cl100k_base caliber when this was written.
        """
        from mcptoon import serve

        self.assertLessEqual(len(serve._INSTRUCTIONS), 1400,
                             "instructions grew past the budget it rides in")

    def test_instructions_pin_the_mark_and_the_note_line(self):
        """ "Quote it verbatim" was not enough, so the directive now names the parts.

        Measured failure (2026-09-22): a model told to "report the savings line"
        wrote one from memory and the `🎉` was gone — the single element the
        feature exists to make noticeable, and the one a paraphrase drops first.
        `footer.MARK` is asserted here, so changing the mark without updating the
        directive (or dropping it from the directive) fails the build instead of
        silently degrading what the user sees.
        """
        from mcptoon import footer as footer_mod

        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res["instructions"]
        self.assertIn(footer_mod.MARK, text, "the directive must name the mark itself")
        self.assertIn("`note:`", text, "the caveat line is part of the pasteable block")
        self.assertIn("verbatim", text)
        self.assertIn("Do not retype it from memory", text,
                      "retyping is exactly how the mark went missing")
        self.assertIn("do not translate", text,
                      "translating re-words the line and drops the prefix")

    def test_off_removes_it_entirely(self):
        """`footer off` must drop the savings-line duty — and only that duty.

        The handshake now carries up to two independent directives. Where the
        upstream tools went is not the footer's business: under the default
        `exposure=compact` it is the only thing telling the model that the user's
        MCP servers still exist, so removing it with the footer would hide the
        tools twice. Asserted on the footer's own text, not on the key's absence.
        """
        from mcptoon import footer as footer_mod
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res.get("instructions", "")
        self.assertNotIn(footer_mod.MARK, text)
        self.assertNotIn("verbatim", text)
        self.assertIn("mcptoon_manifest", text,
                      "withholding the tool list must still be explained")

    def test_off_removes_the_key_when_nothing_else_needs_saying(self):
        """With `exposure=full` and the footer off, no directive remains at all."""
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        set_setting("exposure", "full")
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertNotIn("instructions", res)

    def test_handshake_still_valid_without_it(self):
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        for key in ("protocolVersion", "capabilities", "serverInfo"):
            self.assertIn(key, res)


class TestToolExposure(unittest.TestCase):
    """`exposure` decides how much of the tool catalog `tools/list` enumerates.

    `compact` is the default because the whole point of the gateway is to keep
    tool definitions out of the per-turn context. The risk that buys is that a
    model reads an empty-looking tool list and tells the user their MCP servers are
    gone — so the assertion that matters most here is not "the list is shorter" but
    "the withheld tool is still callable, and something said so".
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._old = {k: os.environ.get(k) for k in
                     ("MCPTOON_SETTINGS_FILE", "MCPTOON_CONFIG_FILE",
                      "MCPTOON_CONFIG_FILE_TOML")}
        os.environ["MCPTOON_SETTINGS_FILE"] = str(base / "settings.json")
        os.environ["MCPTOON_CONFIG_FILE"] = str(base / "cfg.json")
        os.environ["MCPTOON_CONFIG_FILE_TOML"] = str(base / "cfg.toml")
        self.index = {
            "alpha_find": {"server": "alpha", "tool": "find", "full_schema": {},
                           "full_def": {"name": "find", "description": "Find files fast."}},
        }

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_compact_is_the_default(self):
        from mcptoon.config import exposure_mode
        self.assertEqual(exposure_mode(), "compact")

    def test_compact_exposure_withholds_the_upstream_list(self):
        """The default lists mcptoon's own tools and nothing else."""
        tools = _bridge(index=self.index)._handle_list_tools({})["tools"]
        names = sorted(t["name"] for t in tools)
        self.assertEqual(names, sorted(native_tools.NATIVE_NAMES))
        self.assertNotIn("alpha_find", names)

    def test_full_exposure_lists_the_upstream_tools_again(self):
        """The fallback restores the pre-2026-09-25 listing exactly."""
        from mcptoon.config import set_setting
        set_setting("exposure", "full")
        tools = _bridge(index=self.index)._handle_list_tools({})["tools"]
        names = sorted(t["name"] for t in tools)
        self.assertIn("alpha_find", names)
        for native in native_tools.NATIVE_NAMES:
            self.assertIn(native, names)

    def test_a_withheld_tool_is_still_callable_by_its_namespaced_name(self):
        """Withholding the listing must never withhold the capability.

        This is what makes `compact` safe to ship as the default: the tool list is
        a discovery surface, not the call path. The namespaced name routes whether
        or not it was enumerated — pinned here by actually calling it, because a
        green test that only inspected `_tool_index` is how `mcptoon_call` came to
        be documented for months without existing.
        """
        b = _bridge(servers={"alpha": {"command": "x"}}, index=self.index)
        listed = b._handle_list_tools({})["tools"]
        self.assertNotIn("alpha_find", [t["name"] for t in listed])

        calls = []

        class FakePool:
            def call(self, server, tool, arguments):
                calls.append((server, tool, arguments))
                return {"ok": True}

        b._pool = FakePool()
        res = b._handle_call_tool({"name": "alpha_find", "arguments": {}})
        self.assertFalse(res["isError"])
        self.assertEqual(calls, [("alpha", "find", {})])

    def test_the_advertised_meta_tools_actually_exist_and_work(self):
        """The compact handshake names `mcptoon_inspect` and `mcptoon_call`; both
        must exist, and both must be usable in the mode that advertises them."""
        b = _bridge(servers={"alpha": {"command": "x"}}, index=self.index)
        listed = {t["name"] for t in b._handle_list_tools({})["tools"]}
        self.assertIn("mcptoon_inspect", listed)
        self.assertIn("mcptoon_call", listed)

        ins = b._handle_call_tool({"name": "mcptoon_inspect", "arguments": {"tool": "alpha_find"}})
        self.assertFalse(ins["isError"])
        self.assertEqual(ins["structuredContent"]["tool"], "alpha_find")
        self.assertEqual(ins["structuredContent"]["server"], "alpha")

        calls = []

        class FakePool:
            def call(self, server, tool, arguments):
                calls.append((server, tool, arguments))
                return {"ran": True}

        b._pool = FakePool()
        out = b._handle_call_tool({"name": "mcptoon_call",
                                   "arguments": {"name": "alpha_find", "arguments": {}}})
        self.assertFalse(out["isError"])
        self.assertEqual(calls, [("alpha", "find", {})])

    def test_call_bridge_refuses_without_a_target_and_never_recurses(self):
        b = _bridge(index=self.index)
        no_target = b._handle_call_tool({"name": "mcptoon_call", "arguments": {}})
        self.assertTrue(no_target["isError"])
        self.assertIn("name", no_target["content"][0]["text"])
        self_loop = b._handle_call_tool({"name": "mcptoon_call",
                                         "arguments": {"name": "mcptoon_call"}})
        self.assertTrue(self_loop["isError"])
        self.assertIn("itself", self_loop["content"][0]["text"])

    def test_inspect_unknown_tool_is_a_graceful_notice(self):
        b = _bridge(index=self.index)
        res = b._handle_call_tool({"name": "mcptoon_inspect", "arguments": {"tool": "ghost"}})
        self.assertFalse(res["isError"])
        self.assertIn("notice", res["structuredContent"])
        self.assertEqual(res["structuredContent"]["inputSchema"], {})

    def test_compact_directive_says_where_the_tools_went(self):
        """The handshake must name the manifest, or the withheld tools read as gone."""
        res = _bridge(index=self.index)._handle_initialize({"protocolVersion": "2026-07-28"})
        text = res["instructions"]
        self.assertIn("mcptoon_manifest", text)
        self.assertIn("mcptoon_call", text)
        self.assertIn("withheld", text)

    def test_full_exposure_omits_the_directive(self):
        """Nothing is withheld, so there is nothing to explain — and no tokens owed."""
        from mcptoon.config import set_setting
        set_setting("exposure", "full")
        res = _bridge(index=self.index)._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertNotIn("withheld", res.get("instructions", ""))

    def test_compact_instructions_stay_within_their_budget(self):
        """Both directives ride in context every turn, so the pair has a ceiling too."""
        from mcptoon import serve
        total = len(serve._INSTRUCTIONS) + len(serve._COMPACT_TOOLS_DIRECTIVE)
        self.assertLessEqual(total, 1900,
                             "the compact handshake grew past its budget")

    def test_an_unknown_exposure_setting_falls_back_to_compact(self):
        """A hand-edited settings file must not be able to break the gateway."""
        from mcptoon.config import exposure_mode
        from mcptoon.config import set_setting
        settings = Path(os.environ["MCPTOON_SETTINGS_FILE"])
        settings.write_text(json.dumps({"exposure": "COMPACT-ish nonsense"}),
                            encoding="utf-8")
        self.assertEqual(exposure_mode(), "compact")
        # and the setter itself refuses a value nothing would honour
        with self.assertRaises(ValueError):
            set_setting("exposure", "loose")


class TestProtocolHygiene(unittest.TestCase):
    def test_bad_argument_types_do_not_raise_out_of_the_bridge(self):
        """A malformed call must come back as a tool result, not a crash."""
        b = _bridge()
        for name in native_tools.NATIVE_NAMES:
            if name == "mcptoon_call":
                # The bridge delegates it; a missing/garbage target must still be a
                # tool result, never an exception.
                for args in ({}, {"name": 123}, {"name": "x", "arguments": 5},
                             {"name": "mcptoon_nope"}):
                    res = b._handle_call_tool({"name": name, "arguments": args})
                    self.assertIn("content", res, f"{name} {args}")
                continue
            for args in ({"server": 123}, {"include_descriptions": "yes"}, {"server": None}, {}):
                res = b._handle_call_tool({"name": name, "arguments": args})
                self.assertIn("content", res, f"{name} {args}")
                self.assertFalse(res["isError"], f"{name} {args}")

    def test_results_carry_structured_content_matching_text(self):
        b = _bridge(servers={"alpha": {"command": "x"}})
        for name in native_tools.NATIVE_NAMES:
            if name == "mcptoon_call":
                continue  # it forwards an upstream result, not a first-party payload
            res = b._handle_call_tool({"name": name, "arguments": {}})
            self.assertEqual(json.loads(res["content"][0]["text"]), res["structuredContent"], name)

    def test_unknown_tool_still_errors_normally(self):
        b = _bridge()
        res = b._handle_call_tool({"name": "mcptoon_nonexistent", "arguments": {}})
        self.assertTrue(res["isError"])
        self.assertIn("Unknown tool", res["content"][0]["text"])

    def test_is_native_only_matches_ours(self):
        self.assertTrue(native_tools.is_native("mcptoon_health"))
        self.assertFalse(native_tools.is_native("health"))
        self.assertFalse(native_tools.is_native("alpha_health"))


class TestSkillsTools(unittest.TestCase):
    """mcptoon_skills / mcptoon_resolve_skills — the catalog reachable over MCP.

    These exist so an agent connected to the gateway can resolve a skill without
    a skill list in its prompt and without shelling out. The index and usage file
    are sandboxed through the same env overrides the CLI honours.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.usage_path = base / "skills-usage.json"
        # A fixture index describes skills that are not on disk (there are no
        # SKILL.md files here), so it must carry the signature of an empty
        # catalog over its roots — otherwise `ensure_index` sees it as stale and
        # rebuilds over it, wiping the fixture out from under the test.
        (base / "empty-roots").mkdir()
        self.index = {
            "version": 1,
            "roots": [str(base / "empty-roots")],
            "signature": skills.catalog_signature([base / "empty-roots"]),
            "skills": [
                {"slug": "yuyin", "name": "yuyin",
                 "desc": "人声分离：把语音与背景音乐分开。触发词：/yuyin、人声分离",
                 "triggers": ["人声分离", "vocal"]},
                {"slug": "comfyui", "name": "comfyui",
                 "desc": "ComfyUI 出图出视频。触发词：/comfyui、出图",
                 "triggers": ["出图", "出视频"]},
                {"slug": "sep-alias", "name": "sep-alias", "alias_of": "yuyin",
                 "desc": "别名卡", "triggers": []},
            ],
        }
        (base / "skills-index.json").write_text(
            json.dumps(self.index, ensure_ascii=False), encoding="utf-8")
        self._old = {k: os.environ.get(k)
                     for k in ("MCPTOON_SKILLS_INDEX", "MCPTOON_SKILLS_USAGE",
                               "MCPTOON_SKILLS_ROOTS")}
        os.environ["MCPTOON_SKILLS_INDEX"] = str(base / "skills-index.json")
        os.environ["MCPTOON_SKILLS_USAGE"] = str(self.usage_path)
        # Point roots at an empty dir so a test that deletes the index does not
        # silently rebuild it from the *real* catalog on this machine.
        os.environ["MCPTOON_SKILLS_ROOTS"] = str(base / "empty-roots")

    def tearDown(self):
        self.tmp.cleanup()
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _call(self, name: str, arguments: dict) -> dict:
        res = _bridge()._handle_call_tool({"name": name, "arguments": arguments})
        self.assertFalse(res["isError"], name)
        return res["structuredContent"]

    def test_skills_lists_canonical_rows_sorted(self):
        payload = self._call("mcptoon_skills", {})
        self.assertEqual([r["slug"] for r in payload["skills"]], ["comfyui", "yuyin"])
        self.assertEqual(payload["totalSkills"], 2)
        # The trigger tail is stripped, matching `mcptoon skills list`.
        self.assertNotIn("触发词", payload["skills"][1]["desc"])

    def test_skills_hides_alias_cards_unless_asked(self):
        self.assertEqual([r["slug"] for r in self._call("mcptoon_skills", {})["skills"]],
                         ["comfyui", "yuyin"])
        with_alias = self._call("mcptoon_skills", {"include_aliases": True})
        self.assertIn("sep-alias", [r["slug"] for r in with_alias["skills"]])

    def test_skills_matches_the_cli_projection(self):
        """One projection, two surfaces: the tool must not rank or shape its own."""
        from mcptoon import skills as skills_mod

        self.assertEqual(self._call("mcptoon_skills", {})["skills"],
                         skills_mod.catalog_rows(self.index))

    def test_resolve_skills_ranks_the_task(self):
        payload = self._call("mcptoon_resolve_skills", {"task": "人声分离"})
        self.assertEqual(payload["shortlist"][0]["slug"], "yuyin")
        self.assertIn("score", payload["shortlist"][0])

    def test_resolve_skills_matches_the_cli_ranking(self):
        from mcptoon import skills as skills_mod

        self.assertEqual(self._call("mcptoon_resolve_skills", {"task": "人声分离"})["shortlist"],
                         skills_mod.resolve_shortlist("人声分离", 5, index=self.index))

    def test_resolve_skills_records_usage_like_the_cli(self):
        self._call("mcptoon_resolve_skills", {"task": "人声分离"})
        used = json.loads(self.usage_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(used.get("yuyin", {}).get("count", 0), 1)

    def test_resolve_skills_empty_task_is_graceful(self):
        payload = self._call("mcptoon_resolve_skills", {})
        self.assertEqual(payload["shortlist"], [])
        self.assertIn("notice", payload)

    def test_resolve_skills_bad_k_falls_back_not_raises(self):
        for bad in ("abc", 0, -3, None, True):
            payload = self._call("mcptoon_resolve_skills", {"task": "出图", "k": bad})
            self.assertEqual(payload["k"], 5, bad)
        self.assertEqual(
            self._call("mcptoon_resolve_skills", {"task": "出图", "k": 2})["k"], 2)

    def test_missing_index_is_a_result_not_a_crash(self):
        os.environ["MCPTOON_SKILLS_INDEX"] = str(Path(self.tmp.name) / "nope.json")
        payload = self._call("mcptoon_skills", {})
        self.assertEqual(payload["skills"], [])
        self.assertIn("notice", payload)

    def test_a_fresh_install_answers_instead_of_erroring(self):
        """The tool must build the index on first call, not tell the user to.

        A gateway that returns "run `mcptoon skills index` first" is a gateway
        that looks broken on the one call a new user is most likely to make.
        """
        os.environ["MCPTOON_SKILLS_INDEX"] = str(Path(self.tmp.name) / "nope.json")
        root = Path(self.tmp.name) / "root"
        (root / "fresh").mkdir(parents=True)
        (root / "fresh" / "SKILL.md").write_text(
            "---\nname: fresh\ndescription: 全新技能。触发词：fresh\n---\n\nbody\n",
            encoding="utf-8")
        os.environ["MCPTOON_SKILLS_ROOTS"] = str(root)
        try:
            payload = self._call("mcptoon_skills", {})
            self.assertEqual([r["slug"] for r in payload["skills"]], ["fresh"])
            self.assertNotIn("notice", payload)
            self.assertTrue((Path(self.tmp.name) / "nope.json").is_file(),
                            "the first call must write an index")
        finally:
            os.environ.pop("MCPTOON_SKILLS_ROOTS", None)
        self.assertEqual(self._call("mcptoon_resolve_skills", {"task": "x"})["shortlist"], [])


if __name__ == "__main__":
    unittest.main()
