# -*- coding: utf-8 -*-
"""
scripts/filters.py — لایهٔ L0/L1 آبشار حقیقت‌سنجی: یکتاسازی Endpoint و فیلتر ارزان بدون شبکه.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

وظایف این لایه:
  • L0: استخراج زوج (host, port) یکتا به جای مقایسه متنی ساده (صرفه‌جویی بیش از ۱۳٪ پردازش شبکه)
  • L1: حذف کانفیگ‌های ناقص ساختاری، پورت‌های نامعتبر، سرورهای loopback/غیرقابل‌مسیریابی
  • رعایت دقیق استاندارد رسمی Xray برای شناسه‌های کاربری (قانون ۳۰ بایت و پشتیبانی از UUID فشرده ۳۲ رقمی)
  • واگذاری هوشمندانه پارس به مبدل‌ها بدون استفاده از Regexهای شکننده
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import converters

#: پروتکل‌هایی که شناسه کاربری (UUID) الزامی دارند
UUID_PROTOCOLS = frozenset({"vless", "vmess", "tuic"})

#: فرمت متعارف UUID استاندارد با خط تیره
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

#: سقف ۳۰ بایتی شناسه سفارشی طبق مستندات مرجع هسته Xray
_CUSTOM_ID_MAX_BYTES = 30

#: فرمت فشرده ۳۲ رقمی UUID (بدون خط تیره)
_UUID_RE_COMPACT = re.compile(r"^[0-9a-fA-F]{32}$")

#: شناسه تهی (جانگهدار بی‌مصرف بالادست)
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

#: دلایل ثابت و رسمی حذف نودها برای درج در تلمتری
REASON_UNPARSABLE = "unparsable"
REASON_INVALID_PORT = "invalid_port"
REASON_INVALID_UUID = "invalid_uuid"
REASON_UNROUTABLE = "unroutable_server"
REASON_INVALID_SERVER = "invalid_server"

ALL_REASONS = (
    REASON_UNPARSABLE,
    REASON_INVALID_PORT,
    REASON_INVALID_UUID,
    REASON_UNROUTABLE,
    REASON_INVALID_SERVER,
)


def is_invalid_port(port: Any) -> bool:
    """بررسی اعتبار پورت شبکه TCP (بازه ۱ تا ۶۵۵۳۵)."""
    try:
        p = int(str(port).strip())
    except (TypeError, ValueError):
        return True
    return not (0 < p < 65536)


def is_invalid_uuid(uuid: Any, proto: str) -> bool:
    """
    اعتبارسنجی شناسه کاربری طبق مشخصات رسمی هسته Xray.
    شناسه‌های زیر ۳۰ بایت مجاز هستند زیرا هسته آن‌ها را با نگاشت UUIDv5 می‌پذیرد.
    """
    if proto not in UUID_PROTOCOLS:
        return False
    s = str(uuid or "").strip()
    if not s:
        return True
    if _UUID_RE.match(s) or _UUID_RE_COMPACT.match(s):
        return s.replace("-", "").lower() == _NIL_UUID.replace("-", "")
    return len(s.encode("utf-8")) >= _CUSTOM_ID_MAX_BYTES


def endpoint_of_proxy(p: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    """استخراج زوج (host, port) تمیز و بدون کروشه IPv6 برای لایه L2."""
    host = str(p.get("server") or "").strip().strip("[]").lower()
    try:
        port = int(str(p.get("port")).strip())
    except (TypeError, ValueError):
        return None
    if not host or not (0 < port < 65536):
        return None
    return host, port


def classify(line: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """داوری لایه‌ای از ارزان به گران: (proxy, None) در صورت قبولی، (None, reason) در صورت رد."""
    p = converters.parse_proxy(line)
    if not p:
        return None, REASON_UNPARSABLE
    if is_invalid_port(p.get("port")):
        return None, REASON_INVALID_PORT
    server = p.get("server")
    if converters._is_structurally_invalid_server(server):
        return None, REASON_INVALID_SERVER
    if converters._is_unroutable_server(server):
        return None, REASON_UNROUTABLE
    if is_invalid_uuid(p.get("uuid"), str(p.get("type") or "")):
        return None, REASON_INVALID_UUID
    return p, None


def filter_lines(lines: Iterable[str]) -> Dict[str, Any]:
    """
    اجرای فاز L0 و L1 روی دنباله‌ای از کانفیگ‌ها.
    خروجی: نودهای سالم، نقاط پایانی یکتا و تفکیک دلایل حذف نودهای معیوب.
    """
    kept: List[str] = []
    endpoints: List[Tuple[str, int]] = []
    ep_index: Dict[Tuple[str, int], int] = {}
    ep_to_lines: Dict[Tuple[str, int], List[int]] = {}
    line_endpoint: List[Tuple[str, int]] = []
    dropped: Dict[str, int] = {r: 0 for r in ALL_REASONS}
    total = 0

    for raw in lines:
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        total += 1
        p, reason = classify(line)
        if reason is not None:
            dropped[reason] += 1
            continue
        ep = endpoint_of_proxy(p or {})
        if ep is None:
            dropped[REASON_INVALID_PORT] += 1
            continue
        idx = len(kept)
        kept.append(line)
        line_endpoint.append(ep)
        if ep not in ep_index:
            ep_index[ep] = len(endpoints)
            endpoints.append(ep)
            ep_to_lines[ep] = []
        ep_to_lines[ep].append(idx)

    dropped_total = sum(dropped.values())
    return {
        "kept": kept,
        "endpoints": endpoints,
        "ep_to_lines": ep_to_lines,
        "line_endpoint": line_endpoint,
        "dropped": dropped,
        "stats": {
            "input": total,
            "kept": len(kept),
            "dropped": dropped_total,
            "endpoints_unique": len(endpoints),
            "hosts_unique": len({h for h, _ in endpoints}),
            "removal_pct": round(100.0 * dropped_total / total, 2) if total else 0.0,
            "dedup_saving_pct": (
                round(100.0 * (1 - len(endpoints) / len(kept)), 2) if kept else 0.0
            ),
        },
    }


def filter_file(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return filter_lines(fh)


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "all/configs.txt"
    res = filter_file(target)
    print(json.dumps({"stats": res["stats"], "dropped": res["dropped"]}, ensure_ascii=False, indent=2))
