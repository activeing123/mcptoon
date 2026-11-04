# Copyright 2025-2026 activeing123
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

"""ArgParserFactory — per-command argparse parsing.

Verifies that `ArgParserFactory` in `src/mcptoon/arg_parser_factory.py` produces
order-insensitive flag parsing, honors `allow_abbrev=False` and `add_help=False`,
and integrates cleanly with the shared output flags.
"""

from __future__ import annotations

import unittest

from mcptoon.arg_parser_factory import ArgParserFactory

PAYLOAD = '{"x": 1}'


class TestArgParserFactory(unittest.TestCase):
    def setUp(self):
        self.factory = ArgParserFactory()

    def test_parse_cmd_args_returns_namespace_and_extras(self):
        ns, extras = self.factory.parse_cmd_args("list", ["--json"])
        self.assertTrue(ns.json)
        self.assertEqual(extras, [])

    def test_parse_cmd_args_passes_positionals_through(self):
        ns, extras = self.factory.parse_cmd_args("call", ["srv", "tool", PAYLOAD])
        self.assertEqual(extras, ["srv", "tool", PAYLOAD])

    def test_parse_cmd_args_uses_intermixed_parsing(self):
        # Positionals and flags intermixed — order-insensitive.
        ns, extras = self.factory.parse_cmd_args(
            "call", ["srv", "tool", PAYLOAD, "--json"]
        )
        self.assertTrue(ns.json)
        self.assertEqual(extras, ["srv", "tool", PAYLOAD])

    def test_parse_cmd_args_flags_after_positionals(self):
        ns, extras = self.factory.parse_cmd_args(
            "call", ["--json", "srv", "tool", PAYLOAD]
        )
        self.assertTrue(ns.json)
        self.assertEqual(extras, ["srv", "tool", PAYLOAD])

    def test_head_value_syntax(self):
        ns, _ = self.factory.parse_cmd_args("call", ["--head", "5"])
        self.assertEqual(ns.head, "5")
        ns, _ = self.factory.parse_cmd_args("call", ["--head=5"])
        self.assertEqual(ns.head, "5")

    def test_format_flag_accepts_value(self):
        ns, _ = self.factory.parse_cmd_args("list", ["--format", "toon"])
        self.assertEqual(ns.format, "toon")

    def test_transport_flag_accepts_value(self):
        ns, _ = self.factory.parse_cmd_args("list", ["--transport", "http"])
        self.assertEqual(ns.transport, "http")

    def test_unknown_flag_passes_through(self):
        # The factory is permissive: unknowns land in extras and the command
        # handler decides. Strict rejection is the global pre-pass's job.
        ns, extras = self.factory.parse_cmd_args("list", ["--totally-unknown", "srv"])
        self.assertFalse(ns.json)
        self.assertEqual(extras, ["--totally-unknown", "srv"])

    def test_allow_abbrev_false_prevents_partial_matches(self):
        parser = self.factory.create_parser()
        self.assertFalse(parser.allow_abbrev)
        # `--jsons` is not a registered flag; with allow_abbrev=False it must
        # land in extras rather than being silently matched.
        ns, extras = self.factory.parse_cmd_args("list", ["--jsons"])
        self.assertFalse(ns.json)
        self.assertEqual(extras, ["--jsons"])

    def test_add_help_false_prevents_default_help(self):
        parser = self.factory.create_parser()
        self.assertFalse(parser.add_help)
        # `-h` is not intercepted by argparse, so it passes through as an extra.
        ns, extras = self.factory.parse_cmd_args("list", ["-h"])
        self.assertEqual(extras, ["-h"])

    def test_create_parser_takes_custom_prog_and_description(self):
        parser = self.factory.create_parser(prog="mcptoon call", description="call a tool")
        self.assertEqual(parser.prog, "mcptoon call")
        self.assertEqual(parser.description, "call a tool")

    def test_doctor_json_flag_is_consumed_by_factory(self):
        # `mcptoon doctor --json` must be parsed by the factory, not the
        # global pre-pass, so the flag reaches `_cmd_doctor` as `json_mode`.
        ns, extras = self.factory.parse_cmd_args("doctor", ["--json"])
        self.assertTrue(ns.json)
        self.assertEqual(extras, [])

    def test_doctor_without_json_flag(self):
        ns, extras = self.factory.parse_cmd_args("doctor", [])
        self.assertFalse(ns.json)
        self.assertEqual(extras, [])

    def test_doctor_json_flag_position_independent(self):
        # Shared flags must work regardless of position relative to positionals.
        ns, extras = self.factory.parse_cmd_args("doctor", ["--json"])
        self.assertTrue(ns.json)
        ns, extras = self.factory.parse_cmd_args("doctor", ["--json", "srv"])
        self.assertTrue(ns.json)
        self.assertEqual(extras, ["srv"])


if __name__ == "__main__":
    unittest.main()

