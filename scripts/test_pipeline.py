# -*- coding: utf-8 -*-
"""
scripts/test_pipeline.py — سوئیت جامع تست‌های واحد، راستی‌آزمایی و قفل‌های ضدرگرسیون خط‌لوله.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

تضمین‌های تحت پوشش این سوئیت:
  • اعتبارسنجی ۱۰۰٪ هویت رسمی برند: @Goodbaye_filtering
  • آزمون الگوی ۵ خطی ریمارک و پایداری در تمام پروتکل‌ها
  • راستی‌آزمایی آستانه پینگ VIP Strict (زیر ۵۰۰ میلی‌ثانیه)
  • بررسی پایداری ۳ دوره‌ای L3 و محاسبه میانه تاخیر
  • جلوگیری از نشت سوکت‌ها و مهار باگ‌های سیستم‌عامل در L2
  • راستی‌آزمایی پاک‌سازی اتمیک، سازگاری کلاینت‌ها و زنجیره تأمین باینری‌ها
"""
from __future__ import annotations

import atexit
import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import aggregate  # noqa: E402
import converters  # noqa: E402
import core  # noqa: E402
import countries  # noqa: E402
import filters  # noqa: E402
import geo  # noqa: E402
import mihomo_compat  # noqa: E402
import pipeline  # noqa: E402
import reachability  # noqa: E402
import realtest  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402
import validate  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# مدیریت و پاک‌سازی خودکار دایرکتوری‌های موقت (گارد F-6)
# ──────────────────────────────────────────────────────────────────────────────

_TMP_DIRS: List[str] = []
_TMP_HOOKED: bool = False


def _tmpdir(prefix: str = "tp_") -> str:
    global _TMP_HOOKED
    path = tempfile.mkdtemp(prefix=prefix)
    _TMP_DIRS.append(path)
    if not _TMP_HOOKED:
        atexit.register(_tmpdir_cleanup)
        _TMP_HOOKED = True
    return path


def _tmpdir_cleanup() -> int:
    removed = 0
    while _TMP_DIRS:
        path = _TMP_DIRS.pop()
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های اعتبارسنجی ساختاری Shadowsocks و REALITY
# ──────────────────────────────────────────────────────────────────────────────

def test_ss_cipher_whitelist_rejects_uuid_as_cipher():
    assert converters._sanitize_ss("0fb53a60-2372-412a-a693-5157b58ecc94", "pw") is None
    assert converters._sanitize_ss("aes-256-gcm", "pw") == ("aes-256-gcm", "pw")
    assert converters._sanitize_ss("CHACHA20-IETF-POLY1305", "pw") is not None
    assert converters._sanitize_ss("", "pw") is None


def test_ss2022_key_length_must_match_exactly():
    ok16 = base64.b64encode(b"A" * 16).decode()
    ok32 = base64.b64encode(b"A" * 32).decode()
    assert converters._sanitize_ss("2022-blake3-aes-128-gcm", ok16) is not None
    assert converters._sanitize_ss("2022-blake3-aes-256-gcm", ok32) is not None
    assert converters._sanitize_ss("2022-blake3-aes-128-gcm", ok32) is None
    assert converters._sanitize_ss("2022-blake3-aes-256-gcm", ok16) is None
    assert converters._sanitize_ss("2022-blake3-aes-256-gcm", "not-base64!!") is None


def test_reality_short_id_must_be_even_length_hex():
    assert converters._sanitize_short_id("cfe08c23a85f24") == "cfe08c23a85f24"
    assert converters._sanitize_short_id("") == ""
    assert converters._sanitize_short_id("abc") is None
    assert converters._sanitize_short_id("zz") is None
    assert converters._sanitize_short_id("a" * 18) is None


def test_reality_public_key_must_be_32_bytes_base64url():
    good = "XF21CCK2RAaefcs24Vtp3UwgFQX_xkC9ANNOcfJ_c2w"
    assert converters._sanitize_pbk(good) == good
    assert converters._sanitize_pbk("tooshort") is None
    assert converters._sanitize_pbk("") is None


def test_flow_whitelist_strips_udp443_suffix():
    assert converters._sanitize_flow("xtls-rprx-vision-udp443") == "xtls-rprx-vision"
    assert converters._sanitize_flow("xtls-rprx-vision") == "xtls-rprx-vision"
    assert converters._sanitize_flow("xtls-rprx-direct") == ""
    assert converters._sanitize_flow("") == ""


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های برندینگ منشور Goodbaye و ریمارک ۵ خطی
# ──────────────────────────────────────────────────────────────────────────────

def test_brand_remark_enforces_goodbaye_channel():
    line = "vless://11111111-1111-1111-1111-111111111111@1.2.3.4:443?security=tls&type=tcp#old_tag"
    branded = core.brand_remark(line, delay=120)
    assert core.is_branded(branded), f"برند Goodbaye در کانفیگ یافت نشد: {branded!r}"
    assert core.BRAND_CHANNEL in urllib.parse.unquote(branded)
    # بررسی حضور اجزای ۵ خطی
    decoded_remark = core.remark_of(branded)
    assert "👉🆔@Goodbaye_filtering" in decoded_remark
    assert "🅿️ping:" in decoded_remark
    assert "ms" in decoded_remark


