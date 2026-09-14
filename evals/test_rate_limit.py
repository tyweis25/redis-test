"""Rate-limit eval: exact boundary, window reset, sliding vs fixed."""

from __future__ import annotations

import time

import rate_limit_demo
from evals.common import Check, cleanup_prefix, redis_client


def _codes(client, n, **kwargs):
    return [client.get("/api/data", **kwargs).status_code for _ in range(n)]


def _wait_for_fixed_slot(window: int, need_s: float = 2.5) -> None:
    """Avoid firing a burst across a clock-slot boundary."""
    remaining = window - (time.time() % window)
    if remaining < need_s:
        time.sleep(remaining + 0.05)


def run() -> list[Check]:
    checks: list[Check] = []
    cleanup_prefix(redis_client(), "ratelimit")
    client = rate_limit_demo.app.test_client()
    window = 8
    headers = {
        "X-Client-Id": "eval-fixed-1",
        "X-RateLimit-Limit": "5",
        "X-RateLimit-Window": str(window),
    }

    _wait_for_fixed_slot(window)
    codes = _codes(client, 8, headers=headers, query_string={"algo": "fixed"})
    checks.append(Check(
        "fixed_window_five_ok_then_429",
        codes[:5] == [200] * 5 and codes[5:] == [429] * 3,
        f"codes={codes}",
    ))
    denied = client.get("/api/data", headers=headers, query_string={"algo": "fixed"})
    retry = denied.headers.get("Retry-After")
    checks.append(Check(
        "retry_after_header_present",
        denied.status_code == 429 and retry is not None and int(retry) >= 0,
        f"Retry-After={retry}",
    ))

    time.sleep(8.2)
    after = client.get("/api/data", headers=headers, query_string={"algo": "fixed"})
    checks.append(Check(
        "fixed_window_resets",
        after.status_code == 200,
        f"after wait status={after.status_code} body={after.get_json()}",
    ))

    slide_headers = {
        "X-Client-Id": "eval-slide-1",
        "X-RateLimit-Limit": "5",
        "X-RateLimit-Window": "8",
    }
    slide_codes = _codes(client, 8, headers=slide_headers, query_string={"algo": "sliding"})
    checks.append(Check(
        "sliding_window_five_ok_then_429",
        slide_codes[:5] == [200] * 5 and slide_codes[5:] == [429] * 3,
        f"codes={slide_codes}",
    ))

    other = client.get(
        "/api/data",
        headers={"X-Client-Id": "eval-other", "X-RateLimit-Limit": "5", "X-RateLimit-Window": "8"},
        query_string={"algo": "fixed"},
    )
    checks.append(Check(
        "per_client_isolation",
        other.status_code == 200 and other.get_json().get("client_id") == "eval-other",
        str(other.get_json()),
    ))
    return checks
