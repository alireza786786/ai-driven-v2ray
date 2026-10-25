#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/telegram_collector.py — موتور جمع‌آوری و استخراج کانفیگ‌های پروکسی از کانال‌های تلگرام.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

ویژگی‌ها:
  • واکشی امن پیام‌ها از درگاه وب پابلیک تلگرام (t.me/s/...) بدون نیاز به نشست لاگین یا Telethon
  • استخراج کانفیگ‌های خام تمام پروتکل‌ها (VLESS, VMess, Trojan, SS, Hysteria2, TUIC)
  • حفظ تاریخچه آخرین شناسه پیام‌ها در data/last_message_id.json جهت جمع‌آوری دلتا (پیام‌های جدید)
  • همروندی بالا با ThreadPoolExecutor جهت جاروی صدها کانال در چند ثانیه
  • ثبت خروجی خام در data/telegram_configs.txt جهت ورود به آبشار تست L0-L3
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set
import requests

# اضافه کردن مسیر scripts برای دسترسی به متدهای هوشمند core
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

try:
    import core
except ImportError:
    core = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_collector")

CHANNELS_CLEANED_FILE = Path("data/channels_cleaned.txt")
CHANNELS_FALLBACK_FILE = Path("data/channels.txt")
CHECKPOINT_FILE = Path("data/last_message_id.json")
OUTPUT_TELEGRAM_CONFIGS = Path("data/telegram_configs.txt")
RAW_ALL_SERVERS = Path("all_servers.txt")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

FETCH_TIMEOUT = 12
MAX_CONCURRENT_CHANNELS = 20

# رجکس عمومی برای استخراج پروتکل‌های پروکسی
CONFIG_REGEX = re.compile(
    r"(?:vless|vmess|trojan|ss|ssr|hy2|hysteria2|tuic|socks5|wireguard)://[^\s<>\"'`]+",
    re.IGNORECASE,
)


def load_channel_list() -> List[str]:
    """خواندن لیست کانال‌های تمیزشده با اولویت channels_cleaned.txt."""
    target_file = CHANNELS_CLEANED_FILE if CHANNELS_CLEANED_FILE.exists() else CHANNELS_FALLBACK_FILE
    if not target_file.exists():
        logger.warning(f"⚠️ فایل لیست کانال‌ها در {target_file} یافت نشد.")
        return []

    channels = []
    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            # پاک‌سازی پیشوندها و لینک‌های t.me
            clean = clean.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "")
            clean = clean.split("/")[0].strip()
            if clean and clean not in channels:
                channels.append(clean)

    logger.info(f"📋 تعداد {len(channels)} کانال تلگرام برای واکشی آماده شد.")
    return channels


def load_checkpoints() -> Dict[str, int]:
    """بارگذاری آخرین شناسه پیام بررسی‌شده هر کانال."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_checkpoints(checkpoints: Dict[str, int]) -> None:
    """ذخیره اتمیک شناسه‌های آخرین پیام‌ها."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CHECKPOINT_FILE.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoints, f, ensure_ascii=False, indent=2)
        tmp_path.replace(CHECKPOINT_FILE)
    except Exception as e:
        logger.error(f"خطا در ذخیره چک‌پوینت: {e}")


def scrape_channel(channel: str, last_id: int) -> tuple[str, List[str], int]:
    """استخراج پیام‌ها و کانفیگ‌های یک کانال تلگرام از طریق پابلیک وب t.me/s/..."""
    url = f"https://t.me/s/{channel}"
    headers = {"User-Agent": USER_AGENTS[hash(channel) % len(USER_AGENTS)]}

    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            return channel, [], last_id

        page_content = resp.text

        # استخراج شناسه‌های پیام و متن‌ها
        # الگوی تلگرام وب: data-post="channel/1234"
        msg_ids = [int(m) for m in re.findall(rf'data-post="{re.escape(channel)}/(\d+)"', page_content)]
        new_max_id = max(msg_ids) if msg_ids else last_id

        # انکود بایت‌های HTML
        clean_text = html.unescape(page_content)

        extracted: List[str] = []
        for match in CONFIG_REGEX.findall(clean_text):
            # حذف کاراکترهای چسبیده انتهای تگ‌ها
            cfg = match.strip().rstrip(".,;)>]}")
            if core and hasattr(core, "is_proxy_config"):
                if core.is_proxy_config(cfg):
                    extracted.append(cfg)
            else:
                if len(cfg) > 15:
                    extracted.append(cfg)

        return channel, extracted, new_max_id
    except Exception as e:
        logger.debug(f"عدم پاسخ‌دهی کانال {channel}: {e}")
        return channel, [], last_id


def main():
    channels = load_channel_list()
    if not channels:
        logger.info("هیچ کانالی برای بررسی وجود ندارد.")
        return

    checkpoints = load_checkpoints()
    all_extracted_configs: Set[str] = set()
    updated_checkpoints = dict(checkpoints)

    logger.info(f"🚀 شروع فرآیند شکار هم‌روند از {len(channels)} کانال تلگرام...")
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CHANNELS) as executor:
        futures = {
            executor.submit(scrape_channel, ch, checkpoints.get(ch, 0)): ch
            for ch in channels
        }

        for fut in as_completed(futures):
            ch, configs, max_id = fut.result()
            if configs:
                all_extracted_configs.update(configs)
                logger.info(f"  ✓ کانال @{ch:<20} ➔ استخراج {len(configs):>3} کانفیگ")
            updated_checkpoints[ch] = max_id

    elapsed = round(time.time() - t0, 2)
    logger.info(f"✅ پایان واکشی تلگرام در {elapsed} ثانیه. مجموع کانفیگ‌های خام یکتا: {len(all_extracted_configs)}")

    if not all_extracted_configs:
        logger.warning("⚠️ هیچ کانفیگی از کانال‌ها یافت نشد.")
        return

    # ذخیره استخر کانفیگ‌های تلگرام در data/telegram_configs.txt
    OUTPUT_TELEGRAM_CONFIGS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_TELEGRAM_CONFIGS, "w", encoding="utf-8") as f:
        for c in sorted(all_extracted_configs):
            f.write(c + "\n")

    # الحاق یا ساخت all_servers.txt جهت ورود به خط لوله تجمیع و تست
    existing_servers: Set[str] = set()
    if RAW_ALL_SERVERS.exists():
        with open(RAW_ALL_SERVERS, "r", encoding="utf-8", errors="ignore") as f:
            existing_servers = {line.strip() for line in f if line.strip() and not line.startswith("#")}

    combined_servers = existing_servers.union(all_extracted_configs)
    with open(RAW_ALL_SERVERS, "w", encoding="utf-8") as f:
        f.write(f"# Telegram & Git Harvested Raw Pool — Total: {len(combined_servers)}\n")
        for c in sorted(combined_servers):
            f.write(c + "\n")

    save_checkpoints(updated_checkpoints)
    logger.info(f"💾 استخر خام در {RAW_ALL_SERVERS} به‌روزرسانی شد ({len(combined_servers)} کانفیگ).")


if __name__ == "__main__":
    main()
