"""Tests for `mcptoon skills` — skill-catalog indexing and compression-safe routing.

The design claim under test: a compressed catalog must not cost routing accuracy.
We keep the full catalog on disk and retrieve from it, instead of trimming what the
model sees. So the load-bearing test is `test_uninformative_name_is_retrievable_by_trigger`
— a skill whose slug says nothing must still be found from a natural request.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import cli, skills


def write_skill(root: Path, slug: str, desc: str, *, layout: str = "nested",
                name: str | None = None, body: str = "body text",
                tools: list[str] | None = None, tools_block: bool = False) -> Path:
    """Create one SKILL.md fixture. layout='nested' → root/skills/<slug>."""
    base = root / "skills" if layout == "nested" else root
    d = base / slug
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    front = f"---\nname: {name or slug}\ndescription: {desc}\n"
    if tools:
        if tools_block:
            front += "tools:\n" + "".join(f"  - {t}\n" for t in tools)
        else:
            front += f"tools: [{', '.join(tools)}]\n"
    md.write_text(f"{front}---\n\n{body}\n", encoding="utf-8")
    return md


def run_cli(argv, env):
    """Run the CLI in-process and return its stdout."""
    buf = StringIO()
    with patch.dict(os.environ, env), patch.object(sys, "argv", argv), redirect_stdout(buf):
        cli.main()
    return buf.getvalue()


def fixture(tmp: str, layout: str = "nested") -> Path:
    """A small catalog that mirrors the real-world traps."""
    root = Path(tmp)
    write_skill(root, "houtai", "InsForge 后端入口。触发词：后台、建个表、带登录的网页、手机能查", layout=layout)
    write_skill(root, "kao", "记忆体检 (/kao) — 给双脑记忆出考卷打分。触发词：考记忆、记忆体检、记忆掉分", layout=layout)
    write_skill(root, "tu-kami", "Typeset docs. Triggers: 做 PDF, 排版, 简历, landing page", layout=layout)
    write_skill(root, "ffmpeg-skill", "ffmpeg 剪辑工具箱。触发词：剪视频、剪辑、竖屏 9:16、烧字幕", layout=layout)
    write_skill(root, "archify", "别名转发：/archify → /tu-archify（架构图）。触发词：/archify, archify", layout=layout)
    write_skill(root, "tu-archify", "架构图引擎，生成可交互 HTML 架构图。触发词：架构图、链路图、画个系统架构", layout=layout)
    return root


class ScanTests(unittest.TestCase):
    def test_scans_both_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fixture(tmp, layout="nested")
            idx = skills.scan_roots([root])
            self.assertEqual(len(idx["skills"]), 6)
            self.assertIn("houtai", {s["slug"] for s in idx["skills"]})

        with tempfile.TemporaryDirectory() as tmp:
            root = fixture(tmp, layout="flat")
            idx = skills.scan_roots([root])
            self.assertEqual(len(idx["skills"]), 6)

    def test_triggers_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = skills.scan_roots([fixture(tmp)])
            by = {s["slug"]: s for s in idx["skills"]}
            self.assertIn("后台", by["houtai"]["triggers"])
            self.assertIn("建个表", by["houtai"]["triggers"])
            self.assertIn("简历", by["tu-kami"]["triggers"])
            self.assertNotIn("/", "".join(by["houtai"]["triggers"]))

    def test_alias_target_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = skills.scan_roots([fixture(tmp)])
            by = {s["slug"]: s for s in idx["skills"]}
            self.assertEqual(by["archify"]["alias_of"], "tu-archify")
            self.assertEqual(by["houtai"]["alias_of"], "")

    def test_missing_root_is_warned_not_fatal(self):
        idx = skills.scan_roots([Path(tempfile.gettempdir()) / "definitely-not-here-xyz"])
        self.assertEqual(idx["skills"], [])
        self.assertEqual(idx["warnings"][0]["code"], "ROOT_MISSING")

    def test_duplicate_slug_is_warned(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_skill(Path(a), "dup", "one. 触发词：alpha")
            write_skill(Path(b), "dup", "two. 触发词：beta")
            idx = skills.scan_roots([Path(a), Path(b)])
            self.assertEqual(len(idx["skills"]), 2)
            self.assertIn("SKILL_DUPLICATE", {w["code"] for w in idx["warnings"]})

    def test_missing_description_is_warned(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skills" / "bare"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("---\nname: bare\n---\nbody", encoding="utf-8")
            idx = skills.scan_roots([Path(tmp)])
            self.assertIn("SKILL_NO_DESC", {w["code"] for w in idx["warnings"]})


class RetrievalTests(unittest.TestCase):
    def _index(self, tmp):
        return skills.scan_roots([fixture(tmp)])

    def test_uninformative_name_is_retrievable_by_trigger(self):
        """The core guarantee: `houtai`/`kao` are opaque slugs, yet natural
        requests still land on them because triggers carry the meaning."""
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(self._index(tmp))
            cases = [
                ("给我建个带登录、手机能查数据的小网页", "houtai"),
                ("给记忆库出一套考卷，量化召回率", "kao"),
                ("把这份文档排成一份专业的 PDF 简历", "tu-kami"),
                ("把这段视频剪成竖屏 9:16 并烧字幕", "ffmpeg-skill"),
            ]
            for query, gold in cases:
                top = [c["slug"] for c in bm.search(query, 5)]
                self.assertIn(gold, top, f"{query!r} did not retrieve {gold}: {top}")
                self.assertEqual(top[0], gold, f"{query!r} ranked {top[0]} over {gold}")

    def test_alias_resolves_to_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = self._index(tmp)
            canonical, alias_map = skills.resolve_aliases(idx)
            self.assertNotIn("archify", canonical)
            self.assertIn("tu-archify", canonical)
            self.assertEqual(alias_map["archify"], "tu-archify")

    def test_alias_query_reaches_canonical_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(self._index(tmp))
            top = [c["slug"] for c in bm.search("archify 画个架构图", 3)]
            self.assertIn("tu-archify", top)
            self.assertNotIn("archify", top)

    def test_resolve_handles_alias_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(self._index(tmp))
            self.assertEqual(bm.resolve("/archify"), "tu-archify")
            self.assertEqual(bm.resolve("HOUTAI"), "houtai")

    def test_search_is_deterministic_and_ordered(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(self._index(tmp))
            first = bm.search("剪视频 烧字幕", 5)
            second = bm.search("剪视频 烧字幕", 5)
            self.assertEqual(first, second)
            self.assertEqual([c["score"] for c in first],
                             sorted((c["score"] for c in first), reverse=True))

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(self._index(tmp))
            self.assertEqual(bm.search("zzzzz qqqqq", 5), [])


class IndexRoundTripTests(unittest.TestCase):
    def test_build_save_load(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            target = Path(store) / "idx.json"
            with patch.dict(os.environ, {"MCPTOON_SKILLS_INDEX": str(target)}):
                index, path = skills.build_and_save([fixture(tmp)])
                self.assertTrue(path.is_file())
                loaded = skills.load_index()
            self.assertEqual(len(loaded["skills"]), len(index["skills"]))
            self.assertEqual(loaded["version"], skills.INDEX_VERSION)

    def test_load_missing_index_is_empty(self):
        with tempfile.TemporaryDirectory() as store:
            with patch.dict(os.environ, {"MCPTOON_SKILLS_INDEX": str(Path(store) / "nope.json")}):
                self.assertEqual(skills.load_index(), {})

    def test_load_corrupt_index_is_empty(self):
        with tempfile.TemporaryDirectory() as store:
            bad = Path(store) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with patch.dict(os.environ, {"MCPTOON_SKILLS_INDEX": str(bad)}):
                self.assertEqual(skills.load_index(), {})


class RouteTests(unittest.TestCase):
    def _run(self, tmp, answers, models=("m1", "m2", "m3")):
        """answers: model -> raw reply (or Exception)."""
        idx = skills.scan_roots([fixture(tmp)])

        def fake_chat(endpoint, model, prompt, timeout=90):
            self.assertIn("CANDIDATES", prompt)
            got = answers[model]
            if isinstance(got, Exception):
                raise got
            return got

        with patch.object(skills, "_chat", side_effect=fake_chat):
            return skills.route(idx, "建个带登录的网页，手机能查数据", 5, "http://x", list(models))

    def test_majority_vote_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, {
                "m1": '{"skill":"houtai","confidence":0.9}',
                "m2": '{"skill":"houtai","confidence":0.8}',
                "m3": '{"skill":"kao","confidence":0.4}',
            })
            self.assertEqual(res["skill"], "houtai")
            self.assertEqual(res["vote"]["houtai"], 2)
            self.assertFalse(res["unanimous"])

    def test_unanimous_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, {m: '{"skill":"houtai"}' for m in ("m1", "m2", "m3")})
            self.assertTrue(res["unanimous"])
            self.assertEqual(res["confidence"], 1.0)

    def test_transport_failure_does_not_abort_vote(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, {
                "m1": '{"skill":"houtai"}',
                "m2": RuntimeError("gateway 500"),
                "m3": '{"skill":"houtai"}',
            })
            self.assertEqual(res["skill"], "houtai")
            self.assertTrue(res["picks"]["m2"].startswith("!"))

    def test_alias_pick_is_normalised(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = skills.scan_roots([fixture(tmp)])
            with patch.object(skills, "_chat",
                              side_effect=lambda *a, **k: '{"skill":"archify"}'):
                res = skills.route(idx, "画个系统架构图", 5, "http://x", ["m1"])
            self.assertEqual(res["skill"], "tu-archify")

    def test_garbage_reply_yields_no_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, {m: "I cannot help with that." for m in ("m1", "m2", "m3")})
            self.assertEqual(res["skill"], "")
            self.assertEqual(res["confidence"], 0.0)


class BodyTriggerTests(unittest.TestCase):
    """Retrieval must not be hostage to how well an author wrote the description.

    Measured on this machine's catalog: stripping the trigger clause from
    descriptions drops top-1 recall 92.5% → 80%; mining the body puts it back at
    95%. These tests pin the mechanism, not the number.
    """

    def test_body_triggers_reads_trigger_line(self):
        body = "## 用法\n\n触发词：/tu-kami、排版、做PDF\n\n正文"
        got = skills._body_triggers(body)
        self.assertIn("排版", got)
        self.assertIn("做PDF", got)
        self.assertIn("tu-kami", got)  # leading slash stripped

    def test_body_triggers_reads_heading_plus_list(self):
        """Real SKILL.md files often put the heading on one line and the terms
        in a list below it — the shape that broke the first cut."""
        body = "## 触发词\n\n- 做 PDF\n- 排版\n- 简历\n\n## 用法\n\n正文"
        got = skills._body_triggers(body)
        for term in ("做 PDF", "排版", "简历"):
            self.assertIn(term, got)

    def test_body_triggers_heading_list_stops_at_next_heading(self):
        body = "## 触发词\n\n- 排版\n\n## 用法\n\n这里有一句很长的说明文字需要被排除在外\n"
        got = skills._body_triggers(body)
        self.assertIn("排版", got)
        self.assertNotIn("这里有一句很长的说明文字需要被排除在外", got)

    def test_body_triggers_reads_slash_commands_and_headings(self):
        got = skills._body_triggers("# 记忆体检\n\n跑 /kao 看看\n")
        self.assertIn("记忆体检", got)
        self.assertIn("kao", got)

    def test_body_triggers_dedupes_and_bounds_length(self):
        got = skills._body_triggers("触发词：aa、AA、bbbb、cccc、dddd")
        self.assertEqual([t.lower() for t in got].count("aa"), 1)
        self.assertTrue(all(len(t) <= 30 for t in got))

    def test_scan_merges_body_triggers_after_frontmatter(self):
        """A skill whose description carries no triggers is still retrievable."""
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "opaque-name", "没什么信息量的描述。",
                        body="## 用途\n\n触发词：给记忆库出考卷、记忆体检")
            idx = skills.scan_roots([Path(tmp)])
            trg = idx["skills"][0]["triggers"]
            self.assertIn("给记忆库出考卷", trg)
            self.assertIn("记忆体检", trg)

    def test_body_triggers_do_not_duplicate_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "s", "做图。触发词：配图、排版",
                        body="触发词：配图、排版")
            idx = skills.scan_roots([Path(tmp)])
            trg = [t.lower() for t in idx["skills"][0]["triggers"]]
            self.assertEqual(trg.count("配图"), 1)
            self.assertEqual(trg.count("排版"), 1)

    def test_body_compensation_improves_recall_without_triggers(self):
        """The point of the mechanism: a badly-described skill still routes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "tu-kami", "Typeset docs.",
                        body="## 触发词\n\n- 做 PDF\n- 排版\n- 简历\n- landing page")
            write_skill(root, "kao", "记忆体检。", body="触发词：考记忆、记忆掉分")
            bm = skills._BM25(skills.scan_roots([root]))
            for query, gold in [("把这份文档排成一份专业的 PDF 简历", "tu-kami"),
                                ("考一下记忆还准吗", "kao")]:
                top = [c["slug"] for c in bm.search(query, 3)]
                self.assertIn(gold, top, f"{query!r} missed {gold}: {top}")


