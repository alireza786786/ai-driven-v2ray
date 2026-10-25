#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/aggregate.py — خط‌لوله اصلی تجمیع و استانداردسازی کانفیگ‌های Goodbaye Universal Standard.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

وظایف و ویژگی‌ها:
  ۱) واکشی هم‌روند منابع با retry و backoff هوشمند
  ۲) تصفیه ساختاری و اعمال ریمارک ۵ خطی رسمی منشور بر روی دسته‌های ALL / HEAVY / LIGHT
  ۳) استخراج فرمت‌های Clash Meta YAML، Singbox JSON و سابسکریپشن‌های Base64
  ۴) ادغام حافظه تاریخی state.py و گزارش سلامت منابع در health.json
  ۵) تولید index.json ماشین‌خوان برای وب‌پنل گیت‌هاب پیجز (https://alireza786786.github.io/ai-driven-v2ray/)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402
import converters  # noqa: E402
import mihomo_compat  # noqa: E402
import state as memory  # noqa: E402
from sources import LIGHT_SOURCES, HEAVY_SOURCES  # noqa: E402

try:
    import geo  # noqa: E402
except Exception:  # pragma: no cover
    geo = None  # type: ignore

# ──────────────────────────────────────────────────────────────────────────────
# متغیرهای هویتی گیت‌هاب و وب‌پنل پیجز (منطبق بر اصل اول منشور)
# ──────────────────────────────────────────────────────────────────────────────
GH_USER = os.environ.get("AGG_GH_USER", "alireza786786")
GH_REPO = os.environ.get("AGG_GH_REPO", "ai-driven-v2ray")

GH_BRANCH = (
    os.environ.get("AGG_PUBLISH_BRANCH")
    or os.environ.get("PUBLISH_BRANCH")
    or os.environ.get("AGG_DATA_BRANCH")
    or os.environ.get("DATA_BRANCH")
    or "main"
)

RAW_BASE = f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/{GH_BRANCH}"
CDN_BASE = f"https://cdn.jsdelivr.net/gh/{GH_USER}/{GH_REPO}@{GH_BRANCH}"
PRIMARY_BASE = RAW_BASE
MIRROR_BASE = CDN_BASE

USER_AGENTS = (
    "v2rayNG/1.8.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "ClashforWindows/0.20.39",
)

FETCH_TIMEOUT = int(os.getenv("AGG_FETCH_TIMEOUT", "15"))
MAX_WORKERS = int(os.getenv("AGG_MAX_WORKERS", "16"))
FETCH_RETRIES = int(os.getenv("AGG_FETCH_RETRIES", "3"))
RETRY_BACKOFF = 1.5
UPDATE_INTERVAL_MIN = int(os.getenv("AGG_UPDATE_INTERVAL_MIN", "15"))

SOURCE_HEALTH: Dict[str, dict] = {}


def log(msg: str) -> None:
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# واکشی منابع با گارد ضد کرش
# ──────────────────────────────────────────────────────────────────────────────

def fetch_source(url: str) -> Tuple[str, List[str]]:
    """واکشی یک سورس با retry و ثبت تلمتری در SOURCE_HEALTH."""
    name = url.rsplit("/", 1)[-1] or url
    last_err = ""
    last_code = 0
    t_start = time.time()
    tries = max(1, FETCH_RETRIES)

    for attempt in range(1, tries + 1):
        ua = USER_AGENTS[(attempt - 1) % len(USER_AGENTS)]
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": ua})
            last_code = resp.status_code
            body = resp.text.strip() if resp.text else ""
            if resp.status_code == 200 and body:
                cfgs = core.extract_valid_lines(body)
                if cfgs:
                    SOURCE_HEALTH[url] = {
                        "name": name,
                        "status": "ok",
                        "count": len(cfgs),
                        "http_code": resp.status_code,
                        "attempts": attempt,
                        "latency_ms": int((time.time() - t_start) * 1000),
                    }
                    return url, cfgs
                last_err = "200 but 0 valid configs"
            else:
                last_err = f"HTTP {resp.status_code}" if resp.status_code != 200 else "empty body"
                if resp.status_code in (400, 401, 403, 404, 410, 451):
                    break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        if attempt < tries:
            time.sleep(RETRY_BACKOFF * attempt)

    SOURCE_HEALTH[url] = {
        "name": name,
        "status": "empty" if "0 valid" in last_err else "fail",
        "count": 0,
        "http_code": last_code,
        "attempts": attempt,
        "latency_ms": int((time.time() - t_start) * 1000),
        "error": last_err,
    }
    log(f"  ⚠️ fetch fail {name}: {last_err} (after {attempt} tries)")
    return url, []


def fetch_all(urls: List[str]) -> Dict[str, List[str]]:
    """واکشی همروند تمامی URLها."""
    results: Dict[str, List[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as ex:
        futs = {ex.submit(fetch_source, u): u for u in urls}
        for fut in as_completed(futs):
            url, cfgs = fut.result()
            results[url] = cfgs
            log(f"  ✓ {len(cfgs):>5} configs ← {url.rsplit('/', 1)[-1]}")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# پردازش دسته‌ها (یکتاسازی، سپرهای هیدیفای و برندینگ ۵ خطی)
# ──────────────────────────────────────────────────────────────────────────────

class CategoryResult:
    def __init__(self) -> None:
        self.unique: List[str] = []
        self.broken: List[str] = []
        self.duplicates: List[str] = []
        self.total_seen = 0
        self.active_sources = 0
        self.protocol_counts: Dict[str, int] = {}
        self.unbranded_dropped = 0
        self.unbranded_rebranded = 0
        self.unbranded_samples: List[str] = []
        self.mihomo_fatal: Dict[str, int] = {}
        self.mihomo_fatal_samples: List[str] = []


def _note_mihomo_fatal(r: CategoryResult, line: str) -> bool:
    why = mihomo_compat.fatal_reason(line)
    if not why:
        return False
    r.mihomo_fatal[why] = r.mihomo_fatal.get(why, 0) + 1
    if len(r.mihomo_fatal_samples) < 3:
        r.mihomo_fatal_samples.append(line[:160])
    return True


def process_category(
    per_source: Dict[str, List[str]],
    source_urls: List[str],
    _cache: Optional[Dict[str, Tuple[bool, str]]] = None,
) -> CategoryResult:
    """یکتاسازی و اعمال برندینگ رسمی منشور Goodbaye بر روی نودها."""
    if _cache is None:
        _cache = {}
    r = CategoryResult()
    seen_cores: set = set()
    raw_unique: List[str] = []

    for url in source_urls:
        cfgs = per_source.get(url, [])
        if not cfgs:
            continue
        r.active_sources += 1
        for line in cfgs:
            r.total_seen += 1
            cached = _cache.get(line)
            if cached is None:
                cached = (core.is_dummy_config(line), "")
                if not cached[0]:
                    cached = (False, core.dedup_key(line))
                _cache[line] = cached
            is_dummy, key = cached
            if is_dummy:
                r.broken.append(line)
                continue
            if _note_mihomo_fatal(r, line):
                continue
            if key not in seen_cores:
                seen_cores.add(key)
                raw_unique.append(line)
            else:
                r.duplicates.append(line)

    ordered = sorted(raw_unique, key=lambda ln: (core.dedup_key(ln) or ln))

    if geo is not None:
        try:
            hosts = [core.endpoint_of(ln) for ln in ordered if core.endpoint_of(ln)]
            geo.warm_up(hosts)
        except Exception as e:
            log(f"  ⚠️ geo warm-up skipped: {e}")

    for idx, line in enumerate(ordered, start=1):
        branded = core.brand_remark(line, idx)

        # گارد ناوردای برند Goodbaye
        if not core.is_branded(branded):
            retry = core.brand_remark(branded, idx)
            if core.is_branded(retry):
                branded = retry
                r.unbranded_rebranded += 1
            else:
                r.unbranded_dropped += 1
                if len(r.unbranded_samples) < 3:
                    r.unbranded_samples.append(branded[:160])
                continue

        r.unique.append(branded)
        proto = core.protocol_of(branded)
        if proto:
            r.protocol_counts[proto] = r.protocol_counts.get(proto, 0) + 1
    return r


# ──────────────────────────────────────────────────────────────────────────────
# نگارش اتمیک و مدیریت خروجی‌ها
# ──────────────────────────────────────────────────────────────────────────────

def _write_text(path: str, content: str) -> None:
    core.assert_no_control_bytes(path, content)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


CONVERT_FAILURES: Dict[str, str] = {}


def write_category(out_dir: str, cat: str, r: CategoryResult) -> None:
    """نگارش پکیج‌های دسته‌ای (configs.txt, configs_base64.txt, clash.yaml, singbox.json)."""
    base = os.path.join(out_dir, cat)
    hh = core.hiddify_profile_header(cat.upper())
    header = hh + f"# {core.BRAND_CHANNEL} — {cat.upper()} VIP — {len(r.unique)} unique configs\n"
    _write_text(
        os.path.join(base, "configs.txt"),
        header + "\n".join(core.shield_unsupported_runs(r.unique)) + "\n",
    )
    _write_text(
        os.path.join(base, "configs_base64.txt"),
        core.encode_base64_subscription(r.unique, header=hh),
    )
    try:
        _write_text(
            os.path.join(base, "clash.yaml"),
            hh + converters.build_clash_yaml(r.unique),
        )
        CONVERT_FAILURES.pop(f"{cat}/clash", None)
    except Exception as e:
        log(f"  ⚠️ clash {cat}: {e}")
        CONVERT_FAILURES[f"{cat}/clash"] = f"{type(e).__name__}: {e}"[:200]
        if _remove_if_exists(os.path.join(base, "clash.yaml")):
            log(f"  🗑️ pruned stale {cat}/clash.yaml")

    try:
        _write_text(
            os.path.join(base, "singbox.json"),
            converters.build_singbox_json(r.unique),
        )
        CONVERT_FAILURES.pop(f"{cat}/singbox", None)
    except Exception as e:
        log(f"  ⚠️ singbox {cat}: {e}")
        CONVERT_FAILURES[f"{cat}/singbox"] = f"{type(e).__name__}: {e}"[:200]
        if _remove_if_exists(os.path.join(base, "singbox.json")):
            log(f"  🗑️ pruned stale {cat}/singbox.json")


def _remove_if_exists(path: str) -> bool:
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError as e:
            log(f"  ⚠️ could not remove {path}: {e}")
    return False


def write_archive(out_dir: str, cat: str, r: CategoryResult) -> None:
    """بایگانی نودهای خراب در archive/ بدون نگارش تکراری‌ها برای جلوگیری از باد کردن گیت."""
    base = os.path.join(out_dir, "archive")
    btxt = os.path.join(base, f"{cat}_broken.txt")
    bb64 = os.path.join(base, f"{cat}_broken_base64.txt")
    if r.broken:
        bh = f"# {core.BRAND_CHANNEL} — {cat.upper()} BROKEN — {len(r.broken)} configs\n"
        _write_text(btxt, bh + "\n".join(core.shield_unsupported_runs(r.broken)) + "\n")
        _write_text(bb64, core.encode_base64_subscription(r.broken))
    else:
        _remove_if_exists(btxt)
        _remove_if_exists(bb64)

    for stale in (f"{cat}_duplicates.txt", f"{cat}_duplicates_base64.txt"):
        _remove_if_exists(os.path.join(base, stale))


def write_protocols(out_dir: str, all_unique: List[str]) -> Dict[str, int]:
    """تفکیک فایل‌های هر پروتکل در پوشه protocols/ با حذف فایل‌های خالی."""
    base = os.path.join(out_dir, "protocols")
    buckets: Dict[str, List[str]] = {}
    for line in all_unique:
        proto = core.protocol_of(line)
        if proto:
            buckets.setdefault(proto, []).append(line)

    counts: Dict[str, int] = {}
    written = 0
    pruned = 0

    def emit(proto: str, lines: List[str]) -> None:
        nonlocal written, pruned
        txt = os.path.join(base, f"{proto}.txt")
        b64 = os.path.join(base, f"{proto}_base64.txt")
        if lines:
            hh = core.hiddify_profile_header(proto.upper())
            h = hh + f"# {core.BRAND_CHANNEL} — {proto.upper()} VIP — {len(lines)} configs\n"
            _write_text(txt, h + "\n".join(core.shield_unsupported_runs(lines)) + "\n")
            _write_text(b64, core.encode_base64_subscription(lines, header=hh))
            written += 1
        else:
            gone_txt = _remove_if_exists(txt)
            gone_b64 = _remove_if_exists(b64)
            if gone_txt or gone_b64:
                pruned += 1

    for proto in core.PROTOCOL_ORDER:
        lines = buckets.get(proto, [])
        counts[proto] = len(lines)
        emit(proto, lines)

    for proto, lines in sorted(buckets.items(), key=lambda x: -len(x[1])):
        if proto not in counts:
            counts[proto] = len(lines)
            emit(proto, lines)

    log(f"  📁 protocols: {written} file-pairs written, {pruned} empty pruned")
    return counts


def build_index(
    results: Dict[str, CategoryResult],
    proto_counts: Dict[str, int],
    elapsed: float,
    out_dir: Optional[str] = None,
) -> dict:
    """تولید سند index.json با رعایت کامل آدرس‌های وب‌پنل منشور Goodbaye."""
    now = _dt.datetime.now(_dt.timezone.utc)
    next_run = now + _dt.timedelta(minutes=UPDATE_INTERVAL_MIN)

    def _published(*parts: str) -> bool:
        if out_dir is None:
            return True
        return os.path.exists(os.path.join(out_dir, *parts))

    def cat_block(cat: str, r: CategoryResult) -> dict:
        _pairs = (
            ("configs.txt", "configs_txt"),
            ("configs_base64.txt", "configs_base64"),
            ("clash.yaml", "clash_yaml"),
            ("singbox.json", "singbox_json"),
        )
        _live = [(f, k) for f, k in _pairs if _published(cat, f)]
        files: Dict[str, str] = {}
        for fname, key in _live:
            files[key] = f"{PRIMARY_BASE}/{cat}/{fname}"
        for fname, key in _live:
            files[f"{key}_mirror"] = f"{MIRROR_BASE}/{cat}/{fname}"
        return {
            "unique": len(r.unique),
            "broken": len(r.broken),
            "duplicates": len(r.duplicates),
            "total_fetched": r.total_seen,
            "active_sources": r.active_sources,
            "protocols": dict(sorted(r.protocol_counts.items(), key=lambda x: -x[1])),
            "files": files,
        }

    return {
        "brand": core.BRAND_CHANNEL,
        "vip_channel": core.VIP_CHANNEL,
        "generator": "Goodbaye Universal Standard aggregator",
        "updated_at": now.isoformat(),
        "updated_at_unix": int(now.timestamp()),
        "next_update_eta": next_run.isoformat(),
        "update_interval_minutes": UPDATE_INTERVAL_MIN,
        "elapsed_seconds": round(elapsed, 1),
        "raw_base": RAW_BASE,
        "cdn_base": CDN_BASE,
        "primary_base": PRIMARY_BASE,
        "mirror_base": MIRROR_BASE,
        "pages_webpanel": BASE_PAGES_URL,
        "publish_branch": GH_BRANCH,
        "data_branch": GH_BRANCH,
        "self_url": f"{PRIMARY_BASE}/index.json",
        "self_url_mirror": f"{MIRROR_BASE}/index.json",
        "link_policy": {
            "primary": "raw.githubusercontent.com",
            "primary_cache_seconds": 300,
            "mirror": "cdn.jsdelivr.net",
            "mirror_cache_seconds": 43200,
            "note": "raw link is 144x fresher. jsDelivr is mirror.",
        },
        "categories": {
            "all": cat_block("all", results["all"]),
            "heavy": cat_block("heavy", results["heavy"]),
            "light": cat_block("light", results["light"]),
        },
        "protocols": dict(sorted(proto_counts.items(), key=lambda x: -x[1])),
        "protocol_files": {
            p: f"{PRIMARY_BASE}/protocols/{p}.txt"
            for p in core.PROTOCOL_ORDER
            if proto_counts.get(p, 0) > 0 and _published("protocols", f"{p}.txt")
        },
        "protocol_files_base64": {
            p: f"{PRIMARY_BASE}/protocols/{p}_base64.txt"
            for p in core.PROTOCOL_ORDER
            if proto_counts.get(p, 0) > 0 and _published("protocols", f"{p}_base64.txt")
        },
        "protocol_files_mirror": {
            p: f"{MIRROR_BASE}/protocols/{p}.txt"
            for p in core.PROTOCOL_ORDER
            if proto_counts.get(p, 0) > 0 and _published("protocols", f"{p}.txt")
        },
        "archive": {
            **{
                f"{cat}_broken": f"{PRIMARY_BASE}/archive/{cat}_broken.txt"
                for cat in ("all", "heavy", "light")
                if results[cat].broken and _published("archive", f"{cat}_broken.txt")
            },
            **{
                f"{cat}_broken_base64": f"{PRIMARY_BASE}/archive/{cat}_broken_base64.txt"
                for cat in ("all", "heavy", "light")
                if results[cat].broken and _published("archive", f"{cat}_broken_base64.txt")
            },
        },
        "sources": {
            "light_count": len(LIGHT_SOURCES),
            "heavy_count": len(HEAVY_SOURCES),
            "total_count": len(LIGHT_SOURCES) + len(HEAVY_SOURCES),
            "healthy": sum(1 for h in SOURCE_HEALTH.values() if h.get("status") == "ok"),
            "unhealthy": sum(1 for h in SOURCE_HEALTH.values() if h.get("status") != "ok"),
            "health_url": f"{PRIMARY_BASE}/health.json",
            "health_url_mirror": f"{MIRROR_BASE}/health.json",
        },
    }


def disabled_reasons_for(mem: Dict, skipped: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    wanted = set(skipped)
    entries = mem.get("sources") if isinstance(mem, dict) else None
    for ent in (entries or {}).values():
        if not isinstance(ent, dict):
            continue
        url = ent.get("url")
        if isinstance(url, str) and url in wanted:
            out[url] = str(ent.get("reason") or "disabled by memory")
    return out


def build_health_report(
    elapsed: float,
    conv_by_category: Optional[Dict[str, dict]] = None,
    results: Optional[Dict[str, CategoryResult]] = None,
    disabled: Optional[Dict[str, str]] = None,
) -> dict:
    now = _dt.datetime.now(_dt.timezone.utc)
    disabled_map = dict(disabled or {})
    items = []
    for url in (LIGHT_SOURCES + HEAVY_SOURCES):
        fallback: dict = {"name": url.rsplit("/", 1)[-1], "count": 0}
        if url in disabled_map:
            fallback["status"] = "disabled"
            fallback["reason"] = disabled_map[url]
        else:
            fallback["status"] = "unknown"
        h = SOURCE_HEALTH.get(url, fallback)
        tier = "light" if url in LIGHT_SOURCES else "heavy"
        items.append({"url": url, "tier": tier, **h})

    conv_by_cat = dict(conv_by_category or {})
    try:
        conv_stats = conv_by_cat.get("all") or converters.drop_stats()
    except Exception:
        conv_stats = None

    brand_gate = None
    if results:
        brand_gate = {
            cat: {
                "dropped": r.unbranded_dropped,
                "rebranded": r.unbranded_rebranded,
                "samples": list(r.unbranded_samples),
            }
            for cat, r in results.items()
        }

    geo_stats = None
    if geo is not None:
        try:
            geo_stats = geo.stats()
        except Exception:
            geo_stats = None

    converter_gate = dict(CONVERT_FAILURES)

    return {
        "brand": core.BRAND_CHANNEL,
        "vip_channel": core.VIP_CHANNEL,
        "checked_at": now.isoformat(),
        "checked_at_unix": int(now.timestamp()),
        "elapsed_seconds": round(elapsed, 1),
        "summary": {
            "total": len(items),
            "ok": sum(1 for i in items if i.get("status") == "ok"),
            "empty": sum(1 for i in items if i.get("status") == "empty"),
            "fail": sum(1 for i in items if i.get("status") == "fail"),
            "disabled": sum(1 for i in items if i.get("status") == "disabled"),
            "unknown": sum(1 for i in items if i.get("status") == "unknown"),
        },
        "sources": items,
        "converters": conv_stats,
        "converters_by_category": conv_by_cat or None,
        "brand_gate": brand_gate,
        "mihomo_gate": (
            {
                cat: {
                    "dropped": sum(getattr(r, "mihomo_fatal", {}).values()),
                    "by_reason": dict(sorted(getattr(r, "mihomo_fatal", {}).items())),
                    "samples": list(getattr(r, "mihomo_fatal_samples", [])),
                }
                for cat, r in results.items()
            }
            if results
            else None
        ),
        "converter_gate": converter_gate,
        "geo": geo_stats,
    }


def source_keys(per_source: Dict[str, List[str]]) -> Dict[str, set]:
    keys: Dict[str, set] = {}
    for url, cfgs in per_source.items():
        ks = set()
        for line in cfgs:
            try:
                if not core.is_dummy_config(line):
                    ks.add(core.dedup_key(line))
            except Exception:
                continue
        keys[url] = ks
    return keys


def unique_yield(per_source: Dict[str, List[str]]) -> Tuple[Dict[str, int], Dict[str, int], int]:
    keys = source_keys(per_source)
    owners: Dict[str, int] = {}
    for ks in keys.values():
        for k in ks:
            owners[k] = owners.get(k, 0) + 1
    totals = {u: len(ks) for u, ks in keys.items()}
    uniq = {u: sum(1 for k in ks if owners.get(k) == 1) for u, ks in keys.items()}
    return totals, uniq, len(owners)


def advance_memory(
    state: dict,
    per_source: Dict[str, List[str]],
    live_urls: List[str],
    state_path: str,
) -> dict:
    try:
        totals, uniq, union = unique_yield(per_source)
        obs = {
            u: {
                "tier": "light" if u in LIGHT_SOURCES else "heavy",
                "total": totals.get(u, 0),
                "unique": uniq.get(u, 0),
            }
            for u in per_source
        }
        state = memory.record_round(state, obs, live_urls)
        cand = memory.disable_candidates(
            state, uniq, union, keys_by_url=source_keys(per_source)
        )
        if cand:
            state = memory.mark_disabled(state, cand)
            for url, why in cand.items():
                log(f"  🚫 auto-disabling {url.rsplit('/', 1)[-1]} — {why}")
        memory.save_state(state, state_path)

        top = sorted(uniq.items(), key=lambda kv: -kv[1])[:3]
        zero = [u.rsplit("/", 1)[-1] for u, n in uniq.items() if n == 0]
        log(memory.summary(state))
        log(
            f"  📊 union={union} · top unique: "
            + ", ".join(f"{u.rsplit('/', 1)[-1]}={n}" for u, n in top)
        )
        if zero:
            log(f"  ⚠️ zero unique yield this round ({len(zero)}): {', '.join(zero)}")
    except Exception as exc:  # noqa: BLE001
        log(f"  ⚠️ memory step failed ({type(exc).__name__}) — round continues")
    return state


# ──────────────────────────────────────────────────────────────────────────────
# نقطه ورود اصلی خط‌لوله تجمیع
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Goodbaye Universal Standard Config Aggregator")
    ap.add_argument("--out", default=os.getcwd(), help="Output directory (repo root)")
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    log(f"🚀 Goodbaye Aggregator start → out={out_dir}")
    log(f"📡 Fetching {len(LIGHT_SOURCES)} light + {len(HEAVY_SOURCES)} heavy sources …")

    state_path = os.path.join(out_dir, memory.STATE_PATH)
    mem = memory.load_state(state_path)
    skipped = [u for u in memory.disabled_urls(mem) if u in (LIGHT_SOURCES + HEAVY_SOURCES)]
    disabled_reasons = disabled_reasons_for(mem, skipped)

    all_urls = [u for u in (LIGHT_SOURCES + HEAVY_SOURCES) if u not in set(skipped)]
    if skipped:
        log(
            f"🧠 memory disabled {len(skipped)} source(s) → fetching "
            f"{len(all_urls)} of {len(LIGHT_SOURCES) + len(HEAVY_SOURCES)}"
        )
        for u in skipped:
            log(f"     ⏭️ {u.rsplit('/', 1)[-1]}")
    per_source = fetch_all(all_urls)

    log("🧮 Processing categories (dedup + Goodbaye 5-line remark) …")
    analysis_cache: Dict[str, Tuple[bool, str]] = {}
    res_all = process_category(per_source, all_urls, analysis_cache)
    res_heavy = process_category(per_source, HEAVY_SOURCES, analysis_cache)
    res_light = process_category(per_source, LIGHT_SOURCES, analysis_cache)
    results = {"all": res_all, "heavy": res_heavy, "light": res_light}

    for cat, r in results.items():
        log(
            f"  • {cat:<5}: {len(r.unique):>6} unique | "
            f"{len(r.duplicates):>6} dup | {len(r.broken):>5} broken | "
            f"{r.active_sources}/{len(HEAVY_SOURCES if cat=='heavy' else LIGHT_SOURCES if cat=='light' else all_urls)} src"
        )

    if not res_all.unique:
        log("❌ No configs produced — aborting BEFORE writing (existing files preserved)")
        return 2

    mem = advance_memory(mem, per_source, LIGHT_SOURCES + HEAVY_SOURCES, state_path)

    log("💾 Writing output files …")
    conv_by_cat: Dict[str, dict] = {}
    for cat, r in results.items():
        write_category(out_dir, cat, r)
        try:
            conv_by_cat[cat] = converters.drop_stats()
        except Exception:
            pass
        write_archive(out_dir, cat, r)

    for cat, r in results.items():
        if r.unbranded_dropped or r.unbranded_rebranded:
            log(
                f"  ⚠️ brand gate [{cat}]: dropped={r.unbranded_dropped} "
                f"rebranded={r.unbranded_rebranded}"
            )
            for s in r.unbranded_samples:
                log(f"       ↳ {s}")
    for cat, r in results.items():
        if r.mihomo_fatal:
            log(
                f"  🛡️ mihomo gate [{cat}]: dropped {sum(r.mihomo_fatal.values())} "
                f"line(s) — {r.mihomo_fatal}"
            )

    proto_counts = write_protocols(out_dir, res_all.unique)
    log("  • protocols: " + ", ".join(f"{k}={v}" for k, v in proto_counts.items() if v))

    elapsed = time.time() - t0
    index = build_index(results, proto_counts, elapsed, out_dir)
    _write_text(os.path.join(out_dir, "index.json"), json.dumps(index, ensure_ascii=False, indent=2))

    health = build_health_report(elapsed, conv_by_cat, results, disabled=disabled_reasons)
    _write_text(os.path.join(out_dir, "health.json"), json.dumps(health, ensure_ascii=False, indent=2))
    hs = health["summary"]
    log(
        f"  • source health: {hs['ok']} ok / {hs['empty']} empty / {hs['fail']} fail"
        f" / {hs['disabled']} disabled / {hs['unknown']} unknown (total {hs['total']})"
    )

    cs = health.get("converters") or {}
    for target in ("clash", "singbox"):
        t = cs.get(target)
        if t:
            reasons = ", ".join(f"{k}={v}" for k, v in (t.get("by_reason") or {}).items())
            log(f"  • {target} drops: {t.get('total', 0)}" + (f" ({reasons})" if reasons else ""))

    gs = health.get("geo")
    if gs:
        log(
            "  • geo: db="
            + ("yes" if gs.get("db_loaded") else "no")
            + f" ip={gs.get('by_ip_literal', 0)} dns={gs.get('by_dns', 0)} "
            f"dns_failed={gs.get('dns_failed', 0)}"
        )

    log(
        f"✅ Goodbaye Aggregation Done in {elapsed:.1f}s — "
        f"ALL={len(res_all.unique)} HEAVY={len(res_heavy.unique)} LIGHT={len(res_light.unique)} unique"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
