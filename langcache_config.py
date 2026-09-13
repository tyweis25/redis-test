"""
Shared LangCache connection settings.

LangCache is Redis Cloud's managed semantic caching service for LLM
prompts/responses (see redis.io/docs/latest/develop/ai/langcache/).
Edit the values below, or set the matching environment variables, to
point langcache_demo.py at your LangCache cache.
"""

import os

# The regional LangCache API endpoint for your cache (the "REST API
# Endpoint" shown on your cache's details page in the Redis Cloud console).
LANGCACHE_SERVER_URL = os.getenv(
    "LANGCACHE_SERVER_URL", "https://aws-us-east-1.langcache.redis.io"
)

# The cache ID for your LangCache cache (also shown on that details page).
LANGCACHE_CACHE_ID = os.getenv("LANGCACHE_CACHE_ID", "2717482cd1664b7eae9ade2a4e7a3cd5")

# Your LangCache API key. Unlike REDIS_PASSWORD in redis_config.py, no key
# is checked in here - set it via the LANGCACHE_API_KEY environment
# variable before running the demo:
#     export LANGCACHE_API_KEY="your-api-key"
LANGCACHE_API_KEY = os.getenv("LANGCACHE_API_KEY")
