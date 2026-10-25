# -*- coding: utf-8 -*-
"""
scripts/validate.py — دروازهٔ اعتبارسنجی خروجی‌ها با کلاینت‌های واقعی (sing-box و mihomo).
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال رسمی: @Goodbaye_filtering

فلسفه مهندسی دروازه خروج:
  یک کانفیگ نامعتبر در وسط فایل Clash یا Sing-box کل فایل را برای کلاینت غیرقابل‌استفاده می‌کند.
  بنابراین پیش از انتشار، تمام خروجی‌ها مستقیماً با باینری‌های واقعی کاربر تست می‌شوند:
    • sing-box check -c <file>
    • mihomo -t -d <dir> -f <file>
    • آزمون بارگذاری اشتراک متنی در سوکت یونیکس دیمون می‌هومو (Mihomo Provider Load)
  در غیاب باینری‌ها (محیط محلی/ترموکس)، اعتبارسنجی ساختاری کل (Total Structural Check) فعال می‌شود.
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

#: دسته‌های پایه که تولیدشان همیشگی است
CORE_CATEGORIES: Tuple[str, ...] = ("all", "heavy", "light")

#: دسته‌های آبشاری فاز تست ترافیک (الزامی به‌شرط حضور)
OPTIONAL_CATEGORIES: Tuple[str, ...] = ("verified", "fast", "secure")

CATEGORIES: Tuple[str, ...] = CORE_CATEGORIES + OPTIONAL_CATEGORIES

assert not (set(CORE_CATEGORIES) & set(OPTIONAL_CATEGORIES)), "دسته پایه نباید در لیست اختیاری باشد"
assert len(set(CATEGORIES)) == len(CATEGORIES), "نام دسته‌ها نباید تکراری باشد"

CHECK_TIMEOUT: int = 180

#: فهرست سفید وضعیت‌های مجاز برای عبور از دروازه انتشار (گارد F-5)
ACCEPTABLE_STATUSES: Tuple[str, ...] = ("pass", "skipped")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _find_binary(*names: str) -> Optional[str]:
    """یافتن مسیر باینری در PATH سیستم یا مسیرهای استاندارد نصب."""
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for n in names:
        for cand in (
            f"/usr/local/bin/{n}",
            f"/usr/bin/{n}",
            f"./{n}",
            os.path.expanduser(f"~/.local/bin/{n}"),
        ):
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


# ──────────────────────────────────────────────────────────────────────────────
# اعتبارسنجی ساختاری اسناد (Fallback در غیاب باینری)
# ──────────────────────────────────────────────────────────────────────────────

def _total_check(fn):
    """لفاف محافظتی جامع: تبدیل هر استثنای غیرمنتظره به (False, detail) بدون توقف برنامه."""
    def wrapper(path: str) -> Tuple[bool, str]:
        try:
            return fn(path)
        except Exception as e:  # noqa: BLE001
            return False, f"unexpected document shape ({type(e).__name__}: {str(e)[:120]})"
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__wrapped__ = fn
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
                return False, f"{o.get('tag')!r}: selector/urltest outbounds must be a list"
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
        return False, "duplicate proxy names (mihomo rejects the file)"

    groups = doc.get("proxy-groups") or []
    if not isinstance(groups, list):
        return False, f"proxy-groups must be a list, got {type(groups).__name__}"

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


# ──────────────────────────────────────────────────────────────────────────────
# اعتبارسنجی با موتور کلاینت‌های واقعی
# ──────────────────────────────────────────────────────────────────────────────

def check_singbox(path: str, binary: Optional[str]) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"status": "missing", "detail": "file not found"}
    if not binary:
        ok, detail = _structural_singbox(path)
        return {
            "status": "skipped" if ok else "fail",
            "detail": detail,
            "note": "sing-box binary unavailable; structural check only",
        }
    code, out = _run([binary, "check", "-c", path])
    if code == 0:
        return {"status": "pass", "detail": "sing-box check OK"}
    return {"status": "fail", "detail": out.splitlines()[0][:300] if out else f"exit {code}"}


def check_clash(path: str, binary: Optional[str]) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"status": "missing", "detail": "file not found"}
    if not binary:
        ok, detail = _structural_clash(path)
        return {
            "status": "skipped" if ok else "fail",
            "detail": detail,
            "note": "mihomo binary unavailable; structural check only",
        }
    with tempfile.TemporaryDirectory() as d:
        code, out = _run([binary, "-t", "-d", d, "-f", path])
    bad = [ln for ln in out.splitlines() if "level=error" in ln or "level=fatal" in ln]
    if code == 0 and not bad:
        return {"status": "pass", "detail": "mihomo -t OK"}
    detail = bad[0] if bad else out.splitlines()[0] if out else f"exit {code}"
    return {"status": "fail", "detail": detail[:300]}


# ──────────────────────────────────────────────────────────────────────────────
# آزمون بارگذاری واقعی سابسکریپشن‌های متنی در دیمون می‌هومو
# ──────────────────────────────────────────────────────────────────────────────

MIHOMO_URI_SCHEMES = frozenset({
    "hysteria", "hysteria2", "hy2", "hysteria2+realm", "hy2+realm", "tuic",
    "trojan", "vless", "vmess", "ss", "ssr", "socks", "socks5", "socks5h",
    "http", "https", "anytls", "mierus",
})

SUBSCRIPTION_TIMEOUT: int = 120
_SENTINEL = "zz_load_sentinel"
_PROVIDER_ERR_RE = re.compile(r'initial proxy provider (p\d{3}) error: (.*?)"?\s*$', re.M)


def _subscription_files(out_dir: str, categories: List[str]) -> List[str]:
    rels: List[str] = []
    for cat in categories:
        for name in ("configs.txt", "configs_base64.txt"):
            rels.append(f"{cat}/{name}")
    rels.append("top100.txt")
    for sub in ("protocols", "Countries"):
        for p in glob.glob(os.path.join(out_dir, sub, "*.txt")):
            rels.append(f"{sub}/{os.path.basename(p)}")
    seen = sorted(set(rels))
    return [r for r in seen if os.path.isfile(os.path.join(out_dir, r))]


def _supported_lines(text: str) -> int:
    n = 0
    for line in text.split("\n"):
        scheme, sep, _ = line.strip().partition("://")
        if sep and scheme.lower() in MIHOMO_URI_SCHEMES:
            n += 1
    return n


def _mihomo_relevant_lines(buf: bytes) -> int:
    text = buf.decode("utf-8", errors="replace")
    best = _supported_lines(text)
    compact = "".join(text.split())
    if compact:
        try:
            dec = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
            best = max(best, _supported_lines(dec.decode("utf-8", "replace")))
        except Exception:  # noqa: BLE001
            pass
    return best


def _parse_provider_errors(log_text: str) -> Dict[str, str]:
    return {
        m.group(1): m.group(2).replace('\\"', '"')
        for m in _PROVIDER_ERR_RE.finditer(_clean(log_text))
    }


def _api_get(sock_path: str, path: str) -> Any:
    import http.client
    import socket

    class _Unix(http.client.HTTPConnection):
        def connect(self) -> None:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(30)
            self.sock.connect(sock_path)

    conn = _Unix("mihomo")
    try:
        conn.request("GET", path)
        return json.loads(conn.getresponse().read())
    finally:
        conn.close()


def _classify_subscription(
    relevant: int, loaded: int, error: Optional[str]
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"lines": relevant, "loaded": loaded}
    if relevant == 0:
        entry["status"] = "n/a"
        if error:
            entry["detail"] = error[:300]
    elif error:
        entry.update(status="fail", detail=error[:300])
    elif loaded == 0:
        entry.update(status="fail", detail="provider loaded 0 proxies")
    else:
        entry["status"] = "pass"
    return entry


def check_subscriptions(
    out_dir: str,
    binary: Optional[str],
    categories: Optional[List[str]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    cats = list(categories) if categories is not None else list(CORE_CATEGORIES)
    if not binary:
        return {
            "status": "skipped",
            "files": {},
            "detail": "mihomo binary unavailable; subscription load not run",
        }
    limit = float(timeout if timeout is not None else SUBSCRIPTION_TIMEOUT)
    files = _subscription_files(out_dir, cats)
    if not files:
        return {"status": "fail", "files": {}, "detail": "no subscription files"}

    work = tempfile.mkdtemp(prefix="mh_sub_")
    proc = None
    try:
        names: Dict[str, str] = {}
        relevant: Dict[str, int] = {}
        cfg = [
            "mixed-port: 0",
            "log-level: info",
            f"external-controller-unix: {json.dumps(os.path.join(work, 'api.sock'))}",
            "proxy-providers:",
        ]
        for i, rel in enumerate(files):
            name = f"p{i:03d}"
            names[name] = rel
            with open(os.path.join(out_dir, rel), "rb") as fh:
                buf = fh.read()
            relevant[name] = _mihomo_relevant_lines(buf)
            with open(os.path.join(work, f"{name}.txt"), "wb") as fh:
                fh.write(buf)
            cfg.append(f"  {name}: {{type: file, path: ./{name}.txt, health-check: {{enable: false}}}}")

        with open(os.path.join(work, "sentinel.txt"), "w", encoding="utf-8") as fh:
            fh.write("DOMAIN,sentinel.invalid\n")
        cfg += [
            "rule-providers:",
            f"  {_SENTINEL}: {{type: file, behavior: classical, format: text, path: ./sentinel.txt}}",
            "proxy-groups:",
            "  - {name: g, type: select, use: [" + ", ".join(names) + "]}",
            f'rules: ["RULE-SET,{_SENTINEL},DIRECT", "MATCH,DIRECT"]',
        ]

        conf = os.path.join(work, "config.yaml")
        with open(conf, "w", encoding="utf-8") as fh:
            fh.write("\n".join(cfg) + "\n")

        log_path = os.path.join(work, "mihomo.log")
        marker = f"Start initial provider {_SENTINEL}"
        with open(log_path, "wb") as log_file:
            proc = subprocess.Popen(
                [binary, "-d", work, "-f", conf],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            started = time.time()
            while True:
                with open(log_path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                if marker in text:
                    break
                if proc.poll() is not None:
                    last = _clean(text).strip().splitlines()[-1:] or [""]
                    return {
                        "status": "fail",
                        "files": {},
                        "detail": f"mihomo exited {proc.returncode} before loading: {last[0][:300]}",
                    }
                if time.time() - started > limit:
                    return {
                        "status": "fail",
                        "files": {},
                        "detail": f"providers not loaded within {limit:g}s",
                    }
                time.sleep(0.2)

            elapsed = round(time.time() - started, 2)
            data = _api_get(os.path.join(work, "api.sock"), "/providers/proxies").get(
                "providers", {}
            )

        with open(log_path, encoding="utf-8", errors="replace") as fh:
            errors = _parse_provider_errors(fh.read())

        results: Dict[str, Any] = {}
        for name, rel in names.items():
            loaded = len((data.get(name) or {}).get("proxies") or [])
            results[rel] = _classify_subscription(relevant[name], loaded, errors.get(name))

        failed = sorted(r for r, e in results.items() if e["status"] == "fail")
        return {
            "status": "fail" if failed else "pass",
            "files": results,
            "failed": failed,
            "seconds": elapsed,
            "detail": (
                f"{len(failed)} of {len(results)} subscription file(s) load 0 proxies in mihomo"
                if failed
                else f"{len(results)} subscription file(s) loaded"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "fail",
            "files": {},
            "detail": f"subscription check error ({type(e).__name__}: {str(e)[:200]})",
        }
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        shutil.rmtree(work, ignore_errors=True)


# ──────────────────────────────────────────────────────────────────────────────
# گزارش نهایی اعتبارسنجی خروجی‌ها
# ──────────────────────────────────────────────────────────────────────────────

def validate_outputs(out_dir: str) -> Dict[str, Any]:
    sb = _find_binary("sing-box")
    mh = _find_binary("mihomo", "clash-meta", "clash")
    report: Dict[str, Any] = {
        "tools": {
            "sing_box": sb or None,
            "mihomo": mh or None,
        },
        "results": {},
        "summary": {"pass": 0, "fail": 0, "skipped": 0, "missing": 0},
    }
    absent: List[str] = []

    for cat in CATEGORIES:
        cat_dir = os.path.join(out_dir, cat)
        if cat in OPTIONAL_CATEGORIES and not os.path.isdir(cat_dir):
            absent.append(cat)
            continue
        report["results"][cat] = {
            "singbox": check_singbox(os.path.join(cat_dir, "singbox.json"), sb),
            "clash": check_clash(os.path.join(cat_dir, "clash.yaml"), mh),
        }

    report["absent_optional"] = absent
    assert all(c in report["results"] for c in CORE_CATEGORIES), "همه دسته‌های اصلی باید اعتبارسنجی شوند"

    for cat_res in report["results"].values():
        for res in cat_res.values():
            report["summary"][res["status"]] = report["summary"].get(res["status"], 0) + 1

    # گیت فهرست سفید: وضعیت‌های غیر از pass و skipped انتشار را می‌بندند
    offending = {
        status: count
        for status, count in report["summary"].items()
        if count > 0 and status not in ACCEPTABLE_STATUSES
    }
    report["offending"] = offending
    report["ok"] = not offending
    report["real_validation"] = report["summary"]["pass"] > 0
    report["subscriptions"] = check_subscriptions(out_dir, mh, categories=list(report["results"]))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Goodbaye Universal Standard Output Validator")
    ap.add_argument("--out", default=os.getcwd(), help="مسیر ریشه مخزن حاوی پوشه‌های all/ و verified/")
    ap.add_argument("--strict", action="store_true", help="کد خروج ۱ در صورت ریجکت هر فایل")
    ap.add_argument("--strict-subscriptions", action="store_true", help="کد خروج ۱ در صورت بارگذاری صفر نود در اشتراک‌ها")
    ap.add_argument("--json", dest="json_path", default="", help="ذخیره گزارش کامل در این مسیر JSON")
    args = ap.parse_args()

    rep = validate_outputs(os.path.abspath(args.out))
    print("🔍 Goodbaye Client Validation")
    print(f"   sing-box: {rep['tools']['sing_box'] or 'NOT FOUND (structural fallback)'}")
    print(f"   mihomo  : {rep['tools']['mihomo'] or 'NOT FOUND (structural fallback)'}")

    icons = {"pass": "✅", "fail": "❌", "skipped": "⚠️", "missing": "🚫"}
    for cat, res in rep["results"].items():
        for kind, r in res.items():
            print(f"   {icons.get(r['status'], '?')} {cat:<8} {kind:<8} {r['status']:<8} {r['detail']}")

    for cat in rep.get("absent_optional", []):
        print(f"   ➖ {cat:<8} {'—':<8} not produced in this run")

    s = rep["summary"]
    print(f"   → pass={s['pass']} fail={s['fail']} skipped={s['skipped']} missing={s['missing']}")

    if not rep.get("real_validation", False):
        print("   ⚠️ structural fallback only — no real client validated this run")

    sub = rep.get("subscriptions") or {}
    sub_icon = {"pass": "✅", "fail": "❌", "skipped": "⚠️"}.get(sub.get("status"), "?")
    print(f"   {sub_icon} subscriptions (mihomo provider load): {sub.get('status')} — {sub.get('detail', '')}")

    for rel in sub.get("failed", []):
        e = sub["files"][rel]
        print(f"      ❌ {rel}: lines={e['lines']} loaded={e['loaded']} {e.get('detail', '')}")

    if args.json_path:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_path)) or ".", exist_ok=True)
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)

    if args.strict and not rep["ok"]:
        print("❌ Validation gate FAILED — خروجی‌ها معتبر نیستند و اجازه انتشار ندارند.")
        return 1

    if args.strict_subscriptions and sub.get("status") == "fail":
        print("❌ Subscription gate FAILED — فایل اشتراک متنی در می‌هومو بارگذاری نمی‌شود.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