class DeclaredToolsTests(unittest.TestCase):
    """A matched skill surfaces its instruments in the same turn.

    A skill is a playbook; a playbook needs tools. Declaring them lets one search
    hand back both, instead of the agent finding the skill then hunting for tools.
    """

    def test_parses_inline_list_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "slides", "做幻灯片", tools=["fs_write_file", "exa_search"])
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["tools"], ["fs_write_file", "exa_search"])

    def test_parses_indented_block_form(self):
        """Real SKILL.md files use the YAML block form as often as the inline one."""
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "slides", "做幻灯片",
                        tools=["fs_write_file", "exa_search"], tools_block=True)
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["tools"], ["fs_write_file", "exa_search"])

    def test_absent_tools_is_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "plain", "无工具")
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["tools"], [])

    def test_reads_allowed_tools_and_strips_permission_scope(self):
        """Agent Skills spells it `allowed-tools:` and scopes Bash with a pattern."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skills" / "s"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                "---\nname: s\ndescription: 用 opencli\n"
                "allowed-tools: Bash(opencli:*), Read, Edit, Write\n---\n\nbody\n",
                encoding="utf-8")
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["tools"], ["Bash", "Read", "Edit", "Write"])

    def test_shortlist_returns_declared_tools_in_rank_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "slides", "做幻灯片。触发词：幻灯片",
                        tools=["fs_write_file", "exa_search"])
            write_skill(root, "report", "写报告。触发词：报告", tools=["fs_read_file"])
            bm = skills._BM25(skills.scan_roots([root]))
            short = bm.search("做幻灯片", 1)
            self.assertEqual(bm.declared_tools(short), ["fs_write_file", "exa_search"])

    def test_declared_tools_dedupe_across_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "a", "幻灯片甲。触发词：幻灯片", tools=["fs_write_file", "x"])
            write_skill(root, "b", "幻灯片乙。触发词：幻灯片", tools=["fs_write_file", "y"])
            bm = skills._BM25(skills.scan_roots([root]))
            got = bm.declared_tools(bm.search("幻灯片", 5))
            self.assertEqual([t.lower() for t in got].count("fs_write_file"), 1)
            self.assertEqual(set(got), {"fs_write_file", "x", "y"})


class TwoBucketTests(unittest.TestCase):
    """Skills and tools rank in separate buckets with separate budgets."""

    def test_tool_bucket_degrades_to_empty_without_servers(self):
        """A machine with skills but no MCP servers still gets the skills half."""
        with patch("mcptoon.manifest.search_tools", side_effect=RuntimeError("no servers")):
            self.assertEqual(skills.tool_shortlist("anything", 5), [])

    def test_tool_bucket_is_not_starved_by_skills(self):
        fake = [{"server": "exa", "name": "search", "description": "web", "score": 0.9}]
        with patch("mcptoon.manifest.search_tools", return_value=fake) as m:
            got = skills.tool_shortlist("search the web", 5)
            self.assertEqual(got, fake)
            m.assert_called_once()

    def test_resolve_json_carries_both_buckets(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            root = Path(tmp)
            write_skill(root, "slides", "做幻灯片。触发词：幻灯片", tools=["fs_write_file"])
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "i.json"),
                   "MCPTOON_SKILLS_ROOTS": str(root)}
            run_cli(["mcptoon", "skills", "index"], env)
            fake = [{"server": "exa", "name": "search", "description": "web", "score": 0.9}]
            with patch("mcptoon.manifest.search_tools", return_value=fake):
                out = run_cli(["mcptoon", "skills", "resolve", "做幻灯片",
                               "--json", "--tools-k", "5"], env)
            payload = json.loads(out)
            self.assertEqual(payload["shortlist"][0]["slug"], "slides")
            self.assertEqual(payload["declared_tools"], ["fs_write_file"])
            self.assertEqual(payload["tools"], fake)

    def test_flag_value_does_not_leak_into_the_query(self):
        """`--k 2` used to contribute the token "2" to the query text."""
        self.assertEqual(skills._query_of(["opencli", "用法", "--k", "2"]), "opencli 用法")
        self.assertEqual(skills._query_of(["--k=2", "opencli", "用法"]), "opencli 用法")
        self.assertEqual(skills._query_of(["a", "--tools-k", "5", "b", "--json"]), "a b")

    def test_tools_bucket_is_off_unless_requested(self):
        """`resolve` stays offline by default: no server call without --tools-k."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            root = Path(tmp)
            write_skill(root, "slides", "做幻灯片。触发词：幻灯片", tools=["fs_write_file"])
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "i.json"),
                   "MCPTOON_SKILLS_ROOTS": str(root)}
            run_cli(["mcptoon", "skills", "index"], env)
            with patch("mcptoon.manifest.search_tools") as m:
                out = run_cli(["mcptoon", "skills", "resolve", "做幻灯片", "--json"], env)
            m.assert_not_called()
            payload = json.loads(out)
            self.assertEqual(payload["tools"], [])
            self.assertEqual(payload["declared_tools"], ["fs_write_file"])


