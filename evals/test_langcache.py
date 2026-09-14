"""LangCache retrieval eval: paraphrase hits, negatives, attributes, TTL."""

from __future__ import annotations

import time
import uuid

from langcache import LangCache
from langcache.errors import LangCacheError

from evals.common import Check
from redis_config import LANGCACHE_API_KEY, LANGCACHE_CACHE_ID, LANGCACHE_SERVER_URL

PAIRS = [
    ("How does semantic caching work?", "What is semantic caching?", True),
    ("How do I reset my password?", "What is the process to change my password?", True),
    ("Where is the nearest coffee shop?", "Find a cafe close to me", True),
    ("What is the capital of France?", "Which city is France's capital?", True),
    ("How does semantic caching work?", "What is a B-tree index used for?", False),
    ("How do I reset my password?", "Recommend a science fiction novel", False),
]


def _hits(res):
    return list(getattr(res, "data", None) or [])


def _placeholder(key: str | None) -> bool:
    return not key or key.startswith("<") or key == "fake-test-key-12345"


def run() -> list[Check]:
    if _placeholder(LANGCACHE_API_KEY):
        return [Check(
            "langcache_api_key_configured",
            False,
            "LANGCACHE_API_KEY is a placeholder — set a real key in redis_config.py",
            skipped=True,
        )]

    checks: list[Check] = []
    attr = {"eval": f"suite-{uuid.uuid4().hex[:8]}"}
    try:
        with LangCache(
            server_url=LANGCACHE_SERVER_URL,
            cache_id=LANGCACHE_CACHE_ID,
            api_key=LANGCACHE_API_KEY,
        ) as cache:
            stored = {}
            for prompt, _query, _should_hit in PAIRS:
                if prompt in stored:
                    continue
                try:
                    saved = cache.set(
                        prompt=prompt,
                        response=f"cached answer for: {prompt}",
                        attributes=attr,
                        ttl_millis=180_000,
                    )
                except LangCacheError:
                    saved = cache.set(
                        prompt=prompt,
                        response=f"cached answer for: {prompt}",
                        ttl_millis=180_000,
                    )
                    attr = None
                stored[prompt] = getattr(saved, "entry_id", None)

            checks.append(Check("set_unique_prompts", len(stored) >= 4, f"stored={list(stored)}"))

            tp = fp = tn = fn = 0
            similarities = []
            for prompt, query, should_hit in PAIRS:
                kwargs = {"prompt": query}
                if attr:
                    kwargs["attributes"] = attr
                res = cache.search(**kwargs)
                entries = _hits(res)
                hit = bool(entries)
                sim = getattr(entries[0], "similarity", None) if entries else None
                if sim is not None:
                    similarities.append(sim)
                if should_hit and hit:
                    tp += 1
                elif should_hit and not hit:
                    fn += 1
                elif not should_hit and hit:
                    fp += 1
                else:
                    tn += 1

            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            checks.append(Check(
                "retrieval_precision_at_1",
                precision >= 0.5,
                f"P={precision:.2f} R={recall:.2f} tp={tp} fp={fp} tn={tn} fn={fn} sims={similarities}",
                extra={"precision": precision, "recall": recall, "similarities": similarities},
            ))

            exact = cache.search(prompt="How does semantic caching work?", attributes=attr) if attr else cache.search(prompt="How does semantic caching work?")
            exact_hits = _hits(exact)
            strategy = str(getattr(exact_hits[0], "search_strategy", "")) if exact_hits else ""
            checks.append(Check(
                "exact_or_semantic_hit_on_same_prompt",
                bool(exact_hits),
                f"strategy={strategy} n={len(exact_hits)}",
            ))

            if attr:
                filtered = cache.search(prompt="How does semantic caching work?", attributes={"eval": "no-such-run"})
                checks.append(Check(
                    "attribute_filter_excludes_other_runs",
                    len(_hits(filtered)) == 0,
                    f"hits={_hits(filtered)}",
                ))

            ttl_prompt = f"ttl probe {uuid.uuid4().hex[:6]}"
            cache.set(prompt=ttl_prompt, response="ephemeral", ttl_millis=1500, attributes=attr)
            time.sleep(2.2)
            after = cache.search(prompt=ttl_prompt, attributes=attr) if attr else cache.search(prompt=ttl_prompt)
            checks.append(Check(
                "short_ttl_entry_expires",
                len(_hits(after)) == 0,
                f"hits after 2.2s={len(_hits(after))}",
            ))

            if attr:
                try:
                    cache.delete_query(attributes=attr)
                except LangCacheError:
                    pass
    except LangCacheError as e:
        checks.append(Check("langcache_reachable", False, f"{e}"))
    return checks
