#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/realtest.py — لایهٔ L3: آزمونِ واقعیِ عبور ترافیک با هسته پروکسی (xray-knife).
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

ویژگی‌ها و گاردها:
  • پذیرش هوشمندانه semi-passed (موفقیت پروکسی با خطای جست‌وجوی IP)
  • قفل ۴ شرطی ضد باگ: total >= 1 و success == total و 200 <= code < 400
  • دفاع سه‌لایه در برابر قفل شدن CI (بررسی ناتهی بودن فایل، stdin=DEVNULL، تایم‌اوت سخت)
  • حذف فایل‌های کهنه قبل از اجرا جهت جلوگیری از داده‌های منسوخ
  • تجزیه استاندارد CSV با کتابخانه داخلی csv جهت حفظ لینک‌های کامادار
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

XK_BIN = os.environ.get("L3_XK_BIN", "xray-knife")
TEST_URL = os.environ.get("L3_TEST_URL", "https://cp.cloudflare.com/generate_204")
THREADS = int(os.environ.get("L3_THREADS", "200"))
MDELAY_MS = int(os.environ.get("L3_MDELAY", "5000"))
TIMEOUT_MS = int(os.environ.get("L3_TIMEOUT", "5000"))
HARD_TIMEOUT = int(os.environ.get("L3_HARD_TIMEOUT", "600"))

STATUS_PASSED = "passed"
STATUS_SEMI = "semi-passed"
STATUS_FAILED = "failed"
STATUS_BROKEN = "broken"

OK_STATUSES = (STATUS_PASSED, STATUS_SEMI)
ALL_STATUSES = (STATUS_PASSED, STATUS_SEMI, STATUS_FAILED, STATUS_BROKEN)

CSV_COLUMNS = (
    "link", "status", "reason", "tls", "ip", "delay", "code", "download",
    "upload", "location", "ttfb", "connect_time", "success", "total",
    "endpoints",
)

NULL_TOKEN = "null"
CODE_MIN_OK = 200
CODE_MAX_OK = 400


class XrayKnifeMissing(RuntimeError):
    """باینری xray-knife در مسیر سیستم یافت نشد."""


class XrayKnifeFailed(RuntimeError):
    """اجرای ابزار xray-knife با کد خروج ناصفر مواجه شد."""


class EmptyInput(ValueError):
    """فایل ورودی تهی یا ناموجود است."""


class OutputNotWritten(RuntimeError):
    """ابزار بدون خطا خارج شد اما هیچ فایل خروجی ننوشت."""


class MalformedCsv(ValueError):
    """ساختار ستون‌های CSV با قرارداد ۱۵ ستونی سازگار نیست."""


def _as_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = value.strip()
    if not text or text == NULL_TOKEN:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def is_row_genuinely_ok(row: Dict[str, str]) -> bool:
    """قفل ۴ شرطی اثبات کارکرد واقعی پروکسی."""
    if (row.get("status") or "").strip() not in OK_STATUSES:
        return False
    total = _as_int(row.get("total"))
    success = _as_int(row.get("success"))
    code = _as_int(row.get("code"))
    if total is None or success is None or code is None:
        return False
    if total < 1 or success != total:
        return False
    return CODE_MIN_OK <= code < CODE_MAX_OK


def row_delay_ms(row: Dict[str, str]) -> Optional[int]:
    delay = _as_int(row.get("delay"))
    if delay is None or delay < 0:
        return None
    return delay


def row_location(row: Dict[str, str]) -> Optional[str]:
    loc = (row.get("location") or "").strip()
    if not loc or loc == NULL_TOKEN:
        return None
    return loc


def row_tls(row: Dict[str, str]) -> str:
    return (row.get("tls") or "").strip()


def parse_csv(text: str) -> List[Dict[str, str]]:
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(reader.fieldnames or ())
    if header != CSV_COLUMNS:
        raise MalformedCsv(
            f"CSV header mismatch:\n  expected: {CSV_COLUMNS}\n  actual: {header}"
        )
    rows: List[Dict[str, str]] = []
    for raw in reader:
        if raw.get(None) is not None:
            raise MalformedCsv(f"Extra fields in row: {raw.get(None)!r}")
        if any(value is None for value in raw.values()):
            raise MalformedCsv(f"Short row: {raw!r}")
        rows.append({key: (value or "") for key, value in raw.items()})
    return rows


