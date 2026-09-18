"""Tests for `mcptoon skills` — skill-catalog indexing and compression-safe routing.

The design claim under test: a compressed catalog must not cost routing accuracy.
We keep the full catalog on disk and retrieve from it, instead of trimming what the
model sees. So the load-bearing test is `test_uninformative_name_is_retrievable_by_trigger`
— a skill whose slug says nothing must still be found from a natural request.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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


if __name__ == "__main__":
    unittest.main()
