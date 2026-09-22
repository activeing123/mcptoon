# -*- coding: utf-8 -*-
"""Generate every README figure as a self-contained SVG (EN + ZH).

Reproducible:  python scripts/make_readme_figs.py
Output:        assets/fig-<name>-en.svg / -zh.svg

Design system (shared with the landing page):
  - GitHub document language: white base, hairline borders, green brand accent
  - 60-30-10: 60% white/green-tint bg, 30% ink/gray text, 10% green + amber accent
  - depth: ambient glow blobs -> soft card shadow -> focus element with glow
  - no emoji (librsvg renders them monochrome), no foreignObject, no external refs
"""
import os
import re

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# ---- design tokens -----------------------------------------------------------
GREEN = "#1a7f37"
GREEN_L = "#2ea043"
GREEN_BG = "#eaf6ec"
INK = "#1f2328"
GRAY = "#57606a"
GRAY_L = "#8c959f"
LINE = "#d0d7de"
PANEL = "#f6f8fa"
BLUE = "#0969da"
AMBER = "#bf8700"
AMBER_BG = "#fff4d6"
RED = "#cf222e"
RED_BG = "#ffebe9"
FONT = "-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Consolas,'Courier New',monospace"

DEFS = f"""  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#f1f7f2"/>
    </linearGradient>
    <linearGradient id="strip" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{GREEN_L}"/><stop offset="1" stop-color="{GREEN}"/>
    </linearGradient>
    <linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{GREEN_L}"/><stop offset="1" stop-color="{GREEN}"/>
    </linearGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="180%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="10"/>
      <feOffset dy="7"/>
      <feComponentTransfer><feFuncA type="linear" slope="0.20"/></feComponentTransfer>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="glow" x="-70%" y="-70%" width="240%" height="240%">
      <feGaussianBlur stdDeviation="5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="grain" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/>
      <feColorMatrix type="saturate" values="0"/>
    </filter>
    <marker id="arw" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{GRAY_L}"/>
    </marker>
    <marker id="arwg" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{GREEN}"/>
    </marker>
  </defs>
"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=15, fill=INK, anchor="middle", weight="400", mono=False, ls=None, op=None):
    a = f' text-anchor="{anchor}"' if anchor else ""
    f = f' font-family="{MONO}"' if mono else ""
    w = f' font-weight="{weight}"' if weight != "400" else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    o = f' opacity="{op}"' if op else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{a}{f}{w}{l}{o}>{esc(s)}</text>'


def card(x, y, w, h, rx=10, fill="#ffffff", stroke=LINE, shadow=True, sw=1):
    sh = ' filter="url(#soft)"' if shadow else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{sh}/>'


def chip(x, y, s, size=14.5, fill=INK, mono=True, weight="400"):
    """centered text inside a 46-tall card starting at y"""
    return t(x, y + 29, s, size=size, fill=fill, mono=mono, weight=weight)


# ---- minimal geometric icon set (no emoji, no external refs) -----------------
def ic_search(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2" '
            f'stroke-linecap="round"><circle cx="-1" cy="-1" r="5.5"/><line x1="3" y1="3" x2="7.5" y2="7.5"/></g>')


def ic_branch(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2" '
            f'stroke-linecap="round"><circle cx="-4" cy="-5" r="2.4"/><circle cx="-4" cy="6" r="2.4"/>'
            f'<circle cx="5" cy="0" r="2.4"/><path d="M-4,-2.6 L-4,3.6 M-1.8,-4.4 C2,-4 3,-2 4.6,-1"/></g>')


def ic_db(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2">'
            f'<ellipse cx="0" cy="-5.5" rx="7" ry="2.8"/><path d="M-7,-5.5 L-7,5.5 A7,2.8 0 0 0 7,5.5 L7,-5.5"/>'
            f'<path d="M-7,0 A7,2.8 0 0 0 7,0"/></g>')


def ic_globe(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2">'
            f'<circle cx="0" cy="0" r="7"/><ellipse cx="0" cy="0" rx="3" ry="7"/><line x1="-7" y1="0" x2="7" y2="0"/></g>')


def ic_spark(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})"><path d="M0,-8 L2.2,-2.2 L8,0 L2.2,2.2 L0,8 '
            f'L-2.2,2.2 L-8,0 L-2.2,-2.2 Z" fill="{c}"/></g>')


def ic_cursor(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})"><path d="M-4,-8 L-4,7 L-0.5,3.4 L2,9 L4.6,7.8 '
            f'L2.2,2.4 L7,2.2 Z" fill="{c}"/></g>')


def ic_chev(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round"><polyline points="-6,-6 -0.5,0 -6,6"/>'
            f'<polyline points="1,-6 6.5,0 1,6"/></g>')


def ic_grid(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="{c}">'
            f'<rect x="-7" y="-7" width="6" height="6" rx="1.6"/><rect x="1" y="-7" width="6" height="6" rx="1.6"/>'
            f'<rect x="-7" y="1" width="6" height="6" rx="1.6"/><rect x="1" y="1" width="6" height="6" rx="1.6"/></g>')


def ic_term(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"><rect x="-8" y="-6.5" width="16" height="13" rx="2.4"/>'
            f'<polyline points="-4.5,-1.5 -2,1 -4.5,3.5"/><line x1="1" y1="3.5" x2="5" y2="3.5"/></g>')


def ic_shield(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})"><path d="M0,-9 L8,-5.4 L8,1.6 Q0,8.6 0,9 Q0,8.6 -8,1.6 '
            f'L-8,-5.4 Z" fill="{c}"/><path d="M-3.2,0 L-0.8,2.6 L3.6,-2.6" fill="none" stroke="#ffffff" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></g>')


def ic_eye(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2">'
            f'<path d="M-8.5,0 Q0,-6.5 8.5,0 Q0,6.5 -8.5,0 Z"/><circle cx="0" cy="0" r="2.6" fill="{c}" stroke="none"/></g>')


def ic_lock(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2">'
            f'<rect x="-6.5" y="-1.5" width="13" height="10" rx="2.2"/><path d="M-4,-1.5 L-4,-5 A4,4 0 0 1 4,-5 L4,-1.5"/>'
            f'<circle cx="0" cy="3.6" r="1.3" fill="{c}" stroke="none"/></g>')


def ic_bolt(x, y, c=GREEN, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})"><path d="M1.5,-9 L-6,1 L-1,1 L-1.5,9 L6,-1.5 L1,-1.5 Z" '
            f'fill="{c}"/></g>')


def ic_plug(x, y, c="#ffffff", s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})" fill="none" stroke="{c}" stroke-width="2" '
            f'stroke-linecap="round"><line x1="-3.5" y1="-9" x2="-3.5" y2="-4"/><line x1="3.5" y1="-9" x2="3.5" y2="-4"/>'
            f'<path d="M-6,-4 L6,-4 L6,1 A6,6 0 0 1 -6,1 Z" fill="{c}" stroke="none"/>'
            f'<line x1="0" y1="7" x2="0" y2="10"/></g>')


# ---- figure shell -----------------------------------------------------------
def fig(name, w, h, body, subtitle=None):
    blobs = (f'<circle cx="{int(w*0.14)}" cy="{int(h*0.20)}" r="{int(h*0.42)}" fill="{GREEN_L}" opacity="0.055"/>'
             f'<circle cx="{int(w*0.88)}" cy="{int(h*0.82)}" r="{int(h*0.40)}" fill="{AMBER}" opacity="0.045"/>')
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="{FONT}">',
         DEFS,
         f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="18" fill="url(#bg)" stroke="{LINE}"/>',
         blobs,
         f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="18" filter="url(#grain)" opacity="0.045"/>']
    s.append(body)
    s.append('</svg>\n')
    return "\n".join(s)


# =============================================================================
# 1 · HERO — the power strip
# =============================================================================
def f_hero(zh):
    W, H = 1180, 520
    S = {
        "title": "插一次，全都能用。" if zh else "Plug in once. Every AI can use every tool.",
        "sub": "一个 189KB 的零依赖 CLI，把 MCP 工具 schema 和 Agent 技能挡在上下文之外。" if zh
               else "One 189KB zero-dependency CLI keeps every MCP tool schema and agent skill out of context.",
        "lt": "你的工具" if zh else "YOUR TOOLS",
        "rt": "你的 AI" if zh else "YOUR AI AGENTS",
        "tools": (["联网搜索", "GitHub", "文件 · 数据库", "翻译 · 任何工具"] if zh
                  else ["Web search", "GitHub", "Files & database", "Translate · +anything"]),
        "agents": (["Claude / Codex", "Cursor", "Copilot · Cline", "任何 AI，任何终端"] if zh
                   else ["Claude / Codex", "Cursor", "Copilot · Cline", "Any agent, any CLI"]),
        "steps": (["装上", "pip install mcptoon", "插上", "mcptoon quickstart", "完成", "mcptoon demo"] if zh
                  else ["Install", "pip install mcptoon", "Plug in", "mcptoon quickstart", "Done", "mcptoon demo"]),
        "foot": ("不用手写 JSON · 零依赖 · 离线可用 · Apache-2.0" if zh
                 else "You edit no JSON · Zero dependencies · Works offline · Apache-2.0"),
    }
    b = [t(590, 56, S["title"], size=33, weight="800"),
         t(590, 88, S["sub"], size=16, fill=GRAY)]

    b.append(t(150, 132, S["lt"], size=13.5, fill=GRAY, weight="700", ls="1.4"))
    b.append(t(1030, 132, S["rt"], size=13.5, fill=GRAY, weight="700", ls="1.4"))
    icons = [ic_search, ic_branch, ic_db, ic_globe]
    for i in range(4):
        y = 150 + i * 56
        b.append(card(34, y, 232, 46, rx=10))
        b.append(icons[i](62, y + 23))
        b.append(t(150, y + 29, S["tools"][i], size=15, anchor="middle"))
        b.append(card(914, y, 232, 46, rx=10))
        b.append(ic_grid(942, y + 23) if i == 3 else [ic_spark, ic_cursor, ic_chev][i](942, y + 23))
        b.append(t(1030, y + 29, S["agents"][i], size=15, anchor="middle"))

    for i in range(4):
        y = 150 + i * 56 + 23
        ty = [215, 228, 240, 252][i]
        b.append(f'<path d="M266,{y} C330,{y} 330,{ty} 375,{ty}" fill="none" stroke="{GRAY_L}" stroke-width="3"/>')
        b.append(f'<path d="M914,{y} C850,{y} 850,{ty} 805,{ty}" fill="none" stroke="{GRAY_L}" stroke-width="3"/>')

    b.append(f'<rect x="375" y="178" width="430" height="100" rx="24" fill="url(#strip)" filter="url(#glow)"/>')
    b.append('<rect x="395" y="192" width="390" height="34" rx="10" fill="#ffffff" opacity="0.14"/>')
    b.append(ic_plug(430, 209))
    b.append(t(600, 217, "mcptoon", size=20, fill="#ffffff", weight="800", mono=True))
    for k in range(5):
        x = 415 + k * 80
        b.append(f'<rect x="{x}" y="238" width="46" height="26" rx="6" fill="#0f2e18"/>')
        b.append(f'<circle cx="{x+15}" cy="248" r="3.4" fill="#7ee787"/><circle cx="{x+31}" cy="248" r="3.4" fill="#7ee787"/>')
    b.append(f'<circle cx="438" cy="251" r="9" fill="{GREEN}" opacity="0.4" filter="url(#glow)"/>')
    b.append(f'<circle cx="598" cy="251" r="9" fill="{GREEN}" opacity="0.4" filter="url(#glow)"/>')

    for k in range(3):
        x = 120 + k * 325
        b.append(card(x, 396, 290, 54, rx=12))
        b.append(t(x + 145, 419, f"{k+1} · {S['steps'][k*2]}", size=15.5, fill=GREEN, weight="700"))
        b.append(t(x + 145, 440, S["steps"][k * 2 + 1], size=13.5, mono=True, fill=INK))
    b.append(f'<polygon points="414,419 434,419 424,431" fill="{GRAY_L}"/>')
    b.append(f'<polygon points="739,419 759,419 749,431" fill="{GRAY_L}"/>')
    b.append(t(590, 486, S["foot"], size=14.5, fill=GRAY))
    return fig("hero", W, H, "\n".join(b))


# =============================================================================
# 2 · TAX — the token bill
# =============================================================================
def f_tax(zh):
    W, H = 980, 400
    S = {
        "title": "问一句「有哪些工具」，要花多少 token？" if zh else 'What does "which tools are there?" cost in tokens?',
        "sub": "255 个工具 · tiktoken cl100k_base 实测 · 可复现" if zh
               else "255 tools · tiktoken cl100k_base · measured, reproducible",
        "rows": (["原始 JSON schema", "--slim　名字 + 参数", "--compact　只有名字"] if zh
                 else ["Raw JSON schema", "--slim  names + params", "--compact  names only"]),
        "vals": ["71,929", "8,282", "581"],
        "pcts": ["", "−88.5%", "−99.2%"],
        "book": "71,929 ≈ 一本 300 页的书　·　581 ≈ 半页纸" if zh
                else "71,929 ≈ a 300-page book   ·   581 ≈ half a page",
        "kick": "关键不是压缩：schema 根本不进上下文" if zh
                else "The point is not compression: the schema never enters the context",
    }
    b = [t(490, 50, S["title"], size=25, weight="800"),
         t(490, 78, S["sub"], size=14, fill=GRAY)]
    x0, full = 300, 460
    cols = [(RED, RED_BG), (AMBER, AMBER_BG), (GREEN, GREEN_BG)]
    widths = [full, max(10, full * 8282 / 71929), max(8, full * 581 / 71929)]
    for i in range(3):
        y = 118 + i * 74
        b.append(t(276, y + 22, S["rows"][i], size=14.5, anchor="end", fill=INK, weight="700" if i == 0 else "400"))
        b.append(f'<rect x="{x0}" y="{y}" width="{full}" height="34" rx="7" fill="{PANEL}"/>')
        b.append(f'<rect x="{x0}" y="{y}" width="{widths[i]:.1f}" height="34" rx="7" fill="{cols[i][0]}"/>')
        b.append(t(x0 + full + 16, y + 23, S["vals"][i], size=17, anchor="start", weight="800",
                   fill=cols[i][0], mono=True))
        if S["pcts"][i]:
            b.append(t(x0 + full + 104, y + 23, S["pcts"][i], size=14.5, anchor="start", fill=GRAY, mono=True))
    b.append(f'<line x1="60" y1="330" x2="920" y2="330" stroke="{LINE}"/>')
    b.append(t(490, 358, S["book"], size=15, fill=GRAY))
    b.append(t(490, 384, S["kick"], size=15, fill=GREEN, weight="700"))
    return fig("tax", W, H, "\n".join(b))


# =============================================================================
# 3 · BENCHMARK — grouped bars, log scale
# =============================================================================
def f_bench(zh):
    import math
    W, H = 980, 470
    S = {
        "title": "各格式的 token 消耗（越低越好）" if zh else "Token consumption by format (lower is better)",
        "sub": "tiktoken cl100k_base · 数字越小越好" if zh else "tiktoken cl100k_base · shorter bar = fewer tokens",
        "groups": (["5 个工具", "50 个工具", "255 个工具"] if zh else ["5 tools", "50 tools", "255 tools"]),
    }
    data = [[1519, 1017, 274, 11], [14113, 9300, 1620, 114], [71929, 47438, 8282, 581]]
    names = ["JSON", "TOON", "SLIM", "Compact"]
    colors = [GRAY_L, BLUE, AMBER, GREEN]
    b = [t(490, 50, S["title"], size=25, weight="800"),
         t(490, 78, S["sub"], size=14, fill=GRAY)]
    lx = 200
    for i, n in enumerate(names):
        b.append(f'<rect x="{lx + i*175}" y="98" width="13" height="13" rx="3" fill="{colors[i]}"/>')
        b.append(t(lx + i * 175 + 20, 109, n, size=13.5, anchor="start", fill=GRAY, weight="700"))
    top, bot = 130, 392
    lo, hi = math.log10(11), math.log10(71929)

    def Y(v):
        return bot - (bot - top) * (math.log10(v) - lo) / (hi - lo)

    for g in range(3):
        cx = 230 + g * 260
        bw, gap = 44, 8
        tot = 4 * bw + 3 * gap
        x = cx - tot / 2
        for i in range(4):
            v = data[g][i]
            y = Y(v)
            b.append(f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{bot-y:.1f}" rx="4" fill="{colors[i]}"/>')
            lbl = f"{v:,}"
            b.append(t(x + bw / 2, y - 7, lbl, size=12.5, fill=colors[i], weight="700", mono=True))
            x += bw + gap
        b.append(t(cx, 416, S["groups"][g], size=14.5, fill=INK, weight="700"))
    b.append(f'<line x1="70" y1="{bot}" x2="910" y2="{bot}" stroke="{LINE}" stroke-width="1.5"/>')
    for v in (100, 1000, 10000):
        y = Y(v)
        b.append(f'<line x1="70" y1="{y:.1f}" x2="910" y2="{y:.1f}" stroke="{LINE}" stroke-dasharray="3 5"/>')
        b.append(t(62, y + 4, f"{v:,}", size=11.5, anchor="end", fill=GRAY_L, mono=True))
    b.append(t(490, 446, "对数量程 · 每格 10×" if zh else "log scale · each gridline is 10×",
               size=13, fill=GRAY))
    return fig("benchmark", W, H, "\n".join(b))


# =============================================================================
# 4 · SYNC — one config, every agent
# =============================================================================
def f_sync(zh):
    W, H = 1180, 430
    S = {
        "title": "一份配置，喂给所有 Agent" if zh else "One config. Every agent.",
        "sub": "mcptoon 给每个 Agent 写它自己的原生配置，于是大家共用同一个工具箱。" if zh
               else "mcptoon writes each agent's native config, so they all share one toolbox.",
        "cmd": "mcptoon sync",
        "agents": (["Claude Code", "Codex", "Cursor", "Windsurf", "Gemini CLI", "任何 CLI"] if zh
                   else ["Claude Code", "Codex", "Cursor", "Windsurf", "Gemini CLI", "Any CLI"]),
        "files": [".mcp.json", "config.toml", "mcp.json", "mcp_config.json", "settings.json", "shell"],
        "cfg": "~/.mcptoon/config.json",
    }
    BRAND = [GREEN, BLUE, AMBER, "#8250df", "#0969da", GRAY]
    b = [t(590, 50, S["title"], size=28, weight="800"),
         t(590, 80, S["sub"], size=14.5, fill=GRAY)]
    # command card — green
    b.append(f'<rect x="60" y="168" width="250" height="66" rx="12" fill="url(#strip)" filter="url(#soft)"/>')
    b.append(ic_term(96, 201, c="#ffffff"))
    b.append(t(190, 208, "$ " + S["cmd"], size=14, mono=True, fill="#ffffff", weight="700"))
    b.append(f'<path d="M318,201 L392,201" stroke="{GREEN}" stroke-width="3.5" marker-end="url(#arwg)"/>')
    # config card — green tint
    b.append(f'<rect x="400" y="158" width="270" height="86" rx="14" fill="{GREEN_BG}" stroke="{GREEN}" '
             f'stroke-width="1.5" filter="url(#soft)"/>')
    b.append(ic_lock(437, 201, c=GREEN))
    b.append(t(535, 194, S["cfg"], size=13.5, mono=True, fill=INK, weight="700"))
    b.append(t(535, 220, "single source of truth" if not zh else "唯一事实源", size=12.5, fill=GREEN, weight="700"))
    for i in range(6):
        col, row = i % 2, i // 2
        x = 726 + col * 214
        y = 122 + row * 76
        b.append(f'<path d="M672,201 C700,201 700,{y+23} {x-8},{y+23}" fill="none" stroke="{GRAY_L}" '
                 f'stroke-width="2.4" marker-end="url(#arw)"/>')
        b.append(card(x, y, 194, 46, rx=10, shadow=False))
        b.append(f'<rect x="{x}" y="{y}" width="6" height="46" rx="3" fill="{BRAND[i]}"/>')
        b.append(f'<circle cx="{x+26}" cy="{y+23}" r="8" fill="{BRAND[i]}" opacity="0.85"/>')
        b.append(t(x + 44, y + 20, S["agents"][i], size=13.5, anchor="start", weight="700"))
        b.append(t(x + 44, y + 37, S["files"][i], size=11.5, anchor="start", mono=True, fill=GRAY))
    b.append(f'<rect x="120" y="384" width="940" height="34" rx="10" fill="{GREEN_BG}"/>')
    b.append(t(590, 406, "装一次 · 加新工具立刻生效 · 不用重启任何 Agent" if zh
               else "Install once · new tools apply instantly · no agent restart", size=14, fill=GREEN, weight="700"))
    return fig("sync", W, H, "\n".join(b))


# =============================================================================
# 5 · LOOP — manifest -> inspect -> call
# =============================================================================
def f_loop(zh):
    W, H = 1180, 440
    S = {
        "title": "用 manifest 选工具，调用前 inspect" if zh else "Choose with manifest. Call with inspect.",
        "sub": "名字清单负责「选哪个」，按需 inspect 负责「怎么调」" if zh
               else "Names pick the tool; on-demand inspect gets the arguments right.",
        "s": ([("manifest", "只有工具名", "255 个工具 · 581 token"),
               ("inspect <server> <tool>", "一个 schema", "按需 · 约 37 token"),
               ("call … --toon", "调用 + 压缩结果", "结果再省约 34%")] if zh else
              [("manifest", "names only", "255 tools · 581 tokens"),
               ("inspect <server> <tool>", "one schema", "on demand · ~37 tokens"),
               ("call … --toon", "call + shrink result", "~34% off the result")]),
        "stat1": "只靠名字猜参数：41 次里 4 次正确（≈10%）" if zh else "Guessing args from names alone: 4/41 valid calls (≈10%)",
        "stat2": "先 inspect：41/41 全对（100%）" if zh else "Inspect first: 41/41 (100%), same as dumping every schema",
    }
    b = [t(590, 50, S["title"], size=28, weight="800"),
         t(590, 80, S["sub"], size=14.5, fill=GRAY)]
    ICONS = [ic_grid, ic_eye, ic_term]
    METRIC = ["581", "37", "34%"]
    for i in range(3):
        x = 60 + i * 380
        # colored top strip + white body
        b.append(f'<rect x="{x}" y="112" width="300" height="196" rx="14" fill="#ffffff" stroke="{LINE}" filter="url(#soft)"/>')
        b.append(f'<path d="M{x+14},112 h272 a0,0 0 0 1 0,0 v0 h-272 z" fill="none"/>')
        b.append(f'<rect x="{x}" y="112" width="300" height="44" rx="14" fill="url(#strip)"/>')
        b.append(f'<rect x="{x}" y="140" width="300" height="16" fill="url(#strip)"/>')
        b.append(f'<circle cx="{x+34}" cy="134" r="14" fill="#ffffff" opacity="0.22"/>')
        b.append(t(x + 34, 140, str(i + 1), size=15, fill="#ffffff", weight="800"))
        b.append(ICONS[i](x + 64, 134, c="#ffffff", s=1.05))
        b.append(t(x + 92, 140, S["s"][i][0], size=13.5, anchor="start", mono=True, fill="#ffffff", weight="700"))
        b.append(f'<rect x="{x+16}" y="{x and 0 or 0}" width="0" height="0"/>')
        b.append(f'<rect x="{x+16}" y="172" width="268" height="52" rx="9" fill="{PANEL}" stroke="{LINE}"/>')
        b.append(t(x + 150, 195, S["s"][i][1], size=13.5, fill=INK, weight="700"))
        b.append(t(x + 150, 214, S["s"][i][2], size=12.5, fill=GRAY, mono=True))
        b.append(f'<rect x="{x+16}" y="236" width="268" height="52" rx="9" fill="{GREEN_BG}"/>')
        b.append(t(x + 90, 270, METRIC[i], size=22, fill=GREEN, weight="800", mono=True))
        b.append(t(x + 150, 270, ["token", "token", "省"][i] if zh else ["tokens", "tokens", "saved"][i],
                   size=12.5, fill=GREEN, weight="700"))
        if i < 2:
            b.append(f'<path d="M366,210 L434,210" stroke="{GREEN}" stroke-width="3.5" marker-end="url(#arwg)"/>')
    # stat band: red vs green
    b.append(f'<rect x="60" y="332" width="520" height="84" rx="14" fill="{RED_BG}" stroke="{RED}" stroke-width="1.2"/>')
    b.append(ic_search(102, 374, c=RED, s=1.3))
    b.append(t(134, 362, S["stat1"], size=14, anchor="start", fill=RED, weight="700"))
    b.append(t(134, 388, "只靠名字猜参数" if zh else "names alone", size=12.5, anchor="start", fill=RED, op="0.8"))
    b.append(f'<rect x="600" y="332" width="520" height="84" rx="14" fill="{GREEN_BG}" stroke="{GREEN}" stroke-width="1.2"/>')
    b.append(ic_shield(642, 374, c=GREEN, s=1.3))
    b.append(t(674, 362, S["stat2"], size=14, anchor="start", fill=GREEN, weight="700"))
    b.append(t(674, 388, "推荐用法：先 inspect" if zh else "recommended loop", size=12.5, anchor="start", fill=GREEN, op="0.85"))
    return fig("loop", W, H, "\n".join(b))


# =============================================================================
# 6 · SKILLS — the other half of the toolbox
# =============================================================================
def f_skills(zh):
    W, H = 1180, 470
    S = {
        "title": "工具箱的另一半：Agent 技能" if zh else "The other half of the toolbox: agent skills",
        "sub": "同一套引擎，管你的 SKILL.md 目录" if zh else "The same engine, pointed at your SKILL.md catalog",
        "big": "371 个 SKILL.md 全量加载" if zh else "All 371 SKILL.md files, loaded whole",
        "bigv": "926,232 token",
        "res": "mcptoon skills resolve \"…\" --k 5",
        "resv": "501 token · 返回最该用的 5 个" if zh else "501 tokens · the 5 that matter",
        "mid": "BM25 · 离线 · 不调 LLM" if zh else "BM25 · offline · no LLM",
        "win": "一个 128K 上下文窗口" if zh else "one 128K context window",
        "over": "926,232 token = 7.07 个 128K 窗口，装不下" if zh
                else "926,232 tokens = 7.07 full 128K windows. It does not fit.",
    }
    b = [t(590, 50, S["title"], size=28, weight="800"),
         t(590, 80, S["sub"], size=14.5, fill=GRAY)]
    b.append(card(50, 108, 480, 214, rx=14))
    b.append(t(290, 140, S["big"], size=15, weight="700"))
    for i in range(6):
        x = 78 + (i % 3) * 148
        y = 156 + (i // 3) * 40
        b.append(f'<rect x="{x}" y="{y}" width="136" height="30" rx="6" fill="#ffffff" stroke="{LINE}"/>')
        b.append(f'<rect x="{x+8}" y="{y+9}" width="12" height="12" rx="3" fill="{GREEN_L}" opacity="0.5"/>')
        b.append(f'<rect x="{x+27}" y="{y+9}" width="88" height="4" rx="2" fill="{LINE}"/>')
        b.append(f'<rect x="{x+27}" y="{y+17}" width="62" height="4" rx="2" fill="{LINE}"/>')
    b.append(t(290, 250, "… ×371", size=15, fill=GRAY, weight="700"))
    b.append(f'<rect x="78" y="268" width="424" height="34" rx="8" fill="{RED_BG}"/>')
    b.append(t(290, 291, S["bigv"], size=17, fill=RED, weight="800", mono=True))

    b.append(f'<path d="M556,215 L624,215" stroke="{GREEN}" stroke-width="3.5" marker-end="url(#arwg)"/>')
    b.append(t(590, 196, S["mid"], size=12.5, fill=GREEN, weight="700"))

    b.append(card(650, 108, 480, 214, rx=14))
    b.append(t(890, 140, S["res"], size=14.5, mono=True, weight="700"))
    for i in range(5):
        y = 156 + i * 30
        b.append(f'<rect x="678" y="{y}" width="424" height="24" rx="6" fill="{GREEN_BG}" stroke="{GREEN}" stroke-width="1"/>')
        b.append(f'<circle cx="696" cy="{y+12}" r="4.5" fill="{GREEN}"/>')
        b.append(f'<rect x="710" y="{y+9}" width="{140 - i*12}" height="6" rx="3" fill="{GREEN}" opacity="0.45"/>')
    b.append(f'<rect x="678" y="268" width="424" height="34" rx="8" fill="{GREEN_BG}"/>')
    b.append(t(890, 291, S["resv"], size=15.5, fill=GREEN, weight="800"))

    b.append(card(50, 348, 1080, 86, rx=14, shadow=False, fill="#ffffff"))
    b.append(t(90, 380, S["win"], size=13.5, anchor="start", fill=GRAY, weight="700"))
    b.append(f'<rect x="90" y="390" width="760" height="26" rx="6" fill="{PANEL}" stroke="{LINE}"/>')
    b.append(f'<rect x="90" y="390" width="760" height="26" rx="6" fill="{RED}" opacity="0.85"/>')
    b.append(f'<rect x="850" y="390" width="240" height="26" rx="6" fill="{RED}" opacity="0.35" stroke="{RED}" stroke-dasharray="4 4"/>')
    b.append(t(1140, 408, "…×7.07", size=13, anchor="end", fill=RED, weight="800", mono=True))
    b.append(t(90, 428, S["over"], size=14, anchor="start", fill=RED, weight="700"))
    return fig("skills", W, H, "\n".join(b))


# =============================================================================
# 7 · SAFETY — safe by default
# =============================================================================
def f_safety(zh):
    W, H = 1180, 400
    S = {
        "title": "默认安全" if zh else "Safe by default",
        "sub": "危险动作默认拦截；结果过两道扫描；本体零暴露面" if zh
               else "Destructive actions blocked by default; results scanned twice; no attack surface",
        "c": ([("危险操作拦截", ["除非显式加 --destructive，", "删除类操作一律拒绝"], ic_lock),
               ("注入扫描", ["结果文本扫描", "prompt 注入特征"], ic_eye),
               ("凭据扫描", ["结果里出现 token / 密钥", "自动识别并告警"], ic_search),
               ("零暴露面", ["无遥测 · 不存凭证", "无守护进程 · 零依赖"], ic_shield)] if zh else
              [("Destructive blocked", ["Delete-class actions refused", "unless --destructive is passed"], ic_lock),
               ("Injection scan", ["Result text scanned for", "prompt-injection patterns"], ic_eye),
               ("Credential scan", ["Tokens and secrets in results", "are detected and flagged"], ic_search),
               ("No attack surface", ["No telemetry, no stored creds", "no daemon, zero dependencies"], ic_shield)]),
    }
    b = [t(590, 50, S["title"], size=28, weight="800"),
         t(590, 80, S["sub"], size=14.5, fill=GRAY)]
    for i in range(4):
        x = 50 + i * 277
        b.append(f'<rect x="{x}" y="112" width="254" height="204" rx="14" fill="#ffffff" stroke="{LINE}" filter="url(#soft)"/>')
        b.append(f'<rect x="{x}" y="112" width="254" height="72" rx="14" fill="url(#strip)"/>')
        b.append(f'<rect x="{x}" y="160" width="254" height="24" fill="url(#strip)"/>')
        b.append(f'<circle cx="{x+127}" cy="148" r="24" fill="#ffffff" opacity="0.20"/>')
        b.append(S["c"][i][2](x + 127, 148, c="#ffffff", s=1.3))
        b.append(t(x + 127, 216, S["c"][i][0], size=15.5, weight="800"))
        b.append(t(x + 127, 244, S["c"][i][1][0], size=13, fill=GRAY))
        b.append(t(x + 127, 264, S["c"][i][1][1], size=13, fill=GRAY))
        b.append(f'<rect x="{x+70}" y="284" width="114" height="5" rx="2.5" fill="{GREEN}"/>')
    b.append(f'<rect x="330" y="344" width="520" height="34" rx="10" fill="{GREEN_BG}"/>')
    b.append(t(590, 366, "Apache-2.0 · 只在本地跑 · 不联网也能用" if zh
               else "Apache-2.0 · runs locally · works with no network", size=14, fill=GREEN, weight="700"))
    return fig("safety", W, H, "\n".join(b))


# =============================================================================
# 8 · COMPAT — works with every agent
# =============================================================================
def f_compat(zh):
    W, H = 1180, 460
    S = {
        "title": "任何 AI Agent 都能用" if zh else "Works with every AI agent",
        "sub": "mcptoon 是 CLI。你的 Agent 能跑 shell 命令，就能用它。" if zh
               else "mcptoon is a CLI. If your agent can run a shell command, it can use mcptoon.",
        "h1": "Agent",
        "h2": "怎么接" if zh else "How to wire it up",
        "rows": ([("Claude Code", "把 mcptoon 命令写进 SKILL.md"), ("Codex (OpenAI)", "在 AGENTS.md 里加 mcptoon"),
                  ("Cursor", "在 .cursorrules 里加 mcptoon"), ("Windsurf", "在 .windsurfrules 里加 mcptoon"),
                  ("Gemini CLI", "在 GEMINI.md 里加 mcptoon"), ("任何 Agent", "能跑 shell 命令即可")] if zh else
                 [("Claude Code", "put mcptoon commands in SKILL.md"), ("Codex (OpenAI)", "add mcptoon to AGENTS.md"),
                  ("Cursor", "add mcptoon to .cursorrules"), ("Windsurf", "add mcptoon to .windsurfrules"),
                  ("Gemini CLI", "add mcptoon to GEMINI.md"), ("Any agent", "can run shell commands")]),
        "note": "在 ~/.mcptoon/config.json 配一次，所有 Agent 共享；自研格式不动线上协议。" if zh
                else "Configure once in ~/.mcptoon/config.json; custom formats never touch the wire protocol.",
    }
    b = [t(590, 50, S["title"], size=28, weight="800"),
         t(590, 80, S["sub"], size=14.5, fill=GRAY)]
    b.append(f'<rect x="90" y="104" width="1000" height="42" rx="11" fill="url(#strip)" filter="url(#soft)"/>')
    b.append('<circle cx="118" cy="125" r="5" fill="#ffffff" opacity="0.85"/>'
             '<circle cx="136" cy="125" r="5" fill="#ffffff" opacity="0.6"/>'
             '<circle cx="154" cy="125" r="5" fill="#ffffff" opacity="0.4"/>')
    b.append(t(590, 131, "mcptoon — 一份配置，所有 Agent 共享" if zh
               else "mcptoon — one config, shared by every agent", size=13.5, fill="#ffffff", weight="700"))
    MARK = [GREEN, BLUE, AMBER, "#8250df", GREEN, BLUE]
    for i in range(6):
        y = 156 + i * 42
        b.append(card(90, y, 1000, 36, rx=9, shadow=False, fill="#ffffff"))
        b.append(f'<rect x="90" y="{y}" width="6" height="36" rx="3" fill="{MARK[i]}"/>')
        b.append(f'<circle cx="122" cy="{y+18}" r="9" fill="{MARK[i]}" opacity="0.16"/>')
        b.append(f'<circle cx="122" cy="{y+18}" r="4.5" fill="{MARK[i]}"/>')
        b.append(t(146, y + 24, S["rows"][i][0], size=14, anchor="start", weight="700"))
        b.append(t(420, y + 24, S["rows"][i][1], size=13.5, anchor="start", fill=GRAY, mono=(i < 5)))
    b.append(f'<rect x="190" y="424" width="800" height="34" rx="10" fill="{GREEN_BG}"/>')
    b.append(t(590, 446, S["note"], size=13.5, fill=GREEN, weight="700"))
    return fig("compat", W, H, "\n".join(b))


FIGS = [f_hero, f_tax, f_bench, f_sync, f_loop, f_skills, f_safety, f_compat]
# explicit output names (the benchmark figure is `fig-benchmark-*`, not `fig-bench-*`)
NAMES = {"hero": "hero", "tax": "tax", "bench": "benchmark", "sync": "sync",
         "loop": "loop", "skills": "skills", "safety": "safety", "compat": "compat"}


def main():
    os.makedirs(OUT, exist_ok=True)
    # drop stale outputs from an earlier naming scheme
    for old in os.listdir(OUT):
        if re.match(r"^fig-(bench|hero|tax|sync|loop|skills|safety|compat)-", old) and not re.match(
                r"^fig-(hero|tax|benchmark|sync|loop|skills|safety|compat)-(en|zh)\.svg$", old):
            os.remove(os.path.join(OUT, old))
            print(f"  removed stale {old}")
    n = 0
    for fn in FIGS:
        name = NAMES[fn.__name__[2:]]
        for zh, suf in ((False, "en"), (True, "zh")):
            svg = fn(zh)
            p = os.path.join(OUT, f"fig-{name}-{suf}.svg")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(svg)
            print(f"  {os.path.basename(p):<24} {len(svg):>6} bytes")
            n += 1
    print(f"\n{n} files -> {OUT}")


if __name__ == "__main__":
    main()
