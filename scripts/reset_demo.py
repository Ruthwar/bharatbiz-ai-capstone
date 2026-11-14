"""Clear the demo ledger so the next run starts with an empty review queue."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.store.ledger import ledger


def main() -> int:
    ledger.reset()
    print("Demo ledger cleared: no pending reviews, open intakes or processed messages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
