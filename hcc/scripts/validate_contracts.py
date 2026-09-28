"""Validate all fixture schemas and cross-object relationships."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcc.validation import cross_object_errors, validation_errors  # noqa: E402


def main() -> int:
    fixtures = ROOT / "fixtures"
    failures: list[str] = []
    loaded: dict[str, dict] = {}
    for path in sorted(fixtures.glob("*.json")):
        name = path.stem.split("__", 1)[0]
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            failures.append(f"{path.name}: cannot load JSON: {error}")
            continue
        loaded[path.stem] = obj
        errors = validation_errors(name, obj)
        failures.extend(f"{path.name}: {error}" for error in errors)

    retrieval = loaded.get("retrieval_input__example")
    resolved = loaded.get("evidence_bundle__resolved")
    if retrieval is not None and resolved is not None:
        failures.extend(
            f"resolved pair: {error}"
            for error in cross_object_errors(retrieval_input=retrieval, evidence_bundle=resolved)
        )

    for variant in ("answered", "clarification_needed", "insufficient_data"):
        answer = loaded.get(f"grounded_answer__{variant}")
        bundle_variant = {
            "answered": "resolved",
            "clarification_needed": "ambiguous",
            "insufficient_data": "low_confidence",
        }[variant]
        bundle = loaded.get(f"evidence_bundle__{bundle_variant}")
        if answer is not None and bundle is not None:
            failures.extend(
                f"{variant} pair: {error}"
                for error in cross_object_errors(evidence_bundle=bundle, grounded_answer=answer)
            )

    if failures:
        print("Contract validation failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"Validated {len(loaded)} fixture objects and cross-object relationships.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())