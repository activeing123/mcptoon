"""The one-time first-run greeting — the first thing mcptoon ever says.

Why this module exists
----------------------
`cli._maybe_welcome` used to build its greeting inline with eight `print()` calls.
That was fine while the greeting was eight lines of ASCII. It stopped being fine
the moment the greeting had to carry three new duties at once:

1. **It is the only surface a brand-new user sees.** No footer has been stamped
   yet, no tool call has happened, and the model has read no instructions. Every
   claim the product makes about itself has to be true *and legible* here.
2. **Its real reader may be an agent, not a person.** Anything that runs
   `mcptoon … ` through a pipe sees this text. So the beautiful version is for a
   TTY and the piped version must be plain, complete text with no escape codes —
   colour is a reward for having eyes, never a payload requirement.
3. **It must not crash on a console that cannot encode it.** A Windows console
   redirected to a file uses the locale code page (cp936 here, cp437 elsewhere),
   where `🎉` and `┌` do not exist. `print()` would raise `UnicodeEncodeError` —
   the greeting would become the very bug that makes a tool look broken. Every
   glyph is therefore chosen at *call* time by test-encoding it against the real
   stream (never at import time, which is how `footer-facts` once captured a
   stale constant).

Layout rules, in priority order: the numbers first (what it found, what it
saves), then the one action worth taking, then the two ways out. A greeting that
asks for attention must answer "why did you touch my machine" before it asks for
anything — hence `Privacy` above the fold and `Undo` next to it.

Everything shown here is read, never estimated: the figures come from
`footer.facts()` (cache-only, one tokenizer, the same caliber `status`, `stats`
and `bench` print) and the skill count from the built skills index. When a figure
is unknown the row is dropped rather than shown as a guess — a first impression
with a fake number in it is worse than a shorter first impression.
"""

from __future__ import annotations

import os
import shutil
import sys
import unicodedata

__all__ = ["render", "color_enabled", "display_width"]

# ─── Colour: four SGR codes, no dependency, no framework ───
_RESET = "\x1b[0m"
_DIM = "\x1b[2m"
_BRAND = "\x1b[1;36m"   # bold cyan: reads as a product name, not an error
_VALUE = "\x1b[1m"

_MIN_WIDTH = 52
_MAX_WIDTH = 74


def color_enabled(stream=None) -> bool:
    """Whether to paint. Off for pipes, off for `NO_COLOR`, on for `FORCE_COLOR`.

    The TTY test is the load-bearing one: the greeted agent reads this through a
    pipe, and escape codes in a captured transcript are noise a model then has to
    ignore. `NO_COLOR` is the cross-tool convention; the two `MCPTOON_*` switches
    exist so a screenshot or a test can pin either answer without a real console.
    """
    if os.environ.get("MCPTOON_NO_COLOR") or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MCPTOON_FORCE_COLOR"):
        return True
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _char_width(ch: str) -> int:
    """Display columns of one character: 0 / 1 / 2.

    Needed because the card has a right border and this project speaks Chinese:
    `工具` is four columns wide but two characters long, so `len()` would put the
    border one cell short of the text on every CJK row. Combining marks take no
    cell; East-Asian Wide/Fullwidth and the emoji planes take two.
    """
    if unicodedata.combining(ch):
        return 0
    if ord(ch) >= 0x1F000:
        return 2
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text: str) -> int:
    """Columns `text` occupies in a terminal, ignoring colour codes."""
    stripped = text
    for code in (_RESET, _DIM, _BRAND, _VALUE):
        stripped = stripped.replace(code, "")
    return sum(_char_width(c) for c in stripped)


