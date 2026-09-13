"""
Redis Pub/Sub demo - publisher side.

Run pubsub_subscriber.py first (in another terminal), then run this to
send messages. Every currently-subscribed listener receives each
message instantly. Note: Pub/Sub is fire-and-forget - if no one is
subscribed when a message is published, it's gone (unlike a queue).
For guaranteed delivery you'd use Redis Streams instead.

Install:
    pip3 install redis

Run:
    python3 pubsub_publisher.py
"""

import time

import redis

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS

# Edit redis_config.py to point this at Redis Cloud vs. local Redis.
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=REDIS_TLS,
    decode_responses=True,
)

CHANNEL = "notifications"


def main():
    messages = [
        "New order #1042 received",
        "User ty logged in",
        "Cache invalidated for user:1",
        "Server health check: OK",
    ]

    print(f"Publishing to '{CHANNEL}'...\n")
    for msg in messages:
        subscriber_count = r.publish(CHANNEL, msg)
        print(f"Sent: '{msg}' -> delivered to {subscriber_count} subscriber(s)")
        time.sleep(1.5)

    print("\nDone publishing.")


if __name__ == "__main__":
    main()
