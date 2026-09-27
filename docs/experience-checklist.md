# The experience contract

> What makes a command-line tool feel *considered* rather than *assembled* — and
> the specific rules this repo holds itself to. Read this before adding a message,
> a number, or a first-run path.

## Why this exists

On 2026-09-24 a user ran mcptoon and reported three things in one breath:

1. "the last line of the conversation is the same every time — it isn't computed live"
2. "opening the CLI shows no welcome or anything"
3. "what does it actually take to make a tool that feels good?"

The three complaints were one failure. The tool was **not treating its own words as
claims**: it recited a figure it had not re-measured, it stayed silent at the one
moment a new user was looking, and it had no rule that said either was wrong.

Fixing it was not a feature. It was making the tool keep its promises. This page is
the set of promises, so the next change does not quietly break them again.

## The rules

Each rule is stated as a promise, then as the question to ask of any new surface.

### 1. A message is either new, or it is silent

Say the same sentence twice and the reader stops reading it — including when the
reader is a model. Repetition reads as noise, never as presence.

*Ask:* if this prints on turn 1 and turn 2 unchanged, is that useful? If not, gate it
on a change.

*Where it lives:* `footer.changed()` compares the new line against the last one
remembered in `config.FOOTER_STATE_FILE`; `cli._emit_footer` and
`serve._stamp_footer` skip an unchanged line. `footer-facts` deliberately always
prints — it is an explicit ask, not ambient output.

*Gotcha:* compare the **figures**, not the whole block. The `note:` carries a
"catalog is N min old" age that ticks every minute; comparing the whole block
resurrects the line every minute.

### 2. Every number is recomputed live, or it carries its age

A figure with no timestamp is a claim the reader cannot check. Prefer a number that
moves with the machine; when it cannot move, label how stale it is.

*Ask:* where did this number come from, and when? If the answer is "it's a constant
of the catalog", say so.

*Where it lives:* the footer's catalog figures are static, so a **live** figure —
`calls_recorded`, the running total of calls routed — rides alongside them. Stale
or partial figures are disclosed by `footer.note()` ("N servers not cached yet",
"catalog N min old").

### 3. One-time messages say it once, and can be turned off

A first-run greeting is welcome. A greeting on every run is spam. Keep the marker in
a state file, and give the user a switch.

*Ask:* after the first run, does this still print? Can the user silence it?

*Where it lives:* `config.welcome_seen()` / `mark_welcome_seen()` (marker file) and
`mcptoon config set welcome off`. `mcptoon config set footer off` does the same for
the per-turn line. The first-run **self-heal** (install the agent-visible skill +
build the skill index) keeps its own marker, `config.selfheal_done()` /
`mark_selfheal_done()` — one marker cannot serve both, because the self-heal must run
once even when the welcome is off, and the welcome must still show where the
self-heal already ran.

*Gotcha:* do not burn the marker when the message was suppressed (a `--json` run, a
read-only home). A suppressed greeting must still be able to greet later. The
self-heal follows the same rule: a machine-readable format gets clean output and
keeps its marker for the next real run.

### 4. Opening the tool produces a response

The most natural way to open a CLI is to type its name with no arguments. Doing that
and getting nothing — or a wall of help — reads as "this thing is not really
installed".

*Ask:* if a new user types only the command name, what do they see in the first
three lines?

*Where it lives:* `cli._bare_greeting()` runs before the help page on a bare
`mcptoon`: the full card on a first run, a one-line `welcome.hint()` after that, then
the help page unchanged.

*Gotcha:* the hint drops figures it does not have. "0 tools" on a machine that has
servers is a false claim, and a false claim is worse than a shorter line.

### 5. Prefer deltas to absolutes

"Saved 5,090" means nothing without "compared to what". A change since last time is
easier to feel than a running total.

*Ask:* can the reader tell whether *this* turn did anything?

### 6. Say what you did not do

An honest no-op is a feature. A silent skip looks like a bug; a fake zero looks like
a lie. When a figure is unknown, omit the row — do not print a guess.

*Ask:* if this measurement failed or was skipped, what does the user see?

*Where it lives:* `welcome._rows_and_tail` drops unknown rows rather than printing 0;
`footer.note()` names the servers it could not see; `footer.skills_line()` returns
None (not "0 skills") when there is no skill catalog.

### 6b. An estimate is always marked as one

A measured number and a number that rests on an assumption must not look alike on
the page. mcptoon's broadcast carries exactly one estimate — "≈ saved so far" — and
it is labelled three ways: the `≈`, a name (`_cumulative_estimate`) that says what it
is, and a docstring that states the assumption and the direction of the error (it is
a *lower bound*: one turn making three calls is counted three times).

