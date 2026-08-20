#!/usr/bin/env python3
"""Thin entry point for frozen HANDOFF.md conversion."""

from _vendor.lch.cli import convert_main


if __name__ == "__main__":
    raise SystemExit(convert_main("handoff_markdown"))

