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
    curl -X DELETE http://localhost:5000/cache/users/1   # invalidate
    curl http://localhost:5000/users/1        # slow again (cache miss)
"""

import json
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


def cache_key_for(user_id: int) -> str:
    return prefixed("cache", "user", str(user_id))


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


def _hit(cached: str, start: float):
    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": "cache",
        "elapsed_seconds": elapsed,
        "data": json.loads(cached),
    })


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    cache_key = cache_key_for(user_id)
    lock_key = prefixed("cache", "lock", str(user_id))
    start = time.time()

    cached = r.get(cache_key)
    if cached is not None:
        return _hit(cached, start)

    # Stampede-safe fill: only one request does the slow lookup.
    got_lock = r.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not got_lock:
        for _ in range(40):
            time.sleep(0.1)
            cached = r.get(cache_key)
            if cached is not None:
                return _hit(cached, start)

    try:
        cached = r.get(cache_key)
        if cached is not None:
            return _hit(cached, start)
        data = fetch_user_from_slow_source(user_id)
        r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))
    finally:
        r.delete(lock_key)

    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": "database",
        "elapsed_seconds": elapsed,
        "data": data,
    })


@app.route("/cache/users/<int:user_id>", methods=["DELETE"])
def invalidate_user_cache(user_id):
    cache_key = cache_key_for(user_id)
    deleted = r.delete(cache_key)
    return jsonify({
        "cache_key": cache_key,
        "invalidated": bool(deleted),
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
