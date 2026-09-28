"""The seams between tracks. Each real component must satisfy one of these.

Objects are plain dicts that validate against the JSON Schemas in ./schemas.
"""
from __future__ import annotations

from typing import Protocol


class Segmenter(Protocol):
    """Person 1 owns the real implementation (underthesea / pyvi / VnCoreNLP)."""

    def segment(self, text: str) -> str: ...


class Retriever(Protocol):
    """Person 1 owns the real implementation. RetrievalInput -> EvidenceBundle."""

    def retrieve(self, retrieval_input: dict) -> dict: ...


class StatefulRetriever(Protocol):
    """Optional extension for retrieval that needs structured follow-up context."""

    def retrieve_with_state(self, retrieval_input: dict, conversation_state: dict | None) -> dict: ...


class Generator(Protocol):
    """Person 3 owns the real implementation.

    Receives a resolved EvidenceBundle and returns
    {"answer_text": str, "citations": [Citation, ...]}.
    """

    def generate(self, evidence_bundle: dict) -> dict: ...


class ConversationStore(Protocol):
    """Durable or in-memory persistence for the fixed ConversationState contract."""

    def get_conversation_state(self, session_id: str) -> dict | None: ...

    def save_conversation_state(self, state: dict) -> None: ...


class AuditLog(Protocol):
    """Append-only request audit sink; implementations must avoid storing secrets."""

    def record(self, event_type: str, session_id: str | None, payload: dict) -> None: ...
