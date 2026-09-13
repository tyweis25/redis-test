"""
Redis-backed rate limiting demo (fixed-window algorithm).

Limits each client to N requests per time window, tracked with a single
Redis counter key per client per window. This is the same basic
technique used by API gateways to stop one client from overwhelming
a service.

Install:
    pip3 install flask redis

Run:
    python3 rate_limit_demo.py

Try it (fire more requests than the limit allows):
    for i in $(seq 1 8); do curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:5002/api/data; done

You should see "200" for the first few requests, then "429" once the
limit is hit, until the window resets.
"""

import time

import redis
from flask import Flask, jsonify, request

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS

app = Flask(__name__)

# Edit redis_config.py to point this at Redis Cloud vs. local Redis.
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=REDIS_TLS,
    decode_responses=True,
)

RATE_LIMIT = 5          # max requests
WINDOW_SECONDS = 30      # per this many seconds


def rate_limit_key(client_id: str) -> str:
    # Bucket requests into fixed windows, e.g. all requests in the same
    # 30-second slot share one counter.
    window = int(time.time() // WINDOW_SECONDS)
    return f"ratelimit:{client_id}:{window}"


def check_rate_limit(client_id: str):
    key = rate_limit_key(client_id)

    # INCR creates the key at 1 if it doesn't exist yet.
    current = r.incr(key)
    if current == 1:
        # First request in this window - set the key to expire so it
        # cleans itself up (also caps the window's lifetime).
        r.expire(key, WINDOW_SECONDS)

    ttl = r.ttl(key)
    allowed = current <= RATE_LIMIT
    return allowed, current, ttl


@app.route("/api/data", methods=["GET"])
def get_data():
    # In a real app, key by API key, user ID, or authenticated identity
    # rather than raw IP (proxies/NAT can make IP unreliable).
    client_id = request.remote_addr or "unknown"

    allowed, current, ttl = check_rate_limit(client_id)

    if not allowed:
        return jsonify({
            "error": "rate limit exceeded",
            "limit": RATE_LIMIT,
            "window_seconds": WINDOW_SECONDS,
            "retry_after_seconds": ttl,
        }), 429, {"Retry-After": str(ttl)}

    return jsonify({
        "message": "here is your data",
        "requests_used": current,
        "requests_remaining": RATE_LIMIT - current,
        "window_resets_in_seconds": ttl,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
