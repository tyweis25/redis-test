"""Pub/Sub eval: missed message, fan-out, time-to-first-message."""

from __future__ import annotations

import threading
import time

from evals.common import Check, redis_client, timed
from redis_config import prefixed


def run() -> list[Check]:
    checks: list[Check] = []
    r = redis_client()
    channel = prefixed("eval", "pubsub")

    count, ms = timed(lambda: r.publish(channel, "nobody-home"))
    checks.append(Check(
        "publish_with_no_subscriber",
        count == 0,
        f"delivered to {count} subscriber(s)",
        ms,
    ))

    got_a: list[str] = []
    got_b: list[str] = []
    first_at = {"t": None}

    def listen(bucket: list, mark_first: bool):
        # Own connection: pubsub.listen() takes over a socket.
        pubsub = redis_client().pubsub()
        pubsub.subscribe(channel)
        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            if mark_first and first_at["t"] is None:
                first_at["t"] = time.perf_counter()
            bucket.append(message["data"])
            if len(bucket) >= 1:
                break
        pubsub.unsubscribe(channel)
        pubsub.close()

    t1 = threading.Thread(target=listen, args=(got_a, True), daemon=True)
    t2 = threading.Thread(target=listen, args=(got_b, False), daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.8)
    sent_at = time.perf_counter()
    delivered = r.publish(channel, "hello-both")
    t1.join(timeout=5)
    t2.join(timeout=5)

    checks.append(Check("two_subscriber_fanout_count", delivered == 2, f"delivered={delivered}"))
    checks.append(Check("subscriber_a_received", got_a == ["hello-both"], f"got {got_a}"))
    checks.append(Check("subscriber_b_received", got_b == ["hello-both"], f"got {got_b}"))

    if first_at["t"] is None:
        checks.append(Check("time_to_first_message", False, "no message received"))
    else:
        latency = (first_at["t"] - sent_at) * 1000
        checks.append(Check(
            "time_to_first_message",
            latency < 2000,
            f"{latency:.1f}ms subscribe-to-receive",
            latency,
        ))
    return checks
