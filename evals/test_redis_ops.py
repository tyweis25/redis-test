"""Ops-matrix eval for redis_test.py / raw Redis Cloud."""

from __future__ import annotations

import time

import redis

from evals.common import Check, cleanup_prefix, percentile, redis_client, timed
from redis_config import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT, REDIS_TLS, prefixed


def run() -> list[Check]:
    checks: list[Check] = []
    r = redis_client()
    cleanup_prefix(r, "eval", "ops")

    pong, ms = timed(r.ping)
    checks.append(Check("ping", pong is True, f"PING={pong}", ms))

    r.set(prefixed("eval", "ops", "greeting"), "hello")
    value = r.get(prefixed("eval", "ops", "greeting"))
    checks.append(Check("string_set_get", value == "hello", f"got {value!r}"))

    r.set(prefixed("eval", "ops", "counter"), 0)
    r.incr(prefixed("eval", "ops", "counter"))
    r.incr(prefixed("eval", "ops", "counter"))
    count = int(r.get(prefixed("eval", "ops", "counter")))
    checks.append(Check("incr", count == 2, f"counter={count}"))

    key_n = 80
    seq_start = time.perf_counter()
    for i in range(key_n):
        r.set(prefixed("eval", "ops", "seq", str(i)), i)
    seq_ms = (time.perf_counter() - seq_start) * 1000

    pipe = r.pipeline()
    pipe_start = time.perf_counter()
    for i in range(key_n):
        pipe.set(prefixed("eval", "ops", "pipe", str(i)), i)
    pipe.execute()
    pipe_ms = (time.perf_counter() - pipe_start) * 1000
    checks.append(Check(
        "pipeline_faster_than_sequential",
        pipe_ms < seq_ms,
        f"seq={seq_ms:.1f}ms pipe={pipe_ms:.1f}ms for {key_n} SETs",
        pipe_ms,
        extra={"seq_ms": seq_ms, "pipe_ms": pipe_ms},
    ))

    incr_key = prefixed("eval", "ops", "hot")
    r.set(incr_key, 0)
    samples = []
    start = time.perf_counter()
    for _ in range(200):
        t0 = time.perf_counter()
        r.incr(incr_key)
        samples.append((time.perf_counter() - t0) * 1000)
    elapsed = time.perf_counter() - start
    ops = 200 / elapsed
    p50 = percentile(samples, 50)
    p99 = percentile(samples, 99)
    checks.append(Check(
        "incr_throughput",
        ops > 10,
        f"{ops:.0f} INCR/s  p50={p50:.1f}ms p99={p99:.1f}ms",
        extra={"ops_per_sec": ops, "p50_ms": p50, "p99_ms": p99},
    ))

    blob = "x" * (100 * 1024)
    r.set(prefixed("eval", "ops", "blob"), blob)
    got = r.get(prefixed("eval", "ops", "blob"))
    checks.append(Check("large_payload_100kb", got == blob, f"len={len(got or '')}"))

    ttl_key = prefixed("eval", "ops", "ttl")
    r.set(ttl_key, "soon", ex=1)
    ttl = r.ttl(ttl_key)
    checks.append(Check("ttl_set", ttl in (0, 1), f"ttl={ttl}"))
    time.sleep(1.2)
    checks.append(Check("ttl_expired", r.get(ttl_key) is None, "key gone after 1.2s"))

    scan_count = sum(1 for _ in r.scan_iter(match=prefixed("eval", "ops", "*"), count=100))
    keys_count = len(r.keys(prefixed("eval", "ops", "*")))
    checks.append(Check(
        "scan_matches_keys",
        scan_count == keys_count and scan_count > 0,
        f"SCAN={scan_count} KEYS={keys_count}",
    ))

    typed = prefixed("eval", "ops", "wrongtype")
    r.set(typed, "string")
    try:
        r.hgetall(typed)
        checks.append(Check("wrongtype_rejected", False, "HGETALL on string did not error"))
    except redis.exceptions.ResponseError as e:
        checks.append(Check("wrongtype_rejected", "WRONGTYPE" in str(e), str(e)))

    try:
        bad = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password="definitely-not-the-password",
            ssl=REDIS_TLS,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        bad.ping()
        checks.append(Check("bad_password_rejected", False, "wrong password was accepted"))
    except (redis.exceptions.AuthenticationError, redis.exceptions.ConnectionError) as e:
        checks.append(Check("bad_password_rejected", True, type(e).__name__))

    cleanup_prefix(r, "eval", "ops")
    return checks
