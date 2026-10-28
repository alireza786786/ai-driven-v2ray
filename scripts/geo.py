# -*- coding: utf-8 -*-
"""
scripts/geo.py — تعیین کشور واقعی سرور از روی نشانی شبکه با پایگاه داده DB-IP Country Lite.
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

اصلاحات:
  • حل باگ ۱۰: ایزولاسیون کامل تایم‌اوت DNS بدون نشت دادن به سایر سوکت‌های پروسه
  • حل باگ ۱۱: اولویت‌بندی مرتب‌سازی IPv4 نسبت به IPv6 برای جلوگیری از پر شدن زودهنگام سقف ۳ آدرس
  • رأی‌گیری اکثریت (Majority Vote) روی رکوردهای A برای پایداری ۱۰۰٪ برچسب‌ها
"""

from __future__ import annotations

import collections
import contextlib
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Optional, Set, Tuple

MMDB_PATH = os.environ.get("GEOIP_MMDB", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "dbip-country-lite.mmdb"
))

DNS_WORKERS = int(os.environ.get("GEO_DNS_WORKERS", "64"))
DNS_TIMEOUT = float(os.environ.get("GEO_DNS_TIMEOUT", "4"))

_reader = None
_reader_tried = False
_reader_lock = threading.Lock()

_HOST_CC: Dict[str, Tuple[str, str]] = {}
_HOST_ADDRS: Dict[str, Tuple[str, ...]] = {}
_HOST_FAILED: Set[str] = set()
_stats = collections.Counter()


def flag_of(code: str) -> str:
    """محاسبه ریاضی پرچم یونیکد از روی کد دوحرفی ISO-3166-1."""
    c = (code or "").strip().upper()
    if len(c) != 2 or not c.isalpha():
        return "🌐"
    return chr(0x1F1E6 + ord(c[0]) - 65) + chr(0x1F1E6 + ord(c[1]) - 65)


def _get_reader():
    global _reader, _reader_tried
    if _reader is not None or _reader_tried:
        return _reader
    with _reader_lock:
        if _reader is not None or _reader_tried:
            return _reader
        _reader_tried = True
        try:
            import maxminddb  # type: ignore
            if os.path.exists(MMDB_PATH) and os.path.getsize(MMDB_PATH) > 1024:
                _reader = maxminddb.open_database(MMDB_PATH)
                _stats["db_loaded"] = 1
        except Exception:
            _reader = None
    return _reader


def database_available() -> bool:
    return _get_reader() is not None


def country_of_ip(ip: str) -> Optional[str]:
    r = _get_reader()
    if r is None or not ip:
        return None
    try:
        rec = r.get(ip)
        if not rec:
            return None
        return ((rec.get("country") or {}).get("iso_code")) or None
    except Exception:
        return None


@contextlib.contextmanager
def _dns_timeout():
    """ایزولاسیون کامل تایم‌اوت بدون نشت به سوکت‌های عمومی (حل باگ ۱۰)."""
    prev = socket.getdefaulttimeout()
    socket.setdefaulttimeout(DNS_TIMEOUT)
    try:
        yield
    finally:
        socket.setdefaulttimeout(prev)


def is_ip_literal(host: str) -> bool:
    h = (host or "").strip()
    if not h:
        return False
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(fam, h)
            return True
        except Exception:
            continue
    return False


