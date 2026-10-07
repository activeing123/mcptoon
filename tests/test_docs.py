"""Tests for `mcptoon docs` — Markdown-tree indexing and file routing.

The design claim under test: an agent that would otherwise open a whole 42 KB
context file can instead be routed to the two or three files worth opening, and
the routing costs nothing (no LLM, no network, no embeddings).

The load-bearing test is `test_uninformative_slug_is_retrievable_by_heading` —
a document whose filename says nothing (`18-台账域.md` says little to a stranger)
must still be found from the words the author actually wrote inside it. That is
the whole point of deriving a description from headings.

Everything is hermetic: the docs index path and every root come from a temp
directory, so a run never touches `~/.mcptoon/docs-index.json` or a real docs
tree.
"""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import cli, docs


def write_doc(root: Path, rel: str, text: str) -> Path:
    """Create one Markdown fixture at ``root/rel``."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run_cli(*argv: str, env: dict | None = None) -> str:
    """Run the CLI in-process with the given env overlaid; return stdout."""
    buf = StringIO()
    with patch.dict(os.environ, env or {}), patch.object(sys, "argv", list(argv)), \
            redirect_stdout(buf):
        try:
            cli.main()
        except SystemExit:
            pass
    return buf.getvalue()


class _DocsCase(unittest.TestCase):
    """Base: a temp root plus a temp index path, both torn down after.

    The env patch is applied for the whole test, not just for CLI calls, so a
    helper that reaches for the on-disk index (`load_docs_index`) reads the temp
    one. Without this a test would read the developer's real
    ``~/.mcptoon/docs-index.json`` and pass or fail for reasons outside the test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "docs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.idx = Path(self._tmp.name) / "docs-index.json"
        self.env = {"MCPTOON_DOCS_INDEX": str(self.idx),
                    "MCPTOON_DOCS_ROOTS": str(self.root)}
        self._env_patch = patch.dict(os.environ, self.env)
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        self._tmp.cleanup()

    def build(self):
        return docs.build_docs_and_save([self.root])[0]


class DeriveDescriptionTests(_DocsCase):
    """The description is synthesised from headings, and says so."""

    def test_uninformative_slug_is_retrievable_by_heading(self):
        """A file named 18-台账域.md is found by the words inside it, not its name."""
        write_doc(self.root, "18-台账域.md",
                  "## 台账域（与用户定名）\n\n**台账系统 / Ledger OS**: 不弄乱、不弄错、不丢记忆。\n")
        write_doc(self.root, "07-写作域.md",
                  "## 写作域\n\n写文章三件套：标题、开头、结尾。\n")
        self.build()
        hits = docs.resolve_docs("台账系统 不弄乱", 3, index=docs.load_docs_index())
        self.assertTrue(hits, "a document with a real description must be routable")
        self.assertEqual(hits[0]["slug"], "18-台账域")

    def test_description_comes_from_h2_when_no_h1(self):
        """A chapter file opens at ## — requiring # would leave it nameless."""
        write_doc(self.root, "chapter.md", "## 部署流程\n\n先跑测试，再打 tag。\n")
        index = self.build()
        entry = index["docs"][0]
        self.assertIn("部署流程", entry["desc"])
        self.assertIn("先跑测试", entry["desc"])

    def test_heading_markup_is_stripped_from_description(self):
        """**bold** in a heading is noise to a tokenizer, so it is removed."""
        name, desc, _ = docs.derive_description("## **重点** 说明\n\n正文\n")
        self.assertNotIn("*", desc)
        self.assertIn("重点", desc)

    def test_headings_become_triggers(self):
        """Sub-headings are triggers — the author's own table of contents.

        The title is deliberately *not* a trigger: it is already carried by the
        entry's ``name`` and ``slug``, both of which the ranker indexes, so
        repeating it here would only inflate one document's term count.
        """
        name, _, triggers = docs.derive_description(
            "## 甲\n\n### 乙\n\n#### 丙\n\n正文\n")
        self.assertEqual(name, "甲")
        for want in ("乙", "丙"):
            self.assertIn(want, triggers)
        self.assertNotIn("甲", triggers)

    def test_derived_flag_is_recorded(self):
        """The entry admits its description is derived, not authored."""
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        self.assertTrue(index["docs"][0]["derived"])

    def test_empty_document_yields_empty_description(self):
        write_doc(self.root, "empty.md", "")
        name, desc, triggers = docs.derive_description("")
        self.assertEqual((name, desc, triggers), ("", "", []))