def _fits(text: str, stream) -> bool:
    """Whether `stream`'s encoding can carry `text` at all.

    Resolved per call, not per import: tests redirect stdout, and a module-level
    constant would freeze whichever stream happened to be current first.
    """
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _safe(text: str, stream) -> str:
    """Last-resort guarantee: whatever `stream` is, this text can be written to it.

    `_glyphs` covers the characters this module chooses *on purpose*. It cannot
    cover the ones it inherits — a subtitle, a version string, a translated tail
    someone edits later. Without this net the module's own promise ("must not
    crash on a console that cannot encode it") holds only for the characters
    whoever wrote the line remembered to route through the glyph table, and the
    first forgotten `·` or `—` turns the greeting back into the bug.
    """
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(enc)
        return text
    except (UnicodeEncodeError, LookupError):
        pass
    out = []
    for ch in text:
        try:
            ch.encode(enc)
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def _glyphs(stream) -> dict:
    """Box-drawing + emoji if the stream can carry them, ASCII if it cannot."""
    box = _fits("┌─│└", stream)
    mark = _fits("👋", stream)
    return {
        "tl": "┌" if box else "+", "tr": "┐" if box else "+",
        "bl": "└" if box else "+", "br": "┘" if box else "+",
        "h": "─" if box else "-", "v": "│" if box else "|",
        "mark": "👋" if mark else "*",
        "dot": "·" if _fits("·", stream) else "-",
        "arrow": "→" if _fits("→", stream) else "->",
    }


def _terminal_width(stream) -> int:
    try:
        cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        cols = 80
    return max(_MIN_WIDTH, min(_MAX_WIDTH, cols - 2))


def _pad(text: str, width: int) -> str:
    """Right-pad to `width` display columns (never truncates)."""
    return text + " " * max(0, width - display_width(text))


