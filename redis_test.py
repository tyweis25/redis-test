"""
Simple Python app to test a Redis connection.

Connection settings (host/port/password/TLS) come from redis_config.py,
so you only need to edit that one file to point every script at either
your local Rancher Desktop Redis or Redis Cloud.

Install the client library first:
    pip install redis
"""

import redis
import sys

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS

REDIS_DB = 0


def main():
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT} ...")
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            ssl=REDIS_TLS,
            decode_responses=True,   # get back str instead of bytes
            socket_connect_timeout=5,
        )

        # 1. Basic connectivity check
        pong = r.ping()
        print(f"PING -> {pong}")

        # 2. String set/get
        r.set("greeting", "hello from python")
        value = r.get("greeting")
        print(f"GET greeting -> {value}")

        # 3. Increment a counter
        r.set("counter", 0)
        r.incr("counter")
        r.incr("counter")
        count = r.get("counter")
        print(f"Counter after two increments -> {count}")

        # 4. List operations
        r.delete("mylist")
        r.rpush("mylist", "a", "b", "c")
        items = r.lrange("mylist", 0, -1)
        print(f"List contents -> {items}")

        # 5. Hash operations
        r.delete("user:1")
        r.hset("user:1", mapping={"name": "Ty", "role": "tester"})
        user = r.hgetall("user:1")
        print(f"Hash user:1 -> {user}")

        # 6. Key with expiration
        r.set("temp_key", "expires soon", ex=10)
        ttl = r.ttl("temp_key")
        print(f"TTL on temp_key -> {ttl} seconds")

        # 7. Server info
        info = r.info("server")
        print(f"Redis version -> {info.get('redis_version')}")

        print("\nAll checks passed - connection to Redis is working.")

    except redis.exceptions.AuthenticationError:
        print("Authentication failed - check the REDIS_PASSWORD environment variable.")
        sys.exit(1)
    except redis.exceptions.ConnectionError as e:
        print(f"Could not connect to Redis: {e}")
        print("If using local Redis, check that your port-forward is running:")
        print("  kubectl port-forward svc/my-redis-master 6379:6379")
        print("If using Redis Cloud, double-check REDIS_HOST/REDIS_PORT/REDIS_TLS.")
        sys.exit(1)


if __name__ == "__main__":
    main()
