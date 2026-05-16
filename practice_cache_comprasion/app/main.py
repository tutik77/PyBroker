import json
import os
import statistics
import threading
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2 import pool
import redis

CACHE_STRATEGY = os.getenv("CACHE_STRATEGY", "lazy")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "testdb")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
WRITEBACK_INTERVAL = int(os.getenv("WRITEBACK_INTERVAL", "5"))

app = FastAPI(title=f"Cache Demo ({CACHE_STRATEGY})")

r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
db_pool: pool.SimpleConnectionPool | None = None

metrics = {
    "db_reads": 0,
    "db_writes": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_requests": 0,
    "latencies": [],
}
metrics_lock = threading.Lock()

dirty_keys: set[int] = set()
dirty_lock = threading.Lock()


class ProductIn(BaseModel):
    name: str
    price: float
    quantity: int


def get_conn():
    return db_pool.getconn()


def put_conn(conn):
    db_pool.putconn(conn)


def init_db():
    global db_pool
    db_pool = pool.SimpleConnectionPool(
        1, 20,
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
    )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL
        )
    """)
    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        for i in range(1, 101):
            cur.execute(
                "INSERT INTO products (name, price, quantity) VALUES (%s, %s, %s)",
                (f"Product_{i}", round(10 + i * 0.5, 2), i * 10),
            )
    conn.commit()
    put_conn(conn)


def flush_dirty():
    with dirty_lock:
        keys = list(dirty_keys)
        dirty_keys.clear()
    if not keys:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    flushed = 0
    for key in keys:
        data = r.get(f"product:{key}")
        if data:
            p = json.loads(data)
            cur.execute(
                "UPDATE products SET name=%s, price=%s, quantity=%s WHERE id=%s",
                (p["name"], p["price"], p["quantity"], key),
            )
            with metrics_lock:
                metrics["db_writes"] += 1
            flushed += 1
    conn.commit()
    put_conn(conn)
    return flushed


def writeback_loop():
    while True:
        time.sleep(WRITEBACK_INTERVAL)
        flush_dirty()


@app.on_event("startup")
def startup():
    for attempt in range(30):
        try:
            init_db()
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Cannot connect to DB")

    if CACHE_STRATEGY == "write-back":
        t = threading.Thread(target=writeback_loop, daemon=True)
        t.start()

    print(f"[startup] strategy={CACHE_STRATEGY}")


@app.get("/products/{product_id}")
def read_product(product_id: int):
    start = time.time()

    cached = r.get(f"product:{product_id}")
    if cached:
        with metrics_lock:
            metrics["cache_hits"] += 1
            metrics["total_requests"] += 1
        result = json.loads(cached)
    else:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, price, quantity FROM products WHERE id = %s",
            (product_id,),
        )
        row = cur.fetchone()
        put_conn(conn)
        if not row:
            raise HTTPException(404, "Not found")
        result = {"id": row[0], "name": row[1], "price": row[2], "quantity": row[3]}
        r.set(f"product:{product_id}", json.dumps(result), ex=120)
        with metrics_lock:
            metrics["cache_misses"] += 1
            metrics["db_reads"] += 1
            metrics["total_requests"] += 1

    elapsed = time.time() - start
    with metrics_lock:
        metrics["latencies"].append(elapsed)
    return result


@app.put("/products/{product_id}")
def update_product(product_id: int, product: ProductIn):
    start = time.time()
    data = {
        "id": product_id,
        "name": product.name,
        "price": product.price,
        "quantity": product.quantity,
    }

    if CACHE_STRATEGY == "lazy":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE products SET name=%s, price=%s, quantity=%s WHERE id=%s",
            (product.name, product.price, product.quantity, product_id),
        )
        conn.commit()
        put_conn(conn)
        r.delete(f"product:{product_id}")
        with metrics_lock:
            metrics["db_writes"] += 1

    elif CACHE_STRATEGY == "write-through":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE products SET name=%s, price=%s, quantity=%s WHERE id=%s",
            (product.name, product.price, product.quantity, product_id),
        )
        conn.commit()
        put_conn(conn)
        r.set(f"product:{product_id}", json.dumps(data), ex=120)
        with metrics_lock:
            metrics["db_writes"] += 1

    elif CACHE_STRATEGY == "write-back":
        r.set(f"product:{product_id}", json.dumps(data), ex=300)
        with dirty_lock:
            dirty_keys.add(product_id)

    with metrics_lock:
        metrics["total_requests"] += 1

    elapsed = time.time() - start
    with metrics_lock:
        metrics["latencies"].append(elapsed)
    return data


@app.get("/metrics")
def get_metrics():
    with metrics_lock:
        total = metrics["cache_hits"] + metrics["cache_misses"]
        hit_rate = (metrics["cache_hits"] / total * 100) if total > 0 else 0
        avg_lat = (
            statistics.mean(metrics["latencies"]) if metrics["latencies"] else 0
        )
        throughput = (
            metrics["total_requests"] / sum(metrics["latencies"])
            if metrics["latencies"] and sum(metrics["latencies"]) > 0
            else 0
        )
        result = {
            "strategy": CACHE_STRATEGY,
            "total_requests": metrics["total_requests"],
            "cache_hits": metrics["cache_hits"],
            "cache_misses": metrics["cache_misses"],
            "hit_rate": round(hit_rate, 2),
            "db_reads": metrics["db_reads"],
            "db_writes": metrics["db_writes"],
            "avg_latency_ms": round(avg_lat * 1000, 2),
            "throughput": round(throughput, 2),
        }
    if CACHE_STRATEGY == "write-back":
        with dirty_lock:
            result["pending_writes"] = len(dirty_keys)
    return result


@app.post("/reset")
def reset_metrics():
    with metrics_lock:
        metrics["db_reads"] = 0
        metrics["db_writes"] = 0
        metrics["cache_hits"] = 0
        metrics["cache_misses"] = 0
        metrics["total_requests"] = 0
        metrics["latencies"] = []
    r.flushdb()
    return {"status": "ok"}


@app.post("/flush")
def flush_writeback():
    if CACHE_STRATEGY == "write-back":
        n = flush_dirty()
        return {"flushed": n}
    return {"flushed": 0}
