"""
Redis 8 query + vector demo (JSON documents, FT.SEARCH, KNN).

This Cloud database has ReJSON and RediSearch. We store a tiny catalog
as JSON, index TEXT/TAG plus a 4-dim embedding, then:

  1. Filter by tag (role / category) — secondary index, not SCAN
  2. KNN vector search — "what is similar?", vs LangCache's
     "have we already answered this prompt?"

Embeddings here are hand-built so the script needs no model API key.

Install:
    pip3 install redis

Run:
    python3 search_demo.py
"""

from __future__ import annotations

import json
import struct
import time

import redis

from redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_TLS, prefixed

INDEX = "demo:idx:catalog"
PREFIX = prefixed("catalog") + ":"


def connect():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        ssl=REDIS_TLS,
        decode_responses=True,
    )


def pack_vector(*values: float) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def search_results(raw):
    """Normalize FT.SEARCH RESP2 lists and RESP3 dicts to [{id, fields}]."""
    if isinstance(raw, dict):
        out = []
        for row in raw.get("results") or []:
            out.append({
                "id": row.get("id"),
                "fields": row.get("extra_attributes") or {},
            })
        return out
    # RESP2: [total, id1, [k, v, ...], id2, ...]
    if not raw:
        return []
    items = []
    i = 1
    while i < len(raw):
        doc_id = raw[i]
        fields = {}
        if i + 1 < len(raw) and isinstance(raw[i + 1], (list, tuple)):
            pairs = raw[i + 1]
            fields = dict(zip(pairs[0::2], pairs[1::2]))
            i += 2
        else:
            i += 1
        items.append({"id": doc_id, "fields": fields})
    return items


def ensure_index(r: redis.Redis):
    try:
        r.execute_command("FT.DROPINDEX", INDEX)
    except redis.exceptions.ResponseError:
        pass
    r.execute_command(
        "FT.CREATE", INDEX, "ON", "JSON", "PREFIX", "1", PREFIX,
        "SCHEMA",
        "$.name", "AS", "name", "TEXT",
        "$.category", "AS", "category", "TAG",
        "$.embedding", "AS", "embedding", "VECTOR", "FLAT", "6",
        "TYPE", "FLOAT32", "DIM", "4", "DISTANCE_METRIC", "COSINE",
    )


def main():
    r = connect()
    ensure_index(r)

    docs = [
        ("apple-red", {
            "name": "Red apple",
            "category": "fruit",
            "embedding": [1.0, 0.0, 0.0, 0.0],
        }),
        ("apple-green", {
            "name": "Green apple",
            "category": "fruit",
            "embedding": [0.9, 0.1, 0.0, 0.0],
        }),
        ("redis-book", {
            "name": "Redis in Action",
            "category": "book",
            "embedding": [0.0, 0.0, 1.0, 0.0],
        }),
    ]
    for slug, doc in docs:
        r.execute_command("JSON.SET", f"{PREFIX}{slug}", "$", json.dumps(doc))
        print(f"JSON.SET {PREFIX}{slug}")

    time.sleep(0.2)
    tagged = search_results(r.execute_command("FT.SEARCH", INDEX, "@category:{fruit}"))
    print(f"Tag search category=fruit -> {[row['id'] for row in tagged]}")

    knn = search_results(r.execute_command(
        "FT.SEARCH", INDEX, "*=>[KNN 3 @embedding $vec AS score]",
        "PARAMS", "2", "vec", pack_vector(1.0, 0.0, 0.0, 0.0),
        "RETURN", "3", "name", "category", "score",
        "DIALECT", "2",
    ))
    print("KNN near [1,0,0,0] (red apple):")
    for row in knn:
        print(f"  {row['id']} {row['fields']}")

    print("LangCache answers 'did we already answer this prompt?';")
    print("this index answers 'which catalog items are nearby in vector space?'")

    try:
        r.execute_command("FT.DROPINDEX", INDEX)
    except redis.exceptions.ResponseError:
        pass
    for slug, _doc in docs:
        r.delete(f"{PREFIX}{slug}")


if __name__ == "__main__":
    main()
