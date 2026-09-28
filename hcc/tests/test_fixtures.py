"""Every golden fixture and the sample corpus must satisfy the schemas and agree with each other."""
import json
from pathlib import Path

import pytest

from hcc.validation import validation_errors

FIX = Path(__file__).resolve().parents[1] / "fixtures"
CORPUS = FIX / "sample_corpus"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# fixtures/<schema_name>__<variant>.json
FIXTURE_FILES = sorted(FIX.glob("*__*.json"))


def test_fixtures_exist():
    assert len(FIXTURE_FILES) >= 8


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name)
def test_fixture_matches_its_schema(path):
    schema = path.name.split("__")[0]
    assert validation_errors(schema, _load(path)) == []


def test_sample_corpus_matches_schemas():
    assert validation_errors("source_manifest", _load(CORPUS / "source_manifest.json")) == []
    for rec in _load(CORPUS / "procedure_records.json"):
        assert validation_errors("procedure_record", rec) == []
    for frag in _load(CORPUS / "procedure_fragments.json"):
        assert validation_errors("procedure_fragment", frag) == []


def test_corpus_is_internally_consistent():
    manifest = _load(CORPUS / "source_manifest.json")
    records = {r["procedure_id"]: r for r in _load(CORPUS / "procedure_records.json")}
    frags = {f["fragment_id"]: f for f in _load(CORPUS / "procedure_fragments.json")}
    for f in frags.values():
        assert f["procedure_id"] in records
        assert f["source_id"] == manifest["source_id"]
    for r in records.values():
        assert r["source_id"] == manifest["source_id"]
        assert set(r["fragment_ids"]) == {f["fragment_id"] for f in frags.values() if f["procedure_id"] == r["procedure_id"]}


@pytest.mark.parametrize("scenario", ["resolved", "ambiguous", "low_confidence"])
def test_bundle_evidence_matches_corpus(scenario):
    """Evidence in golden bundles must be a faithful snapshot of corpus fragments."""
    frags = {f["fragment_id"]: f for f in _load(CORPUS / "procedure_fragments.json")}
    for ev in _load(FIX / f"evidence_bundle__{scenario}.json")["evidence"]:
        frag = frags[ev["fragment_id"]]
        assert ev["text"] == frag["text"]
        assert ev["source_locator"] == frag["source_locator"]
        assert ev["procedure_id"] == frag["procedure_id"]


@pytest.mark.parametrize("scenario", ["resolved", "ambiguous", "low_confidence"])
def test_bundle_margin_is_consistent(scenario):
    b = _load(FIX / f"evidence_bundle__{scenario}.json")
    assert b["margin"] == pytest.approx(b["top_score"] - b["second_score"], abs=1e-4)


def test_non_resolved_bundles_follow_conventions():
    """Convention to confirm with Person 1: ambiguous/low_confidence have no procedure and no evidence."""
    for scenario in ("ambiguous", "low_confidence"):
        b = _load(FIX / f"evidence_bundle__{scenario}.json")
        assert b["resolved_procedure_id"] is None
        assert b["evidence"] == []
