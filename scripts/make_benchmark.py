"""Re-derive the TOON benchmark numbers from a corpus that lives in this script.

Why this file exists (2026-10-02). The headline "~34%" had been measured once, on
2026-08-18, by a script that no longer exists — `bench_tokens.py` emits the JSON /
SLIM / compact rows but never had a TOON row — and the corpus was never committed, so
the number could not be reproduced by anyone, including us. The encoder has since moved
(python-toon 0.1.1 -> 0.2.0) without it being re-measured.

Worse, the 34% was a *schema* number quoted as if it described *call results*, which is
what `--toon` actually encodes. The two payloads behave very differently: schemas save
11.8% on this corpus, call results 5.7% mixed but 1.8%-48.6% by shape.

DELIBERATELY DOES NOT OVERWRITE assets/benchmark_tiktoken.json. That file is a real
measurement from 2026-08-18 and it is still quoted across the README; replacing it with
numbers from a corpus we invented today would trade a real number for a reproducible
one, and would silently downgrade the flagship compact figure (99.2% -> 98.4% here,
a corpus artifact, not a regression). The historical corpus is lost, and losing a
measurement is not the same as faking its replacement.

So: this script writes two *new* files as a cross-check, and the gap between them and
the historical table is itself the finding worth reading.
  assets/benchmark_schemas_repro.json — same shape of table, this corpus
  assets/benchmark_results.json      — call results, which `--toon` really encodes

    python scripts/make_benchmark.py            # rewrite both assets
    python scripts/make_benchmark.py --print    # just show the numbers
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcptoon.bench_tokens import as_json_blob, as_slim  # noqa: E402
from mcptoon.output import compact  # noqa: E402
from mcptoon.toon_vendored import encode as toon_encode  # noqa: E402

OUT = ROOT / "assets" / "benchmark_schemas_repro.json"
SEED = 20261002

SERVERS = [
    "github", "gitlab", "slack", "jira", "confluence", "notion", "linear", "trello",
    "asana", "monday", "zoom", "google-drive", "dropbox", "onedrive", "sharepoint",
    "salesforce", "hubspot", "zendesk", "intercom", "freshdesk", "shopify", "stripe",
    "square", "quickbooks", "xero", "netsuite", "workday", "greenhouse", "lever",
    "okta", "auth0", "1password", "vault", "datadog", "grafana", "prometheus",
    "elasticsearch", "kibana", "cloudwatch", "pagerduty", "opsgenie", "terraform",
    "kubernetes", "docker", "ansible", "puppet", "chef", "nagios", "zabbix",
    "airtable", "postgres", "mongodb", "redis",
]
# 51 servers x 5 tools = 255 tools exactly, matching the historical table's headline.
SERVERS = SERVERS[:51]
# 50 servers x 5 tools + a 51st with 5 more = 255 tools, matching the historical table.
PER_SERVER = 5

VERBS = ["search", "create", "update", "delete", "list", "get", "set", "add", "remove",
         "fetch", "export", "import", "sync", "validate", "resolve", "archive", "restore",
         "publish", "revoke", "rotate"]
NOUNS = ["issue", "pull_request", "document", "page", "record", "channel", "user", "team",
         "project", "epic", "ticket", "ticket_comment", "attachment", "label", "milestone",
         "workflow", "repository", "branch", "commit", "release", "pipeline", "job",
         "credential", "policy", "audit_log", "webhook", "integration", "template",
         "dashboard", "alert", "metric", "dashboard_widget", "query", "table", "column"]

DESCRIPTIONS = [
    "Search the index. Returns up to 100 matches ordered by relevance.",
    "Create a new record. Requires an authenticated caller with write scope.",
    "Update an existing record. Only the fields present in the body are changed.",
    "Delete a record permanently. This cannot be undone.",
    "List records visible to the caller, following the standard pagination rules.",
    "Get a single record by identifier, including its revision history summary.",
    "Set one or more fields on a record, validating each against the server schema.",
    "Attach a file to a record, or replace an existing attachment.",
    "Return the audit trail for a record since a given timestamp.",
    "Export records as newline-delimited JSON, streaming to a temporary object store.",
]

PROP_TYPES = [
    ("string", 40), ("string", 12),          # plain + enum-ish share
    ("integer", 10), ("number", 4), ("boolean", 12),
    ("array<string>", 8), ("array<object>", 5), ("object", 9),
]
_POOL: list[str] = []
for _t, _w in PROP_TYPES:
    _POOL += [_t] * _w


def _prop(rng: random.Random, name: str) -> tuple[str, dict]:
    kind = rng.choice(_POOL)
    desc = rng.choice(DESCRIPTIONS)
    if kind == "string":
        return "string", {"type": "string", "description": desc}
    if kind == "integer":
        return "integer", {"type": "integer", "description": desc}
    if kind == "number":
        return "number", {"type": "number", "description": desc}
    if kind == "boolean":
        return "boolean", {"type": "boolean", "description": desc}
    if kind == "array<string>":
        return "array", {"type": "array", "description": desc,
                         "items": {"type": "string"}}
    if kind == "array<object>":
        return "array", {"type": "array", "description": desc,
                         "items": {"type": "object",
                                   "properties": {"key": {"type": "string"},
                                                  "value": {"type": "string"}}}}
    return "object", {"type": "object", "description": desc,
                      "properties": {"key": {"type": "string"},
                                     "value": {"type": "string"}},
                      "required": ["key"]}


def build_corpus(seed: int = SEED) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    tools: dict[str, list[dict]] = {}
    used: set[str] = set()
    for server in SERVERS:
        server_tools = []
        for _ in range(PER_SERVER):
            name = f"{rng.choice(VERBS)}_{rng.choice(NOUNS)}"
            while name in used:
                name = f"{rng.choice(VERBS)}_{rng.choice(NOUNS)}"
            used.add(name)
            props: dict[str, dict] = {}
            for i in range(rng.randint(3, 8)):
                pname, spec = _prop(rng, f"field{i}")
                while pname in props:
                    pname = f"{pname}_x"
                props[pname] = spec
            required = [p for p in props if rng.random() < 0.55]
            schema: dict = {"type": "object", "properties": props}
            if required:
                schema["required"] = required
            server_tools.append({
                "name": name,
                "description": rng.choice(DESCRIPTIONS),
                "inputSchema": schema,
            })
        tools[server] = server_tools
    return tools


def measure(tools: dict[str, list[dict]]) -> list[dict]:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    def n(text: str) -> int:
        return len(enc.encode(text))

    def payload(subset: dict[str, list[dict]]) -> list[dict]:
        """Same object list as_json_blob serializes — TOON gets the object, not its text.

        Encoding the JSON *string* instead of the object is a real mistake: the encoder
        would treat it as one escaped scalar, which is larger than the JSON and makes
        TOON look like a loss. It is the reason the first run of this script reported
        -7% "savings".
        """
        return [{"name": t.get("name"), "description": t.get("description", ""),
                 "inputSchema": t.get("inputSchema") or t.get("parameters") or {}}
                for server in subset.values() for t in server]

    rows = []
    for size in (5, 50, 255):
        subset: dict[str, list[dict]] = {}
        got = 0
        for server, ts in tools.items():
            if got >= size:
                break
            take = ts[: max(0, min(len(ts), size - got))]
            if take:
                subset[server] = take
                got += len(take)
        j = n(as_json_blob(subset))
        t = n(toon_encode(payload(subset)))
        s = n(as_slim(subset))
        c = n(compact({srv: [x["name"] for x in ts] for srv, ts in subset.items()}))
        rows.append({"tools": got, "json": j, "toon": t, "slim": s, "compact": c,
                     "toon_save": round((j - t) / j * 100, 1),
                     "slim_save": round((j - s) / j * 100, 1),
                     "compact_save": round((j - c) / j * 100, 1)})
    return rows


def build_result_corpus(seed: int = SEED) -> list:
    """Typical *call results* — the payload `--toon` actually encodes.

    Distinct from build_corpus() on purpose. Until 2026-10-02 the README and the
    --toon help text quoted one number (34%) that had been measured on tool SCHEMAS,
    while --toon is a flag on call RESULTS. Two different payloads, two different
    numbers — and the project's own code already said "~8-34%", which is what a
    results payload actually looks like: a result can be a flat record, a long list,
    or a blob, and the saving swings with the shape.
    """
    rng = random.Random(seed + 1)
    results: list = []
    for i in range(200):
        shape = rng.choice(["record", "list", "records_table", "blob"])
        if shape == "record":
            obj = {"id": rng.randint(1000, 9999), "name": f"item_{i}",
                   "status": rng.choice(["open", "closed", "pending"]),
                   "created_at": "2026-09-01T12:00:00Z",
                   "assignee": {"login": f"user{i % 40}", "id": i % 40}}
        elif shape == "list":
            obj = [f"value_{j}" for j in range(rng.randint(5, 20))]
        elif shape == "records_table":
            obj = [{"id": j, "name": f"row_{j}", "status": "open",
                    "score": rng.randint(0, 100)} for j in range(rng.randint(5, 15))]
        else:
            obj = {"content": "x" * rng.randint(200, 2000),
                   "mime_type": "text/plain", "truncated": False}
        results.append({"__shape__": shape, "payload": obj})
    return results


def measure_results(tagged: list) -> dict:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    payloads = [t["payload"] for t in tagged]
    js = json.dumps(payloads, ensure_ascii=False)
    ts = toon_encode(payloads)
    j, t = len(enc.encode(js)), len(enc.encode(ts))

    # Per-shape saving. Grouping by an explicit tag rather than re-guessing the shape
    # from the structure: the first version of this function did that and silently
    # dropped one of the four buckets, which is how a wrong number survives.
    per_shape: dict[str, float] = {}
    for shape in ("record", "list", "records_table", "blob"):
        sel = [t["payload"] for t in tagged if t["__shape__"] == shape]
        if not sel:
            continue
        a = len(enc.encode(json.dumps(sel, ensure_ascii=False)))
        b = len(enc.encode(toon_encode(sel)))
        if a:
            per_shape[shape] = round((a - b) / a * 100, 1)
    return {"results": len(payloads), "json": j, "toon": t,
            "toon_save": round((j - t) / j * 100, 1), "by_shape": per_shape,
            "note": "mixed corpus; the saving is shape-dependent, see by_shape"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", dest="show", action="store_true",
                    help="print the table without writing the asset")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)

    corpus = build_corpus(args.seed)
    n_tools = sum(len(v) for v in corpus.values())
    rows = measure(corpus)
    res = measure_results(build_result_corpus(args.seed))

    head = f"{'tools':>6} {'JSON':>9} {'TOON':>9} {'SLIM':>9} {'compact':>9}  " \
           f"{'toon':>6} {'slim':>6} {'cmpt':>6}"
    print(f"corpus: {len(corpus)} servers / {n_tools} tools (synthetic, seed={args.seed})")
    print(head)
    for r in rows:
        print(f"{r['tools']:>6} {r['json']:>9,} {r['toon']:>9,} {r['slim']:>9,} "
              f"{r['compact']:>9,}  {r['toon_save']:>5}% {r['slim_save']:>5}% "
              f"{r['compact_save']:>5}%")
    print(f"\ncall results ({res['results']} results, what --toon actually encodes): "
          f"JSON {res['json']:,} -> TOON {res['toon']:,}  = {res['toon_save']}%")
    for shape, pct in res["by_shape"].items():
        print(f"    {shape:<14} {pct}%")

    if not args.show:
        OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        (ROOT / "assets" / "benchmark_results.json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {OUT}")
        print(f"wrote {ROOT / 'assets' / 'benchmark_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())