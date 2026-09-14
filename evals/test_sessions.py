"""Session eval: login, revoke, isolation, expiry, sliding TTL."""

from __future__ import annotations

import time

import sessions_demo
from evals.common import Check, redis_client
from redis_config import prefixed


def run() -> list[Check]:
    checks: list[Check] = []
    app = sessions_demo.app
    r = redis_client()

    c1 = app.test_client()
    denied = c1.get("/profile")
    checks.append(Check(
        "profile_without_cookie_is_401",
        denied.status_code == 401 and denied.get_json().get("error") == "not logged in",
        str(denied.get_json()),
    ))

    login = c1.post("/login", json={"username": "alice", "ttl": 30})
    checks.append(Check("login_ok", login.status_code == 200, login.get_data(as_text=True)[:120]))
    cookie = login.headers.get("Set-Cookie", "")
    checks.append(Check("sets_httponly_cookie", "session_id=" in cookie and "HttpOnly" in cookie, cookie[:80]))

    sid = None
    for part in cookie.split(";"):
        if part.strip().startswith("session_id="):
            sid = part.split("=", 1)[1].strip()
    ttl_at_login = r.ttl(prefixed("session", sid)) if sid else -2
    checks.append(Check(
        "login_honors_requested_ttl",
        sid is not None and 20 <= ttl_at_login <= 30,
        f"ttl after login={ttl_at_login}s (requested 30)",
    ))

    profile = c1.get("/profile")
    body = profile.get_json() or {}
    checks.append(Check(
        "profile_returns_server_session",
        profile.status_code == 200 and body.get("session", {}).get("username") == "alice",
        str(body),
    ))

    ttl_after = r.ttl(prefixed("session", sid)) if sid else -2
    checks.append(Check(
        "sliding_ttl_extends_on_activity",
        sid is not None and ttl_after >= 250,
        f"ttl {ttl_at_login}s -> {ttl_after}s (profile refreshes to 300s)",
    ))

    c2 = app.test_client()
    c2.post("/login", json={"username": "bob", "ttl": 30})
    a = c1.get("/profile").get_json()["session"]["username"]
    b = c2.get("/profile").get_json()["session"]["username"]
    checks.append(Check("two_clients_isolated_sessions", a == "alice" and b == "bob", f"{a=} {b=}"))

    c1.post("/logout")
    after_logout = c1.get("/profile")
    checks.append(Check(
        "logout_revokes_even_if_cookie_resent",
        after_logout.status_code == 401,
        str(after_logout.get_json()),
    ))
    if sid:
        checks.append(Check(
            "logout_deletes_redis_key",
            r.get(prefixed("session", sid)) is None,
            "session key gone",
        ))

    c3 = app.test_client()
    c3.post("/login", json={"username": "temp", "ttl": 1})
    time.sleep(1.3)
    expired = c3.get("/profile")
    checks.append(Check(
        "ttl_expiry_rejects_stale_cookie",
        expired.status_code == 401,
        str(expired.get_json()),
    ))

    page = app.test_client().get("/")
    checks.append(Check("html_home_renders", page.status_code == 200 and b"Log in" in page.data, "GET /"))

    c4 = app.test_client()
    c4.post("/presence/alice", json={"ttl": 2})
    c4.post("/presence/bob", json={"ttl": 30})
    listed = c4.get("/presence").get_json() or {}
    checks.append(Check(
        "presence_lists_heartbeats",
        set(listed.get("online") or []) >= {"alice", "bob"},
        str(listed),
    ))
    time.sleep(2.3)
    after = c4.get("/presence").get_json() or {}
    alice = c4.get("/presence/alice").get_json() or {}
    bob = c4.get("/presence/bob").get_json() or {}
    checks.append(Check(
        "presence_expires_without_heartbeat",
        alice.get("online") is False and bob.get("online") is True and "alice" not in (after.get("online") or []),
        f"list={after} alice={alice} bob={bob}",
    ))
    return checks
