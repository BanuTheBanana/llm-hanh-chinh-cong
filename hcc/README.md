# LLM Hành chính công: Person 2 track (Backend & Grounding)

Backend handoff for parallel work: fixed JSON contracts, deterministic interpretation,
conversation state, grounding, an injectable WSGI API, SQLite state/audit storage, and a
mock end-to-end pipeline.

## Run it

```
pip install -r requirements.txt
python -m pytest -q
python scripts/demo.py       # runs the three scenarios end to end
python scripts/build_fixtures.py   # regenerate fixtures after editing the script
python scripts/validate_contracts.py  # schema + cross-object fixture checks
python scripts/serve_api.py    # mock API at http://127.0.0.1:8000
```

The mock API accepts `POST /answer` with `query_text_raw`, optional `session_id`, `filters`,
and `top_k`. The response body is a `GroundedAnswer`; the session ID is returned in the
`X-Conversation-Session-Id` header. `GET /health` is available for readiness checks.

To connect real components, construct `Pipeline(segmenter, retriever, generator,
conversation_store=store, audit_log=store)` and pass it to `create_app(pipeline, store)`.
The `SQLiteStore` can be replaced by an implementation of the small persistence protocols
in `interfaces.py`.

## Layout

```
schemas/            the 10 JSON Schema contracts (fixed; changes go through a proposal)
fixtures/           golden objects, named <schema>__<variant>.json
fixtures/sample_corpus/   tiny hand-made corpus (3 procedures, 7 fragments, SAMPLE DATA)
scripts/            build_fixtures.py, demo.py
src/hcc/
  validation.py     load schemas, validate any object (cross-file $refs resolved)
  interfaces.py     Segmenter / Retriever / Generator protocols (the seams to other tracks)
  mocks.py          StubSegmenter, MockRetriever, MockGenerator (with corruption modes)
   interpretation.py query -> RetrievalInput, filter/section extraction
   conversation.py  ConversationState creation and turn transitions
  grounding.py      check_sufficiency (before generation), verify_citations (after)
  templates.py      clarification / abstention messages (placeholder wording)
  pipeline.py       orchestrator: interpret -> retrieve -> branch -> ground -> generate -> verify
   api.py            dependency-injected WSGI endpoints
   storage.py        SQLite ConversationState and append-only audit events
tests/              fixtures, grounding, pipeline
```

## How the pipeline branches

| `confidence_status` | What happens | Final `status` |
|---|---|---|
| `low_confidence` | abstain, ask to rephrase; generator never called | `insufficient_data` |
| `ambiguous` | "did you mean X or Y?" from `ambiguous_candidates`; generator never called | `clarification_needed` |
| `resolved` | sufficiency check, generate, verify citations | `answered`, or `insufficient_data` if any check fails |

Whatever the generator writes is only shown if every citation traces to this request's
evidence; otherwise the user gets the abstention message instead.

## Conventions assumed here (need sign-off from the neighbouring tracks)

These are not spelled out in the schemas, so they are choices this track made. Each one
touches another person's work, so they should go through a short proposal.

1. **Person 1:** for `ambiguous` and `low_confidence` bundles, `resolved_procedure_id` is
   `null` and `evidence` is `[]`. For `resolved` bundles, every `Evidence.procedure_id`
   equals `resolved_procedure_id`.
2. **Person 3:** the generator returns `{"answer_text", "citations"}`. An answer with no
   citations is rejected.
3. **Person 3:** each `Citation.claim_text` must be a verbatim substring of `answer_text`,
   and its `source_id` and `source_locator` must equal those of the matching `Evidence`.
4. **All:** `clarification_needed` and `insufficient_data` answers have an empty
   `answer_text` and no citations; the message to show is in `clarification_prompt`.

## Handoff Notes

- Person 1 implements `Segmenter.segment(text)` and `Retriever.retrieve(retrieval_input)`;
   retrieval must echo `query_text_segmented` exactly, populate confidence scores/margin,
   and return evidence with provenance. The pipeline validates the input/bundle pair and
   raises `ContractError` if the bundle refers to a different query.
- For retrieval-aware follow-ups, implement the optional
   `retrieve_with_state(retrieval_input, conversation_state)` method. The pipeline prefers
   this method when present and falls back to `retrieve(retrieval_input)` for stateless or
   legacy retrievers. `RetrievalInput` remains unchanged; the structured state is passed as a
   separate argument and includes the prior resolved procedure and requested sections.
- Person 2 extracts explicit filters, retains structured state, and validates requested
   section coverage using evidence text. `Evidence` currently has no `section_type` field,
   so section coverage uses deterministic text rules rather than changing the frozen schema.
- Person 3 implements `Generator.generate(evidence_bundle)` returning `answer_text` and
   citations. The pipeline rejects citations not bound to this bundle.
- Schemas stay unchanged. In particular, `RetrievalInput` carries `conversation_session_id`
   but not the previous procedure ID or requested section list. Full retrieval-aware follow-up
   routing therefore needs Person 1 to resolve that session through an injected state store,
   or a jointly reviewed contract proposal; do not smuggle extra fields into the dict.
- The included segmenter, retriever, generator, sample corpus, and API server are test/demo
   components. Production retrieval, LLM runtime, durable deployment configuration, migrations,
   and benchmark thresholds remain owned by the corresponding track.