def resolve_all(host: str) -> Tuple[str, ...]:
    """حل آدرس‌های هاست با اولویت دادن به نشانی‌های IPv4 (حل باگ ۱۱)."""
    h = (host or "").strip().lower()
    if not h:
        return ()
    if h in _HOST_ADDRS:
        return _HOST_ADDRS[h]
    if is_ip_literal(h):
        _HOST_ADDRS[h] = (h,)
        return (h,)

    try:
        # استخراج آدرس‌ها
        infos = socket.getaddrinfo(h, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        v4_addrs = sorted({i[4][0] for i in infos if i[0] == socket.AF_INET})
        v6_addrs = sorted({i[4][0] for i in infos if i[0] == socket.AF_INET6})
        # قرار دادن IPv4 در ابتدا جهت تطابق با پایگاه داده کشورها
        addrs = tuple(v4_addrs + v6_addrs)
    except Exception:
        addrs = ()
    _HOST_ADDRS[h] = addrs
    return addrs


def country_of_addrs(addrs: Iterable[str]) -> Optional[str]:
    """رأی‌گیری اکثریت روی آدرس‌های CDN برای تضمین پایداری برچسب."""
    votes: collections.Counter = collections.Counter()
    first: Dict[str, str] = {}
    for ip in sorted(set(addrs)):
        cc = country_of_ip(ip)
        if cc:
            votes[cc] += 1
            first.setdefault(cc, ip)
    if not votes:
        return None
    top = max(votes.values())
    return sorted((c for c, n in votes.items() if n == top), key=lambda c: first[c])[0]


def warm_up(hosts: Iterable[str]) -> Dict[str, int]:
    uniq: Set[str] = set()
    for h in hosts:
        h = (h or "").strip().lower()
        if h and h not in _HOST_CC and h not in _HOST_FAILED:
            uniq.add(h)
    if not uniq:
        return dict(_stats)

    ordered = sorted(uniq)
    literal = [h for h in ordered if is_ip_literal(h)]
    named = [h for h in ordered if not is_ip_literal(h)]

    for h in literal:
        cc = country_of_ip(h)
        _HOST_ADDRS[h] = (h,)
        if cc:
            _HOST_CC[h] = (cc, flag_of(cc))
            _stats["by_ip_literal"] += 1
        else:
            _HOST_FAILED.add(h)
            _stats["unknown_ip_literal"] += 1

    if named and _get_reader() is not None:
        try:
            with _dns_timeout():
                with ThreadPoolExecutor(max_workers=max(1, DNS_WORKERS)) as ex:
                    results = list(ex.map(resolve_all, named))
        except Exception:
            with _dns_timeout():
                results = [resolve_all(h) for h in named]
        for h, addrs in zip(named, results):
            if not addrs:
                _HOST_FAILED.add(h)
                _stats["dns_failed"] += 1
                continue
            cc = country_of_addrs(addrs)
            if cc:
                _HOST_CC[h] = (cc, flag_of(cc))
                _stats["by_dns"] += 1
            else:
                _HOST_FAILED.add(h)
                _stats["unknown_after_dns"] += 1
    elif named:
        _stats["skipped_no_db"] += len(named)

    return dict(_stats)


def country_for_host(host: str) -> Optional[Tuple[str, str]]:
    h = (host or "").strip().lower()
    if not h:
        return None
    hit = _HOST_CC.get(h)
    if hit is not None:
        return hit
    if h in _HOST_FAILED:
        return None
    if _get_reader() is None:
        _stats["skipped_no_db"] += 1
        return None
    literal = is_ip_literal(h)
    with _dns_timeout():
        addrs = resolve_all(h)
    if not addrs:
        _HOST_FAILED.add(h)
        _stats["dns_failed"] += 1
        return None
    cc = country_of_addrs(addrs)
    if not cc:
        _HOST_FAILED.add(h)
        _stats["unknown_ip_literal" if literal else "unknown_after_dns"] += 1
        return None
    res = (cc, flag_of(cc))
    _HOST_CC[h] = res
    _stats["by_ip_literal" if literal else "by_dns"] += 1
    return res


_STAT_KEYS = (
    "db_loaded", "by_ip_literal", "unknown_ip_literal", "by_dns",
    "dns_failed", "unknown_after_dns", "skipped_no_db",
)


def stats() -> Dict[str, int]:
    out = {k: int(_stats.get(k, 0)) for k in _STAT_KEYS}
    out["db_loaded"] = 1 if _get_reader() is not None else 0
    out["hosts_resolved"] = out["by_ip_literal"] + out["by_dns"]
    out["hosts_unknown"] = (
        out["unknown_ip_literal"] + out["unknown_after_dns"]
        + out["dns_failed"] + out["skipped_no_db"]
    )
    return out


def reset() -> None:
    _HOST_CC.clear()
    _HOST_ADDRS.clear()
    _HOST_FAILED.clear()
    _stats.clear()
    if _get_reader() is not None:
        _stats["db_loaded"] = 1
