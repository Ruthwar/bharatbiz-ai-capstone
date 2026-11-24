"""Clear the demo ledger so the next run starts with an empty review queue."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.observability.traces import reset_traces
from app.store.ledger import ledger
from app.store.retail import retail_store


def main() -> int:
    ledger.reset()
    retail_store.reset()
    reset_traces()
    print("Demo ledger, retail store and model traces cleared: no reviews, intakes, cases, drafts, observations or spans.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
