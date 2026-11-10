"""One-call check that the configured model gateway and key work. Never prints the key."""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.extraction import configured_extractor, validate_extraction
from app.schemas.contracts import MessageSubmission
from app.state import load_business_state


def main() -> int:
    extractor = configured_extractor()
    print(f"extractor: {extractor.name}")
    if extractor.name != "llm":
        print("LLM not configured. Set LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL and LLM_MODEL in .env.")
        return 1

    state = load_business_state()
    message = MessageSubmission(
        message_id="key-check-1",
        source_type="supplier_update",
        text="Sri Venkateswara FMCG Supply reports a two-day delay for Cooking oil 1 L pouch.",
        observed_at=datetime.now().astimezone(),
        language="English",
        state_version=state.state_version,
    )

    try:
        extraction = extractor.extract(message, state)
        violations = validate_extraction(extraction, message, state)
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 2

    print(
        json.dumps(
            {
                "mode": extraction.mode,
                "intents": [intent.model_dump() for intent in extraction.intents],
                "facts": [fact.model_dump() for fact in extraction.facts],
                "unknowns": extraction.uncertainties,
                "violations": violations,
                "usable": not violations,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if not violations else 3


if __name__ == "__main__":
    raise SystemExit(main())
