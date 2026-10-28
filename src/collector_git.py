#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/collector_git.py — موتور هوشمند واکشی کانفیگ‌ها و سابسکریپشن‌ها از مخازن گیت‌هاب و وب.
مالک: alireza786786 | مخزن: ai-driven-v2ray | برند: @Goodbaye_filtering

اصلاحات کلیدی:
  • حل باگ ۸: ریجکس ایمن با Lookbehind منفی (عدم استخراج اشتباه ss:// از دل wss://)
  • پشتیبانی کامل از لینک‌های مستقیم و سابسکریپشن‌های انکودشده با Base64
  • ادغام، یکتاسازی و ذخیره خروجی در data/git_configs.txt جهت ورود به خط لوله تجمیع
"""

import os
import re
import sys
import base64
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("collector_git")

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "git_configs.txt"

MAX_POOL_SIZE = 25000
FETCH_TIMEOUT = 15
MAX_WORKERS = 10

# ریجکس ایمن و استاندارد (حل باگ ۸)
CONFIG_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9])(?:vless|vmess|trojan|shadowsocksr|ssr|shadowsocks|ss|hy2|hysteria2|tuic|socks5|socks|wireguard|warp|wg)://[^\s<>\"']+",
    re.IGNORECASE
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# منابع و مخازن گیت‌هابی معتبر
GIT_SOURCES = [
    "https://raw.githubusercontent.com/iampedii/whitedns-sub/main/base64.txt",
    "https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
    "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/refs/heads/main/mci/sub_1.txt",
    "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/refs/heads/main/mtn/sub_1.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/server.txt",
    "https://raw.githubusercontent.com/Au1rxx/free-vpn-subscriptions/main/output/v2ray-base64.txt",
    "https://raw.githubusercontent.com/Danialsamadi/v2go/main/AllConfigsSub.txt",
    "https://raw.githubusercontent.com/LalatinaHub/LatinaSub/main/result/sub",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/V2RAY_RAW.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/refs/heads/main/All_Configs_base64_Sub.txt",
    "https://raw.githubusercontent.com/ShadowException/VPN/refs/heads/main/configs/VPN-cat",
    "https://raw.githubusercontent.com/Delta-Kronecker/V2ray-Config/refs/heads/main/config/all_configs.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
]


def try_base64_decode(text: str) -> str:
    """تلاش برای دیکد Base64 در صورتی که پاسخ یک سابسکریپشن انکودشده باشد."""
    cleaned = re.sub(r"\s+", "", text)
    if not cleaned:
        return text
    padded = cleaned + "=" * (-len(cleaned) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(padded.encode()).decode("utf-8", errors="ignore")
            if any(p in decoded.lower() for p in ("vless://", "vmess://", "trojan://", "ss://", "ssr://")):
                return decoded
        except Exception:
            continue
    return text


def fetch_url(url: str) -> list[str]:
    configs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if resp.status_code == 200 and resp.text.strip():
            raw_text = resp.text
            # استخراج مستقیم
            found = CONFIG_PATTERN.findall(raw_text)
            if not found:
                # تلاش با دیکد Base64
                decoded_text = try_base64_decode(raw_text)
                found = CONFIG_PATTERN.findall(decoded_text)

            for cfg in found:
                clean = cfg.strip().replace("&amp;", "&")
                configs.append(clean)
            logger.info(f"  ✓ {len(configs):>5} configs ← {url.rsplit('/', 1)[-1]}")
        else:
            logger.warning(f"  ⚠️ HTTP {resp.status_code} for {url.rsplit('/', 1)[-1]}")
    except Exception as e:
        logger.warning(f"  ⚠️ Error fetching {url.rsplit('/', 1)[-1]}: {type(e).__name__}")
    return configs


def merge_and_save_configs(new_configs: list[str]):
    existing = []
    if OUTPUT_FILE.exists():
        try:
            existing = [
                line.strip() for line in OUTPUT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        except Exception:
            existing = []

    seen = set()
    combined = []
    for cfg in new_configs + existing:
        if cfg not in seen:
            seen.add(cfg)
            combined.append(cfg)

    final_pool = combined[:MAX_POOL_SIZE]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    header = f"# Goodbaye Git Collector — {len(final_pool)} Unique Harvested Configs\n"
    OUTPUT_FILE.write_text(header + "\n".join(final_pool) + "\n", encoding="utf-8")
    logger.info(f"💾 Saved {len(final_pool)} unique configs to {OUTPUT_FILE}")


def main():
    logger.info(f"🚀 Starting Git harvest across {len(GIT_SOURCES)} sources...")
    all_configs = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_url, url): url for url in GIT_SOURCES}
        for fut in as_completed(futures):
            cfgs = fut.result()
            all_configs.extend(cfgs)

    merge_and_save_configs(all_configs)


if __name__ == "__main__":
    main()
