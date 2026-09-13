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
import os
import time

import redis
from flask import Flask, jsonify

app = Flask(__name__)

# --- Redis connection ---
# Set REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_TLS env vars to point at
# Redis Cloud instead of local Redis. See redis_test.py for the full list.
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
    db=0,
    ssl=os.getenv("REDIS_TLS", "false").lower() == "true",
    decode_responses=True,
)

CACHE_TTL_SECONDS = 30  # how long a cached entry stays valid


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


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    cache_key = f"user:{user_id}"
    start = time.time()

    cached = r.get(cache_key)
    if cached is not None:
        elapsed = round(time.time() - start, 4)
        return jsonify({
            "source": "cache",
            "elapsed_seconds": elapsed,
            "data": json.loads(cached),
        })

    # Cache miss - do the "expensive" work
    data = fetch_user_from_slow_source(user_id)
    r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data))

    elapsed = round(time.time() - start, 4)
    return jsonify({
        "source": "database",
        "elapsed_seconds": elapsed,
        "data": data,
    })


@app.route("/cache/users/<int:user_id>", methods=["DELETE"])
def invalidate_user_cache(user_id):
    cache_key = f"user:{user_id}"
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
    app.run(host="0.0.0.0", port=5000, debug=True)
