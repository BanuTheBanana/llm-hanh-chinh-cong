"""Grounding: programmatic checks that gate what the user sees.

BASIC version. It already enforces the rules that protect against invented citations
(Section 10.2), but the sufficiency check is minimal and will be extended (for example,
requiring every requested section type to be present).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence

from .interpretation import requested_section_types


@dataclass
class GroundingResult:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_sufficiency(
    bundle: dict, requested_sections: Sequence[str] = ()
) -> GroundingResult:
    """Before generation: is there real, consistent evidence to answer from?"""
    result = GroundingResult()
    resolved = bundle.get("resolved_procedure_id")
    evidence = bundle.get("evidence", [])
    if not resolved:
        result.problems.append("resolved bundle has no resolved_procedure_id")
    if not evidence:
        result.problems.append("resolved bundle has no evidence")
    for ev in evidence:
        if resolved and ev["procedure_id"] != resolved:
            result.problems.append(
                f"evidence {ev['fragment_id']} belongs to {ev['procedure_id']}, not {resolved}"
            )
    present_sections = {
        section
        for ev in evidence
        for section in requested_section_types(ev.get("text", ""))
    }
    for section in requested_sections:
        if section not in present_sections:
            result.problems.append(f"evidence is missing requested section {section}")
    return result


def verify_citations(bundle: dict, answer_text: str, citations: list[dict]) -> GroundingResult:
    """After generation: every citation must trace to evidence from THIS request."""
    result = GroundingResult()
    if not answer_text.strip():
        result.problems.append("answer_text is empty")
    if not citations:
        result.problems.append("answer has no citations")

    by_id = {ev["fragment_id"]: ev for ev in bundle.get("evidence", [])}
    for i, c in enumerate(citations):
        label = f"citation[{i}]"
        ev = by_id.get(c.get("fragment_id"))
        if ev is None:
            result.problems.append(f"{label}: fragment_id {c.get('fragment_id')!r} not in evidence bundle")
            continue
        if c.get("source_id") != ev["source_id"]:
            result.problems.append(f"{label}: source_id does not match the evidence")
        if c.get("source_locator") != ev["source_locator"]:
            result.problems.append(f"{label}: source_locator does not match the evidence")
        if c.get("claim_text") not in answer_text:
            result.problems.append(f"{label}: claim_text is not a verbatim span of answer_text")
    return result
