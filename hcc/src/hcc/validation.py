"""Load the JSON Schema contracts and validate objects against them.

Every object that crosses a component boundary is validated here, so a contract
mismatch with another track fails loudly during development.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

SCHEMA_NAMES = (
    "source_manifest",
    "procedure_record",
    "procedure_fragment",
    "filters",
    "retrieval_input",
    "evidence",
    "evidence_bundle",
    "citation",
    "grounded_answer",
    "conversation_state",
)


class ContractError(ValueError):
    """An object did not match its JSON Schema contract."""


@lru_cache(maxsize=1)
def _schemas() -> dict[str, dict]:
    return {
        name: json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        for name in SCHEMA_NAMES
    }


@lru_cache(maxsize=1)
def _registry() -> Registry:
    # Schemas reference each other by relative file name (e.g. "filters.schema.json"),
    # which is also each schema's $id, so key the registry by that file name.
    resources = [
        (f"{name}.schema.json", Resource.from_contents(schema, default_specification=DRAFT202012))
        for name, schema in _schemas().items()
    ]
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"Unknown schema {name!r}; expected one of {SCHEMA_NAMES}")
    return Draft202012Validator(
        _schemas()[name], registry=_registry(), format_checker=FormatChecker()
    )


def validation_errors(name: str, obj: object) -> list[str]:
    """Return human-readable errors (empty list means valid)."""
    errors = sorted(_validator(name).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    ]


def is_valid(name: str, obj: object) -> bool:
    return not validation_errors(name, obj)


def assert_valid(name: str, obj: object) -> None:
    errors = validation_errors(name, obj)
    if errors:
        raise ContractError(f"{name} contract violated:\n  " + "\n  ".join(errors))


def cross_object_errors(
    *,
    retrieval_input: dict | None = None,
    evidence_bundle: dict | None = None,
    grounded_answer: dict | None = None,
) -> list[str]:
    """Validate invariants JSON Schema cannot express across contract objects."""
    supplied = (
        ("retrieval_input", retrieval_input),
        ("evidence_bundle", evidence_bundle),
        ("grounded_answer", grounded_answer),
    )
    problems = [
        f"{name}: {error}"
        for name, obj in supplied
        if obj is not None
        for error in validation_errors(name, obj)
    ]

    if evidence_bundle is not None:
        bundle = evidence_bundle
        evidence = bundle.get("evidence", [])
        status = bundle.get("confidence_status")
        procedure_id = bundle.get("resolved_procedure_id")
        candidates = bundle.get("ambiguous_candidates", [])

        if retrieval_input is not None and bundle.get("query_text_segmented") != retrieval_input.get(
            "query_text_segmented"
        ):
            problems.append("evidence_bundle.query_text_segmented does not match retrieval_input")

        if status == "resolved":
            if not procedure_id:
                problems.append("resolved bundle must name a resolved_procedure_id")
            if not evidence:
                problems.append("resolved bundle must contain evidence")
            if any(item.get("procedure_id") != procedure_id for item in evidence):
                problems.append("resolved bundle evidence must all belong to resolved_procedure_id")
        elif status == "ambiguous":
            if procedure_id is not None or evidence:
                problems.append("ambiguous bundle must not resolve a procedure or include evidence")
            if len(candidates) < 2:
                problems.append("ambiguous bundle must provide at least two candidates")
        elif status == "low_confidence":
            if procedure_id is not None or evidence or candidates:
                problems.append("low_confidence bundle must not include resolved evidence or candidates")

        top_score = bundle.get("top_score")
        second_score = bundle.get("second_score")
        margin = bundle.get("margin")
        if second_score is not None and top_score is None:
            problems.append("second_score cannot be set when top_score is null")
        if margin is not None:
            if top_score is None or second_score is None:
                problems.append("margin requires both top_score and second_score")
            elif not math.isclose(margin, top_score - second_score, rel_tol=1e-7, abs_tol=1e-9):
                problems.append("margin must equal top_score minus second_score")

    if evidence_bundle is not None and grounded_answer is not None:
        bundle = evidence_bundle
        answer = grounded_answer
        if answer.get("evidence_bundle_id") != bundle.get("bundle_id"):
            problems.append("grounded_answer.evidence_bundle_id does not match evidence_bundle")
        status = bundle.get("confidence_status")
        answer_status = answer.get("status")
        if answer_status == "answered" and status != "resolved":
            problems.append("answered output requires a resolved evidence bundle")
        if answer_status == "clarification_needed" and status != "ambiguous":
            problems.append("clarification_needed output requires an ambiguous evidence bundle")
        if answer_status != "answered":
            if answer.get("answer_text") or answer.get("citations"):
                problems.append("non-answered output must have empty answer_text and citations")
            if not answer.get("clarification_prompt"):
                problems.append("non-answered output must provide a clarification_prompt")
        elif answer.get("answer_text") and answer.get("citations"):
            from .grounding import verify_citations

            problems.extend(verify_citations(bundle, answer["answer_text"], answer["citations"]).problems)

    return problems


def assert_valid_cross_objects(**objects: dict | None) -> None:
    problems = cross_object_errors(**objects)
    if problems:
        raise ContractError("cross-object contract violated:\n  " + "\n  ".join(problems))