def classify(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    ok: List[str] = []
    failed: List[str] = []
    broken: List[str] = []
    by_status: Dict[str, int] = {name: 0 for name in ALL_STATUSES}
    unknown_status: Dict[str, int] = {}
    by_link: Dict[str, Dict[str, str]] = {}

    for row in rows:
        link = row.get("link") or ""
        by_link[link] = row
        status = (row.get("status") or "").strip()
        if status in by_status:
            by_status[status] += 1
        else:
            unknown_status[status] = unknown_status.get(status, 0) + 1
        if is_row_genuinely_ok(row):
            ok.append(link)
        elif status == STATUS_BROKEN:
            broken.append(link)
        else:
            failed.append(link)

    delays = [row_delay_ms(by_link[link]) for link in ok]
    delays = sorted(d for d in delays if d is not None)
    stats: Dict[str, Any] = {
        "rows": len(rows),
        "ok": len(ok),
        "failed": len(failed),
        "broken": len(broken),
        "ok_pct": round(100.0 * len(ok) / len(rows), 2) if rows else 0.0,
        "by_status": by_status,
        "with_location": sum(1 for link in ok if row_location(by_link[link])),
        "delay_min": delays[0] if delays else None,
        "delay_median": delays[len(delays) // 2] if delays else None,
        "delay_max": delays[-1] if delays else None,
    }
    if unknown_status:
        stats["unknown_status"] = unknown_status
    return {"ok": ok, "failed": failed, "broken": broken, "rows": by_link, "stats": stats}


def resolve_binary(binary: Optional[str] = None) -> str:
    name = binary or XK_BIN
    if os.path.sep in name:
        if os.path.isfile(name) and os.access(name, os.X_OK):
            return os.path.abspath(name)
        raise XrayKnifeMissing(f"xray-knife is not an executable file at {name!r}")
    found = shutil.which(name)
    if not found:
        # جست‌وجو در مسیرهای متداول رانر
        for cand in (f"{os.environ.get('HOME', '')}/.local/bin/{name}", f"/usr/local/bin/{name}"):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        raise XrayKnifeMissing(f"xray-knife ({name!r}) is not on PATH.")
    return found


def _non_blank_count(path: str) -> int:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def build_argv(in_path: str, out_path: str, *,
               binary: str,
               test_url: Optional[str] = None,
               threads: Optional[int] = None,
               mdelay_ms: Optional[int] = None,
               timeout_ms: Optional[int] = None,
               max_passed: int = 0,
               retries: int = 0) -> List[str]:
    argv = [
        binary, "http",
        "-f", in_path,
        "-x", "csv",
        "-o", out_path,
        "-t", str(int(threads if threads is not None else THREADS)),
        "-d", str(int(mdelay_ms if mdelay_ms is not None else MDELAY_MS)),
        "--timeout", str(int(timeout_ms if timeout_ms is not None else TIMEOUT_MS)),
        "-u", test_url if test_url is not None else TEST_URL,
    ]
    if max_passed:
        argv += ["--max-passed", str(int(max_passed))]
    if retries:
        argv += ["--retries", str(int(retries))]
    return argv


def run_test(in_path: str, *,
             out_path: Optional[str] = None,
             binary: Optional[str] = None,
             test_url: Optional[str] = None,
             threads: Optional[int] = None,
             mdelay_ms: Optional[int] = None,
             timeout_ms: Optional[int] = None,
             max_passed: int = 0,
             retries: int = 0,
             hard_timeout: Optional[int] = None) -> Dict[str, Any]:
    if not os.path.isfile(in_path):
        raise EmptyInput(f"input file does not exist: {in_path!r}")
    n_lines = _non_blank_count(in_path)
    if n_lines == 0:
        raise EmptyInput(f"input file has no non-blank line: {in_path!r}")

    resolved = resolve_binary(binary)
    owned = out_path is None
    if owned:
        handle, out_path = tempfile.mkstemp(prefix="l3_", suffix=".csv")
        os.close(handle)
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)

    try:
        argv = build_argv(in_path, out_path, binary=resolved,
                          test_url=test_url, threads=threads,
                          mdelay_ms=mdelay_ms, timeout_ms=timeout_ms,
                          max_passed=max_passed, retries=retries)
        limit = int(hard_timeout if hard_timeout is not None else HARD_TIMEOUT)
        started = time.time()
        try:
            proc = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=limit,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise XrayKnifeFailed(f"xray-knife timed out after {limit}s.") from exc

        elapsed = round(time.time() - started, 2)
        output = (proc.stdout or b"").decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise XrayKnifeFailed(f"xray-knife exited {proc.returncode}.\n--- output ---\n{output[-2000:]}")

        if not os.path.isfile(out_path):
            raise OutputNotWritten(f"xray-knife wrote no file at {out_path!r}.\n--- output ---\n{output[-2000:]}")

        with open(out_path, encoding="utf-8", errors="replace") as handle:
            result = classify(parse_csv(handle.read()))

        unique_in = _unique_links(in_path)
        result["partial"] = len(result["rows"]) < len(unique_in)
        result["stats"]["elapsed_sec"] = elapsed
        result["stats"]["lines_in"] = n_lines
        result["stats"]["unique_in"] = len(unique_in)
        result["stats"]["test_url"] = (test_url if test_url is not None else TEST_URL)
        result["stats"]["threads"] = int(threads if threads is not None else THREADS)
        result["out_path"] = out_path
        return result
    finally:
        if owned:
            try:
                os.remove(out_path)
            except OSError:
                pass


def _unique_links(path: str) -> List[str]:
    seen: Dict[str, None] = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if text:
                seen.setdefault(text, None)
    return list(seen)


def test_lines(lines: Iterable[str], **kwargs: Any) -> Dict[str, Any]:
    handle, path = tempfile.mkstemp(prefix="l3_in_", suffix=".txt")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            for line in lines:
                text = line.strip()
                if text:
                    out.write(text + "\n")
        return run_test(path, **kwargs)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_file(path: str, **kwargs: Any) -> Dict[str, Any]:
    return run_test(path, **kwargs)


def _main(argv: Sequence[str]) -> int:
    import json
    if len(argv) < 2:
        print(f"usage: {os.path.basename(argv[0])} <configs.txt> [out.csv]", file=sys.stderr)
        return 64
    in_path = argv[1]
    out_path = argv[2] if len(argv) > 2 else None

    try:
        result = test_file(in_path, out_path=out_path)
    except (XrayKnifeMissing, EmptyInput) as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2
    except (XrayKnifeFailed, OutputNotWritten, MalformedCsv) as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 3

    payload = {"stats": result["stats"], "partial": result["partial"]}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
