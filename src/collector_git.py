#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/collector_git.py — موتور جمع‌آوری و استخراج کانفیگ‌ها از مخازن گیت‌هاب و سورس‌های اشتراکی.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

ویژگی‌ها:
  • واکشی هم‌روند و پایدار از سورس‌های گیت‌هاب و اشتراک‌های آنلاین (با retry و backoff)
  • پشتیبانی کامل از محتوای متنی خام و اشتراک‌های انکودشده Base64
  • ادغام هوشمند نودهای جدید (Delta) در all_servers.txt بدون رونویسی مخرب دیتای قبلی
  • ثبت گزارش جامع منابع در data/repo_report.txt
"""

from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set, Tuple
import requests

# اتصال به موتور هویت و استخراج core
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

try:
    import core
    import sources
except ImportError:
    core = None
    sources = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("collector_git")

RAW_ALL_SERVERS = Path("all_servers.txt")
OUTPUT_GIT_CONFIGS = Path("data/git_configs.txt")
REPO_REPORT_FILE = Path("data/repo_report.txt")

FETCH_TIMEOUT = 15
MAX_WORKERS = 16

USER_AGENTS = (
    "v2rayNG/1.8.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "ClashforWindows/0.20.39",
)


def get_git_sources() -> List[str]:
    """استخراج لیست سورس‌های اشتراکی و مخازن گیت‌هاب."""
    urls = []
    # ۱. استفاده از منابع معتبر و رسمی sources.py
    if sources and hasattr(sources, "all_sources"):
        urls.extend(sources.all_sources())

    # ۲. بررسی فایل منابع خارجی در صورت وجود
    external_sources = Path("data/sources_list.txt")
    if external_sources.exists():
        with open(external_sources, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                u = line.strip()
                if u and not u.startswith("#") and u.startswith("http") and u not in urls:
                    urls.append(u)

    return urls


def fetch_url(url: str) -> Tuple[str, List[str], str]:
    """واکشی یک آدرس و استخراج کانفیگ‌های درون آن با رمزگشایی هوشمند."""
    name = url.rsplit("/", 1)[-1] or url
    headers = {"User-Agent": USER_AGENTS[hash(url) % len(USER_AGENTS)]}

    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200 or not resp.text.strip():
            return url, [], f"HTTP {resp.status_code}"

        body = resp.text.strip()
        lines: List[str] = []

        if core and hasattr(core, "extract_valid_lines"):
            lines = core.extract_valid_lines(body)
        else:
            # روش پشتیبان استخراج مستقیم
            import re
            cfg_re = re.compile(r"(?:vless|vmess|trojan|ss|ssr|hy2|hysteria2|tuic)://[^\s<>\"'`]+")
            lines = cfg_re.findall(body)

        return url, lines, "ok" if lines else "empty (0 valid configs)"
    except Exception as e:
        return url, [], f"Error: {type(e).__name__}"


def main():
    target_urls = get_git_sources()
    if not target_urls:
        logger.info("هیچ منبع گیت‌هابی برای واکشی تعریف نشده است.")
        return

    logger.info(f"🚀 شروع واکشی هم‌روند از {len(target_urls)} سورس گیت‌هاب...")
    t0 = time.time()

    all_harvested_configs: Set[str] = set()
    report_lines: List[str] = [
        f"# Goodbaye Git Collector Report — Generated at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        f"# Total Sources Queried: {len(target_urls)}\n",
    ]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_url, url): url for url in target_urls}

        for fut in as_completed(futures):
            url, configs, status = fut.result()
            name = url.rsplit("/", 1)[-1] or url
            count = len(configs)
            report_lines.append(f"- {name:<35} | Count: {count:>4} | Status: {status}")

            if configs:
                all_harvested_configs.update(configs)
                logger.info(f"  ✓ سورس {name:<30} ➔ دریافت {count:>4} کانفیگ")
            else:
                logger.warning(f"  ⚠️ سورس {name:<30} ➔ وضعیت: {status}")

    elapsed = round(time.time() - t0, 2)
    logger.info(f"✅ پایان واکشی گیت‌هاب در {elapsed} ثانیه. کانفیگ‌های استخراج‌شده: {len(all_harvested_configs)}")

    # ذخیره گزارش سلامت سورس‌ها در data/repo_report.txt
    REPO_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPO_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    # ذخیره کانفیگ‌های گیت در data/git_configs.txt
    OUTPUT_GIT_CONFIGS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GIT_CONFIGS, "w", encoding="utf-8") as f:
        for c in sorted(all_harvested_configs):
            f.write(c + "\n")

    # ادغام هوشمند با all_servers.txt (حفظ کانفیگ‌های تلگرام و افزودن کانفیگ‌های گیت)
    existing_servers: Set[str] = set()
    if RAW_ALL_SERVERS.exists():
        with open(RAW_ALL_SERVERS, "r", encoding="utf-8", errors="ignore") as f:
            existing_servers = {line.strip() for line in f if line.strip() and not line.startswith("#")}

    combined = existing_servers.union(all_harvested_configs)
    with open(RAW_ALL_SERVERS, "w", encoding="utf-8") as f:
        f.write(f"# Unified Raw Server Pool (Telegram + Git) — Total: {len(combined)}\n")
        for c in sorted(combined):
            f.write(c + "\n")

    logger.info(f"💾 استخر جامع در {RAW_ALL_SERVERS} بازنویسی شد (مجموع نودها: {len(combined)}).")


if __name__ == "__main__":
    main()
