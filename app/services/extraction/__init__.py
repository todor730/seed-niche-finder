"""Rule-based extraction layer for persisted source evidence."""

from app.services.extraction.canonicalization import SemanticSignalNormalizer
from app.services.extraction.service import RuleBasedExtractionService
from app.services.extraction.types import SupportedSignalType

__all__ = [
    "RuleBasedExtractionService",
    "SemanticSignalNormalizer",
    "SupportedSignalType",
]
