from typing import Protocol

from pydantic import BaseModel, Field

from app.orchestration.taxonomy import UNCLASSIFIED
from app.schemas.contracts import BusinessState, EvidenceFact, IntentMatch, MessageSubmission


class Extraction(BaseModel):
    intents: list[IntentMatch] = Field(default_factory=list)
    facts: list[EvidenceFact] = Field(default_factory=list)
    inferences: dict[str, str | bool | None] = Field(default_factory=dict)
    uncertainties: list[str] = Field(default_factory=list)
    mode: str = "rules_mock"

    @property
    def primary_intent(self) -> str:
        if not self.intents:
            return UNCLASSIFIED
        return max(self.intents, key=lambda match: match.confidence).intent

    def fact(self, field: str) -> EvidenceFact | None:
        return next((fact for fact in self.facts if fact.field == field), None)


class Extractor(Protocol):
    name: str

    def extract(self, message: MessageSubmission, state: BusinessState) -> Extraction: ...
