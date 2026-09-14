"""Cache-aside eval: miss/hit latency, invalidate, stampede-safe fill."""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import urllib.request

from werkzeug.serving import make_server

import app as cache_app
from evals.common import Check, cleanup_prefix, redis_client


def run() -> list[Check]:
    checks: list[Check] = []
    client = cache_app.app.test_client()
    r = redis_client()
    cleanup_prefix(r, "cache")

    health = client.get("/health")
    body = health.get_json()
    checks.append(Check(
        "health_connected",
        health.status_code == 200 and body.get("redis") == "connected",
        str(body),
    ))

    user_id = 9101
    t0 = time.perf_counter()
    miss = client.get(f"/users/{user_id}").get_json()
    miss_s = time.perf_counter() - t0
    checks.append(Check(
        "first_request_is_cache_miss",
        miss.get("source") == "database" and miss_s >= 1.8,
        f"source={miss.get('source')} elapsed={miss_s:.3f}s",
        miss_s * 1000,
    ))

    t0 = time.perf_counter()
    hit = client.get(f"/users/{user_id}").get_json()
    hit_s = time.perf_counter() - t0
    checks.append(Check(
        "second_request_is_cache_hit",
        hit.get("source") == "cache" and hit_s < 0.25,
        f"source={hit.get('source')} elapsed={hit_s:.4f}s",
        hit_s * 1000,
    ))
    checks.append(Check(
        "hit_much_faster_than_miss",
        hit_s < miss_s / 5,
        f"miss={miss_s:.3f}s hit={hit_s:.4f}s ratio={miss_s / max(hit_s, 1e-6):.0f}x",
    ))

    deleted = client.delete(f"/cache/users/{user_id}").get_json()
    again = client.get(f"/users/{user_id}").get_json()
    checks.append(Check(
        "invalidate_then_miss",
        deleted.get("invalidated") is True and again.get("source") == "database",
        f"invalidated={deleted.get('invalidated')} source={again.get('source')}",
    ))

    stampede_id = 9102
    cleanup_prefix(r, "cache")

    # Flask's test_client is not thread-safe; a real threaded WSGI server is.
    server = make_server("127.0.0.1", 0, cache_app.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/users/{stampede_id}"

    def fetch():
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode())

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: fetch(), range(8)))
    finally:
        server.shutdown()

    generated = {row["data"]["generated_at"] for row in results}
    db_fills = sum(1 for row in results if row.get("source") == "database")
    checks.append(Check(
        "stampede_single_fill",
        len(generated) == 1 and db_fills <= 2,
        f"unique generated_at={len(generated)} database_source={db_fills}",
        extra={"generated_at": list(generated), "db_fills": db_fills},
    ))

    cache_app.clear_l1()
    user_id = 9103
    client.get(f"/users/{user_id}")
    l1 = client.get(f"/cache/l1/{user_id}").get_json()
    checks.append(Check(
        "l1_populated_after_get",
        l1.get("present") is True,
        str(l1),
    ))

    replica: dict[str, str] = {str(user_id): "stale-from-other-process"}
    replica_ready = threading.Event()

    def listen_replica():
        pubsub = redis_client().pubsub()
        pubsub.subscribe(cache_app.INVALIDATE_CHANNEL)
        replica_ready.set()
        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            replica.pop(str(message["data"]), None)
            break
        pubsub.unsubscribe(cache_app.INVALIDATE_CHANNEL)
        pubsub.close()

    t = threading.Thread(target=listen_replica, daemon=True)
    t.start()
    replica_ready.wait(timeout=5)
    time.sleep(0.3)
    invalidated = client.delete(f"/cache/users/{user_id}").get_json()
    t.join(timeout=5)
    time.sleep(0.3)
    l1_after = client.get(f"/cache/l1/{user_id}").get_json()
    checks.append(Check(
        "pubsub_invalidation_clears_local_and_replica_l1",
        l1_after.get("present") is False
        and str(user_id) not in replica
        and invalidated.get("invalidated") is True,
        f"l1={l1_after} replica={replica} pubsub={invalidated}",
    ))

    cache_app.clear_l1()
    cleanup_prefix(r, "cache")
    return checks
