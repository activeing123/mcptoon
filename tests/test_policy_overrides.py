"""Per-tool compression policies (`mcptoon policy`) — the MuleSoft answer.

The bridge compresses every tool result with one bridge-wide format. That is
wrong for some tools: an image generator returning base64 must never be
compressed, while a chatty search tool might deserve forced TOON. Policies
give each server:tool its own answer, stored in ~/.mcptoon/compression.json
(same granularity as toggles, same env-isolation pattern as the rest of the
config layer).
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import output, serve

RESULT = {"content": [{"type": "text", "text": "hello"}], "meta": {"n": 1}}


class EnvIsolated(unittest.TestCase):
    """Redirect the policy file to a tmp dir so tests never touch ~/.mcptoon."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.policy_file = Path(self._tmp.name) / "compression.json"
        patcher = mock.patch.dict(
            os.environ, {"MCPTOON_COMPRESSION_FILE": str(self.policy_file)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class TestPolicyConfig(EnvIsolated):
    def test_set_get_clear_roundtrip(self):
        self.assertIsNone(cfg.get_compression_policy("img", "generate"))
        self.assertTrue(cfg.set_compression_policy("img", "generate", "raw"))
        self.assertEqual(cfg.get_compression_policy("img", "generate"), "raw")
        self.assertEqual(cfg.list_policies(), {"img:generate": "raw"})
        self.assertTrue(cfg.set_compression_policy("img", "generate", None))
        self.assertIsNone(cfg.get_compression_policy("img", "generate"))
        self.assertEqual(cfg.list_policies(), {})

    def test_unknown_policy_is_rejected_and_nothing_is_written(self):
        self.assertFalse(cfg.set_compression_policy("img", "generate", "zip"))
        self.assertEqual(cfg.list_policies(), {})

    def test_server_wildcard_and_exact_priority(self):
        cfg.set_compression_policy("img", "*", "raw")
        self.assertEqual(cfg.get_compression_policy("img", "generate"), "raw")
        self.assertIsNone(cfg.get_compression_policy("other", "generate"))
        # Exact key beats the wildcard.
        cfg.set_compression_policy("img", "generate", "toon")
        self.assertEqual(cfg.get_compression_policy("img", "generate"), "toon")
        self.assertEqual(
            cfg.get_compression_policy("img", "other_tool"), "raw"
        )

    def test_resolve_output_format_policy_wins_base(self):
        cfg.set_compression_policy("img", "generate", "raw")
        self.assertEqual(cfg.resolve_output_format("img", "generate", "auto"), "raw")
        self.assertEqual(cfg.resolve_output_format("img", "generate", "toon"), "raw")
        self.assertEqual(cfg.resolve_output_format("img", "other", "toon"), "toon")

    def test_auto_policy_means_default(self):
        cfg.set_compression_policy("img", "generate", "auto")
        self.assertIsNone(cfg.get_compression_policy("img", "generate"))
        self.assertEqual(
            cfg.resolve_output_format("img", "generate", "compact"), "compact"
        )


class TestPolicyCLI(EnvIsolated):
    def _run(self, *args):
        """Run `mcptoon <args>` in-process; return stdout (SystemExit 0 passes)."""
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["mcptoon", *args]), \
                redirect_stdout(buf):
            try:
                cli.main()
            except SystemExit as e:
                if e.code not in (0, None):
                    raise
        return buf.getvalue()

    def test_help_lists_the_policy_command(self):
        self.assertIn("mcptoon policy", self._run("--help"))

    def test_set_list_clear_flow(self):
        out = self._run("policy", "set", "img", "generate", "raw")
        self.assertIn("img:generate -> raw", out)
        self.assertIn("never compressed", out)

        out = self._run("policy")
        self.assertIn("img:generate", out)
        self.assertIn("-> raw", out)

        out = self._run("policy", "clear", "img", "generate")
        self.assertIn("default behaviour", out)
        self.assertIn("No compression policies", self._run("policy"))

    def test_set_server_wildcard(self):
        out = self._run("policy", "set", "img", "*", "toon")
        self.assertIn("img:* -> toon", out)

    def test_unknown_policy_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self._run("policy", "set", "img", "generate", "zip")
        self.assertEqual(cm.exception.code, 1)


class TestCallHonorsPolicy(EnvIsolated):
    def _call(self, fmt="auto"):
        buf = io.StringIO()
        with mock.patch.object(cli, "call_tool", return_value=RESULT), \
                redirect_stdout(buf):
            cli._cmd_call(["srv", "tool", "{}"], fmt=fmt, head_n=0,
                          max_chars=0, full=False)
        return buf.getvalue()

    def test_raw_policy_beats_auto_default(self):
        cfg.set_compression_policy("srv", "tool", "raw")
        self.assertEqual(
            self._call().strip(), json.dumps(RESULT, ensure_ascii=False)
        )

    def test_toon_policy_applies_without_a_flag(self):
        cfg.set_compression_policy("srv", "tool", "toon")
        expected = output.render(RESULT, fmt="toon", head_n=0, max_chars=0,
                                 full=False)
        self.assertEqual(self._call(), expected + "\n")

    def test_explicit_flag_beats_policy(self):
        cfg.set_compression_policy("srv", "tool", "toon")
        out = self._call(fmt="json")
        self.assertIn('"content"', out)
        self.assertNotEqual(out.strip(),
                            output.render(RESULT, fmt="toon", max_chars=0,
                                          full=True))

    def test_no_policy_keeps_default(self):
        before = self._call()
        self.assertEqual(before, self._call())  # deterministic, no policy file


class TestServeBridgePolicy(EnvIsolated):
    def _bridge(self, fmt="compact"):
        bridge = object.__new__(serve.MCPServerBridge)
        bridge._output_format = fmt
        return bridge

    def test_raw_policy_protects_result_from_bridge_compression(self):
        with mock.patch.object(cfg, "resolve_output_format",
                               return_value="raw"):
            out = self._bridge()._compress_result(RESULT, "img", "generate")
        self.assertIs(out, RESULT)

    def test_toon_policy_forces_bridge_compression(self):
        with mock.patch.object(cfg, "resolve_output_format",
                               return_value="toon"), \
                mock.patch.object(output, "render",
                                  return_value="TOONED") as render:
            out = self._bridge()._compress_result(RESULT, "db", "query")
        self.assertEqual(out, "TOONED")
        self.assertEqual(render.call_args.kwargs["fmt"], "toon")

    def test_no_policy_keeps_bridge_default(self):
        bridge = self._bridge("raw")
        with mock.patch.object(cfg, "resolve_output_format",
                               side_effect=lambda s, t, base: base):
            self.assertIs(bridge._compress_result(RESULT, "a", "b"), RESULT)


if __name__ == "__main__":
    unittest.main()
