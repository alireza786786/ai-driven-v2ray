#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# Goodbaye Universal Standard - Telegram Publisher
# Rules: 4 Inline Buttons | VIP Strict (Ping < 500ms) | Approval Gate ("ارسال شود")
# Repository: https://github.com/alireza786786/ai-driven-v2ray
# ==============================================================================

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_publisher")

# ══════════════════════════════════════════════════════════════════════════════
# 🎛️ پنل کنترل پکیج‌های ارسالی به تلگرام (تنها با نوشتن: "ارسال شود" یا "ارسال نشود")
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_PACKAGES = [
    {
        "file": "top100.txt",
        "title": "پکیج طلایی Top 100 VIP (زیر ۵۰۰ میلی‌ثانیه)",
        "status": "ارسال شود"       # ◄◄ وضعیت: "ارسال شود" یا "ارسال نشود"
    },
    {
        "file": "fast/configs.txt",
        "title": "پکیج فوق‌سریع Fast VIP Strict",
        "status": "ارسال شود"       # ◄◄ وضعیت
    },
    {
        "file": "verified/configs.txt",
        "title": "پکیج جامع تأییدشده All VIP",
        "status": "ارسال نشود"      # ◄◄ وضعیت
    },
    {
        "file": "all_servers.txt",
        "title": "پکیج تجمیعی سرورها All Servers",
        "status": "ارسال نشود"      # ◄◄ وضعیت
    },
    {
        "file": "servers/lite.txt",
        "title": "پکیج سبک Ultra Lite",
        "status": "ارسال نشود"      # ◄◄ وضعیت
    },
    {
        "file": "Countries/Germany.txt",
        "title": "پکیج سرورهای آلمان 🇩🇪",
        "status": "ارسال نشود"      # ◄◄ وضعیت
    }
]

# ──────────────────────────────────────────────────────────────────────────────
# پیکربندی هویت و آدرس‌های پویا (Dynamic Settings)
# ──────────────────────────────────────────────────────────────────────────────
REPO_NAME = os.getenv("GITHUB_REPOSITORY", "").split("/")[-1] or "ai-driven-v2ray"
BASE_URL = f"https://alireza786786.github.io/{REPO_NAME}"
MAIN_CHANNEL = "@Goodbaye_filtering"
VIP_CHANNEL = "@CONFIG_V2RAY_VIP"
COUNTER_FILE = "data/publish_counter.txt"

# سقف ایمنی برای جلوگیری از اسپم کانال (حداکثر ۳۵۰۰ کانفیگ در هر فایل)
MAX_SAFE_CONFIG_LIMIT = 3500


