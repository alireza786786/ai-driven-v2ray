# -*- coding: utf-8 -*-
"""
scripts/state.py — حافظه بین‌دوره‌ای و سیستم خودکار ارزیابی کیفیت و بازده یکتای منابع.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

اصول طراحی:
  • سنجش بازدهِ یکتا (Unique Yield): منبعی که همه نودهایش تکراریِ سورس‌های دیگر باشد، انگل شناسایی شده و خاموش می‌شود.
  • گارد ایمنی سورس‌های آینه‌ای (Mirror Guard): جلوگیری از خاموش شدن هم‌زمان دو سورس هم‌پوشان جهت عدم ریزش نودها.
  • طراحی Fail-Open: هیچ خطایی در خواندن حافظه نمی‌تواند اجرای خط لوله و انتشار کانفیگ‌ها را متوقف کند.
  • رشد کران‌دار (Bounded Growth): نگهداری حداکثر ۲۰ دور گذشته در state.json جهت جلوگیری از تورم حجم گیت.
  • نگارش کاملاً اتمیک با فایل موقت (.tmp) و جایگزینی آنی (os.replace).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Dict, List, Optional, Set

SCHEMA: int = 1
MAX_HISTORY: int = 20
MIN_ROUNDS: int = 10
MIN_ACTIVE: int = 8
STATE_PATH: str = "state.json"


def source_key(url: str) -> str:
    """شناسه هشدار پایدار و محتوامحور برای هر منبع بر پایه URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def empty_state() -> Dict:
    """ساختار اولیه و امن در صورت نبود حافظه قبلی."""
    return {"schema": SCHEMA, "updated_at": _now_iso(), "round": 0, "sources": {}}


def _clip(seq: Any, n: int = MAX_HISTORY) -> List[int]:
    """برش امن آخرین n عنصر عددی جهت تضمین کران رشد ثابت دیتابیس."""
    if not isinstance(seq, list):
        return []
    out: List[int] = []
    for v in seq:
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            out.append(v)
        elif isinstance(v, float) and v == int(v):
            out.append(int(v))
    return out[-n:] if n > 0 else []


def load_state(path: str = STATE_PATH) -> Dict:
    """خواندن امن حافظه دوره‌های قبل بدون پرتاب استثنا در زمان خطا (Fail-Open)."""
    if not os.path.exists(path):
        print(f"🧠 no {path} yet — starting with an empty memory (first round)")
        return empty_state()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ {path} is unreadable ({type(exc).__name__}) — starting with empty memory")
        return empty_state()

    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return empty_state()

    srcs = raw.get("sources")
    if not isinstance(srcs, dict):
        return empty_state()

    clean: Dict[str, Dict] = {}
    for key, ent in srcs.items():
        if not isinstance(key, str) or not isinstance(ent, dict):
            continue
        url = ent.get("url")
        if not isinstance(url, str) or "://" not in url:
            continue
        clean[key] = {
            "url": url,
            "tier": ent.get("tier") if isinstance(ent.get("tier"), str) else "unknown",
            "rounds": int(ent["rounds"]) if isinstance(ent.get("rounds"), int) else 0,
            "last_seen": ent.get("last_seen") if isinstance(ent.get("last_seen"), str) else None,
            "yield": _clip(ent.get("yield")),
            "unique": _clip(ent.get("unique")),
            "fail": int(ent["fail"]) if isinstance(ent.get("fail"), int) else 0,
            "disabled_since": (
                ent.get("disabled_since") if isinstance(ent.get("disabled_since"), str) else None
            ),
            "reason": ent.get("reason") if isinstance(ent.get("reason"), str) else None,
        }

    rnd = raw.get("round")
    return {
        "schema": SCHEMA,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else _now_iso(),
        "round": int(rnd) if isinstance(rnd, int) and rnd >= 0 else 0,
        "sources": clean,
    }


