#!/usr/bin/env python3
"""Zero-dependency local HTTP & command benchmark harness for perf-issue.

Measures p50/p95/p99/max latency, throughput, and error rate with TCP dial-time
subtraction on persistent HTTP/1.1 keep-alive connections (inspired by mload).
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import subprocess
import sys
import threading
import time
import urllib.parse

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(math.ceil((pct / 100.0) * len(sorted_vals))) - 1))
    return sorted_vals[idx]


def run_http_bench(url: str, concurrency: int, duration_s: float, gzip: bool, warmup_s: float) -> dict:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = {"Connection": "keep-alive"}
    if gzip:
        headers["Accept-Encoding"] = "gzip"

    stop_at = time.monotonic() + warmup_s + duration_s
    record_after = time.monotonic() + warmup_s
    lock = threading.Lock()
    latencies_ms: list[float] = []
    errors = 0
    total = 0

    def worker() -> None:
        nonlocal errors, total
        local_lats: list[float] = []
        local_err = 0
        local_tot = 0
        conn: http.client.HTTPConnection | None = None
        while time.monotonic() < stop_at:
            now = time.monotonic()
            try:
                if conn is None:
                    conn = http.client.HTTPConnection(host, port, timeout=5.0)
                    conn.connect()
                t0 = time.perf_counter()
                conn.request("GET", path, headers=headers)
                resp = conn.getresponse()
                resp.read()
                dt_ms = (time.perf_counter() - t0) * 1000.0
                if now >= record_after:
                    local_tot += 1
                    if resp.status >= 400:
                        local_err += 1
                    else:
                        local_lats.append(dt_ms)
            except OSError:
                if conn is not None:
                    conn.close()
                    conn = None
                if now >= record_after:
                    local_tot += 1
                    local_err += 1
        if conn is not None:
            conn.close()
        with lock:
            latencies_ms.extend(local_lats)
            errors += local_err
            total += local_tot

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    latencies_ms.sort()
    rps = round(total / max(duration_s, 1e-6), 1)
    return {
        "mode": "http",
        "url": url,
        "concurrency": concurrency,
        "duration_s": duration_s,
        "requests": total,
        "errors": errors,
        "rps": rps,
        "p50_ms": round(percentile(latencies_ms, 50), 3),
        "p95_ms": round(percentile(latencies_ms, 95), 3),
        "p99_ms": round(percentile(latencies_ms, 99), 3),
        "max_ms": round(latencies_ms[-1], 3) if latencies_ms else 0.0,
    }


def run_cmd_bench(cmd: list[str], runs: int, warmup: int) -> dict:
    for _ in range(warmup):
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=NO_WINDOW,
        )
    times_ms: list[float] = []
    errors = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=NO_WINDOW,
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        times_ms.append(dt_ms)
        if proc.returncode != 0:
            errors += 1
    times_ms.sort()
    return {
        "mode": "cmd",
        "runs": runs,
        "errors": errors,
        "min_ms": round(times_ms[0], 3) if times_ms else 0.0,
        "p50_ms": round(percentile(times_ms, 50), 3),
        "p95_ms": round(percentile(times_ms, 95), 3),
        "max_ms": round(times_ms[-1], 3) if times_ms else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local HTTP and command benchmark harness.")
    sub = parser.add_subparsers(dest="subcmd", required=True)

    http_p = sub.add_parser("http", help="Benchmark an HTTP endpoint with persistent keep-alive.")
    http_p.add_argument("--url", required=True)
    http_p.add_argument("--concurrency", type=int, default=16)
    http_p.add_argument("--duration", type=float, default=3.0)
    http_p.add_argument("--warmup", type=float, default=0.5)
    http_p.add_argument("--gzip", action="store_true")
    http_p.add_argument("--json", action="store_true")

    cmd_p = sub.add_parser("cmd", help="Benchmark a CLI command across repeated runs.")
    cmd_p.add_argument("--runs", type=int, default=10)
    cmd_p.add_argument("--warmup", type=int, default=2)
    cmd_p.add_argument("--json", action="store_true")
    cmd_p.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.subcmd == "http":
        res = run_http_bench(args.url, args.concurrency, args.duration, args.gzip, args.warmup)
    else:
        cmd = list(args.command)
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        if not cmd:
            parser.error("cmd requires a command after --")
        res = run_cmd_bench(cmd, args.runs, args.warmup)

    if args.json:
        print(json.dumps(res, indent=2))
    elif res["mode"] == "http":
        print(
            f"HTTP {res['url']} c={res['concurrency']} rps={res['rps']} "
            f"p50={res['p50_ms']}ms p95={res['p95_ms']}ms p99={res['p99_ms']}ms "
            f"max={res['max_ms']}ms errors={res['errors']}/{res['requests']}"
        )
    else:
        print(
            f"CMD runs={res['runs']} min={res['min_ms']}ms p50={res['p50_ms']}ms "
            f"p95={res['p95_ms']}ms max={res['max_ms']}ms errors={res['errors']}"
        )
    return 1 if res["errors"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
