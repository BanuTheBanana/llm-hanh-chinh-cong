import io
import json

from hcc.api import create_app
from hcc.conversation import advance_conversation_state, new_conversation_state
from hcc.interpretation import extract_explicit_filters, requested_section_types
from hcc.mocks import MockGenerator, MockRetriever, StubSegmenter, load_fixture
from hcc.pipeline import Pipeline
from hcc.storage import SQLiteStore
from hcc.validation import cross_object_errors


def test_interpretation_extracts_sections_and_explicit_filters():
    query = "Lệ phí cấp đổi tại thành phố Hồ Chí Minh, áp dụng ngày 28/09/2026"
    assert requested_section_types(query) == ["fee"]
    assert extract_explicit_filters(query) == {
        "jurisdiction": "thành phố Hồ Chí Minh",
        "effective_date": "2026-09-28",
        "scope": None,
    }


def test_state_transition_replaces_stale_procedure_context():
    state = new_conversation_state("session-1", now="2026-09-28T00:00:00Z")
    state["last_resolved_procedure_id"] = "PROC-OLD"
    state["last_requested_section_types"] = ["fee"]
    bundle = load_fixture("evidence_bundle__resolved")
    answer = load_fixture("grounded_answer__answered")
    updated = advance_conversation_state(
        state,
        "thời hạn cấp đổi thẻ căn cước là bao lâu",
        bundle,
        answer,
        {"jurisdiction": None, "effective_date": None, "scope": None},
        now="2026-09-28T00:00:01Z",
    )
    assert updated["last_resolved_procedure_id"] == "PROC-001"
    assert updated["last_requested_section_types"] == ["processing_time"]
    assert updated["recent_raw_turns"] == ["thời hạn cấp đổi thẻ căn cước là bao lâu"]


def test_cross_object_validation_checks_bundle_answer_binding():
    bundle = load_fixture("evidence_bundle__resolved")
    answer = load_fixture("grounded_answer__answered")
    answer["evidence_bundle_id"] = "another-bundle"
    assert any("does not match evidence_bundle" in error for error in cross_object_errors(
        evidence_bundle=bundle, grounded_answer=answer
    ))


def test_pipeline_abstains_when_requested_section_is_missing():
    pipeline = Pipeline(StubSegmenter(), MockRetriever(), MockGenerator())
    answer = pipeline.answer("điều kiện và lệ phí cấp đổi thẻ căn cước là gì")
    assert answer["status"] == "insufficient_data"
    assert pipeline.generator.calls == []


def test_sqlite_store_persists_conversation_and_audit(tmp_path):
    store = SQLiteStore(tmp_path / "hcc.sqlite3")
    state = new_conversation_state("session-2", now="2026-09-28T00:00:00Z")
    store.save_conversation_state(state)
    assert store.get_conversation_state("session-2") == state
    store.record("test_event", "session-2", {"status": "ok"})
    events = store.list_audit_events("session-2")
    assert len(events) == 1
    assert events[0]["payload"] == {"status": "ok"}


def test_sqlite_store_supports_shared_in_memory_database():
    store = SQLiteStore(":memory:")
    state = new_conversation_state("memory-session", now="2026-09-28T00:00:00Z")
    store.save_conversation_state(state)
    assert store.get_conversation_state("memory-session") == state


def test_api_returns_schema_valid_answer_and_persists_state(tmp_path):
    store = SQLiteStore(tmp_path / "api.sqlite3")
    pipeline = Pipeline(StubSegmenter(), MockRetriever(), MockGenerator())
    app = create_app(pipeline, store)
    body = json.dumps({"query_text_raw": "thời hạn cấp đổi thẻ căn cước là bao lâu"}).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/answer",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    payload = json.loads(b"".join(app(environ, start_response)))
    session_id = captured["headers"]["X-Conversation-Session-Id"]
    assert captured["status"] == "200 OK"
    assert payload["status"] == "answered"
    assert "session_id" not in payload
    assert store.get_conversation_state(session_id)["last_resolved_procedure_id"] == "PROC-001"
    assert store.list_audit_events(session_id)[0]["event_type"] == "answer_completed"