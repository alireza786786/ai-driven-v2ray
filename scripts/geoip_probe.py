#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/geoip_probe.py — بازرس متادیتای باینری دیتابیس MMDB و نگهبان ضدِ مسمومیت کَش گیت‌هاب اکشنز.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

هدف این اسکریپت:
  • مهار باگ اولِ ماه در گیت‌هاب اکشنز (جلوگیری از کَش شدن دیتابیس ماه قبل به جای ماه جاری)
  • داوری بر اساس بایت‌های واقعی محتوا (خواندن مستقیم فیلد باینری build_epoch) نه بر اساس نام کلید
  • تست سلامت داده با بررسی دو IP مرجع جهانی (8.8.8.8 برای آمریکا و 1.1.1.1 برای استرالیا)
  • خروج همیشگی با کد ۰ جهت عدم توقف پایپ‌لاین در زیرمجموعه خط فرمان‌های سخت‌گیرانه (set -euo pipefail)
"""

from __future__ import annotations

import datetime
import os
import sys
from typing import Optional, Tuple

#: کمینه اندازه مجاز فایل دیتابیس سالم (بایت)
MIN_SIZE: int = 1_000_000

#: نوع رسمی و مورد انتظار پایگاه داده DB-IP
EXPECTED_TYPE: str = "DBIP-Country-Lite"

#: آزمون‌های مرجع سلامت محتوای دیتابیس
SANITY: Tuple[Tuple[str, str], ...] = (
    ("8.8.8.8", "US"),
    ("1.1.1.1", "AU"),
)


def month_of_epoch(epoch: int) -> str:
    """تبدیل باینری build_epoch به فرمت تاریخ تقویمی YYYY-MM در ساعت هماهنگ جهانی (UTC)."""
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc
    ).strftime("%Y-%m")


def inspect_database(path: str) -> Tuple[str, str]:
    """
    بازرسی سلامت درونی فایل mmdb و استخراج سال-ماه انتشار.
    این تابع تحت هیچ شرایطی استثنا پرتاب نمی‌کند.
    """
    if not os.path.isfile(path):
        return "absent", ""
    try:
        if os.path.getsize(path) < MIN_SIZE:
            return "absent", ""
    except OSError:
        return "absent", ""

    try:
        import maxminddb  # noqa: PLC0415
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        return "corrupt", ""


def probe(path: str, want: str = "") -> Tuple[str, str]:
    """بررسی اینکه آیا نسخه لودشده متعلق به همان ماه تقویمی مدنظر است یا خیر."""
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
    except Exception:  # noqa: BLE001
        status, ym = "corrupt", ""
    print(f"status={status}")
    print(f"ym={ym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