class CliTests(unittest.TestCase):
    def _cli(self, argv, env):
        buf = StringIO()
        with patch.dict(os.environ, env), patch.object(sys, "argv", argv), redirect_stdout(buf):
            cli.main()
        return buf.getvalue()

    def test_index_resolve_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            root = fixture(tmp)
            env = {
                "MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                "MCPTOON_SKILLS_ROOTS": str(root),
            }
            out = self._cli(["mcptoon", "skills", "index"], env)
            self.assertIn("indexed 6 skills", out)

            out = self._cli(["mcptoon", "skills", "resolve", "考一下记忆还准吗", "--json"], env)
            payload = json.loads(out)
            self.assertEqual(payload["shortlist"][0]["slug"], "kao")

            out = self._cli(["mcptoon", "skills", "manifest"], env)
            self.assertIn("skills resolve", out)

    def test_resolve_without_index_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as store:
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "none.json")}
            with self.assertRaises(SystemExit):
                self._cli(["mcptoon", "skills", "resolve", "x"], env)

    def test_route_without_llm_config_exits_with_hint(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            env = {
                "MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                "MCPTOON_SKILLS_ROOTS": str(fixture(tmp)),
                "MCPTOON_SKILLS_ENDPOINT": "",
                "MCPTOON_SKILLS_MODEL": "",
            }
            self._cli(["mcptoon", "skills", "index"], env)
            err = StringIO()
            with patch.dict(os.environ, env), patch.object(sys, "argv",
                            ["mcptoon", "skills", "route", "hi"]), redirect_stdout(err):
                with self.assertRaises(SystemExit):
                    cli.main()

    def test_stats_reports_catalog_health(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            env = {
                "MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                "MCPTOON_SKILLS_ROOTS": str(fixture(tmp)),
            }
            self._cli(["mcptoon", "skills", "index"], env)
            out = self._cli(["mcptoon", "skills", "stats", "--json"], env)
            stats = json.loads(out)
            self.assertEqual(stats["skills"], 6)
            self.assertEqual(stats["canonical"], 5)
            self.assertEqual(stats["aliases"], 1)
            self.assertEqual(stats["no_description"], [])


class SyncTests(unittest.TestCase):
    """`skills sync` distributes a source catalog into agent views.

    These pin the three safety rules, because each one corresponds to a real
    way a naive sync destroys user work: drift silently overwritten, deletion
    propagated as data loss, and two managers fighting over one folder.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        for slug in ("alpha", "beta"):
            d = self.src / slug
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {slug}\ndescription: d\n---\n", encoding="utf-8")
        self.v1 = self.base / "v1"
        self.v2 = self.base / "v2"

    def tearDown(self):
        self.tmp.cleanup()

    def test_links_every_skill_into_every_view(self):
        rep = skills.sync_skills(self.src, [self.v1, self.v2])
        for view in (self.v1, self.v2):
            self.assertEqual(sorted(rep["views"][str(view)]["added"]), ["alpha", "beta"])
            self.assertTrue(skills._is_link(view / "alpha"))

    def test_second_run_is_a_no_op(self):
        skills.sync_skills(self.src, [self.v1])
        rep = skills.sync_skills(self.src, [self.v1])
        a = rep["views"][str(self.v1)]
        self.assertEqual(a["added"], [])
        self.assertEqual(sorted(a["ok"]), ["alpha", "beta"])

    def test_drift_is_archived_never_deleted(self):
        skills.sync_skills(self.src, [self.v1])
        stray = self.v1 / "alpha"
        stray.unlink()
        stray.mkdir()
        (stray / "SKILL.md").write_text("user's hand-edited copy\n", encoding="utf-8")
        rep = skills.sync_skills(self.src, [self.v1])
        self.assertEqual(rep["views"][str(self.v1)]["drifted"], ["alpha"])
        self.assertTrue(skills._is_link(self.v1 / "alpha"))
        archived = list((self.base / "_archive" / "v1").iterdir())
        self.assertEqual(len(archived), 1)
        self.assertIn("user's hand-edited copy", (archived[0] / "SKILL.md").read_text(
            encoding="utf-8"))

    def test_source_removal_prunes_the_views(self):
        skills.sync_skills(self.src, [self.v1, self.v2])
        shutil.rmtree(self.src / "beta")
        rep = skills.sync_skills(self.src, [self.v1, self.v2])
        for view in (self.v1, self.v2):
            self.assertEqual(rep["views"][str(view)]["pruned"], ["beta"])
            self.assertFalse((view / "beta").exists())

    def test_foreign_link_is_left_alone(self):
        """A view entry another manager owns must never be touched."""
        other = self.base / "other" / "alpha"
        other.mkdir(parents=True)
        self.v2.mkdir(parents=True)
        if os.name == "nt":
            import subprocess
            subprocess.run(["cmd", "/c", "mklink", "/J", str(self.v2 / "alpha"), str(other)],
                           capture_output=True, check=False)
        else:
            os.symlink(other, self.v2 / "alpha", target_is_directory=True)
        rep = skills.sync_skills(self.src, [self.v2])
        # alpha is owned elsewhere: reported, never touched. beta is missing, so
        # it is still placed — leaving a foreign entry alone does not block the
        # rest of the sync.
        self.assertEqual(rep["views"][str(self.v2)]["foreign"], ["alpha"])
        self.assertEqual(rep["views"][str(self.v2)]["added"], ["beta"])
        self.assertTrue(skills._is_link(self.v2 / "beta"))

    def test_real_directory_that_is_not_ours_is_never_removed(self):
        """A plain folder in a view is not drift — it may be a user's own skill."""
        self.v1.mkdir(parents=True)
        keep = self.v1 / "gamma"
        keep.mkdir()
        (keep / "SKILL.md").write_text("mine\n", encoding="utf-8")
        skills.sync_skills(self.src, [self.v1])
        self.assertTrue(keep.is_dir())
        self.assertFalse(skills._is_link(keep))

    def test_source_is_never_written(self):
        before = sorted(p.name for p in self.src.iterdir())
        skills.sync_skills(self.src, [self.v1, self.v2])
        self.assertEqual(before, sorted(p.name for p in self.src.iterdir()))

    def test_dry_run_writes_nothing(self):
        rep = skills.sync_skills(self.src, [self.v1], dry_run=True)
        self.assertTrue(rep["dryRun"])
        self.assertEqual(rep["views"][str(self.v1)]["added"], ["alpha", "beta"])
        self.assertFalse(self.v1.exists(), "dry run must not create the view")

    def test_copy_strategy_makes_real_directories(self):
        skills.sync_skills(self.src, [self.v1], strategy="copy")
        self.assertFalse(skills._is_link(self.v1 / "alpha"))
        self.assertTrue((self.v1 / "alpha" / "SKILL.md").is_file())

    def test_bad_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            skills.sync_skills(self.src, [self.v1], strategy="teleport")

    def test_whole_directory_view_link_is_never_descended_into(self):
        """A view that is itself a link to the source must be left alone.

        This is the tongbu-skills layout: ~/.claude/skills is a junction to the
        source. Descending into it would see the source's own children as real
        directories and archive every one of them.
        """
        self.v1.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            import subprocess
            subprocess.run(["cmd", "/c", "mklink", "/J", str(self.v1), str(self.src)],
                           capture_output=True, check=False)
        else:
            os.symlink(self.src, self.v1, target_is_directory=True)
        before = sorted(p.name for p in self.src.iterdir())
        rep = skills.sync_skills(self.src, [self.v1])
        a = rep["views"][str(self.v1)]
        self.assertTrue(a.get("wholeDirLink"))
        self.assertEqual(a["drifted"], [])
        self.assertEqual(before, sorted(p.name for p in self.src.iterdir()),
                         "the source must be untouched")
        self.assertFalse((self.base / "_archive").exists(),
                         "nothing may be archived when the view is a whole-dir link")

    def test_cli_dry_run_reports_but_writes_nothing(self):
        out = run_cli(["mcptoon", "skills", "sync", str(self.src), str(self.v1), "--dry"],
                      {"MCPTOON_SKILLS_VIEWS": ""})
        self.assertIn("dry run", out)
        self.assertIn("+2 new", out)
        self.assertFalse(self.v1.exists())

    def test_cli_json_output_is_machine_readable(self):
        out = run_cli(["mcptoon", "skills", "sync", str(self.src), str(self.v1), "--json"],
                      {"MCPTOON_SKILLS_VIEWS": ""})
        data = json.loads(out)
        self.assertEqual(data["skills"], ["alpha", "beta"])


class CatalogManagementTests(unittest.TestCase):
    """add / remove / list --usage. Removal archives; it never deletes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        self.src.mkdir()
        self.env = {
            "MCPTOON_SKILLS_INDEX": str(self.base / "idx.json"),
            "MCPTOON_SKILLS_USAGE": str(self.base / "usage.json"),
            "MCPTOON_SKILLS_ROOTS": str(self.src),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_creates_a_valid_skill(self):
        out = run_cli(["mcptoon", "skills", "add", str(self.src), "search-web",
                       "--desc", "Search the web. 触发词：搜网页"], self.env)
        self.assertIn("added search-web", out)
        md = self.src / "search-web" / "SKILL.md"
        self.assertTrue(md.is_file())
        self.assertIn("name: search-web", md.read_text(encoding="utf-8"))

    def test_add_refuses_a_duplicate(self):
        run_cli(["mcptoon", "skills", "add", str(self.src), "dup"], self.env)
        with self.assertRaises(SystemExit) as cm:
            run_cli(["mcptoon", "skills", "add", str(self.src), "dup"], self.env)
        self.assertEqual(cm.exception.code, 1)

    def test_add_rejects_a_bad_slug(self):
        with self.assertRaises(SystemExit) as cm:
            run_cli(["mcptoon", "skills", "add", str(self.src), "bad/name"], self.env)
        self.assertEqual(cm.exception.code, 1)

    def test_remove_archives_instead_of_deleting(self):
        run_cli(["mcptoon", "skills", "add", str(self.src), "gone"], self.env)
        out = run_cli(["mcptoon", "skills", "remove", str(self.src), "gone"], self.env)
        self.assertIn("archived to", out)
        self.assertFalse((self.src / "gone").exists())
        archived = list((self.base / "_archive" / "removed").iterdir())
        self.assertEqual(len(archived), 1)
        self.assertIn("gone", archived[0].name)
        self.assertTrue((archived[0] / "SKILL.md").is_file(),
                        "the archived skill must still be recoverable")

    def test_remove_unknown_skill_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            run_cli(["mcptoon", "skills", "remove", str(self.src), "ghost"], self.env)
        self.assertEqual(cm.exception.code, 1)

    def test_resolve_records_usage(self):
        for name, desc in (("search-web", "Search the web. 触发词：搜网页"),
                           ("make-pdf", "Typeset a PDF")):
            run_cli(["mcptoon", "skills", "add", str(self.src), name, "--desc", desc], self.env)
        run_cli(["mcptoon", "skills", "index", str(self.src)], self.env)
        run_cli(["mcptoon", "skills", "resolve", "搜网页", "--k", "1"], self.env)
        run_cli(["mcptoon", "skills", "resolve", "搜网页", "--k", "1"], self.env)
        usage = json.loads((self.base / "usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["search-web"]["count"], 2)
        self.assertEqual(usage["search-web"]["last"], date.today().isoformat())

    def test_list_usage_orders_by_hits(self):
        for name in ("aaa", "bbb"):
            run_cli(["mcptoon", "skills", "add", str(self.src), name,
                     "--desc", f"{name} thing"], self.env)
        run_cli(["mcptoon", "skills", "index", str(self.src)], self.env)
        run_cli(["mcptoon", "skills", "resolve", "bbb thing", "--k", "1"], self.env)
        out = run_cli(["mcptoon", "skills", "list", "--usage", "--json"], self.env)
        rows = json.loads(out)
        self.assertEqual(rows[0]["slug"], "bbb")
        self.assertEqual(rows[0]["uses"], 1)

    def test_list_json_hides_alias_cards_by_default(self):
        write_skill(self.src, "archify", "别名转发：/archify → /tu-archify。触发词：/archify",
                    layout="flat")
        write_skill(self.src, "tu-archify", "架构图引擎。触发词：架构图", layout="flat")
        run_cli(["mcptoon", "skills", "index", str(self.src)], self.env)
        rows = json.loads(run_cli(["mcptoon", "skills", "list", "--json"], self.env))
        self.assertEqual([r["slug"] for r in rows], ["tu-archify"])
        rows_all = json.loads(run_cli(["mcptoon", "skills", "list", "--all", "--json"], self.env))
        self.assertEqual(sorted(r["slug"] for r in rows_all), ["archify", "tu-archify"])


class UnroutableTests(unittest.TestCase):
    """`stats` must name the skills no query can reach — that is the guarantee."""

    def test_flags_skill_with_nothing_to_match_on(self):
        """No description and no triggers anywhere — only the slug remains."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "houtai", "", body="正文也没有触发词，只有一段普通说明。")
            write_skill(root, "tu-kami", "做图。触发词：排版、做PDF")
            got = [u["slug"] for u in skills.unroutable(skills.scan_roots([root]))]
            self.assertIn("houtai", got)
            self.assertNotIn("tu-kami", got)

    def test_body_triggers_make_a_skill_routable(self):
        """The compensation counts: no frontmatter triggers, but the body has them."""
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "houtai", "无信息", body="## 触发词\n\n- 后台\n- 建个表")
            self.assertEqual(skills.unroutable(skills.scan_roots([Path(tmp)])), [])

    def test_healthy_catalog_reports_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(skills.unroutable(skills.scan_roots([fixture(tmp)])), [])


class VersionGateTests(unittest.TestCase):
    """The gate is the discipline that stops "edited but forgot to bump".

    Every rule below mirrors the tongbu-skills v7 ledger the two managers share,
    so a skill the gate blocks here is blocked there too — and, just as
    important, a skill it lets through is not blocked there.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        self.src.mkdir()
        self.ledger = self.base / "versions.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _skill(self, slug: str, version: str | None, body: str = "b") -> Path:
        d = self.src / slug
        d.mkdir(parents=True, exist_ok=True)
        ver = f"version: {version}\n" if version is not None else ""
        (d / "SKILL.md").write_text(
            f"---\nname: {slug}\ndescription: d\n{ver}---\n\n{body}\n", encoding="utf-8")
        return d

    def test_first_sight_onboards_without_blocking(self):
        self._skill("alpha", "1.0")
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(rep["allowed"], ["alpha"])
        self.assertEqual(rep["blocked"], [])
        self.assertEqual(rep["onboarded"], ["alpha"])

    def test_unchanged_content_passes_on_the_second_run(self):
        self._skill("alpha", "1.0")
        skills.version_gate(skills._source_skills(self.src), self.ledger)
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(rep["allowed"], ["alpha"])
        self.assertEqual(rep["blocked"], [])

    def test_content_change_without_a_bump_is_blocked(self):
        self._skill("alpha", "1.0")
        skills.version_gate(skills._source_skills(self.src), self.ledger)
        self._skill("alpha", "1.0", body="changed!")
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(rep["allowed"], [])
        self.assertEqual(rep["blocked"], [("alpha", "1.0")])

    def test_a_bump_lets_the_change_through(self):
        self._skill("alpha", "1.0")
        skills.version_gate(skills._source_skills(self.src), self.ledger)
        self._skill("alpha", "1.1", body="changed!")
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(rep["allowed"], ["alpha"])
        self.assertEqual(rep["blocked"], [])

    def test_force_overrides_and_refreshes_the_ledger(self):
        self._skill("alpha", "1.0")
        skills.version_gate(skills._source_skills(self.src), self.ledger)
        self._skill("alpha", "1.0", body="changed!")
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger, force=True)
        self.assertEqual(rep["allowed"], ["alpha"])
        self.assertEqual(rep["forced"], ["alpha"])
        again = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(again["blocked"], [], "a forced run must rebaseline the ledger")

    def test_unversioned_skill_is_warned_not_blocked(self):
        self._skill("legacy", None)
        skills.version_gate(skills._source_skills(self.src), self.ledger)
        self._skill("legacy", None, body="changed!")
        rep = skills.version_gate(skills._source_skills(self.src), self.ledger)
        self.assertEqual(rep["allowed"], ["legacy"])
        self.assertEqual(rep["legacy"], ["legacy"])

    def test_ledger_files_do_not_hash_themselves(self):
        """A skill holding the ledger must not drift every run (the self-reference bug)."""
        d = self.src / "tongbu-skills"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: tongbu-skills\ndescription: d\nversion: 1.0\n---\n\nb\n",
            encoding="utf-8")
        (d / "skill_versions.json").write_text("{}", encoding="utf-8")
        first = skills._skill_content_hash(d)
        (d / "skill_versions.json").write_text('{"x": 1}', encoding="utf-8")
        self.assertEqual(skills._skill_content_hash(d), first)

    def test_dry_run_does_not_write_the_ledger(self):
        self._skill("alpha", "1.0")
        skills.version_gate(skills._source_skills(self.src), self.ledger, update_ledger=False)
        self.assertFalse(self.ledger.exists())

    def test_cli_blocks_and_exits_nonzero_when_everything_is_gated(self):
        self._skill("alpha", "1.0")
        env = {"MCPTOON_SKILLS_LEDGER": str(self.ledger)}
        run_cli(["mcptoon", "skills", "sync", str(self.src), str(self.base / "v1"),
                 "--version-gate"], env)
        self._skill("alpha", "1.0", body="changed!")
        fresh = self.base / "v2"
        with self.assertRaises(SystemExit) as cm:
            run_cli(["mcptoon", "skills", "sync", str(self.src), str(fresh),
                     "--version-gate"], env)
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse(fresh.exists(),
                         "a blocked skill must not be linked into a view")

    def test_cli_force_lets_a_blocked_skill_through(self):
        self._skill("alpha", "1.0")
        env = {"MCPTOON_SKILLS_LEDGER": str(self.ledger)}
        run_cli(["mcptoon", "skills", "sync", str(self.src), str(self.base / "v1"),
                 "--version-gate"], env)
        self._skill("alpha", "1.0", body="changed!")
        out = run_cli(["mcptoon", "skills", "sync", str(self.src), str(self.base / "v2"),
                       "--version-gate", "--force"], env)
        self.assertIn("+1 new", out)
        self.assertTrue(skills._is_link(self.base / "v2" / "alpha"))


class DerivedViewTests(unittest.TestCase):
    """Roo/OpenCode consume a flat ``<slug>.md`` per skill.

    The bytes must match the tongbu lineage exactly, line endings included:
    a derived view that differs by CRLF is a diff the next sync has to fight.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        d = self.src / "alpha"
        d.mkdir(parents=True)
        self.body = "---\nname: alpha\ndescription: d\n---\n\nline one\nline two\n"
        (d / "SKILL.md").write_text(self.body, encoding="utf-8")
        (d / "helper.py").write_text("print('x')\n", encoding="utf-8")
        self.view = self.base / "roo"
        self.views = {"roo": self.view}

    def tearDown(self):
        self.tmp.cleanup()

    def test_derived_md_matches_the_source_body(self):
        skills.sync_derived(self.src, skills._source_skills(self.src), self.views)
        got = (self.view / "alpha.md").read_text(encoding="utf-8")
        self.assertEqual(got.replace("\r\n", "\n"), self.body)

    def test_derived_md_uses_platform_line_endings(self):
        """tongbu writes via text mode, so on Windows the view is CRLF."""
        skills.sync_derived(self.src, skills._source_skills(self.src), self.views)
        raw = (self.view / "alpha.md").read_bytes()
        expected = self.body.replace("\n", os.linesep).encode("utf-8")
        self.assertEqual(raw, expected)

    def test_py_attachments_are_copied_with_the_slug_prefix(self):
        skills.sync_derived(self.src, skills._source_skills(self.src), self.views)
        self.assertTrue((self.view / "alpha_helper.py").is_file())

    def test_stale_derived_files_are_archived_not_deleted(self):
        skills.sync_derived(self.src, skills._source_skills(self.src), self.views)
        (self.view / "ghost.md").write_text("old\n", encoding="utf-8")
        rep = skills.sync_derived(self.src, skills._source_skills(self.src), self.views)
        self.assertEqual(rep["views"]["roo"]["stale"], ["ghost.md"])
        self.assertFalse((self.view / "ghost.md").exists())
        archived = list((self.base / "_archive" / "derived-roo").iterdir())
        self.assertEqual([f.name for f in archived], ["ghost.md"])

    def test_dry_run_writes_nothing(self):
        skills.sync_derived(self.src, skills._source_skills(self.src), self.views,
                            dry_run=True)
        self.assertFalse(self.view.exists())

    def test_cli_derived_writes_the_flat_view(self):
        env = {"MCPTOON_SKILLS_DERIVED": f"roo={self.view}"}
        out = run_cli(["mcptoon", "skills", "sync", str(self.src), "--derived", "roo"], env)
        self.assertIn("roo:", out)
        self.assertTrue((self.view / "alpha.md").is_file())


class TombstoneTests(unittest.TestCase):
    """Removal must land as a git commit, or a two-way git sync revives it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        (self.repo / "skills" / "alpha").mkdir(parents=True)
        (self.repo / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: d\n---\n", encoding="utf-8")
        (self.repo / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
        self._git("init")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        self._git("add", "-A")
        self._git("commit", "-m", "init")
        self.src = self.repo / "skills"

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=str(self.repo),
                              capture_output=True, text=True)

    def test_tombstone_commits_only_the_removed_path(self):
        (self.repo / "unrelated.txt").write_text("edited by another session\n",
                                                 encoding="utf-8")
        rc = skills._cmd_skills_remove(self.src, "alpha", "text", tombstone=True,
                                       archive=self.base / "graveyard")
        self.assertEqual(rc, 0)
        log = self._git("log", "--oneline", "-1").stdout
        self.assertIn("tombstone", log)
        changed = self._git("show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("skills/alpha", changed)
        self.assertNotIn("unrelated.txt", changed,
                         "a tombstone commit must never sweep unrelated work")
        status = self._git("status", "--porcelain").stdout
        self.assertIn("unrelated.txt", status, "the other edit stays uncommitted")

    def test_removal_uses_the_shared_graveyard_when_given_one(self):
        shared = self.base / "skills_archive"
        rc = skills._cmd_skills_remove(self.src, "alpha", "text",
                                       archive=shared)
        self.assertEqual(rc, 0)
        archived = list((shared / "removed").iterdir())
        self.assertEqual(len(archived), 1)
        self.assertTrue((archived[0] / "SKILL.md").is_file())

    def test_removal_without_a_repo_still_archives(self):
        plain = self.base / "plain"
        (plain / "alpha").mkdir(parents=True)
        (plain / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n",
                                                  encoding="utf-8")
        rc = skills._cmd_skills_remove(plain, "alpha", "text", tombstone=True,
                                       archive=self.base / "g2")
        self.assertEqual(rc, 0)
        self.assertTrue(list((self.base / "g2" / "removed").iterdir()))


class ArchiveFlagTests(unittest.TestCase):
    """`--archive` points drift/removal at the same graveyard tongbu uses."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        d = self.src / "alpha"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: alpha\ndescription: d\n---\n",
                                    encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_parks_drift_in_the_given_archive(self):
        view = self.base / "v1"
        view.mkdir()
        drift = view / "alpha"
        drift.mkdir()
        (drift / "SKILL.md").write_text("user copy\n", encoding="utf-8")
        shared = self.base / "skills_archive"
        skills.sync_skills(self.src, [view], archive=shared)
        parked = list((shared / "v1").iterdir())
        self.assertEqual(len(parked), 1)
        self.assertIn("user copy", (parked[0] / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((self.base / "_archive").exists(),
                         "the default graveyard must not be touched when one is given")


class SkipDirTests(unittest.TestCase):
    """`_index` carries a SKILL.md but is not a skill — it must never be published.

    The live vault keeps its index card at ``skills/_index/SKILL.md``. tongbu-skills
    skips that name in every walker; mcptoon adding it would put a phantom skill
    into every derived view, which is exactly what the byte-parity check against
    the live ``~/.roo/commands`` caught.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        for name in ("_index", ".hidden", "real"):
            d = self.src / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n",
                                        encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_source_skills_skips_index_and_dot_dirs(self):
        self.assertEqual(list(skills._source_skills(self.src)), ["real"])

    def test_scan_roots_skips_them_too(self):
        got = [s["slug"] for s in skills.scan_roots([self.src])["skills"]]
        self.assertEqual(got, ["real"])

    def test_sync_never_publishes_the_index_card(self):
        view = self.base / "v1"
        skills.sync_skills(self.src, [view])
        self.assertEqual(sorted(p.name for p in view.iterdir()), ["real"])

    def test_derived_never_writes_the_index_card(self):
        view = self.base / "roo"
        skills.sync_derived(self.src, skills._source_skills(self.src), {"roo": view})
        self.assertEqual(sorted(p.name for p in view.iterdir()), ["real.md"])


class RealPathDedupTests(unittest.TestCase):
    """`skills index` must de-duplicate roots by *real* path, like `bench` does.

    A machine whose agent skill folders are junctions onto one real catalog is the
    normal multi-agent layout, not an exotic one. Walking each root naively then
    reports the catalog N times and emits a bogus ``SKILL_DUPLICATE`` per file —
    the exact noise `bench` already avoids. These pin the same behaviour here.
    """

    def _catalog(self, base: Path, *slugs: str) -> Path:
        real = base / "real"
        for slug in slugs:
            d = real / slug
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {slug}\ndescription: does {slug}\n---\n\nbody\n",
                encoding="utf-8")
        return real

    def test_alias_root_does_not_duplicate_the_catalog(self):
        """Two roots pointing at the same real files must index each skill once."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = self._catalog(base, "alpha", "beta")
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                alias = real  # platform without symlink rights: same path, one count
            idx = skills.scan_roots([real, alias])
            self.assertEqual(sorted(s["slug"] for s in idx["skills"]), ["alpha", "beta"])
            self.assertEqual(idx["warnings"], [])

    def test_same_root_twice_counts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = self._catalog(Path(tmp), "alpha")
            idx = skills.scan_roots([real, real])
            self.assertEqual([s["slug"] for s in idx["skills"]], ["alpha"])
            self.assertFalse([w for w in idx["warnings"]
                              if w["code"] == "SKILL_DUPLICATE"])

    def test_distinct_roots_are_unchanged(self):
        """No aliases on the machine: counts must not move (the safety net)."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            root_a = self._catalog(Path(a), "alpha", "beta")
            root_b = self._catalog(Path(b), "gamma")
            idx = skills.scan_roots([root_a, root_b])
            self.assertEqual(sorted(s["slug"] for s in idx["skills"]),
                             ["alpha", "beta", "gamma"])
            self.assertEqual(idx["warnings"], [])

    def test_same_slug_from_two_distinct_real_files_is_still_flagged(self):
        """The genuinely ambiguous case (different files, same slug) keeps warning."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write_skill(Path(a), "dup", "one. 触发词：alpha")
            write_skill(Path(b), "dup", "two. 触发词：beta")
            idx = skills.scan_roots([Path(a), Path(b)])
            self.assertEqual(len(idx["skills"]), 2)
            self.assertIn("SKILL_DUPLICATE", {w["code"] for w in idx["warnings"]})


class DescriptionQuoteTests(unittest.TestCase):
    """A YAML-quoted ``description: "…"`` must never leak its quotes.

    YAML quoting is frontmatter syntax, not part of the value. It must be gone
    everywhere a description is seen — the index, `skills list`, `skills resolve`
    and BM25 matching — while internal quotes stay as content.
    """

    def test_scan_strips_surrounding_double_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "agent", '"🤖 子代理管理器。触发词：/agent、agent"')
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["desc"], "🤖 子代理管理器。触发词：/agent、agent")

    def test_scan_strips_surrounding_single_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "q", "'single quoted desc. 触发词：q'")
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["desc"], "single quoted desc. 触发词：q")

    def test_internal_quotes_are_preserved(self):
        """Only a matching pair at the very ends is stripped — never a blanket replace."""
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "inner", 'He said "hi" then left. 触发词：inner')
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["desc"], 'He said "hi" then left. 触发词：inner')

    def test_unquoted_description_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "plain", "no quotes here. 触发词：plain")
            idx = skills.scan_roots([Path(tmp)])
            self.assertEqual(idx["skills"][0]["desc"], "no quotes here. 触发词：plain")

    def test_list_output_has_no_leading_quote(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            write_skill(Path(tmp), "agent", '"🤖 子代理管理器。触发词：/agent、agent"')
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                   "MCPTOON_SKILLS_ROOTS": str(Path(tmp))}
            run_cli(["mcptoon", "skills", "index"], env)
            out = run_cli(["mcptoon", "skills", "list"], env)
            self.assertNotIn('"', out)
            self.assertIn("🤖 子代理管理器", out)

    def test_resolve_output_and_matching_see_cleaned_text(self):
        """Display AND BM25 read the same cleaned description."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            write_skill(Path(tmp), "agent", '"子代理管理器。触发词：/agent、agent"')
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                   "MCPTOON_SKILLS_ROOTS": str(Path(tmp))}
            run_cli(["mcptoon", "skills", "index"], env)
            out = run_cli(["mcptoon", "skills", "resolve", "子代理管理器", "--k", "1"], env)
            self.assertIn("agent", out)
            self.assertNotIn('"', out)

    def test_bm25_matches_through_a_legacy_quoted_index(self):
        """An index built before the fix is still clean at match and display time."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as store:
            write_skill(Path(tmp), "agent", '"子代理管理器。触发词：/agent、agent"')
            env = {"MCPTOON_SKILLS_INDEX": str(Path(store) / "idx.json"),
                   "MCPTOON_SKILLS_ROOTS": str(Path(tmp))}
            run_cli(["mcptoon", "skills", "index"], env)
            idx_path = Path(store) / "idx.json"
            legacy = json.loads(idx_path.read_text(encoding="utf-8"))
            for s in legacy["skills"]:  # simulate a pre-fix persisted index
                s["desc"] = f'"{s["desc"]}"'
            idx_path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            shortlist = skills._BM25(skills.load_index()).search("子代理管理器", 1)
            self.assertEqual(shortlist[0]["slug"], "agent")
            self.assertFalse(shortlist[0]["desc"].startswith('"'))


