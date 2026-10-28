#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/countries.py — تفکیکِ کانفیگ‌های تأییدشده بر پایهٔ کشور → Countries/<Name>.txt
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

اصلاحات:
  • سازگاری کامل با الگوی ۵ خطی ریمارک Goodbaye Universal Standard
  • استخراج دقیق نام و پرچم کشور بدون نیاز به پرس‌وجوی شبکه مضاعف
  • جاروی اتمیک پیش از نوشتن و ساخت فهرست Countries/index.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402
import geo  # noqa: E402


def _warn_env(name: str, raw: str, fallback: Any, why: str) -> None:
    print(f"⚠️ {name}={raw!r} {why}; falling back to {fallback!r}", file=sys.stderr, flush=True)


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        _warn_env(name, raw, default, "is not an integer")
        return default
    if value < minimum:
        _warn_env(name, raw, minimum, f"is below the minimum {minimum}")
        return minimum
    return value


def _float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        _warn_env(name, raw, default, "is not a number")
        return default
    if value != value or value in (float("inf"), float("-inf")):
        _warn_env(name, raw, default, "is not finite")
        return default
    if value < minimum:
        _warn_env(name, raw, minimum, f"is below the minimum {minimum}")
        return minimum
    return value


COUNTRIES_DIR = "Countries"
INDEX_NAME = "index.json"
GLOBAL_CODE = "Global"

NAME_SCAN_BUDGET = _float_env("COUNTRIES_NAME_BUDGET", 2.0, 0.1)
_CLOCK_EVERY = 20_000
MIN_PER_COUNTRY = _int_env("COUNTRIES_MIN", 1, 1)
MAX_SLUG_LEN = 96
_SAFE_SLUG_RE = re.compile(r"\A[A-Za-z0-9_]{1,%d}\Z" % MAX_SLUG_LEN)