def _clip(text: str, width: int, ell: str = "…") -> str:
    """Truncate to `width` display columns, marking the cut with `ell`.

    `ell` is a parameter because the ASCII fallback stream cannot encode `…`
    either — the fallback that exists to stop a `UnicodeEncodeError` must not
    itself raise one.
    """
    if display_width(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > width - display_width(ell):
            break
        out += ch
        used += w
    return out + ell


def _rows_and_tail(facts: dict, skills: int | None, lng: str, stream) -> tuple[list, list]:
    """The (label, value, hint) rows and the closing lines, for one language.

    `stream` is threaded through so every glyph — including the one on the
    closing note — is chosen for the console that will actually receive it. The
    tail used to read `sys.stdout` directly, so a caller rendering for a
    different stream (a test, or a redirect) got box-drawing chosen for the
    terminal and emoji for the file.
    """
    zh = lng == "zh"
    g = _glyphs(stream)
    dot = g["dot"]
    arrow = g["arrow"]

    servers = int(facts.get("servers") or 0)
    tools = int(facts.get("tools") or 0)

    # What it found. A missing figure is omitted, never guessed.
    found_bits = []
    if servers:
        found_bits.append(f"{servers} " + ("个服务器" if zh else "servers"))
    if tools:
        found_bits.append(f"{tools} " + ("个工具" if zh else "tools"))
    if skills:
        found_bits.append(f"{skills} " + ("个技能" if zh else "skills"))
    found = f" {dot} ".join(found_bits) if found_bits else (
        "还没发现 MCP 服务器" if zh else "no MCP servers yet")

    # What it saves, on the same caliber as every other surface.
    full = int(facts.get("tokens_full") or 0)
    slim = int(facts.get("tokens_slim") or 0)
    saved = int(facts.get("tokens_saved") or 0)
    pct = float(facts.get("savings_pct") or 0.0)
    context = (f"{full:,} {arrow} {slim:,} tokens"
               + (f"（省 {saved:,}，{pct:.0f}%）" if zh else f" (saved {saved:,}, {pct:.0f}%)")
               ) if full else ("尚未缓存" if zh else "catalog not cached yet")

    rows = [
        ("本机已有" if zh else "Found", found, ""),
        ("上下文本钱" if zh else "In context", context, ""),
    ]
    if servers:
        rows += [
            ("下一步" if zh else "Next", "mcptoon status",
             "一屏看全部" if zh else "everything in one screen"),
            ("", "mcptoon skills list", "你的技能包" if zh else "the skills you own"),
        ]
    else:
        rows += [("下一步" if zh else "Next", "mcptoon quickstart",
                  "自动发现本机 MCP 服务器" if zh else "find the servers already on this machine")]
    rows += [
        ("撤销" if zh else "Undo", "mcptoon off",
         "从 agent 里拔掉网关" if zh else "unplug it from your agents"),
        ("", "mcptoon uninstall --dry", "预览完整清理" if zh else "preview a full cleanup"),
        ("隐私" if zh else "Privacy",
         f"无常驻进程 {dot} 无开机自启 {dot} 不上传数据" if zh
         else f"no daemon {dot} no autostart {dot} no upload", ""),
    ]

    tail = [
        f"{g['mark']} " + ("首次在本机运行，此提示只出现一次。" if zh
                           else "First run on this machine - this note shows once."),
        ("   关闭它：mcptoon config set welcome off" if zh
         else "   Silence it: mcptoon config set welcome off"),
    ]
    return rows, tail


def render(facts: dict, *, skills: int | None = None, lng: str = "en",
           stream=None) -> str:
    """The whole greeting as one string — built once, printed once.

    Returned rather than printed so the caller writes a single `os.write`-sized
    block: eight separate `print()` calls can interleave with a background
    process, and a half-drawn card looks like a bug.
    """
    stream = stream if stream is not None else sys.stdout
    g = _glyphs(stream)
    paint = color_enabled(stream)
    zh = lng == "zh"

    from . import __version__

    def dim(s: str) -> str:
        return f"{_DIM}{s}{_RESET}" if paint else s

    def brand(s: str) -> str:
        return f"{_BRAND}{s}{_RESET}" if paint else s

    def value(s: str) -> str:
        return f"{_VALUE}{s}{_RESET}" if paint else s

    width = _terminal_width(stream)
    title = f"{g['mark']} mcptoon {__version__}"
    # The subtitle goes through the glyph table like every other divider: a
    # hardcoded `·` here is exactly how the ASCII fallback grew a hole.
    d = g["dot"]
    subtitle = (f"工具 {d} 技能 {d} 已压缩 {d} 可撤销" if zh
                else f"tools {d} skills {d} compressed {d} reversible")

    inner = width - 2
    head = g["h"] + " " + title + " "
    head_pad = g["h"] * max(0, inner - display_width(head))
    card = [
        g["tl"] + head + head_pad + g["tr"],
        g["v"] + " " + _pad(_clip(subtitle, inner - 2), inner - 2) + " " + g["v"],
        g["bl"] + g["h"] * inner + g["br"],
    ]

    rows, tail = _rows_and_tail(facts, skills, lng, stream)
    label_w = max((display_width(label) for label, _, _ in rows), default=0)
    ell = "…" if _fits("…", stream) else "..."
    body = []
    for label, val, hint in rows:
        lead = "  " + (" " * label_w if not label else _pad(label, label_w)) + "  "
        line = lead + value(val) + (("  " + dim(hint)) if hint else "")
        # A row that outgrows the terminal wraps, and a wrapped row reads as a
        # rendering bug. Keep the label and the command always — clip the value
        # and drop the hint, which is the least informative part of the row.
        if display_width(line) > width:
            room = max(8, width - display_width(lead) - 1)
            line = lead + value(_clip(val, room, ell))
        body.append(line.rstrip())

    out = [""]
    out.append(brand(card[0]) if paint else card[0])
    out.append(dim(card[1]) if paint else card[1])
    out.append(dim(card[2]) if paint else card[2])
    out.append("")
    out.extend(body)
    out.append("")
    out.append(dim(tail[0]) if paint else tail[0])
    out.append(dim(tail[1]) if paint else tail[1])
    out.append("")
    return _safe("\n".join(out), stream)
