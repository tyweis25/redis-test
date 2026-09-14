"""Streams eval: messages survive with no live reader, then a group consumes them."""

from __future__ import annotations

import redis

from evals.common import Check, redis_client
from redis_config import prefixed


def run() -> list[Check]:
    checks: list[Check] = []
    r = redis_client()
    stream = prefixed("eval", "stream")
    group = "eval-workers"
    r.delete(stream)
    r.xgroup_create(stream, group, id="0", mkstream=True)

    ids = [
        r.xadd(stream, {"text": "written-offline-1"}),
        r.xadd(stream, {"text": "written-offline-2"}),
    ]
    checks.append(Check("xadd_two_messages", len(ids) == 2, f"ids={ids}"))

    claimed = r.xreadgroup(group, "c1", {stream: ">"}, count=10)
    texts = [fields["text"] for _s, entries in claimed for _i, fields in entries]
    checks.append(Check(
        "group_reads_messages_published_offline",
        texts == ["written-offline-1", "written-offline-2"],
        f"read {texts}",
    ))

    again = r.xreadgroup(group, "c1", {stream: ">"}, count=10)
    empty = again == [] or again[0][1] == []
    checks.append(Check("already_delivered_not_redelivered_as_new", empty, f"second read={again}"))

    pending = r.xpending_range(stream, group, min="-", max="+", count=10)
    checks.append(Check(
        "unacked_jobs_stay_pending",
        len(pending or []) == 2,
        f"pending={pending}",
    ))

    for entry in pending or []:
        msg_id = entry["message_id"] if isinstance(entry, dict) else entry[0]
        r.xclaim(stream, group, "c2", min_idle_time=0, message_ids=[msg_id])
        r.xack(stream, group, msg_id)

    leftover = r.xpending_range(stream, group, min="-", max="+", count=10)
    checks.append(Check(
        "claim_and_ack_clears_pending",
        len(leftover or []) == 0,
        f"leftover={leftover}",
    ))

    r.delete(stream)
    return checks
