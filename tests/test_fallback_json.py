# -*- coding: utf-8 -*-
"""Tests for --fallback-json flag behavior."""
import json
import sys
from unittest.mock import patch, MagicMock

import pytest

from mcptoon.cli import _render_result
from mcptoon.output import render


class TestRenderResult:
    def test_normal_render_no_fallback(self):
        """Without fallback_json, should use requested format."""
        result = {"name": "test", "value": 42}
        with patch("builtins.print") as mock_print:
            _render_result(result, fmt="json", head_n=0, max_chars=0, full=True, fallback_json=False)
            mock_print.assert_called_once()
            printed = mock_print.call_args[0][0]
            assert json.loads(printed)["name"] == "test"

    def test_fallback_json_with_json_format(self):
        """With fmt=json, fallback_json should have no effect."""
        result = {"name": "test"}
        with patch("builtins.print") as mock_print:
            _render_result(result, fmt="json", head_n=0, max_chars=0, full=True, fallback_json=True)
            mock_print.assert_called_once()
            # Should just print normally, no fallback message
            assert "# fallback-json" not in mock_print.call_args[0][0]

    def test_fallback_json_with_toon_success(self):
        """fallback_json with successful toon encoding should print toon."""
        result = {"name": "test", "value": 42}
        with patch("builtins.print") as mock_print:
            _render_result(result, fmt="toon", head_n=0, max_chars=0, full=True, fallback_json=True)
            mock_print.assert_called_once()
            printed = mock_print.call_args[0][0]
            assert "name: test" in printed

    def test_fallback_json_with_toon_failure(self):
        """fallback_json should fall back to JSON when toon encoding fails."""
        result = {"complex": "data"}
        # First call (toon) raises ValueError, second call (json) succeeds
        with patch("mcptoon.cli.output.render", side_effect=[ValueError("encode error"), '{"complex": "data"}']):
            with patch("builtins.print") as mock_print:
                _render_result(result, fmt="toon", head_n=0, max_chars=0, full=True, fallback_json=True)
                # Should have printed fallback message to stderr and JSON to stdout
                assert mock_print.call_count >= 2
                # Verify the JSON fallback was printed
                json_output = mock_print.call_args[0][0]
                assert "complex" in json_output

    def test_fallback_json_with_auto_format(self):
        """fallback_json with auto format should not trigger fallback."""
        result = {"name": "test"}
        with patch("builtins.print") as mock_print:
            _render_result(result, fmt="auto", head_n=0, max_chars=0, full=True, fallback_json=True)
            mock_print.assert_called_once()

    def test_fallback_json_disabled_by_default(self):
        """fallback_json defaults to False."""
        result = {"name": "test"}
        with patch("builtins.print") as mock_print:
            _render_result(result, fmt="toon", head_n=0, max_chars=0, full=True)
            mock_print.assert_called_once()
            printed = mock_print.call_args[0][0]
            assert "name: test" in printed
