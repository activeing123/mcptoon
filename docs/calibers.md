# The four savings calibers — and which one each surface is allowed to quote

> Why this page exists: on 2026-09-26 a user said, in one breath, "I'm totally
> confused about what a user actually gets versus what we advertise." That
> confusion was not the user's fault. The repo was quoting **four different
> "savings" percentages**, all of them true, none of them labelled, on one
> machine. This page names them, measures them on the author's box, and says
> where each one may appear.

Every number below is a real `tiktoken cl100k_base` measurement on the author's
box (mcptoon 0.8.2), not a memory. The catalog there: **12 servers, 96 tools, 408
skills.**

---

## The four calibers

| # | Name | What is measured | On this box | Where it belongs |
|---|---|---|---|---|
| 1 | **Gateway** | full upstream schemas → what the agent *actually loads* under the default `compact` exposure (mcptoon's 8 meta-tools + the directive) | **21,074 → 2,291 = 89%** | The headline. What *installing mcptoon* buys. |
| 2 | **Slim-schema** | the same tools, descriptions written terser (`manifest --slim`) | **21,074 → 15,955 = 24%** | Secondary. Always named as the smaller claim. |
| 3 | **Name index** | full catalog dump → names only (`manifest`, the default tier) | **21,092 → 374 = 98%** | A per-command figure. Never the product headline. |
| 4 | **Synthetic bench** | a fixed 255-tool / 50-server sample recorded in `assets/benchmark_tiktoken.json` (the README table) | **71,929 → 581 = 99.2%** | Docs only, always labelled "synthetic sample". Note: `mcptoon bench` does **not** print this — it measures *your* catalog (caliber #1's inputs). |

**Why #1 and #2 differ by 3.6×.** #2 compares two ways of *describing the same
tools* — both descriptions are in context. #1 compares "all those descriptions in
context" against "almost none of them in context", because the gateway withholds
the upstream schemas entirely and hands the agent 8 meta-tools instead. The user's
question ("does it actually save?") is #1. #2 is a detail about one tier.

**Why #4 is not #1.** #4 is a lab sample. #1 is *your* catalog. They are not
supposed to match, and quoting #4 as if it were the user's number is the
"advertised ≠ actual" trap.

---

## What a new user actually sees, step by step

Reproduced in an isolated `HOME` so nothing real was touched.

**1. `pip install mcptoon && mcptoon status`** (first command, no servers yet)

```
  Found       no MCP servers yet
  In context  catalog not cached yet
  Next        mcptoon quickstart  find the servers already on this machine
  Undo        mcptoon off  unplug it from your agents
  Privacy     no daemon · no autostart · no upload
```

**2. After `mcptoon quickstart` discovers servers — the welcome card** (this is
the first *number* the user ever sees):

```
  本机已有    12 个服务器 · 96 个工具 · 408 个技能
  上下文本钱  21,074 → 2,291 tokens（网关省 89%；仅瘦身 schema 省 24%）
```

**3. The per-turn broadcast** (`mcptoon footer-facts`, and the tail of every
command). Three lines since 2026-09-26 — tools, skills, result compression — plus
the caveat. Every line is budgeted at **≤80 display columns** (CJK glyphs are
double-width), so nothing wraps on a normal terminal:

```
🎉 mcptoon: 工具 96→9（省 88%） · ≈省82M·4,407次 [tiktoken cl100k_base]
   技能 410 — 1,033,948→39（省 99.99%）· mcptoon report · /mcptoon 技能
   结果压缩（对话）— 已启用（自动）· 原文可 mcptoon_retrieve 取回
note: 12 个服务器里有 1 个还没缓存；数字可能滞后
```

The 2026-09-26 redesign (second pass) fixed a *size* defect the first three-line
version introduced: it packed the raw token pair, two percentages and the call
count onto line 1, which measured **166 display columns** and wrapped to three
terminal rows on every turn. The headline now carries one figure per unit —
reduction (`96→9`), rate (`省 88%`), and the **cumulative** estimate with the
running call count (`≈省82M·4,407次`) — and the figures that no longer fit moved to
line 2 or to `mcptoon report`:

* **`96→9`** (tools) — the reduction a user actually experiences.
* **the skills line** — the skills saving, the `mcptoon report` pointer, and the
  `/mcptoon` skill pointer (the single entry point for the raw token pair, the
  slim-schema percentage, the per-server split, and the way back). Omitted, never
  zeroed, when a machine has no skill catalog.
* **the compression line** — result compression, on by default since 2026-09-26.
  It always prints: "off" is the fact the reader needs when they have turned it
  off, and the default line says the originals are recoverable. When *this run*
  actually compressed something it changes to `本轮已压缩，失真问 /mcptoon 技能`.

**`≈省 82M`** is the only *estimate* on any surface: calls routed × the per-turn
saving, assuming every routed call stands in for a turn that would have carried
the full catalog. That makes it a **lower bound**, which is why it always carries
`≈`. The call count beside it (`4,407次`) is a real counter and the reason the
line moves turn over turn — a badge that never changes stops being read. The
estimate is labelled **累计** (cumulative), never 本轮 (this turn): `usage` counts
*calls*, not turns, so calls × per-turn rate is the only honest unit.

**4. `mcptoon status`** — both figures, labelled, adjacent:

```
  Tool definitions   : 21,074 → 2,291 tokens via the gateway (saved 89%)  [tiktoken cl100k_base]
                       (slim schemas alone: 15,955, 24%)
```

**5. `mcptoon stats`** — the same pair, plus the per-server split marked
`slim schemas only`.

So the answer to "what does it look like after install?" is: **the user sees the
gateway caliber (89%) as the headline, the slim-schema caliber (24%) named as the
smaller one, and a live call counter that moves.** That is the intended state.

---

## The advertisement, side by side

| Surface | Says | Caliber | Verdict |
|---|---|---|---|
| README line 11 | "saves 99.2% of tokens" | #4 (bench) | ⚠️ unlabelled in the sentence — the table below it now says "synthetic sample" |
| README comparison table | "581 tokens for 255 tools (−99.2%)" | #4 | ✅ that table's caption is `mcptoon bench`; labelled as a sample |
| README "three bills" | gateway 89% vs slim 24%, both named | #1 + #2 | ✅ fixed 2026-09-26 |
| README bench table | 71,929 → 581 | #4 | ✅ now says "synthetic sample … not your catalog" |
| welcome card | 21,074 → 2,291 (89%; 24%) | #1 + #2 | ✅ fixed 2026-09-26 |
| footer / broadcast | `96→9`, `省 88%`, `≈省 82M·4,407次`; skills `1,033,948→39（省 99.99%）`; compression state | #1 + skills + compression | ✅ fixed 2026-09-26 (≤80-col redesign; raw pair + slim % + per-turn moved to `report`) |
| `status` | 89% headline, 24% secondary | #1 + #2 | ✅ fixed 2026-09-26 |
| `stats` | 89.1% gateway, 24.3% slim, per-server "slim only" | #1 + #2 | ✅ fixed 2026-09-26 |
| skills claims | "926,232 tokens → 39 + 501" | skills-only | ✅ separate feature, separately measured |

**The one open item.** README line 11 still says "saves 99.2% of tokens" in the
hero sentence with no qualifier. Everything under it now explains that 99.2% is a
synthetic sample, but a reader who stops at line 11 takes away 99.2% as *their*
number. Recommendation: either qualify the sentence inline ("up to 99.2% on a
255-tool sample; `mcptoon status` shows yours") or lead with the live caliber.
Not changed here because line 11 is a headline decision for the maintainer, not a
mechanical fix.

---

## The rule (also in `docs/experience-checklist.md` §8)

- **The headline is the gateway caliber.** Anything that answers "how much does
  this save?" leads with it.
- **The slim-schema caliber is always named as the smaller, secondary claim.**
  Never stand it alone as "the" saving.
- **The synthetic bench is always labelled a sample.** Never present it as the
  user's catalog. It is the fixed 255-tool sample in `assets/benchmark_tiktoken.json`;
  `mcptoon bench` measures *your* catalog instead, so the two are different commands
  answering different questions.
- **One helper computes the gateway figure** (`footer.gateway_savings()`), so no
  two surfaces can round or baseline it differently.
- **`mcptoon report` is where every caliber is added up**, each on its own labelled
  row. It deliberately carries no "cumulative turns saved" figure: turns are not
  counted, and a number that needs an uncounted input would be a guess.

---

## Reproduce

```bash
mcptoon status            # your gateway + slim figures, labelled
mcptoon stats             # the same pair, plus per-server slim split
mcptoon report            # every caliber added up, one screen
mcptoon footer-facts      # the broadcast line, with its staleness note
mcptoon bench             # YOUR catalog: tools + skills, measured live
python scripts/bench_tokens.py   # the fixed 255-tool sample (needs tiktoken)
```
