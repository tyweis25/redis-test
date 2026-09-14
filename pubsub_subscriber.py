"""
Redis Pub/Sub demo - subscriber side.

Pub/Sub lets one process broadcast messages to any number of listeners
in real time, with no polling. Common uses: live notifications, chat
fan-out, invalidating caches across multiple app servers, telling
worker processes to reload config.

Run this FIRST, in its own terminal, then run pubsub_publisher.py in
another terminal and watch messages appear here as they're published.

Install:
    pip3 install redis

Run:
    python3 pubsub_subscriber.py
"""

import redis

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

# Edit redis_config.py to point this at Redis Cloud vs. local Redis.
r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=REDIS_TLS,
    decode_responses=True,
)

CHANNEL = prefixed("notifications")


def main():
    pubsub = r.pubsub()
    pubsub.subscribe(CHANNEL)
    print(f"Subscribed to '{CHANNEL}'. Waiting for messages... (Ctrl+C to stop)\n")

    try:
        for message in pubsub.listen():
            # The first message(s) confirm the subscription itself;
            # actual published messages have type "message".
            if message["type"] != "message":
                continue
            print(f"Received: {message['data']}")
    except KeyboardInterrupt:
        print("\nStopping subscriber.")
    finally:
        pubsub.unsubscribe(CHANNEL)
        pubsub.close()


if __name__ == "__main__":
    main()
