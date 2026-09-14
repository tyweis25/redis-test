"""JSON + FT.SEARCH + vector KNN eval for search_demo.py."""

from __future__ import annotations

import json
import time

import redis

from evals.common import Check, redis_client
from redis_config import prefixed
from search_demo import INDEX, PREFIX, ensure_index, pack_vector, search_results


def run() -> list[Check]:
    checks: list[Check] = []
    r = redis_client()
    try:
        ensure_index(r)
    except redis.exceptions.ResponseError as e:
        return [Check("search_module_available", False, str(e), skipped=True)]

    docs = {
        "apple-red": {"name": "Red apple", "category": "fruit", "embedding": [1.0, 0.0, 0.0, 0.0]},
        "apple-green": {"name": "Green apple", "category": "fruit", "embedding": [0.9, 0.1, 0.0, 0.0]},
        "redis-book": {"name": "Redis in Action", "category": "book", "embedding": [0.0, 0.0, 1.0, 0.0]},
    }
    for slug, doc in docs.items():
        r.execute_command("JSON.SET", f"{PREFIX}{slug}", "$", json.dumps(doc))

    raw = r.execute_command("JSON.GET", f"{PREFIX}apple-red")
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(parsed, list):
        parsed = parsed[0]
    checks.append(Check(
        "json_round_trip",
        isinstance(parsed, dict) and parsed.get("name") == "Red apple",
        f"got={parsed!r}",
    ))

    time.sleep(0.25)
    fruit = search_results(r.execute_command("FT.SEARCH", INDEX, "@category:{fruit}"))
    fruit_ids = {row["id"] for row in fruit}
    checks.append(Check(
        "tag_search_returns_only_fruit",
        f"{PREFIX}apple-red" in fruit_ids
        and f"{PREFIX}apple-green" in fruit_ids
        and f"{PREFIX}redis-book" not in fruit_ids,
        f"ids={fruit_ids}",
    ))

    knn = search_results(r.execute_command(
        "FT.SEARCH", INDEX, "*=>[KNN 3 @embedding $vec AS score]",
        "PARAMS", "2", "vec", pack_vector(1.0, 0.0, 0.0, 0.0),
        "RETURN", "3", "name", "category", "score",
        "DIALECT", "2",
    ))
    top_id = knn[0]["id"] if knn else None
    checks.append(Check(
        "knn_ranks_red_apple_first",
        top_id == f"{PREFIX}apple-red" and len(knn) >= 2,
        f"order={[row['id'] for row in knn]}",
    ))

    try:
        r.execute_command("FT.DROPINDEX", INDEX)
    except redis.exceptions.ResponseError:
        pass
    for slug in docs:
        r.delete(f"{PREFIX}{slug}")
    return checks
