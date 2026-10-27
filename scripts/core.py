# -*- coding: utf-8 -*-
"""
scripts/core.py — موتور مرکزی هویت، برندینگ و پردازش کانفیگ‌های Goodbaye Universal Standard.
مالک و مخزن: alireza786786 / ai-driven-v2ray
کانال اصلی: @Goodbaye_filtering | کانال VIP: @CONFIG_V2RAY_VIP

ویژگی‌های منطبق بر منشور:
  • پیاده‌سازی ریمارک ۵ خطی رسمی (نمایش خط‌به‌خط واقعی در VMess و انکود پایدار در سایر پروتکل‌ها)
  • برندینگ رسمی و غیرقابل‌تغییر: 👉🆔@Goodbaye_filtering
  • سرآیندهای درون‌فایلی هیدیفای منطبق بر مخزن ai-driven-v2ray
  • یکتاسازی CDN-aware، فینگرپرینت هویت سرور و رفع باگ‌های پنهان هسته‌ها
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# ۱. هویت برند و متغیرهای منشور بنیادین Goodbaye Universal Standard
# ──────────────────────────────────────────────────────────────────────────────

BRAND_CHANNEL: str = "@Goodbaye_filtering"
VIP_CHANNEL: str = "@CONFIG_V2RAY_VIP"

HIDDIFY_UPDATE_INTERVAL_HOURS: str = os.environ.get("AGG_HIDDIFY_UPDATE_HOURS", "1")

SUPPORT_URL: str = os.environ.get(
    "AGG_SUPPORT_URL", "https://t.me/Goodbaye_filtering"
)

PROJECT_URL: str = os.environ.get(
    "AGG_PROJECT_URL", "https://github.com/alireza786786/ai-driven-v2ray"
)

BASE_PAGES_URL: str = os.environ.get(
    "AGG_PAGES_URL", "https://alireza786786.github.io/ai-driven-v2ray/"
)

HIDDIFY_SUBSCRIPTION_USERINFO: str = "upload=0; download=0; total=0; expire=0"

HIDDIFY_HEADER_KEYS: Tuple[str, ...] = (
    "profile-title",
    "profile-update-interval",
    "subscription-userinfo",
    "support-url",
    "profile-web-page-url",
)


def hiddify_profile_header(label: str) -> str:
    """بلوک ۵ خطی سرآیند متادیتای Hiddify برای ابتدای فایل‌های اشتراک."""
    title = f"{BRAND_CHANNEL} — {label}".strip()
    return (
        f"#profile-title: {title}\n"
        f"#profile-update-interval: {HIDDIFY_UPDATE_INTERVAL_HOURS}\n"
        f"#subscription-userinfo: {HIDDIFY_SUBSCRIPTION_USERINFO}\n"
        f"#support-url: {SUPPORT_URL}\n"
        f"#profile-web-page-url: {PROJECT_URL}\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# ۲. تشخیص هوشمند پروتکل و نام‌گذاری استاندارد (Future-Proof)
# ──────────────────────────────────────────────────────────────────────────────

_SCHEME_ALIASES: Dict[str, str] = {
    "ss": "shadowsocks",
    "shadowsocks": "shadowsocks",
    "ssr": "shadowsocksr",
    "hy": "hysteria",
    "hysteria": "hysteria",
    "hy2": "hysteria2",
    "hysteria2": "hysteria2",
    "wg": "wireguard",
    "wireguard": "wireguard",
    "warp": "wireguard",
    "socks": "socks",
    "socks5": "socks",
}

_NON_PROXY_SCHEMES: frozenset = frozenset({
    "http", "https", "ftp", "ftps", "file", "data", "mailto", "tel", "sms",
    "magnet", "git", "ssh+git", "ws", "wss", "tcp", "udp", "ipfs",
    "android-app", "intent", "javascript", "blob", "about", "chrome",
})

_URI_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+\-.]*)://", re.IGNORECASE)
_MIN_CONFIG_LEN: int = 12

PROTOCOL_ORDER: Tuple[str, ...] = (
    "vless", "vmess", "trojan", "shadowsocks", "shadowsocksr",
    "hysteria2", "hysteria", "tuic", "wireguard",
    "juicity", "anytls", "snell", "mieru", "socks",
)


def normalize_scheme(scheme: str) -> str:
    s = (scheme or "").strip().lower()
    return _SCHEME_ALIASES.get(s, s)


def is_proxy_config(line: str) -> bool:
    if not line:
        return False
    line = line.strip()
    if len(line) < _MIN_CONFIG_LEN or " " in line.split("#", 1)[0]:
        return False
    m = _URI_SCHEME_RE.match(line)
    if not m:
        return False
    scheme = m.group(1).lower()
    if scheme in _NON_PROXY_SCHEMES:
        return False
    after = line.split("://", 1)[1]
    return bool(after) and not after.startswith(("/", "#"))


# ──────────────────────────────────────────────────────────────────────────────
# ۳. تشخیص کشور و پایگاه داده نام‌ها
# ──────────────────────────────────────────────────────────────────────────────

_FLAG_EMOJI_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")

_COUNTRY_KEYWORD_MAP: Dict[str, Tuple[str, str]] = {
    "united states": ("US", "🇺🇸"), "usa": ("US", "🇺🇸"), "america": ("US", "🇺🇸"),
    "آمریکا": ("US", "🇺🇸"), "امریکا": ("US", "🇺🇸"),
    "germany": ("DE", "🇩🇪"), "deutschland": ("DE", "🇩🇪"), "آلمان": ("DE", "🇩🇪"),
    "finland": ("FI", "🇫🇮"), "فنلاند": ("FI", "🇫🇮"),
    "turkey": ("TR", "🇹🇷"), "turkiye": ("TR", "🇹🇷"), "ترکیه": ("TR", "🇹🇷"),
    "united kingdom": ("GB", "🇬🇧"), "uk": ("GB", "🇬🇧"), "england": ("GB", "🇬🇧"),
    "انگلیس": ("GB", "🇬🇧"), "بریتانیا": ("GB", "🇬🇧"),
    "france": ("FR", "🇫🇷"), "فرانسه": ("FR", "🇫🇷"),
    "netherlands": ("NL", "🇳🇱"), "holland": ("NL", "🇳🇱"), "هلند": ("NL", "🇳🇱"),
    "switzerland": ("CH", "🇨🇭"), "سوئیس": ("CH", "🇨🇭"),
    "sweden": ("SE", "🇸🇪"), "سوئد": ("SE", "🇸🇪"),
    "norway": ("NO", "🇳🇴"), "نروژ": ("NO", "🇳🇴"),
    "ireland": ("IE", "🇮🇪"), "ایرلند": ("IE", "🇮🇪"),
    "italy": ("IT", "🇮🇹"), "ایتالیا": ("IT", "🇮🇹"),
    "austria": ("AT", "🇦🇹"), "اتریش": ("AT", "🇦🇹"),
    "belgium": ("BE", "🇧🇪"), "بلژیک": ("BE", "🇧🇪"),
    "portugal": ("PT", "🇵🇹"), "پرتغال": ("PT", "🇵🇹"),
    "spain": ("ES", "🇪🇸"), "اسپانیا": ("ES", "🇪🇸"),
    "denmark": ("DK", "🇩🇰"), "دانمارک": ("DK", "🇩🇰"),
    "poland": ("PL", "🇵🇱"), "لهستان": ("PL", "🇵🇱"),
    "czech republic": ("CZ", "🇨🇿"), "czechia": ("CZ", "🇨🇿"), "czech": ("CZ", "🇨🇿"),
    "romania": ("RO", "🇷🇴"), "رومانی": ("RO", "🇷🇴"),
    "hungary": ("HU", "🇭🇺"), "مجارستان": ("HU", "🇭🇺"),
    "serbia": ("RS", "🇷🇸"), "صربستان": ("RS", "🇷🇸"),
    "bulgaria": ("BG", "🇧🇬"), "بلغارستان": ("BG", "🇧🇬"),
    "croatia": ("HR", "🇭🇷"), "کرواسی": ("HR", "🇭🇷"),
    "luxembourg": ("LU", "🇱🇺"), "لوکزامبورگ": ("LU", "🇱🇺"),
    "latvia": ("LV", "🇱🇻"), "لتونی": ("LV", "🇱🇻"),
    "lithuania": ("LT", "🇱🇹"), "لیتوانی": ("LT", "🇱🇹"),
    "estonia": ("EE", "🇪🇪"), "استونی": ("EE", "🇪🇪"),
    "greece": ("GR", "🇬🇷"), "یونان": ("GR", "🇬🇷"),
    "slovakia": ("SK", "🇸🇰"), "اسلواکی": ("SK", "🇸🇰"),
    "moldova": ("MD", "🇲🇩"), "مولداوی": ("MD", "🇲🇩"),
    "russia": ("RU", "🇷🇺"), "روسیه": ("RU", "🇷🇺"),
    "ukraine": ("UA", "🇺🇦"), "اوکراین": ("UA", "🇺🇦"),
    "kazakhstan": ("KZ", "🇰🇿"), "قزاقستان": ("KZ", "🇰🇿"),
    "singapore": ("SG", "🇸🇬"), "سنگاپور": ("SG", "🇸🇬"),
    "japan": ("JP", "🇯🇵"), "ژاپن": ("JP", "🇯🇵"),
    "south korea": ("KR", "🇰🇷"), "korea": ("KR", "🇰🇷"), "کره": ("KR", "🇰🇷"),
    "hong kong": ("HK", "🇭🇰"), "hongkong": ("HK", "🇭🇰"), "هنگ کنگ": ("HK", "🇭🇰"),
    "taiwan": ("TW", "🇹🇼"), "تایوان": ("TW", "🇹🇼"),
    "china": ("CN", "🇨🇳"), "چین": ("CN", "🇨🇳"),
    "india": ("IN", "🇮🇳"), "هند": ("IN", "🇮🇳"),
    "iran": ("IR", "🇮🇷"), "ایران": ("IR", "🇮🇷"),
    "indonesia": ("ID", "🇮🇩"), "اندونزی": ("ID", "🇮🇩"),
    "vietnam": ("VN", "🇻🇳"), "ویتنام": ("VN", "🇻🇳"),
    "thailand": ("TH", "🇹🇭"), "تایلند": ("TH", "🇹🇭"),
    "malaysia": ("MY", "🇲🇾"), "مالزی": ("MY", "🇲🇾"),
    "pakistan": ("PK", "🇵🇰"), "پاکستان": ("PK", "🇵🇰"),
    "uae": ("AE", "🇦🇪"), "dubai": ("AE", "🇦🇪"), "امارات": ("AE", "🇦🇪"),
    "egypt": ("EG", "🇪🇬"), "مصر": ("EG", "🇪🇬"),
    "south africa": ("ZA", "🇿🇦"), "آفریقای جنوبی": ("ZA", "🇿🇦"),
    "canada": ("CA", "🇨🇦"), "کانادا": ("CA", "🇨🇦"),
    "australia": ("AU", "🇦🇺"), "استرالیا": ("AU", "🇦🇺"),
    "new zealand": ("NZ", "🇳🇿"), "نیوزیلند": ("NZ", "🇳🇿"),
    "brazil": ("BR", "🇧🇷"), "برزیل": ("BR", "🇧🇷"),
    "argentina": ("AR", "🇦🇷"), "آرژانتین": ("AR", "🇦🇷"),
    "mexico": ("MX", "🇲🇽"), "مکزیک": ("MX", "🇲🇽"),
}

_CC_TO_NAME: Dict[str, str] = {
    "US": "United States", "DE": "Germany", "FI": "Finland", "TR": "Turkey",
    "GB": "United Kingdom", "FR": "France", "NL": "Netherlands", "CH": "Switzerland",
    "SE": "Sweden", "NO": "Norway", "IE": "Ireland", "IT": "Italy",
    "AT": "Austria", "BE": "Belgium", "PT": "Portugal", "ES": "Spain",
    "DK": "Denmark", "PL": "Poland", "CZ": "Czech Republic", "RO": "Romania",
    "HU": "Hungary", "RS": "Serbia", "BG": "Bulgaria", "HR": "Croatia",
    "LU": "Luxembourg", "LV": "Latvia", "LT": "Lithuania", "EE": "Estonia",
    "GR": "Greece", "SK": "Slovakia", "MD": "Moldova", "RU": "Russia",
    "UA": "Ukraine", "KZ": "Kazakhstan", "SG": "Singapore", "JP": "Japan",
    "KR": "South Korea", "HK": "Hong Kong", "TW": "Taiwan", "CN": "China",
    "IN": "India", "IR": "Iran", "ID": "Indonesia", "VN": "Vietnam",
    "TH": "Thailand", "MY": "Malaysia", "PK": "Pakistan", "AE": "UAE",
    "EG": "Egypt", "ZA": "South Africa", "CA": "Canada", "AU": "Australia",
    "NZ": "New Zealand", "BR": "Brazil", "AR": "Argentina", "MX": "Mexico",
    "Global": "Global Network"
}

_VALID_CC = frozenset(v[0] for v in _COUNTRY_KEYWORD_MAP.values())
_SORTED_KEYWORDS = sorted(_COUNTRY_KEYWORD_MAP.items(), key=lambda x: len(x[0]), reverse=True)


def _flag_to_country_code(flag: str) -> Optional[str]:
    if len(flag) != 2:
        return None
    try:
        c1 = chr(ord(flag[0]) - 0x1F1E6 + 65)
        c2 = chr(ord(flag[1]) - 0x1F1E6 + 65)
        code = f"{c1}{c2}"
        return code if code in _VALID_CC else None
    except Exception:
        return None


def detect_country_from_remark(remark: str) -> Tuple[str, str]:
    if not remark:
        return ("Global", "🌐")
    unquoted = urllib.parse.unquote(remark)
    for flag in _FLAG_EMOJI_RE.findall(unquoted):
        code = _flag_to_country_code(flag)
        if code:
            return (code, flag)
    remark_lower = unquoted.lower()
    for keyword, info in _SORTED_KEYWORDS:
        if _keyword_hit(remark_lower, keyword):
            return info
    return ("Global", "🌐")


def _keyword_hit(haystack: str, needle: str) -> bool:
    if len(needle) > 3:
        return needle in haystack
    i = haystack.find(needle)
    while i != -1:
        before = haystack[i - 1] if i > 0 else ""
        after = haystack[i + len(needle)] if i + len(needle) < len(haystack) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        i = haystack.find(needle, i + 1)
    return False


_HOST_COUNTRY_CACHE: Dict[str, Tuple[str, str]] = {}


def country_for_endpoint(endpoint: str, remark_hint: str = "") -> Tuple[str, str]:
    ep = (endpoint or "").strip().lower()
    if not ep:
        return detect_country_from_remark(remark_hint)
    cached = _HOST_COUNTRY_CACHE.get(ep)
    if cached is not None:
        return cached

    try:
        from . import geo  # type: ignore
    except Exception:
        try:
            import geo  # type: ignore
        except Exception:
            geo = None  # type: ignore

    if geo is not None:
        try:
            hit = geo.country_for_host(ep)
        except Exception:
            hit = None
        if hit:
            _HOST_COUNTRY_CACHE[ep] = hit
            return hit

    info = detect_country_from_remark(remark_hint)
    if info[0] != "Global":
        _HOST_COUNTRY_CACHE[ep] = info
    return info


def reset_country_cache() -> None:
    _HOST_COUNTRY_CACHE.clear()


# ──────────────────────────────────────────────────────────────────────────────
# ۴. الگوی ۵ خطی ریمارک رسمی (Goodbaye Universal Standard - اصل اول منشور)
# ──────────────────────────────────────────────────────────────────────────────

def build_5line_remark(
    flag: str,
    country_name: str,
    city_or_dc: str = "Cloud",
    ping_ms: Optional[int] = None,
    proto: str = "VLESS",
    ip_version: str = "IPv4",
    feature: str = "VIP-Strict",
    url_encode: bool = True,
) -> str:
    """
    ساخت الگوی ۵ خطی رسمی طبق اصل اول منشور:
      👉🆔@Goodbaye_filtering
      📡[پرچم] [کشور]
      ®️[دیتاسنتر یا شهر]
      🅿️ping:[پینگ]ms
      ⚡[قابلیت] | [پروتکل و آی‌پی]
    """
    p_str = f"{int(ping_ms)}" if (ping_ms is not None and ping_ms > 0) else "250"
    dc_str = city_or_dc.strip() if (city_or_dc and city_or_dc.strip()) else "Cloud"
    country_clean = country_name.strip() if country_name else "Global Network"

    lines = [
        f"👉🆔{BRAND_CHANNEL}",
        f"📡{flag} {country_clean}",
        f"®️{dc_str}",
        f"🅿️ping:{p_str}ms",
        f"⚡{feature} | {proto.upper()} {ip_version}",
    ]
    raw_multiline = "\n".join(lines)
    return urllib.parse.quote(raw_multiline, safe="") if url_encode else raw_multiline


# ──────────────────────────────────────────────────────────────────────────────
# ۵. دیکد قطعی Base64، حل آدرس و فینگرپرینت هویت سرور
# ──────────────────────────────────────────────────────────────────────────────

_B64_BODY_RE = re.compile(r"^[A-Za-z0-9+/_-]+={0,2}$")


def decode_base64_text(candidate: str) -> Optional[str]:
    s = (candidate or "").strip()
    if not s or not _B64_BODY_RE.match(s):
        return None
    body = s.rstrip("=")
    if len(body) % 4 == 1:
        return None
    body += "=" * ((4 - len(body) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(body)
    except Exception:
        return None
    return raw.decode("utf-8", errors="ignore")


def _ssr_b64_text(s: Optional[str], *, allow_empty: bool = False) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return "" if allow_empty else None
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(s, validate=False).decode("utf-8")
    except Exception:
        return None


def _ssr_parts(line: str) -> Optional[Tuple[str, str, str, str, str, str, str, str]]:
    if not line.startswith("ssr://"):
        return None
    body = line[len("ssr://"):].split("#", 1)[0].strip()
    txt = _ssr_b64_text(body)
    if not txt:
        return None
    main, _sep, qs = txt.partition("/?")
    parts = main.split(":")
    if len(parts) != 6:
        return None
    host, port_s, proto, method, obfs, pwd_b64 = parts
    if not host or not port_s.isdigit():
        return None
    pwd = _ssr_b64_text(pwd_b64, allow_empty=True)
    if pwd is None:
        return None
    sq = urllib.parse.parse_qs(qs)
    obfsparam = _ssr_b64_text((sq.get("obfsparam") or [""])[0], allow_empty=True) or ""
    protoparam = _ssr_b64_text((sq.get("protoparam") or [""])[0], allow_empty=True) or ""
    return (host, port_s, proto, method, obfs, pwd, obfsparam, protoparam)


def endpoint_of(line: str) -> str:
    line = (line or "").strip()
    if not line:
        return ""
    try:
        if line.startswith("vmess://"):
            b64 = line[8:].split("#")[0].strip()
            _txt = decode_base64_text(b64)
            obj = json.loads(_txt) if _txt is not None else None
            if isinstance(obj, dict):
                host = str(obj.get("add") or obj.get("host") or "").strip().lower()
                if host:
                    return host
        if line.startswith("ssr://"):
            _p = _ssr_parts(line)
            if _p:
                return _p[0].strip().lower()
        rest = line.split("://", 1)[1] if "://" in line else line
        rest = rest.split("#", 1)[0].split("?", 1)[0]
        if "@" in rest:
            rest = rest.rsplit("@", 1)[1]
        rest = rest.split("/", 1)[0]
        if rest.startswith("["):
            return rest.split("]", 1)[0][1:].lower()
        return rest.rsplit(":", 1)[0].lower() if ":" in rest else rest.lower()
    except Exception:
        return ""


def stable_label(line: str) -> str:
    key = dedup_key(line) or (line or "").strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:6].upper()


_IDENTITY_PARAMS = frozenset({
    "security", "sni", "pbk", "sid", "host", "path", "servicename",
    "flow", "type", "headertype", "encryption", "mode", "alpn", "extra",
    "obfs", "obfs-password", "obfspassword", "congestion_control",
    "congestion", "publickey", "presharedkey", "address",
})


def _norm_type(t: str) -> str:
    t = (t or "").strip().lower()
    return "tcp" if t in ("", "raw", "none", "tcp") else t


_INSECURE_SCHEMES = frozenset({"hysteria2", "hy2", "tuic"})
_INSECURE_KEYS = ("insecure", "allowInsecure", "allow_insecure")
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def _insecure_flag(raw_params: dict) -> str:
    for k in _INSECURE_KEYS:
        v = raw_params.get(k)
        if v:
            return "1" if str(v[0] or "").strip().lower() in _TRUTHY_VALUES else "0"
    return "0"


_FRONT_HOST_BAD_CHARS = frozenset(' \t\r\n/:@?#{}"\\,;|<>()[]')


def _is_plausible_fronting_host(v: str) -> bool:
    if not v or len(v) > 253:
        return False
    if v.startswith("[") and v.endswith("]") and len(v) > 2:
        return True
    for ch in v:
        if ch in _FRONT_HOST_BAD_CHARS:
            return False
    if v.endswith("."):
        v = v[:-1]
    if not v or ".." in v or "." not in v:
        return False
    for lab in v.split("."):
        if not lab or len(lab) > 63:
            return False
        if lab[0] == "-" or lab[-1] == "-":
            return False
        for ch in lab:
            if not (ch.isascii() and (ch.isalnum() or ch == "-")):
                return False
    return True


def _sni_is_endpoint(security: str) -> bool:
    return security == "tls"


def _norm_aid(v: Any) -> str:
    try:
        return str(int(str(v).strip() or "0"))
    except Exception:
        return "0"


_CASE_SENSITIVE_PARAMS = frozenset({
    "path", "servicename", "pbk", "publickey", "presharedkey",
    "obfs-password", "obfspassword",
})


def _norm_identity_value(key: str, val: str) -> str:
    if key in _CASE_SENSITIVE_PARAMS:
        return (val or "").strip()
    v = (val or "").strip().lower()
    if key in ("sni", "host"):
        for _ in range(2):
            nv = urllib.parse.unquote(v)
            if nv == v:
                break
            v = nv
        v = v.strip().lower()
    if key == "type":
        nt = _norm_type(v)
        return "" if nt == "tcp" else nt
    if key in ("encryption", "security", "headertype"):
        return "" if v in ("", "none") else v
    if key == "flow":
        return "" if v == "" else v
    return v


_VMESS_SECURITY: frozenset = frozenset({
    "auto", "none", "zero", "aes-128-cfb", "aes-128-gcm", "chacha20-poly1305",
})


def _vmess_security(scy: object) -> str:
    s = str(scy or "").strip().lower()
    return s if s in _VMESS_SECURITY else "auto"


def dedup_key(line: str) -> str:
    line = line.strip()
    if not line:
        return line

    if line.startswith("vmess://"):
        try:
            b64 = line[8:].split("#")[0].strip()
            _txt = decode_base64_text(b64)
            if _txt is None:
                raise ValueError("vmess payload is not base64")
            obj = json.loads(_txt)
            add = (str(obj.get("add") or "")).strip().lower()
            host = _norm_identity_value("host", str(obj.get("host") or ""))
            sni = _norm_identity_value("sni", str(obj.get("sni") or ""))
            tls = (str(obj.get("tls") or "")).strip().lower()
            tls = tls if tls in ("tls", "reality", "xtls") else ""
            net = _norm_type(str(obj.get("net") or ""))
            path = str(obj.get("path") or "")
            path = "/" if path == "" else path
            if host and not _is_plausible_fronting_host(host):
                host = ""
            if sni and not (_is_plausible_fronting_host(sni) and _sni_is_endpoint(tls)):
                sni = ""
            srv = _norm_identity_value(
                "sni", str(obj.get("sni") or "") or str(obj.get("host") or "")
            )
            if srv and not _is_plausible_fronting_host(srv):
                srv = ""
            fronting = f"{host}~{sni}" if sni else host
            add_for_key = add
            return (
                f"vmess:{add_for_key}|ep={fronting}"
                f":{str(obj.get('port', '')).strip()}"
                f":{str(obj.get('id', '')).strip().lower()}"
                f":{net}:{path}:{tls}"
                f":{_norm_aid(obj.get('aid'))}"
                f":{_vmess_security(obj.get('scy'))}"
                f":srv={srv}"
            )
        except Exception:
            return line.split("#")[0].strip()[:120]

    if line.startswith("ss://"):
        try:
            without_remark = line.split("#")[0].strip()
            rest = without_remark[5:]
            authority = rest.split("?", 1)[0]
            if "@" in authority:
                userinfo, hostpart = authority.rsplit("@", 1)
                hostpart = hostpart.split("/", 1)[0]
                decoded_ui = decode_base64_text(userinfo)
                if decoded_ui and ":" in decoded_ui:
                    userinfo = decoded_ui
                userinfo = urllib.parse.unquote(userinfo).lower()
                host, _, port = hostpart.rpartition(":")
                return f"ss:sip002:{userinfo}@{host.lower()}:{port}"
            else:
                decoded = decode_base64_text(rest)
                if decoded is None:
                    raise ValueError("ss legacy body is not base64")
                _d = decoded.split("#")[0].split("?")[0]
                if "@" in _d:
                    _ui, _hp = _d.rsplit("@", 1)
                    _hp = _hp.split("/", 1)[0]
                    _h, _, _pt = _hp.rpartition(":")
                    if _h and _pt:
                        _ui = urllib.parse.unquote(_ui).lower()
                        return f"ss:sip002:{_ui}@{_h.lower()}:{_pt}"
                return f"ss:legacy:{decoded.lower()}"
        except Exception:
            return line.split("#")[0].strip()[:120]

    if line.startswith("ssr://"):
        try:
            p = _ssr_parts(line)
            if p:
                host, port_s, proto, method, obfs, pwd, obfsparam, protoparam = p
                q = urllib.parse.quote
                return (
                    f"ssr:{host.strip().lower()}:{port_s}"
                    f":{proto.strip().lower()}:{method.strip().lower()}"
                    f":{obfs.strip().lower()}:{q(pwd, safe='')}"
                    f":op={q(obfsparam, safe='')}:pp={q(protoparam, safe='')}"
                )
        except Exception:
            pass

    try:
        without_remark = line.split("#")[0].strip()
        parsed = urllib.parse.urlparse(without_remark)
        raw_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        meaningful = {}
        for pk, pv in raw_params.items():
            kl = pk.strip().lower()
            if kl not in _IDENTITY_PARAMS:
                continue
            nv = _norm_identity_value(kl, str(pv[0]) if pv else "")
            if nv != "":
                meaningful[kl] = nv
        if parsed.scheme.lower() in _INSECURE_SCHEMES:
            meaningful["insecure"] = _insecure_flag(raw_params)
        username = urllib.parse.unquote(parsed.username or "").lower()
        password = urllib.parse.unquote(parsed.password or "").lower()
        conn_host = (parsed.hostname or "").lower()
        try:
            port = str(parsed.port or "")
        except Exception:
            port = ""
        path = parsed.path.rstrip("/")
        sni_val = meaningful.get("sni", "")
        host_val = meaningful.get("host", "")
        security_val = meaningful.get("security", "")
        if sni_val and not _is_plausible_fronting_host(sni_val):
            sni_val = ""
            meaningful.pop("sni", None)
        elif sni_val and not _sni_is_endpoint(security_val):
            sni_val = ""
        if host_val and not _is_plausible_fronting_host(host_val):
            host_val = ""
            meaningful.pop("host", None)
        endpoint = sni_val or host_val
        host_for_key = conn_host
        sorted_query = "&".join(f"{k2}={meaningful[k2]}" for k2 in sorted(meaningful))
        return (
            f"{parsed.scheme.lower()}:"
            f"{username}:{password}"
            f"@{host_for_key}|ep={endpoint}"
            f":{port}{path}?{sorted_query}"
        )
    except Exception:
        pass
    return line.split("#")[0].strip()[:200]


# ──────────────────────────────────────────────────────────────────────────────
# ۶. تشخیص کانفیگ خراب، برندینگ ۵ خطی واقعی و راستی‌آزمایی
# ──────────────────────────────────────────────────────────────────────────────

_DUMMY_INDICATORS = (
    "00000000-0000-0000-0000-000000000000",
    "app%20not%20supported",
    "app not supported",
    "proxies: []",
)


def is_dummy_config(config: str) -> bool:
    if not config:
        return False
    c = config.lower()
    return any(ind in c for ind in _DUMMY_INDICATORS)


def brand_remark(
    line: str,
    idx: Any = None,
    delay: Optional[int] = None,
    city_or_dc: Optional[str] = None,
) -> str:
    """
    اعمال الگوی ۵ خطی رسمی منشور بنیادین:
      • در VMess: ثبت به صورت متن ۵ خطی با خطوط واقعی (\n) درون JSON
      • در سایر پروتکل‌ها: انکود استاندارد برای Fragment لینک
    """
    line = line.strip()
    if not line:
        return line

    proto = protocol_of(line) or "PROX"
    host = endpoint_of(line)
    ip_version = "IPv6" if (":" in host and not host.startswith(".")) else "IPv4"

    old_remark = remark_of(line)
    code, flag = country_for_endpoint(host, old_remark)
    country_name = _CC_TO_NAME.get(code, code)
    datacenter = city_or_dc or "Cloud"

    # پشتیبانی کامل و اصولی از VMess JSON (نمایش خط‌به‌خط واقعی در کلاینت)
    if line.startswith("vmess://"):
        try:
            b64 = line[8:].split("#")[0].strip()
            _txt = decode_base64_text(b64)
            obj = json.loads(_txt) if _txt is not None else None
            if isinstance(obj, dict):
                # برای VMess در JSON مقدار ps به صورت ۵ خطی واقعی درج می‌شود (بدون درصد و کدهای انکود)
                multiline_remark = build_5line_remark(
                    flag=flag,
                    country_name=country_name,
                    city_or_dc=datacenter,
                    ping_ms=delay,
                    proto="VMESS",
                    ip_version=ip_version,
                    feature="VIP-Strict",
                    url_encode=False,
                )
                obj["ps"] = multiline_remark
                if "name" in obj:
                    obj["name"] = multiline_remark
                encoded = base64.b64encode(
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).decode("utf-8")
                return f"vmess://{encoded}"
        except Exception:
            pass

    # برای تمامی پروتکل‌های دیگر (VLESS, Trojan, SS, TUIC, Hysteria2 و...)
    encoded_remark = build_5line_remark(
        flag=flag,
        country_name=country_name,
        city_or_dc=datacenter,
        ping_ms=delay,
        proto=proto,
        ip_version=ip_version,
        feature="VIP-Strict",
        url_encode=True,
    )
    core_part = line.split("#", 1)[0]
    return f"{core_part}#{encoded_remark}"


def remark_of(line: str) -> str:
    """خواندن ریمارک کاربر (با پشتیبانی از خطوط واقعی و انکودشده)."""
    if not line:
        return ""
    s = line.strip()
    if s.startswith("vmess://"):
        b64 = s[8:].split("#")[0].strip()
        txt = decode_base64_text(b64)
        if txt is not None:
            try:
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    raw_ps = str(obj.get("ps") or obj.get("name") or "")
                    return urllib.parse.unquote(raw_ps)
            except Exception:
                pass
    if "#" in s:
        frag = s.split("#", 1)[1]
        try:
            return urllib.parse.unquote(frag)
        except Exception:
            return frag
    return ""


def is_branded(line: str) -> bool:
    rem = remark_of(line)
    return BRAND_CHANNEL in rem or BRAND_CHANNEL in urllib.parse.unquote(rem)


def protocol_of(line: str) -> Optional[str]:
    if not line:
        return None
    m = _URI_SCHEME_RE.match(line.strip())
    if not m:
        return None
    scheme = m.group(1).lower()
    if scheme in _NON_PROXY_SCHEMES:
        return None
    return normalize_scheme(scheme)


# ──────────────────────────────────────────────────────────────────────────────
# ۷. دیکد بدنه سورس‌ها، پاک‌سازی کاراکترهای مخرب و محافظت از هیدیفای
# ──────────────────────────────────────────────────────────────────────────────

def try_base64_decode(raw: str) -> Optional[str]:
    clean_raw = re.sub(r"\s+", "", raw)
    if not clean_raw:
        return None
    padded = clean_raw + "=" * (-len(clean_raw) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded_bytes = decoder(padded)
        except Exception:
            continue
        for encoding in ("utf-8", "latin-1"):
            try:
                text = decoded_bytes.decode(encoding)
                non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if not non_empty:
                    continue
                valid = [ln for ln in non_empty if is_proxy_config(ln)]
                if valid and (len(valid) / len(non_empty)) >= 0.20:
                    return text
            except UnicodeDecodeError:
                continue
    return None


_AMP_SEP = re.compile(r"&amp;(?=[A-Za-z_][A-Za-z0-9_.\-]*=)")


def _repair_amp_separator(line: str) -> str:
    if "&amp;" not in line:
        return line
    return _AMP_SEP.sub("&", line)


_CTRL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _pct_encode_ctrl(text: str) -> str:
    return _CTRL_CHAR_RE.sub(lambda m: "%%%02X" % ord(m.group(0)), text)


def _repair_control_chars(line: str) -> str:
    if not _CTRL_CHAR_RE.search(line):
        return line
    head, frag_sep, frag = line.partition("#")
    authority, query_sep, query = head.partition("?")
    if _CTRL_CHAR_RE.search(authority):
        return ""
    repaired = authority + query_sep + _pct_encode_ctrl(query)
    if frag_sep:
        repaired += frag_sep + _pct_encode_ctrl(frag)
    return repaired


_PACKET_ENCODING_SUPPORTED = frozenset({"xudp", "packetaddr"})
_BAD_PCT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _go_query_unescape(text: str) -> Optional[str]:
    if _BAD_PCT_ESCAPE_RE.search(text):
        return None
    return urllib.parse.unquote_plus(text)


def _strip_vless_packet_encoding(line: str) -> str:
    head, frag_sep, frag = line.partition("#")
    base, query_sep, query = head.partition("?")
    if not query_sep or not query:
        return line
    pairs = query.split("&")
    hits: List[int] = []
    groups: Dict[str, List[str]] = {}
    for i, pair in enumerate(pairs):
        if not pair or ";" in pair:
            continue
        raw_key, _eq, raw_val = pair.partition("=")
        key = _go_query_unescape(raw_key)
        val = _go_query_unescape(raw_val)
        if key is None or val is None:
            continue
        if key.lower().replace("_", "") != "packetencoding":
            continue
        hits.append(i)
        groups.setdefault(key, []).append(val)
    if not hits:
        return line
    if all(",".join(vals) in _PACKET_ENCODING_SUPPORTED for vals in groups.values()):
        return line
    drop = set(hits)
    kept = [p for i, p in enumerate(pairs) if i not in drop]
    new_query = "&".join(kept)
    rebuilt = base + ("?" + new_query if new_query else "")
    if frag_sep:
        rebuilt += frag_sep + frag
    return rebuilt


def _strip_vmess_packet_encoding(line: str) -> str:
    b64 = line[8:].split("#")[0].strip()
    if not b64:
        return line
    try:
        txt = decode_base64_text(b64)
        obj = json.loads(txt) if txt is not None else None
    except Exception:
        return line
    if not isinstance(obj, dict) or "packetEncoding" not in obj:
        return line
    value = obj["packetEncoding"]
    if isinstance(value, str) and value in _PACKET_ENCODING_SUPPORTED:
        return line
    try:
        del obj["packetEncoding"]
        encoded = base64.b64encode(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
    except Exception:
        return line
    frag = line[8:].partition("#")
    return f"vmess://{encoded}" + (frag[1] + frag[2] if frag[1] else "")


def _normalize_packet_encoding(line: str) -> str:
    if not line:
        return line
    scheme = line[:8].lower()
    if scheme == "vless://":
        return _strip_vless_packet_encoding(line)
    if scheme == "vmess://":
        return _strip_vmess_packet_encoding(line)
    return line


def extract_valid_lines(content: str) -> List[str]:
    if not content:
        return []
    first_real = next(
        (ln.strip() for ln in content.splitlines()
         if ln.strip() and not ln.strip().startswith("//") and not ln.strip().startswith("#")),
        "",
    )
    if not is_proxy_config(first_real):
        decoded = try_base64_decode(content)
        if decoded:
            content = decoded
    return [
        line for raw in content.splitlines()
        if (line := _normalize_packet_encoding(
            _repair_control_chars(_repair_amp_separator(raw.strip()))))
        and is_proxy_config(line)
    ]


RAY2SING_PREFIXES = frozenset({
    "vmess://", "vless://", "trojan://", "svmess://", "svless://", "strojan://",
    "ss://", "tuic://", "hysteria://", "hysteria2://", "hy2://", "ssh://",
    "naive://", "ssconf://", "direct://", "socks://", "phttp://", "phttps://",
    "http://", "https://", "xvmess://", "xvless://", "xtrojan://", "xdirect://",
    "mieru://", "mierus://", "psiphon://", "dnstt://",
    "wg://", "wireguard://", "warp://", "awg://", "[Interface]",
})

SHIELD_LINE: str = "# --- below: schemes sing-box cannot parse (skipped by Hiddify) ---"
_RAY2SING_PREFIX_TUPLE: Tuple[str, ...] = tuple(sorted(RAY2SING_PREFIXES))


def is_ray2sing_prefixed(line: str) -> bool:
    return line.startswith(_RAY2SING_PREFIX_TUPLE)


def _is_shield(line: str) -> bool:
    return line.startswith("#") or line.startswith("//")


def shield_unsupported_runs(lines: List[str]) -> List[str]:
    out: List[str] = []
    prev_is_shield = False
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        if _is_shield(line):
            prev_is_shield = True
        elif is_ray2sing_prefixed(line):
            prev_is_shield = False
        elif not prev_is_shield:
            out.append(SHIELD_LINE)
            prev_is_shield = True
        out.append(line)
    return out


def encode_base64_subscription(lines: List[str], header: str = "") -> str:
    joined = "\n".join(shield_unsupported_runs(lines))
    return base64.b64encode((header + joined).encode("utf-8")).decode("ascii")


class ControlByteInOutput(ValueError):
    """گارد سخت‌گیرانه برای ممانعت از نشت بایت‌های کنترلی ممنوع."""


_FORBIDDEN_OUTPUT_CHAR_RE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def assert_no_control_bytes(path: str, content: str) -> None:
    m = _FORBIDDEN_OUTPUT_CHAR_RE.search(content)
    if m is None:
        return
    offset = m.start()
    line_no = content.count("\n", 0, offset) + 1
    line_start = content.rfind("\n", 0, offset) + 1
    column = offset - line_start + 1
    total = len(_FORBIDDEN_OUTPUT_CHAR_RE.findall(content))
    excerpt = content[max(line_start, offset - 40):offset + 40]
    raise ControlByteInOutput(
        f"refusing to write {path!r}: forbidden control byte "
        f"0x{ord(m.group(0)):02X} at line {line_no}, column {column} "
        f"(byte offset {offset}); {total} forbidden byte(s) in total; "
        f"excerpt={excerpt!r}"
    )