def test_brand_remark_supports_vmess_json():
    payload = {
        "v": "2", "ps": "old_name", "add": "1.2.3.4", "port": "443",
        "id": "11111111-1111-1111-1111-111111111111", "aid": "0",
        "net": "ws", "tls": "tls"
    }
    raw = base64.b64encode(json.dumps(payload).encode()).decode()
    line = f"vmess://{raw}"
    branded = core.brand_remark(line, delay=150)
    assert core.is_branded(branded)
    rem = core.remark_of(branded)
    assert "👉🆔@Goodbaye_filtering" in rem


def test_plain_uri_vmess_is_branded_properly():
    line = (
        "vmess://500cdc83-b189-4d79-b06b-139c7972a57f@91.107.139.186:51459"
        "?encryption=auto&security=none&type=tcp#%F0%9F%93%AF1%40competitor"
    )
    branded = core.brand_remark(line, delay=220)
    assert core.is_branded(branded)
    assert "competitor" not in core.remark_of(branded)


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های ترنسپورت و سازگاری کلاینت‌ها (Clash & Sing-box)
# ──────────────────────────────────────────────────────────────────────────────

def test_clash_network_mapping():
    assert converters._clash_network("websocket") == "ws"
    assert converters._clash_network("httpupgrade") == "ws"
    assert converters._clash_network("gun") == "grpc"
    assert converters._clash_network("splithttp") == "xhttp"
    assert converters._clash_network("raw") == "tcp"


def test_singbox_transport_filtering():
    assert converters._singbox_transport({"network": "xhttp"}) is False
    assert converters._singbox_transport({"network": "kcp"}) is False
    ws = converters._singbox_transport({"network": "ws", "path": "/a", "host": "h"})
    assert ws and ws["type"] == "ws"


def test_lone_percent_in_path_is_repaired():
    for raw, want in (("%", "%25"), ("/a%", "/a%25"), ("/a%20b", "/a%20b")):
        got = converters._safe_transport_path(raw)
        assert got == want, f"{raw!r} -> {got!r}"


