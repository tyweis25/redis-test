"""
Redis Streams demo - durable alternative to Pub/Sub, plus a work queue.

Unlike Pub/Sub (fire-and-forget), a Stream keeps every message until
you trim it. A consumer group can read messages that were published
while nobody was listening. If a worker crashes before XACK, the
message stays in the pending list and another consumer can claim it.

Install:
    pip3 install redis

Run:
    python3 streams_demo.py
"""

import redis

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

STREAM = prefixed("stream", "jobs")
GROUP = "workers"


def connect():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        ssl=REDIS_TLS,
        decode_responses=True,
    )


def ensure_group(r):
    r.delete(STREAM)
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def main():
    r = connect()
    ensure_group(r)

    messages = [
        "order #1042 (written while no reader was running)",
        "charge $12 for ty",
        "send welcome email",
    ]
    ids = [r.xadd(STREAM, {"text": msg}) for msg in messages]
    print(f"Wrote {len(ids)} jobs to stream {STREAM}")

    claimed = r.xreadgroup(GROUP, "worker-1", {STREAM: ">"}, count=10)
    texts = [fields["text"] for _stream, entries in claimed for _id, fields in entries]
    print(f"worker-1 read (and then 'crashed' without XACK): {texts}")

    pending = r.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    pending_count = len(pending or [])
    print(f"Pending after crash: {pending_count} job(s) still unacked")

    # Another worker claims the abandoned jobs and finishes them.
    claimed_ids = []
    for entry in pending or []:
        msg_id = entry["message_id"] if isinstance(entry, dict) else entry[0]
        r.xclaim(STREAM, GROUP, "worker-2", min_idle_time=0, message_ids=[msg_id])
        claimed_ids.append(msg_id)
        r.xack(STREAM, GROUP, msg_id)
    print(f"worker-2 claimed + XACK'd: {claimed_ids}")

    leftover = r.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    print(f"Pending after ACK: {len(leftover or [])} (should be 0)")
    print("That's the difference vs Pub/Sub: jobs survive a crash and are processed once.")


if __name__ == "__main__":
    main()
