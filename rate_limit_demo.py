"""
Redis-backed rate limiting demo (fixed-window and sliding-window).

Limits each client to N requests per time window. Fixed window buckets
by clock slot; sliding window uses a Redis sorted set of timestamps so
bursts at a window boundary cannot sneak extra requests through.

Install:
    pip3 install flask redis

Run:
    python3 rate_limit_demo.py

Try it (fire more requests than the limit allows):
    for i in $(seq 1 8); do curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:5002/api/data; done
"""

import time
import uuid

import redis
from flask import Flask, jsonify, request

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

app = Flask(__name__)

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=REDIS_TLS,
    decode_responses=True,
)

RATE_LIMIT = 5
WINDOW_SECONDS = 30


def _params():
    try:
        limit = int(request.headers.get("X-RateLimit-Limit") or RATE_LIMIT)
    except ValueError:
        limit = RATE_LIMIT
    try:
        window = int(request.headers.get("X-RateLimit-Window") or WINDOW_SECONDS)
    except ValueError:
        window = WINDOW_SECONDS
    client_id = (
        request.headers.get("X-Client-Id")
        or request.args.get("client_id")
        or request.remote_addr
        or "unknown"
    )
    algo = (request.args.get("algo") or "fixed").lower()
    return max(1, limit), max(1, window), client_id, algo


def check_fixed(client_id: str, limit: int, window: int):
    slot = int(time.time() // window)
    key = prefixed("ratelimit", "fixed", client_id, str(slot))
    current = r.incr(key)
    if current == 1:
        r.expire(key, window)
    ttl = r.ttl(key)
    return current <= limit, current, ttl


def check_sliding(client_id: str, limit: int, window: int):
    key = prefixed("ratelimit", "sliding", client_id)
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex[:8]}"
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, current, _ = pipe.execute()
    oldest = r.zrange(key, 0, 0, withscores=True)
    retry_after = window
    if oldest:
        retry_after = max(1, int(window - (now - oldest[0][1])))
    return current <= limit, current, retry_after


@app.route("/api/data", methods=["GET"])
def get_data():
    limit, window, client_id, algo = _params()
    if algo == "sliding":
        allowed, current, ttl = check_sliding(client_id, limit, window)
    else:
        allowed, current, ttl = check_fixed(client_id, limit, window)

    if not allowed:
        return jsonify({
            "error": "rate limit exceeded",
            "algo": algo,
            "limit": limit,
            "window_seconds": window,
            "client_id": client_id,
            "retry_after_seconds": ttl,
        }), 429, {"Retry-After": str(ttl)}

    return jsonify({
        "message": "here is your data",
        "algo": algo,
        "requests_used": current,
        "requests_remaining": max(0, limit - current),
        "window_resets_in_seconds": ttl,
        "client_id": client_id,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
