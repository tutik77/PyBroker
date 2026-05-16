"""
Нагрузочный генератор для тестирования стратегий кеширования.
Запуск: python load_generator.py [base_url]
"""

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
NUM_REQUESTS = 1000
CONCURRENCY = 10
PRODUCT_IDS = list(range(1, 101))


def single_request(is_read: bool):
    pid = random.choice(PRODUCT_IDS)
    start = time.time()
    try:
        if is_read:
            resp = requests.get(f"{BASE_URL}/products/{pid}", timeout=10)
        else:
            resp = requests.put(
                f"{BASE_URL}/products/{pid}",
                json={
                    "name": f"Upd_{pid}_{random.randint(1,9999)}",
                    "price": round(random.uniform(5, 200), 2),
                    "quantity": random.randint(1, 500),
                },
                timeout=10,
            )
        ok = resp.status_code in (200, 201)
    except Exception:
        ok = False
    return time.time() - start, ok


def run_test(name: str, read_pct: int):
    write_pct = 100 - read_pct
    print(f"\n{'='*60}")
    print(f"  Test: {name}  (read {read_pct}% / write {write_pct}%)")
    print(f"{'='*60}")

    requests.post(f"{BASE_URL}/reset", timeout=10)
    time.sleep(1)

    latencies = []
    errors = 0
    wall_start = time.time()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = []
        for _ in range(NUM_REQUESTS):
            is_read = random.randint(1, 100) <= read_pct
            futures.append(pool.submit(single_request, is_read))

        for f in as_completed(futures):
            lat, ok = f.result()
            latencies.append(lat)
            if not ok:
                errors += 1

    wall_time = time.time() - wall_start

    time.sleep(7)

    m = requests.get(f"{BASE_URL}/metrics", timeout=10).json()

    throughput = NUM_REQUESTS / wall_time
    avg_lat = sum(latencies) / len(latencies) * 1000

    print(f"  Strategy:            {m['strategy']}")
    print(f"  Requests:            {NUM_REQUESTS}")
    print(f"  Errors:              {errors}")
    print(f"  Throughput:          {throughput:.2f} req/sec")
    print(f"  Avg Latency:         {avg_lat:.2f} ms")
    print(f"  Cache hits:          {m['cache_hits']}")
    print(f"  Cache misses:        {m['cache_misses']}")
    print(f"  Hit rate:            {m['hit_rate']}%")
    print(f"  DB reads:            {m['db_reads']}")
    print(f"  DB writes:           {m['db_writes']}")
    if "pending_writes" in m:
        print(f"  Pending writes:      {m['pending_writes']}")

    return {
        "test": name,
        "strategy": m["strategy"],
        "throughput": round(throughput, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "cache_hits": m["cache_hits"],
        "cache_misses": m["cache_misses"],
        "hit_rate": m["hit_rate"],
        "db_reads": m["db_reads"],
        "db_writes": m["db_writes"],
    }


def main():
    results = []
    results.append(run_test("Read-Heavy (80/20)", 80))
    results.append(run_test("Balanced (50/50)", 50))
    results.append(run_test("Write-Heavy (20/80)", 20))

    print(f"\n{'='*60}")
    print("  ИТОГО (JSON)")
    print(f"{'='*60}")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    out_file = os.getenv("RESULTS_FILE", "")
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    return results


if __name__ == "__main__":
    main()
