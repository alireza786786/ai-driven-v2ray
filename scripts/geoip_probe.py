#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/geoip_probe.py — راستی‌آزمایی متادیتای باینری فایل MMDB و مهار باگ مسمومیت کَش.
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray
"""
from __future__ import annotations

import datetime
import os
import sys
from typing import Optional, Tuple

MIN_SIZE = 1_000_000
EXPECTED_TYPE = "DBIP-Country-Lite"
SANITY = (("8.8.8.8", "US"), ("1.1.1.1", "AU"))


def month_of_epoch(epoch: int) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m")


def inspect_database(path: str) -> Tuple[str, str]:
    if not os.path.isfile(path):
        return "absent", ""
    try:
        if os.path.getsize(path) < MIN_SIZE:
            return "absent", ""
    except OSError:
        return "absent", ""

    try:
        import maxminddb
    except Exception:
        return "unverifiable", ""

    try:
        with maxminddb.open_database(path) as reader:
            meta = reader.metadata()
            if meta.database_type != EXPECTED_TYPE:
                return "wrongtype", ""
            for ip, expected in SANITY:
                record = reader.get(ip)
                got = None
                if isinstance(record, dict):
                    country = record.get("country")
                    if isinstance(country, dict):
                        got = country.get("iso_code")
                if got != expected:
                    return "badlookup", ""
            return "ok", month_of_epoch(int(meta.build_epoch))
    except Exception:
        return "corrupt", ""


def probe(path: str, want: str = "") -> Tuple[str, str]:
    status, ym = inspect_database(path)
    if status != "ok":
        return status, ym
    if want and ym == want:
        return "current", ym
    return "stale", ym


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("status=absent")
        print("ym=")
        return 0
    path = args[0]
    want = args[1] if len(args) > 1 else ""
    try:
        status, ym = probe(path, want)
    except Exception:
        status, ym = "corrupt", ""
    print(f"status={status}")
    print(f"ym={ym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
