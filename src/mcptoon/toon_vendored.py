# Copyright 2025-2026 cxh (mcptoon wrapper)
# Vendored TOON encoder/decoder: Copyright (c) 2025 Xavi Vinaixa (xaviviro)
# Source: https://github.com/xaviviro/python-toon (MIT License)
# Vendored under MIT License — see NOTICE for full attribution.
#
# python-toon **v0.2.0** — the release that declares `toon-spec: 4.1` conformance.
#   0.1.1 (2025-10-30)  ← what we shipped until 2026-10-02
#   0.2.0 (2026-09-29)  ← what we ship now; release note: "conform to TOON spec 4.1"
# Upstream layout: https://github.com/toon-format/toon — official TypeScript reference.
# Upstream spec:    https://github.com/toon-format/spec — toon-spec 4.1
#
# Upstream ships a package (encoder/decoder/encoders/normalize/primitives/types/
# writer/constants); those files live verbatim in `_toon/`. **This module is only a
# facade** — its whole job is to carry the two mcptoon-specific patches below and keep
# the call sites in `output.py` unchanged.
#
# mcptoon patches (deliberately kept OUT of `_toon/` so re-vendoring stays mechanical):
#   1. Non-strict decode by default. Upstream's DecodeOptions defaults `strict=True`
#      and raises on anything ambiguous; mcptoon must survive real-world tool output,
#      so we flip the default to lenient.
#   2. Empty input returns {} instead of raising. `mcptoon decode` on a blank/garbage
#      payload must yield an empty mapping, not blow up a user's pipeline.

"""Vendored TOON (Token-Oriented Object Notation) encoder/decoder for mcptoon.

Implements the TOON spec v4.1 (toon-format/spec).
- encode(): JSON → TOON (spec-compliant, round-trip safe)
- decode(): TOON → JSON (lenient by default)

Source: python-toon v0.2.0 by Xavi Vinaixa (MIT License), vendored in `_toon/`.
"""

from __future__ import annotations

from ._toon import ToonDecodeError
from ._toon import encode as _upstream_encode
from ._toon import decode as _upstream_decode
from ._toon.types import DecodeOptions, EncodeOptions

__all__ = ["encode", "decode", "ToonDecodeError", "DecodeOptions", "EncodeOptions"]

# The exact upstream version vendored in _toon/ — bump it in the same commit that
# refreshes _toon/, so a stale claim can't outlive the code (2026-10-02: the docs used
# to advertise spec v4.1 while shipping 0.1.1, which predates v4.1 conformance).
VENDORED_VERSION = "0.2.0"
TOON_SPEC_VERSION = "4.1"


def encode(value, options=None):
    """Encode a JSON-compatible value as TOON. Spec-compliant, round-trip safe."""
    return _upstream_encode(value, options)


def decode(input_str, options=None):
    """Decode TOON text (or UTF-8 bytes) to a Python value.

    mcptoon-specific defaults: non-strict, and empty input yields {} instead of
    raising. Pass `options` to override (a dict or a DecodeOptions).
    """
    if not input_str or not input_str.strip():
        return {}

    if options is None:
        options = DecodeOptions(strict=False)
    elif isinstance(options, dict):
        options = DecodeOptions(
            indent=options.get("indent", 2),
            strict=options.get("strict", False),
        )

    return _upstream_decode(input_str, options)
