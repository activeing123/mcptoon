import json, urllib.request, subprocess, os, zipfile, io

s = open(os.path.expanduser("~/.bw_session")).read().strip()
r = subprocess.run(["bw.cmd","get","password","MCPCLI_GITHUB_TOKEN","--session",s],
                    capture_output=True, text=True, shell=True)
t = r.stdout.strip()

# Download logs for the latest run (eb31af8)
# First get the run ID
req = urllib.request.Request("https://api.github.com/repos/activeing123/mcptoon/actions/runs?per_page=1")
req.add_header("Accept","application/vnd.github.v3+json")
req.add_header("Authorization",f"Bearer {t}")
resp = urllib.request.urlopen(req)
runs = json.load(resp)
run_id = runs["workflow_runs"][0]["id"]
print(f"Run ID: {run_id}")

# Download logs zip
url = f"https://api.github.com/repos/activeing123/mcptoon/actions/runs/{run_id}/logs"
req = urllib.request.Request(url)
req.add_header("Accept","application/vnd.github.v3+json")
req.add_header("Authorization",f"Bearer {t}")

try:
    resp = urllib.request.urlopen(req)
    zip_data = resp.read()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        # Find the debug step log
        for name in sorted(zf.namelist()):
            if "debug" in name.lower() or ("windows" in name.lower() and "3.10" in name):
                print(f"\n=== {name} ===")
                content = zf.read(name).decode("utf-8", errors="replace")
                # Print lines with Debug or traceback
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if any(k in line.lower() for k in ["debug", "traceback", "error", "import", "module", "file", "path"]):
                        print(f"  {line[:300]}")
except Exception as e:
    print(f"Error: {e}")
