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
