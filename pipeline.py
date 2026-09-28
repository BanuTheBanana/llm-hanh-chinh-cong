"""Request orchestration: interpret -> retrieve -> branch -> ground -> generate -> verify."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from . import templates
from .grounding import check_sufficiency, verify_citations
from .interfaces import Generator, Retriever, Segmenter
from .interpretation import interpret
from .validation import assert_valid

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
    ):
        self.segmenter = segmenter
        self.retriever = retriever
        self.generator = generator
        self.clock = clock

    def answer(
        self,
        query_text_raw: str,
        *,
        filters: dict | None = None,
        state: dict | None = None,
        top_k: int = 5,
    ) -> dict:
        """Return a GroundedAnswer (dict) for one request."""
        retrieval_input = interpret(
            query_text_raw, self.segmenter, filters=filters, state=state, top_k=top_k
        )
        assert_valid("retrieval_input", retrieval_input)

        bundle = self.retriever.retrieve(retrieval_input)
        assert_valid("evidence_bundle", bundle)

        status = bundle["confidence_status"]

        if status == "low_confidence":
            return self._finish("insufficient_data", bundle, prompt=templates.NO_MATCH_PROMPT)

        if status == "ambiguous":
            candidates = bundle.get("ambiguous_candidates", [])
            if not candidates:
                logger.error("bundle %s is ambiguous but has no candidates", bundle["bundle_id"])
                return self._finish("insufficient_data", bundle, prompt=templates.NO_MATCH_PROMPT)
            return self._finish(
                "clarification_needed", bundle, prompt=templates.clarification_prompt(candidates)
            )

        # status == "resolved": only now is there evidence worth grounding on.
        pre = check_sufficiency(bundle)
        if not pre.ok:
            logger.warning("insufficient evidence for %s: %s", bundle["bundle_id"], pre.problems)
            return self._finish(
                "insufficient_data", bundle, prompt=templates.INSUFFICIENT_EVIDENCE_PROMPT
            )

        generated = self.generator.generate(bundle)
        answer_text = generated.get("answer_text", "")
        citations = generated.get("citations", [])

        post = verify_citations(bundle, answer_text, citations)
        if not post.ok:
            logger.warning("citation check failed for %s: %s", bundle["bundle_id"], post.problems)
            return self._finish(
                "insufficient_data", bundle, prompt=templates.INSUFFICIENT_EVIDENCE_PROMPT
            )

        return self._finish("answered", bundle, answer_text=answer_text, citations=citations)

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
