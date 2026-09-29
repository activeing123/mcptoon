#!/usr/bin/env python3
"""Repository shim for ``python -m mcptoon.bench_tokens``.

The measurement itself lives in the package (``src/mcptoon/bench_tokens.py``) so a
``pip install mcptoon`` user can reproduce the README numbers without a clone. This
file stays for the muscle memory of anyone who has the repo open, and so old links
and docs that say ``scripts/bench_tokens.py`` keep working — it just delegates.

    mcptoon manifest                        # populate the schema cache
    python scripts/bench_tokens.py          # your own numbers (same as -m)
    python -m mcptoon.bench_tokens --json   # machine-readable
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcptoon.bench_tokens import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
