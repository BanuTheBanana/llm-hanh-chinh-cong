import pytest

from hcc import templates
from hcc.mocks import MockGenerator, MockRetriever, StubSegmenter, load_fixture
from hcc.pipeline import Pipeline
from hcc.validation import ContractError, validation_errors

FIXED_TIME = "2026-09-28T00:00:00Z"


def make(scenario="resolved", gen_mode="ok"):
    retriever = MockRetriever(default=scenario)
    generator = MockGenerator(mode=gen_mode)
    pipe = Pipeline(StubSegmenter(), retriever, generator, clock=lambda: FIXED_TIME)
    return pipe, retriever, generator


def test_resolved_path_returns_answered_with_valid_citation():
    pipe, _, gen = make("resolved")
    out = pipe.answer("thời hạn cấp đổi thẻ căn cước là bao lâu")
    assert out["status"] == "answered"
    assert out["answer_text"] and out["citations"]
    assert out["clarification_prompt"] is None
    assert out["evidence_bundle_id"] == "BUNDLE-SAMPLE-RESOLVED"
    assert len(gen.calls) == 1


def test_answered_output_matches_golden_fixture():
    pipe, _, _ = make("resolved")
    assert pipe.answer("x") == load_fixture("grounded_answer__answered")


def test_ambiguous_path_asks_which_procedure_and_never_calls_generator():
    pipe, _, gen = make("ambiguous")
    out = pipe.answer("làm thẻ căn cước mất bao lâu")
    assert out["status"] == "clarification_needed"
    assert out["answer_text"] == "" and out["citations"] == []
    for name in ("Cấp đổi thẻ căn cước công dân", "Cấp thẻ căn cước công dân lần đầu"):
        assert name in out["clarification_prompt"]
    assert gen.calls == []
    assert out == load_fixture("grounded_answer__clarification_needed")


def test_low_confidence_path_abstains_and_never_calls_generator():
    pipe, _, gen = make("low_confidence")
    out = pipe.answer("xin giấy phép lái tàu vũ trụ")
    assert out["status"] == "insufficient_data"
    assert out["clarification_prompt"] == templates.NO_MATCH_PROMPT
    assert gen.calls == []
    assert out == load_fixture("grounded_answer__insufficient_data")


@pytest.mark.parametrize(
    "mode",
    ["bad_fragment", "bad_locator", "bad_source", "claim_not_in_answer", "no_citations", "empty_answer"],
)
def test_bad_generator_output_is_never_shown_to_the_user(mode):
    pipe, _, gen = make("resolved", gen_mode=mode)
    out = pipe.answer("thời hạn cấp đổi thẻ căn cước là bao lâu")
    assert out["status"] == "insufficient_data"
    assert out["answer_text"] == "" and out["citations"] == []
    assert out["clarification_prompt"] == templates.INSUFFICIENT_EVIDENCE_PROMPT
    assert len(gen.calls) == 1  # generator ran, but its output was rejected


def test_resolved_bundle_with_no_evidence_skips_generation():
    bundle = load_fixture("evidence_bundle__resolved")
    bundle["evidence"] = []

    class EmptyRetriever:
        def retrieve(self, _):
            return bundle

    gen = MockGenerator()
    with pytest.raises(ContractError, match="resolved bundle must contain evidence"):
        Pipeline(StubSegmenter(), EmptyRetriever(), gen, clock=lambda: FIXED_TIME).answer("x")
    assert gen.calls == []


def test_ambiguous_bundle_without_candidates_degrades_safely():
    bundle = load_fixture("evidence_bundle__ambiguous")
    bundle["ambiguous_candidates"] = []

    class R:
        def retrieve(self, _):
            return bundle

    with pytest.raises(ContractError, match="at least two candidates"):
        Pipeline(StubSegmenter(), R(), MockGenerator(), clock=lambda: FIXED_TIME).answer("x")


def test_retriever_bundle_must_match_the_request_query():
    class MismatchedRetriever:
        def retrieve(self, _):
            return load_fixture("evidence_bundle__resolved")

    with pytest.raises(ContractError, match="query_text_segmented does not match"):
        Pipeline(StubSegmenter(), MismatchedRetriever(), MockGenerator()).answer("new query")


def test_retriever_contract_violation_fails_loudly():
    class BrokenRetriever:
        def retrieve(self, _):
            return {"bundle_id": "b1"}  # missing required fields

    pipe = Pipeline(StubSegmenter(), BrokenRetriever(), MockGenerator())
    with pytest.raises(ContractError):
        pipe.answer("x")


def test_retrieval_input_is_built_from_the_query():
    pipe, retriever, _ = make("resolved")
    pipe.answer("  thẻ   căn cước  ", state={"session_id": "sess-1"}, top_k=3)
    sent = retriever.calls[0]
    assert sent["query_text_raw"] == "  thẻ   căn cước  "
    assert sent["query_text_segmented"] == "thẻ căn cước"
    assert sent["conversation_session_id"] == "sess-1"
    assert sent["top_k"] == 3
    assert validation_errors("retrieval_input", sent) == []


@pytest.mark.parametrize("scenario", ["resolved", "ambiguous", "low_confidence"])
@pytest.mark.parametrize("gen_mode", ["ok", "bad_fragment"])
def test_every_output_is_a_valid_grounded_answer(scenario, gen_mode):
    pipe, _, _ = make(scenario, gen_mode)
    assert validation_errors("grounded_answer", pipe.answer("x")) == []