CRITERION_LINES: Tuple[str, ...] = (
    "# source: verified/ — every config passed a real proxied request in ALL L3 rounds",
    "# location: GeoIP (DB-IP Country Lite) on the real network address of the server",
    "# note: this is where the SERVER is, not necessarily where your traffic exits",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def country_code_of(line: str) -> Optional[str]:
    """
    استخراج کد دوحرفی کشور از ریمارک ۵ خطی Goodbaye یا اطلاعات شبکه.
    """
    if not line:
        return None
    remark = core.remark_of(line)
    if not remark:
        return None

    # ۱. استخراج مستقیم بر اساس پرچم یا نام در ریمارک ۵ خطی
    code, _ = core.detect_country_from_remark(remark)
    if code and code != GLOBAL_CODE:
        return code

    # ۲. در صورت نامشخص بودن، استخراج از روی آدرس سرور با GeoIP
    host = core.endpoint_of(line)
    if host:
        c, _ = core.country_for_endpoint(host, remark)
        if c and c != GLOBAL_CODE:
            return c

    return GLOBAL_CODE if code == GLOBAL_CODE else None


def slug_for(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:MAX_SLUG_LEN]


def is_safe_slug(slug: str) -> bool:
    return bool(slug) and _SAFE_SLUG_RE.match(slug) is not None


def group_by_country(lines: Iterable[str]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for line in lines:
        s = (line or "").strip()
        if not s or s.startswith("#"):
            continue
        code = country_code_of(s)
        if not code or code == GLOBAL_CODE:
            continue
        groups.setdefault(code, []).append(s)
    return groups


def _host_of(line: str) -> str:
    endpoint = core.endpoint_of(line) or ""
    if not endpoint:
        return ""
    host = endpoint.rsplit(":", 1)[0] if ":" in endpoint else endpoint
    return host.strip().strip("[]")


def _targeted_names(groups: Dict[str, List[str]], reader: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for code, lines in groups.items():
        for line in lines:
            host = _host_of(line)
            if not host or not geo.is_ip_literal(host):
                continue
            try:
                record = reader.get(host)
            except Exception:
                continue
            country = (record or {}).get("country") or {}
            if country.get("iso_code") != code:
                continue
            name = (country.get("names") or {}).get("en")
            if name:
                out[code] = name
                break
    return out


def _scan_names(missing: Iterable[str], reader: Any,
                budget: float = NAME_SCAN_BUDGET) -> Dict[str, str]:
    need = {c for c in missing if c and c != GLOBAL_CODE}
    found: Dict[str, str] = {}
    if not need:
        return found
    started = time.time()
    steps = 0
    try:
        for _network, record in reader:
            steps += 1
            country = (record or {}).get("country") or {}
            iso = country.get("iso_code")
            if iso in need:
                name = (country.get("names") or {}).get("en")
                if name:
                    found[iso] = name
                need.discard(iso)
                if not need:
                    break
            if steps % _CLOCK_EVERY == 0 and (time.time() - started) > budget:
                log(f"  ⚠️ {COUNTRIES_DIR}: name scan hit budget ({budget}s)")
                break
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️ {COUNTRIES_DIR}: name scan error: {exc}")
    return found


def resolve_names(groups: Dict[str, List[str]]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    reader = None
    if geo and geo.database_available():
        try:
            reader = geo._get_reader()
        except Exception:
            reader = None

    if reader is not None:
        try:
            names.update(_targeted_names(groups, reader))
        except Exception:
            pass
        missing = [c for c in groups if c not in names]
        if missing:
            try:
                names.update(_scan_names(missing, reader))
            except Exception:
                pass

    for code in groups:
        if code not in names:
            # استفاده از نام کانونیکال پیش‌فرض اگر دیتابیس در دسترس نبود
            names[code] = core._CC_TO_NAME.get(code, code)
    return names


def header_for(name: str, code: str, count: int) -> str:
    label = (f"{name.upper().replace('_', ' ')} ({code})" if name != code else code)
    out = [core.hiddify_profile_header(label).rstrip("\n")]
    out.append(f"# {core.BRAND_CHANNEL} — {label} — {count} configs")
    out.extend(CRITERION_LINES)
    return "\n".join(out) + "\n"


def _remove_if_exists(path: str) -> bool:
    if os.path.lexists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            pass
    return False


def _sweep(base: str, keep: Iterable[str]) -> List[str]:
    if not os.path.isdir(base):
        return []
    keep_set = set(keep)
    pruned: List[str] = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return []
    for entry in entries:
        if entry.endswith(".tmp"):
            pass
        elif entry.endswith(".txt") and entry not in keep_set:
            pass
        else:
            continue
        target = os.path.join(base, entry)
        if (os.path.islink(target) or os.path.isfile(target)) and _remove_if_exists(target):
            pruned.append(entry)
    return pruned


def _write_text(path: str, content: str) -> None:
    core.assert_no_control_bytes(path, content)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o666)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            if os.path.lexists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def write_countries(out_dir: str, lines: Sequence[str]) -> Dict[str, Any]:
    base = os.path.join(out_dir, COUNTRIES_DIR)
    started = time.time()
    lines = list(lines or [])

    groups = group_by_country(lines)
    skipped = {c: len(v) for c, v in groups.items() if len(v) < MIN_PER_COUNTRY}
    for code in skipped:
        groups.pop(code, None)

    names = resolve_names(groups) if groups else {}

    plan: Dict[str, Tuple[str, str]] = {}
    used: Dict[str, str] = {}
    for code in sorted(groups):
        slug = slug_for(names.get(code, code))
        if not is_safe_slug(slug):
            slug = code if is_safe_slug(code) else ""
        if not slug:
            continue
        filename = f"{slug}.txt"
        if filename in used:
            slug = f"{slug}_{code}"
            filename = f"{slug}.txt"
        if filename in used or not is_safe_slug(slug):
            continue
        used[filename] = code
        plan[code] = (filename, slug)

    pruned = _sweep(base, keep=set(used))
    if pruned:
        log(f"  🗑️ {COUNTRIES_DIR}: pruned {len(pruned)} stale file(s)")

    written: Dict[str, Dict[str, Any]] = {}
    failed: Dict[str, str] = {}
    for code in sorted(plan):
        filename, slug = plan[code]
        group = groups[code]
        path = os.path.join(base, filename)
        try:
            body = core.shield_unsupported_runs(group)
            content = header_for(slug, code, len(group)) + "\n".join(body) + "\n"
            _write_text(path, content)
        except Exception as exc:
            _remove_if_exists(path)
            failed[code] = str(exc)
            continue
        written[code] = {
            "file": f"{COUNTRIES_DIR}/{filename}",
            "name": slug.replace("_", " "),
            "code": code,
            "flag": geo.flag_of(code) if geo else "🌐",
            "count": len(group),
        }

    stats: Dict[str, Any] = {
        "countries": len(written),
        "configs": sum(v["count"] for v in written.values()),
        "input": len([ln for ln in lines if (ln or "").strip()]),
        "pruned": pruned,
        "skipped_small": skipped,
        "failed": failed,
        "named_from_db": sum(1 for c in written if names.get(c) != c),
        "min_per_country": MIN_PER_COUNTRY,
        "seconds": round(time.time() - started, 3),
    }

    if written:
        index = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "verified",
            "criterion": "passed a real proxied request in ALL L3 rounds",
            "brand": core.BRAND_CHANNEL,
            "countries": [written[c] for c in sorted(written, key=lambda c: (-written[c]["count"], c))],
            "stats": {k: stats[k] for k in ("countries", "configs", "min_per_country")},
        }
        try:
            _write_text(os.path.join(base, INDEX_NAME), json.dumps(index, ensure_ascii=False, indent=2) + "\n")
            stats["index"] = f"{COUNTRIES_DIR}/{INDEX_NAME}"
        except Exception as exc:
            log(f"  ⚠️ {COUNTRIES_DIR}/{INDEX_NAME}: {exc}")
    else:
        if _remove_if_exists(os.path.join(base, INDEX_NAME)):
            log(f"  🗑️ {COUNTRIES_DIR}: pruned stale {INDEX_NAME}")

    stats["files"] = {c: written[c]["file"] for c in written}
    log(f"  🌍 {COUNTRIES_DIR}: {stats['countries']} countries · {stats['configs']} configs")
    return stats
