#!/usr/bin/env python3
"""build_portable_zip.py · build the self-contained mcptoon zip for a release.

Why this exists
---------------
`microsoft/winget-pkgs` PR #443014 and the Chocolatey package both need a
**self-contained Windows artifact** per version. Only v0.8.3 ever had one; the
script that produced it was a one-shot with the version hardcoded and machine
paths baked in, so v0.8.4 .. v0.8.16 shipped with zero release assets and both
channels stalled on 0.8.3. This is that script, made version-generic and
repeatable, so every release produces its own zip.

Shape (proven by the v0.8.3 zip and the Chocolatey package, reused deliberately):

    mcptoon/
      python.exe, python313.dll, *.pyd, python313._pth ...   <- official CPython
      mcptoon/                                               <- official PyPI wheel
      mcptoon.exe                                            <- launcher (portable entry)
      mcptoon.cmd                                            <- same, for shells

Why not PyInstaller: mcptoon ships an MCP `serve` command and a `--pip` installer,
both of which spawn `sys.executable -m ...`. Under a frozen exe `sys.executable`
is the exe itself, so those paths break. Embedding the real interpreter keeps
`sys.executable` a real python.exe — the same reason the Chocolatey package chose
this shape over a frozen binary.

Usage
-----
    python scripts/build_portable_zip.py                    # version from pyproject.toml
    python scripts/build_portable_zip.py --version 0.8.16
    python scripts/build_portable_zip.py --wheel dist/*.whl # use a locally built wheel
    python scripts/build_portable_zip.py --upload           # attach it to the GitHub Release

`--upload` needs a token in `GITHUB_TOKEN` (CI sets this) or `GH_TOKEN`.

Exit codes: 0 = built (and uploaded, if asked); 1 = a self-check failed; 2 = setup error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

# ─── pinned inputs ───────────────────────────────────────────────────────────
# The embeddable CPython is the one moving part we do not build ourselves, so its
# bytes are pinned by hash. Bumping the version means bumping the hash here too;
# the assert below refuses to build from a zip that does not match.
EMBED_VERSION = "3.13.15"
EMBED_URL = (
    f"https://www.python.org/ftp/python/{EMBED_VERSION}/"
    f"python-{EMBED_VERSION}-embed-amd64.zip"
)
EMBED_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"

# No machine-local defaults: the repo is wherever we are run from, and the stage
# is a temp directory. This keeps the public tree free of local paths and lets
# the same script run unchanged on a developer box and on a CI runner.
DEFAULT_STAGE = pathlib.Path(tempfile.gettempdir()) / "mcptoon-portable"

LAUNCHER_CS = r"""
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;

class McptoonLauncher {
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern IntPtr CreateFileW(string f, uint access, uint share, IntPtr sa,
                                     uint disp, uint flags, IntPtr tmpl);
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern uint GetFinalPathNameByHandleW(IntPtr h, StringBuilder buf, uint cch, uint flags);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool CloseHandle(IntPtr h);

