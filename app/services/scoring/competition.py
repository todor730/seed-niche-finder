"""Dedicated competition density model for niche hypothesis ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import log1p
import re
from typing import Any, Sequence

from app.db.models import SourceItem

_SERIES_MARKERS_RE = re.compile(
    r"\b(?:book\s+\d+|series|trilogy|saga|collection|box set|volume\s+\d+|vol\.\s*\d+)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass(frozen=True, slots=True)
class CompetitionModelCalibration:
    """Calibration hooks for the dedicated competition density model."""

    low_evidence_floor: float = 42.0
    low_evidence_ceiling: float = 58.0
    relevant_item_weight: float = 0.18
    incumbent_dominance_weight: float = 0.18
    review_footprint_weight: float = 0.19
    recency_distribution_weight: float = 0.15
    series_dominance_weight: float = 0.12
    direct_match_density_weight: float = 0.18


@dataclass(frozen=True, slots=True)
class CompetitionFeatures:
    """Extracted competition features for one hypothesis."""

    relevant_item_count: int
    source_count: int
    incumbent_dominance: float
    review_rating_footprint: float
    recency_distribution: float
    series_dominance: float
    direct_match_density: float
    evidence_coverage: float
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class CompetitionAssessment:
    """Explainable competition-density assessment."""

    density_score: float
    rationale: str
    evidence_json: dict[str, Any]
    features: CompetitionFeatures


class CompetitionDensityModel:
    """Dedicated competition feature extractor and density scorer."""

    def __init__(self, *, calibration: CompetitionModelCalibration | None = None) -> None:
        self._calibration = calibration or CompetitionModelCalibration()

    def assess(
        self,
        *,
        hypothesis_label: str,
        source_items: Sequence[SourceItem],
        component_labels: Sequence[str],
    ) -> CompetitionAssessment:
        """Return a competition density assessment for one hypothesis."""
        features = self._extract_features(
            hypothesis_label=hypothesis_label,
            source_items=source_items,
            component_labels=component_labels,
        )

        if features.fallback_used:
            density_score = _bounded(
                self._calibration.low_evidence_floor
                + (features.relevant_item_count * 4.0)
                + features.direct_match_density * 0.12
            )
            rationale = "Competition density uses a low-confidence fallback because provider evidence lacks sufficient market footprint signals."
        else:
            density_score = _bounded(
                features.relevant_item_count * 14.0 * self._calibration.relevant_item_weight
                + features.incumbent_dominance * self._calibration.incumbent_dominance_weight
                + features.review_rating_footprint * self._calibration.review_footprint_weight
                + features.recency_distribution * self._calibration.recency_distribution_weight
                + features.series_dominance * self._calibration.series_dominance_weight
                + features.direct_match_density * self._calibration.direct_match_density_weight
            )
            rationale = "Competition density reflects relevant item volume, incumbent dominance, review footprint, recency concentration, series dominance, and direct query-surface match density."

        evidence_json = {
            "relevant_item_count": features.relevant_item_count,
            "source_count": features.source_count,
            "incumbent_dominance": round(features.incumbent_dominance, 1),
            "review_rating_footprint": round(features.review_rating_footprint, 1),
            "recency_distribution": round(features.recency_distribution, 1),
            "series_dominance": round(features.series_dominance, 1),
            "direct_match_density": round(features.direct_match_density, 1),
            "evidence_coverage": round(features.evidence_coverage, 2),
            "fallback_used": features.fallback_used,
            "limitations": [
                "Public-only provider evidence may understate true marketplace competition when review/rating or catalog breadth signals are sparse."
            ],
        }
        return CompetitionAssessment(
            density_score=round(density_score, 1),
            rationale=rationale,
            evidence_json=evidence_json,
            features=features,
        )

    def _extract_features(
        self,
        *,
        hypothesis_label: str,
        source_items: Sequence[SourceItem],
        component_labels: Sequence[str],
    ) -> CompetitionFeatures:
        relevant_items = [item for item in source_items if _is_relevant_item(item=item, hypothesis_label=hypothesis_label, component_labels=component_labels)]
        if not relevant_items:
            return CompetitionFeatures(
                relevant_item_count=0,
                source_count=0,
                incumbent_dominance=self._calibration.low_evidence_floor,
                review_rating_footprint=self._calibration.low_evidence_floor,
                recency_distribution=self._calibration.low_evidence_floor,
                series_dominance=self._calibration.low_evidence_floor,
                direct_match_density=self._calibration.low_evidence_floor,
                evidence_coverage=0.0,
                fallback_used=True,
            )

        relevant_item_count = len(relevant_items)
        source_count = len({item.provider_name for item in relevant_items})
        review_like_values = [_review_like_footprint(item) for item in relevant_items if _review_like_footprint(item) is not None]
        incumbent_dominance = _incumbent_dominance_score(review_like_values)
        review_rating_footprint = _review_rating_footprint_score(review_like_values)
        recency_distribution = _recency_distribution_score(relevant_items)
        series_dominance = _series_dominance_score(relevant_items)
        direct_match_density = _direct_match_density_score(
            relevant_items=relevant_items,
            hypothesis_label=hypothesis_label,
            component_labels=component_labels,
        )

        coverage_flags = [
            bool(review_like_values),
            any(_extract_year(item.published_date_raw) is not None for item in relevant_items),
            any(_looks_like_series(item.title) for item in relevant_items),
            True,
        ]
        evidence_coverage = sum(1 for flag in coverage_flags if flag) / len(coverage_flags)
        fallback_used = evidence_coverage < 0.50

        return CompetitionFeatures(
            relevant_item_count=relevant_item_count,
            source_count=source_count,
            incumbent_dominance=incumbent_dominance,
            review_rating_footprint=review_rating_footprint,
            recency_distribution=recency_distribution,
            series_dominance=series_dominance,
            direct_match_density=direct_match_density,
            evidence_coverage=evidence_coverage,
            fallback_used=fallback_used,
        )


def _is_relevant_item(*, item: SourceItem, hypothesis_label: str, component_labels: Sequence[str]) -> bool:
    item_surface = " ".join(
        [
            item.title,
            item.subtitle or "",
            " ".join(item.categories_json),
            item.description_text or "",
        ]
    ).lower()
    hypothesis_tokens = set(hypothesis_label.lower().split())
    if not hypothesis_tokens:
        return False
    overlap = len(hypothesis_tokens & set(item_surface.split()))
    if overlap >= max(2, len(hypothesis_tokens) // 2):
        return True
    return any(component_label.lower() in item_surface for component_label in component_labels if component_label)


def _review_like_footprint(item: SourceItem) -> float | None:
    review_count = item.review_count or 0
    rating_count = item.rating_count or 0
    if review_count == 0 and rating_count == 0:
        return None
    rating_strength = (item.average_rating or 0.0) / 5.0
    return log1p(review_count + rating_count) * (0.65 + rating_strength * 0.35) * 18.0


def _incumbent_dominance_score(review_like_values: Sequence[float]) -> float:
    if not review_like_values:
        return 50.0
    ordered = sorted(review_like_values, reverse=True)
    total = sum(ordered)
    if total <= 0:
        return 50.0
    top_share = ordered[0] / total
    top_three_share = sum(ordered[:3]) / total
    return _bounded(top_share * 45.0 + top_three_share * 55.0)


def _review_rating_footprint_score(review_like_values: Sequence[float]) -> float:
    if not review_like_values:
        return 48.0
    average = sum(review_like_values) / len(review_like_values)
    return _bounded(min(100.0, average * 1.6))


def _recency_distribution_score(relevant_items: Sequence[SourceItem]) -> float:
    current_year = datetime.now(UTC).year
    years = [_extract_year(item.published_date_raw) for item in relevant_items]
    known_years = [year for year in years if year is not None]
    if not known_years:
        return 45.0
    recent_fraction = sum(1 for year in known_years if year >= current_year - 3) / len(known_years)
    very_recent_fraction = sum(1 for year in known_years if year >= current_year - 1) / len(known_years)
    return _bounded(recent_fraction * 60.0 + very_recent_fraction * 40.0)


def _series_dominance_score(relevant_items: Sequence[SourceItem]) -> float:
    if not relevant_items:
        return 0.0
    series_hits = sum(1 for item in relevant_items if _looks_like_series(item.title))
    repeated_title_prefix_hits = _repeated_prefix_fraction(relevant_items)
    fraction = series_hits / len(relevant_items)
    return _bounded(fraction * 70.0 + repeated_title_prefix_hits * 30.0)


def _direct_match_density_score(
    *,
    relevant_items: Sequence[SourceItem],
    hypothesis_label: str,
    component_labels: Sequence[str],
) -> float:
    hypothesis_tokens = set(hypothesis_label.lower().split())
    if not relevant_items or not hypothesis_tokens:
        return 0.0

    direct_matches = 0
    strong_token_matches = 0
    for item in relevant_items:
        surface = " ".join([item.title, item.subtitle or "", " ".join(item.categories_json)]).lower()
        if hypothesis_label.lower() in surface:
            direct_matches += 1
            continue
        surface_tokens = set(surface.split())
        overlap_ratio = len(hypothesis_tokens & surface_tokens) / len(hypothesis_tokens)
        if overlap_ratio >= 0.7 or any(component_label.lower() in surface for component_label in component_labels if component_label):
            strong_token_matches += 1

    return _bounded((direct_matches / len(relevant_items)) * 65.0 + (strong_token_matches / len(relevant_items)) * 35.0)


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = _YEAR_RE.search(value)
    if match is None:
        return None
    return int(match.group(0))


def _looks_like_series(title: str) -> bool:
    return bool(_SERIES_MARKERS_RE.search(title))


def _repeated_prefix_fraction(relevant_items: Sequence[SourceItem]) -> float:
    prefixes: dict[str, int] = {}
    for item in relevant_items:
        prefix = " ".join(item.title.lower().split()[:3])
        if prefix:
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
    if not prefixes:
        return 0.0
    repeated = sum(count for count in prefixes.values() if count >= 2)
    return min(1.0, repeated / len(relevant_items))


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))