class ViewScopeTests(unittest.TestCase):
    """What a sync must NOT touch in a view folder.

    A real agent skill folder is shared ground: Codex keeps a ``.system`` folder,
    and a user may keep unrelated directories there. mcptoon only ever acts on
    the source catalog's own slugs, and never on a dot-entry.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        d = self.src / "alpha"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: alpha\ndescription: d\n---\n",
                                    encoding="utf-8")
        self.view = self.base / "v1"
        self.view.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_dot_entries_are_never_touched(self):
        system = self.view / ".system"
        system.mkdir()
        (system / "keep.md").write_text("codex's own\n", encoding="utf-8")
        skills.sync_skills(self.src, [self.view])
        self.assertTrue((system / "keep.md").is_file())
        self.assertEqual((system / "keep.md").read_text(encoding="utf-8"),
                         "codex's own\n")

    def test_view_entries_outside_the_catalog_are_left_alone(self):
        mine = self.view / "my-own-thing"
        mine.mkdir()
        (mine / "SKILL.md").write_text("---\nname: my-own-thing\n---\n", encoding="utf-8")
        skills.sync_skills(self.src, [self.view])
        self.assertTrue(mine.is_dir())
        self.assertFalse(skills._is_link(mine), "an unrelated folder must not be replaced")


class NestedSkillScanTests(unittest.TestCase):
    """Skills nest, and a one-level walk hid them without raising anything.

    On the machine this was found on, 29 skills sat one level deeper than the
    walk looked — the whole ``video-seedance`` family plus a bundled example.
    The catalog indexed 376 of 405 and retrieval simply never offered the rest:
    a silent miss, which is the worst failure mode for a router.
    """

    def _nested(self, tmp: str, depth: int = 1) -> Path:
        """One skill whose own ``skills/`` folder holds another one.

        ``depth=1`` is the real-world shape (``<skill>/skills/<slug>/``);
        higher values add extra sub-catalogs in between.
        """
        root = Path(tmp)
        write_skill(root, "video-seedance", "Seedance 2.0 video router", layout="nested")
        base = root / "skills" / "video-seedance" / "skills"
        for level in range(depth - 1):
            base = base / f"sub{level}"
        base.mkdir(parents=True, exist_ok=True)
        write_skill(base, "seedance-audio",
                    "Seedance audio, dialogue, lip-sync, music, sound effects",
                    layout="flat")
        return root

    def test_skill_nested_inside_a_skill_is_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = skills.scan_roots([self._nested(tmp)])
            slugs = {s["slug"] for s in idx["skills"]}
            self.assertIn("video-seedance", slugs)
            self.assertIn("seedance-audio", slugs,
                          "a skill one level below another must still be indexed")

    def test_nested_skill_is_retrievable_by_its_own_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            bm = skills._BM25(skills.scan_roots([self._nested(tmp)]))
            top = [c["slug"] for c in bm.search("audio lip-sync dialogue", 3)]
            self.assertEqual(top[0], "seedance-audio", top)

    def test_arbitrary_depth_is_walked(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx = skills.scan_roots([self._nested(tmp, depth=4)])
            self.assertIn("seedance-audio", {s["slug"] for s in idx["skills"]})

    def test_skipped_directories_stay_skipped_at_depth(self):
        """Recursion must not sneak into ``node_modules`` or a dot-folder."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._nested(tmp)
            parent = root / "skills" / "video-seedance"
            for junk in ("node_modules", ".git", "__pycache__"):
                write_skill(parent / junk, f"ghost-{junk.strip('.')}",
                            "should never be indexed", layout="flat")
            slugs = {s["slug"] for s in skills.scan_roots([root])["skills"]}
            self.assertFalse([s for s in slugs if s.startswith("ghost-")], slugs)