    // winget installs a *portable* package by symlinking Links\<name>.exe to the
    // real exe under Packages\. Launched that way, Assembly.Location and
    // MainModule.FileName both report the LINK path, so `next to the launcher`
    // resolves to Links\ — where python.exe is not. Resolve the link target.
    static string RealPath(string path) {
        try {
            IntPtr h = CreateFileW(path, 0, 7, IntPtr.Zero, 3 /*OPEN_EXISTING*/, 0x80, IntPtr.Zero);
            if (h == new IntPtr(-1)) return path;
            var sb = new StringBuilder(2048);
            uint n = GetFinalPathNameByHandleW(h, sb, (uint)sb.Capacity, 0);
            CloseHandle(h);
            if (n == 0) return path;
            string r = sb.ToString();
            if (r.StartsWith(@"\\?\UNC\")) return @"\\" + r.Substring(8);
            if (r.StartsWith(@"\\?\")) return r.Substring(4);
            return r;
        } catch { return path; }
    }

    static string ExePath() {
        try { return Process.GetCurrentProcess().MainModule.FileName; }
        catch { return Assembly.GetExecutingAssembly().Location; }
    }

    static int Main(string[] args) {
        // Resolve next to the launcher, not the caller's cwd: winget puts a shim
        // on PATH and runs it from anywhere, including through a symlink.
        string dir = Path.GetDirectoryName(RealPath(ExePath()));
        string py = Path.Combine(dir, "python.exe");
        if (!File.Exists(py)) {
            Console.Error.WriteLine("mcptoon: python.exe not found next to the launcher at " + dir);
            return 127;
        }
        var psi = new ProcessStartInfo(py);
        psi.Arguments = "-m mcptoon";
        foreach (string a in args) psi.Arguments += " " + Quote(a);
        psi.UseShellExecute = false;
        psi.WorkingDirectory = dir;
        try {
            var p = Process.Start(psi);
            p.WaitForExit();
            return p.ExitCode;
        } catch (Exception e) {
            Console.Error.WriteLine("mcptoon: failed to start the interpreter: " + e.Message);
            return 127;
        }
    }
    static string Quote(string s) {
        if (s.Length > 0 && s.IndexOfAny(new[] {' ', '\t', '"'}) < 0) return s;
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }
}
"""


def _proxy() -> str | None:
    """Standard proxy env vars only — CI has none, a developer box may set one."""
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None


def _fetch(url: str) -> bytes:
    handlers = []
    p = _proxy()
    if p:
        handlers.append(urllib.request.ProxyHandler({"https": p, "http": p}))
    req = urllib.request.Request(url, headers={"User-Agent": "mcptoon-portable-build"})
    return urllib.request.build_opener(*handlers).open(req, timeout=120).read()


def read_version(repo: pathlib.Path) -> str:
    """The version is the single source of truth in pyproject; never pass it twice."""
    import tomllib
    with open(repo / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def wheel_url(version: str) -> str:
    meta = json.loads(_fetch(f"https://pypi.org/pypi/mcptoon/{version}/json").decode())
    for u in meta["urls"]:
        if u["packagetype"] == "bdist_wheel":
            return u["url"]
    sys.exit(f"[2] no wheel on PyPI for mcptoon {version}")


def ensure_embeddable(art: pathlib.Path) -> pathlib.Path:
    z = art / f"python-{EMBED_VERSION}-embed-amd64.zip"
    if not z.exists():
        print(f"  downloading {EMBED_URL}")
        z.write_bytes(_fetch(EMBED_URL))
    got = hashlib.sha256(z.read_bytes()).hexdigest()
    if got != EMBED_SHA256:
        sys.exit(f"[2] embeddable sha256 mismatch\n  got  {got}\n  want {EMBED_SHA256}")
    return z


def build_launcher(build: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    cs = build / "launcher.cs"
    cs.write_text(LAUNCHER_CS, encoding="utf-8")
    csc = pathlib.Path(os.environ.get(
        "CSC",
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"))
    if not csc.exists():
        sys.exit(f"[2] csc.exe not found at {csc} (set CSC to override)")
    exe = root / "mcptoon.exe"
    r = subprocess.run([str(csc), "/nologo", "/target:exe", f"/out:{exe}", str(cs)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not exe.exists():
        sys.exit(f"[1] csc failed:\n{r.stdout}\n{r.stderr}")
    (root / "mcptoon.cmd").write_text(
        '@echo off\r\n"%~dp0python.exe" -m mcptoon %*\r\n', encoding="ascii")
    return exe


def self_check(root: pathlib.Path, exe: pathlib.Path, version: str, build: pathlib.Path) -> None:
    """Prove the artifact runs *before* zipping it.

    Three probes, each catching a different failure the others cannot:
      - the embedded interpreter, which proves the wheel unpacked correctly;
      - the launcher directly, which proves the C# shim resolves python.exe;
      - the launcher through a symlink, which is how winget actually installs a
        portable package — the only probe that catches a launcher resolving its
        own link instead of the link target.
    """
    probe = subprocess.run([str(root / "python.exe"), "-m", "mcptoon", "--version"],
                           capture_output=True, text=True, cwd=root)
    if probe.returncode != 0 or version not in probe.stdout:
        sys.exit(f"[1] embedded interpreter failed: {probe.stdout!r} {probe.stderr[:400]}")
    print("  OK embedded :", probe.stdout.strip())

    probe_exe = subprocess.run([str(exe), "--version"], capture_output=True, text=True, cwd=root)
    if probe_exe.returncode != 0 or version not in probe_exe.stdout:
        sys.exit(f"[1] launcher failed: {probe_exe.stdout!r} {probe_exe.stderr[:300]}")
    print("  OK launcher :", probe_exe.stdout.strip())

    link_dir = build / "links"
    link_dir.mkdir(exist_ok=True)
    link = link_dir / "mcptoon.exe"
    try:
        link.symlink_to(exe)
    except OSError as e:
        print(f"  SKIP symlink probe (needs privilege): {e}")
        return
    pl = subprocess.run([str(link), "--version"], capture_output=True, text=True, cwd=link_dir)
    link.unlink()
    if pl.returncode != 0 or version not in pl.stdout:
        sys.exit(f"[1] launcher broke through a symlink (the winget install path): "
                 f"{pl.stdout!r} {pl.stderr[:300]}")
    print("  OK symlink  :", pl.stdout.strip())


def upload(dist_zip: pathlib.Path, version: str, repo_slug: str = "activeing123/mcptoon") -> None:
    """Attach the zip to the GitHub Release over the REST API.

    Reads `GITHUB_TOKEN` (CI) or `GH_TOKEN`. Deliberately not `gh release upload`,
    which needs an interactive login and would not run unattended.
    """
    import urllib.error
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("[2] --upload needs GITHUB_TOKEN or GH_TOKEN in the environment")

    handlers = []
    p = _proxy()
    if p:
        handlers.append(urllib.request.ProxyHandler({"https": p, "http": p}))
    op = urllib.request.build_opener(*handlers)
    auth = {"User-Agent": "mcptoon-portable-build", "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token}

    def api(url: str, method: str = "GET", data: bytes | None = None, ctype: str | None = None):
        h = dict(auth)
        if ctype:
            h["Content-Type"] = ctype
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            return op.open(req, timeout=300)
        except urllib.error.HTTPError as e:
            return e

    rel = api(f"https://api.github.com/repos/{repo_slug}/releases/tags/v{version}")
    if getattr(rel, "code", 200) == 404:
        sys.exit(f"[1] no GitHub Release v{version} to attach to — create it first")
    release = json.loads(rel.read().decode())
    rid = release["id"]

    # Idempotent: the upload endpoint refuses a duplicate name with HTTP 422, so a
    # re-run of the workflow would fail on an asset it already created. Delete the
    # old one first — that is the "replace in place" the release ritual asks for.
    name = dist_zip.name
    for asset in release.get("assets", []):
        if asset["name"] == name:
            d = api(f"https://api.github.com/repos/{repo_slug}/releases/assets/{asset['id']}",
                    method="DELETE")
            if getattr(d, "code", 200) not in (200, 204):
                sys.exit(f"[1] could not delete the existing {name}: HTTP {d.code}")
            print(f"  replaced existing asset {name}")

    resp = api(f"https://uploads.github.com/repos/{repo_slug}/releases/{rid}/assets?name={name}",
               method="POST", data=dist_zip.read_bytes(), ctype="application/zip")
    if getattr(resp, "code", 200) not in (200, 201):
        body = resp.read().decode("utf-8", "replace")[:400]
        sys.exit(f"[1] asset upload failed: HTTP {resp.code} {body}")
    asset = json.loads(resp.read().decode())
    print(f"  uploaded: {asset['name']} ({asset['size']:,} bytes) -> {asset['browser_download_url']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the self-contained mcptoon zip.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default=None, help="default: read from pyproject.toml")
    ap.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    ap.add_argument("--stage", type=pathlib.Path, default=DEFAULT_STAGE)
    ap.add_argument("--wheel", type=pathlib.Path, default=None,
                    help="use this wheel instead of downloading from PyPI "
                         "(CI builds it from the tag, which avoids the publish race)")
    ap.add_argument("--upload", action="store_true", help="attach the zip to the GitHub Release")
    a = ap.parse_args()

    version = a.version or read_version(a.repo)
    art, build, dist = a.stage / "artifacts", a.stage / "build", a.stage / "dist"
    for d in (art, build, dist):
        d.mkdir(parents=True, exist_ok=True)
    for d in (build, dist):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    print(f"mcptoon portable zip — version {version}")
    print("  stage:", a.stage)

    # 1. official CPython embeddable
    py_zip = ensure_embeddable(art)
    root = build / "mcptoon"
    root.mkdir()
    with zipfile.ZipFile(py_zip) as z:
        z.extractall(root)

    # 2. the mcptoon wheel — CI passes one built from the tag; otherwise PyPI
    if a.wheel is not None:
        wheel = pathlib.Path(a.wheel)
        if not wheel.exists():
            sys.exit(f"[2] --wheel {wheel} does not exist")
        print(f"  using wheel: {wheel.name}")
    else:
        url = wheel_url(version)
        wheel = art / pathlib.Path(url).name
        if not wheel.exists():
            print(f"  downloading {wheel.name}")
            wheel.write_bytes(_fetch(url))
    with zipfile.ZipFile(wheel) as z:
        z.extractall(root)  # puts `mcptoon/` next to python.exe
    if not (root / "mcptoon" / "__main__.py").exists():
        sys.exit("[1] wheel did not unpack mcptoon/")

    # 3. launcher + 4. self-check
    exe = build_launcher(build, root)
    self_check(root, exe, version, build)

    # 5. zip
    out = dist / f"mcptoon-{version}-win-x64.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(root.rglob("*")):
            z.write(p, p.relative_to(build).as_posix())
    digest = hashlib.sha256(out.read_bytes()).hexdigest().upper()
    (dist / "sha256.txt").write_text(digest)
    print(f"  ZIP    {out}  {out.stat().st_size:,} bytes")
    print(f"  SHA256 {digest}")

    if a.upload:
        upload(out, version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
