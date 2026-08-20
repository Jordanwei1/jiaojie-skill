#!/usr/bin/env python3
"""Thin entry point for frozen LTM Packet conversion."""

from _vendor.lch.cli import convert_main


if __name__ == "__main__":
    raise SystemExit(convert_main("ltm_packet"))

