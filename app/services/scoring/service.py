"""Ranking Engine v2 for evidence-backed niche hypotheses."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from math import log1p
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import NicheHypothesis, NicheHypothesisStatus, SourceItem
from app.db.repositories.niche_hypotheses import NicheHypothesisRepository
from app.db.repositories.niche_scores import NicheScoreRepository
from app.schemas.evidence import NicheHypothesisRankingUpdate, NicheScoreCreate, NicheScoreUpdate
from app.services.scoring.competition import CompetitionDensityModel

logger = logging.getLogger(__name__)

_GENERIC_LABELS = {
    "romance",
    "fiction",
    "novel",
    "books",
    "story",
    "guide",
    "system",
    "plan",
    "method",
    "readers",
    "book lovers",
    "everyone",
    "anyone",
}


@dataclass(frozen=True, slots=True)
class RankingCalibration:
    """Tunable constants for the honest heuristic ranking model."""

    discovery_weight: float = 0.26
    opportunity_weight: float = 0.29
    competition_inverse_weight: float = 0.20
    confidence_weight: float = 0.25


class HypothesisRankingService:
    """Compute explainable score components for persisted niche hypotheses."""

    def __init__(
        self,
        *,
        calibration: RankingCalibration | None = None,
        competition_model: CompetitionDensityModel | None = None,
    ) -> None:
        self._calibration = calibration or RankingCalibration()
        self._competition_model = competition_model or CompetitionDensityModel()

    def rank_and_persist(
        self,
        *,
        session: Session,
        run_id: UUID,
    ) -> list[NicheHypothesis]:
        """Compute component scores, persist them, and update ranked hypotheses."""
        hypotheses = self._load_hypotheses(session=session, run_id=run_id)
        if not hypotheses:
            return []

        score_repository = NicheScoreRepository(session)
        hypothesis_repository = NicheHypothesisRepository(session)

        ranking_rows: list[tuple[NicheHypothesis, float]] = []
        for hypothesis in hypotheses:
            supporting_source_items = self._load_supporting_source_items(session=session, hypothesis=hypothesis)
            breakdown = self._score_hypothesis(hypothesis, supporting_source_items=supporting_source_items)
            self._persist_breakdown(
                session=session,
                score_repository=score_repository,
                hypothesis=hypothesis,
                breakdown=breakdown,
            )
            ranking_rows.append((hypothesis, breakdown["final_score"]["score_value"]))

        ranking_rows.sort(key=lambda item: (-item[1], item[0].hypothesis_label))
        for index, (hypothesis, final_score) in enumerate(ranking_rows, start=1):
            hypothesis_repository.update_ranking(
                hypothesis_id=hypothesis.id,
                payload=NicheHypothesisRankingUpdate(
                    overall_score=round(final_score, 1),
                    rank_position=index,
                ),
            )
            hypothesis_repository.update_status(
                hypothesis_id=hypothesis.id,
                status=NicheHypothesisStatus.SCORED,
            )

        logger.info(
            "Niche hypothesis scores persisted.",
            extra={
                "stage": "niche_scores_persisted",
                "run_id": str(run_id),
                "hypothesis_count": len(hypotheses),
            },
        )
        return hypotheses

    def _load_hypotheses(
        self,
        *,
        session: Session,
        run_id: UUID,
    ) -> list[NicheHypothesis]:
        return list(
            session.scalars(
                select(NicheHypothesis)
                .where(NicheHypothesis.run_id == run_id)
                .options(selectinload(NicheHypothesis.primary_signal_cluster), selectinload(NicheHypothesis.niche_scores))
            )
        )

    def _load_supporting_source_items(
        self,
        *,
        session: Session,
        hypothesis: NicheHypothesis,
    ) -> list[SourceItem]:
        rationale = dict(hypothesis.rationale_json or {})
        source_item_ids = [
            UUID(value)
            for value in rationale.get("supporting_source_item_ids", [])
            if isinstance(value, str)
        ]
        if not source_item_ids:
            return []
        return list(session.scalars(select(SourceItem).where(SourceItem.id.in_(source_item_ids))))

    def _score_hypothesis(
        self,
        hypothesis: NicheHypothesis,
        *,
        supporting_source_items: Sequence[SourceItem],
    ) -> dict[str, dict[str, Any]]:
        rationale = dict(hypothesis.rationale_json or {})
        components = list(rationale.get("components", []))
        supporting_providers = list(rationale.get("supporting_providers", []))
        evidence_count = hypothesis.evidence_count
        source_count = hypothesis.source_count
        label = hypothesis.hypothesis_label
        component_labels = [str(component.get("label", "")) for component in components]

        source_agreement = self._source_agreement_score(source_count=source_count)
        specificity = self._specificity_score(label=label)
        repeated_appearance = self._repeated_appearance_score(evidence_count=evidence_count)
        audience_clarity = self._audience_clarity_score(components=components)
        promise_strength = self._promise_strength_score(components=components, label=label)
        genericness_penalty = self._genericness_penalty(label=label, components=components)
        competition_assessment = self._competition_model.assess(
            hypothesis_label=label,
            source_items=supporting_source_items,
            component_labels=component_labels,
        )
        competition_density = competition_assessment.density_score
        single_source_dependence_penalty = self._single_source_penalty(source_count=source_count)
        novelty_proxy = self._novelty_proxy(components=components)
        anchor_confidence = float(rationale.get("anchor_avg_confidence", 0.0)) * 100.0

        discovery_score = _bounded(
            source_agreement * 0.28
            + specificity * 0.24
            + repeated_appearance * 0.24
            + novelty_proxy * 0.24
        )
        opportunity_score = _bounded(
            specificity * 0.25
            + audience_clarity * 0.25
            + promise_strength * 0.30
            + novelty_proxy * 0.20
            - genericness_penalty * 0.20
        )
        competition_score = _bounded(
            competition_density * 0.68
            + genericness_penalty * 0.22
            + max(0.0, 100.0 - novelty_proxy) * 0.10
        )
        confidence_score = _bounded(
            source_agreement * 0.32
            + repeated_appearance * 0.23
            + anchor_confidence * 0.25
            + min(100.0, source_count * 18.0) * 0.20
            - single_source_dependence_penalty
        )
        final_score = _bounded(
            discovery_score * self._calibration.discovery_weight
            + opportunity_score * self._calibration.opportunity_weight
            + (100.0 - competition_score) * self._calibration.competition_inverse_weight
            + confidence_score * self._calibration.confidence_weight
        )

        return {
            "discovery_score": self._score_entry(
                score_value=discovery_score,
                weight=self._calibration.discovery_weight,
                evidence_count=evidence_count,
                rationale="Discovery reflects source agreement, specificity, repeated appearance, and novelty proxy.",
                evidence_json={
                    "source_agreement": round(source_agreement, 1),
                    "specificity": round(specificity, 1),
                    "repeated_appearance": round(repeated_appearance, 1),
                    "novelty_proxy": round(novelty_proxy, 1),
                },
            ),
            "opportunity_score": self._score_entry(
                score_value=opportunity_score,
                weight=self._calibration.opportunity_weight,
                evidence_count=evidence_count,
                rationale="Opportunity reflects audience clarity, promise strength, specificity, and novelty minus genericness.",
                evidence_json={
                    "audience_clarity": round(audience_clarity, 1),
                    "promise_strength": round(promise_strength, 1),
                    "specificity": round(specificity, 1),
                    "novelty_proxy": round(novelty_proxy, 1),
                    "genericness_penalty": round(genericness_penalty, 1),
                },
            ),
            "competition_score": self._score_entry(
                score_value=competition_score,
                weight=self._calibration.competition_inverse_weight,
                evidence_count=evidence_count,
                rationale=competition_assessment.rationale,
                evidence_json={
                    "competition_density": round(competition_density, 1),
                    "genericness_penalty": round(genericness_penalty, 1),
                    "novelty_proxy": round(novelty_proxy, 1),
                    "competition_features": competition_assessment.evidence_json,
                },
            ),
            "confidence_score": self._score_entry(
                score_value=confidence_score,
                weight=self._calibration.confidence_weight,
                evidence_count=evidence_count,
                rationale="Confidence reflects evidence volume, source agreement, anchor confidence, and single-source dependence penalty.",
                evidence_json={
                    "source_agreement": round(source_agreement, 1),
                    "repeated_appearance": round(repeated_appearance, 1),
                    "anchor_confidence": round(anchor_confidence, 1),
                    "single_source_dependence_penalty": round(single_source_dependence_penalty, 1),
                    "supporting_providers": supporting_providers,
                },
            ),
            "final_score": self._score_entry(
                score_value=final_score,
                weight=1.0,
                evidence_count=evidence_count,
                rationale="Final score is a weighted blend of discovery, opportunity, inverse competition, and confidence.",
                evidence_json={
                    "component_weights": {
                        "discovery": self._calibration.discovery_weight,
                        "opportunity": self._calibration.opportunity_weight,
                        "competition_inverse": self._calibration.competition_inverse_weight,
                        "confidence": self._calibration.confidence_weight,
                    },
                    "component_scores": {
                        "discovery_score": round(discovery_score, 1),
                        "opportunity_score": round(opportunity_score, 1),
                        "competition_score": round(competition_score, 1),
                        "confidence_score": round(confidence_score, 1),
                    },
                },
            ),
        }

    def _persist_breakdown(
        self,
        *,
        session: Session,
        score_repository: NicheScoreRepository,
        hypothesis: NicheHypothesis,
        breakdown: dict[str, dict[str, Any]],
    ) -> None:
        existing_scores = {score.score_type: score for score in hypothesis.niche_scores}
        for score_type, payload in breakdown.items():
            if score_type in existing_scores:
                score_repository.update(
                    niche_score_id=existing_scores[score_type].id,
                    payload=NicheScoreUpdate(
                        score_value=payload["score_value"],
                        weight=payload["weight"],
                        weighted_score=payload["weighted_score"],
                        evidence_count=payload["evidence_count"],
                        rationale=payload["rationale"],
                        evidence_json=payload["evidence_json"],
                    ),
                )
                continue

            score_repository.create(
                NicheScoreCreate(
                    run_id=hypothesis.run_id,
                    niche_hypothesis_id=hypothesis.id,
                    score_type=score_type,
                    score_value=payload["score_value"],
                    weight=payload["weight"],
                    weighted_score=payload["weighted_score"],
                    evidence_count=payload["evidence_count"],
                    rationale=payload["rationale"],
                    evidence_json=payload["evidence_json"],
                )
            )

    @staticmethod
    def _score_entry(
        *,
        score_value: float,
        weight: float,
        evidence_count: int,
        rationale: str,
        evidence_json: dict[str, Any],
    ) -> dict[str, Any]:
        bounded_value = round(_bounded(score_value), 1)
        return {
            "score_value": bounded_value,
            "weight": round(weight, 3),
            "weighted_score": round(bounded_value * weight, 2),
            "evidence_count": evidence_count,
            "rationale": rationale,
            "evidence_json": evidence_json,
        }

    @staticmethod
    def _source_agreement_score(*, source_count: int) -> float:
        return min(100.0, 42.0 + source_count * 22.0)

    @staticmethod
    def _specificity_score(*, label: str) -> float:
        tokens = [token for token in label.split() if token]
        token_score = min(100.0, len(tokens) * 18.0)
        long_token_bonus = min(18.0, sum(1 for token in tokens if len(token) >= 7) * 3.5)
        return _bounded(token_score + long_token_bonus)

    @staticmethod
    def _repeated_appearance_score(*, evidence_count: int) -> float:
        return min(100.0, 35.0 + log1p(max(evidence_count, 0)) * 28.0)

    @staticmethod
    def _audience_clarity_score(*, components: Sequence[dict[str, Any]]) -> float:
        audience = next((component for component in components if component.get("signal_type") == "audience"), None)
        if audience is None:
            return 28.0
        label = str(audience.get("label", ""))
        if label in _GENERIC_LABELS:
            return 22.0
        return _bounded(70.0 + float(audience.get("cooccurrence_ratio", 0.0)) * 20.0)

    @staticmethod
    def _promise_strength_score(*, components: Sequence[dict[str, Any]], label: str) -> float:
        promise = next((component for component in components if component.get("signal_type") == "promise"), None)
        if promise is not None:
            return _bounded(72.0 + float(promise.get("cooccurrence_ratio", 0.0)) * 18.0)

        trope = next((component for component in components if component.get("signal_type") == "trope"), None)
        solution = next((component for component in components if component.get("signal_type") == "solution_angle"), None)
        if trope is not None:
            return _bounded(66.0 + float(trope.get("cooccurrence_ratio", 0.0)) * 16.0)
        if solution is not None:
            return _bounded(64.0 + float(solution.get("cooccurrence_ratio", 0.0)) * 18.0)
        return 38.0 if len(label.split()) <= 2 else 48.0

    @staticmethod
    def _genericness_penalty(*, label: str, components: Sequence[dict[str, Any]]) -> float:
        label_tokens = set(label.split())
        generic_hits = len(label_tokens & _GENERIC_LABELS)
        base_penalty = generic_hits * 16.0
        if len(label_tokens) <= 2:
            base_penalty += 20.0
        if not any(component.get("signal_type") in {"trope", "solution_angle", "audience", "promise"} for component in components):
            base_penalty += 10.0
        return _bounded(base_penalty)

    @staticmethod
    def _single_source_penalty(*, source_count: int) -> float:
        if source_count <= 1:
            return 18.0
        if source_count == 2:
            return 6.0
        return 0.0

    def _novelty_proxy(self, *, components: Sequence[dict[str, Any]]) -> float:
        explicit_novelty = [float(component["novelty_score"]) for component in components if "novelty_score" in component]
        if explicit_novelty:
            return _bounded(sum(explicit_novelty) / len(explicit_novelty))

        specificity_bonus = sum(1 for component in components if len(str(component.get("label", "")).split()) >= 3) * 8.0
        trope_bonus = 12.0 if any(component.get("signal_type") == "trope" for component in components) else 0.0
        audience_bonus = 8.0 if any(component.get("signal_type") == "audience" for component in components) else 0.0
        return _bounded(38.0 + specificity_bonus + trope_bonus + audience_bonus)


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))
