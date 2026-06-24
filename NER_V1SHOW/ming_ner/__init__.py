"""Local package shim for running the src-layout project without installation."""

from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "ming_ner"
if _SRC_PACKAGE.exists():
    __path__.append(str(_SRC_PACKAGE))

__version__ = "0.1.0"
