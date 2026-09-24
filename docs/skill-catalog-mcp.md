# Reaching the skill catalog over MCP

`mcptoon skills` has always been a CLI. That was fine while the skill catalog was
something a human ran by hand, but it left a gap for agents: an agent connected to
`mcptoon serve` could see every *tool* the gateway proxied and none of the *skills*
it manages. Resolving a skill meant shelling out to a subprocess, which not every
agent host allows and which duplicates work the gateway had already done.

Two first-party tools close that gap. They are published by `serve` like the other
`mcptoon_*` tools, need no upstream servers, and are read-only.

| Tool | Answers |
|---|---|
| `mcptoon_skills` | "What skills exist?" — the catalog, one `slug` + one-line description per skill. |
| `mcptoon_resolve_skills` | "Which skill fits this task?" — the best matches for a task, best first. |

## Try it

```jsonc
// tools/call
{"name": "mcptoon_resolve_skills", "arguments": {"task": "把视频里的人声和背景音乐分开", "k": 5}}
```

```jsonc
// result (abridged)
{"query": "把视频里的人声和背景音乐分开", "k": 5,
 "shortlist": [{"slug": "…", "score": 56.57, "desc": "…"}, …]}
```

`mcptoon_skills` takes an optional `include_aliases` (default `false`, one row per
real skill). `mcptoon_resolve_skills` takes `task` and an optional `k` (default 5).

## Wiring it into an agent

The tools ride the connection the agent already has, so there is nothing to add:

```jsonc
{"mcpServers": {"mcptoon": {"command": "mcptoon", "args": ["serve"]}}}
```

An agent that sees the gateway's tool list sees the two skill tools with it. Two
properties make them safe to publish unconditionally: they are read-only, and they
never shadow an upstream tool (on a name collision the upstream definition wins —
see `native_names` in `src/mcptoon/native_tools.py`).

### When you would rather not mount MCP

If the host has no MCP, the catalog is still reachable two ways, and the same
ranking backs both:

- **Pointer line** — `mcptoon skills manifest` prints a one-line entry to keep in
  context, so the agent always knows the catalog exists.
- **CLI** — `mcptoon skills resolve "<task>" --k 5`, the command these tools mirror.

For a host that reads a global instruction file (Codex, DSH, anything AGENTS.md-
aware), `mcptoon sync --self` writes that pointer into it for you:

```markdown
## Skill catalog (mcptoon)

This machine has a skill catalog managed by mcptoon. Before acting on a task,
find the right skill first — do not guess, and do not read the whole catalog:

    mcptoon skills resolve "<the user request>" --k 5
```

The write is idempotent (heading-anchored, so a second sync appends nothing) and
reversible: `mcptoon off` removes exactly that block and leaves the rest of the
file byte-for-byte. `~/.codex/AGENTS.md` is the target — the global file, not the
current directory, which is where the old writer put it.

## Nothing to configure, nothing to index

Two steps used to stand between "pip install" and "the catalog works":

1. **`mcptoon skills index`** — `resolve` refused to answer until you ran it, and
   a skill added afterwards stayed invisible until you ran it again. The index now
   builds itself on first use and rebuilds when the catalog on disk no longer
   matches the signature it was built from (path, size and mtime of every
   manifest, so an add, an edit and a delete are all seen). The probe is a
   stat-only walk — 0.25s cold, 0.03s warm for this machine's 1,217 manifests —
   so it rides every resolve without a perceptible cost. `list` and `stats` stay
   strict readers and never build an index as a side effect of being asked a
   question. `mcptoon quickstart` builds it too, at the end of onboarding.
2. **Finding the host** — `sync` now detects Claude Code (`~/.claude.json`) and
   Codex (`~/.codex/AGENTS.md`) alongside the five it already knew, so
   `mcptoon quickstart` registers the gateway wherever it will be read.

## The handshake carries the pointer

Tools alone are not enough. `mcptoon_resolve_skills` shows up in `tools/list` like
any other tool, but a list of tools says nothing about *when* to reach for one — an
agent that never sees a skill list in its prompt has no reason to call a resolver.

MCP has an official channel for exactly this: the `instructions` field of the
`initialize` result, which a client hands to the model as part of its context, with
no tool call and no system-prompt edit. mcptoon already used it (to ask for the
savings line); it now opens by naming the resolver:

> Before acting on a task, call `mcptoon_resolve_skills` with the user's request and
> read only the SKILL.md files it returns; never load the whole catalog.

The pointer names the *tool*, not the shell command, because the reader always has
this gateway mounted and may have no shell. The rest of the paragraph was tightened
in the same edit, so the block is 314 tokens — the pointer was paid for out of prose,
not added on top.

**Verified, not assumed.** An agent connected to the gateway was asked to name the
skill it would use for a task, with no tool named in the prompt. It called
`mcptoon_resolve_skills` on its own and quoted the returned shortlist. Two honest
caveats: the channel only works in clients that honour `instructions` (Claude Code
does; **DSH mounts no MCP, so it is unaffected**), and the field is sent once at
connect time, so an edit needs a reconnect — unlike a system-prompt pointer, which
survives restarts on its own.

## One ranking, two surfaces

`mcptoon_skills` and `mcptoon skills list` must agree, and so must
`mcptoon_resolve_skills` and `mcptoon skills resolve`. Rather than re-implement the
projection per surface — two rankings that drift are how a tool loses the argument
that its answer is the catalog's answer — both call the same two functions in
`src/mcptoon/skills.py`:

- `catalog_rows(index, include_aliases=…)` — the list projection
- `resolve_shortlist(query, k, index=…)` — the BM25 ranking

`resolve_shortlist` records the same usage counts the CLI records, so
`mcptoon skills list --usage` counts MCP resolutions too. Neither function needs a
network, an API key, or a subprocess: ranking is offline BM25 over the on-disk index.

## What it costs

Measured on the machine that wrote this page, with `tiktoken` (`cl100k_base`):

| Payload | Cost |
|---|---|
| The two new tool definitions, in `tools/list` | 583 tokens, paid once per session |
| `mcptoon_skills`, full catalog (391 skills) | 23,867 tokens, only if you ask for it |
| `mcptoon_resolve_skills`, `k=5` | ~1,100 tokens (85% of it the candidate descriptions) |

The descriptions dominate the `resolve` payload and are kept whole on purpose: a
truncated description is the half-claim that costs an agent a wrong pick, and a
caller who wants only the names can read `mcptoon skills manifest` (39 tokens)
instead. The point of the shortlist is that the agent loads *one* skill, not that
the shortlist itself is small.

## Tests

Nine tests in `tests/test_native_tools.py` cover the two tools: the projections
match the CLI byte-for-byte, usage is recorded, an empty or missing index is a
result rather than a crash, a bad `k` falls back instead of raising, and the
descriptions stay inside the budget `schema_simplifier` enforces on every other
tool. Run `python -m pytest tests/`.
