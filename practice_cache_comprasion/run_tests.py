"""
Оркестратор: последовательно запускает приложение с каждой стратегией кеширования,
прогоняет нагрузочные тесты и выводит сводную таблицу.

Использование:
  cd practice_cache_comprasion
  python run_tests.py
"""

import json
import os
import subprocess
import sys
import time

STRATEGIES = ["lazy", "write-through", "write-back"]
COMPOSE = "docker-compose"
BASE_URL = "http://localhost:8000"


def run(cmd: str, check=True, **kw):
    print(f"  > {cmd}")
    return subprocess.run(cmd, shell=True, check=check, **kw)


def wait_for_app(timeout=60):
    """Ждём, пока приложение ответит."""
    import requests

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/metrics", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    all_results = {}

    print("\n[build] Building Docker images...")
    run(f"{COMPOSE} build")

    for strategy in STRATEGIES:
        print(f"\n{'#'*60}")
        print(f"  STRATEGY: {strategy}")
        print(f"{'#'*60}")

        run(f"{COMPOSE} down -v", check=False, capture_output=True)
        time.sleep(2)

        env = {**os.environ, "CACHE_STRATEGY": strategy}
        run(f"{COMPOSE} up -d", **{"env": env})

        print("  Waiting for application to be ready...")
        if not wait_for_app():
            print("  [!] Application did not start, skipping.")
            continue

        print("  Running load tests...")
        result_file = os.path.abspath(f"results_{strategy}.json")
        env_gen = {**os.environ, "RESULTS_FILE": result_file}
        result = subprocess.run(
            [sys.executable, "load_generator.py", BASE_URL],
            capture_output=True, env=env_gen,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        print(stdout)
        if stderr:
            print(stderr[-500:])

        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_results[strategy] = data
        except Exception as e:
            print(f"  [!] Could not read results: {e}")

        run(f"{COMPOSE} down -v", check=False, capture_output=True)
        time.sleep(2)

    print(f"\n{'='*80}")
    print("  SUMMARY TABLE")
    print(f"{'='*80}")

    header = f"{'Strategy':<16} {'Test':<22} {'req/s':>8} {'Latency':>10} {'Hits':>6} {'Miss':>6} {'Hit%':>7} {'DB R':>6} {'DB W':>6}"
    print(header)
    print("-" * len(header))

    for strategy, tests in all_results.items():
        for t in tests:
            print(
                f"{t['strategy']:<16} {t['test']:<22} {t['throughput']:>8.1f} "
                f"{t['avg_latency_ms']:>8.2f}ms {t['cache_hits']:>6} {t['cache_misses']:>6} "
                f"{t['hit_rate']:>6.1f}% {t['db_reads']:>6} {t['db_writes']:>6}"
            )

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print("\nResults saved to results.json")


if __name__ == "__main__":
    main()
