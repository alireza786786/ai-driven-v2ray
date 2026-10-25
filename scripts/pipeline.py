#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/pipeline.py — هماهنگ‌کننده آبشار چهارلایه (L0/L1 -> L2 -> L3) و رتبه‌بندی کیفی سرورها.
پروژه: Goodbaye Universal Standard | ai-driven-v2ray
مالک: alireza786786 | کانال: @Goodbaye_filtering

اصلاحات و ارتقاهای منطبق بر منشور:
  • ارتقای شاخص پینگ Fast VIP Strict به زیر ۵۰۰ میلی‌ثانیه (L3_FAST_MS = 500)
  • تزریق پینگ دقیق میانه و ریمارک ۵ خطی رسمی به تمام کانفیگ‌های خروجی
  • حفظ پایداری کامل در ۳ دور آزمون هسته (Multi-Round Consensus)
  • تفکیک محرمانگی پیشرو (PFS) برای پکیج Secure و رتبه‌بندی Top 100
  • تولید فایل‌های چهارگانه کلاینت‌ها و تفکیک کشوری
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import realtest  # noqa: E402
import reachability  # noqa: E402
import filters  # noqa: E402
import converters  # noqa: E402
import core  # noqa: E402
import countries  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# ثابت‌ها و آستانه‌های کیفی
# ──────────────────────────────────────────────────────────────────────────────

#: تعداد دورهای اجرای L3 برای اثبات قطعی پایداری سرور (قبولی در هر ۳ دور اجباری است)
L3_ROUNDS: int = int(os.environ.get("L3_ROUNDS", "3"))

#: آستانه پینگ پکیج فوق‌سریع بر پایه میانه دورها (منطبق با دستور جدید منشور: زیر ۵۰۰ms)
FAST_THRESHOLD_MS: int = int(os.environ.get("L3_FAST_MS", "500"))

#: سقف تعداد کانفیگ‌های پکیج طلایی top100.txt
TOP_N: int = int(os.environ.get("L3_TOP_N", "100"))

#: مقادیر مجاز TLS با محرمانگی پیشرو (Forward Secrecy)
FS_TLS_VALUES: frozenset = frozenset({"tls", "reality", "xtls"})

#: پروتکل‌های مبتنی بر QUIC با TLS 1.3 اجباری
FS_SCHEMES: frozenset = frozenset({"hysteria2", "hy2", "tuic"})

#: پارامترهایی که اعتبارسنجی سرتیفیکیت را خاموش می‌کنند (ناامن در برابر MITM)
INSECURE_KEYS: frozenset = frozenset({
    "insecure", "allowinsecure", "allow_insecure",
    "skip-cert-verify", "skipcertverify", "allowinsecureciphers",
})
_TRUEISH: frozenset = frozenset({"1", "true", "yes", "on"})

CATEGORIES: Tuple[str, ...] = ("verified", "fast", "secure")


class StabilityError(RuntimeError):
    """خطای محیطی در صورت عدم تولید نتایج معتبر توسط آزمون L3."""


# ──────────────────────────────────────────────────────────────────────────────
# داوری امنیت و محرمانگی پیشرو (Forward Secrecy)
# ──────────────────────────────────────────────────────────────────────────────

def scheme_of(link: str) -> str:
    return link.split("://", 1)[0].strip().lower() if "://" in link else ""


def _query(link: str) -> Dict[str, str]:
    try:
        raw = parse_qs(urlsplit(link).query)
    except ValueError:
        return {}
    return {k.strip().lower(): (v[0] if v else "") for k, v in raw.items()}


def declares_insecure(link: str) -> bool:
    """آیا لینک اعتبارسنجی گواهی SSL را غیرفعال کرده است؟"""
    q = _query(link)
    for key in INSECURE_KEYS:
        if unquote(q.get(key, "")).strip().lower() in _TRUEISH:
            return True
    return False


def has_forward_secrecy(link: str, tls_value: str) -> bool:
    """آیا رمزنگاری نود دارای محرمانگی پیشرو (PFS) با دست‌دادن ECDHE است؟"""
    if (tls_value or "").strip().lower() in FS_TLS_VALUES:
        return True
    return scheme_of(link) in FS_SCHEMES


def is_secure(link: str, tls_value: str) -> bool:
    return has_forward_secrecy(link, tls_value) and not declares_insecure(link)


# ──────────────────────────────────────────────────────────────────────────────
# دور چندباره L3 (اجماع آماری و حذف Flakiness)
# ──────────────────────────────────────────────────────────────────────────────

