"""End-to-end: `--format smart` compresses a tool result and stays reversible.

This is the test that matters for the feature's whole premise: a compressed
result must carry a handle, and ``mcptoon_retrieve`` must give back exactly what
was there before. If this passes, compression is lazy loading; if it fails,
compression is data loss.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from mcptoon import ccr, config as cfg, native_tools, output, serve


def search_rows(n=25):
    return [
        {
            "path": f"src/module_{i}/handler.py",
            "line": 100 + i,
            "score": round(0.99 - i * 0.01, 3),
            "snippet": "def handle_request(self, req):  # a long context line " * 6,
            "matched_terms": ["request", "handler"],
            "language": "python",
            "is_vendor": False,
            "extra": None,
        }
        for i in range(n)
    ]


class EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(
            os.environ,
            {"MCPTOON_CCR_DIR": self._tmp.name,
             "MCPTOON_COMPRESSION_FILE": os.path.join(self._tmp.name, "compression.json")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class TestSmartFormat(EnvIsolated):
    def test_render_smart_does_not_compress(self):
        """`output.render` is not a compression entry point any more.

        It has no store context to key a retrieve handle on, so it cannot honour the
        contract that makes compression safe — that whatever it hides can be fetched
        back. It used to compress anyway and append an "original not stored"
        admission: honest about the loss, but still a loss, and a *second* entry
        point next to `compressor.compress_with_ccr`. Two entry points is what let
        the bug in (this one discarded the stats and rendered a crushed payload with
        no handle and no notice, on the reachable `mcptoon install … --smart` path).
        """
        rows = search_rows()
        plain = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        smart = output.render(rows, fmt="smart")
        self.assertEqual(smart, plain)
        self.assertEqual(len(json.loads(smart)), len(rows))
        self.assertNotIn("nothing to retrieve", smart)
        self.assertNotIn("mcptoon_retrieve", smart)

    def test_render_smart_keeps_a_payload_compression_would_have_cut(self):
        payload = [{"id": i, "image": "A" * 400} for i in range(3)]
        rendered = json.loads(output.render(payload, fmt="smart"))
        self.assertEqual(rendered, payload)

    def test_smart_is_a_valid_policy(self):
        self.assertIn("smart", cfg.VALID_POLICIES)
        self.assertTrue(cfg.set_compression_policy("fs", "search", "smart"))
        self.assertEqual(cfg.get_compression_policy("fs", "search"), "smart")


class TestBridgeSmart(EnvIsolated):
    def _bridge(self, fmt="smart"):
        bridge = object.__new__(serve.MCPServerBridge)
        bridge._output_format = fmt
        return bridge

    def test_smart_compress_returns_text_with_handle(self):
        rows = search_rows()
        out = self._bridge()._compress_result(rows, "fs", "search")
        self.assertIsInstance(out, str)
        self.assertIn("mcptoon_retrieve handle=", out)
        handle = out.rsplit("handle=", 1)[1].rstrip("]").strip()
        self.assertEqual(ccr.retrieve(handle), rows)

    def test_roundtrip_via_native_retrieve_tool(self):
        rows = search_rows()
        out = self._bridge()._compress_result(rows, "fs", "search")
        handle = out.rsplit("handle=", 1)[1].rstrip("]").strip()
        result = native_tools.call_native(
            "mcptoon_retrieve", {"handle": handle}, {"tool_index": {}}
        )
        payload = json.loads(result["content"][0]["text"])
        self.assertTrue(payload["found"])
        self.assertEqual(payload["original"], rows)

    def test_uncompressible_result_passes_through(self):
        obj = {"ok": True}
        self.assertEqual(self._bridge()._compress_result(obj, "s", "t"), obj)

    def test_retrieve_unknown_handle_is_not_an_error(self):
        result = native_tools.call_native(
            "mcptoon_retrieve", {"handle": "deadbeef0000"}, {"tool_index": {}}
        )
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(payload["found"])
        self.assertFalse(result["isError"])


class TestCliSmartPath(EnvIsolated):
    def test_cli_smart_prints_compressed_with_handle(self):
        import io
        from contextlib import redirect_stdout
        from mcptoon import cli
        rows = search_rows()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._render_result(rows, "smart", 0, 0, True, False,
                               server="fs", tool="search")
        out = buf.getvalue()
        self.assertIn("mcptoon_retrieve handle=", out)
        handle = out.rsplit("handle=", 1)[1].strip().rstrip("]")
        self.assertEqual(ccr.retrieve(handle), rows)

    def test_cli_smart_passthrough_when_nothing_to_crush(self):
        import io
        from contextlib import redirect_stdout
        from mcptoon import cli
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._render_result({"ok": True}, "smart", 0, 0, True, False,
                               server="s", tool="t")
        self.assertIn("ok", buf.getvalue())

    def test_a_real_compression_marks_the_run_for_the_footer(self):
        """The footer's third line changes when *this process* compressed
        something. The CLI must reset that flag at the top of every command (each
        command is its own process, but the test process is not), and a compressed
        render must set it."""
        import io
        from contextlib import redirect_stdout
        from mcptoon import cli, compressor

        compressor.reset_compressed_this_run()
        self.assertFalse(compressor.compressed_this_run())
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._render_result(search_rows(), "smart", 0, 0, True, False,
                               server="fs", tool="search")
        self.assertTrue(compressor.compressed_this_run(),
                        "a compressed render must mark the run")

    def test_a_passthrough_render_does_not_mark_the_run(self):
        import io
        from contextlib import redirect_stdout
        from mcptoon import cli, compressor

        compressor.reset_compressed_this_run()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._render_result({"ok": True}, "smart", 0, 0, True, False,
                               server="s", tool="t")
        self.assertFalse(compressor.compressed_this_run(),
                         "nothing compressed -> the hint must not fire")


class TestInstallAndItWorks(EnvIsolated):
    """A fresh install compresses redundant results without anyone typing a flag."""

    def test_default_resolves_to_smart(self):
        # No settings file, no policies → the default must be smart.
        self.assertEqual(cfg.resolve_output_format("fs", "search", "auto"), "smart")

    def test_config_off_restores_passthrough(self):
        from unittest import mock
        with mock.patch.object(cfg, "get_setting",
                               lambda k: "off" if k == "compress" else "auto"):
            self.assertEqual(cfg.resolve_output_format("fs", "search", "auto"), "auto")
            self.assertFalse(cfg.auto_smart_enabled())

    def test_explicit_format_still_wins(self):
        self.assertEqual(cfg.resolve_output_format("fs", "search", "json"), "json")

    def test_policy_overrides_the_default(self):
        cfg.set_compression_policy("fs", "search", "raw")
        self.assertEqual(cfg.resolve_output_format("fs", "search", "auto"), "raw")

    def test_source_file_passes_through_untouched(self):
        src = "def f():\n    return 1\n" * 400
        self.assertEqual(self._bridge()._compress_result(src, "fs", "read"), src)

    def _bridge(self, fmt="auto"):
        bridge = object.__new__(serve.MCPServerBridge)
        bridge._output_format = fmt
        return bridge


class TestNativeToolRegistration(EnvIsolated):
    def test_retrieve_is_a_native_tool(self):
        self.assertIn("mcptoon_retrieve", native_tools.NATIVE_NAMES)
        self.assertTrue(native_tools.is_native("mcptoon_retrieve"))

    def test_retrieve_def_fits_description_budget(self):
        defn = next(d for d in native_tools.native_tools()
                    if d["name"] == "mcptoon_retrieve")
        self.assertLessEqual(len(defn["description"]), 360)
        self.assertIn("handle", defn["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