*Ask:* if this figure is wrong, is it wrong in a way the reader can see?

*Where it lives:* `footer._cumulative_estimate`; the `≈` is added in
`footer.skills_line()` (it moved there in the 2026-09-26 ≤80-column redesign) and
never omitted. Every other figure on every surface is a measurement with a
stated caliber (`[tiktoken cl100k_base]`).

### 7. The first run names one concrete next step

Not a manual. One command the user can type right now.

*Ask:* after the greeting, does the user know exactly what to type next?

*Where it lives:* `welcome.render()` "Next: `mcptoon status`"; `welcome.hint()` names
the same step in one line.

### 8. "How much does it save?" has exactly two answers, and they are labelled

The single most-confused thing about this tool, and it caused a real defect: on
2026-09-26 the footer quoted a **24%** saving while the product's actual claim was
**89%**, and both numbers were "true". They answer different questions:

* **Gateway caliber** — full upstream schemas versus what the agent actually loads
  under the default `compact` exposure (mcptoon's own meta-tools + directive). This
  is what *installing mcptoon* buys. It is the honest headline.
* **Slim-schema caliber** — the same tools with terser descriptions (`manifest
  --slim`). Smaller, secondary.

A third figure — the synthetic 255-tool sample recorded in `assets/benchmark_tiktoken.json`
(71,929 → 581) — is a *reproducible benchmark*, not the user's catalog. It must always be
labelled as a sample, never presented as "your" saving. Note `mcptoon bench` is **not**
this figure: `bench` measures the user's own catalog (the inputs to the gateway caliber),
while the fixed sample is reproduced by `scripts/bench_tokens.py`. Conflating the two is
the same "advertised ≠ actual" trap in a different coat.

*Ask:* which of the two does this number mean, and does the sentence say so? If it is
the sample, does the reader know it is not their machine?

*Where it lives:* `footer.gateway_savings()` computes the gateway figure once;
`footer.line()`, `cli._cmd_status` and `cli._cmd_stats` all call it, so no surface can
round or baseline it differently. `status` prints both figures on adjacent lines,
labelled. `mcptoon report` adds every caliber up, one labelled row each, and refuses to
print a cumulative-turn figure (turns are not counted). The sample tables live in the
READMEs and `docs/tiktoken-benchmarks.md` and say "synthetic sample".

*Gotcha:* never put the two calibers in the same sentence without naming which is
which, and never let the smaller one stand alone as "the" saving — it understates the
product ~3.6× while *looking* like the conservative, honest choice.

### 9. Every broadcast line fits 80 columns, or it is not done

The 2026-09-26 lesson, and the reason the footer was rewritten twice. The complaint
was "too verbose", but the measurable cause was **wrapping**: line 1 packed five
figures and measured **166 display columns**, so a normal 80-column terminal broke it
into three rows on every turn — the block read as noise before a single word was
judged. Word count was never the constraint; **display width is** (a CJK glyph is two
columns, so a Chinese line that "looks short" can still wrap).

Every line is now budgeted at ≤80 columns, and figures that no longer fit are moved
down a line or into `mcptoon report` — never crammed back in.

*Ask:* does any line wrap on an 80-column terminal, in any state, at any realistic
catalog size?

*Where it lives:* the `≤80` budget is enforced mechanically by
`tests/test_footer_broadcast.py::TestLineWidthBudget`, which renders the broadcast in
every state (normal, uncached, stale, no skills, no calls, fresh, and a grown catalog)
in both languages and fails if any line exceeds 80 display columns.

## How to check a change against this page

1. Run the tool the way a stranger would: bare invocation, then a real command,
   twice.
2. Compare the two runs. Anything identical that adds no information is rule 1.
3. Point at every number on screen and say where it came from and when — rule 2.
4. Read the first three lines as someone who just installed it — rules 4 and 7.
5. Break it on purpose: unreadable home, no cache, machine-readable format. It
   should degrade to less output, never to a wrong one — rules 3 and 6.
6. Squeeze the terminal to 80 columns and grow the catalog — rule 9.

## What this page is not

**It is a checklist, not a gate.** Most of it fails no build; these rules are read by
a human during review, and the judgement is the human's. Two mechanical guards back
two of them: `tests/test_footer_broadcast.py::TestLineWidthBudget` enforces rule 9's
80-column budget, and `tests/test_footprint_claims.py` covers a narrower claim (the
suite totals printed in the docs). Everything else on this page is a promise kept by
care, not by CI.
