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
import time

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

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
        r.set(prefixed("greeting"), "hello from python")
        value = r.get(prefixed("greeting"))
        print(f"GET greeting -> {value}")

        # 3. Increment a counter
        r.set(prefixed("counter"), 0)
        r.incr(prefixed("counter"))
        r.incr(prefixed("counter"))
        count = r.get(prefixed("counter"))
        print(f"Counter after two increments -> {count}")

        # 4. List operations
        r.delete(prefixed("mylist"))
        r.rpush(prefixed("mylist"), "a", "b", "c")
        items = r.lrange(prefixed("mylist"), 0, -1)
        print(f"List contents -> {items}")

        # 5. Hash operations (namespaced so it cannot collide with app.py's cache)
        r.delete(prefixed("hash", "user", "1"))
        r.hset(prefixed("hash", "user", "1"), mapping={"name": "Ty", "role": "tester"})
        user = r.hgetall(prefixed("hash", "user", "1"))
        print(f"Hash user:1 -> {user}")

        # 6. Key with expiration
        r.set(prefixed("temp_key"), "expires soon", ex=10)
        ttl = r.ttl(prefixed("temp_key"))
        print(f"TTL on temp_key -> {ttl} seconds")

        # 7. Leaderboard (sorted set)
        board = prefixed("leaderboard")
        r.delete(board)
        r.zincrby(board, 30, "ty")
        r.zincrby(board, 20, "sam")
        r.zincrby(board, 15, "ty")
        top = r.zrevrange(board, 0, -1, withscores=True)
        print(f"Leaderboard -> {top}")

        # 8. Unique visitors (HyperLogLog)
        hll = prefixed("visitors")
        r.delete(hll)
        r.pfadd(hll, "ty", "sam", "ty", "ada")
        print(f"HyperLogLog unique visitors -> {r.pfcount(hll)}")

        # 9. "Have we seen this id?" (Bloom filter, if the bf module is loaded)
        bloom = prefixed("seen")
        r.delete(bloom)
        try:
            r.execute_command("BF.RESERVE", bloom, 0.01, 100)
            r.execute_command("BF.ADD", bloom, "evt-1")
            seen = bool(r.execute_command("BF.EXISTS", bloom, "evt-1"))
            unseen = bool(r.execute_command("BF.EXISTS", bloom, "evt-missing"))
            print(f"Bloom seen evt-1={seen} evt-missing={unseen}")
        except redis.exceptions.ResponseError as e:
            print(f"Bloom filter not available: {e}")

        # 10. Delayed jobs (sorted set of due timestamps)
        jobs = prefixed("jobs")
        r.delete(jobs)
        now = int(time.time())
        r.zadd(jobs, {"ready-now": now - 1, "later": now + 3600})
        due = r.zrangebyscore(jobs, 0, now)
        print(f"Delayed jobs due now -> {due}")

        # 11. Server info
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
