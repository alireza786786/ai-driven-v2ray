#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/state.py — حافظهٔ بین‌دوره‌ای خط لوله، محاسبه بازده یکتا و مدیریت هوشمند سورس‌ها.
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

اصلاحات:
  • حل باگ ۱۸: وارد کردن Any از typing
  • پیاده‌سازی پیشنهاد ۱۲: احیای خودکار سورس‌های منقضی‌شده بعد از ۳۰ روز (reenable_expired)
  • حفظ گارد منابع آینه‌ای و سیستم ضدانگل بدون رگرسیون
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

SCHEMA = 1
MAX_HISTORY = 20
MIN_ROUNDS = 10
MIN_ACTIVE = 8
STATE_PATH = "state.json"
MAX_DISABLED_DAYS = 30  # احیای سورس بعد از ۳۰ روز (پیشنهاد ۱۲)


def source_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def empty_state() -> Dict[str, Any]:
    return {"schema": SCHEMA, "updated_at": _now_iso(), "round": 0, "sources": {}}


def _clip(seq: Any, n: int = MAX_HISTORY) -> List[int]:
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


def reenable_expired(state: Dict[str, Any], max_days: int = MAX_DISABLED_DAYS) -> Dict[str, Any]:
    """احیای خودکار سورس‌های غیرفعال‌شده پس از گذشت ۳۰ روز (پیاده‌سازی پیشنهاد ۱۲)."""
    now = datetime.now(timezone.utc)
    srcs = state.get("sources", {})
    reenabled_count = 0

    for key, ent in srcs.items():
        disabled_since_str = ent.get("disabled_since")
        if not disabled_since_str:
            continue
        try:
            disabled_time = datetime.fromisoformat(disabled_since_str.replace("Z", "+00:00"))
            days_passed = (now - disabled_time).total_seconds() / 86400.0
            if days_passed >= max_days:
                ent["disabled_since"] = None
                ent["reason"] = None
                ent["unique"] = []
                ent["rounds"] = 0
                reenabled_count += 1
        except Exception:
            continue

    if reenabled_count > 0:
        print(f"🔄 Memory: Re-enabled {reenabled_count} expired source(s) for a fresh trial.")
    return state


def load_state(path: str = STATE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return empty_state()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return empty_state()

    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        return empty_state()

    srcs = raw.get("sources")
    if not isinstance(srcs, dict):
        return empty_state()

    clean: Dict[str, Dict[str, Any]] = {}
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
            "disabled_since": (ent.get("disabled_since") if isinstance(ent.get("disabled_since"), str) else None),
            "reason": ent.get("reason") if isinstance(ent.get("reason"), str) else None,
        }

    rnd = raw.get("round")
    loaded = {
        "schema": SCHEMA,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else _now_iso(),
        "round": int(rnd) if isinstance(rnd, int) and rnd >= 0 else 0,
        "sources": clean,
    }
    # بررسی احیای سورس‌های قدیمی
    return reenable_expired(loaded)


def save_state(state: Dict[str, Any], path: str = STATE_PATH) -> bool:
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def record_round(state: Dict[str, Any], per_source: Dict[str, Dict[str, Any]], live_urls: List[str]) -> Dict[str, Any]:
    live_keys = {source_key(u) for u in live_urls}
    srcs: Dict[str, Dict[str, Any]] = {k: v for k, v in state.get("sources", {}).items() if k in live_keys}

    now = _now_iso()
    for url, obs in per_source.items():
        key = source_key(url)
        if key not in live_keys:
            continue
        ent = srcs.get(key) or {
            "url": url, "tier": obs.get("tier", "unknown"), "rounds": 0,
            "last_seen": None, "yield": [], "unique": [], "fail": 0,
            "disabled_since": None, "reason": None,
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


def disable_candidates(state: Dict[str, Any],
                       current_unique: Dict[str, int],
                       union_size: int,
                       keys_by_url: Optional[Dict[str, Set[str]]] = None) -> Dict[str, str]:
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
            f"zero unique yield in the last {MIN_ROUNDS} of {rounds} rounds, and zero again this round"
        )
    return out


def mark_disabled(state: Dict[str, Any], reasons: Dict[str, str]) -> Dict[str, Any]:
    now = _now_iso()
    for url, why in reasons.items():
        ent = state.get("sources", {}).get(source_key(url))
        if ent is not None and not ent.get("disabled_since"):
            ent["disabled_since"] = now
            ent["reason"] = why
    return state


def disabled_urls(state: Dict[str, Any]) -> List[str]:
    return [
        e["url"] for e in state.get("sources", {}).values()
        if e.get("disabled_since") and isinstance(e.get("url"), str)
    ]


def summary(state: Dict[str, Any]) -> str:
    srcs = state.get("sources", {})
    off = sum(1 for e in srcs.values() if e.get("disabled_since"))
    return f"🧠 Memory: round={state.get('round', 0)} sources={len(srcs)} disabled={off}"
