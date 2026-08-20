# Zero Dependencies, 250KB, 486 Tests: What I Learned Building an MCP Client

> This is not a product pitch. It's an engineering diary. If you want the pitch, [the README is here](https://github.com/activeing123/mcptoon). This is about the cost of zero.

---

## The setup

Six weeks ago I started building [mcptoon](https://github.com/activeing123/mcptoon) — a CLI tool that sits between AI agents (Claude Code, Cursor, Codex) and MCP servers. The problem it solves: MCP tool schemas get injected into your context window as JSON. 255 tools = ~91K tokens of JSON braces, brackets, quotes, and commas — before any actual work happens.

mcptoon keeps schemas out of context. The agent runs shell commands. Only the compact result enters context.

But none of that is what I want to talk about.

I want to talk about the decision that shaped everything: **zero dependencies**.

```toml
# pyproject.toml
dependencies = []
```

Not "minimal dependencies." Not "few dependencies." **Zero.**

---

## Why zero?

The trigger was the [uv security incident](https://github.com/astral-sh/uv/issues/9423). A transitive dependency in a popular Python tool had a supply chain vulnerability. Thousands of projects were affected. Not because they did anything wrong — because someone upstream did something wrong.

I looked at my own `pip install` history. How many packages had I installed in the last year? Hundreds. Each one pulling in its own dependency tree. How many of those dependencies had I audited? Zero.

So when I started mcptoon, I made a rule: **no third-party imports. Python standard library only.**

This sounded reasonable in theory. In practice, it meant I was about to hand-roll a lot of things.

---

## The cost: What I had to build myself

### No `requests` → hand-write an HTTP client

The standard library has `http.client` and `urllib`. They work. But they're verbose. Here's what a POST request looks like with `urllib`:

```python
import json, urllib.request

def http_post(url, data, headers=None):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))
```

That's 8 lines. With `requests`, it would be 1:

```python
import requests
resp = requests.post(url, json=data, headers=headers, timeout=30)
```

**Cost: ~200 lines of HTTP plumbing** (streaming SSE, error handling, retry logic, auth). With `requests`, maybe 30 lines.

**Was it worth it?** For SSE (Server-Sent Events) parsing — yes, I learned how the protocol actually works. For basic HTTP — no, it was just plumbing.

### No `click` or `argparse` extensions → hand-write CLI parsing

Python's stdlib `argparse` is... fine. But `click` is so much nicer. Decorators, subcommands, context, help text generation. With `argparse`, I ended up with a 400-line CLI dispatch function:

```python
def main():
    parser = argparse.ArgumentParser(prog="mcptoon")
    sub = parser.add_subparsers(dest="command")
    
    # ... 15 subcommands, each with its own args ...
    
    add_cmd = sub.add_parser("add")
    add_cmd.add_argument("name")
    add_cmd.add_argument("--stdio", nargs="+")
    add_cmd.add_argument("--url")
    # ... etc for every command
```

**Cost: ~400 lines of argument parsing.** With `click`, maybe 150 lines.

### No `pydantic` → hand-write validation

MCP servers return JSON. Without `pydantic`, every response is a `dict` and you validate by hand:

```python
def validate_tool_result(result):
    if not isinstance(result, dict):
        raise ValueError("Expected dict")
    if "content" not in result:
        raise ValueError("Missing 'content'")
    for item in result["content"]:
        if "type" not in item:
            raise ValueError("Each content item needs 'type'")
        if item["type"] == "text" and "text" not in item:
            raise ValueError("text content missing 'text' field")
```

**Cost: ~300 lines of validation across the codebase.** With `pydantic`, models would self-validate.

### No `rich` → hand-write terminal formatting

This one actually surprised me. I didn't need `rich`. ANSI escape codes work fine:

```python
def bold(text): return f"\033[1m{text}\033[0m"
def green(text): return f"\033[32m{text}\033[0m"
def dim(text): return f"\033[2m{text}\033[0m"
```

**Cost: ~50 lines.** Not bad.

### No `pytest` plugins → plain `unittest`-style tests

Actually, I do use `pytest` as a dev dependency (in `[project.optional-dependencies]`). But no `pytest-mock`, no `pytest-cov`, no `responses`, no `httpx` for mocking. Just `unittest.mock`:

```python
from unittest.mock import patch, MagicMock

@patch("mcptoon.client.MCPClient._stdio_request")
def test_call_tool(mock_request):
    mock_request.return_value = {"result": {"content": [{"type": "text", "text": "hello"}]}}
    client = MCPClient(stdio=["echo", "test"])
    result = client.call_tool("search", {"q": "test"})
    assert result["content"][0]["text"] == "hello"
```

**Cost: More verbose test setup.** But 486 tests still run in 0.5 seconds because there are no heavy fixtures.

---

## The payoff: What zero dependencies bought me

### 1. Install size: 250KB

```bash
$ pip install mcptoon
# Downloaded 250KB. Installed in 0.3s.
```

For comparison, a typical MCP client with `requests`, `pydantic`, `click`, `rich`:
- `requests` + its deps: ~5MB
- `pydantic` + its deps: ~15MB
- `click`: ~200KB
- `rich`: ~5MB
- Total: ~25MB

mcptoon is **1% of that**.

### 2. Security audit surface: zero

```bash
$ pip audit mcptoon
# No vulnerabilities found.
# (Because there's nothing to audit beyond stdlib.)
```

When the next supply chain attack hits npm or PyPI, mcptoon users are unaffected. Not because I was clever — because there's nothing to attack.

### 3. Cross-platform: actually works on Windows

Most Python CLI tools are developed on macOS/Linux and "should work on Windows." With zero dependencies, there are no platform-specific binary wheels to worry about. No `uvloop` that doesn't support Windows. No `uvicorn` worker model differences. Just `sys.platform` checks for `.cmd` vs binary names:

```python
def _resolve_cmd(cmd):
    if sys.platform == "win32" and not cmd[0].endswith(".cmd"):
        if shutil.which(cmd[0] + ".cmd"):
            cmd = [cmd[0] + ".cmd"] + cmd[1:]
    return cmd
```

mcptoon works on Windows, macOS, and Linux. Not "should work" — "tested on all three."

### 4. Install speed

```bash
$ time pip install mcptoon
# real    0m0.3s

$ time pip install <competitor-with-20-deps>
# real    0m12.4s
```

When your CI runs 1000 times a day, 12 seconds per install adds up.

### 5. Trust

When someone reads your source and sees `import json, subprocess, urllib.request, argparse` — they understand it. There's no `import magical_toolkit` that does something opaque. The entire codebase is readable by anyone who knows Python.

This matters for adoption. Developers who care about security (and MCP users tend to) can audit your code in an afternoon. They don't need to audit 30 transitive dependencies.

---

## When zero dependencies is NOT worth it

I'm not going to pretend zero dependencies is always the right choice. Here's when it hurts:

**When you're building a web app.** You need a router, a template engine, a database ORM, session management. Hand-writing all of these is insane. Use Django, FastAPI, Flask.

**When the problem is already solved well.** `json` parsing? Use stdlib. HTTP/2? Use `httpx` or `h2` — the protocol is complex enough that a hand-rolled implementation will have bugs.

**When your team is larger than one.** Zero dependencies means everyone needs to understand the entire stack. With libraries, you can treat them as black boxes. That scales better with team size.

**When you need to move fast.** Zero dependencies means writing more code. More code means more bugs. If you're racing to market, use libraries.

For mcptoon, it was the right choice because:
1. It's a CLI tool, not a web app — scope is bounded
2. The core problem (JSON encoding/decoding, HTTP, subprocess) is well-defined
3. It's security-sensitive — it handles credentials and tool results
4. Small enough for one person to maintain
5. The zero-dependency story IS the marketing — it's not just engineering, it's product

---

## The unexpected lesson: Zero dependencies made me a better programmer

This is going to sound like a motivational poster. Bear with me.

When you use `requests.post()`, you don't think about:
- What HTTP version is being used
- How redirects are followed
- What happens when the connection drops mid-response
- How SSL verification works

When you hand-write HTTP, you have to understand all of it.

When you use `pydantic`, you don't think about:
- What happens when a field is `None` vs missing
- How nested validation works
- What the error messages look like for users

When you hand-write validation, you own all of it.

When you use `click`, you don't think about:
- How subcommands are dispatched
- How help text is generated
- How arguments are parsed from `sys.argv`

When you hand-write CLI parsing, you understand your own interface.

I'm not saying you should never use libraries. I'm saying: **if you've never built something with zero dependencies, you should try it at least once.** The things you learn about the tools you use every day are worth the extra code.

---

## The numbers

After six weeks of zero-dependency development:

| Metric | Value |
|--------|-------|
| Source size | ~250KB |
| Lines of code | ~6,400 |
| Tests | 486 |
| Test runtime | 0.5s |
| Dependencies | 0 |
| Install time | 0.3s |
| GitHub stars | 177 |
| PyPI versions | 8 (v0.1.0 → v0.5.1) |
| Security vulnerabilities | 0 |

The most surprising number is the test runtime. 486 tests in 0.5 seconds. No fixtures to load, no mocking frameworks to initialize, no database to set up. Just pure Python functions. I can run the entire test suite before my terminal even finishes rendering the prompt.

---

## What's next

mcptoon v0.5.1 just shipped with `mcptoon serve` (stdio bridge mode) and `mcptoon demo` (zero-config one-command experience). The project is at 177 stars and growing.

The zero-dependency rule stays. It's not just an engineering decision — it's a promise to users: **when you install this tool, you get exactly what you see. No hidden code. No transitive surprises. No supply chain.**

If that resonates with you:

```bash
pip install mcptoon
```

Or [read the source](https://github.com/activeing123/mcptoon). It's 250KB. You can audit it in an afternoon.

---

*This is an independent project. Not affiliated with Anthropic. Apache 2.0 licensed. If you found it useful, a GitHub star helps others find it.*
