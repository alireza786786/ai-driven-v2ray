#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/telegram_collector.py — موتور هوشمند واکشی و استخراج کانفیگ‌ها از کانال‌های تلگرام.
مالک: alireza786786 | مخزن: ai-driven-v2ray | برند: @Goodbaye_filtering

اصلاحات کلیدی:
  • حل باگ ۵: Fallback خودکار به channels.txt در صورت خالی بودن channels_cleaned.txt
  • حل باگ ۸: اصلاح ریجکس با Lookbehind منفی (جلوگیری از استخراج اشتباه ss:// از دل wss://)
  • حل باگ ۹: فعال‌سازی واقعی Checkpoint بر اساس last_message_id و ادغام نودها تا سقف ۲۵ هزار کانفیگ
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_collector")

DATA_DIR = Path("data")
CHANNELS_CLEANED_FILE = DATA_DIR / "channels_cleaned.txt"
CHANNELS_FALLBACK_FILE = DATA_DIR / "channels.txt"
CHECKPOINT_FILE = DATA_DIR / "last_message_id.json"
OUTPUT_FILE = DATA_DIR / "telegram_configs.txt"

MAX_POOL_SIZE = 25000
FETCH_TIMEOUT = 15

# ریجکس ایمن و استاندارد (حل باگ ۸): ssr قبل از ss، پشتیبانی از socks5 و مهار wss://
CONFIG_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9])(?:vless|vmess|trojan|shadowsocksr|ssr|shadowsocks|ss|hy2|hysteria2|tuic|socks5|socks|wireguard|warp|wg)://[^\s<>\"']+",
    re.IGNORECASE
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def load_channels() -> list[str]:
    """بارگذاری لیست کانال‌ها با فال‌بک ایمن (حل باگ ۵)."""
    channels = []
    
    # اولویت ۱: فایل پاک‌سازی‌شده
    if CHANNELS_CLEANED_FILE.exists():
        try:
            lines = [
                line.strip().lstrip("@") for line in CHANNELS_CLEANED_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if lines:
                channels = lines
                logger.info(f"📋 Loaded {len(channels)} channels from {CHANNELS_CLEANED_FILE.name}")
        except Exception as e:
            logger.warning(f"⚠️ Could not read {CHANNELS_CLEANED_FILE.name}: {e}")

    # اولویت ۲ (Fallback): در صورت خالی بودن، فایل اصلی خوانده می‌شود
    if not channels and CHANNELS_FALLBACK_FILE.exists():
        try:
            lines = [
                line.strip().lstrip("@") for line in CHANNELS_FALLBACK_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if lines:
                channels = lines
                logger.info(f"🔄 Fallback: Loaded {len(channels)} channels from {CHANNELS_FALLBACK_FILE.name}")
        except Exception as e:
            logger.warning(f"⚠️ Could not read fallback {CHANNELS_FALLBACK_FILE.name}: {e}")

    return list(dict.fromkeys(channels))


def load_checkpoints() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_checkpoints(checkpoints: dict):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_FILE.write_text(json.dumps(checkpoints, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"❌ Failed to save checkpoints: {e}")


def fetch_channel_messages(channel: str, last_id: int) -> tuple[list[str], int]:
    """واکشی پیام‌های جدید وب‌پیش‌نمایش کانال با در نظر گرفتن checkpoint (حل باگ ۹)."""
    url = f"https://t.me/s/{channel}"
    configs = []
    max_seen_id = last_id

    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            return configs, max_seen_id

        html = resp.text
        # استخراج بلاک‌های پیام همراه با آی‌دی پست
        message_blocks = re.findall(
            r'data-post="([^"]+)/(\d+)"[\s\S]*?<div class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>',
            html
        )

        for ch_name, post_id_str, text in message_blocks:
            try:
                post_id = int(post_id_str)
            except ValueError:
                continue

            # گارد Checkpoint: نادیده گرفتن پیام‌های قدیمی و از قبل خوانده‌شده
            if post_id <= last_id:
                continue

            if post_id > max_seen_id:
                max_seen_id = post_id

            found = CONFIG_PATTERN.findall(text)
            for cfg in found:
                clean_cfg = cfg.strip().replace("&amp;", "&")
                configs.append(clean_cfg)

    except Exception as e:
        logger.debug(f"Fetch failed for channel {channel}: {e}")

    return configs, max_seen_id


def merge_and_save_configs(new_configs: list[str]):
    """ادغام کانفیگ‌های جدید با استخر قبلی، یکتاسازی و نگهداری سقف ۲۵۰۰۰ نود."""
    existing_configs = []
    if OUTPUT_FILE.exists():
        try:
            existing_configs = [
                line.strip() for line in OUTPUT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        except Exception:
            existing_configs = []

    # ادغام با حفظ تقدم کانفیگ‌های جدید و حذف تکراری‌ها
    seen = set()
    combined = []
    
    for cfg in new_configs + existing_configs:
        if cfg not in seen:
            seen.add(cfg)
            combined.append(cfg)

    # حفظ حداکثر سقف مجاز
    final_pool = combined[:MAX_POOL_SIZE]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = f"# Goodbaye Telegram Collector — {len(final_pool)} Unique Harvested Configs\n"
    OUTPUT_FILE.write_text(header + "\n".join(final_pool) + "\n", encoding="utf-8")
    logger.info(f"💾 Saved {len(final_pool)} unique configs to {OUTPUT_FILE} (New: {len(new_configs)})")


def main():
    channels = load_channels()
    if not channels:
        logger.warning("⚠️ No channels found to process. Exiting.")
        return

    checkpoints = load_checkpoints()
    all_new_configs = []
    updated_checkpoints = dict(checkpoints)

    logger.info(f"🚀 Starting telegram harvest across {len(channels)} channels...")

    for idx, ch in enumerate(channels, 1):
        last_id = checkpoints.get(ch, 0)
        configs, new_max_id = fetch_channel_messages(ch, last_id)

        if configs:
            all_new_configs.extend(configs)
            logger.info(f"  [{idx}/{len(channels)}] @{ch}: +{len(configs)} new configs (last_id: {last_id} -> {new_max_id})")

        if new_max_id > last_id:
            updated_checkpoints[ch] = new_max_id

    save_checkpoints(updated_checkpoints)
    merge_and_save_configs(all_new_configs)


if __name__ == "__main__":
    main()
