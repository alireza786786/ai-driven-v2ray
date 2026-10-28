# -*- coding: utf-8 -*-
"""
scripts/filters.py — لایهٔ L0/L1 آبشارِ حقیقت‌سنجی: یکتاسازی و فیلترِ ارزانِ بی‌شبکه.
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

جای این ماژول در معماری:
    all/configs.txt → [L0 یکتاسازی] → [L1 فیلترِ ارزان] → L2 (TCP) → L3 (پروکسیِ واقعی)

ویژگی‌ها:
  • قاعده سقف ۳۰ بایتی شناسه سفارشی Xray و مهار Nil UUID
  • یکتاسازی بر پایه زوج (host, port) و صرفه‌جویی در پردازش شبکه
  • استفاده از converters.parse_proxy به جای عبارات منظم جهت جلوگیری از آسیب به IPv6
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import converters

UUID_PROTOCOLS = frozenset({"vless", "vmess", "tuic"})

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_CUSTOM_ID_MAX_BYTES = 30
_UUID_RE_COMPACT = re.compile(r"^[0-9a-fA-F]{32}$")
_NIL_UUID = "00000000-0000-0000-0000-000000000000"

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
    try:
        p = int(str(port).strip())
    except (TypeError, ValueError):
        return True
    return not (0 < p < 65536)


def is_invalid_uuid(uuid: Any, proto: str) -> bool:
    if proto not in UUID_PROTOCOLS:
        return False
    s = str(uuid or "").strip()
    if not s:
        return True
    if _UUID_RE.match(s) or _UUID_RE_COMPACT.match(s):
        return s.replace("-", "").lower() == _NIL_UUID.replace("-", "")
    return len(s.encode("utf-8")) >= _CUSTOM_ID_MAX_BYTES


def endpoint_of_proxy(p: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    host = str(p.get("server") or "").strip().strip("[]").lower()
    try:
        port = int(str(p.get("port")).strip())
    except (TypeError, ValueError):
        return None
    if not host or not (0 < port < 65536):
        return None
    return host, port


def classify(line: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
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
    print(json.dumps({"stats": res["stats"], "dropped": res["dropped"]},
                     ensure_ascii=False, indent=2))
