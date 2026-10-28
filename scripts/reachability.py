#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/reachability.py — لایهٔ L2: سنجشِ دسترسی‌پذیریِ TCP با همروندی ۸۰۰ سوکت.
برند: @Goodbaye_filtering | مخزن: ai-driven-v2ray

اصلاحات کلیدی:
  • حل باگ ۳: پروتکل‌های مبتنی بر UDP (مانند WireGuard, Hysteria2, TUIC) تست TCP را دور می‌زنند
    تا اشتباهاً حذف نشوند و مستقیماً به آزمون واقعی L3 برسند.
  • مهار نشت سوکت لینوکس (F-13) و ایزولاسیون کامل تایم‌اوت DNS.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONCURRENCY = int(os.environ.get("L2_CONCURRENCY", "800"))
TCP_TIMEOUT = float(os.environ.get("L2_TCP_TIMEOUT", "3"))
DNS_WORKERS = int(os.environ.get("L2_DNS_WORKERS", "64"))
DNS_TIMEOUT = float(os.environ.get("L2_DNS_TIMEOUT", "4"))
ADDR_CAP = int(os.environ.get("L2_ADDR_CAP", "3"))
_FD_HEADROOM = 200

ERR_TIMEOUT = "timeout"
ERR_REFUSED = "refused"
ERR_UNREACHABLE = "unreachable"
ERR_DNS = "dns_failed"
ERR_EMFILE = "emfile"
ERR_OTHER = "other"
ALL_ERRORS = (ERR_TIMEOUT, ERR_REFUSED, ERR_UNREACHABLE, ERR_DNS, ERR_EMFILE, ERR_OTHER)

# پروتکل‌هایی که بر بستر UDP کار می‌کنند و تست TCP نباید آنها را فیلتر کند
UDP_SCHEMES = frozenset({
    "hysteria", "hysteria2", "hy", "hy2", "tuic", "wireguard", "wg", "warp"
})


class FileDescriptorExhaustion(RuntimeError):
    """کمبود یا نشت سوکت در سیستم‌عامل رخ داده است."""


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip().strip("[]"))
        return True
    except ValueError:
        return False


def _resolve_one(host: str) -> Tuple[str, Tuple[str, ...]]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except Exception:
        return host, ()
    return host, tuple(sorted({i[4][0] for i in infos}))


def resolve_hosts(hosts: Iterable[str]) -> Tuple[Dict[str, Tuple[str, ...]], float]:
    out: Dict[str, Tuple[str, ...]] = {}
    named: List[str] = []
    for h in hosts:
        h = (h or "").strip()
        if not h:
            continue
        if _is_ip(h):
            out[h] = (h.strip("[]"),)
        else:
            named.append(h)

    t0 = time.monotonic()
    if named:
        named = sorted(set(named))
        prev = socket.getdefaulttimeout()
        socket.setdefaulttimeout(DNS_TIMEOUT)
        try:
            with ThreadPoolExecutor(max_workers=max(1, DNS_WORKERS)) as ex:
                for h, addrs in ex.map(_resolve_one, named):
                    out[h] = addrs
        finally:
            socket.setdefaulttimeout(prev)
    return out, time.monotonic() - t0


def fd_count() -> int:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return -1


def socket_fd_count() -> int:
    try:
        names = os.listdir("/proc/self/fd")
    except OSError:
        return -1
    n = 0
    for name in names:
        try:
            if os.readlink(f"/proc/self/fd/{name}").startswith("socket:"):
                n += 1
        except OSError:
            continue
    return n


async def _probe(ip: str, port: int, sem: asyncio.Semaphore,
                 timeout: float, tally: Dict[str, int]) -> Optional[int]:
    async with sem:
        t0 = time.monotonic()
        writer = None
        try:
            conn = asyncio.open_connection(ip, port)
            _, writer = await asyncio.wait_for(conn, timeout=timeout)
            return int((time.monotonic() - t0) * 1000)
        except asyncio.TimeoutError:
            tally[ERR_TIMEOUT] += 1
        except OSError as exc:
            errno = getattr(exc, "errno", None)
            if errno == 24:
                tally[ERR_EMFILE] += 1
            elif errno == 111:
                tally[ERR_REFUSED] += 1
            elif errno in (101, 113):
                tally[ERR_UNREACHABLE] += 1
            else:
                tally[ERR_OTHER] += 1
        except Exception:  # noqa: BLE001
            tally[ERR_OTHER] += 1
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:  # noqa: BLE001
                    pass
        return None


async def _probe_endpoint(addrs: Sequence[str], port: int,
                          sem: asyncio.Semaphore, timeout: float,
                          tally: Dict[str, int]) -> Optional[int]:
    results = await asyncio.gather(*[
        _probe(ip, port, sem, timeout, tally)
        for ip in addrs[:max(1, ADDR_CAP)]
    ])
    ok = [r for r in results if r is not None]
    return min(ok) if ok else None


async def _run_tcp(targets: Sequence[Tuple[Tuple[str, int], Tuple[str, ...]]],
                   conc: int, timeout: float,
                   tally: Dict[str, int]) -> List[Optional[int]]:
    sem = asyncio.Semaphore(conc)
    return list(await asyncio.gather(*[
        _probe_endpoint(addrs, port, sem, timeout, tally)
        for (_host, port), addrs in targets
    ]))


