"""Submit mcptoon to awesome-mcp-servers via GitHub API."""
import requests, json, base64, sys

token = sys.argv[1]
headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}

# 1. Get fork README
r = requests.get('https://api.github.com/repos/activeing123/awesome-mcp-servers/contents/README.md', headers=headers)
data = r.json()
readme_sha = data['sha']
content = base64.b64decode(data['content']).decode('utf-8')

# 2. Insert mcptoon entry before ## Frameworks
entry = '\n- [activeing123/mcptoon](https://github.com/activeing123/mcptoon) \U0001f40d \U0001f3e0 \U0001f34e \U0001f4bb \U0001f311 - Zero-dependency CLI that connects any AI agent to every MCP server. Configures once, syncs to all agents (`mcptoon sync`). 99.8% token savings on tool discovery (`mcptoon manifest --compact`). Security checks on every call. `pip install mcptoon`.\n'

idx = content.find('## Frameworks')
if idx > 0:
    new_content = content[:idx] + entry + '\n' + content[idx:]
else:
    new_content = content + entry

# 3. Commit
new_b64 = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
commit_data = {
    'message': 'Add mcptoon: zero-dependency CLI MCP client with 99.8% token savings',
    'content': new_b64,
    'sha': readme_sha,
    'branch': 'add-mcptoon'
}
r = requests.put('https://api.github.com/repos/activeing123/awesome-mcp-servers/contents/README.md', headers=headers, json=commit_data)
if r.status_code not in (200, 201):
    print(f'Commit failed: {r.status_code} {r.text[:200]}')
    sys.exit(1)
print(f'Committed successfully')

# 4. Create PR
pr_data = {
    'title': 'Add mcptoon: zero-dependency CLI MCP client with 99.8% token savings',
    'head': 'activeing123:add-mcptoon',
    'base': 'main',
    'body': """## What
Adds [mcptoon](https://github.com/activeing123/mcptoon) to the list -- a zero-dependency CLI that connects any AI agent to every MCP server.

## Why
- **99.8% token savings** on tool discovery (255 tools = 123 tokens vs 71,929 raw JSON)
- **Cross-agent sync**: one config for Claude Code, Cursor, Codex, Cline, Windsurf, etc.
- **Zero setup**: no MCP protocol config needed, any shell-capable agent works day one
- **Security**: injection/credential-leak/destructive-op guards on every call
- **531 tests**, pure Python stdlib, ~250KB, Apache 2.0

## Install
```bash
pip install mcptoon
```"""
}
r = requests.post('https://api.github.com/repos/punkpeye/awesome-mcp-servers/pulls', headers=headers, json=pr_data)
if r.status_code == 201:
    print(f'PR created: {r.json()["html_url"]}')
else:
    print(f'PR failed: {r.status_code} {r.text[:300]}')
