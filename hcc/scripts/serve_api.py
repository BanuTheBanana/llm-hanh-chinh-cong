"""Run the API against mocks so other tracks can integrate before real components land."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcc.api import create_app, serve  # noqa: E402
from hcc.mocks import MockGenerator, MockRetriever, StubSegmenter  # noqa: E402
from hcc.pipeline import Pipeline  # noqa: E402
from hcc.storage import SQLiteStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=".data/hcc.sqlite3")
    args = parser.parse_args()

    store = SQLiteStore(ROOT / args.database)
    pipeline = Pipeline(StubSegmenter(), MockRetriever(), MockGenerator())
    app = create_app(pipeline, store)
    print(f"HCC mock API listening on http://{args.host}:{args.port}")
    serve(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()