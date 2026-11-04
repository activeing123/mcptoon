# Copyright 2025-2026 activeing123
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""`doctor` must tell the user whether the savings badge is actually visible.

`doctor` tested every server and every config path but never asked the one
question a healthy-but-invisible install raises: is the status-line badge on a
status bar, or is the user paying for a tool they never see? `mode.statusline_status()`
existed for exactly this and was never called from `doctor` (found 2026-10-19).

Not being wired is a CHOICE, not a fault — only Claude Code auto-supports a status
bar — so the check is informational and must never bump the issue count or the
exit code.
"""
import io
import json
import os
from contextlib import redirect_stdout
from unittest.mock import patch

from mcptoon import cli
from mcptoon import config as cfg
from mcptoon import manifest as manifest_mod
from mcptoon import mode as mode_mod


def _run_doctor(tmp_path, statusline_result, *, as_json=False):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    servers = {"good": {"transport": "stdio"}}
    buf = io.StringIO()
    code = 0
    argv = ["--json"] if as_json else []
    with patch.object(cfg, "CONFIG_FILE", config_file), \
         patch.object(cfg, "CACHE_DIR", tmp_path / "cache"), \
         patch.object(cfg, "load_config", return_value=servers), \
         patch.object(cfg, "has_config_file", return_value=True), \
         patch.object(manifest_mod, "get_server_tools",
                      side_effect=lambda name, use_cache=True: [{"name": "a"}]), \
         patch.object(mode_mod, "statusline_status", return_value=statusline_result), \
         patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}), \
         redirect_stdout(buf):
        try:
            cli._cmd_doctor(argv, json_mode=as_json)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return buf.getvalue(), code


def test_doctor_reports_wired_status_line(tmp_path):
    out, code = _run_doctor(tmp_path, {
        "wired": True, "path": "C:/x/settings.json", "file_exists": True})
    assert "Status line: wired" in out
    assert code == 0


def test_doctor_teaches_install_when_settings_exist_but_not_wired(tmp_path):
    """The key case: Claude Code is present, badge is not wired — say how to fix."""
    out, code = _run_doctor(tmp_path, {
        "wired": False, "path": "C:/x/settings.json", "file_exists": True})
    assert "Status line: not wired" in out
    assert "mcptoon statusline --install" in out
    # Informational only: a missing badge is not a health issue.
    assert code == 0


def test_doctor_handles_no_claude_code_gracefully(tmp_path):
    out, code = _run_doctor(tmp_path, {
        "wired": False, "path": "C:/x/settings.json", "file_exists": False})
    assert "Status line" in out
    assert code == 0


def test_statusline_check_never_bumps_the_issue_count(tmp_path):
    """A not-wired badge must not turn a healthy machine red."""
    raw, code = _run_doctor(tmp_path, {
        "wired": False, "path": "C:/x/settings.json", "file_exists": True},
        as_json=True)
    data = json.loads(raw)
    assert data["issues"] == 0
    assert data["ok"] is True
    assert code == 0
    names = [c["name"] for c in data["checks"]]
    assert "statusline" in names
