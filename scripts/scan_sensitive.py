#!/usr/bin/env python3
"""Thin entry point for conservative static scanning."""

from _vendor.lch.cli import scan_main


if __name__ == "__main__":
    raise SystemExit(scan_main())

