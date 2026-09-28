"""Request orchestration: interpret -> retrieve -> branch -> ground -> generate -> verify."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from . import templates
from .grounding import check_sufficiency, verify_citations
from .conversation import advance_conversation_state
from .interfaces import AuditLog, ConversationStore, Generator, Retriever, Segmenter
from .interpretation import interpret, requested_section_types
from .validation import assert_valid, assert_valid_cross_objects

logger = logging.getLogger("hcc.pipeline")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Pipeline:
    def __init__(
        self,
        segmenter: Segmenter,
        retriever: Retriever,
        generator: Generator,
        clock: Callable[[], str] = _now_iso,
        conversation_store: ConversationStore | None = None,
        audit_log: AuditLog | None = None,
    ):
        self.segmenter = segmenter
        self.retriever = retriever
        self.generator = generator
        self.clock = clock
        self.conversation_store = conversation_store
        self.audit_log = audit_log

    def answer(
        self,
        query_text_raw: str,
        *,
        filters: dict | None = None,
        state: dict | None = None,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Return a GroundedAnswer (dict) for one request."""
        if state is None and session_id and self.conversation_store:
            state = self.conversation_store.get_conversation_state(session_id)
            if state is None:
                from .conversation import new_conversation_state

                state = new_conversation_state(session_id, now=self.clock())
        retrieval_input = interpret(
            query_text_raw, self.segmenter, filters=filters, state=state, top_k=top_k
        )
        assert_valid("retrieval_input", retrieval_input)

        retrieve_with_state = getattr(self.retriever, "retrieve_with_state", None)
        if callable(retrieve_with_state):
            bundle = retrieve_with_state(retrieval_input, state)
        else:
            bundle = self.retriever.retrieve(retrieval_input)
        assert_valid("evidence_bundle", bundle)
        assert_valid_cross_objects(
            retrieval_input=retrieval_input,
            evidence_bundle=bundle,
        )

        status = bundle["confidence_status"]

        if status == "low_confidence":
            result = self._finish("insufficient_data", bundle, prompt=templates.NO_MATCH_PROMPT)
        elif status == "ambiguous":
            candidates = bundle.get("ambiguous_candidates", [])
            if not candidates:
                logger.error("bundle %s is ambiguous but has no candidates", bundle["bundle_id"])
                result = self._finish("insufficient_data", bundle, prompt=templates.NO_MATCH_PROMPT)
            else:
                result = self._finish(
                    "clarification_needed", bundle, prompt=templates.clarification_prompt(candidates)
                )
        else:
            requested = requested_section_types(query_text_raw)
            pre = check_sufficiency(bundle, requested)
            if not pre.ok:
                logger.warning("insufficient evidence for %s: %s", bundle["bundle_id"], pre.problems)
                result = self._finish(
                    "insufficient_data", bundle, prompt=templates.INSUFFICIENT_EVIDENCE_PROMPT
                )
            else:
                generated = self.generator.generate(bundle)
                answer_text = generated.get("answer_text", "")
                citations = generated.get("citations", [])
                post = verify_citations(bundle, answer_text, citations)
                if not post.ok:
                    logger.warning("citation check failed for %s: %s", bundle["bundle_id"], post.problems)
                    result = self._finish(
                        "insufficient_data", bundle, prompt=templates.INSUFFICIENT_EVIDENCE_PROMPT
                    )
                else:
                    result = self._finish("answered", bundle, answer_text=answer_text, citations=citations)

        if state is not None:
            updated_state = advance_conversation_state(
                state,
                query_text_raw,
                bundle,
                result,
                retrieval_input["filters"],
                now=self.clock(),
            )
            if self.conversation_store:
                self.conversation_store.save_conversation_state(updated_state)
        if self.audit_log:
            self.audit_log.record(
                "answer_completed",
                retrieval_input["conversation_session_id"],
                {"retrieval_input": retrieval_input, "evidence_bundle": bundle, "grounded_answer": result},
            )
        return result

    def _finish(
        self,
        status: str,
        bundle: dict,
        *,
        answer_text: str = "",
        prompt: str | None = None,
        citations: list[dict] | None = None,
    ) -> dict:
        result = {
            "status": status,
            "answer_text": answer_text,
            "clarification_prompt": prompt,
            "citations": citations or [],
            "evidence_bundle_id": bundle["bundle_id"],
            "created_at": self.clock(),
        }
        assert_valid("grounded_answer", result)
        return result
