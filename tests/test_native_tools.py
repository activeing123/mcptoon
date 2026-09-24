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

from mcptoon import __version__
from mcptoon import native_tools
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

    def test_every_native_tool_is_declared_read_only(self):
        for defn in native_tools.native_tools():
            ann = defn["annotations"]
            self.assertTrue(ann["readOnlyHint"], defn["name"])
            self.assertFalse(ann["destructiveHint"], defn["name"])
            self.assertFalse(ann["openWorldHint"], defn["name"])
            self.assertIn("outputSchema", defn)
            self.assertIn("title", defn)

    def test_upstream_tool_with_same_name_wins(self):
        """A user's server must never be shadowed by our own naming."""
        upstream = {"name": "mcptoon_health", "description": "Upstream server's own tool."}
        b = _bridge(index={"mcptoon_health": {
            "server": "clinic", "tool": "mcptoon_health", "full_schema": {}, "full_def": upstream}})
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
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        self.assertNotIn("instructions", res)

    def test_handshake_still_valid_without_it(self):
        from mcptoon.config import set_setting
        set_setting("footer", "off")
        res = _bridge()._handle_initialize({"protocolVersion": "2026-07-28"})
        for key in ("protocolVersion", "capabilities", "serverInfo"):
            self.assertIn(key, res)


class TestProtocolHygiene(unittest.TestCase):
    def test_bad_argument_types_do_not_raise_out_of_the_bridge(self):
        """A malformed call must come back as a tool result, not a crash."""
        b = _bridge()
        for name in native_tools.NATIVE_NAMES:
            for args in ({"server": 123}, {"include_descriptions": "yes"}, {"server": None}, {}):
                res = b._handle_call_tool({"name": name, "arguments": args})
                self.assertIn("content", res, f"{name} {args}")
                self.assertFalse(res["isError"], f"{name} {args}")

    def test_results_carry_structured_content_matching_text(self):
        b = _bridge(servers={"alpha": {"command": "x"}})
        for name in native_tools.NATIVE_NAMES:
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
        self.index = {
            "version": 1,
            "roots": [str(base)],
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
                     for k in ("MCPTOON_SKILLS_INDEX", "MCPTOON_SKILLS_USAGE")}
        os.environ["MCPTOON_SKILLS_INDEX"] = str(base / "skills-index.json")
        os.environ["MCPTOON_SKILLS_USAGE"] = str(self.usage_path)

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
        self.assertEqual(self._call("mcptoon_resolve_skills", {"task": "x"})["shortlist"], [])


if __name__ == "__main__":
    unittest.main()
