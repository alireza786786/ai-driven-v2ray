#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# Goodbaye Universal Standard - Telegram Publisher
# Rules:
#   • ارسال خودکار در هر دور چهارم (هر ۳ ساعت با فاصله ۴۵ دقیقه‌ای)
#   • پنل سوئیچ شفاف: "ارسال شود" / "ارسال نشود" بدون نیاز به تغییر منطق کد
#   • ۴ دکمه شیشه‌ای رسمی طبق اصل دوم منشور
#   • شاخص کیفیت: VIP Strict (Ping < 500ms) طبق اصل سوم منشور
#   • وب‌پنل کاملاً پویا منطبق بر مخزن ai-driven-v2ray
# ==============================================================================

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

try:
    import jdatetime
except ImportError:
    jdatetime = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_publisher")

COUNTER_FILE = "data/publish_counter.txt"
DEFAULT_TARGET_CHAT = "@Goodbaye_filtering"
VIP_TARGET_CHAT = "@CONFIG_V2RAY_VIP"

# نام مخزن به صورت کاملاً پویا استخراج می‌شود
REPO_NAME = os.getenv("GITHUB_REPOSITORY", "").split("/")[-1] or "ai-driven-v2ray"
BASE_URL = f"https://alireza786786.github.io/{REPO_NAME}"

# سقف ایمنی برای جلوگیری از اسپم در کانال
MAX_SAFE_CONFIG_LIMIT = 3500

# ══════════════════════════════════════════════════════════════════════════════
# 🎛️ پنل کنترل پکیج‌ها (تنها با تغییر کلمه: "ارسال شود" یا "ارسال نشود")
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_PACKAGES = [
    {
        "file": "top100.txt",
        "title": "پکیج طلایی Top 100 VIP",
        "status": "ارسال شود"     # ◄◄ ارسال شود / ارسال نشود
    },
    {
        "file": "fast/configs.txt",
        "title": "پکیج فوق‌سریع Fast VIP Strict",
        "status": "ارسال شود"     # ◄◄ ارسال شود / ارسال نشود
    },
    {
        "file": "verified/configs.txt",
        "title": "پکیج جامع تأییدشده All VIP",
        "status": "ارسال نشود"    # ◄◄ ارسال شود / ارسال نشود
    },
    {
        "file": "Countries/Germany.txt",
        "title": "پکیج سرورهای اختصاصی آلمان 🇩🇪",
        "status": "ارسال نشود"    # ◄◄ ارسال شود / ارسال نشود
    },
]

# ۴ دکمه شیشه‌ای رسمی طبق اصل دوم منشور
INLINE_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "📢 کانال اصلی Goodbaye Filtering", "url": "https://t.me/Goodbaye_filtering"}],
        [{"text": "⚡ کانال اختصاصی VIP", "url": "https://t.me/CONFIG_V2RAY_VIP"}],
        [{"text": "🌐 وب‌پنل آنلاین سابسکریپشن", "url": f"{BASE_URL}/"}],
        [{"text": "🔄 اشتراک‌گذاری با دوستان", "url": "https://t.me/share/url?url=https://t.me/Goodbaye_filtering"}]
    ]
}


def get_tehran_time():
    tz_tehran = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(timezone.utc).astimezone(tz_tehran)


def _gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
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
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def build_caption(package_title: str, file_path: str, count: int) -> str:
    """ساخت کپشن رسمی طبق اصل چهارم منشور با شاخص پینگ زیر ۵۰۰ میلی‌ثانیه."""
    now_tehran = get_tehran_time()
    if jdatetime:
        j_now = jdatetime.datetime.fromgregorian(datetime=now_tehran)
        date_str = j_now.strftime("%Y/%m/%d")
    else:
        jy, jm, jd = _gregorian_to_jalali(now_tehran.year, now_tehran.month, now_tehran.day)
        date_str = f"{jy:04d}/{jm:02d}/{jd:02d}"

    time_str = now_tehran.strftime("%H:%M")

    return (
        f"🚀 *مجموعه کانفیگ‌های تست‌شده و زنده ({package_title})*\n"
        f"📡 مناسب دوران اختلال، فیلترینگ و شبکه ملی\n\n"
        f"📅 تاریخ شمسی: `{date_str}`\n"
        f"⏰ ساعت تهران: `{time_str}`\n"
        f"📊 شاخص کیفیت: `VIP Strict (Ping < 500ms)`\n"
        f"🔢 تعداد کانفیگ سالم این فایل: `{count}`\n\n"
        f"🌐 لینک مستقیم دانلود / سابسکریپشن:\n"
        f"`{BASE_URL}/{file_path}`"
    )


