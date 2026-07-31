#!/usr/bin/env python3
"""Render README.md to HTML and open in browser."""
import markdown
import webbrowser
import os

here = os.path.dirname(os.path.abspath(__file__))
md_path = os.path.join(here, "README.md")
html_path = os.path.join(here, "preview.html")

md_text = open(md_path, encoding="utf-8").read()
html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "codehilite", "toc"])

html_full = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>mcptoon — README Preview</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    max-width: 980px;
    margin: 0 auto;
    padding: 48px 32px;
    background: #fff;
    color: #24292f;
    line-height: 1.6;
  }}
  h1 {{ font-size: 2em; font-weight: 600; padding-bottom: .3em; border-bottom: 1px solid #d0d7de; }}
  h2 {{ font-size: 1.5em; font-weight: 600; padding-bottom: .3em; border-bottom: 1px solid #d0d7de; margin-top: 32px; }}
  h3 {{ font-size: 1.25em; font-weight: 600; margin-top: 24px; }}
  p {{ margin-bottom: 16px; }}
  a {{ color: #0969da; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 85%;
    background: #eff1f3;
    padding: .2em .4em;
    border-radius: 6px;
  }}
  pre {{
    background: #f6f8fa;
    border-radius: 8px;
    padding: 16px;
    overflow: auto;
    margin-bottom: 16px;
  }}
  pre code {{
    background: none;
    padding: 0;
    font-size: 85%;
    line-height: 1.45;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    display: block;
    overflow: auto;
  }}
  th, td {{
    border: 1px solid #d0d7de;
    padding: 6px 13px;
  }}
  th {{ font-weight: 600; background: #f6f8fa; }}
  tr:nth-child(even) {{ background: #f6f8fa; }}
  blockquote {{
    padding: 0 1em;
    color: #57606a;
    border-left: .25em solid #d0d7de;
    margin: 0 0 16px 0;
  }}
  hr {{ border: 0; border-bottom: 1px solid #d0d7de; margin: 24px 0; }}
  strong {{ font-weight: 600; color: #1f2328; }}
  img {{ max-width: 100%; }}
  div[style*="text-align: center"] h1 {{
    border: none;
    text-align: center;
  }}
  ul, ol {{ padding-left: 2em; margin-bottom: 16px; }}
  li {{ margin-top: .25em; }}
  em {{ color: #57606a; }}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_full)

webbrowser.open("file:///" + html_path.replace("\\", "/"))
print(f"Preview opened: {html_path}")