def _median_int(values: Sequence[int]) -> int:
    return int(round(statistics.median(values)))


def _rows_of(result: Dict[str, Any]) -> List[Dict[str, str]]:
    rows = result.get("rows")
    if isinstance(rows, dict):
        return list(rows.values())
    if isinstance(rows, list):
        return rows
    raise StabilityError(f"شکل نامعتبر فیلد rows در خروجی L3: {type(rows).__name__}")


def run_l3_round(
    lines: Sequence[str],
    rounds: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """اجرای آزمون عبور ترافیک در ۳ دور مستقل و استخراج سرورهای واقعاً پایدار."""
    if rounds is None:
        rounds = L3_ROUNDS
    if rounds < 1:
        raise ValueError(f"تعداد دورها باید حداقل ۱ باشد، دریافت شد: {rounds!r}")

    lines = [ln.strip() for ln in lines if (ln or "").strip()]
    if not lines:
        raise realtest.EmptyInput("هیچ کانفیگی برای آزمون L3 وجود ندارد.")

    ok_sets: List[set] = []
    per_run_ok: List[int] = []
    delays: Dict[str, List[int]] = {}
    tls_of: Dict[str, str] = {}

    for _ in range(rounds):
        res = realtest.test_lines(lines, **kwargs)
        ok_now = set()
        for row in _rows_of(res):
            link = (row.get("link") or "").strip()
            if not link:
                continue
            tls_of.setdefault(link, realtest.row_tls(row))
            if realtest.is_row_genuinely_ok(row):
                ok_now.add(link)
                d = realtest.row_delay_ms(row)
                if d is not None:
                    delays.setdefault(link, []).append(d)
        ok_sets.append(ok_now)
        per_run_ok.append(len(ok_now))

    if not ok_sets:
        raise StabilityError("هیچ دور آزمونی به نتیجه نرسید.")

    stable = set.intersection(*ok_sets)
    ever_ok = set.union(*ok_sets)
    flaky_pct = (
        round(100.0 * (len(ever_ok) - len(stable)) / len(ever_ok), 2)
        if ever_ok
        else 0.0
    )

    return {
        "rounds": rounds,
        "per_run_ok": per_run_ok,
        "stable": stable,
        "ever_ok": ever_ok,
        "delays": {L: _median_int(delays[L]) for L in stable if L in delays},
        "tls": tls_of,
        "flaky_pct": flaky_pct,
    }


def build_buckets(
    round_result: Dict[str, Any],
    fast_ms: Optional[int] = None,
    top_n: Optional[int] = None,
) -> Dict[str, Any]:
    """
    سبدبندی نهایی کانفیگ‌ها و اعمال ریمارک ۵ خطی منشور Goodbaye همراه با پینگ واقعی.
    """
    if fast_ms is None:
        fast_ms = FAST_THRESHOLD_MS
    if top_n is None:
        top_n = TOP_N

    delays = round_result["delays"]
    tls_of = round_result["tls"]
    stable = round_result["stable"]

    # مرتب‌سازی بر اساس کمترین میانه تاخیر (پینگ)
    ranked = sorted(stable, key=lambda L: (delays.get(L, 10 ** 9), L))

    # انتخاب نودها برای هر دسته پیش از اعمال ریمارک نهایی
    fast_raw = [L for L in ranked if delays.get(L, 10 ** 9) < fast_ms]
    secure_raw = [L for L in ranked if is_secure(L, tls_of.get(L, ""))]
    top_raw = ranked[:top_n]

    # اعمال ریمارک ۵ خطی رسمی با پینگ واقعی به هر کانفیگ تأییدشده
    def _apply_goodbaye_remark(raw_link: str) -> str:
        measured_ping = delays.get(raw_link)
        return core.brand_remark(raw_link, delay=measured_ping)

    verified = [_apply_goodbaye_remark(L) for L in ranked]
    fast = [_apply_goodbaye_remark(L) for L in fast_raw]
    secure = [_apply_goodbaye_remark(L) for L in secure_raw]
    top = [_apply_goodbaye_remark(L) for L in top_raw]

    return {
        "verified": verified,
        "fast": fast,
        "secure": secure,
        "top": top,
        "delays": delays,
        "stats": {
            "rounds": round_result["rounds"],
            "per_run_ok": round_result["per_run_ok"],
            "ever_ok": len(round_result["ever_ok"]),
            "stable": len(stable),
            "flaky_pct": round_result["flaky_pct"],
            "fast_threshold_ms": fast_ms,
            "verified": len(verified),
            "fast": len(fast),
            "secure": len(secure),
            "top": len(top),
            "top_short_by": max(0, top_n - len(top)),
            "median_delay_ms": (
                _median_int(sorted(delays.values())) if delays else None
            ),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# نگارش اتمیک فایل‌های خروجی و تبدیل چندکلاینته
# ──────────────────────────────────────────────────────────────────────────────

def _write_lines(path: str, header: str, lines: Sequence[str]) -> None:
    core.assert_no_control_bytes(path, header)
    for line in lines:
        core.assert_no_control_bytes(path, line)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header)
        for line in lines:
            fh.write(line + "\n")


def write_buckets(out_dir: str, buckets: Dict[str, Any]) -> Dict[str, str]:
    """نگارش پکیج‌های خروجی همراه با سرآیندهای رسمی Hiddify و فایل‌های Clash و Sing-box."""
    st = buckets["stats"]
    rounds = st["rounds"]
    written: Dict[str, str] = {}

    hh = {cat: core.hiddify_profile_header(cat.upper()) for cat in CATEGORIES}

    heads = {
        "verified": (
            hh["verified"]
            + f"# {core.BRAND_CHANNEL} — VERIFIED ALL VIP — {st['verified']} configs\n"
            f"# criterion: a real proxied request to {realtest.TEST_URL} succeeded\n"
            f"# in ALL {rounds} independent runs of this round.\n"
            f"# measured: {st['flaky_pct']}% of tested working configs were flaky.\n"
        ),
        "fast": (
            hh["fast"]
            + f"# {core.BRAND_CHANNEL} — FAST VIP STRICT (<500ms) — {st['fast']} configs\n"
            f"# criterion: verified AND median delay across {rounds} runs < {st['fast_threshold_ms']}ms.\n"
            f"# strict low-latency filter suitable for restricted networks.\n"
        ),
        "secure": (
            hh["secure"]
            + f"# {core.BRAND_CHANNEL} — SECURE VIP — {st['secure']} configs\n"
            f"# criterion: verified AND forward secrecy (ECDHE / TLS / REALITY / QUIC)\n"
            f"# with certificate validation strictly enforced.\n"
        ),
    }

    for cat in CATEGORIES:
        path = os.path.join(out_dir, cat, "configs.txt")
        _write_lines(path, heads[cat], core.shield_unsupported_runs(buckets[cat]))
        written[cat] = path

        # تولید فرمت‌های تکمیلی برای هر دسته (Base64, Clash Meta YAML, Singbox JSON)
        for name, build in (
            ("configs_base64.txt",
             lambda L, head=hh[cat]: core.encode_base64_subscription(L, header=head)),
            ("clash.yaml",
             lambda L, head=hh[cat]: head + converters.build_clash_yaml(L)),
            ("singbox.json",
             lambda L: converters.build_singbox_json(L)),
        ):
            try:
                body = build(buckets[cat])
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ {cat}/{name}: {exc}", file=sys.stderr)
                continue
            sub = os.path.join(out_dir, cat, name)
            _write_lines(sub, "", [body.rstrip("\n")])
            written[f"{cat}/{name}"] = sub

    # نگارش پکیج طلایی top100.txt
    top_path = os.path.join(out_dir, "top100.txt")
    short = st["top_short_by"]
    top_head = (
        core.hiddify_profile_header(f"TOP {len(buckets['top'])}")
        + f"# {core.BRAND_CHANNEL} — TOP {len(buckets['top'])} VIP — sorted by median delay\n"
        f"# every entry passed a real proxied request in all {rounds} runs.\n"
    )
    if short:
        top_head += (
            f"# NOTE: only {len(buckets['top'])} configs met the bar this round "
            f"({short} short of {TOP_N}). The file is NOT padded with untested configs.\n"
        )
    _write_lines(top_path, top_head, core.shield_unsupported_runs(buckets["top"]))
    written["top"] = top_path
    return written


TRACE_URL: str = "https://cp.cloudflare.com/cdn-cgi/trace"


def exit_country(timeout: float = 10.0) -> Optional[Dict[str, str]]:
    """استعلام موقعیت جغرافیایی و آی‌پی رانر تست‌کننده."""
    import urllib.request

    try:
        with urllib.request.urlopen(TRACE_URL, timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None

    out: Dict[str, str] = {}
    for row in body.splitlines():
        k, _, v = row.partition("=")
        if k in ("loc", "colo") and v:
            out[k] = v
    if not out:
        return None
    out["source"] = TRACE_URL
    return out


def merge_health(out_dir: str, cascade: Dict[str, Any]) -> Optional[str]:
    """افزودن اتمیک تلمتری آبشار تست به گزارش سلامت health.json."""
    path = os.path.join(out_dir, "health.json")
    if not os.path.exists(path):
        print(f"⚠️ {path} وجود ندارد؛ تلمتری آبشار ادغام نشد.", file=sys.stderr)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ خواندن {path} ناموفق بود ({exc})", file=sys.stderr)
        return None
    if not isinstance(doc, dict):
        return None

    doc["cascade"] = cascade
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


CASCADE_CRITERIA: Dict[str, str] = {
    "verified": "a real proxied request succeeded in ALL rounds of this run",
    "fast": "verified AND median delay across all rounds is under 500ms (VIP Strict)",
    "secure": "verified AND forward secrecy ((EC)DHE via TLS/REALITY/QUIC) AND certificate validation active",
}


def merge_index(out_dir: str, buckets: Dict[str, Any]) -> Optional[str]:
    """افزودن خروجی‌های آبشار و تفکیک کشوری به سند رسمی index.json."""
    path = os.path.join(out_dir, "index.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(doc, dict):
        return None

    primary = doc.get("primary_base")
    mirror = doc.get("mirror_base") or ""
    if not isinstance(primary, str) or not primary:
        return None

    def _rel(*parts: str) -> str:
        return "/".join(parts)

    file_keys = (
        ("configs.txt", "configs_txt"),
        ("configs_base64.txt", "configs_base64"),
        ("clash.yaml", "clash_yaml"),
        ("singbox.json", "singbox_json"),
    )

    cascade: Dict[str, Any] = {}
    for cat in CATEGORIES:
        cat_dir = os.path.join(out_dir, cat)
        files: Dict[str, str] = {}
        for fname, key in file_keys:
            if not os.path.exists(os.path.join(cat_dir, fname)):
                continue
            files[key] = f"{primary}/{_rel(cat, fname)}"
            if mirror:
                files[f"{key}_mirror"] = f"{mirror}/{_rel(cat, fname)}"
        if not files:
            continue
        cascade[cat] = {
            "unique": len(buckets.get(cat, [])),
            "criterion": CASCADE_CRITERIA.get(cat, ""),
            "files": files,
        }
    if cascade:
        doc["cascade_categories"] = cascade

    top_name = "top100.txt"
    if os.path.exists(os.path.join(out_dir, top_name)):
        top_block: Dict[str, Any] = {
            "count": len(buckets.get("top", [])),
            "criterion": "verified configs sorted by median delay (<500ms first); never padded",
            "url": f"{primary}/{top_name}",
        }
        if mirror:
            top_block["url_mirror"] = f"{mirror}/{top_name}"
        doc["top100"] = top_block

    # تبلیغ و ارجاع به شاخه تفکیک کشوری Countries/
    countries_index = os.path.join(out_dir, countries.COUNTRIES_DIR, countries.INDEX_NAME)
    if os.path.exists(countries_index):
        rel = _rel(countries.COUNTRIES_DIR, countries.INDEX_NAME)
        cstats = buckets.get("stats", {}).get("countries") or {}
        countries_block: Dict[str, Any] = {
            "count": cstats.get("countries", 0),
            "configs": cstats.get("configs", 0),
            "source": "verified",
            "criterion": "verified configs grouped by the server's country (GeoIP); one .txt per country",
            "index": f"{primary}/{rel}",
        }
        if mirror:
            countries_block["index_mirror"] = f"{mirror}/{rel}"
        doc["countries"] = countries_block
    else:
        doc.pop("countries", None)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def _pct(part: int, whole: int) -> float:
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 2)


def run_pipeline(
    lines: Iterable[str],
    out_dir: str,
    rounds: Optional[int] = None,
    fast_ms: Optional[int] = None,
    top_n: Optional[int] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """اجرای چرخه کامل آبشار: L0/L1 -> L2 -> L3x3 -> سبدبندی Goodbaye -> کشورهای خروجی."""
    lines = list(lines)
    t_all = time.time()

    # فاز L0/L1: فیلترینگ ارزان بدون شبکه
    t = time.time()
    pre = filters.filter_lines(lines)
    l01_s = round(time.time() - t, 2)

    # فاز L2: تست سوکت همروند TCP
    t = time.time()
    l2 = reachability.check_lines(lines)
    l2_s = round(time.time() - t, 2)
    open_lines = l2["kept_open"]

    # فاز L3: آزمون حقیقی ترافیک پروکسی با xray-knife در ۳ دور مستقل
    t = time.time()
    rr = run_l3_round(open_lines, rounds=rounds, **kwargs)
    l3_s = round(time.time() - t, 2)

    # ساخت سبدهای نهایی با ریمارک ۵ خطی و پینگ واقعی زیر ۵۰۰ms
    buckets = build_buckets(rr, fast_ms=fast_ms, top_n=top_n)
    paths = write_buckets(out_dir, buckets)
    st = buckets["stats"]
    st["l2"] = l2["stats"]
    buckets["paths"] = paths

    # تفکیک کانفیگ‌های تأییدشده بر پایه کشور با جاروی اتمیک
    try:
        st["countries"] = countries.write_countries(out_dir, buckets["verified"])
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Countries/: {exc}", file=sys.stderr)
        st["countries"] = {"error": str(exc)}

    total_s = round(time.time() - t_all, 2)
    cascade = {
        "exit_country": exit_country(),
        "layers": {
            "l0_l1": {
                "in": pre["stats"]["input"],
                "out": pre["stats"]["kept"],
                "dropped": pre["dropped"],
                "endpoints_unique": pre["stats"]["endpoints_unique"],
                "dedup_saving_pct": pre["stats"]["dedup_saving_pct"],
                "seconds": l01_s,
            },
            "l2": {
                "in": pre["stats"]["kept"],
                "out": l2["stats"]["configs_open"],
                "open_pct": _pct(l2["stats"]["configs_open"], pre["stats"]["kept"]),
                "open_pct_of_raw_input": l2["stats"]["configs_open_pct"],
                "dns_failed": l2["stats"]["dns_failed"],
                "dns_seconds": l2["stats"]["dns_s"],
                "tcp_seconds": l2["stats"]["tcp_s"],
                "fd_before": l2["stats"]["fd_before"],
                "fd_after": l2["stats"]["fd_after"],
                "seconds": l2_s,
            },
            "l3": {
                "in": len(open_lines),
                "rounds": st["rounds"],
                "per_run_ok": st["per_run_ok"],
                "ever_ok": st["ever_ok"],
                "stable": st["stable"],
                "flaky_pct": st["flaky_pct"],
                "seconds": l3_s,
            },
        },
        "buckets": {
            "verified": st["verified"],
            "fast": st["fast"],
            "secure": st["secure"],
            "top": st["top"],
            "top_short_by": st["top_short_by"],
            "fast_threshold_ms": st["fast_threshold_ms"],
        },
        "total_seconds": total_s,
    }
    st["cascade"] = cascade
    health = merge_health(out_dir, cascade)
    if health:
        buckets["paths"]["health.json"] = health

    index = merge_index(out_dir, buckets)
    if index:
        buckets["paths"]["index.json"] = index

    return buckets


def _main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="Goodbaye Universal Standard Verification Cascade")
    ap.add_argument("input", help="فایل ورودی حاوی کانفیگ‌ها در هر خط")
    ap.add_argument("--out", default=".", help="پوشه خروجی انتشار")
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--fast-ms", type=int, default=None)
    ap.add_argument("--top-n", type=int, default=None)
    ap.add_argument("--json", default=None, help="ذخیره تلمتری به صورت JSON")
    args = ap.parse_args(argv)

    with open(args.input, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    res = run_pipeline(
        lines,
        args.out,
        rounds=args.rounds,
        fast_ms=args.fast_ms,
        top_n=args.top_n,
    )
    st = res["stats"]
    print(
        f"→ rounds={st['rounds']} per_run_ok={st['per_run_ok']} "
        f"ever_ok={st['ever_ok']} stable={st['stable']} flaky={st['flaky_pct']}%"
    )
    print(
        f"→ verified={st['verified']} fast(<{st['fast_threshold_ms']}ms)={st['fast']} "
        f"secure={st['secure']} top={st['top']}"
    )
    if st["top_short_by"]:
        print(f"⚠️ پکیج top100 به تعداد {st['top_short_by']} نود از حد نصاب کمتر بود و بدون پدینگ فیک منتشر شد.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
