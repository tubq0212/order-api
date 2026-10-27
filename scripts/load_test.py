"""Simple standard-library HTTP load check for the running order service."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def one_request(url: str, timeout: float) -> dict:
    started = time.perf_counter()
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout) as response:
            response.read()
            status = response.status
        return {"status": status, "latency_ms": (time.perf_counter() - started) * 1000, "error": None}
    except HTTPError as exc:
        return {"status": exc.code, "latency_ms": (time.perf_counter() - started) * 1000, "error": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": None, "latency_ms": (time.perf_counter() - started) * 1000, "error": type(exc).__name__}


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a repeatable HTTP load check.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--path", default="/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests 和 concurrency 必须大于 0")

    url = args.base_url.rstrip("/") + "/" + args.path.lstrip("/")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: one_request(url, args.timeout), range(args.requests)))
    elapsed = time.perf_counter() - started
    latencies = [item["latency_ms"] for item in results]
    successful = sum(200 <= item["status"] < 300 for item in results if item["status"] is not None)
    status_counts = {}
    for item in results:
        key = str(item["status"]) if item["status"] is not None else "network_error"
        status_counts[key] = status_counts.get(key, 0) + 1
    report = {
        "url": url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 4),
        "throughput_rps": round(args.requests / elapsed, 2) if elapsed else 0,
        "success_rate": round(successful / args.requests, 4),
        "status_counts": status_counts,
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if successful == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
