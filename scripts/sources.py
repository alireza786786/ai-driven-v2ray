# -*- coding: utf-8 -*-
"""
scripts/sources.py — مدیریت هوشمند منابع سابسکریپشن و ورودی‌های پروکسی.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

دسته‌بندی منابع:
  • LIGHT  — منابع دستچین‌شده با حجم بهینه و نرخ اتصال و پایداری بالا (مناسب پکیج‌های Fast و Top 100).
  • HEAVY  — تجمیع‌کننده‌های انبوه و سرورهای توزیع‌شده با تنوع پروتکل بالا.
  • ALL    — اجتماع یکتای تمام منابع زنده بدون URL تکراری.

پایش مداوم:
  منابع بر مبنای «بازدهِ یکتا» (Unique Yield) توسط ماژول state.py ارزیابی می‌شوند؛
  هر منبعی که ۱۰ دور پیاپی هیچ کانفیگ یکتایی ارائه نکند به طور خودکار به حالت غیرفعال می‌رود.
  آخرین اعتبارسنجی همهٔ URLهای زیر: ۱۵ اکتبر ۲۰۲۶ — هر ۱۳ منبع HTTP 200 برگرداندند.
"""
from __future__ import annotations

from typing import List

# ── منابع سبک و باکیفیت دستچین (۸ منبع فعال) ──────────────────────────────────
LIGHT_SOURCES: List[str] = [
    # سورس پرسرعت و پایدار whitedns-sub
    "https://raw.githubusercontent.com/iampedii/whitedns-sub/main/base64.txt",
    # تجمیع‌کننده با اعتبارسنجی ساختاری 4n0nymou3
    "https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
    # سورس‌های مهسانت (همراه اول و ایرانسل)
    "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/refs/heads/main/mci/sub_1.txt",
    "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/refs/heads/main/mtn/sub_1.txt",
    # سورس پایدار ALIILAPRO
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/server.txt",
    # سورس‌های برگزیده با نرخ پایداری بالا در آزمون L3
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/v2ray-base64.txt",
    "https://raw.githubusercontent.com/Danialsamadi/v2go/main/AllConfigsSub.txt",
    "https://raw.githubusercontent.com/LalatinaHub/LatinaSub/main/result/sub",
]

# ── منابع انبوه و تجمیعی با تنوع پروتکل (۵ منبع فعال) ──────────────────────────
HEAVY_SOURCES: List[str] = [
    # لیست خام roosterkid
    "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/V2RAY_RAW.txt",
    # سورس تجمیعی barry-far
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/refs/heads/main/All_Configs_base64_Sub.txt",
    # سورس دسته‌بندی‌شده ShadowException
    "https://raw.githubusercontent.com/ShadowException/VPN/refs/heads/main/configs/VPN-cat",
    # منبع پرحجم و غنی Delta-Kronecker
    "https://raw.githubusercontent.com/Delta-Kronecker/V2ray-Config/refs/heads/main/config/all_configs.txt",
    # سورس تجمیعی Epodonios
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
]


def all_sources() -> List[str]:
    """اجتماع مرتب و بدون تکرار تمامی منابع سبک و سنگین فعال."""
    seen = set()
    out: List[str] = []
    for url in LIGHT_SOURCES + HEAVY_SOURCES:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
