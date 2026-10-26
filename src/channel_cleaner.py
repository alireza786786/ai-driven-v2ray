#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/channel_cleaner.py — پایشگر و پالایشگر خودکار لیست کانال‌های تلگرام.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

عملکرد:
  ۱) خواندن لیست خام کانال‌ها از data/channels.txt
  ۲) راستی‌آزمایی برخط دسترس‌پذیری کانال (شناسایی کانال‌های حذف‌شده، خصوصی یا بن‌شده)
  ۳) تفکیک خودکار به:
     • data/channels_cleaned.txt (کانال‌های عمومی فعال و زنده)
     • data/invalid_channels.txt (کانال‌های نامعتبر یا غیرقابل دسترس)
     • data/channel_report.txt (گزارش آماری دقیق وضعیت کانال‌ها)
  ۴) اجرای هم‌روند با ThreadPoolExecutor جهت پالایش سریع بدون افت سرعت خط‌لوله
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set, Tuple
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("channel_cleaner")

RAW_CHANNELS_FILE = Path("data/channels.txt")
CLEANED_CHANNELS_FILE = Path("data/channels_cleaned.txt")
INVALID_CHANNELS_FILE = Path("data/invalid_channels.txt")
CHANNEL_REPORT_FILE = Path("data/channel_report.txt")

FETCH_TIMEOUT = 10
MAX_WORKERS = 20

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
)


def sanitize_channel_name(raw: str) -> str:
    """نرمال‌سازی و پاک‌سازی آدرس کانال."""
    clean = raw.strip()
    clean = clean.replace("https://t.me/", "").replace("http://t.me/", "")
    clean = clean.replace("t.me/", "").replace("@", "")
    clean = clean.split("/")[0].split("?")[0].strip()
    return clean


def verify_channel(channel: str) -> Tuple[str, bool, str]:
    """بررسی زنده وضعیت کانال در تلگرام وب (t.me/s/...)."""
    if not channel or len(channel) < 4:
        return channel, False, "نامعتبر (طول بسیار کوتاه)"

    if not re.match(r"^[A-Za-z0-9_]{4,32}$", channel):
        return channel, False, "فرمت شناسه نامعتبر"

    url = f"https://t.me/s/{channel}"
    headers = {"User-Agent": USER_AGENTS[hash(channel) % len(USER_AGENTS)]}

    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        if resp.status_code == 404:
            return channel, False, "کانال یافت نشد (HTTP 404)"
        if resp.status_code != 200:
            return channel, False, f"خطای HTTP {resp.status_code}"

        text = resp.text

        if "tgme_page_icon" in text and "tgme_head" not in text:
            return channel, False, "کانال خصوصی یا حذف شده است"

        if "tgme_channel_info" not in text and "tgme_page_title" not in text:
            return channel, False, "فاقد محتوای پابلیک"

        return channel, True, "فعال و عمومی"
    except Exception as e:
        return channel, False, f"تایم‌اوت یا خطای شبکه ({type(e).__name__})"


def main():
    if not RAW_CHANNELS_FILE.exists():
        RAW_CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        RAW_CHANNELS_FILE.write_text(
            "# لیست کانال‌های تلگرام جهت واکشی کانفیگ\n"
            "# هر خط یک آدرس کانال (بدون @ یا با @)\n"
            "Goodbaye_filtering\n",
            encoding="utf-8",
        )
        logger.info(f"ℹ️ فایل {RAW_CHANNELS_FILE} ایجاد شد.")

    raw_lines = RAW_CHANNELS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
    candidates: Set[str] = set()

    for line in raw_lines:
        clean = sanitize_channel_name(line)
        if clean and not clean.startswith("#"):
            candidates.add(clean)

    if not candidates:
        logger.info("هیچ کانالی در channels.txt یافت نشد.")
        return

    logger.info(f"🔍 شروع پایش و سلامت‌سنجی {len(candidates)} کانال تلگرام...")
    t0 = time.time()

    valid_channels: List[str] = []
    invalid_channels: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(verify_channel, ch): ch for ch in sorted(candidates)}
        for fut in as_completed(futures):
            ch, is_ok, reason = fut.result()
            if is_ok:
                valid_channels.append(ch)
                logger.info(f"  ✅ @{ch:<25} ➔ {reason}")
            else:
                invalid_channels[ch] = reason
                logger.warning(f"  ❌ @{ch:<25} ➔ {reason}")

    valid_channels.sort()
    elapsed = round(time.time() - t0, 2)

    CLEANED_CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CLEANED_CHANNELS_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Cleaned Active Telegram Channels — Total: {len(valid_channels)}\n")
        f.write(f"# Verified on: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n")
        for ch in valid_channels:
            f.write(f"{ch}\n")

    with open(INVALID_CHANNELS_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Invalid or Inaccessible Telegram Channels — Total: {len(invalid_channels)}\n")
        for ch, reason in sorted(invalid_channels.items()):
            f.write(f"{ch:<30} # {reason}\n")

    report_content = (
        f"═══════════════════════════════════════════════════════════════\n"
        f"📋 گزارش پایش کانال‌های تلگرام Goodbaye Universal Standard\n"
        f"═══════════════════════════════════════════════════════════════\n"
        f"• تاریخ بررسی: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        f"• زمان اجرا: {elapsed} ثانیه\n"
        f"• کل کانال‌های ورودی: {len(candidates)}\n"
        f"• کانال‌های سالم و فعال: {len(valid_channels)}\n"
        f"• کانال‌های غیرفعال/نامعتبر: {len(invalid_channels)}\n"
        f"• نرخ سلامت کانال‌ها: {round(100.0 * len(valid_channels) / len(candidates), 2)}%\n"
        f"═══════════════════════════════════════════════════════════════\n"
    )
    CHANNEL_REPORT_FILE.write_text(report_content, encoding="utf-8")
    logger.info(f"✅ پایش کانال‌ها پایان یافت ({len(valid_channels)} سالم از {len(candidates)} کانال).")


if __name__ == "__main__":
    main()
