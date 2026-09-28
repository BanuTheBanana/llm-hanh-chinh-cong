"""Mock components so this track can run end to end before the others exist."""
from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


class StubSegmenter:
    """Placeholder until Person 1's real segment() exists: only normalizes whitespace."""

    def segment(self, text: str) -> str:
        return " ".join(text.split())


class MockRetriever:
    """Returns a golden EvidenceBundle chosen by the query text.

    scenarios maps a substring of the raw query to one of
    "resolved" | "ambiguous" | "low_confidence"; anything else uses `default`.
    """

    def __init__(self, scenarios: dict[str, str] | None = None, default: str = "resolved"):
        self.scenarios = scenarios or {}
        self.default = default
        self.calls: list[dict] = []

    def retrieve(self, retrieval_input: dict) -> dict:
        self.calls.append(retrieval_input)
        query = retrieval_input["query_text_raw"]
        scenario = next((s for key, s in self.scenarios.items() if key in query), self.default)
        bundle = load_fixture(f"evidence_bundle__{scenario}")
        bundle["query_text_segmented"] = retrieval_input["query_text_segmented"]
        return bundle


class MockGenerator:
    """Returns the golden answer, optionally corrupted to exercise grounding.

    modes: ok | bad_fragment | bad_locator | bad_source | claim_not_in_answer |
           no_citations | empty_answer
    """

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls: list[dict] = []

    def generate(self, evidence_bundle: dict) -> dict:
        self.calls.append(evidence_bundle)
        golden = load_fixture("grounded_answer__answered")
        out = {"answer_text": golden["answer_text"], "citations": copy.deepcopy(golden["citations"])}
        c = out["citations"][0]
        if self.mode == "bad_fragment":
            c["fragment_id"] = "FRAG-DOES-NOT-EXIST"
        elif self.mode == "bad_locator":
            c["source_locator"] = "Điều 99, khoản 9 (bịa)"
        elif self.mode == "bad_source":
            c["source_id"] = "SRC-INVENTED"
        elif self.mode == "claim_not_in_answer":
            c["claim_text"] = "một câu không có trong câu trả lời"
        elif self.mode == "no_citations":
            out["citations"] = []
        elif self.mode == "empty_answer":
            out["answer_text"] = ""
        elif self.mode != "ok":
            raise ValueError(f"Unknown MockGenerator mode: {self.mode}")
        return out
