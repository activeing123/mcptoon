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

"""Verify mcptoon imports only Python stdlib modules (zero dependencies).

AST-based, so it is immune to indentation, line continuations and import
styles that defeat grep-based checks. Relative imports (from . import x)
are always allowed; anything outside sys.stdlib_module_names fails.

Usage: python scripts/check_zero_deps.py [root]
      root defaults to src/mcptoon
"""
import ast
import sys
from pathlib import Path


def check(root: Path) -> list[str]:
    stdlib = set(sys.stdlib_module_names)
    bad = []
    files = sorted(root.rglob("*.py"))
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if _optional_guarded(node, parents):
                continue    # try/except ImportError pattern = optional enhancement
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib:
                        bad.append(f"{p}:{node.lineno}: import {alias.name}")
            else:
                if node.level > 0:          # relative import — always ours
                    continue
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib:
                    bad.append(f"{p}:{node.lineno}: from {node.module} import ...")
    return bad


def _optional_guarded(node, parents) -> bool:
    """True if the import sits inside a try/except catching ImportError-ish."""
    anc = parents.get(node)
    while anc is not None:
        if isinstance(anc, ast.Try):
            for handler in anc.handlers:
                t = handler.type
                names = []
                if isinstance(t, ast.Name):
                    names = [t.id]
                elif isinstance(t, ast.Tuple):
                    names = [e.id for e in t.elts if isinstance(e, ast.Name)]
                if any(n in ("ImportError", "ModuleNotFoundError", "Exception")
                       for n in names):
                    return True
        anc = parents.get(anc)
    return False


def main(argv):
    root = Path(argv[0]) if argv else Path("src/mcptoon")
    bad = check(root)
    if bad:
        print("THIRD-PARTY IMPORTS FOUND:")
        for line in bad:
            print(f"  {line}")
        return 1
    n = sum(1 for _ in root.rglob("*.py"))
    print(f"Zero third-party dependencies confirmed ({n} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
