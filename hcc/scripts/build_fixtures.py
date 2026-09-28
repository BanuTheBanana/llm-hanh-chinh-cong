"""Regenerate the golden fixtures and the tiny sample corpus.

All content is SAMPLE DATA for testing (not real legal text). Run from the repo root:
    python scripts/build_fixtures.py
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcc import templates  # noqa: E402

FIX = ROOT / "fixtures"
CORPUS = FIX / "sample_corpus"
TS = "2026-09-28T00:00:00Z"
SRC_ID, VERSION, EFFECTIVE = "SRC-SAMPLE-001", "sample-1", "2024-01-01"
NOTE = "(dữ liệu mẫu để kiểm thử)"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---- sample corpus -------------------------------------------------------
PROCS = {
    "PROC-001": ("Cấp đổi thẻ căn cước công dân", ["đổi thẻ căn cước", "cấp đổi CCCD"]),
    "PROC-002": ("Cấp thẻ căn cước công dân lần đầu", ["làm thẻ căn cước lần đầu", "cấp mới CCCD"]),
    "PROC-003": ("Đăng ký khai sinh", ["khai sinh", "làm giấy khai sinh"]),
}

FRAGS = [
    # (fragment_id, procedure_id, section_type, text, locator)
    ("FRAG-001-fee", "PROC-001", "fee",
     f"Lệ phí cấp đổi thẻ căn cước công dân: 30.000 đồng {NOTE}.", "Điều 1, khoản 1 (mẫu)"),
    ("FRAG-001-time", "PROC-001", "processing_time",
     f"Thời hạn giải quyết cấp đổi thẻ căn cước công dân: 7 ngày làm việc kể từ khi nhận đủ hồ sơ {NOTE}.",
     "Điều 1, khoản 2 (mẫu)"),
    ("FRAG-001-docs", "PROC-001", "required_documents",
     f"Hồ sơ cấp đổi thẻ căn cước công dân gồm: tờ khai theo mẫu và thẻ căn cước công dân cũ {NOTE}.",
     "Điều 1, khoản 3 (mẫu)"),
    ("FRAG-002-fee", "PROC-002", "fee",
     f"Lệ phí cấp thẻ căn cước công dân lần đầu: miễn lệ phí {NOTE}.", "Điều 2, khoản 1 (mẫu)"),
    ("FRAG-002-time", "PROC-002", "processing_time",
     f"Thời hạn giải quyết cấp thẻ căn cước công dân lần đầu: 10 ngày làm việc kể từ khi nhận đủ hồ sơ {NOTE}.",
     "Điều 2, khoản 2 (mẫu)"),
    ("FRAG-003-fee", "PROC-003", "fee",
     f"Lệ phí đăng ký khai sinh: miễn lệ phí {NOTE}.", "Điều 3, khoản 1 (mẫu)"),
    ("FRAG-003-time", "PROC-003", "processing_time",
     f"Thời hạn giải quyết đăng ký khai sinh: 3 ngày làm việc kể từ khi nhận đủ hồ sơ {NOTE}.",
     "Điều 3, khoản 2 (mẫu)"),
]

fragments = [
    {"fragment_id": fid, "procedure_id": pid, "section_type": st, "text": text,
     "source_id": SRC_ID, "ordinal": i, "content_hash": sha(text), "source_locator": loc}
    for i, (fid, pid, st, text, loc) in enumerate(FRAGS)
]
FRAG_BY_ID = {f["fragment_id"]: f for f in fragments}

records = [
    {"procedure_id": pid, "canonical_name": name, "aliases": aliases, "official_codes": [],
     "jurisdiction": "national",
     "fragment_ids": [f["fragment_id"] for f in fragments if f["procedure_id"] == pid],
     "source_id": SRC_ID}
    for pid, (name, aliases) in PROCS.items()
]

manifest = {
    "source_id": SRC_ID,
    "title": "Bộ dữ liệu mẫu để kiểm thử (không phải văn bản pháp luật thật)",
    "publishing_authority": "Nhóm dự án (dữ liệu mẫu)",
    "review_status": "reviewed", "effective_date": EFFECTIVE, "superseded_by": None,
    "version": VERSION,
    "content_hash": sha("".join(f["content_hash"] for f in fragments)),
    "ingested_at": TS,
}

dump(CORPUS / "source_manifest.json", manifest)
dump(CORPUS / "procedure_records.json", records)
dump(CORPUS / "procedure_fragments.json", fragments)


# ---- golden fixtures -----------------------------------------------------
def evidence(fid: str, score: float, method: str = "fused") -> dict:
    f = FRAG_BY_ID[fid]
    return {"fragment_id": fid, "procedure_id": f["procedure_id"], "text": f["text"],
            "score": score, "method": method, "source_id": SRC_ID, "source_version": VERSION,
            "effective_date": EFFECTIVE, "source_locator": f["source_locator"]}


def bundle(bid, seg, resolved, top, second, status, candidates, ev):
    margin = None if second is None else round(top - second, 4)
    return {"bundle_id": bid, "query_text_segmented": seg, "resolved_procedure_id": resolved,
            "top_score": top, "second_score": second, "margin": margin,
            "confidence_status": status, "ambiguous_candidates": candidates, "evidence": ev,
            "fusion_method": "weighted_sum(bm25_norm, cosine) [placeholder]", "created_at": TS}


b_resolved = bundle("BUNDLE-SAMPLE-RESOLVED", "thời_hạn cấp_đổi thẻ căn_cước là bao_lâu",
                    "PROC-001", 0.91, 0.42, "resolved", [],
                    [evidence("FRAG-001-time", 0.91), evidence("FRAG-001-fee", 0.58)])
b_ambiguous = bundle("BUNDLE-SAMPLE-AMBIGUOUS", "thời_hạn làm thẻ căn_cước là bao_lâu",
                     None, 0.86, 0.82, "ambiguous",
                     [{"procedure_id": "PROC-001", "canonical_name": PROCS["PROC-001"][0], "score": 0.86},
                      {"procedure_id": "PROC-002", "canonical_name": PROCS["PROC-002"][0], "score": 0.82}],
                     [])
b_low = bundle("BUNDLE-SAMPLE-LOW", "xin giấy_phép lái tàu vũ_trụ",
               None, 0.31, 0.28, "low_confidence", [], [])

dump(FIX / "evidence_bundle__resolved.json", b_resolved)
dump(FIX / "evidence_bundle__ambiguous.json", b_ambiguous)
dump(FIX / "evidence_bundle__low_confidence.json", b_low)

ev0 = b_resolved["evidence"][0]
ANSWER = "Thời hạn giải quyết cấp đổi thẻ căn cước công dân là 7 ngày làm việc kể từ khi nhận đủ hồ sơ."
CLAIM = "7 ngày làm việc kể từ khi nhận đủ hồ sơ"
assert CLAIM in ANSWER


def answer(status, text, prompt, citations, bundle_id):
    return {"status": status, "answer_text": text, "clarification_prompt": prompt,
            "citations": citations, "evidence_bundle_id": bundle_id, "created_at": TS}


dump(FIX / "grounded_answer__answered.json", answer(
    "answered", ANSWER, None,
    [{"claim_text": CLAIM, "fragment_id": ev0["fragment_id"], "source_id": ev0["source_id"],
      "source_locator": ev0["source_locator"]}], b_resolved["bundle_id"]))
dump(FIX / "grounded_answer__clarification_needed.json", answer(
    "clarification_needed", "",
    templates.clarification_prompt(b_ambiguous["ambiguous_candidates"]), [], b_ambiguous["bundle_id"]))
dump(FIX / "grounded_answer__insufficient_data.json", answer(
    "insufficient_data", "", templates.NO_MATCH_PROMPT, [], b_low["bundle_id"]))

NULL_FILTERS = {"jurisdiction": None, "effective_date": None, "scope": None}
dump(FIX / "retrieval_input__example.json", {
    "query_text_raw": "thời hạn cấp đổi thẻ căn cước là bao lâu",
    "query_text_segmented": "thời_hạn cấp_đổi thẻ căn_cước là bao_lâu",
    "filters": NULL_FILTERS, "conversation_session_id": None, "top_k": 5})
dump(FIX / "conversation_state__example.json", {
    "session_id": "sess-sample-001", "last_resolved_procedure_id": "PROC-001",
    "last_requested_section_types": ["processing_time"], "active_filters": NULL_FILTERS,
    "unresolved_references": [], "recent_raw_turns": [], "updated_at": TS})
print("fixtures written")
