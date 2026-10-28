# -*- coding: utf-8 -*-
"""
scripts/validate.py — دروازهٔ اعتبارسنجی خروجی‌ها با کلاینت واقعی (sing-box و mihomo).
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

اصلاحات:
  • حل باگ شماره ۷: مدیریت هوشمند دسته‌های اختیاری خالی تا --strict انتشار را بی‌دلیل مسدود نکند
  • حفظ فهرست سفید مجاز (F-5) و لفاف خطای کامل (F-4)
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

CORE_CATEGORIES = ("all", "heavy", "light")
OPTIONAL_CATEGORIES = ("verified", "fast", "secure")
CATEGORIES = CORE_CATEGORIES + OPTIONAL_CATEGORIES

CHECK_TIMEOUT = 180
ACCEPTABLE_STATUSES = ("pass", "skipped")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _find_binary(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for n in names:
        for cand in (f"/usr/local/bin/{n}", f"/usr/bin/{n}", f"./{n}", f"{os.environ.get('HOME', '')}/.local/bin/{n}"):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def _run(cmd: List[str]) -> Tuple[int, str]:
    try:
        pr = subprocess.run(cmd, capture_output=True, text=True, timeout=CHECK_TIMEOUT)
        return pr.returncode, _clean((pr.stdout or "") + (pr.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {CHECK_TIMEOUT}s"
    except Exception as e:  # noqa: BLE001
        return 125, f"{type(e).__name__}: {e}"


def _total_check(fn):
    def wrapper(path: str) -> Tuple[bool, str]:
        try:
            return fn(path)
        except Exception as e:  # noqa: BLE001
            return False, f"unexpected document shape ({type(e).__name__}: {str(e)[:120]})"
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_total_check
def _structural_singbox(path: str) -> Tuple[bool, str]:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:  # noqa: BLE001
        return False, f"JSON parse error: {e}"
    if not isinstance(doc, dict):
        return False, f"top-level JSON must be an object, got {type(doc).__name__}"
    if not isinstance(doc.get("outbounds"), list) or not doc["outbounds"]:
        return False, "missing/empty outbounds"
    tags = set()
    for o in doc["outbounds"]:
        if not isinstance(o, dict):
            return False, "non-object outbound"
        tag = o.get("tag")
        if isinstance(tag, (dict, list, set)):
            return False, f"outbound tag must be a scalar, got {type(tag).__name__}"
        tags.add(tag)
    for o in doc["outbounds"]:
        if o.get("type") in ("selector", "urltest"):
            refs = o.get("outbounds", [])
            if not isinstance(refs, list):
                return False, f"{o.get('tag')!r}: outbounds must be a list"
            for ref in refs:
                if ref not in tags:
                    return False, f"dangling reference: {ref!r}"
    route = doc.get("route")
    if route is not None and not isinstance(route, dict):
        return False, f"route must be an object, got {type(route).__name__}"
    final = (route or {}).get("final")
    if final and final not in tags:
        return False, f"route.final points to unknown tag: {final!r}"
    return True, f"structural ok ({len(doc['outbounds'])} outbounds)"


@_total_check
def _structural_clash(path: str) -> Tuple[bool, str]:
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except Exception as e:  # noqa: BLE001
        return False, f"YAML parse error: {e}"
    if not isinstance(doc, dict):
        got = "empty document" if doc is None else type(doc).__name__
        return False, f"top-level YAML must be a mapping, got {got}"
    proxies = doc.get("proxies")
    if not isinstance(proxies, list) or not proxies:
        return False, "missing/empty proxies"
    names = set()
    for p in proxies:
        if not isinstance(p, dict):
            return False, "non-object proxy entry"
        nm = p.get("name")
        if isinstance(nm, (dict, list, set)):
            return False, f"proxy name must be a scalar, got {type(nm).__name__}"
        names.add(nm)
    if len(names) != len(proxies):
        return False, "duplicate proxy names"
    groups = doc.get("proxy-groups") or []
    if not isinstance(groups, list):
        return False, "proxy-groups must be a list"
    group_names = {g.get("name") for g in groups if isinstance(g, dict)}
    for g in groups:
        if not isinstance(g, dict):
            return False, "non-object proxy-group entry"
        refs = g.get("proxies", [])
        if not isinstance(refs, list):
            return False, f"group {g.get('name')!r}: proxies must be a list"
        for ref in refs:
            if ref not in names and ref not in group_names:
                return False, f"group {g.get('name')!r} references unknown proxy {ref!r}"
    return True, f"structural ok ({len(proxies)} proxies)"


def check_singbox(path: str, binary: Optional[str]) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"status": "missing", "detail": "file not found"}
    if not binary:
        ok, detail = _structural_singbox(path)
        return {"status": "skipped" if ok else "fail", "detail": detail}
    code, out = _run([binary, "check", "-c", path])
    if code == 0:
        return {"status": "pass", "detail": "sing-box check OK"}
    return {"status": "fail", "detail": out.splitlines()[0][:300] if out else f"exit {code}"}


def check_clash(path: str, binary: Optional[str]) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"status": "missing", "detail": "file not found"}
    if not binary:
        ok, detail = _structural_clash(path)
        return {"status": "skipped" if ok else "fail", "detail": detail}
    with tempfile.TemporaryDirectory() as d:
        code, out = _run([binary, "-t", "-d", d, "-f", path])
    bad = [ln for ln in out.splitlines() if "level=error" in ln or "level=fatal" in ln]
    if code == 0 and not bad:
        return {"status": "pass", "detail": "mihomo -t OK"}
    detail = (bad[0] if bad else out.splitlines()[0] if out else f"exit {code}")
    return {"status": "fail", "detail": detail[:300]}


def validate_outputs(out_dir: str) -> Dict[str, Any]:
    sb = _find_binary("sing-box")
    mh = _find_binary("mihomo", "clash-meta", "clash")
    report: Dict[str, Any] = {
        "tools": {"sing_box": sb or None, "mihomo": mh or None},
        "results": {},
        "summary": {"pass": 0, "fail": 0, "skipped": 0, "missing": 0},
    }
    absent: List[str] = []

    for cat in CATEGORIES:
        cat_dir = os.path.join(out_dir, cat)
        sb_file = os.path.join(cat_dir, "singbox.json")
        cl_file = os.path.join(cat_dir, "clash.yaml")

        # حل باگ شماره ۷: اگر دسته‌ای اختیاری فاقد فایل بود یا دایرکتوری نداشت، آن را به عنوان غایب تلقی کن
        if cat in OPTIONAL_CATEGORIES:
            if not os.path.isdir(cat_dir) or (not os.path.exists(sb_file) and not os.path.exists(cl_file)):
                absent.append(cat)
                continue

        report["results"][cat] = {
            "singbox": check_singbox(sb_file, sb),
            "clash": check_clash(cl_file, mh),
        }

    report["absent_optional"] = absent
    for cat_res in report["results"].values():
        for res in cat_res.values():
            report["summary"][res["status"]] = report["summary"].get(res["status"], 0) + 1

    offending = {
        status: count
        for status, count in report["summary"].items()
        if count > 0 and status not in ACCEPTABLE_STATUSES
    }
    report["offending"] = offending
    report["ok"] = not offending
    report["real_validation"] = report["summary"]["pass"] > 0
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate generated client configs")
    ap.add_argument("--out", default=os.getcwd(), help="repo root containing all/ heavy/ light/")
    ap.add_argument("--strict", action="store_true", help="exit non-zero when any file fails validation")
    ap.add_argument("--json", dest="json_path", default="", help="also write the report to this path")
    args = ap.parse_args()

    rep = validate_outputs(os.path.abspath(args.out))
    print("🔍 Client validation")
    print(f"   sing-box: {rep['tools']['sing_box'] or 'NOT FOUND (structural fallback)'}")
    print(f"   mihomo  : {rep['tools']['mihomo'] or 'NOT FOUND (structural fallback)'}")
    icons = {"pass": "✅", "fail": "❌", "skipped": "⚠️", "missing": "🚫"}
    for cat, res in rep["results"].items():
        for kind, r in res.items():
            print(f"   {icons.get(r['status'], '?')} {cat:<8} {kind:<8} {r['status']:<8} {r['detail']}")
    for cat in rep.get("absent_optional", []):
        print(f"   ➖ {cat:<8} {'—':<8} skipped/not produced")

    s = rep["summary"]
    print(f"   → pass={s['pass']} fail={s['fail']} skipped={s['skipped']} missing={s['missing']}")

    if args.json_path:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_path)) or ".", exist_ok=True)
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)

    if args.strict and not rep["ok"]:
        print("❌ Validation gate FAILED — outputs must not be published.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
