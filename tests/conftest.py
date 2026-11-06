import json
from pathlib import Path

import pytest

from app.schemas.contracts import MessageSubmission
from app.state import load_business_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def state():
    return load_business_state(expected_version="synthetic-v2-seed-20261105")


@pytest.fixture
def demo_message():
    fixture = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenario_fixtures" / "SCN-003.json").read_text(encoding="utf-8")
    )
    return MessageSubmission.model_validate(fixture["message"])
