import json
import os

os.environ["LLM_PROVIDER"] = "none"
# Tests must never touch the demo database on disk.
os.environ["BHARATBIZ_LEDGER_DB"] = ":memory:"
os.environ["BHARATBIZ_RETAIL_DB"] = ":memory:"
os.environ["BHARATBIZ_RAG_DB"] = ":memory:"

from pathlib import Path

import pytest

from app.schemas.contracts import MessageSubmission
from app.state import load_business_state
from app.store.retail import retail_store

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clear_retail_store():
    retail_store.reset()
    yield
    retail_store.reset()


@pytest.fixture
def state():
    return load_business_state(expected_version="synthetic-v2-seed-20261105")


@pytest.fixture
def demo_message():
    fixture = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8")
    )
    return MessageSubmission.model_validate(fixture["message"])
