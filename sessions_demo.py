"""
Redis-backed session storage demo.

Instead of Flask's default signed-cookie sessions (which store data
client-side), this stores session data in Redis, keyed by a random
session ID that's given to the client as a cookie. This is the same
pattern used by most production apps: the cookie only holds an opaque
ID, and the real data (and revocation control) stays server-side.

Install:
    pip3 install flask redis

Run:
    python3 sessions_demo.py

Try it (note -c/-b to persist cookies between curl calls):
    curl -c cookies.txt -X POST http://localhost:5001/login \\
         -H "Content-Type: application/json" \\
         -d '{"username": "ty"}'

    curl -b cookies.txt http://localhost:5001/profile

    curl -b cookies.txt -X POST http://localhost:5001/logout

    curl -b cookies.txt http://localhost:5001/profile   # now rejected
"""

import json
import os
import secrets
import time

import redis
from flask import Flask, jsonify, request, make_response

app = Flask(__name__)

# Set REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_TLS env vars to point at
# Redis Cloud instead of local Redis. See redis_test.py for the full list.
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
    ssl=os.getenv("REDIS_TLS", "false").lower() == "true",
    decode_responses=True,
)

SESSION_TTL_SECONDS = 300  # sessions expire after 5 minutes of creation
COOKIE_NAME = "session_id"


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400

    # Create a new opaque session ID - never expose internal user data in it
    session_id = secrets.token_urlsafe(24)
    session_data = {
        "username": username,
        "logged_in_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    r.setex(session_key(session_id), SESSION_TTL_SECONDS, json.dumps(session_data))

    resp = make_response(jsonify({"message": f"logged in as {username}"}))
    resp.set_cookie(COOKIE_NAME, session_id, httponly=True, max_age=SESSION_TTL_SECONDS)
    return resp


@app.route("/profile", methods=["GET"])
def profile():
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return jsonify({"error": "not logged in"}), 401

    raw = r.get(session_key(session_id))
    if raw is None:
        return jsonify({"error": "session expired or invalid"}), 401

    # Sliding expiration: extend the session on activity
    r.expire(session_key(session_id), SESSION_TTL_SECONDS)

    return jsonify({"session": json.loads(raw)})


@app.route("/logout", methods=["POST"])
def logout():
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        r.delete(session_key(session_id))

    resp = make_response(jsonify({"message": "logged out"}))
    resp.delete_cookie(COOKIE_NAME)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
