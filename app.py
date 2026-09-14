"""
Flask app demonstrating cache-aside caching with Redis.

Simulates a "slow" data lookup (like a real DB query or external API call)
and caches the result in Redis so repeated requests are fast.

Install dependencies:
    pip3 install flask redis

Run:
    python3 app.py

Then in another terminal try:
    curl http://localhost:5000/users/1        # first call: slow (cache miss)
    curl http://localhost:5000/users/1        # second call: fast (cache hit)
    curl http://localhost:5000/cache/l1/1     # process-local L1 copy
    curl -X DELETE http://localhost:5000/cache/users/1   # Redis + Pub/Sub L1
    curl http://localhost:5000/users/1        # slow again (cache miss)
"""

import json
import threading
import time

import redis
from flask import Flask, jsonify

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

app = Flask(__name__)

# --- Redis connection ---
# Edit redis_config.py to point every script at Redis Cloud vs. local Redis.
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=0,
    ssl=REDIS_TLS,
    decode_responses=True,
)

CACHE_TTL_SECONDS = 30  # how long a cached entry stays valid
LOCK_TTL_SECONDS = 5
INVALIDATE_CHANNEL = prefixed("cache", "invalidate")

# Process-local L1 cache. Redis is the shared L2. A Pub/Sub listener
# drops L1 entries when any replica invalidates, so two app processes
# don't serve stale data after a DELETE.
_l1: dict[str, dict] = {}
_listener_started = False
_listener_lock = threading.Lock()


def cache_key_for(user_id: int) -> str:
    return prefixed("cache", "user", str(user_id))


def clear_l1() -> None:
    _l1.clear()


def l1_get(user_id) -> dict | None:
    return _l1.get(str(user_id))


def _l1_set(user_id, data: dict) -> None:
    _l1[str(user_id)] = data


def _l1_drop(user_id) -> None:
    _l1.pop(str(user_id), None)


def _listen_invalidations():
    pub = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=0,
        ssl=REDIS_TLS,
        decode_responses=True,
    )
    ps = pub.pubsub()
    ps.subscribe(INVALIDATE_CHANNEL)
    for message in ps.listen():
        if message["type"] != "message":
            continue
        _l1_drop(message["data"])


def ensure_invalidation_listener():
    global _listener_started
    with _listener_lock:
        if _listener_started:
            return
        threading.Thread(
            target=_listen_invalidations,
            daemon=True,
            name="cache-invalidate",
        ).start()
        _listener_started = True
        time.sleep(0.25)


def fetch_user_from_slow_source(user_id: int) -> dict:
    """
    Stand-in for something expensive: a slow database query,
    a third-party API call, a heavy computation, etc.
    """
    time.sleep(2)  # simulate latency
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "role": "tester",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _hit(data: dict, start: float, source: str):
    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": source,
        "elapsed_seconds": elapsed,
        "data": data,
    })


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    ensure_invalidation_listener()
    cache_key = cache_key_for(user_id)
    lock_key = prefixed("cache", "lock", str(user_id))
    start = time.time()

    cached = r.get(cache_key)
    if cached is not None:
        data = json.loads(cached)
        _l1_set(user_id, data)
        return _hit(data, start, "cache")

    # Stampede-safe fill: only one request does the slow lookup.
    got_lock = r.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not got_lock:
        for _ in range(40):
            time.sleep(0.1)
            cached = r.get(cache_key)
            if cached is not None:
                data = json.loads(cached)
                _l1_set(user_id, data)
                return _hit(data, start, "cache")

    try:
        cached = r.get(cache_key)
        if cached is not None:
            data = json.loads(cached)
            _l1_set(user_id, data)
            return _hit(data, start, "cache")
        data = fetch_user_from_slow_source(user_id)
        r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))
        _l1_set(user_id, data)
    finally:
        r.delete(lock_key)

    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": "database",
        "elapsed_seconds": elapsed,
        "data": data,
    })


@app.route("/cache/l1/<int:user_id>", methods=["GET"])
def get_l1(user_id):
    ensure_invalidation_listener()
    data = l1_get(user_id)
    return jsonify({
        "present": data is not None,
        "data": data,
        "channel": INVALIDATE_CHANNEL,
    })


@app.route("/cache/users/<int:user_id>", methods=["DELETE"])
def invalidate_user_cache(user_id):
    ensure_invalidation_listener()
    cache_key = cache_key_for(user_id)
    deleted = r.delete(cache_key)
    # Fan-out to every replica's L1. Fire-and-forget: a process that is
    # down will miss this message (see streams_demo.py for durable jobs).
    delivered = r.publish(INVALIDATE_CHANNEL, str(user_id))
    _l1_drop(user_id)
    return jsonify({
        "cache_key": cache_key,
        "invalidated": bool(deleted),
        "pubsub_channel": INVALIDATE_CHANNEL,
        "l1_replicas_notified": delivered,
    })


@app.route("/health", methods=["GET"])
def health():
    try:
        r.ping()
        return jsonify({"status": "ok", "redis": "connected"})
    except redis.exceptions.ConnectionError:
        return jsonify({"status": "error", "redis": "unreachable"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
