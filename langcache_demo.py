"""
Redis LangCache demo - semantic caching for LLM prompts/responses.

LangCache is Redis Cloud's managed semantic caching service: instead of
matching on exact prompt text, it caches based on *meaning*. A
differently-worded prompt that means roughly the same thing as one
you've already cached can still hit the cache, skipping a slow/expensive
LLM call. This is the hosted-service counterpart to running your own
semantic cache against a self-managed Redis instance.

Install:
    pip3 install langcache

Configure:
    Fill in LANGCACHE_API_KEY in redis_config.py with a real API key
    from the Redis Cloud console (https://redis.io/docs/latest/develop/ai/langcache/).
    LANGCACHE_SERVER_URL and LANGCACHE_CACHE_ID are already set there.

Run:
    python3 langcache_demo.py
"""

from langcache import LangCache
from langcache.errors import LangCacheError

from redis_config import LANGCACHE_API_KEY, LANGCACHE_CACHE_ID, LANGCACHE_SERVER_URL


def main():
    try:
        with LangCache(
            server_url=LANGCACHE_SERVER_URL,
            cache_id=LANGCACHE_CACHE_ID,
            api_key=LANGCACHE_API_KEY,
        ) as lang_cache:

            # Save an entry - the prompt/response pair is embedded and
            # stored so semantically similar future prompts can reuse it.
            save_response = lang_cache.set(
                prompt="How does semantic caching work?",
                response="Semantic caching stores and retrieves data based on meaning, not exact matches.",
            )
            print("Save entry response:\n", save_response)

            # Search with a differently-worded prompt that means the same
            # thing - semantic search should still surface the entry above.
            search_response = lang_cache.search(
                prompt="What is semantic caching?"
            )
            print("Search entry response:\n", search_response)

            # Tenant isolation: same prompt, different attributes, must not leak.
            try:
                lang_cache.set(
                    prompt="What is my plan?",
                    response="acme enterprise plan",
                    attributes={"tenant": "acme"},
                )
                lang_cache.set(
                    prompt="What is my plan?",
                    response="globex starter plan",
                    attributes={"tenant": "globex"},
                )
                acme = lang_cache.search(prompt="What is my plan?", attributes={"tenant": "acme"})
                globex = lang_cache.search(prompt="What is my plan?", attributes={"tenant": "globex"})
                print("Tenant acme search:\n", acme)
                print("Tenant globex search:\n", globex)
            except LangCacheError as e:
                print(f"Tenant attributes not available on this cache: {e}")

    except LangCacheError as e:
        print(f"LangCache request failed: {e}")
        print("Double-check LANGCACHE_API_KEY (and CACHE_ID/SERVER_URL) in redis_config.py.")


if __name__ == "__main__":
    main()
