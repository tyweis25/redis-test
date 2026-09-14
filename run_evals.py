"""
Run the scored eval suite for every demo.

    python3 run_evals.py
    python3 run_evals.py --json

LangCache and Agent Memory checks are skipped unless real API keys
are set in redis_config.py. Everything else hits the Redis Cloud DB.
"""

from __future__ import annotations

import argparse
import sys

from evals.common import dump_json, print_suite, suite_summary
from evals import (
    test_agent_memory,
    test_cache_aside,
    test_langcache,
    test_pubsub,
    test_rate_limit,
    test_redis_ops,
    test_sessions,
    test_streams,
)

SUITES = [
    ("redis_ops", test_redis_ops.run),
    ("pubsub", test_pubsub.run),
    ("streams", test_streams.run),
    ("cache_aside", test_cache_aside.run),
    ("sessions", test_sessions.run),
    ("rate_limit", test_rate_limit.run),
    ("langcache", test_langcache.run),
    ("agent_memory", test_agent_memory.run),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score every Redis demo")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args(argv)

    suites = {}
    for name, fn in SUITES:
        try:
            suites[name] = fn()
        except Exception as exc:  # noqa: BLE001 — surface eval crashes as failed checks
            from evals.common import Check
            suites[name] = [Check(f"{name}_crashed", False, repr(exc))]
        print_suite(name, suites[name])

    summary = suite_summary(suites)
    print(
        f"\nSCORE {summary['passed']}/{summary['total_scored']} passed, "
        f"{summary['failed']} failed, {summary['skipped']} skipped"
    )
    if args.json:
        print(dump_json(summary))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
