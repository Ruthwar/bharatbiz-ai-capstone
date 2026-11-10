from app.extraction.base import Extraction, Extractor
from app.extraction.llm import ExtractionError, LLMExtractor
from app.extraction.rules import RulesExtractor
from app.extraction.validate import validate_extraction

__all__ = [
    "Extraction",
    "Extractor",
    "ExtractionError",
    "LLMExtractor",
    "RulesExtractor",
    "configured_extractor",
    "validate_extraction",
]


def configured_extractor() -> Extractor:
    """LLM when configured by environment, otherwise the deterministic rules extractor."""
    return LLMExtractor.from_environment() or RulesExtractor()