def check_endpoints(endpoints: Sequence[Tuple[str, int]],
                    concurrency: Optional[int] = None,
                    timeout: Optional[float] = None) -> Dict[str, Any]:
    conc = int(concurrency or CONCURRENCY)
    tmo = float(timeout or TCP_TIMEOUT)

    eps = [(str(h).strip().strip("[]"), int(p)) for h, p in endpoints]
    fd_before = fd_count()
    sock_before = socket_fd_count()

    addrs, dns_s = resolve_hosts({h for h, _ in eps})

    targets = [(ep, addrs.get(ep[0], ())) for ep in eps]
    resolvable = [(ep, a) for ep, a in targets if a]
    tally = {k: 0 for k in ALL_ERRORS}
    tally[ERR_DNS] = sum(1 for _ep, a in targets if not a)

    t0 = time.monotonic()
    delays = asyncio.run(_run_tcp(resolvable, conc, tmo, tally))
    tcp_s = time.monotonic() - t0
    fd_after = fd_count()
    sock_after = socket_fd_count()

    open_map: Dict[Tuple[str, int], int] = {}
    for (ep, _a), d in zip(resolvable, delays):
        if d is not None:
            open_map[ep] = d
    closed = [ep for ep in eps if ep not in open_map]

    probes = sum(min(max(1, ADDR_CAP), len(a)) for _ep, a in resolvable)
    res: Dict[str, Any] = {
        "open": open_map,
        "closed": closed,
        "addrs": addrs,
        "errors": tally,
        "stats": {
            "endpoints": len(eps),
            "hosts": len({h for h, _ in eps}),
            "dns_failed": tally[ERR_DNS],
            "probes": probes,
            "open": len(open_map),
            "closed": len(closed),
            "open_pct": round(100.0 * len(open_map) / len(eps), 2) if eps else 0.0,
            "concurrency": conc,
            "tcp_timeout": tmo,
            "addr_cap": max(1, ADDR_CAP),
            "dns_s": round(dns_s, 2),
            "tcp_s": round(tcp_s, 2),
            "fd_before": fd_before,
            "fd_after": fd_after,
            "sock_before": sock_before,
            "sock_after": sock_after,
        },
    }

    if tally[ERR_EMFILE]:
        raise FileDescriptorExhaustion(
            f"{tally[ERR_EMFILE]} EMFILE errors at concurrency={conc}; measurement is void."
        )

    if sock_before >= 0 and sock_after > sock_before:
        raise FileDescriptorExhaustion(
            f"socket leak: {sock_after - sock_before} socket descriptor(s) still open."
        )

    return res


def headroom_warning(concurrency: Optional[int] = None) -> Optional[str]:
    conc = int(concurrency or CONCURRENCY)
    try:
        import resource
        soft = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except Exception:  # noqa: BLE001
        soft = -1
    if soft > 0 and conc + _FD_HEADROOM > soft:
        return f"concurrency={conc} leaves less than {_FD_HEADROOM} spare descriptors under {soft}"
    return None


def is_udp_protocol(line: str) -> bool:
    """تشخیص پروتکل‌های مبتنی بر UDP (برای حل باگ ۳)."""
    s = (line or "").strip().lower()
    scheme = s.split("://", 1)[0] if "://" in s else ""
    return scheme in UDP_SCHEMES


def check_lines(lines: Iterable[str]) -> Dict[str, Any]:
    """
    اجرای L0/L1 + L2 با بای‌پاس هوشمند پروتکل‌های UDP (WireGuard, Hy2, TUIC).
    """
    import filters

    pre = filters.filter_lines(lines)

    # تفکیک کانفیگ‌های UDP از TCP: کانفیگ‌های UDP مستقیماً عبور داده می‌شوند
    tcp_endpoints: List[Tuple[str, int]] = []
    tcp_lines_idx: set = set()
    udp_lines: List[str] = []
    udp_delays: List[int] = []

    for idx, line in enumerate(pre["kept"]):
        if is_udp_protocol(line):
            udp_lines.append(line)
            udp_delays.append(100)  # مقدار پیش‌فرض پینگ تا تست در L3
        else:
            tcp_lines_idx.add(idx)

    for ep, idxs in pre["ep_to_lines"].items():
        if any(i in tcp_lines_idx for i in idxs):
            tcp_endpoints.append(ep)

    res = check_endpoints(tcp_endpoints)

    kept_open: List[str] = []
    line_delay: List[int] = []

    # افزودن کانفیگ‌های TCP که پورت آنها باز بود
    for ep, idxs in pre["ep_to_lines"].items():
        if ep in res["open"]:
            for i in idxs:
                if i in tcp_lines_idx:
                    kept_open.append(pre["kept"][i])
                    line_delay.append(res["open"][ep])

    # افزودن تمام کانفیگ‌های UDP که آزمون TCP را دور زدند (حل باگ ۳)
    kept_open.extend(udp_lines)
    line_delay.extend(udp_delays)

    res["kept_open"] = kept_open
    res["line_delay"] = line_delay
    res["filter"] = pre["stats"]
    res["stats"]["configs_in"] = pre["stats"]["input"]
    res["stats"]["configs_open"] = len(kept_open)
    res["stats"]["udp_bypassed"] = len(udp_lines)
    res["stats"]["configs_open_pct"] = (
        round(100.0 * len(kept_open) / pre["stats"]["input"], 2)
        if pre["stats"]["input"] else 0.0
    )
    return res


def check_file(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return check_lines(fh)


def _main(argv: Sequence[str]) -> int:
    import json
    path = argv[1] if len(argv) > 1 else "all/configs.txt"

    warn = headroom_warning()
    if warn:
        print(f"# warning: {warn}", file=sys.stderr)

    try:
        res = check_file(path)
    except FileDescriptorExhaustion as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "stats": res["stats"],
        "errors": res["errors"],
        "filter": res["filter"]
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
