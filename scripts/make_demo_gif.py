#!/usr/bin/env python3
"""Render assets/demo-en.gif from a captured mcptoon transcript.

The lines below are copied verbatim from a real run on a clean virtualenv:

    python -m venv .venv && .venv/bin/pip install mcptoon
    .venv/bin/mcptoon demo

Only the frame pacing is synthetic; every character of terminal text is what
mcptoon v0.7.4 actually printed. (The tail of the real output is omitted here
because it still advertises the pre-0.7.5 "93%" figure.)

Requires Pillow - a dev-only dependency, never imported by the package:

    pip install pillow && python scripts/make_demo_gif.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "assets" / "demo-en.gif"

W, H = 960, 600
BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (139, 148, 158)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
PROMPT = (121, 192, 255)

LINE_H = 17
PAD_X, PAD_Y = 26, 20
FONT_SIZE = 13

# (kind, text) - kind drives colour; "$ " prefix is typed, everything else appears.
TRANSCRIPT: list[tuple[str, str]] = [
    ("cmd", "$ pip install mcptoon"),
    ("dim", "Collecting mcptoon"),
    ("dim", "  Downloading mcptoon-0.7.4-py3-none-any.whl (130 kB)"),
    ("dim", "Installing collected packages: mcptoon"),
    ("ok", "Successfully installed mcptoon-0.7.4"),
    ("txt", ""),
    ("cmd", "$ mcptoon demo"),
    ("txt", ""),
    ("txt", "╔══════════════════════════════════════════════╗"),
    ("txt", "║         mcptoon — Zero-config demo          ║"),
    ("txt", "║    Install 1,000 MCP tools, 0 token schemas ║"),
    ("txt", "╚══════════════════════════════════════════════╝"),
    ("txt", ""),
    ("dim", "  Starting demo server..."),
    ("ok", "  ✓ Demo server ready"),
    ("txt", ""),
    ("txt", "  Official benchmark: 255 tools, 50 servers, tiktoken cl100k_base:"),
    ("txt", ""),
    ("txt", "  Format           Tokens    Savings"),
    ("txt", "  ──────────── ────────── ──────────"),
    ("bad", "  JSON             71,929          -"),
    ("txt", "  TOON             47,438        34%"),
    ("txt", "  SLIM              8,282      88.5%"),
    ("ok", "  Compact             581      99.2%"),
    ("txt", ""),
    ("ok", "  Schemas in context with mcptoon: 0 tokens (always)"),
    ("txt", ""),
    ("dim", "  ✓ connect every agent with ONE config   →  mcptoon sync"),
    ("dim", "  ✓ expose ALL servers as ONE stdio server →  mcptoon serve"),
    ("dim", "  ✓ never paste tool schemas again         →  mcptoon manifest --slim"),
]

COLOURS = {"txt": FG, "dim": DIM, "ok": GREEN, "bad": RED}


def font() -> ImageFont.ImageFont:
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def render(lines: list[tuple[str, str]], caret: bool) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    f = font()
    draw.rounded_rectangle([6, 6, W - 7, 34], radius=6, fill=(22, 27, 34))
    for i, col in enumerate(((248, 81, 73), (219, 171, 9), (63, 185, 80))):
        draw.ellipse([20 + i * 18, 14, 30 + i * 18, 24], fill=col)
    draw.text((W // 2 - 90, 12), "mcptoon — Windows PowerShell", font=f, fill=DIM)

    y = 34 + PAD_Y
    for kind, text in lines:
        if kind == "cmd" and text:
            draw.text((PAD_X, y), "$ ", font=f, fill=PROMPT)
            width = draw.textlength("$ ", font=f)
            draw.text((PAD_X + width, y), text[2:], font=f, fill=FG)
        else:
            draw.text((PAD_X, y), text, font=f, fill=COLOURS.get(kind, FG))
        y += LINE_H
    if caret:
        cx = PAD_X + draw.textlength(lines[-1][1], font=f) + 8
        draw.rectangle([cx, y - 15, cx + 8, y + 2], fill=FG)
    return img


def main() -> None:
    frames: list[Image.Image] = []
    shown: list[tuple[str, str]] = []

    def hold(image: Image.Image, times: int) -> None:
        frames.extend([image] * times)

    hold(render([("txt", "")], caret=False), 6)

    for kind, text in TRANSCRIPT:
        if kind == "cmd":
            for n in range(2, len(text) + 1):
                partial = shown + [("cmd", text[:n])]
                hold(render(partial, caret=True), 1)
            shown = shown + [("cmd", text)]
            hold(render(shown, caret=False), 5)
        else:
            shown = shown + [(kind, text)]
            hold(render(shown, caret=False), 2 if text else 1)
        if len(shown) * LINE_H > H - 60:  # keep the last screen readable
            break

    hold(render(shown, caret=False), 26)

    OUT.parent.mkdir(exist_ok=True)
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        optimize=True,
    )
    print(f"{OUT.name}: {len(frames)} frames, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
