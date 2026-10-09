# Tests for `doctor`'s plain-language server errors.
#
# The research point: the worst MCP failure is a server that silently does not
# work. `doctor` detected it, but printed a protocol string ("[RESPONSE_TIMEOUT]
# no JSON-RPC response for request id 2 within 30s") that only a protocol
# engineer can act on. These tests pin the translation table and the fact that
# the failing servers are named together at the end.
import contextlib
import io
import os
from unittest.mock import patch

from mcptoon import config as cfg
from mcptoon import manifest as manifest_mod
from mcptoon.cli import _cmd_doctor, _explain_server_error

class TestExplainServerError:
    def test_timeout_names_the_wait_not_the_id(self):
        reason, step = _explain_server_error(
            "RESPONSE_TIMEOUT: no JSON-RPC response for request id 2 within 30s "
            "(server went silent)")
        assert "never answered" in reason
        assert "request id" not in reason
        assert step  # always offers a next step

    def test_missing_command_blames_the_command(self):
        reason, _ = _explain_server_error(
            "PROCESS_DIED: [Errno 2] No such file or directory: 'npx'")
        assert "does not exist" in reason or "exited" in reason

    def test_permission_error_is_explained(self):
        reason, _ = _explain_server_error("PermissionError: [Errno 13] Access is denied")
        assert "refused" in reason

    def test_non_mcp_output_is_called_out(self):
        reason, _ = _explain_server_error("PROTOCOL_ERROR: request payload has no numeric id")
        assert "not in the MCP protocol" in reason

    def test_unknown_error_does_not_invent_a_cause(self):
        reason, step = _explain_server_error("something nobody has seen before")
        assert "could not be reached" in reason
        assert step  # still gives a way forward

    def test_empty_input_is_safe(self):
        reason, step = _explain_server_error("")
        assert reason and step


def _run_doctor(tmp_path, tools_by_server):
    """Run _cmd_doctor with a fake config and fake server tools; return stdout."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    servers = {name: {"transport": "stdio"} for name in tools_by_server}

    def fake_tools(name, use_cache=True):
        return tools_by_server[name]

    buf = io.StringIO()
    with patch.object(cfg, "CONFIG_FILE", config_file), \
         patch.object(cfg, "CACHE_DIR", cache_dir), \
         patch.object(cfg, "load_config", return_value=servers), \
         patch.object(cfg, "has_config_file", return_value=True), \
         patch.object(manifest_mod, "get_server_tools", side_effect=fake_tools), \
         patch.dict(os.environ, {"MCPTOON_NO_STAR_HINT": "1", "CI": ""}), \
         contextlib.redirect_stdout(buf):
        _cmd_doctor([])
    return buf.getvalue()


class TestDoctorPlainLanguage:
    def test_broken_server_gets_reason_and_next_step(self, tmp_path):
        out = _run_doctor(tmp_path, {
            "good": [{"name": "a"}, {"name": "b"}],
            "bad": [{"error": "RESPONSE_TIMEOUT: no JSON-RPC response for request id 2 "
                              "within 30s (server went silent)"}],
        })
        assert "never answered" in out
        assert "Run it once by hand" in out
        # the raw error is still shown - it names the real cause
        assert "RESPONSE_TIMEOUT" in out

    def test_broken_servers_are_summarised_together(self, tmp_path):
        out = _run_doctor(tmp_path, {
            "bad-one": [{"error": "RESPONSE_TIMEOUT: went silent"}],
            "bad-two": [{"error": "PROCESS_DIED: [Errno 2] No such file or directory"}],
        })
        assert "2 server(s) need attention" in out
        assert "bad-one" in out and "bad-two" in out
        assert "mcptoon inspect" in out

    def test_healthy_run_has_no_summary_block(self, tmp_path):
        out = _run_doctor(tmp_path, {"good": [{"name": "a"}]})
        assert "All good!" in out
        assert "need attention" not in out

    def test_a_server_with_zero_tools_is_not_a_failure(self, tmp_path):
        # started fine, just exposes nothing - a warning, not an issue
        out = _run_doctor(tmp_path, {"empty": []})
        assert "0 tools" in out
        assert "All good!" in out


class TestManifestErrorRendering:
    """`manifest` and `inspect` render the same failures; they must not drift
    back to the raw protocol string."""

    def test_format_manifest_explains_instead_of_echoing(self):
        out = manifest_mod.format_manifest({
            "bad": [{"error": "RESPONSE_TIMEOUT: no JSON-RPC response for request id 2 "
                              "within 30s (server went silent)"}]})
        assert "never answered" in out
        assert "→" in out            # a next step is always offered
        assert "RESPONSE_TIMEOUT" in out  # raw kept for the real cause

    def test_cli_delegates_to_the_one_table(self):
        assert _explain_server_error("PROCESS_DIED: boom") == \
               manifest_mod.explain_error("PROCESS_DIED: boom")
