"""
Redis LangCache demo - semantic caching for LLM prompts/responses.

LangCache is Redis Cloud's managed semantic caching service: instead of
matching on exact prompt text, it caches based on *meaning*. A
differently-worded prompt that means roughly the same thing as one
you've already cached can still hit the cache, skipping a slow/expensive
LLM call. This is the hosted-service counterpart to running your own
semantic cache against a self-managed Redis instance.

Connection settings (server URL, cache ID, API key) come from
langcache_config.py - see that file for how to configure them.

Install:
    pip3 install langcache

Run:
    export LANGCACHE_API_KEY="your-api-key"
    python3 langcache_demo.py
"""

import sys

from langcache import LangCache
from langcache import errors as langcache_errors

from langcache_config import LANGCACHE_API_KEY, LANGCACHE_CACHE_ID, LANGCACHE_SERVER_URL


def main():
    if not LANGCACHE_API_KEY:
        print("LANGCACHE_API_KEY is not set.")
        print("Set it via the LANGCACHE_API_KEY environment variable (see")
        print("langcache_config.py), then re-run this script.")
        sys.exit(1)

    print(f"Connecting to LangCache at {LANGCACHE_SERVER_URL} (cache_id={LANGCACHE_CACHE_ID}) ...")

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
            print(f"Save entry response:\n{save_response}\n")

            # Search with a differently-worded prompt that means the same
            # thing - semantic search should still surface the entry above.
            search_response = lang_cache.search(
                prompt="What is semantic caching?"
            )
            print(f"Search entry response:\n{search_response}\n")

        print("Done - LangCache save + search both succeeded.")

    except langcache_errors.LangCacheError as e:
        print(f"LangCache request failed: {e.message} (status {e.status_code})")
        print("Double-check LANGCACHE_SERVER_URL, LANGCACHE_CACHE_ID, and LANGCACHE_API_KEY.")
        sys.exit(1)


if __name__ == "__main__":
    main()
