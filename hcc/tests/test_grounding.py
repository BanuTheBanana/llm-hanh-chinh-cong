import copy

from hcc.grounding import check_sufficiency, verify_citations
from hcc.mocks import load_fixture


def _setup():
    bundle = load_fixture("evidence_bundle__resolved")
    golden = load_fixture("grounded_answer__answered")
    return bundle, golden["answer_text"], copy.deepcopy(golden["citations"])


def test_golden_answer_passes():
    bundle, text, cites = _setup()
    assert check_sufficiency(bundle).ok
    assert verify_citations(bundle, text, cites).ok


def test_sufficiency_fails_without_evidence():
    bundle, _, _ = _setup()
    bundle["evidence"] = []
    assert not check_sufficiency(bundle).ok


def test_sufficiency_fails_without_resolved_procedure():
    bundle, _, _ = _setup()
    bundle["resolved_procedure_id"] = None
    assert not check_sufficiency(bundle).ok


def test_sufficiency_fails_when_evidence_belongs_to_another_procedure():
    bundle, _, _ = _setup()
    bundle["evidence"][0]["procedure_id"] = "PROC-002"
    assert not check_sufficiency(bundle).ok


def test_citation_outside_bundle_is_rejected():
    bundle, text, cites = _setup()
    cites[0]["fragment_id"] = "FRAG-003-fee"  # real fragment, but not in THIS bundle
    result = verify_citations(bundle, text, cites)
    assert not result.ok and "not in evidence bundle" in result.problems[0]


def test_citation_with_wrong_source_or_locator_is_rejected():
    bundle, text, cites = _setup()
    cites[0]["source_id"] = "SRC-INVENTED"
    cites[0]["source_locator"] = "Điều 99"
    problems = verify_citations(bundle, text, cites).problems
    assert any("source_id" in p for p in problems)
    assert any("source_locator" in p for p in problems)


def test_claim_must_be_verbatim_span_of_answer():
    bundle, text, cites = _setup()
    cites[0]["claim_text"] = "không có trong câu trả lời"
    assert not verify_citations(bundle, text, cites).ok


def test_answer_without_citations_or_text_is_rejected():
    bundle, text, cites = _setup()
    assert not verify_citations(bundle, text, []).ok
    assert not verify_citations(bundle, "", cites).ok
