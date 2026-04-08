"""Rule-based extraction service for persisted source items."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import logging
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.db.models import ExtractedSignal, SourceItem, SourceItemStatus
from app.db.repositories.extracted_signals import ExtractedSignalRepository
from app.db.repositories.source_items import SourceItemRepository
from app.schemas.evidence import ExtractedSignalCreate
from app.services.extraction.canonicalization import SemanticSignalNormalizer
from app.services.extraction.normalization import build_evidence_span, clean_text, compile_phrase_regex, normalize_signal_value
from app.services.extraction.types import ExtractedSignalCandidate, KeywordRule, PatternRule, SourceTextField, SupportedSignalType
from app.services.extraction.vocab import KEYWORD_SIGNAL_RULES, PATTERN_SIGNAL_RULES

logger = logging.getLogger(__name__)

_KEYWORD_FIELD_CONFIDENCE = {
    "category": 0.95,
    "title": 0.90,
    "subtitle": 0.84,
    "description": 0.74,
}
_PATTERN_FIELD_CONFIDENCE = {
    "title": 0.82,
    "subtitle": 0.78,
    "description": 0.70,
}
_ALIAS_PENALTY = 0.05
_CORROBORATION_BONUS = 0.05
_MAX_CORROBORATION_BONUS = 0.10
_MIN_CONFIDENCE = 0.55


class RuleBasedExtractionService:
    """Deterministic rule-based extraction over persisted raw source items."""

    def __init__(
        self,
        *,
        keyword_rules: dict[SupportedSignalType, tuple[KeywordRule, ...]] | None = None,
        pattern_rules: dict[SupportedSignalType, tuple[PatternRule, ...]] | None = None,
        signal_normalizer: SemanticSignalNormalizer | None = None,
    ) -> None:
        self._keyword_rules = keyword_rules or KEYWORD_SIGNAL_RULES
        self._pattern_rules = pattern_rules or PATTERN_SIGNAL_RULES
        self._signal_normalizer = signal_normalizer or SemanticSignalNormalizer()

    def extract_and_persist(
        self,
        *,
        session: Session,
        source_items: Sequence[SourceItem],
    ) -> list[ExtractedSignal]:
        """Extract rule-based signals from source items and persist them."""
        if not source_items:
            return []

        repository = ExtractedSignalRepository(session)
        source_item_repository = SourceItemRepository(session)

        payloads: list[ExtractedSignalCreate] = []
        signal_type_counter: Counter[str] = Counter()
        for source_item in source_items:
            for candidate in self.extract_source_item(source_item):
                payloads.append(
                    ExtractedSignalCreate(
                        run_id=candidate.run_id,
                        source_item_id=candidate.source_item_id,
                        signal_type=candidate.signal_type.value,
                        signal_value=candidate.signal_value,
                        normalized_value=candidate.normalized_value,
                        confidence=candidate.confidence,
                        extraction_method=candidate.extraction_method,
                        evidence_span=candidate.evidence_span,
                    )
                )
                signal_type_counter[candidate.signal_type.value] += 1

        extracted_signals = repository.bulk_create(payloads) if payloads else []
        source_item_repository.bulk_update_status(
            source_item_ids=[source_item.id for source_item in source_items],
            status=SourceItemStatus.EXTRACTED,
        )

        logger.info(
            "Rule-based extraction completed.",
            extra={
                "stage": "rule_based_extraction_completed",
                "run_id": str(source_items[0].run_id),
                "source_item_count": len(source_items),
                "signal_count": len(extracted_signals),
                "signal_type_breakdown": dict(signal_type_counter),
            },
        )
        return extracted_signals

    def extract_source_item(self, source_item: SourceItem) -> list[ExtractedSignalCandidate]:
        """Extract and collapse signals for one source item."""
        fields = self._build_fields(source_item)
        raw_candidates = [
            *self._extract_keyword_candidates(source_item, fields),
            *self._extract_pattern_candidates(source_item, fields),
        ]
        return self._collapse_candidates(raw_candidates)

    @staticmethod
    def _build_fields(source_item: SourceItem) -> list[SourceTextField]:
        fields: list[SourceTextField] = []
        for category in source_item.categories_json:
            category_text = clean_text(category)
            if category_text:
                fields.append(SourceTextField(name="category", text=category_text))
        for field_name, value in (
            ("title", source_item.title),
            ("subtitle", source_item.subtitle),
            ("description", source_item.description_text),
        ):
            field_text = clean_text(value)
            if field_text:
                fields.append(SourceTextField(name=field_name, text=field_text))
        return fields

    def _extract_keyword_candidates(
        self,
        source_item: SourceItem,
        fields: Sequence[SourceTextField],
    ) -> list[ExtractedSignalCandidate]:
        candidates: list[ExtractedSignalCandidate] = []
        for signal_type, rules in self._keyword_rules.items():
            for rule in rules:
                for field in fields:
                    if field.name not in rule.allowed_fields:
                        continue
                    candidate = self._match_keyword_rule(source_item, signal_type, rule, field)
                    if candidate is not None:
                        candidates.append(candidate)
        return candidates

    def _match_keyword_rule(
        self,
        source_item: SourceItem,
        signal_type: SupportedSignalType,
        rule: KeywordRule,
        field: SourceTextField,
    ) -> ExtractedSignalCandidate | None:
        for phrase in sorted(rule.phrases(), key=len, reverse=True):
            match = compile_phrase_regex(phrase).search(field.text)
            if match is None:
                continue

            canonical = self._signal_normalizer.canonicalize(signal_type=signal_type, value=rule.canonical_value)
            if not canonical.normalized_value:
                return None
            signal_value = clean_text(match.group(0)) or rule.canonical_value
            evidence_span = build_evidence_span(
                field_name=field.name,
                source_text=field.text,
                start=match.start(),
                end=match.end(),
            )
            confidence = self._keyword_confidence(
                field_name=field.name,
                matched_phrase=signal_value,
                canonical_value=rule.canonical_value,
            )
            return ExtractedSignalCandidate(
                run_id=source_item.run_id,
                source_item_id=source_item.id,
                signal_type=signal_type,
                signal_value=signal_value,
                normalized_value=canonical.normalized_value,
                confidence=confidence,
                extraction_method=f"rule:{signal_type.value}:keyword_v1",
                evidence_span=evidence_span,
                field_name=field.name,
                duplicate_key=canonical.duplicate_key,
            )
        return None

    def _extract_pattern_candidates(
        self,
        source_item: SourceItem,
        fields: Sequence[SourceTextField],
    ) -> list[ExtractedSignalCandidate]:
        candidates: list[ExtractedSignalCandidate] = []
        for signal_type, rules in self._pattern_rules.items():
            for rule in rules:
                for field in fields:
                    if field.name not in rule.allowed_fields:
                        continue
                    for match in rule.pattern.finditer(field.text):
                        signal_value = rule.build_value(match)
                        if not signal_value:
                            continue
                        canonical = self._signal_normalizer.canonicalize(signal_type=signal_type, value=signal_value)
                        if not canonical.normalized_value:
                            continue
                        confidence = self._pattern_confidence(field_name=field.name)
                        if confidence < _MIN_CONFIDENCE:
                            continue
                        candidates.append(
                            ExtractedSignalCandidate(
                                run_id=source_item.run_id,
                                source_item_id=source_item.id,
                                signal_type=signal_type,
                                signal_value=clean_text(signal_value),
                                normalized_value=canonical.normalized_value,
                                confidence=confidence,
                                extraction_method=f"rule:{signal_type.value}:pattern_{rule.name}_v1",
                                evidence_span=build_evidence_span(
                                    field_name=field.name,
                                    source_text=field.text,
                                    start=match.start(),
                                    end=match.end(),
                                ),
                                field_name=field.name,
                                duplicate_key=canonical.duplicate_key,
                            )
                        )
        return candidates

    def _collapse_candidates(self, candidates: Sequence[ExtractedSignalCandidate]) -> list[ExtractedSignalCandidate]:
        grouped: dict[tuple[str, str], list[ExtractedSignalCandidate]] = {}
        for candidate in candidates:
            grouped.setdefault((candidate.signal_type.value, candidate.duplicate_key), []).append(candidate)

        collapsed: list[ExtractedSignalCandidate] = []
        for grouped_candidates in grouped.values():
            winner = max(grouped_candidates, key=lambda candidate: candidate.confidence)
            support_count = len({candidate.field_name for candidate in grouped_candidates})
            boosted_confidence = min(
                1.0,
                winner.confidence + min(_MAX_CORROBORATION_BONUS, (support_count - 1) * _CORROBORATION_BONUS),
            )
            if boosted_confidence < _MIN_CONFIDENCE:
                continue
            collapsed.append(replace(winner, confidence=round(boosted_confidence, 2)))

        collapsed.sort(key=lambda candidate: (-candidate.confidence, candidate.signal_type.value, candidate.normalized_value))
        return collapsed

    @staticmethod
    def _keyword_confidence(*, field_name: str, matched_phrase: str, canonical_value: str) -> float:
        base = _KEYWORD_FIELD_CONFIDENCE.get(field_name, 0.68)
        if normalize_signal_value(matched_phrase) != normalize_signal_value(canonical_value):
            base -= _ALIAS_PENALTY
        return round(max(_MIN_CONFIDENCE, min(1.0, base)), 2)

    @staticmethod
    def _pattern_confidence(*, field_name: str) -> float:
        return round(_PATTERN_FIELD_CONFIDENCE.get(field_name, 0.68), 2)
