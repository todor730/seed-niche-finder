"""Semantic normalization helpers for extracted signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.extraction.dictionaries import SAFE_SINGULAR_SUFFIXES, SIGNAL_ALIAS_MAP
from app.services.extraction.normalization import clean_text, normalize_signal_value
from app.services.extraction.types import SupportedSignalType


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    """Result of semantic normalization for one extracted signal value."""

    raw_value: str
    cleaned_value: str
    normalized_value: str
    duplicate_key: str
    applied_transforms: tuple[str, ...]
    safety: str


class SemanticSignalNormalizer:
    """Conservative canonicalization layer for extracted signal values."""

    def canonicalize(self, *, signal_type: SupportedSignalType, value: str) -> CanonicalizationResult:
        raw_value = value
        cleaned_value = normalize_signal_value(value)
        if not cleaned_value:
            return CanonicalizationResult(
                raw_value=raw_value,
                cleaned_value="",
                normalized_value="",
                duplicate_key="",
                applied_transforms=(),
                safety="safe",
            )

        transforms: list[str] = []
        normalized_value = cleaned_value

        singularized = self._safe_singular_collapse(signal_type=signal_type, value=normalized_value)
        if singularized != normalized_value:
            normalized_value = singularized
            transforms.append("safe_plural_collapse")

        alias_mapped = self._alias_map(signal_type=signal_type, value=normalized_value)
        if alias_mapped != normalized_value:
            normalized_value = alias_mapped
            transforms.append("alias_map")

        typo_mapped = self._safe_typo_map(signal_type=signal_type, value=normalized_value)
        if typo_mapped != normalized_value:
            normalized_value = typo_mapped
            transforms.append("typo_cleanup")

        safety = "safe" if self._is_safe_normalization(cleaned_value, normalized_value, transforms) else "unsafe"
        duplicate_key = f"{signal_type.value}:{normalized_value}"

        return CanonicalizationResult(
            raw_value=raw_value,
            cleaned_value=cleaned_value,
            normalized_value=normalized_value,
            duplicate_key=duplicate_key,
            applied_transforms=tuple(transforms),
            safety=safety,
        )

    def suppress_duplicates(
        self,
        *,
        signal_type: SupportedSignalType,
        values: Iterable[str],
    ) -> set[str]:
        """Return canonical duplicate keys for pre-clustering suppression."""
        duplicate_keys: set[str] = set()
        for value in values:
            result = self.canonicalize(signal_type=signal_type, value=value)
            if result.normalized_value:
                duplicate_keys.add(result.duplicate_key)
        return duplicate_keys

    @staticmethod
    def _safe_singular_collapse(*, signal_type: SupportedSignalType, value: str) -> str:
        tokens = value.split()
        if not tokens:
            return value
        safe_suffixes = SAFE_SINGULAR_SUFFIXES.get(signal_type, frozenset())
        last_token = tokens[-1]
        if last_token not in safe_suffixes:
            return value
        tokens[-1] = _singularize_token(last_token)
        return " ".join(tokens)

    @staticmethod
    def _alias_map(*, signal_type: SupportedSignalType, value: str) -> str:
        return SIGNAL_ALIAS_MAP.get(signal_type, {}).get(value, value)

    def _safe_typo_map(self, *, signal_type: SupportedSignalType, value: str) -> str:
        alias_map = SIGNAL_ALIAS_MAP.get(signal_type, {})
        if value in alias_map:
            return alias_map[value]

        candidate_map = dict(alias_map)
        for canonical_value in alias_map.values():
            candidate_map.setdefault(canonical_value, canonical_value)

        best_candidate: str | None = None
        best_distance: int | None = None
        for candidate_value, canonical in candidate_map.items():
            if len(candidate_value.split()) != len(value.split()):
                continue
            distance = _levenshtein_distance(candidate_value, value)
            max_distance = 1 if len(candidate_value) <= 12 else 2
            if distance > max_distance:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_candidate = canonical
            elif best_distance is not None and distance == best_distance and best_candidate != canonical:
                return value
        return best_candidate or value

    @staticmethod
    def _is_safe_normalization(cleaned_value: str, normalized_value: str, transforms: list[str]) -> bool:
        if not transforms:
            return True
        if "typo_cleanup" in transforms and _levenshtein_distance(cleaned_value, normalized_value) > 2:
            return False
        cleaned_tokens = cleaned_value.split()
        normalized_tokens = normalized_value.split()
        if abs(len(cleaned_tokens) - len(normalized_tokens)) > 1:
            return False
        return True


def _singularize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 3:
        return f"{token[:-3]}y"
    if token.endswith("ses") and len(token) > 3:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 1:
        return token[:-1]
    return token


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            substitute_cost = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insert_cost, delete_cost, substitute_cost))
        previous = current
    return previous[-1]
