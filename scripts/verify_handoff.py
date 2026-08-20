#!/usr/bin/env python3
"""Thin entry point for deterministic result issuance."""

from _vendor.lch.cli import verify_main


if __name__ == "__main__":
    raise SystemExit(verify_main())

