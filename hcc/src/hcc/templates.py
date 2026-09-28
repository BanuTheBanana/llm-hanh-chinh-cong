"""User-facing messages for clarification and abstention.

These are deterministic templates (no LLM). The wording is a PLACEHOLDER until the
team decides tone and language (open question in the work-split doc).
"""
from __future__ import annotations

NO_MATCH_PROMPT = (
    "Tôi chưa tìm thấy thủ tục phù hợp với câu hỏi của bạn. "
    "Bạn có thể mô tả rõ hơn thủ tục hoặc thông tin bạn cần không?"
)

INSUFFICIENT_EVIDENCE_PROMPT = (
    "Tôi chưa có đủ thông tin trong dữ liệu hiện có để trả lời chính xác câu hỏi này."
)


def clarification_prompt(candidates: list[dict]) -> str:
    """Ask the user to choose between near-tied candidate procedures."""
    names = [f"“{c['canonical_name']}”" for c in candidates]
    if len(names) == 1:
        options = names[0]
    else:
        options = ", ".join(names[:-1]) + " hoặc " + names[-1]
    return f"Bạn muốn hỏi về thủ tục nào: {options}?"
