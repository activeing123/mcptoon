import urllib.request, json

repos = [
    'activeing123/mcptoon',
    'toon-format/toon',
    'theshadow27/mcp-cli',
]

for r in repos:
    try:
        url = f'https://api.github.com/repos/{r}'
        req = urllib.request.Request(url, headers={'User-Agent': 'mcptoon-check'})
        resp = urllib.request.urlopen(req)
        d = json.loads(resp.read())
        print(f"{r}:")
        print(f"  stars={d['stargazers_count']} forks={d['forks_count']} open_issues={d['open_issues_count']}")
        print(f"  created={d['created_at']} pushed={d['pushed_at']}")
        print(f"  description={d.get('description','')}")
        print()
    except Exception as e:
        print(f"{r}: ERROR {e}")
        print()
