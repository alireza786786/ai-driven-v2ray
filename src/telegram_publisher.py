#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# Goodbaye Universal Standard - Telegram Publisher
# Rules: 4 Inline Buttons | Fast tier (L3_FAST_MS, default 800 ms) | Approval Gate ("ارسال شود")
# Schedule: هر TELEGRAM_PUBLISH_EVERY (پیش‌فرض ۴) اجرای موفق یک‌بار ارسال؛
#           شمارش از GITHUB_RUN_NUMBER می‌آید، نه از فایلِ کامیت‌نشده.
# Repository: https://github.com/alireza786786/ai-driven-v2ray
# ==============================================================================

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_publisher")

# ══════════════════════════════════════════════════════════════════════════════
# 🎛️ پنل کنترل پکیج‌های ارسالی به تلگرام (تنها با نوشتن: "ارسال شود" یا "ارسال نشود")
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_PACKAGES = [
    {
        "file": "top100.txt",
        "title": "پکیج طلایی Top 100 — سریع‌ترین کانفیگ‌های تأییدشده",
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
REPO_OWNER = os.getenv("GITHUB_REPOSITORY", "").split("/")[0] or "alireza786786"
BASE_URL = f"https://alireza786786.github.io/{REPO_NAME}"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main"
MAIN_CHANNEL = "@Goodbaye_filtering"
VIP_CHANNEL = "@CONFIG_V2RAY_VIP"
# نشانیِ عمومیِ کانال برای دکمه‌ها. کانالِ خصوصی با آیدیِ عددی ارسال می‌شود،
# ولی لینکِ دعوت تنها نشانی‌ای است که کاربر می‌تواند باز کند.
CHANNEL_URL = os.getenv("MAIN_CHANNEL_URL", "https://t.me/+m4GhEHGLd2k5ZjU0")
SHARE_TEXT = "کانال گودبای فیلترینگ — کانفیگ‌های رایگان و به‌روز V2Ray"
COUNTER_FILE = "data/publish_counter.txt"

# هر چند اجرا یک بار به تلگرام ارسال شود (۳ دور استراحت + دور چهارم ارسال).
PUBLISH_EVERY = max(1, int(os.getenv("TELEGRAM_PUBLISH_EVERY", "4") or 4))


# سقف ایمنی برای جلوگیری از اسپم کانال (حداکثر ۳۵۰۰ کانفیگ در هر فایل)
MAX_SAFE_CONFIG_LIMIT = 3500


def build_share_url() -> str:
    """دیالوگِ اشتراک‌گذاریِ خودِ تلگرام.

    دکمهٔ شیشه‌ایِ URL نمی‌تواند دیالوگ اشتراک را باز کند و اگر مستقیم به
    کانال لینک شود فقط کانال را باز می‌کند — کاربر همان کارِ قبلی را می‌کند.
    `t.me/share/url` تنها راهی است که تلگرام برای دکمه‌ها به رسمیت می‌شناسد.
    """
    return (
        "https://t.me/share/url?url=" + quote(CHANNEL_URL, safe="")
        + "&text=" + quote(SHARE_TEXT, safe="")
    )


def get_inline_keyboard() -> dict:
    """۴ دکمه شیشه‌ای رسمی طبق اصل دوم منشور بنیادین."""
    return {
        "inline_keyboard": [
            [{"text": "📢 کانال رسمی Goodbaye Filtering", "url": CHANNEL_URL}],
            [{"text": "⚡ کانال اختصاصی VIP", "url": "https://t.me/CONFIG_V2RAY_VIP"}],
            [{"text": "🌐 وب‌پنل آنلاین سابسکریپشن", "url": f"{BASE_URL}/"}],
            [{"text": "🔄 اشتراک‌گذاری با دوستان", "url": build_share_url()}]
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
        f"📊 شاخص کیفیت: `تأییدشده در ۳ دورِ آزمونِ واقعی`\n"
        f"🔢 تعداد کانفیگ سالم این فایل: `{count}`\n\n"
        f"🌐 لینک مستقیم فایل (سابسکریپشن):\n"
        f"`{RAW_BASE}/{Path(str(file_path)).as_posix()}`\n"
        f"🖥️ وب‌پنل:\n`{BASE_URL}/`"
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
    if any(c.startswith("https://t.me/+") or c.startswith("t.me/+") for c in target_chats):
        logger.error(
            "❌ TARGET_CHAT_ID یک لینکِ دعوت است. Bot API لینکِ دعوت را نمی‌شناسد؛ "
            "آیدیِ عددی (مثل -1001234567890) یا یوزرنیمِ عمومی (@channel) بدهید "
            "و مطمئن شوید ربات در کانال ادمین است."
        )
        return

    # مدیریت چرخهٔ ارسال — چرا دیگر به فایلِ شمارنده تکیه نمی‌کنیم:
    # آن فایل در data/ است و data/ جزو OUTPUT_PATHS نیست، پس افزایشش هیچ‌وقت
    # کامیت نمی‌شد. نتیجه: هر اجرا عدد ۱ را می‌خواند، ۲ می‌کرد و دور چهارم
    # هرگز نمی‌رسید — یعنی «هیچ‌چیز به تلگرام نمی‌رفت».
    # GITHUB_RUN_NUMBER خودش یکنوا و پایدار است و نیازی به حالتِ ذخیره‌شده ندارد.
    run_number = os.getenv("GITHUB_RUN_NUMBER", "").strip()
    if run_number.isdigit():
        cycle_count = int(run_number)
    else:
        counter_path = Path(COUNTER_FILE)
        counter_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cycle_count = int(counter_path.read_text(encoding="utf-8").strip())
        except Exception:
            cycle_count = 0
        cycle_count += 1
        counter_path.write_text(str(cycle_count), encoding="utf-8")

    if cycle_count % PUBLISH_EVERY != 0:
        logger.info(
            f"⏳ دور #{cycle_count}: استراحت (ارسال در هر {PUBLISH_EVERY} اجرا یک‌بار — "
            f"دور بعدی: #{((cycle_count // PUBLISH_EVERY) + 1) * PUBLISH_EVERY})."
        )
        return

    logger.info(f"🚀 دور #{cycle_count}: انتشار در {', '.join(target_chats)} آغاز شد…")

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
