"""Deterministic query interpretation against the fixed RetrievalInput contract."""
from __future__ import annotations

import re
from datetime import date

from .interfaces import Segmenter

NULL_FILTERS = {"jurisdiction": None, "effective_date": None, "scope": None}

SECTION_TERMS = {
    "fee": ("lệ phí", "phí", "mức thu", "chi phí"),
    "processing_time": ("bao lâu", "thời gian giải quyết", "thời hạn giải quyết", "ngày làm việc"),
    "required_documents": ("hồ sơ", "giấy tờ", "thành phần hồ sơ", "cần nộp"),
    "eligibility": ("đối tượng", "điều kiện", "ai được", "được cấp"),
    "submission_location": ("nộp ở đâu", "nơi nộp", "cơ quan tiếp nhận", "địa điểm"),
    "legal_basis": ("căn cứ pháp lý", "văn bản nào", "theo nghị định", "theo thông tư"),
    "validity_period": ("thời hạn sử dụng", "thời hạn của", "có giá trị bao lâu", "hiệu lực bao lâu"),
}


def requested_section_types(text: str) -> list[str]:
    """Infer requested evidence sections using simple Vietnamese keyword rules."""
    normalized = " ".join(text.casefold().split())
    return [
        section
        for section, terms in SECTION_TERMS.items()
        if any(term in normalized for term in terms)
    ]


def extract_explicit_filters(text: str) -> dict:
    """Extract only unambiguous date, jurisdiction, and applicant-scope phrases."""
    normalized = " ".join(text.casefold().split())
    filters = dict(NULL_FILTERS)

    date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", normalized)
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized)
    if date_match:
        day, month, year = map(int, date_match.groups())
        try:
            filters["effective_date"] = date(year, month, day).isoformat()
        except ValueError:
            pass
    elif iso_match:
        try:
            filters["effective_date"] = date.fromisoformat(iso_match.group()).isoformat()
        except ValueError:
            pass

    jurisdiction_match = re.search(
        r"\b(?:tại|ở|thuộc)\s+((?:tỉnh|thành phố|quận|huyện|thị xã|phường|xã)\s+[\wÀ-ỹ-]+(?:\s+[\wÀ-ỹ-]+){0,3})",
        text,
        re.IGNORECASE,
    )
    if jurisdiction_match:
        filters["jurisdiction"] = " ".join(jurisdiction_match.group(1).split())

    scope_match = re.search(r"\b(?:đối với|dành cho)\s+([^,.!?;]{2,60})", text, re.IGNORECASE)
    if scope_match:
        filters["scope"] = " ".join(scope_match.group(1).split())

    return filters


def interpret(
    query_text_raw: str,
    segmenter: Segmenter,
    *,
    filters: dict | None = None,
    state: dict | None = None,
    top_k: int = 5,
) -> dict:
    state = state or {}
    explicit = extract_explicit_filters(query_text_raw)
    carried = state.get("active_filters") or {}
    supplied = filters or {}
    merged_filters = {
        key: supplied.get(key, explicit[key] if explicit[key] is not None else carried.get(key))
        for key in NULL_FILTERS
    }
    return {
        "query_text_raw": query_text_raw,
        "query_text_segmented": segmenter.segment(query_text_raw),
        "filters": merged_filters,
        "conversation_session_id": state.get("session_id"),
        "top_k": top_k,
    }