class ScanTests(_DocsCase):
    """What gets indexed, and what deliberately does not."""

    def test_indexes_markdown_recursively(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, "sub/b.md", "## 乙\n\n正文\n")
        index = self.build()
        slugs = {d["slug"] for d in index["docs"]}
        self.assertEqual(slugs, {"a", "sub-b"})

    def test_non_markdown_is_ignored(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, "notes.txt", "not markdown")
        write_doc(self.root, "data.json", "{}")
        index = self.build()
        self.assertEqual(len(index["docs"]), 1)

    def test_boilerplate_is_skipped(self):
        """LICENSE/CHANGELOG are packaging, not documentation."""
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, "LICENSE.md", "# MIT License\n\nPermission is hereby granted.\n")
        write_doc(self.root, "CHANGELOG.md", "# Changelog\n\n## 1.0\n\n- first\n")
        index = self.build()
        self.assertEqual({d["slug"] for d in index["docs"]}, {"a"})

    def test_dot_directories_are_skipped(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, ".git/x.md", "## 藏起来的\n\n正文\n")
        index = self.build()
        self.assertEqual({d["slug"] for d in index["docs"]}, {"a"})

    def test_duplicate_slug_warns(self):
        """Two files claiming one slug dilute retrieval — say so, do not hide it."""
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, "sub/a.md", "## 甲二\n\n正文\n")
        # Different slugs here (a vs sub-a), so instead force a real collision:
        write_doc(self.root, "sub-a.md", "## 甲三\n\n正文\n")
        index = self.build()
        codes = {w["code"] for w in index["warnings"]}
        self.assertIn("DOC_DUPLICATE", codes)

    def test_missing_root_warns_not_raises(self):
        index = docs.scan_docs([Path(self._tmp.name) / "nope"])
        self.assertEqual(index["docs"], [])
        self.assertEqual(index["warnings"][0]["code"], "ROOT_MISSING")

    def test_same_root_twice_is_deduped(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = docs.scan_docs([self.root, self.root])
        self.assertEqual(len(index["docs"]), 1)

    def test_path_is_recorded(self):
        """resolve must return a path — a slug alone sends the agent hunting."""
        p = write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        self.assertEqual(Path(index["docs"][0]["path"]), p)


class ResolveTests(_DocsCase):
    """Ranking, and the honest empty answers."""

    def test_returns_path_and_size_with_the_hit(self):
        p = write_doc(self.root, "a.md", "## 台账域\n\n台账系统说明。\n")
        self.build()
        hits = docs.resolve_docs("台账", 3, index=docs.load_docs_index())
        self.assertEqual(hits[0]["path"], str(p))
        self.assertGreater(hits[0]["size"], 0)

    def test_k_zero_returns_nothing(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        self.build()
        self.assertEqual(docs.resolve_docs("甲", 0, index=docs.load_docs_index()), [])

    def test_no_index_returns_empty_not_raise(self):
        """A machine with no docs must answer, not crash."""
        with patch.dict(os.environ, {"MCPTOON_DOCS_INDEX": str(self.idx)}):
            self.assertEqual(docs.resolve_docs("anything", 3), [])

    def test_unmatched_query_returns_empty(self):
        write_doc(self.root, "a.md", "## 台账域\n\n台账系统。\n")
        self.build()
        hits = docs.resolve_docs("zzzzz-nonexistent-token", 3,
                                 index=docs.load_docs_index())
        self.assertEqual(hits, [])

    def test_best_match_is_first(self):
        write_doc(self.root, "a.md", "## 台账域\n\n台账系统 / Ledger OS。\n")
        write_doc(self.root, "b.md", "## 写作域\n\n写文章三件套。\n")
        self.build()
        hits = docs.resolve_docs("台账系统", 5, index=docs.load_docs_index())
        self.assertEqual(hits[0]["slug"], "a")


class StalenessTests(_DocsCase):
    """The index knows when the disk has moved on."""

    def test_fresh_index_is_not_stale(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        self.assertFalse(docs.docs_are_stale(index))

    def test_edited_file_makes_index_stale(self):
        p = write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        p.write_text("## 甲\n\n改过了，变长了。\n", encoding="utf-8")
        os.utime(p, (1, 1))  # mtime is part of the signature; force a change
        self.assertTrue(docs.docs_are_stale(index))

    def test_added_file_makes_index_stale(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        write_doc(self.root, "b.md", "## 乙\n\n正文\n")
        self.assertTrue(docs.docs_are_stale(index))

    def test_deleted_file_makes_index_stale(self):
        p = write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        p.unlink()
        self.assertTrue(docs.docs_are_stale(index))

    def test_index_without_signature_reads_stale(self):
        self.assertTrue(docs.docs_are_stale({"docs": []}))

    def test_no_roots_is_not_stale(self):
        self.assertFalse(docs.docs_are_stale({"signature": "x", "roots": []}))


class LoadTests(_DocsCase):
    """The on-disk index: atomic write, tolerant read."""

    def test_build_writes_the_index_atomically(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        _, path = docs.build_docs_and_save([self.root])
        self.assertTrue(path.is_file())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"],
                         docs.DOCS_INDEX_VERSION)
        self.assertEqual(list(path.parent.glob("*.tmp.*")), [])

    def test_load_absent_is_empty(self):
        self.assertEqual(docs.load_docs_index(), {})

    def test_load_corrupt_is_empty(self):
        self.idx.write_text("{not json", encoding="utf-8")
        self.assertEqual(docs.load_docs_index(), {})

    def test_load_non_dict_is_empty(self):
        self.idx.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(docs.load_docs_index(), {})


class CliTests(_DocsCase):
    """The CLI surface: discoverable, and honest when there is nothing to show."""

    def test_help_lists_every_action(self):
        out = run_cli("mcptoon", "docs")
        for verb in ("index", "resolve", "list", "stats", "doctor", "clear"):
            self.assertIn(verb, out)

    def test_index_then_resolve_round_trip(self):
        write_doc(self.root, "18-台账域.md", "## 台账域\n\n台账系统说明。\n")
        out = run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        self.assertIn("indexed 1 document", out)
        out = run_cli("mcptoon", "docs", "resolve", "台账", env=self.env)
        self.assertIn("18-台账域", out)
        self.assertIn("18-台账域.md", out)  # the path is shown, not just the slug

    def test_index_json_is_machine_readable(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        out = run_cli("mcptoon", "docs", "index", str(self.root), "--json", env=self.env)
        payload = json.loads(out)
        self.assertEqual(payload["indexed"], 1)

    def test_resolve_json_carries_paths(self):
        write_doc(self.root, "a.md", "## 台账域\n\n台账系统。\n")
        run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        out = run_cli("mcptoon", "docs", "resolve", "台账", "--json", env=self.env)
        payload = json.loads(out)
        self.assertEqual(payload["hits"][0]["slug"], "a")
        self.assertTrue(payload["hits"][0]["path"])

    def test_resolve_without_index_exits_nonzero(self):
        buf = StringIO()
        with patch.dict(os.environ, self.env), \
                patch.object(sys, "argv", ["mcptoon", "docs", "resolve", "x"]), \
                redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("no docs index", buf.getvalue())

    def test_index_without_root_exits_nonzero(self):
        """No guessed default: say so rather than scan the cwd."""
        buf = StringIO()
        env = {"MCPTOON_DOCS_INDEX": str(self.idx), "MCPTOON_DOCS_ROOTS": ""}
        with patch.dict(os.environ, env), \
                patch.object(sys, "argv", ["mcptoon", "docs", "index"]), \
                redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("no docs roots", buf.getvalue())

    def test_unknown_action_exits_nonzero(self):
        buf = StringIO()
        with patch.dict(os.environ, self.env), \
                patch.object(sys, "argv", ["mcptoon", "docs", "bogus"]), \
                redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, 1)

    def test_doctor_reports_missing_file(self):
        p = write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        p.unlink()
        out = run_cli("mcptoon", "docs", "doctor", env=self.env)
        self.assertIn("no longer on disk", out)

    def test_doctor_passes_on_a_clean_index(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        out = run_cli("mcptoon", "docs", "doctor", env=self.env)
        self.assertIn("all checks passed", out)

    def test_stats_counts_documents(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        write_doc(self.root, "b.md", "## 乙\n\n正文\n")
        run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        out = run_cli("mcptoon", "docs", "stats", env=self.env)
        self.assertIn("documents   : 2", out)

    def test_clear_removes_the_index(self):
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        run_cli("mcptoon", "docs", "index", str(self.root), env=self.env)
        self.assertTrue(self.idx.is_file())
        out = run_cli("mcptoon", "docs", "clear", env=self.env)
        self.assertIn("removed", out)
        self.assertFalse(self.idx.is_file())

    def test_clear_on_absent_index_is_a_no_op(self):
        out = run_cli("mcptoon", "docs", "clear", env=self.env)
        self.assertIn("nothing to clear", out)

    def test_docs_appears_in_top_level_help(self):
        """A command nobody can discover may as well not exist."""
        buf = StringIO()
        with redirect_stdout(buf):
            cli._print_help()
        self.assertIn("mcptoon docs index", buf.getvalue())


class WiringTests(unittest.TestCase):
    """The dispatch and completion tables must both know the new verb."""

    def test_docs_is_in_the_dispatch_chain(self):
        source = (Path(__file__).resolve().parents[1]
                  / "src" / "mcptoon" / "cli.py").read_text(encoding="utf-8")
        self.assertIn('elif command == "docs":', source)

    def test_docs_is_offered_by_completion(self):
        self.assertIn("docs", cli._COMPLETION_COMMANDS)


class IsolationTests(_DocsCase):
    """The docs index must never be mistaken for the skill index."""

    def test_docs_index_path_differs_from_skills_index(self):
        from mcptoon import skills
        self.assertNotEqual(docs._docs_index_path(), skills._index_path())

    def test_docs_index_shape_is_not_a_skill_index(self):
        """A docs index carries `docs`, never `skills` — the two never merge."""
        write_doc(self.root, "a.md", "## 甲\n\n正文\n")
        index = self.build()
        self.assertIn("docs", index)
        self.assertNotIn("skills", index)


if __name__ == "__main__":
    unittest.main()