class SearchKBudgetTests(unittest.TestCase):
    """``search`` must read ``k <= 0`` as "nothing", not as "one".

    ``max(1, k)`` quietly turned a request for zero results into one result, so
    a caller could not tell "nothing, please" from "here is one". A negative
    ``k`` was worse: ``ranked[:-1]`` returned the entire ranking minus its last
    entry — a plausible-looking answer nobody asked for, and no error anywhere.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bm = skills._BM25(skills.scan_roots([fixture(self.tmp.name)]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_zero_asks_for_nothing(self):
        self.assertEqual(self.bm.search("剪视频", 0), [])

    def test_negative_k_does_not_slice_from_the_end(self):
        """The old bug answered with the whole ranking minus its last entry.

        Needs two matches to be a real test: with one match, ``ranked[:-1]`` is
        empty too, and the bug would hide behind a passing assertion.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "cut-a", "剪视频 竖屏 烧字幕", layout="nested")
            write_skill(root, "cut-b", "剪视频 剪辑 工具箱", layout="nested")
            bm = skills._BM25(skills.scan_roots([root]))
            full = bm.search("剪视频", 5)
            self.assertGreaterEqual(len(full), 2, full)
            self.assertNotEqual(full[:-1], [])
            self.assertEqual(bm.search("剪视频", -1), [])

    def test_positive_k_still_returns_that_ranking(self):
        hits = self.bm.search("剪视频", 3)
        self.assertTrue(hits)
        self.assertLessEqual(len(hits), 3)
        self.assertEqual(hits[0]["slug"], "ffmpeg-skill")

    def test_k_past_the_catalog_is_harmless(self):
        self.assertLessEqual(len(self.bm.search("剪视频", 999)), 6)


