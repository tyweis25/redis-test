"""
Redis Streams demo - durable alternative to Pub/Sub.

Unlike Pub/Sub (fire-and-forget), a Stream keeps every message until
you trim it. A consumer group can read messages that were published
while nobody was listening.

Install:
    pip3 install redis

Run:
    python3 streams_demo.py
"""

import redis

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

STREAM = prefixed("stream", "notifications")
GROUP = "workers"
CONSUMER = "worker-1"


def main():
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        ssl=REDIS_TLS,
        decode_responses=True,
    )
    r.delete(STREAM)
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    messages = [
        "order #1042 (written while no reader was running)",
        "user ty logged in",
        "cache invalidated",
    ]
    ids = [r.xadd(STREAM, {"text": msg}) for msg in messages]
    print(f"Wrote {len(ids)} messages to stream {STREAM}")

    claimed = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=10)
    texts = [fields["text"] for _stream, entries in claimed for _id, fields in entries]
    print(f"Consumer group '{GROUP}' later read: {texts}")
    print("That's the difference vs Pub/Sub: these survived with no live subscriber.")


if __name__ == "__main__":
    main()
