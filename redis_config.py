"""
Shared Redis connection settings.

Edit the values below to point every script at either your local
Redis (Rancher Desktop) or Redis Cloud. All the other scripts import
from this file, so you only need to change it in one place.
"""

# --- Option 1: Local Redis (Rancher Desktop) ---
# Requires: kubectl port-forward svc/my-redis-master 6379:6379
# REDIS_HOST = "localhost"
# REDIS_PORT = 6379
# REDIS_PASSWORD = None
# REDIS_TLS = False

# --- Option 2: Redis Cloud (currently active) ---
# If you ever rotate this password in the Redis Cloud console, update
# it here too.
REDIS_HOST = "pancake-navy-steel-71454.db.redis.io"
REDIS_PORT = 14142
REDIS_PASSWORD = "HCNzJ6hPI2yRiCfzn2JqcJDsRvgDjYbt"
REDIS_TLS = False  # this database's connection string used redis:// (not rediss://)
# If scripts fail with an SSL/handshake-related error, try flipping
# REDIS_TLS to True instead.

# Namespace every demo/eval key so scripts don't collide (e.g. redis_test.py
# used to leave a hash at user:1 that broke app.py's string cache key).
KEY_PREFIX = "demo"


def prefixed(*parts: str) -> str:
    """Build a Redis key like demo:cache:user:1."""
    return ":".join((KEY_PREFIX, *parts))

# --- Redis Cloud Agent Memory (used by agent_memory_demo.py) ---
# Settings for the `redis_agent_memory` SDK, which talks to a Redis Cloud
# Agent Memory store (https://cloud.redis.io/#/agent-memory) rather than a
# plain Redis database. Find these values on the store's page in the Redis
# Cloud console.
AGENT_MEMORY_BASE_URL = "https://aws-us-east-1.memory.redis.io"
AGENT_MEMORY_STORE_ID = "2b6f7a2569f64665b030a10695021eee"
# Replace this with the real API key from the Redis Cloud console before
# running agent_memory_demo.py - it will fail with an auth error otherwise.
AGENT_MEMORY_API_KEY = "<AGENT_MEMORY_API_KEY>"

# --- Redis LangCache (used by langcache_demo.py) ---
# Settings for the `langcache` SDK, which talks to a Redis Cloud LangCache
# semantic-caching service (https://redis.io/docs/latest/develop/ai/langcache/)
# rather than a plain Redis database. Find these values on your cache's
# details page in the Redis Cloud console.
LANGCACHE_SERVER_URL = "https://aws-us-east-1.langcache.redis.io"
LANGCACHE_CACHE_ID = "2717482cd1664b7eae9ade2a4e7a3cd5"
# Replace this with the real API key from the Redis Cloud console before
# running langcache_demo.py - it will fail with an auth error otherwise.
LANGCACHE_API_KEY = "<LANGCACHE_API_KEY>"