def save_state(state: Dict, path: str = STATE_PATH) -> bool:
    """ذخیره اتمیک وضعیت حافظه با os.replace جهت مهار فایل‌های نیمه‌نوشته."""
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ could not write {path} ({type(exc).__name__}) — round continues")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def record_round(
    state: Dict, per_source: Dict[str, Dict], live_urls: List[str]
) -> Dict:
    """ثبت آمار دور جاری و پاک‌سازی سورس‌های حذف‌شده (Garbage Collection)."""
    live_keys = {source_key(u) for u in live_urls}
    srcs: Dict[str, Dict] = {
        k: v for k, v in state.get("sources", {}).items() if k in live_keys
    }

    now = _now_iso()
    for url, obs in per_source.items():
        key = source_key(url)
        if key not in live_keys:
            continue
        ent = srcs.get(key) or {
            "url": url,
            "tier": obs.get("tier", "unknown"),
            "rounds": 0,
            "last_seen": None,
            "yield": [],
            "unique": [],
            "fail": 0,
            "disabled_since": None,
            "reason": None,
        }
        ent["url"] = url
        ent["tier"] = obs.get("tier", ent.get("tier", "unknown"))
        total = int(obs.get("total", 0) or 0)
        uniq = int(obs.get("unique", 0) or 0)
        ent["yield"] = _clip(list(ent.get("yield", [])) + [total])
        ent["unique"] = _clip(list(ent.get("unique", [])) + [uniq])
        ent["rounds"] = int(ent.get("rounds", 0)) + 1
        ent["last_seen"] = now
        ent["fail"] = int(ent.get("fail", 0)) + (1 if total == 0 else 0)
        srcs[key] = ent

    state["schema"] = SCHEMA
    state["sources"] = srcs
    state["round"] = int(state.get("round", 0)) + 1
    state["updated_at"] = now
    return state


def disable_candidates(
    state: Dict,
    current_unique: Dict[str, int],
    union_size: int,
    keys_by_url: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, str]:
    """
    شناسایی سورس‌های انگلی با ۳ شرط سخت‌گیرانه:
      ۱) حداقل ۱۰ دور آزمون ثبت شده باشد.
      ۲) در ۱۰ دور متوالی بازده یکتای سورس صفر باشد.
      ۳) وتوی لحظه‌ای: اگر امروز حتی ۱ نود یکتا داشته باشد، هرگز خاموش نمی‌شود.
      + کف ایمنی: تعداد سورس‌های فعال هرگز از ۸ کمتر نخواهد شد.
      + گارد آینه‌ها: سورس‌های آینه‌ای هم‌زمان خاموش نمی‌شوند.
    """
    srcs = state.get("sources", {})
    active = [k for k, e in srcs.items() if not e.get("disabled_since")]
    eligible: List[tuple] = []

    for key in active:
        ent = srcs[key]
        rounds = int(ent.get("rounds", 0))
        hist = _clip(ent.get("unique"), MIN_ROUNDS)
        if rounds < MIN_ROUNDS:
            continue
        if len(hist) < MIN_ROUNDS or any(v != 0 for v in hist):
            continue
        today = int(current_unique.get(ent["url"], 0) or 0)
        if today > 0:
            continue
        eligible.append((key, rounds))

    budget = max(0, len(active) - MIN_ACTIVE)
    eligible.sort(key=lambda kv: -kv[1])
    out: Dict[str, str] = {}

    if keys_by_url is None:
        chosen = eligible[:budget]
    else:
        active_urls = [srcs[k]["url"] for k in active]
        dropped: Set[str] = set()
        chosen = []
        for key, rounds in eligible:
            if len(chosen) >= budget:
                break
            url = srcs[key]["url"]
            mine = keys_by_url.get(url) or set()
            if mine:
                remaining: Set[str] = set()
                for other in active_urls:
                    if other != url and other not in dropped:
                        remaining |= keys_by_url.get(other) or set()
                if not mine <= remaining:
                    continue
            dropped.add(url)
            chosen.append((key, rounds))

    for key, rounds in chosen:
        out[srcs[key]["url"]] = (
            f"zero unique yield in the last {MIN_ROUNDS} of {rounds} rounds, "
            f"and zero again this round"
        )
    return out


def mark_disabled(state: Dict, reasons: Dict[str, str]) -> Dict:
    """ثبت زمان و علت غیرفعال‌سازی سورس در دیتابیس حافظه."""
    now = _now_iso()
    for url, why in reasons.items():
        ent = state.get("sources", {}).get(source_key(url))
        if ent is not None and not ent.get("disabled_since"):
            ent["disabled_since"] = now
            ent["reason"] = why
    return state


def disabled_urls(state: Dict) -> List[str]:
    """لیست آدرس‌هایی که به دلیل بازده صفر خاموش شده‌اند."""
    return [
        e["url"]
        for e in state.get("sources", {}).values()
        if e.get("disabled_since") and isinstance(e.get("url"), str)
    ]


def summary(state: Dict) -> str:
    srcs = state.get("sources", {})
    off = sum(1 for e in srcs.values() if e.get("disabled_since"))
    return (
        f"🧠 memory: round={state.get('round', 0)} "
        f"sources={len(srcs)} disabled={off}"
    )
