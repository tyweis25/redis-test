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
import secrets
import time

import redis
from flask import Flask, jsonify, request, make_response, render_template_string

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

app = Flask(__name__)

# Edit redis_config.py to point this at Redis Cloud vs. local Redis.
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=REDIS_TLS,
    decode_responses=True,
)

SESSION_TTL_SECONDS = 300  # sessions expire after 5 minutes of creation
COOKIE_NAME = "session_id"


def session_key(session_id: str) -> str:
    return prefixed("session", session_id)


def _ttl_from_request() -> int:
    raw = None
    body = request.get_json(silent=True) or {}
    raw = body.get("ttl") or request.form.get("ttl") or request.args.get("ttl")
    if raw is None:
        return SESSION_TTL_SECONDS
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return SESSION_TTL_SECONDS


_PAGE = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Sessions demo</title>
<style>
  body { font-family: sans-serif; max-width: 32rem; margin: 2rem auto; }
  pre { background: #111; color: #eee; padding: 1rem; border-radius: 8px; }
  form { margin: .75rem 0; }
  input, button { padding: .4rem .6rem; }
</style></head><body>
  <h1>Redis-backed session</h1>
  <p>Cookie holds only an opaque id. Data lives in Redis and can be revoked.</p>
  <form method="post" action="/login">
    <input name="username" value="ty" />
    <button type="submit">Log in</button>
  </form>
  <form method="post" action="/logout"><button type="submit">Log out</button></form>
  <p><a href="/profile">View profile (JSON)</a></p>
  {% if session %}
  <pre>{{ session }}</pre>
  {% elif error %}
  <pre>{{ error }}</pre>
  {% endif %}
</body></html>
"""


@app.route("/", methods=["GET"])
def home():
    session_id = request.cookies.get(COOKIE_NAME)
    session = None
    error = None
    if not session_id:
        error = {"error": "not logged in"}
    else:
        raw = r.get(session_key(session_id))
        if raw is None:
            error = {"error": "session expired or invalid"}
        else:
            session = json.loads(raw)
    return render_template_string(_PAGE, session=session, error=error)


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    # Also accept a plain HTML form POST (application/x-www-form-urlencoded),
    # e.g. from a browser <form>, in addition to the JSON body shown above.
    username = body.get("username") or request.form.get("username")
    if not username:
        return jsonify({"error": "username is required"}), 400

    ttl = _ttl_from_request()
    # Create a new opaque session ID - never expose internal user data in it
    session_id = secrets.token_urlsafe(24)
    session_data = {
        "username": username,
        "logged_in_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    r.setex(session_key(session_id), ttl, json.dumps(session_data))

    wants_html = "text/html" in (request.headers.get("Accept") or "") and not request.is_json
    if wants_html or request.form:
        resp = make_response(render_template_string(
            _PAGE, session=session_data, error=None
        ))
    else:
        resp = make_response(jsonify({"message": f"logged in as {username}"}))
    resp.set_cookie(COOKIE_NAME, session_id, httponly=True, max_age=ttl)
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


def _presence_ttl():
    raw = None
    body = request.get_json(silent=True) or {}
    raw = body.get("ttl") or request.form.get("ttl") or request.args.get("ttl")
    if raw is None:
        return 30
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def presence_key(user: str) -> str:
    return prefixed("presence", user)


@app.route("/presence/<user>", methods=["POST"])
def presence_heartbeat(user):
    """Mark a user online. The key expires if they stop heartbeating."""
    ttl = _presence_ttl()
    r.setex(presence_key(user), ttl, "online")
    r.sadd(prefixed("presence", "users"), user)
    r.expire(prefixed("presence", "users"), 3600)
    return jsonify({"user": user, "status": "online", "ttl_seconds": ttl})


@app.route("/presence/<user>", methods=["GET"])
def presence_status(user):
    online = r.get(presence_key(user)) is not None
    return jsonify({"user": user, "online": online})


@app.route("/presence", methods=["GET"])
def presence_list():
    members = list(r.smembers(prefixed("presence", "users")) or [])
    online = []
    for user in members:
        if r.get(presence_key(user)) is not None:
            online.append(user)
        else:
            r.srem(prefixed("presence", "users"), user)
    return jsonify({"online": sorted(online)})


@app.route("/logout", methods=["POST"])
def logout():
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        r.delete(session_key(session_id))

    if request.form or "text/html" in (request.headers.get("Accept") or ""):
        resp = make_response(render_template_string(_PAGE, session=None, error={"error": "not logged in"}))
    else:
        resp = make_response(jsonify({"message": "logged out"}))
    resp.delete_cookie(COOKIE_NAME)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
