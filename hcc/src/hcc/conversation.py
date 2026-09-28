"""ConversationState creation and deterministic transition rules."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .interpretation import requested_section_types
from .validation import assert_valid


def new_conversation_state(session_id: str, *, now: str | None = None) -> dict:
    state = {
        "session_id": session_id,
        "last_resolved_procedure_id": None,
        "last_requested_section_types": [],
        "active_filters": {"jurisdiction": None, "effective_date": None, "scope": None},
        "unresolved_references": [],
        "recent_raw_turns": [],
        "updated_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    assert_valid("conversation_state", state)
    return state


def advance_conversation_state(
    state: dict | None,
    query_text_raw: str,
    evidence_bundle: dict,
    grounded_answer: dict,
    active_filters: dict,
    *,
    now: str | None = None,
) -> dict:
    """Apply a completed turn, clearing stale procedure context on ambiguity/switch."""
    if state is None:
        raise ValueError("state is required to advance a conversation")
    updated = {**new_conversation_state(state["session_id"]), **state}
    previous_procedure = updated.get("last_resolved_procedure_id")
    resolved_procedure = evidence_bundle.get("resolved_procedure_id")
    answer_status = grounded_answer["status"]
    sections = requested_section_types(query_text_raw)
    is_correction = bool(
        re.search(r"\b(không phải|ý tôi là|sửa lại|đính chính|thay vì)\b", query_text_raw, re.IGNORECASE)
    )

    updated["active_filters"] = {
        key: active_filters.get(key)
        for key in ("jurisdiction", "effective_date", "scope")
    }
    updated["recent_raw_turns"] = [*updated.get("recent_raw_turns", []), query_text_raw][-3:]

    if evidence_bundle.get("confidence_status") == "ambiguous":
        updated["last_resolved_procedure_id"] = None
        updated["last_requested_section_types"] = []
        updated["unresolved_references"] = [query_text_raw]
    elif answer_status == "answered" and resolved_procedure:
        switched = previous_procedure not in (None, resolved_procedure) or is_correction
        updated["last_resolved_procedure_id"] = resolved_procedure
        updated["last_requested_section_types"] = sections or (
            [] if switched else updated.get("last_requested_section_types", [])
        )
        updated["unresolved_references"] = []
    elif answer_status == "clarification_needed":
        updated["unresolved_references"] = [query_text_raw]

    updated["updated_at"] = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    assert_valid("conversation_state", updated)
    return updated