def get_inline_keyboard() -> dict:
    """۴ دکمه شیشه‌ای رسمی طبق اصل دوم منشور بنیادین."""
    return {
        "inline_keyboard": [
            [{"text": "📢 کانال اصلی Goodbaye Filtering", "url": "https://t.me/Goodbaye_filtering"}],
            [{"text": "⚡ کانال اختصاصی VIP", "url": "https://t.me/CONFIG_V2RAY_VIP"}],
            [{"text": "🌐 وب‌پنل آنلاین سابسکریپشن", "url": f"{BASE_URL}/"}],
            [{"text": "🔄 اشتراک‌گذاری با دوستان", "url": "https://t.me/share/url?url=https://t.me/Goodbaye_filtering"}]
        ]
    }


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل دقیق و آفلاین تاریخ میلادی به هجری شمسی (جلالی)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy if gm > 2 else gy - 1
    days = (365 * gy) + ((gy2 + 4) // 4) - ((gy2 + 100) // 100) + ((gy2 + 400) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        days -= 186
        jm = 7 + (days // 30)
        jd = 1 + (days % 30)
    return jy, jm, jd


def get_tehran_time() -> datetime:
    """محاسبه ساعت رسمی تهران (UTC + 3:30)."""
    tz_tehran = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(timezone.utc).astimezone(tz_tehran)


def build_caption(package_title: str, file_path: str, count: int) -> str:
    """کپشن رسمی فایل‌ها در تلگرام طبق اصل سوم منشور بنیادین."""
    now_tehran = get_tehran_time()
    jy, jm, jd = gregorian_to_jalali(now_tehran.year, now_tehran.month, now_tehran.day)
    date_str = f"{jy:04d}/{jm:02d}/{jd:02d}"
    time_str = now_tehran.strftime("%H:%M")

    return (
        f"🚀 *مجموعه کانفیگ‌های تست‌شده و زنده ({package_title})*\n"
        f"📡 مناسب دوران اختلال، فیلترینگ و شبکه ملی\n\n"
        f"📅 تاریخ شمسی: `{date_str}`\n"
        f"⏰ ساعت تهران: `{time_str}`\n"
        f"📊 شاخص کیفیت: `VIP Strict (Ping < 500ms)`\n"
        f"🔢 تعداد کانفیگ سالم این فایل: `{count}`\n\n"
        f"🌐 لینک مستقیم وب‌پنل / سابسکریپشن:\n"
        f"`{BASE_URL}/{file_path}`"
    )


def publish_file_to_chat(bot_token: str, chat_id: str, file_path: Path, title: str, count: int) -> bool:
    """ارسال سند به یک چت تلگرامی به همراه ۴ دکمه شیشه‌ای و کپشن رسمی."""
    caption = build_caption(title, file_path.as_posix(), count)
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        with open(file_path, "rb") as doc:
            files = {"document": (file_path.name, doc, "text/plain")}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(get_inline_keyboard())
            }
            resp = requests.post(url, data=data, files=files, timeout=40)
            if resp.status_code == 200:
                logger.info(f"✅ Published '{title}' ({count} configs) to {chat_id}")
                return True
            else:
                logger.error(f"❌ Telegram API Error ({resp.status_code}) for {chat_id}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Network error sending {file_path} to {chat_id}: {e}")
        return False


def main():
    bot_token = os.getenv("BOT_TOKEN")
    target_chats_raw = os.getenv("TARGET_CHAT_ID", f"{MAIN_CHANNEL},{VIP_CHANNEL}")

    if not bot_token:
        logger.info("ℹ️ BOT_TOKEN is not configured. Skipping Telegram broadcast.")
        return

    # تفکیک چت‌آیدی‌ها (امکان ارسال همزمان به کانال اصلی و VIP)
    target_chats = [c.strip() for c in target_chats_raw.split(",") if c.strip()]
    if not target_chats:
        target_chats = [MAIN_CHANNEL]

    # بررسی چرخه ارسال (شمارنده هر ۳ ساعت / دوره ۱۲ گیت‌هاب اکشنز)
    Path("data").mkdir(exist_ok=True)
    cycle_count = 0
    if Path(COUNTER_FILE).exists():
        try:
            cycle_count = int(Path(COUNTER_FILE).read_text(encoding="utf-8").strip())
        except Exception:
            cycle_count = 0

    if cycle_count % 12 != 0:
        logger.info(f"⏳ Cycle #{cycle_count % 12}/12: Telegram broadcast deferred until cycle #12.")
        return

    logger.info(f"🚀 Cycle #{cycle_count}: Evaluating packages for Telegram broadcast...")

    for pkg in TELEGRAM_PACKAGES:
        file_path_str = pkg.get("file", "")
        title = pkg.get("title", "VIP Package")
        status = pkg.get("status", "ارسال نشود").strip()

        # بررسی گیت کنترلی: آیا این فایل اجازه ارسال به تلگرام دارد؟
        if status != "ارسال شود":
            logger.info(f"⏭️ Skipping '{file_path_str}' (Status: '{status}'). File remains safe in repository.")
            continue

        p = Path(file_path_str)
        if not p.exists():
            logger.warning(f"⚠️ Target file '{file_path_str}' does not exist on disk yet. Skipping.")
            continue

        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        total_lines = len(lines)
        if total_lines == 0:
            logger.info(f"⚠️ File '{file_path_str}' is empty. Skipping broadcast.")
            continue

        # گارد ضد اسپم کانال (محدودیت ۳۵۰۰ کانفیگ)
        if total_lines > MAX_SAFE_CONFIG_LIMIT:
            logger.warning(
                f"🚨 Safety Alert: '{file_path_str}' has {total_lines} configs (exceeds {MAX_SAFE_CONFIG_LIMIT}). "
                f"Blocked to protect channel."
            )
            continue

        # ارسال به تمام کانال‌های هدف تعیین‌شده
        for chat_id in target_chats:
            publish_file_to_chat(bot_token, chat_id, p, title, total_lines)


if __name__ == "__main__":
    main()
