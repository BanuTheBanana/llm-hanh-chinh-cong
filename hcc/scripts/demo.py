"""Run the pipeline on the three golden scenarios (all components mocked).

    python scripts/demo.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hcc.mocks import MockGenerator, MockRetriever, StubSegmenter  # noqa: E402
from hcc.pipeline import Pipeline  # noqa: E402

QUERIES = [
    ("resolved", "thời hạn cấp đổi thẻ căn cước là bao lâu"),
    ("ambiguous", "thời hạn làm thẻ căn cước là bao lâu"),
    ("low_confidence", "xin giấy phép lái tàu vũ trụ"),
]

for scenario, query in QUERIES:
    pipe = Pipeline(StubSegmenter(), MockRetriever(default=scenario), MockGenerator())
    result = pipe.answer(query)
    print(f"\n[{scenario}] {query}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
