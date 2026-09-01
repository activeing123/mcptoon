#!/usr/bin/env bash
# mcptoon one-line installer (macOS / Linux / WSL / Git Bash)
#   curl -fsSL https://raw.githubusercontent.com/activeing123/mcptoon/main/install.sh | bash
set -eu

info() { printf '  \033[36m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m%s\033[0m\n' "$1"; }
err()  { printf '  \033[31m%s\033[0m\n' "$1" >&2; }

echo ""
echo "  mcptoon installer — zero-dependency MCP gateway"
echo "  ────────────────────────────────────────────────"

# 1. Find Python 3.10+
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    v=$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0)
    case "$v" in
      3.[1-9][0-9]*|3.1[0-9]|3.10) PY="$cand"; break ;;
    esac
  fi
done
if [ -z "$PY" ]; then
  err "Python 3.10+ not found. Install it first: https://www.python.org/downloads/"
  exit 1
fi
info "Found $PY (Python $("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])'))"

# 2. Install mcptoon (pipx → pip --user → venv fallback)
if command -v pipx >/dev/null 2>&1; then
  info "Installing via pipx..."
  pipx install mcptoon || pipx upgrade mcptoon
elif "$PY" -m pip install --user mcptoon 2>/tmp/mcptoon_pip_err; then
  ok "Installed via pip --user"
else
  if grep -qi "externally-managed" /tmp/mcptoon_pip_err 2>/dev/null; then
    info "PEP 668 environment detected — using a dedicated venv"
    "$PY" -m venv "$HOME/.mcptoon-venv"
    "$HOME/.mcptoon-venv/bin/pip" install -q mcptoon
    mkdir -p "$HOME/.local/bin"
    ln -sf "$HOME/.mcptoon-venv/bin/mcptoon" "$HOME/.local/bin/mcptoon"
    case ":$PATH:" in
      *":$HOME/.local/bin:"*) ;;
      *) export PATH="$HOME/.local/bin:$PATH" ;;
    esac
    ok "Installed into ~/.mcptoon-venv"
  else
    err "pip install failed:"; cat /tmp/mcptoon_pip_err >&2 || true
    exit 1
  fi
fi
rm -f /tmp/mcptoon_pip_err

# 3. Verify + hand off to quickstart
BIN="$(command -v mcptoon || echo "$HOME/.local/bin/mcptoon")"
if [ ! -x "$BIN" ] && ! command -v mcptoon >/dev/null 2>&1; then
  err "mcptoon not on PATH. Add ~/.local/bin to PATH and re-run: mcptoon quickstart"
  exit 1
fi
ok "mcptoon installed: $("$BIN" --version 2>/dev/null || echo ok)"
echo ""
exec "$BIN" quickstart
