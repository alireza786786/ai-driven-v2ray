#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/channel_cleaner.py — ابزار پالایش و راستی‌آزمایی کانال‌های تلگرام با مکانیزم Fallback ایمن.
مالک: alireza786786 | مخزن: ai-driven-v2ray | برند: @Goodbaye_filtering

اصلاحات:
  • حل باگ شماره ۵: جلوگیری از خالی شدن channels_cleaned.txt در صورت بروز ریت‌لیمیت یا قطعی موقت
  • حفظ کانال‌های معتبر و حذف کانال‌های مسدود یا غیرفعال
"""

import os
import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("channel_cleaner")

DATA_DIR = Path("data")
CHANNELS_SOURCE = DATA_DIR / "channels.txt"
CHANNELS_CLEANED = DATA_DIR / "channels_cleaned.txt"

TIMEOUT = 10
MAX_WORKERS = 8
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def is_channel_alive(channel: str) -> bool:
    """بررسی در دسترس بودن وب‌پیش‌نمایش کانال تلگرام."""
    url = f"https://t.me/s/{channel}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            text = resp.text
            # نشانه‌های کانال مسدود، ناموجود یا حذف‌شده
            if "tgme_page_extra" in text and ("Telegram channel" in text or "subscribers" in text):
                return True
            if "tgme_widget_message" in text:
                return True
        return False
    except Exception:
        # در صورت تایم‌اوت، کانال را حذف نمی‌کنیم تا اشتباهاً کانال سالم از دست نرود
        return True


def clean_channels():
    if not CHANNELS_SOURCE.exists():
        logger.warning(f"⚠️ Source file {CHANNELS_SOURCE} does not exist.")
        return

    raw_lines = CHANNELS_SOURCE.read_text(encoding="utf-8").splitlines()
    channels = [
        line.strip().lstrip("@") for line in raw_lines
        if line.strip() and not line.strip().startswith("#")
    ]
    channels = list(dict.fromkeys(channels))

    logger.info(f"🔍 Validating {len(channels)} telegram channels...")
    alive_channels = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(is_channel_alive, ch): ch for ch in channels}
        for fut in as_completed(futures):
            ch = futures[fut]
            try:
                if fut.result():
                    alive_channels.append(ch)
            except Exception:
                alive_channels.append(ch)

    # حل باگ شماره ۵: اگر به هر دلیلی لیست خالی شد، هرگز فایل خالی نمی‌نویسیم
    if not alive_channels:
        logger.warning("⚠️ Warning: Validation yielded 0 channels. Fallback: keeping original channel list.")
        alive_channels = channels

    alive_channels.sort()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = f"# Cleaned & Verified Telegram Channels — Count: {len(alive_channels)}\n"
    CHANNELS_CLEANED.write_text(header + "\n".join(alive_channels) + "\n", encoding="utf-8")
    logger.info(f"✅ Successfully saved {len(alive_channels)} verified channels to {CHANNELS_CLEANED}")


if __name__ == "__main__":
    clean_channels()
