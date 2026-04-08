"""Types and contracts for the rule-based extraction layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import Match, Pattern
from typing import Callable
from uuid import UUID


class SupportedSignalType(StrEnum):
    """Closed set of signal types supported by the first extraction engine."""

    TROPE = "trope"
    SUBGENRE = "subgenre"
    AUDIENCE = "audience"
    PROMISE = "promise"
    TONE = "tone"
    SETTING = "setting"
    PROBLEM_ANGLE = "problem_angle"
    SOLUTION_ANGLE = "solution_angle"


@dataclass(frozen=True, slots=True)
class SourceTextField:
    """One source-item text field prepared for extraction."""

    name: str
    text: str


@dataclass(frozen=True, slots=True)
class KeywordRule:
    """Controlled-vocabulary keyword rule for one signal label."""

    canonical_value: str
    aliases: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] = ("category", "title", "subtitle", "description")

    def phrases(self) -> tuple[str, ...]:
        return (self.canonical_value, *self.aliases)


@dataclass(frozen=True, slots=True)
class PatternRule:
    """Regex-based rule that captures a signal value from raw text."""

    name: str
    pattern: Pattern[str]
    allowed_fields: tuple[str, ...]
    post_process: Callable[[str], str | None] | None = None

    def build_value(self, match: Match[str]) -> str | None:
        value = match.groupdict().get("value") or match.group(0)
        if self.post_process is None:
            return value
        return self.post_process(value)


@dataclass(frozen=True, slots=True)
class ExtractedSignalCandidate:
    """Intermediate extraction result before persistence."""

    run_id: UUID
    source_item_id: UUID
    signal_type: SupportedSignalType
    signal_value: str
    normalized_value: str
    confidence: float
    extraction_method: str
    evidence_span: str | None
    field_name: str
    duplicate_key: str
