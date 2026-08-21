import json, urllib.request, subprocess, os
s = open(os.path.expanduser("~/.bw_session")).read().strip()
r = subprocess.run(["bw.cmd","get","password","MCPCLI_GITHUB_TOKEN","--session",s],
                    capture_output=True, text=True, shell=True)
t = r.stdout.strip()
req = urllib.request.Request("https://api.github.com/repos/activeing123/mcptoon/actions/runs?per_page=3")
req.add_header("Accept","application/vnd.github.v3+json")
req.add_header("Authorization",f"Bearer {t}")
resp = urllib.request.urlopen(req)
runs = json.load(resp)
for r in runs["workflow_runs"]:
    sha = r["head_sha"][:7]
    name = r["name"]
    status = r["conclusion"] or r["status"]
    msg = r["head_commit"]["message"].splitlines()[0][:50]
    print(f"{sha} | {name:20s} | {status:12s} | {msg}")
    if r["conclusion"] and r["name"] == "CI":
        run_id = r["id"]
        req2 = urllib.request.Request(f"https://api.github.com/repos/activeing123/mcptoon/actions/runs/{run_id}/jobs")
        req2.add_header("Accept","application/vnd.github.v3+json")
        req2.add_header("Authorization",f"Bearer {t}")
        resp2 = urllib.request.urlopen(req2)
        jobs = json.load(resp2)
        for j in jobs["jobs"]:
            jc = j["conclusion"]
            m = "X" if jc == "failure" else "V" if jc == "success" else "?" if jc != "cancelled" else "-"
            print(f"  [{m}] {j['name']} -> {jc}")