def main():
    bot_token = os.getenv("BOT_TOKEN")
    target_chat = os.getenv("TARGET_CHAT_ID", DEFAULT_TARGET_CHAT)

    if not bot_token:
        logger.info("BOT_TOKEN is not configured. Skipping Telegram broadcast.")
        return

    # مدیریت شمارنده چرخه‌ها: اجرای چهارم (هر ۳ ساعت با اجرای ۴۵ دقیقه‌ای)
    counter_path = Path(COUNTER_FILE)
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if counter_path.exists():
        try:
            count = int(counter_path.read_text(encoding="utf-8").strip())
        except Exception:
            count = 0

    count += 1
    counter_path.write_text(str(count), encoding="utf-8")

    # بررسی شرط دوره چهارم: سه دوره استراحت، دوره چهارم انتشار
    if count % 4 != 0:
        logger.info(f"⏳ دور #{count % 4}/4: انتشار در تلگرام برای اجرای چهارم ذخیره شد.")
        return

    logger.info(f"🚀 دور #{count} (اجرای چهارم): آغاز فرآیند انتشار پکیج‌های تأییدشده در تلگرام...")

    # پشتیبانی از ارسال همزمان به کانال اصلی و VIP
    targets = [c.strip() for c in target_chat.split(",") if c.strip()]
    if VIP_TARGET_CHAT not in targets and "@Goodbaye_filtering" in targets:
        targets.append(VIP_TARGET_CHAT)

    for item in TELEGRAM_PACKAGES:
        file_path = item["file"]
        title = item["title"]
        status = item.get("status", "").strip()

        # بررسی سوئیچ کنترلی
        if status != "ارسال شود":
            logger.info(f"⏭️ پکیج '{title}' روی '{status}' تنظیم شده؛ در مخزن ماند و به تلگرام ارسال نشد.")
            continue

        p = Path(file_path)
        if not p.exists():
            logger.warning(f"⚠️ فایل '{file_path}' روی دیسک یافت نشد.")
            continue

        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        total_lines = len(lines)
        if total_lines == 0:
            logger.info(f"⚠️ فایل '{file_path}' خالی است؛ ارسال رد شد.")
            continue

        if total_lines > MAX_SAFE_CONFIG_LIMIT:
            logger.warning(f"🚨 هشدار ایمنی: '{file_path}' دارای {total_lines} کانفیگ است (بیشتر از سقف {MAX_SAFE_CONFIG_LIMIT}).")
            continue

        caption = build_caption(title, file_path, total_lines)
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

        for chat_id in targets:
            try:
                with open(p, "rb") as doc:
                    files = {"document": (p.name, doc, "text/plain")}
                    data = {
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "Markdown",
                        "reply_markup": json.dumps(INLINE_KEYBOARD)
                    }
                    resp = requests.post(url, data=data, files=files, timeout=35)
                    if resp.status_code == 200:
                        logger.info(f"✅ پکیج '{title}' ({total_lines} کانفیگ) با موفقیت به {chat_id} ارسال شد.")
                    else:
                        logger.error(f"❌ خطای تلگرام ({resp.status_code}) در ارسال به {chat_id}: {resp.text}")
            except Exception as e:
                logger.error(f"❌ خطای شبکه در ارسال {file_path} به {chat_id}: {e}")


if __name__ == "__main__":
    main()
