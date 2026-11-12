# Copyright 2025 activeing123
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

import argparse


class ArgParserFactory:
    def __init__(self):
        self._shared_flags = [
            ("json", "store_true"),
            ("toon", "store_true"),
            ("slim", "store_true"),
            ("compact", "store_true"),
            ("mcptoon", "store_true"),
            # ("yaml", "store_true") was declared here for parity with the other
            # output formats, but no renderer ever existed and nothing read the
            # parsed attribute - a command that accepted `--yaml` printed human
            # text and exited 0 (issues #49/#50, found 2026-11-12). Dropped from
            # the baseline and from KNOWN_FLAGS until YAML output is implemented.
            ("format", "store"),
            ("head", "store"),
            ("max-chars", "store"),
            ("full", "store_true"),
            ("transport", "store"),
            ("stdin", "store_true"),
            ("fallback-json", "store_true"),
        ]

    def _add_shared_flags(self, parser: argparse.ArgumentParser):
        for flag, action in self._shared_flags:
            parser.add_argument(f"--{flag}", action=action)

    def create_parser(self, prog: str = "mcptoon", description: str = "") -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=prog,
            description=description,
            allow_abbrev=False,
            add_help=False,
        )
        self._add_shared_flags(parser)
        return parser

    def parse_cmd_args(self, command: str, args: list[str]) -> tuple[argparse.Namespace, list[str]]:
        parser = self.create_parser(prog=f"mcptoon {command}")
        # Using parse_known_args (not parse_intermixed_args) so that positionals
        # and opaque tails can be passed through to the command handler without
        # aborting on unrecognized tokens.
        return parser.parse_known_args(args)
