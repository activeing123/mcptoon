"""Registry-source smoke test: the URLs in ``installer.py`` must be alive.

Why this exists
---------------
``mcptoon install <name>`` once worked and then silently stopped: the Smithery host
moved (``smithery.ai/api`` -> ``registry.smithery.ai``) and the official registry
hostname stopped resolving, while a bare ``except Exception: return []`` made a dead
registry look exactly like "no results". Nobody noticed for months.

A unit test cannot catch that class of rot — it mocks the network, so it stays green
while production is broken. This script makes a real request to each configured source
and fails loudly. It is *not* part of ``pytest tests/`` (it needs the network, which
CI for a zero-dependency stdlib project should not require for the normal suite); run
it in a workflow that has network access, or by hand before a release.

Usage:
    python scripts/check_registry_sources.py          # exit 0 = all sources alive
    python scripts/check_registry_sources.py --json    # machine-readable
"""
import json
import os
import sys
import urllib.request

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from mcptoon.installer import (  # noqa: E402
    MCP_REGISTRY_URL,
    SMITHERY_API_URL,
    RegistryError,
    search_registry,
)

TIMEOUT = 20


def _get(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "mcptoon-registry-check/1.0",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, r.read(2048)


def main():
    as_json = "--json" in sys.argv
    checks = []

    # 1. Each source answers with JSON, not a 404 / NXDOMAIN.
    for label, url in (
        ("smithery", f"{SMITHERY_API_URL}/servers?q=github&pageSize=1"),
        ("registry", f"{MCP_REGISTRY_URL}/servers?search=github&limit=1"),
    ):
        try:
            status, body = _get(url)
            ok = status == 200 and body.lstrip()[:1] in (b"{", b"[")
            checks.append({"source": label, "ok": ok, "status": status, "url": url,
                           "detail": "" if ok else "non-JSON body"})
        except Exception as e:
            checks.append({"source": label, "ok": False, "status": None, "url": url,
                           "detail": f"{type(e).__name__}: {str(e)[:120]}"})

    # 2. The end-to-end path returns real results for a term that must exist.
    try:
        results = search_registry("github", limit=5)
        ok = len(results) > 0
        checks.append({"source": "search_registry('github')", "ok": ok, "status": None,
                       "url": "", "detail": f"{len(results)} results"})
    except RegistryError as e:
        checks.append({"source": "search_registry('github')", "ok": False, "status": None,
                       "url": "", "detail": str(e)[:160]})

    # 3. A nonsense term returns [] and does NOT raise — "no matches" must stay
    #    distinguishable from "network down".
    try:
        empty = search_registry("zzzz_no_such_server_zzzz", limit=5)
        ok = empty == []
        checks.append({"source": "empty-query semantics", "ok": ok, "status": None,
                       "url": "", "detail": f"{len(empty)} results (expected 0)"})
    except Exception as e:
        checks.append({"source": "empty-query semantics", "ok": False, "status": None,
                       "url": "", "detail": f"raised {type(e).__name__}: {str(e)[:120]}"})

    failed = [c for c in checks if not c["ok"]]

    if as_json:
        print(json.dumps({"ok": not failed, "checks": checks}, indent=2, ensure_ascii=False))
    else:
        for c in checks:
            print(f"  [{'OK' if c['ok'] else 'FAIL'}] {c['source']}"
                  + (f"  {c['detail']}" if c["detail"] else ""))
        print()
        if failed:
            print(f"  ❌ {len(failed)} registry check(s) failed — "
                  f"`mcptoon install <name>` is broken. Fix the URL constants in "
                  f"src/mcptoon/installer.py.")
        else:
            print("  ✅ All registry sources alive.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
