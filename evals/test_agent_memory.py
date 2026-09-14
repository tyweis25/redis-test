"""Agent Memory eval: session isolation, search relevance, delete."""

from __future__ import annotations

import time
import uuid

from redis_agent_memory import AgentMemory, models
from redis_agent_memory.errors import AgentMemoryError, NotFoundErrorResponseContent

from evals.common import Check
from redis_config import AGENT_MEMORY_API_KEY, AGENT_MEMORY_BASE_URL, AGENT_MEMORY_STORE_ID


def _placeholder(key: str | None) -> bool:
    return not key or key.startswith("<")


def _event_text(event) -> str:
    content = getattr(event, "content", None) or []
    bits = []
    for part in content:
        if isinstance(part, dict):
            bits.append(part.get("text", ""))
        else:
            bits.append(getattr(part, "text", "") or str(part))
    return " ".join(bits)


def run() -> list[Check]:
    if _placeholder(AGENT_MEMORY_API_KEY):
        return [Check(
            "agent_memory_api_key_configured",
            False,
            "AGENT_MEMORY_API_KEY is a placeholder — set a real key in redis_config.py",
            skipped=True,
        )]

    checks: list[Check] = []
    run_id = uuid.uuid4().hex[:8]
    session_a = f"eval-a-{run_id}"
    session_b = f"eval-b-{run_id}"
    owner = f"eval-owner-{run_id}"
    mem_id = f"eval-mem-{run_id}"
    decoy_id = f"eval-decoy-{run_id}"
    now = int(time.time() * 1000)

    try:
        with AgentMemory(
            AGENT_MEMORY_BASE_URL,
            store_id=AGENT_MEMORY_STORE_ID,
            api_key=AGENT_MEMORY_API_KEY,
        ) as am:
            am.add_session_event(
                session_id=session_a,
                actor_id=owner,
                role=models.MessageRole.USER,
                content=[{"text": f"secret token alpha-{run_id}"}],
                created_at=now,
            )
            am.add_session_event(
                session_id=session_b,
                actor_id=owner,
                role=models.MessageRole.USER,
                content=[{"text": f"secret token beta-{run_id}"}],
                created_at=now,
            )
            mem_a = am.get_session_memory(session_id=session_a)
            mem_b = am.get_session_memory(session_id=session_b)
            text_a = " ".join(_event_text(e) for e in (mem_a.events or []))
            text_b = " ".join(_event_text(e) for e in (mem_b.events or []))
            checks.append(Check(
                "session_a_has_its_event",
                f"alpha-{run_id}" in text_a,
                text_a[:200],
            ))
            checks.append(Check(
                "sessions_do_not_leak",
                f"alpha-{run_id}" not in text_b and f"beta-{run_id}" not in text_a,
                f"a={text_a[:120]!r} b={text_b[:120]!r}",
            ))

            fact = f"The eval mascot for run {run_id} is a crimson axolotl."
            decoy = f"Unrelated decoy fact {run_id}: bananas are berries."
            am.bulk_create_long_term_memories(memories=[
                {"id": mem_id, "text": fact, "owner_id": owner},
                {"id": decoy_id, "text": decoy, "owner_id": owner},
            ])
            results = am.search_long_term_memory(request={"text": f"What is the eval mascot for run {run_id}?"})
            items = list(getattr(results, "items", None) or [])
            top_id = getattr(items[0], "id", None) if items else None
            top_text = getattr(items[0], "text", "") if items else ""
            checks.append(Check(
                "long_term_search_recall_at_1",
                top_id == mem_id or "axolotl" in str(top_text).lower(),
                f"top_id={top_id} n={len(items)} text={top_text!r}",
            ))

            am.delete_session_memory(session_id=session_a)
            try:
                gone = am.get_session_memory(session_id=session_a)
                gone_events = list(getattr(gone, "events", None) or [])
                checks.append(Check(
                    "delete_session_memory",
                    len(gone_events) == 0,
                    f"events after delete={len(gone_events)}",
                ))
            except NotFoundErrorResponseContent as e:
                # Correct API behavior: a deleted session is gone, not empty.
                checks.append(Check(
                    "delete_session_memory",
                    True,
                    f"GET after delete is 404 Session Not Found ({e})",
                ))

            still = am.search_long_term_memory(
                request={"text": f"What is the eval mascot for run {run_id}?"}
            )
            still_items = list(getattr(still, "items", None) or [])
            still_text = getattr(still_items[0], "text", "") if still_items else ""
            still_id = getattr(still_items[0], "id", None) if still_items else None
            checks.append(Check(
                "long_term_survives_session_delete",
                "axolotl" in str(still_text).lower() or still_id == mem_id,
                f"n={len(still_items)} text={still_text!r}",
            ))

            try:
                am.delete_session_memory(session_id=session_b)
                am.bulk_delete_long_term_memories(memory_ids=[mem_id, decoy_id])
            except AgentMemoryError:
                pass
    except AgentMemoryError as e:
        checks.append(Check("agent_memory_unexpected_error", False, str(e)))
    return checks