class KFlagTests(unittest.TestCase):
    """``--k`` must refuse bad input in one line instead of a traceback.

    ``--k abc`` escaped as ``ValueError: invalid literal for int()`` from inside
    the parser, so a typo read as a crash in mcptoon. ``--k 0`` answered with
    one result. Both are now a clear message on stderr and exit 1, matching
    every other bad-invocation path in this CLI.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = tempfile.TemporaryDirectory()
        self.env = {
            "MCPTOON_SKILLS_INDEX": str(Path(self.store.name) / "idx.json"),
            "MCPTOON_SKILLS_ROOTS": str(fixture(self.tmp.name)),
        }
        self._cli(["mcptoon", "skills", "index"], self.env)

    def tearDown(self):
        self.tmp.cleanup()
        self.store.cleanup()

    def _cli(self, argv, env=None):
        buf = StringIO()
        with patch.dict(os.environ, env or self.env), patch.object(sys, "argv", argv), \
                redirect_stdout(buf):
            cli.main()
        return buf.getvalue()

    def _refusal(self, argv):
        err = StringIO()
        with patch.dict(os.environ, self.env), patch.object(sys, "argv", argv), \
                redirect_stdout(StringIO()), redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                cli.main()
        return caught.exception.code, err.getvalue()

    def _resolve(self, *extra):
        return json.loads(self._cli(["mcptoon", "skills", "resolve", "考记忆", "--json", *extra]))

    def test_non_integer_k_is_refused_in_one_line(self):
        code, err = self._refusal(["mcptoon", "skills", "resolve", "考记忆", "--k", "abc"])
        self.assertEqual(code, 1)
        self.assertIn("--k needs an integer", err)
        self.assertIn("'abc'", err)
        self.assertNotIn("Traceback", err)

    def test_zero_and_negative_k_are_refused(self):
        for bad in ("0", "-1", "-5"):
            code, err = self._refusal(["mcptoon", "skills", "resolve", "考记忆", "--k", bad])
            self.assertEqual(code, 1, bad)
            self.assertIn("--k must be at least 1", err, bad)

    def test_bad_tools_k_names_the_flag_it_complained_about(self):
        code, err = self._refusal(
            ["mcptoon", "skills", "resolve", "考记忆", "--tools-k", "abc"])
        self.assertEqual(code, 1)
        self.assertIn("--tools-k needs an integer", err)

    def test_tools_k_zero_is_the_documented_default_not_an_error(self):
        self.assertEqual(self._resolve("--tools-k", "0")["k"], 5)

    def test_valid_k_is_honoured(self):
        payload = self._resolve("--k", "2")
        self.assertEqual(payload["k"], 2)
        self.assertTrue(payload["shortlist"])
        self.assertLessEqual(len(payload["shortlist"]), 2)

    def test_k_defaults_when_absent(self):
        self.assertEqual(self._resolve()["k"], 5)


if __name__ == "__main__":
    unittest.main()
