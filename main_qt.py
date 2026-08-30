"""
Fylorra - Qt (PySide6) GUI

This is the next-generation UI for Fylorra.
It reuses the existing backend (core/) but replaces the Tk/CustomTkinter UI.
"""

from __future__ import annotations

import sys

from qt_app.app import run


def main() -> int:
    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
