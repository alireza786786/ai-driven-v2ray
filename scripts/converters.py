
# -*- coding: utf-8 -*-
"""
scripts/converters.py — مبدل جامع پروتکل‌های پروکسی به فرمت‌های استاندارد Clash (Mihomo) YAML و Sing-box JSON.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

پروتکل‌های تحت پوشش: VLESS, VMess, Trojan, Shadowsocks, ShadowsocksR, Hysteria2, TUIC.
ویژگی‌ها و تضمین‌های منشور:
  • اتصال مستقیم به هویت رسمی برند: @Goodbaye_filtering
  • سازگاری کامل با ریمارک‌های ۵ خطی رسمی (URL-Encoded تک‌خطی برای جلوگیری از شکستن کلاینت‌ها)
  • حفظ گارد طلایی: هرگز خروجی نامعتبر تولید نکن (جلوگیری از باگ‌های All-or-Nothing در کلش و هیدیفای)
  • اصلاح خودکار کاراکترهای درصد تنها (%) در مسیرها برای جلوگیری از کرش هسته Go
  • دامپر اختصاصی YAML برای حل ناسازگاری PyYAML 1.1 با YAML 1.2
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import core

# ──────────────────────────────────────────────────────────────────────────────
# ۱. هویت برند و گروه‌های خروجی (Goodbaye Universal Standard)
# ──────────────────────────────────────────────────────────────────────────────
BRAND: str = core.BRAND_CHANNEL

GROUP_MAIN: str = f"🚀 {BRAND}"
GROUP_AUTO: str = f"♻️ Auto | {BRAND}"
GROUP_FALLBACK: str = f"🔯 Fallback | {BRAND}"


def _branded_fallback(kind: Optional[str]) -> str:
    """تولید نام پشتیبان دارای هویت رسمی برند در صورت نبود ریمارک اولیه."""
    k = (kind or "").strip() or "node"
    return f"{k} | {BRAND}"


def _enforce_brand(name: Optional[str], kind: Optional[str]) -> str:
    """
    تضمین حضور هویت رسمی @Goodbaye_filtering در نام و تگ نهایی خروجی
    (با پشتیبانی از ریمارک‌های ۵ خطی انکودشده و دیکودشده).
    """
    nm = name or ""
    if BRAND in nm or BRAND in urllib.parse.unquote(nm):
        return nm
    return _branded_fallback(kind)


# ──────────────────────────────────────────────────────────────────────────────
# ۲. لیست‌های سفید سازگاری هسته‌ها (Mihomo & Sing-box)
# ──────────────────────────────────────────────────────────────────────────────

SS_CIPHERS: frozenset = frozenset({
    "aes-128-gcm", "aes-192-gcm", "aes-256-gcm",
    "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
    "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr",
    "rc4-md5", "chacha20-ietf", "none",
})

SS2022_KEY_BYTES: Dict[str, int] = {
    "2022-blake3-aes-128-gcm": 16,
    "2022-blake3-aes-256-gcm": 32,
    "2022-blake3-chacha20-poly1305": 32,
}

SSR_CIPHERS: frozenset = frozenset({
    "rc4-md5",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr",
    "aes-128-cfb", "aes-192-cfb", "aes-256-cfb",
    "chacha20", "chacha20-ietf", "xchacha20",
    "none", "dummy",
})

SSR_OBFS: frozenset = frozenset({
    "plain", "http_simple", "http_post", "random_head",
    "tls1.2_ticket_auth", "tls1.2_ticket_fastauth",
})

SSR_PROTOCOLS: frozenset = frozenset({
    "origin", "auth_sha1_v4", "auth_aes128_md5", "auth_aes128_sha1",
    "auth_chain_a", "auth_chain_b",
})

UTLS_FINGERPRINTS: frozenset = frozenset({
    "chrome", "firefox", "edge", "safari", "ios", "android",
    "random", "randomized", "qq", "360",
})

DEFAULT_UTLS_FINGERPRINT: str = "chrome"
VLESS_FLOWS: frozenset = frozenset({"xtls-rprx-vision"})
_HEX_DIGITS: frozenset = frozenset("0123456789abcdefABCDEF")


def _sanitize_flow(flow: str) -> str:
    f = (flow or "").strip().lower()
    if f in VLESS_FLOWS:
        return f
    if f.startswith("xtls-rprx-vision"):
        return "xtls-rprx-vision"
    return ""


def _sanitize_short_id(sid: str) -> Optional[str]:
    s = (sid or "").strip()
    if s == "":
        return ""
    if len(s) > 16 or len(s) % 2 != 0:
        return None
    if any(ch not in _HEX_DIGITS for ch in s):
        return None
    return s


def _sanitize_pbk(pbk: str) -> Optional[str]:
    s = (pbk or "").strip()
    if len(s) != 43:
        return None
    try:
        if len(base64.urlsafe_b64decode(s + "=")) != 32:
            return None
    except Exception:
        return None
    return s


def _sanitize_ss(cipher: str, password: str) -> Optional[tuple]:
    cipher = (cipher or "").strip().lower()
    if cipher not in SS_CIPHERS:
        return None
    if not password:
        return None
    need = SS2022_KEY_BYTES.get(cipher)
    if need is not None:
        for part in password.split(":"):
            try:
                raw = base64.b64decode(part + "=" * ((4 - len(part) % 4) % 4), validate=False)
            except Exception:
                return None
            if len(raw) != need:
                return None
    return cipher, password


_SS_B64_RE = re.compile(r"^[A-Za-z0-9+/_-]+={0,2}$")


def _ss_userinfo(raw: str) -> str:
    text = urllib.parse.unquote(raw or "")
    s = text.strip()
    if s and _SS_B64_RE.match(s):
        body = s.rstrip("=")
        if len(body) % 4 != 1:
            try:
                dec = base64.urlsafe_b64decode(
                    body.replace("+", "-").replace("/", "_") + "=" * (-len(body) % 4)
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                dec = None
            if dec and ":" in dec:
                return dec
    return text


_SS_PLUGIN_UNUSABLE = object()


def _sip003_split(text: str) -> List[tuple]:
    out: List[tuple] = []
    key: List[str] = []
    val: Optional[List[str]] = None
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            (key if val is None else val).append(text[i + 1])
            i += 2
            continue
        if ch == ";":
            out.append(("".join(key), None if val is None else "".join(val)))
            key, val = [], None
        elif ch == "=" and val is None:
            val = []
        else:
            (key if val is None else val).append(ch)
        i += 1
    out.append(("".join(key), None if val is None else "".join(val)))
    return out


def _sip003_escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace("=", "\\=")


def _ss_plugin(query: str) -> Any:
    try:
        qs = dict(urllib.parse.parse_qsl(query or "", keep_blank_values=True))
    except ValueError:
        return None
    plugin = qs.get("plugin", "")
    if not plugin or ";" not in plugin:
        return None
    parts = _sip003_split(plugin)
    name = parts[0][0].strip()
    opts: Dict[str, str] = {}
    flags = set()
    for k, v in parts[1:]:
        k = k.strip()
        if not k:
            continue
        if v is None:
            flags.add(k)
        else:
            opts[k] = v.strip()
    if "obfs" in name:
        mode = opts.get("obfs", "")
        if mode not in ("http", "tls"):
            return _SS_PLUGIN_UNUSABLE
        return {"name": "obfs", "mode": mode, "host": _clean_sni(opts.get("obfs-host")) or ""}
    if "v2ray-plugin" in name:
        mode = opts.get("mode") or opts.get("obfs", "")
        if mode != "websocket":
            return _SS_PLUGIN_UNUSABLE
        return {
            "name": "v2ray-plugin",
            "mode": "websocket",
            "host": _clean_sni(opts.get("host") or opts.get("obfs-host")) or "",
            "path": opts.get("path", ""),
            "tls": "tls" in flags or "tls" in opts,
        }
    return _SS_PLUGIN_UNUSABLE


def _ub64_text(s: Optional[str], *, allow_empty: bool = False) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return "" if allow_empty else None
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(s, validate=False).decode("utf-8")
    except Exception:
        return None


def _sanitize_ssr(cipher: str, password: str, obfs: str, protocol: str) -> Optional[tuple]:
    cipher = (cipher or "").strip().lower()
    if cipher not in SSR_CIPHERS:
        return None
    if not password:
        return None
    obfs = (obfs or "").strip().lower()
    if obfs not in SSR_OBFS:
        return None
    protocol = (protocol or "").strip().lower()
    if protocol not in SSR_PROTOCOLS:
        return None
    return cipher, password, obfs, protocol


def _b64_json(b64: str) -> Optional[dict]:
    try:
        b64 = b64.strip()
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        return json.loads(base64.b64decode(b64).decode("utf-8", errors="ignore"))
    except Exception:
        return None


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _remark_of(line: str) -> str:
    if "#" in line:
        frag = line.split("#", 1)[1]
        try:
            return urllib.parse.unquote(frag).strip()
        except Exception:
            return frag.strip()
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# ۳. ثبت آمار کانفیگ‌های حذف‌شده (Drop Telemetry)
# ──────────────────────────────────────────────────────────────────────────────

class _DropRecorder:
    def __init__(self) -> None:
        self.data: Dict[str, Dict[str, Any]] = {}

    def clear_target(self, target: str) -> None:
        self.data[target] = {"total": 0, "by_reason": {}, "by_protocol": {}}

    def record(
        self, target: str, reason: str, line: str, proto: Optional[str] = None
    ) -> None:
        d = self.data.setdefault(target, {"total": 0, "by_reason": {}, "by_protocol": {}})
        d["total"] += 1
        d["by_reason"][reason] = d["by_reason"].get(reason, 0) + 1
        key = proto or _scheme_of(line)
        if key:
            d["by_protocol"][key] = d["by_protocol"].get(key, 0) + 1

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            t: {
                "total": v["total"],
                "by_reason": dict(sorted(v["by_reason"].items())),
                "by_protocol": dict(sorted(v["by_protocol"].items(), key=lambda kv: (-kv[1], kv[0]))),
            }
            for t, v in sorted(self.data.items())
        }


_drops = _DropRecorder()


def _scheme_of(line: str) -> str:
    s = (line or "").strip()
    i = s.find("://")
    return s[:i].lower() if 0 < i < 20 else ""


def drop_stats() -> Dict[str, Dict[str, Any]]:
    return _drops.snapshot()


_TUIC_CONGESTION = frozenset({"cubic", "new_reno", "bbr"})
_ALPN_ALLOWED = frozenset({"h3", "h2", "http/1.1", "hysteria", "tuic", "quic"})
XHTTP_MODES: frozenset = frozenset({"auto", "packet-up", "stream-up", "stream-one"})

_SNI_SENTINELS = frozenset({
    "none", "null", "undefined", "nil", "nan", "false", "true",
    "localhost", "0.0.0.0", "127.0.0.1", "::1", "example.com",
})
_SNI_LABEL = re.compile(r"^(?!-)[A-Za-z0-9_-]{1,63}(?<!-)$")


def _is_unroutable_server(host: Any) -> bool:
    s = str(host or "").strip().strip("[]")
    if not s:
        return True
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return False
    return bool(
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_link_local
    )


def _is_structurally_invalid_server(host: Any) -> bool:
    s = str(host or "").strip()
    if not s:
        return True
    try:
        ipaddress.ip_address(s.strip("[]"))
        return False
    except ValueError:
        pass
    if any(ch in s for ch in ("/", "?", "#", "@", "\\")) or "://" in s:
        return True
    if any(ch.isspace() for ch in s) or ":" in s or "." not in s or len(s) > 253:
        return True
    labels = s.rstrip(".").split(".")
    return not all(_SNI_LABEL.match(x) for x in labels)


def _clean_sni(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    for _ in range(3):
        nxt = urllib.parse.unquote(s)
        if nxt == s:
            break
        s = nxt
    s = s.strip()
    s = re.sub(r":\d{1,5}$", "", s)
    s = s.strip("$").strip(".").strip()
    if not s or len(s) > 253 or s.lower() in _SNI_SENTINELS:
        return ""
    if any(ch in s for ch in ("://", "/", "?", "@", " ", ":")):
        return ""
    labels = s.split(".")
    if len(labels) < 2 or not all(_SNI_LABEL.match(lb) for lb in labels):
        return ""
    return s


def _truthy(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "on")


def _alpn_list(raw: Any) -> list:
    if not raw:
        return []
    out: list = []
    for part in str(raw).split(","):
        p = urllib.parse.unquote(part).strip().lower()
        if p in _ALPN_ALLOWED and p not in out:
            out.append(p)
    return out


VMESS_SECURITY: frozenset = frozenset({
    "auto", "none", "zero", "aes-128-cfb", "aes-128-gcm", "chacha20-poly1305",
})


def _sanitize_vmess_security(scy: Any) -> str:
    s = str(scy or "").strip().lower()
    return s if s in VMESS_SECURITY else "auto"


# ──────────────────────────────────────────────────────────────────────────────
# ۴. تجزیه یکپارچه پروتکل‌ها (Parse Proxy)
# ──────────────────────────────────────────────────────────────────────────────

def parse_proxy(line: str) -> Optional[Dict[str, Any]]:
    """پارس استاندارد پروتکل به ساختار دیکشنری واسط."""
    line = line.strip()
    try:
        if line.startswith("vmess://"):
            obj = _b64_json(line[8:].split("#")[0])
            if not obj:
                return None
            return {
                "type": "vmess",
                "name": (
                    _remark_of(line)
                    or str(obj.get("ps") or obj.get("name") or "")
                    or _branded_fallback("vmess")
                ),
                "server": str(obj.get("add") or ""),
                "port": _safe_int(obj.get("port")),
                "uuid": str(obj.get("id") or ""),
                "alterId": _safe_int(obj.get("aid"), 0),
                "cipher": _sanitize_vmess_security(obj.get("scy")),
                "network": (str(obj.get("net") or "tcp") or "tcp").lower(),
                "tls": str(obj.get("tls") or "").lower() in ("tls", "reality"),
                "sni": _clean_sni(obj.get("sni") or obj.get("host")),
                "host": _clean_sni(obj.get("host")),
                "path": str(obj.get("path") or ""),
                "servicename": str(obj.get("path") or "").lstrip("/"),
                "fp": str(obj.get("fp") or "").lower(),
                "reality": str(obj.get("tls") or "").lower() == "reality",
                "mode": str(obj.get("mode") or ""),
                "extra": str(obj.get("extra") or ""),
            }

        parsed = urllib.parse.urlparse(line.split("#")[0])
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        scheme = parsed.scheme.lower()
        name = _remark_of(line) or _branded_fallback(scheme)

        if scheme == "vless":
            return {
                "type": "vless",
                "name": name,
                "server": parsed.hostname or "",
                "port": _safe_int(parsed.port),
                "uuid": urllib.parse.unquote(parsed.username or ""),
                "network": (q.get("type") or "tcp").lower(),
                "tls": (q.get("security") or "").lower() in ("tls", "reality"),
                "reality": (q.get("security") or "").lower() == "reality",
                "sni": _clean_sni(q.get("sni") or q.get("host")),
                "host": _clean_sni(q.get("host")),
                "path": q.get("path") or "",
                "flow": q.get("flow") or "",
                "pbk": q.get("pbk") or "",
                "sid": q.get("sid") or "",
                "fp": q.get("fp") or "",
                "servicename": q.get("serviceName") or q.get("servicename") or "",
                "mode": q.get("mode") or "",
                "extra": q.get("extra") or "",
            }

        if scheme == "trojan":
            return {
                "type": "trojan",
                "name": name,
                "server": parsed.hostname or "",
                "port": _safe_int(parsed.port),
                "password": urllib.parse.unquote(parsed.username or ""),
                "network": (q.get("type") or "tcp").lower(),
                "sni": _clean_sni(q.get("sni") or q.get("host")),
                "host": _clean_sni(q.get("host")),
                "path": q.get("path") or "",
                "tls": True,
                "fp": q.get("fp") or "",
                "servicename": q.get("serviceName") or q.get("servicename") or "",
                "mode": q.get("mode") or "",
                "extra": q.get("extra") or "",
            }

        if scheme in ("ss", "shadowsocks"):
            rest = line[len(scheme) + 3:].split("#")[0]
            method = password = ""
            host = ""
            port = 0
            authority, _qsep, query = rest.partition("?")
            if "@" in authority:
                userinfo, hostpart = authority.rsplit("@", 1)
                hostpart = hostpart.split("/", 1)[0]
                userinfo = _ss_userinfo(userinfo)
                if ":" in userinfo:
                    method, password = userinfo.split(":", 1)
                h, _, p = hostpart.rpartition(":")
                host, port = h, (int(p) if p.isdigit() and p.isascii() else 0)
                if host.startswith("[") and host.endswith("]"):
                    host = host[1:-1]
            else:
                try:
                    dec = base64.urlsafe_b64decode(rest + "==").decode("utf-8", errors="ignore")
                    creds, _, hp = dec.rpartition("@")
                    if ":" in creds:
                        method, password = creds.split(":", 1)
                    h, _, p = hp.rpartition(":")
                    host, port = h, _safe_int(p)
                except Exception:
                    return None
            if not host or not port:
                return None
            ok = _sanitize_ss(method, password)
            if not ok:
                return None
            method, password = ok
            out = {
                "type": "shadowsocks",
                "name": name,
                "server": host,
                "port": port,
                "cipher": method,
                "password": password,
            }
            plugin = _ss_plugin(query)
            if plugin is _SS_PLUGIN_UNUSABLE:
                return None
            if plugin:
                out["plugin"] = plugin
            return out

        if scheme == "ssr":
            body = line[len("ssr://"):].split("#", 1)[0]
            raw = _ub64_text(body)
            if raw is None:
                return None
            main, _sep, qs = raw.partition("/?")
            parts = main.split(":")
            if len(parts) != 6:
                return None
            host, port_s, sproto, method, sobfs, pwd_b64 = parts
            port = _safe_int(port_s)
            password = _ub64_text(pwd_b64)
            if password is None or not host or not port:
                return None
            ok = _sanitize_ssr(method, password, sobfs, sproto)
            if not ok:
                return None
            method, password, sobfs, sproto = ok
            sq = {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}
            return {
                "type": "shadowsocksr",
                "name": name,
                "server": host,
                "port": port,
                "cipher": method,
                "password": password,
                "obfs": sobfs,
                "protocol": sproto,
                "obfs_param": _ub64_text(sq.get("obfsparam"), allow_empty=True) or "",
                "protocol_param": _ub64_text(sq.get("protoparam"), allow_empty=True) or "",
            }

        if scheme in ("hysteria2", "hy2"):
            if not parsed.hostname or not parsed.port:
                return None
            pwd = urllib.parse.unquote(parsed.username or "")
            if parsed.password:
                pwd = f"{pwd}:{urllib.parse.unquote(parsed.password)}" if pwd else urllib.parse.unquote(parsed.password)
            if not pwd:
                return None
            obfs = (q.get("obfs") or "").strip().lower()
            if obfs and obfs != "salamander":
                obfs = ""
            return {
                "type": "hysteria2",
                "name": name,
                "server": parsed.hostname,
                "port": _safe_int(parsed.port),
                "password": pwd,
                "sni": _clean_sni(q.get("sni") or q.get("peer")),
                "insecure": _truthy(
                    q.get("insecure") or q.get("allowInsecure") or q.get("allow_insecure")
                ),
                "obfs": obfs,
                "obfs_password": urllib.parse.unquote(
                    q.get("obfs-password") or q.get("obfs_password") or ""
                ),
                "alpn": _alpn_list(q.get("alpn")),
                "tls": True,
            }

        if scheme == "tuic":
            if not parsed.hostname or not parsed.port:
                return None
            uuid = urllib.parse.unquote(parsed.username or "")
            pwd = urllib.parse.unquote(parsed.password or "")
            if not uuid or not pwd:
                return None
            cc = (
                q.get("congestion_control")
                or q.get("congestion-control")
                or q.get("congestion")
                or "cubic"
            ).strip().lower()
            if cc not in _TUIC_CONGESTION:
                cc = "cubic"
            urm = (q.get("udp_relay_mode") or q.get("udp-relay-mode") or "native").strip().lower()
            if urm not in ("native", "quic"):
                urm = "native"
            return {
                "type": "tuic",
                "name": name,
                "server": parsed.hostname,
                "port": _safe_int(parsed.port),
                "uuid": uuid,
                "password": pwd,
                "congestion_control": cc,
                "udp_relay_mode": urm,
                "sni": _clean_sni(q.get("sni")),
                "insecure": _truthy(
                    q.get("allow_insecure") or q.get("insecure") or q.get("allowInsecure")
                ),
                "alpn": _alpn_list(q.get("alpn")),
                "tls": True,
            }
    except Exception:
        return None
    return None


# ──────────────────────────────────────────────────────────────────────────────
# ۵. نرمال‌سازی ترنسپورت و ترمیم مسیرها
# ──────────────────────────────────────────────────────────────────────────────

_CLASH_NETWORK_MAP: Dict[str, str] = {
    "tcp": "tcp", "raw": "tcp", "": "tcp", "none": "tcp",
    "ws": "ws", "websocket": "ws",
    "httpupgrade": "ws",
    "grpc": "grpc", "gun": "grpc",
    "xhttp": "xhttp", "splithttp": "xhttp",
    "h2": "h2", "http": "http",
    "kcp": "tcp", "mkcp": "tcp",
    "quic": "tcp",
}

_SINGBOX_TRANSPORTS: frozenset = frozenset({"ws", "grpc", "http", "httpupgrade", "quic"})
_BAD_PCT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _safe_transport_path(raw: Any) -> str:
    """ترمیم کاراکترهای درصد بدون هگز (مانند path=%) به %25 جهت جلوگیری از کرش کلاینت‌ها."""
    return _BAD_PCT_ESCAPE_RE.sub("%25", raw if isinstance(raw, str) else "")


def _sanitize_xhttp_mode(raw: Any) -> str:
    m = (raw or "").strip().lower() if isinstance(raw, str) else ""
    return m if m in XHTTP_MODES else ""


def _clash_network(raw: str) -> str:
    return _CLASH_NETWORK_MAP.get((raw or "").lower(), "tcp")


def _reality_params(p: Dict[str, Any]) -> Optional[tuple]:
    if not p.get("reality"):
        return None
    pbk = _sanitize_pbk(p.get("pbk", ""))
    if not pbk:
        return None
    sid = _sanitize_short_id(p.get("sid", ""))
    if sid is None:
        return None
    return pbk, sid


def _clash_transport_opts(p: Dict[str, Any], out: Dict[str, Any]) -> None:
    raw = (p.get("network") or "").lower()
    net = _clash_network(raw)
    host = p.get("host") or p.get("sni") or ""
    path = _safe_transport_path(p.get("path")) or "/"
    out["network"] = net

    if net == "ws":
        ws: Dict[str, Any] = {"path": path}
        if host:
            ws["headers"] = {"Host": host}
        if raw in ("httpupgrade",):
            ws["v2ray-http-upgrade"] = True
            ws["v2ray-http-upgrade-fast-open"] = True
        out["ws-opts"] = ws
    elif net == "grpc":
        svc = p.get("servicename") or (p.get("path") or "").lstrip("/")
        out["grpc-opts"] = {"grpc-service-name": svc}
    elif net == "xhttp":
        xh: Dict[str, Any] = {"path": path}
        if host:
            xh["host"] = host
        mode = _sanitize_xhttp_mode(p.get("mode"))
        if mode:
            xh["mode"] = mode
        if p.get("extra"):
            try:
                ex = json.loads(p["extra"])
                if isinstance(ex, dict):
                    if isinstance(ex.get("xPaddingBytes"), (str, int)):
                        xh["x-padding-bytes"] = str(ex["xPaddingBytes"])
                    if isinstance(ex.get("noGRPCHeader"), bool):
                        xh["no-grpc-header"] = ex["noGRPCHeader"]
            except Exception:
                pass
        out["xhttp-opts"] = xh
    elif net == "h2":
        h2: Dict[str, Any] = {"path": path}
        if host:
            h2["host"] = [host]
        out["h2-opts"] = h2
    elif net == "http":
        ho: Dict[str, Any] = {"path": [path]}
        if host:
            ho["headers"] = {"Host": [host]}
        out["http-opts"] = ho


# ──────────────────────────────────────────────────────────────────────────────
# ۶. تولید Clash / Mihomo YAML
# ──────────────────────────────────────────────────────────────────────────────

def _to_clash_proxy(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    t = p["type"]
    base = {"name": p["name"], "server": p["server"], "port": p["port"]}
    if not p["server"] or not p["port"]:
        return None
    try:
        if t == "vmess":
            out = {
                **base, "type": "vmess", "uuid": p["uuid"],
                "alterId": p.get("alterId", 0), "cipher": p.get("cipher", "auto"),
                "udp": True, "tls": p["tls"],
            }
            if p["sni"]:
                out["servername"] = p["sni"]
            _clash_transport_opts(p, out)
            return out
        if t == "vless":
            out = {**base, "type": "vless", "uuid": p["uuid"], "udp": True, "tls": p["tls"]}
            flow = _sanitize_flow(p.get("flow", ""))
            if flow:
                out["flow"] = flow
            if p["sni"]:
                out["servername"] = p["sni"]
            if p.get("reality"):
                rp = _reality_params(p)
                if rp is None:
                    return None
                out["reality-opts"] = {"public-key": rp[0], "short-id": rp[1]}
            fp = (p.get("fp") or "").lower()
            if fp in UTLS_FINGERPRINTS:
                out["client-fingerprint"] = fp
            elif p.get("reality"):
                out["client-fingerprint"] = DEFAULT_UTLS_FINGERPRINT
            _clash_transport_opts(p, out)
            return out
        if t == "trojan":
            out = {**base, "type": "trojan", "password": p["password"], "udp": True}
            if p["sni"]:
                out["sni"] = p["sni"]
            fp = (p.get("fp") or "").lower()
            if fp in UTLS_FINGERPRINTS:
                out["client-fingerprint"] = fp
            _clash_transport_opts(p, out)
            return out
        if t == "shadowsocks":
            out = {
                **base, "type": "ss", "cipher": p["cipher"],
                "password": p["password"], "udp": True,
            }
            pl = p.get("plugin")
            if pl:
                if pl["name"] == "obfs":
                    out["plugin"] = "obfs"
                    out["plugin-opts"] = {"mode": pl["mode"], "host": pl["host"]}
                else:
                    out["plugin"] = "v2ray-plugin"
                    out["plugin-opts"] = {
                        "mode": "websocket", "host": pl["host"],
                        "path": pl["path"], "tls": bool(pl["tls"]),
                    }
            return out
        if t == "shadowsocksr":
            # به دلیل عدم پشتیبانی در هسته تبدیل Hiddify و جلوگیری از سوختن کل فایل، در clash.yaml قرار نمی‌گیرد
            return None
        if t == "hysteria2":
            out = {**base, "type": "hysteria2", "password": p["password"]}
            if p.get("sni"):
                out["sni"] = p["sni"]
            if p.get("insecure"):
                out["skip-cert-verify"] = True
            if p.get("obfs"):
                out["obfs"] = p["obfs"]
                if p.get("obfs_password"):
                    out["obfs-password"] = p["obfs_password"]
                else:
                    out.pop("obfs")
            if p.get("alpn"):
                out["alpn"] = list(p["alpn"])
            return out
        if t == "tuic":
            out = {
                **base, "type": "tuic", "uuid": p["uuid"], "password": p["password"],
                "congestion-controller": p.get("congestion_control", "cubic"),
                "udp-relay-mode": p.get("udp_relay_mode", "native"),
            }
            if p.get("sni"):
                out["sni"] = p["sni"]
            if p.get("insecure"):
                out["skip-cert-verify"] = True
            out["alpn"] = list(p["alpn"]) if p.get("alpn") else ["h3"]
            return out
    except Exception:
        return None
    return None


OUTPUT_PROXY_LIMIT = 20000

_YAML12_AMBIGUOUS = re.compile(
    r"""^(?:
          [-+]?[0-9]+
        | 0[oO][0-7]+ | 0[xX][0-9a-fA-F]+
        | [-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?
        | [-+]?\.(?:inf|Inf|INF) | \.(?:nan|NaN|NAN)
        | true|True|TRUE|false|False|FALSE
        | null|Null|NULL|~
        )$""",
    re.VERBOSE,
)


def _yaml_str_representer(dumper, data):
    if data == "" or _YAML12_AMBIGUOUS.match(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _clash_dumper():
    import yaml

    base = getattr(yaml, "CSafeDumper", None) or yaml.SafeDumper

    class _SafeClashDumper(base):
        pass

    _SafeClashDumper.add_representer(str, _yaml_str_representer)
    return _SafeClashDumper


def build_clash_yaml(lines: List[str], limit: int = OUTPUT_PROXY_LIMIT) -> str:
    """تبدیل کانفیگ‌ها به فایل ساختاریافته Clash Meta YAML همراه با گروه‌های رسمی Goodbaye."""
    import yaml

    proxies: List[Dict[str, Any]] = []
    used_names: set = {GROUP_MAIN, GROUP_AUTO, GROUP_FALLBACK}
    _drops.clear_target("clash")

    for line in lines:
        if len(proxies) >= limit:
            _drops.record("clash", "over_limit", line)
            continue
        p = parse_proxy(line)
        if not p:
            _drops.record("clash", "unparsable", line)
            continue
        if _is_unroutable_server(p.get("server")):
            _drops.record("clash", "unroutable_server", line, p.get("type"))
            continue
        if _is_structurally_invalid_server(p.get("server")):
            _drops.record("clash", "invalid_server", line, p.get("type"))
            continue
        cp = _to_clash_proxy(p)
        if not cp:
            _drops.record("clash", "not_expressible", line, p.get("type"))
            continue

        nm = _enforce_brand(cp["name"], cp["type"])
        base_nm = nm
        i = 1
        while nm in used_names:
            nm = f"{base_nm} #{i}"
            i += 1
        cp["name"] = nm
        used_names.add(nm)
        proxies.append(cp)

    names = [p["name"] for p in proxies]
    doc = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": GROUP_MAIN,
                "type": "select",
                "proxies": [GROUP_AUTO, GROUP_FALLBACK] + names,
            },
            {
                "name": GROUP_AUTO,
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": names,
            },
            {
                "name": GROUP_FALLBACK,
                "type": "fallback",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": names,
            },
        ],
        "rules": [f"MATCH,{GROUP_MAIN}"],
    }
    header = f"# Clash subscription — generated by {BRAND} aggregator\n"
    return header + yaml.dump(
        doc,
        Dumper=_clash_dumper(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10 ** 6,
    )


# ──────────────────────────────────────────────────────────────────────────────
# ۷. تولید Sing-box JSON
# ──────────────────────────────────────────────────────────────────────────────

def _singbox_tls(p: Dict[str, Any]) -> Dict[str, Any]:
    tls: Dict[str, Any] = {"enabled": True, "server_name": p.get("sni") or p["server"]}
    rp = _reality_params(p)
    reality = rp is not None
    if reality:
        tls["reality"] = {"enabled": True, "public_key": rp[0], "short_id": rp[1]}
    fp = (p.get("fp") or "").lower()
    if fp not in UTLS_FINGERPRINTS:
        fp = DEFAULT_UTLS_FINGERPRINT if reality else ""
    if fp:
        tls["utls"] = {"enabled": True, "fingerprint": fp}
    if p.get("alpn"):
        tls["alpn"] = p["alpn"]
    return tls


def _singbox_transport(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = (p.get("network") or "").lower()
    host = p.get("host") or p.get("sni") or ""
    path = _safe_transport_path(p.get("path")) or "/"

    if raw in ("", "tcp", "raw", "none"):
        return None
    if raw in ("ws", "websocket"):
        tr: Dict[str, Any] = {"type": "ws", "path": path}
        if host:
            tr["headers"] = {"Host": host}
        return tr
    if raw == "httpupgrade":
        tr = {"type": "httpupgrade", "path": path}
        if host:
            tr["host"] = host
        return tr
    if raw in ("grpc", "gun"):
        svc = p.get("servicename") or (p.get("path") or "").lstrip("/")
        return {"type": "grpc", "service_name": svc}
    if raw in ("h2", "http"):
        tr = {"type": "http", "path": path}
        if host:
            tr["host"] = [host]
        return tr
    if raw == "quic":
        return {"type": "quic"}
    return False


def _to_singbox_outbound(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    t = p["type"]
    if t == "shadowsocksr" or not p["server"] or not p["port"]:
        return None

    try:
        transport = _singbox_transport(p)
        if transport is False:
            return None

        if t == "vmess":
            ob = {
                "type": "vmess", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "uuid": p["uuid"],
                "security": p.get("cipher", "auto"), "alter_id": p.get("alterId", 0),
            }
            if p["tls"]:
                ob["tls"] = _singbox_tls(p)
            if transport:
                ob["transport"] = transport
            return ob
        if t == "vless":
            if p.get("reality") and _reality_params(p) is None:
                return None
            ob = {
                "type": "vless", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "uuid": p["uuid"],
            }
            flow = _sanitize_flow(p.get("flow", ""))
            if flow:
                ob["flow"] = flow
            if p["tls"]:
                ob["tls"] = _singbox_tls(p)
            if transport:
                ob["transport"] = transport
            return ob
        if t == "trojan":
            ob = {
                "type": "trojan", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "password": p["password"],
                "tls": _singbox_tls(p),
            }
            if transport:
                ob["transport"] = transport
            return ob
        if t == "shadowsocks":
            ob = {
                "type": "shadowsocks", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "method": p["cipher"], "password": p["password"],
            }
            pl = p.get("plugin")
            if pl:
                if pl["name"] == "obfs":
                    opts = [f"obfs={_sip003_escape(pl['mode'])}"]
                    if pl["host"]:
                        opts.append(f"obfs-host={_sip003_escape(pl['host'])}")
                    ob["plugin"] = "obfs-local"
                else:
                    opts = ["mode=websocket"]
                    if pl["host"]:
                        opts.append(f"host={_sip003_escape(pl['host'])}")
                    if pl["path"]:
                        opts.append(f"path={_sip003_escape(pl['path'])}")
                    if pl["tls"]:
                        opts.append("tls")
                    ob["plugin"] = "v2ray-plugin"
                ob["plugin_opts"] = ";".join(opts)
            return ob
        if t == "hysteria2":
            ob = {
                "type": "hysteria2", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "password": p["password"],
                "tls": {
                    "enabled": True,
                    "server_name": p.get("sni") or p["server"],
                    "insecure": bool(p.get("insecure")),
                },
            }
            if p.get("alpn"):
                ob["tls"]["alpn"] = list(p["alpn"])
            if p.get("obfs") and p.get("obfs_password"):
                ob["obfs"] = {"type": p["obfs"], "password": p["obfs_password"]}
            return ob
        if t == "tuic":
            ob = {
                "type": "tuic", "tag": p["name"], "server": p["server"],
                "server_port": p["port"], "uuid": p["uuid"],
                "password": p["password"],
                "congestion_control": p.get("congestion_control", "cubic"),
                "udp_relay_mode": p.get("udp_relay_mode", "native"),
                "tls": {
                    "enabled": True,
                    "server_name": p.get("sni") or p["server"],
                    "insecure": bool(p.get("insecure")),
                    "alpn": list(p["alpn"]) if p.get("alpn") else ["h3"],
                },
            }
            return ob
    except Exception:
        return None
    return None


def build_singbox_json(lines: List[str], limit: int = OUTPUT_PROXY_LIMIT) -> str:
    """تبدیل کانفیگ‌ها به سند رسمی و سازگار Sing-box JSON."""
    outbounds: List[Dict[str, Any]] = []
    used_tags: set = {GROUP_MAIN, GROUP_AUTO}
    _drops.clear_target("singbox")

    for line in lines:
        if len(outbounds) >= limit:
            _drops.record("singbox", "over_limit", line)
            continue
        p = parse_proxy(line)
        if not p:
            _drops.record("singbox", "unparsable", line)
            continue
        if _is_unroutable_server(p.get("server")):
            _drops.record("singbox", "unroutable_server", line, p.get("type"))
            continue
        if _is_structurally_invalid_server(p.get("server")):
            _drops.record("singbox", "invalid_server", line, p.get("type"))
            continue
        ob = _to_singbox_outbound(p)
        if not ob:
            _drops.record("singbox", "not_expressible", line, p.get("type"))
            continue

        tag = _enforce_brand(ob["tag"], ob["type"])
        base_tag = tag
        i = 1
        while tag in used_tags:
            tag = f"{base_tag} #{i}"
            i += 1
        ob["tag"] = tag
        used_tags.add(tag)
        outbounds.append(ob)

    tags = [o["tag"] for o in outbounds]
    if not tags:
        return json.dumps(
            {"log": {"level": "info"}, "outbounds": [{"type": "direct", "tag": "direct"}]},
            ensure_ascii=False,
            indent=2,
        )

    doc = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "proxy-dns", "type": "https", "server": "1.1.1.1", "detour": GROUP_MAIN},
                {"tag": "local-dns", "type": "local"},
            ],
            "rules": [
                {"clash_mode": "Direct", "server": "local-dns"},
                {"clash_mode": "Global", "server": "proxy-dns"},
            ],
            "final": "proxy-dns",
            "strategy": "prefer_ipv4",
            "independent_cache": True,
        },
        "inbounds": [
            {
                "type": "tun", "tag": "tun-in",
                "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
                "auto_route": True, "strict_route": True, "stack": "mixed",
            },
            {
                "type": "mixed", "tag": "mixed-in",
                "listen": "127.0.0.1", "listen_port": 2080,
            },
        ],
        "outbounds": [
            {
                "type": "selector", "tag": GROUP_MAIN,
                "outbounds": [GROUP_AUTO] + tags, "default": GROUP_AUTO,
            },
            {
                "type": "urltest", "tag": GROUP_AUTO, "outbounds": tags,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "5m", "tolerance": 50,
            },
            *outbounds,
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": "direct"},
            ],
            "final": GROUP_MAIN,
            "auto_detect_interface": True,
            "default_domain_resolver": {"server": "local-dns"},
        },
        "experimental": {
            "cache_file": {"enabled": True, "store_fakeip": True},
            "clash_api": {"external_controller": "127.0.0.1:9090"},
        },
    }
    return json.dumps(doc, ensure_ascii=False, indent=2)
