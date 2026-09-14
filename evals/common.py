"""Shared eval types, Redis client, and key cleanup."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import redis

from redis_config import (
    KEY_PREFIX,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_TLS,
    prefixed,
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    latency_ms: Optional[float] = None
    skipped: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def timed(fn: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    result = fn()
    return result, (time.perf_counter() - start) * 1000


def redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        ssl=REDIS_TLS,
        decode_responses=True,
        socket_connect_timeout=5,
    )


def cleanup_prefix(r: redis.Redis, *extra_parts: str) -> int:
    """Delete keys under demo: or demo:<extra>:... via SCAN (never KEYS)."""
    pattern = prefixed(*extra_parts, "*") if extra_parts else f"{KEY_PREFIX}:*"
    deleted = 0
    for key in r.scan_iter(match=pattern, count=200):
        deleted += r.delete(key)
    return deleted


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def print_suite(name: str, checks: list[Check]) -> None:
    scored = [c for c in checks if not c.skipped]
    passed = sum(1 for c in scored if c.passed)
    skipped = sum(1 for c in checks if c.skipped)
    print(f"\n=== {name}: {passed}/{len(scored)} passed ({skipped} skipped) ===")
    for c in checks:
        if c.skipped:
            mark = "SKIP"
        elif c.passed:
            mark = "PASS"
        else:
            mark = "FAIL"
        lat = f"  {c.latency_ms:.1f}ms" if c.latency_ms is not None else ""
        print(f"  [{mark}] {c.name}{lat}")
        if c.detail:
            print(f"         {c.detail}")


def suite_summary(suites: dict[str, list[Check]]) -> dict:
    checks = [c for group in suites.values() for c in group]
    scored = [c for c in checks if not c.skipped]
    return {
        "passed": sum(1 for c in scored if c.passed),
        "failed": sum(1 for c in scored if not c.passed),
        "skipped": sum(1 for c in checks if c.skipped),
        "total_scored": len(scored),
        "suites": {
            name: [c.to_dict() for c in group] for name, group in suites.items()
        },
    }


def dump_json(summary: dict) -> str:
    return json.dumps(summary, indent=2, default=str)
