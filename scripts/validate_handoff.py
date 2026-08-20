#!/usr/bin/env python3
"""Thin entry point for native validation."""

from _vendor.lch.cli import validate_main


if __name__ == "__main__":
    raise SystemExit(validate_main())

