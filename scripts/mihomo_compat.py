# -*- coding: utf-8 -*-
"""
scripts/mihomo_compat.py — سپر محافظتی برای رفع باگ فاجعه‌بار «یک خط خراب = صفر پروکسی» در کلش و می‌هومو.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

چرا این ماژول حیاتی است:
  در کلاینت‌های مبتنی بر هسته Mihomo (مانند Clash Verge Rev، FlClash و Mihomo Party)، اگر حتی یک خط
  در اشتراک‌های متنی دارای خطای پارس در تابع ParseProxy هسته Go باشد، کل فایل رد شده و تعداد صفر پروکسی
  برای کاربر لود می‌شود. این ماژول بر مبنای سورس‌کد هسته Go، خطوط مهلک را پیش از انتشار اخراج می‌کند.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.parse
from typing import Dict, Optional

#: روش‌های رمزنگاری معتبر Shadowsocks در هسته Mihomo (حساس به بزرگی و کوچکی حروف)
SS_METHODS = frozenset({
    "aes-128-gcm", "aes-192-gcm", "aes-256-gcm",
    "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
    "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr",
    "rc4-md5", "chacha20-ietf", "xchacha20", "none",
})

#: طول دقیق کلید برای هر متد در Shadowsocks-2022
SS2022_KEY_BYTES: Dict[str, int] = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-aes-256-gcm": 32,
    "2022-blake3-chacha20-poly1305": 32,
}

#: متدهای رمزنگاری مجاز VMess در Mihomo (غیرحساس به حروف ولی فاقد تحمل فاصله خالی)
VMESS_CIPHERS = frozenset({
    "auto", "none", "zero", "aes-128-gcm", "aes-128-cfb", "chacha20-poly1305",
})

#: حالت‌های مجاز xhttp در کلاینت Go
XHTTP_MODES = frozenset({"auto", "stream-one", "stream-up", "packet-up"})

#: انواع مجاز obfs در Hysteria2
HY2_OBFS = frozenset({"salamander", "gecko"})

_SS_OBFS_MODES = frozenset({"tls", "http"})
_SS_V2RAY_MODES = frozenset({"websocket"})
_REALITY_MAX_SID_HEX = 16
_HEX = frozenset("0123456789abcdefABCDEF")

# دلایل رسمی رد سطر جهت ثبت در گزارش سلامت
REASON_SS_METHOD = "ss_unknown_method"
REASON_SS_KEY = "ss_bad_key"
REASON_SS_PLUGIN = "ss_bad_plugin_mode"
REASON_REALITY_NO_TLS = "reality_without_tls"
REASON_REALITY_KEY = "reality_bad_public_key"
REASON_REALITY_SID = "reality_bad_short_id"
REASON_VLESS_ENC = "vless_bad_encryption"
REASON_XHTTP_MODE = "xhttp_bad_mode"
REASON_VMESS_CIPHER = "vmess_bad_cipher"
REASON_VMESS_INT = "vmess_non_integer_field"
REASON_HY2_OBFS = "hysteria2_bad_obfs"
REASON_PORT = "missing_port"


def _query(head: str) -> Dict[str, str]:
    qs = head.split("?", 1)[1] if "?" in head else ""
    out: Dict[str, str] = {}
    try:
        for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True):
            out.setdefault(k, v)
    except ValueError:
        pass
    return out


def _b64_raw_url(s: str) -> Optional[bytes]:
    if "=" in s or "+" in s or "/" in s:
        return None
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (binascii.Error, ValueError):
        return None


def _authority_port(head: str) -> Optional[str]:
    rest = head.split("://", 1)[1] if "://" in head else ""
    rest = re.split(r"[/?]", rest, maxsplit=1)[0]
    hostport = rest.rsplit("@", 1)[-1]
    if hostport.startswith("["):
        close = hostport.find("]")
        if close < 0:
            return None
        tail = hostport[close + 1:]
        return tail[1:] if tail.startswith(":") else ""
    if ":" not in hostport:
        return ""
    return hostport.rpartition(":")[2]


def _reality_reason(q: Dict[str, str]) -> Optional[str]:
    pbk = q.get("pbk", "")
    if not pbk:
        return None
    sec = q.get("security", "").lower()
    if not (sec.endswith("tls") or sec == "reality"):
        return REASON_REALITY_NO_TLS
    key = _b64_raw_url(pbk)
    if key is None or len(key) != 32:
        return REASON_REALITY_KEY
    sid = q.get("sid", "")
    if len(sid) > _REALITY_MAX_SID_HEX or len(sid) % 2 or any(c not in _HEX for c in sid):
        return REASON_REALITY_SID
    return None


def _xhttp_reason(q: Dict[str, str]) -> Optional[str]:
    if q.get("type", "").lower() != "xhttp":
        return None
    mode = q.get("mode", "")
    if mode and mode not in XHTTP_MODES:
        return REASON_XHTTP_MODE
    return None


def _vless_encryption_reason(q: Dict[str, str]) -> Optional[str]:
    enc = q.get("encryption", "")
    if enc in ("", "none"):
        return None
    parts = enc.split(".")
    if len(parts) < 4 or parts[0] != "mlkem768x25519plus":
        return REASON_VLESS_ENC
    if parts[1] not in ("native", "xorpub", "random") or parts[2] not in ("1rtt", "0rtt"):
        return REASON_VLESS_ENC
    keys = 0
    for r in parts[3:]:
        if len(r) < 20:
            continue
        raw = _b64_raw_url(r)
        if raw is None or len(raw) not in (32, 1184):
            return REASON_VLESS_ENC
        keys += 1
    if keys == 0:
        return REASON_VLESS_ENC
    return None


def _ss_reason(head: str, q: Dict[str, str]) -> Optional[str]:
    try:
        u = urllib.parse.urlsplit(head)
        port = u.port
        host_enc = u.netloc.rsplit("@", 1)[-1]
        user = u.username
        password = u.password
    except ValueError:
        return None
    if port is None:
        try:
            dec = base64.b64decode(host_enc + "=" * (-len(host_enc) % 4), validate=True)
            u = urllib.parse.urlsplit("ss://" + dec.decode("utf-8"))
            if u.port is None:
                return None
            user, password = u.username, u.password
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
    if user is None:
        return None
    if password is not None:
        method = urllib.parse.unquote(user)
        password = urllib.parse.unquote(password)
    else:
        raw = urllib.parse.unquote(user)
        dec = None
        for cand in (raw, raw + "=" * (-len(raw) % 4)):
            for fn in (base64.urlsafe_b64decode, base64.b64decode):
                try:
                    dec = fn(cand).decode("utf-8", errors="replace")
                    break
                except (binascii.Error, ValueError):
                    continue
            if dec is not None:
                break
        if dec is None or ":" not in dec:
            return None
        method, password = dec.split(":", 1)
    if method not in SS_METHODS:
        return REASON_SS_METHOD
    need = SS2022_KEY_BYTES.get(method)
    if need is not None:
        for part in password.split(":"):
            try:
                if len(base64.b64decode(part, validate=True)) != need:
                    return REASON_SS_KEY
            except (binascii.Error, ValueError):
                return REASON_SS_KEY
    elif method != "none" and password == "":
        return REASON_SS_KEY
    plugin = q.get("plugin", "")
    if ";" in plugin:
        info = dict(urllib.parse.parse_qsl("pluginName=" + plugin.replace(";", "&"), keep_blank_values=True))
        name = info.get("pluginName", "")
        if "obfs" in name:
            if info.get("obfs", "") not in _SS_OBFS_MODES:
                return REASON_SS_PLUGIN
        elif "v2ray-plugin" in name:
            mode = info.get("mode") or info.get("obfs", "")
            if mode not in _SS_V2RAY_MODES:
                return REASON_SS_PLUGIN
    return None


def _vmess_json_reason(body: str) -> Optional[str]:
    b = body.strip()
    try:
        raw = base64.b64decode(b + "=" * (-len(b) % 4))
    except (binascii.Error, ValueError):
        try:
            raw = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
        except (binascii.Error, ValueError):
            return None
    try:
        obj = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("ps"), str):
        return None
    for field in ("port", "aid"):
        v = obj.get(field)
        if isinstance(v, str) and v != "" and not re.fullmatch(r"[+-]?[0-9]+", v):
            return REASON_VMESS_INT
        if isinstance(v, str) and v == "":
            return REASON_VMESS_INT
    scy = obj.get("scy")
    if isinstance(scy, str) and scy != "" and scy.lower() not in VMESS_CIPHERS:
        return REASON_VMESS_CIPHER
    net = str(obj.get("net") or "").lower()
    if net == "xhttp":
        mode = obj.get("mode")
        if isinstance(mode, str) and mode and mode not in XHTTP_MODES:
            return REASON_XHTTP_MODE
    return None


def fatal_reason(line: str) -> Optional[str]:
    """بررسی اینکه آیا خطی باعث شکستن کل سابسکریپشن کلاینت‌های مبتنی بر Mihomo می‌شود یا خیر."""
    try:
        return _fatal_reason(line)
    except Exception:  # noqa: BLE001
        return None


def _fatal_reason(line: str) -> Optional[str]:
    if not line or "://" not in line:
        return None
    scheme = line.split("://", 1)[0].strip().lower()
    head = line.split("#", 1)[0]

    if scheme == "vmess":
        body = head[len("vmess://"):]
        if "@" not in body:
            return _vmess_json_reason(body)
        q = _query(head)
        enc = q.get("encryption", "")
        if enc and enc.lower() not in VMESS_CIPHERS:
            return REASON_VMESS_CIPHER
        return _reality_reason(q) or _xhttp_reason(q)

    if scheme in ("trojan", "tuic", "hysteria"):
        try:
            parsed = urllib.parse.urlsplit(head)
            parsed.port  # noqa: B018
        except ValueError:
            return None
        if parsed.hostname and _authority_port(head) == "":
            return REASON_PORT

    q = _query(head)
    if scheme == "vless":
        return _reality_reason(q) or _vless_encryption_reason(q) or _xhttp_reason(q)
    if scheme == "trojan":
        return _xhttp_reason(q)
    if scheme == "ss":
        return _ss_reason(head, q)
    if scheme in ("hysteria2", "hy2"):
        obfs = q.get("obfs", "")
        if obfs and (obfs not in HY2_OBFS or not q.get("obfs-password")):
            return REASON_HY2_OBFS
    return None
