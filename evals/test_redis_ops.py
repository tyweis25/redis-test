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

    board = prefixed("eval", "ops", "board")
    r.delete(board)
    r.zincrby(board, 30, "ty")
    r.zincrby(board, 20, "sam")
    r.zincrby(board, 15, "ty")
    top = r.zrevrange(board, 0, -1, withscores=True)
    checks.append(Check(
        "leaderboard_ranks_by_score",
        top == [("ty", 45.0), ("sam", 20.0)],
        f"top={top}",
    ))

    hll = prefixed("eval", "ops", "hll")
    r.delete(hll)
    r.pfadd(hll, "ty", "sam", "ty", "ada")
    checks.append(Check("hyperloglog_unique_count", r.pfcount(hll) == 3, f"pfcount={r.pfcount(hll)}"))

    bloom = prefixed("eval", "ops", "bloom")
    r.delete(bloom)
    try:
        r.execute_command("BF.RESERVE", bloom, 0.01, 100)
        r.execute_command("BF.ADD", bloom, "evt-1")
        checks.append(Check(
            "bloom_membership",
            bool(r.execute_command("BF.EXISTS", bloom, "evt-1"))
            and not bool(r.execute_command("BF.EXISTS", bloom, "evt-missing")),
            "evt-1 in, evt-missing out",
        ))
    except redis.exceptions.ResponseError as e:
        checks.append(Check("bloom_membership", False, str(e), skipped=True))

    jobs = prefixed("eval", "ops", "jobs")
    r.delete(jobs)
    now = time.time()
    r.zadd(jobs, {"ready": now - 1, "later": now + 3600})
    due = list(r.zrangebyscore(jobs, 0, now))
    checks.append(Check(
        "delayed_jobs_ready_only",
        due == ["ready"],
        f"due={due}",
    ))

    cleanup_prefix(r, "eval", "ops")
    return checks
