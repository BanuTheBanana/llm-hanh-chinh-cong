"""Dependency-injected WSGI API for the grounded-answer pipeline."""
from __future__ import annotations

import json
from typing import Callable
from uuid import uuid4
from wsgiref.simple_server import make_server

from .conversation import new_conversation_state
from .interfaces import ConversationStore
from .pipeline import Pipeline
from .validation import ContractError

MAX_REQUEST_BYTES = 1_000_000


def create_app(pipeline: Pipeline, conversation_store: ConversationStore | None = None):
    """Create a WSGI application; inject real or mock pipeline components at startup."""
    if conversation_store is not None:
        if pipeline.conversation_store is None:
            pipeline.conversation_store = conversation_store
        if pipeline.audit_log is None and hasattr(conversation_store, "record"):
            pipeline.audit_log = conversation_store

    def respond(
        start_response: Callable,
        status: str,
        payload: dict,
        headers: list[tuple[str, str]] | None = None,
    ) -> list[bytes]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(
            status,
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))]
            + (headers or []),
        )
        return [body]

    def app(environ: dict, start_response: Callable) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        if method == "GET" and path == "/health":
            return respond(start_response, "200 OK", {"status": "ok"})
        if method != "POST" or path != "/answer":
            return respond(start_response, "404 Not Found", {"error": "not_found"})

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body size is invalid")
            raw_body = environ["wsgi.input"].read(length)
            request = json.loads(raw_body.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request body must be a JSON object")
            query = request.get("query_text_raw")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query_text_raw must be a non-empty string")
            filters = request.get("filters") or {}
            if not isinstance(filters, dict):
                raise ValueError("filters must be an object")
            top_k = request.get("top_k", 5)
            if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
                raise ValueError("top_k must be a positive integer")
            session_id = request.get("session_id") or str(uuid4())
            if not isinstance(session_id, str) or not session_id.strip():
                raise ValueError("session_id must be a non-empty string")

            state = None
            if conversation_store is not None:
                state = conversation_store.get_conversation_state(session_id)
                if state is None:
                    state = new_conversation_state(session_id, now=pipeline.clock())
            answer = pipeline.answer(
                query,
                filters=filters,
                state=state,
                session_id=session_id,
                top_k=top_k,
            )
            return respond(
                start_response,
                "200 OK",
                answer,
                [("X-Conversation-Session-Id", session_id)],
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ContractError) as error:
            return respond(start_response, "400 Bad Request", {"error": "invalid_request", "detail": str(error)})
        except Exception:
            return respond(start_response, "500 Internal Server Error", {"error": "internal_error"})

    return app


def serve(app, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the WSGI application with Python's standard-library development server."""
    with make_server(host, port, app) as server:
        server.serve_forever()