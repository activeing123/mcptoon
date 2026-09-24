"""Tests for `mcptoon skills search` — searching skills.sh (the open skills registry).

Design under test: skills.sh exposes a live *search* API (``/api/search?q=``) but no
enumerable listing, so ``search`` reaches it by keyword and, when the network is down,
falls back to the offline BM25 index instead of pretending nothing matched. The payload
shape asserted here was captured from the real endpoint on 2026-09-24.

Offline: ``mcptoon.installer._fetch_json`` is patched.
"""
import os
import sys
import unittest
from unittest.mock import patch

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon import skills  # noqa: E402

# ── real payload shape (captured 2026-09-24) ──
SKILLS_SH_PAYLOAD = {
    "query": "test", "searchType": "fuzzy", "searchVersion": "algolia",
    "skills": [
        {"id": "obra/superpowers/test-driven-development", "source": "obra/superpowers",
         "skillId": "test-driven-development", "name": "test-driven-development",
         "installs": 235041},
        {"id": "addyosmani/agent-skills/test-driven-development",
         "source": "addyosmani/agent-skills", "skillId": "test-driven-development",
         "name": "test-driven-development", "installs": 40070},
    ],
}


class TestSkillsShClient(unittest.TestCase):
    def test_parses_the_real_payload(self):
        with patch("mcptoon.installer._fetch_json", return_value=SKILLS_SH_PAYLOAD):
            rows = skills._search_skills_sh("test", limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "obra/superpowers/test-driven-development")
        self.assertEqual(rows[0]["source"], "obra/superpowers")
        self.assertEqual(rows[0]["installs"], 235041)

    def test_respects_limit(self):
        with patch("mcptoon.installer._fetch_json", return_value=SKILLS_SH_PAYLOAD):
            rows = skills._search_skills_sh("test", limit=1)
        self.assertEqual(len(rows), 1)

    def test_quotes_the_query_into_the_url(self):
        seen = {}

        def fake_fetch(url, timeout=10):
            seen["url"] = url
            return {"skills": []}

        with patch("mcptoon.installer._fetch_json", fake_fetch):
            skills._search_skills_sh("code review & test", limit=5)
        self.assertIn("q=code%20review%20%26%20test", seen["url"])

    def test_empty_skills_list_is_not_an_error(self):
        with patch("mcptoon.installer._fetch_json", return_value={"skills": []}):
            rows = skills._search_skills_sh("zzz", limit=10)
        self.assertEqual(rows, [])


class TestSearchSkillsWithFallback(unittest.TestCase):
    def test_online_returns_skills_sh_source(self):
        with patch("mcptoon.installer._fetch_json", return_value=SKILLS_SH_PAYLOAD):
            rows, source = skills.search_skills("test", limit=10)
        self.assertEqual(source, "skills.sh")
        self.assertEqual(len(rows), 2)

    def test_offline_falls_back_and_says_so(self):
        with patch("mcptoon.installer._fetch_json", side_effect=OSError("no net")):
            rows, source = skills.search_skills("test", limit=10, index=None)
        self.assertEqual(source, "offline")
        self.assertEqual(rows, [])

    def test_offline_uses_the_local_index_when_given_one(self):
        index = {"skills": [
            {"slug": "pdf-tools", "desc": "work with pdf files",
             "triggers": ["pdf"], "alias_of": None, "body_triggers": []},
            {"slug": "unrelated", "desc": "something else entirely",
             "triggers": ["zebra"], "alias_of": None, "body_triggers": []},
        ]}
        with patch("mcptoon.installer._fetch_json", side_effect=OSError("no net")):
            rows, source = skills.search_skills("pdf", limit=5, index=index)
        self.assertEqual(source, "offline")
        self.assertTrue(rows, "offline search should still return local matches")
        self.assertEqual(rows[0]["id"], "pdf-tools")


class TestCliSearch(unittest.TestCase):
    def _run(self, argv):
        from contextlib import redirect_stdout
        from io import StringIO
        buf = StringIO()
        with redirect_stdout(buf):
            skills._cmd_skills(argv, "text")
        return buf.getvalue()

    def test_cli_prints_remote_results(self):
        with patch("mcptoon.skills.search_skills",
                   return_value=([{"id": "obra/superpowers/pdf-tools", "name": "pdf-tools",
                                   "source": "obra/superpowers", "installs": 200363}],
                                 "skills.sh")):
            out = self._run(["search", "pdf"])
        self.assertIn("obra/superpowers/pdf-tools", out)
        self.assertIn("200,363", out)
        self.assertIn("skills.sh", out)

    def test_cli_offline_message(self):
        with patch("mcptoon.skills.search_skills", return_value=([], "offline")):
            out = self._run(["search", "pdf"])
        self.assertIn("offline", out.lower())

    def test_cli_needs_a_query(self):
        with self.assertRaises(SystemExit):
            self._run(["search"])


if __name__ == "__main__":
    unittest.main()