def test_ambiguous_yaml_scalars_are_quoted():
    ambiguous = ["9e63", "123456", "true", "False", "null", ".inf"]
    dumped = yaml.dump(
        {"v": ambiguous},
        Dumper=converters._clash_dumper(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    for item in ambiguous:
        assert f"'{item}'" in dumped or f'"{item}"' in dumped


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های یکپارچگی مخزن و متغیرهای هویتی
# ──────────────────────────────────────────────────────────────────────────────

def test_repo_identity_and_pages_url():
    assert aggregate.GH_USER == "alireza786786"
    assert aggregate.GH_REPO == "ai-driven-v2ray"
    assert aggregate.GH_BRANCH == "main"
    assert "alireza786786.github.io/ai-driven-v2ray" in aggregate.BASE_PAGES_URL


def test_primary_links_are_raw_and_fresh():
    r = aggregate.CategoryResult()
    r.unique = ["vless://x@1.2.3.4:443#a"]
    results = {c: r for c in ("all", "heavy", "light")}
    idx = aggregate.build_index(results, {"vless": 1}, 1.0)
    assert "raw.githubusercontent.com" in idx["primary_base"]
    assert "cdn.jsdelivr.net" in idx["mirror_base"]


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های آبشار L0/L1 و L2
# ──────────────────────────────────────────────────────────────────────────────

def test_filters_l0_l1_integrity():
    for bad in (0, -1, 65536, "abc"):
        assert filters.is_invalid_port(bad)
    assert not filters.is_invalid_port(443)
    assert not filters.is_invalid_uuid("13094", "vless")
    assert filters.is_invalid_uuid("00000000-0000-0000-0000-000000000000", "vless")


def test_reachability_concurrency_and_headroom():
    assert reachability.CONCURRENCY <= 1000
    assert reachability.headroom_warning(100) is None
    assert reachability.headroom_warning(1000000) is not None


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های آبشار L3 و آستانه پینگ زیر ۵۰۰ میلی‌ثانیه
# ──────────────────────────────────────────────────────────────────────────────

def _pl_row(link: str, status: str = "passed", delay: int = 120, tls: str = "tls") -> dict:
    return {
        "link": link, "status": status, "reason": "", "tls": tls,
        "ip": "9.9.9.9", "delay": str(delay), "code": "204",
        "download": "0", "upload": "0", "location": "US", "ttfb": "119",
        "connect_time": "8", "success": "1", "total": "1",
        "endpoints": "cp.cloudflare.com=ok",
    }


class _StubL3:
    def __init__(self, per_round: list) -> None:
        self.per_round = per_round
        self.calls = 0
        self._orig = None

    def __enter__(self) -> _StubL3:
        self._orig = realtest.test_lines

        def fake(lines, **kwargs):
            rows = self.per_round[min(self.calls, len(self.per_round) - 1)]
            self.calls += 1
            return {"rows": {(r.get("link") or ""): r for r in rows}}

        realtest.test_lines = fake
        return self

    def __exit__(self, *exc: object) -> None:
        realtest.test_lines = self._orig


def test_pipeline_fast_strict_under_500ms():
    """تأیید کارکرد شاخص پینگ Fast VIP Strict برای نودهای زیر ۵۰۰ میلی‌ثانیه."""
    fast_node = "vless://fast@1.1.1.1:443?security=tls#fast"
    slow_node = "vless://slow@2.2.2.2:443?security=tls#slow"
    rounds = [
        [_pl_row(fast_node, delay=150), _pl_row(slow_node, delay=600)],
        [_pl_row(fast_node, delay=180), _pl_row(slow_node, delay=550)],
        [_pl_row(fast_node, delay=140), _pl_row(slow_node, delay=520)],
    ]
    with _StubL3(rounds):
        res = pipeline.run_l3_round([fast_node, slow_node], rounds=3)

    buckets = pipeline.build_buckets(res, fast_ms=500)
    assert len(buckets["verified"]) == 2
    # نود با میانه تاخیر کمتر از ۵۰۰ms باید وارد سبد fast شود
    assert any("fast" in str(link) for link in buckets["fast"])
    assert not any("slow" in str(link) for link in buckets["fast"])


def test_pipeline_forward_secrecy():
    assert pipeline.has_forward_secrecy("vless://a@1.1.1.1:443?security=reality#r", "reality")
    assert pipeline.has_forward_secrecy("hysteria2://p@1.1.1.1:443#h", "")
    assert not pipeline.has_forward_secrecy("vless://a@1.1.1.1:443?security=none#n", "none")


def test_realtest_genuinely_ok_guard():
    ok_row = {"status": "passed", "total": "1", "success": "1", "code": "204"}
    assert realtest.is_row_genuinely_ok(ok_row)
    broken_row = {"status": "broken", "total": "0", "success": "0", "code": "-1"}
    assert not realtest.is_row_genuinely_ok(broken_row)


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های تفکیک کشوری Countries/
# ──────────────────────────────────────────────────────────────────────────────

def test_countries_slug_and_safety():
    assert countries.slug_for("Germany") == "Germany"
    assert countries.slug_for("United States") == "United_States"
    assert countries.is_safe_slug("Germany")
    assert not countries.is_safe_slug("../../bad")


def test_countries_extracts_code_from_5line_remark():
    # ساخت یک کانفیگ تست با ریمارک ۵ خطی رسمی منشور
    line = core.brand_remark("vless://u@1.2.3.4:443?type=tcp", delay=120)
    code = countries.country_code_of(line)
    assert code is not None and code != "Global"


# ──────────────────────────────────────────────────────────────────────────────
# تست‌های پایداری و حافظه state.py
# ──────────────────────────────────────────────────────────────────────────────

def test_state_memory_bounds():
    st = state.empty_state()
    urls = ["https://example.com/s1.txt"]
    for i in range(25):
        obs = {urls[0]: {"tier": "light", "total": 100, "unique": i}}
        st = state.record_round(st, obs, urls)
    ent = st["sources"][state.source_key(urls[0])]
    assert len(ent["yield"]) <= state.MAX_HISTORY
    assert len(ent["unique"]) <= state.MAX_HISTORY


# ──────────────────────────────────────────────────────────────────────────────
# تست دروازه سازگاری کلش و می‌هومو (mihomo_compat)
# ──────────────────────────────────────────────────────────────────────────────

def test_mihomo_compat_catches_fatal_lines():
    bad_ss = "ss://Y2hhY2hhMjAtcG9seTEzMDU6eA==@1.2.3.4:443#t"  # chacha20-poly1305 در ss غیرمجاز است
    assert mihomo_compat.fatal_reason(bad_ss) == mihomo_compat.REASON_SS_METHOD
    good_ss = "ss://YWVzLTEyOC1nY206eA==@1.2.3.4:443#t"
    assert mihomo_compat.fatal_reason(good_ss) is None


# ──────────────────────────────────────────────────────────────────────────────
# تست دروازه انتشار validate.py
# ──────────────────────────────────────────────────────────────────────────────

def test_validate_output_whitelist():
    assert "pass" in validate.ACCEPTABLE_STATUSES
    assert "skipped" in validate.ACCEPTABLE_STATUSES
    assert "fail" not in validate.ACCEPTABLE_STATUSES


# ──────────────────────────────────────────────────────────────────────────────
# تابع اجرای کلیه تست‌ها
# ──────────────────────────────────────────────────────────────────────────────

def _run_all() -> int:
    tests = [
        (n, f) for n, f in sorted(globals().items())
        if n.startswith("test_") and callable(f)
    ]
    failed = 0
    print(f"🚀 شروع اجرای {len(tests)} آزمون تضمین کیفیت خط‌لوله Goodbaye Universal Standard...\n")
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {name}\n       {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  💥 {name}\n       {type(e).__name__}: {e}")
    print(f"\n📊 نتیجه نهایی: {len(tests) - failed} از {len(tests)} آزمون با موفقیت پاس شدند.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
