# Redis Test

Python demos against a Redis Cloud database (plus Redis Cloud Agent Memory and LangCache). Every script reads connection settings from `redis_config.py`.

## Setup

```bash
git clone https://github.com/tyweis25/redis-test.git
cd redis-test
git checkout cursor/redis-cloud-testing-c795   # branch with all demos

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Edit `redis_config.py` before running:

| Setting | Used by | Notes |
|---|---|---|
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_TLS` | redis_test, app, sessions, rate_limit, pubsub | Already filled in for Redis Cloud |
| `AGENT_MEMORY_API_KEY` | agent_memory_demo.py | Replace `<AGENT_MEMORY_API_KEY>` with a real key from [Agent Memory](https://cloud.redis.io/#/agent-memory) |
| `LANGCACHE_API_KEY` | langcache_demo.py | Replace `<LANGCACHE_API_KEY>` with a real key from the LangCache page. Do not leave a leading backtick. |

## Easiest way: the demo hub

```bash
python3 demo_hub.py
```

Open [http://localhost:5050](http://localhost:5050). One-shot scripts have a **Run** button (output shown on the page). Flask demos have **Start server**, then **Open** plus example curl commands. The sessions card also has **Log in** / **Log out**.

You can still run each demo from a terminal instead — details below.

---

## One-shot scripts

### `redis_test.py` — basic connectivity

What it does: PING, string set/get, INCR a counter, list RPUSH/LRANGE, hash HSET/HGETALL, a 10-second TTL key, and `INFO server`.

```bash
python3 redis_test.py
```

Expect: `PING -> True`, counter `2`, list `['a', 'b', 'c']`, hash `{name: Ty, role: tester}`, Redis 8.x.

Leaves `greeting`, `counter`, `mylist`, and `user:1` (a **hash**) with no TTL. That `user:1` hash collides with `app.py`'s `user:1` **string** cache key — if you run this then `app.py`, you'll get `WRONGTYPE`. Delete the key first: `redis-cli DEL user:1`, or just wait and use a different user id (`/users/2`).

### `pubsub_publisher.py` + `pubsub_subscriber.py` — live notifications

What it does: subscriber listens on the `notifications` channel; publisher sends 4 messages. Pub/Sub is fire-and-forget — if nobody is subscribed, the message is gone.

```bash
# Terminal 1 first:
python3 pubsub_subscriber.py

# Terminal 2:
python3 pubsub_publisher.py
```

Or click **Run** on the hub (it starts both for you). Expect 4 `Received:` lines and `delivered to 1 subscriber(s)`.

### `agent_memory_demo.py` — Redis Cloud Agent Memory

What it does: talks to the managed Agent Memory HTTPS service (not the Redis database). Adds a short-term session event, reads it back, stores a long-term fact, then searches it.

```bash
# First: set AGENT_MEMORY_API_KEY in redis_config.py
python3 agent_memory_demo.py
```

A placeholder key fails cleanly with 403. A real key prints session memory and search results.

### `langcache_demo.py` — semantic LLM cache

What it does: stores `prompt="How does semantic caching work?"` / a canned response, then searches with `"What is semantic caching?"`. A hit via `SearchStrategy.SEMANTIC` (~96% similarity) proves meaning-based matching, not exact text.

```bash
# First: set LANGCACHE_API_KEY in redis_config.py
python3 langcache_demo.py
```

Expect: an `entry_id` on save, then a `CacheEntry` on search.

---

## Long-running Flask demos

Start each in its own terminal (or use **Start server** in the hub). None of these define a `/` route — open the paths below, not `http://localhost:PORT/`.

### `app.py` — cache-aside (port 5000)

What it does: `/users/<id>` sleeps 2 seconds to fake a DB query, then caches the JSON in Redis for 30 seconds. Repeat requests are fast until you invalidate or the TTL expires.

```bash
python3 app.py
```

```bash
curl http://localhost:5000/health          # {"status":"ok","redis":"connected"}
curl http://localhost:5000/users/1         # ~2s, "source": "database"
curl http://localhost:5000/users/1         # ~0.06s, "source": "cache"
curl -X DELETE http://localhost:5000/cache/users/1
curl http://localhost:5000/users/1         # miss again
```

### `sessions_demo.py` — Redis-backed sessions (port 5001)

What it does: `/login` creates an opaque `session_id` cookie and stores `{username, logged_in_at}` in Redis (5-minute TTL, sliding). `/profile` reads it. `/logout` deletes it. Opening `/profile` with no cookie returns `{"error":"not logged in"}` — that's correct, not a failure.

```bash
python3 sessions_demo.py
```

From the hub: **Log in** (username `ty`) → **Open** `/profile` → **Log out** → **Open** again.

From the terminal (cookie jar required):

```bash
curl -c cookies.txt -X POST http://localhost:5001/login \
     -H "Content-Type: application/json" -d '{"username": "ty"}'
curl -b cookies.txt http://localhost:5001/profile
curl -b cookies.txt -X POST http://localhost:5001/logout
curl -b cookies.txt http://localhost:5001/profile   # rejected
```

### `rate_limit_demo.py` — fixed-window limiter (port 5002)

What it does: 5 requests per client IP per 30-second window, counted with Redis `INCR`. Extra requests get HTTP 429.

```bash
python3 rate_limit_demo.py
```

```bash
for i in $(seq 1 8); do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/api/data
done
# 200, 200, 200, 200, 200, 429, 429, 429
```

---

## Files

| File | Role |
|---|---|
| `redis_config.py` | Host, port, password, TLS, Agent Memory, LangCache |
| `demo_hub.py` | Web UI at `:5050` that runs/starts everything |
| `requirements.txt` | `redis`, `flask`, `redis-agent-memory`, `langcache` |
