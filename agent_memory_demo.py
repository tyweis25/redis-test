"""
Redis Agent Memory demo.

Redis Cloud Agent Memory is a managed service for storing and retrieving
memory for AI agents: short-term "session" memory (the running
conversation) and long-term memory (facts/preferences worth keeping
around after the conversation ends). This talks to it over HTTPS via the
`redis_agent_memory` SDK - it's a separate service from a plain Redis
database, so it doesn't use the `redis` package or REDIS_HOST/PORT at all.

Install:
    pip3 install redis-agent-memory

Configure:
    Fill in AGENT_MEMORY_API_KEY in redis_config.py with a real API key
    from the Redis Cloud console (https://cloud.redis.io/#/agent-memory).
    AGENT_MEMORY_BASE_URL and AGENT_MEMORY_STORE_ID are already set there.

Run:
    python3 agent_memory_demo.py
"""

import time

from redis_agent_memory import AgentMemory, models
from redis_agent_memory.errors import AgentMemoryError, NotFoundErrorResponseContent

from redis_config import AGENT_MEMORY_API_KEY, AGENT_MEMORY_BASE_URL, AGENT_MEMORY_STORE_ID

SESSION_ID = "session-1"


def main():
    try:
        with AgentMemory(
            AGENT_MEMORY_BASE_URL,
            store_id=AGENT_MEMORY_STORE_ID,
            api_key=AGENT_MEMORY_API_KEY,
        ) as agent_memory:
            # 1. Add an event to a session's short-term memory
            agent_memory.add_session_event(
                session_id=SESSION_ID,
                actor_id="user-123",
                role=models.MessageRole.USER,
                content=[{"text": "What is semantic memory?"}],
                created_at=int(time.time() * 1000),
            )

            # 2. Read back the session's memory
            session = agent_memory.get_session_memory(session_id=SESSION_ID)
            print("Session memory:\n", session)

            # 3. Store a fact in long-term memory
            agent_memory.bulk_create_long_term_memories(memories=[
                {
                    "id": "memory-1",
                    "text": "Semantic memory stores facts and knowledge for later retrieval.",
                    "owner_id": "user-123",
                },
            ])

            # 4. Search long-term memory
            results = agent_memory.search_long_term_memory(request={"text": "What is semantic memory?"})
            print("Search results:\n", results)

            # Session is short-term. Deleting it must not erase long-term facts.
            agent_memory.delete_session_memory(session_id=SESSION_ID)
            try:
                gone = agent_memory.get_session_memory(session_id=SESSION_ID)
                print("Session after delete:\n", gone)
            except NotFoundErrorResponseContent:
                print("Session after delete: 404 Session Not Found (expected)")
            still = agent_memory.search_long_term_memory(request={"text": "What is semantic memory?"})
            print("Long-term search after session delete:\n", still)

    except AgentMemoryError as e:
        print(f"Agent Memory request failed: {e}")
        print("Double-check AGENT_MEMORY_API_KEY (and STORE_ID/BASE_URL) in redis_config.py.")


if __name__ == "__main__":
    main()
