"""Decision-grade summary service for ranked niche hypotheses."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import logging
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import NicheHypothesis, ResearchRun, SignalCluster
from app.schemas.report import (
    CompetitionDensitySnapshot,
    NicheOpportunitySummary,
    RunSummaryReport,
    SignalSummary,
    SourceAgreementSnapshot,
    SummaryScoreBreakdown,
)
from app.schemas.research import DepthScoreSnapshot
from app.services.depth_score import DepthScoreService
from app.services.shared import to_depth_score_snapshot

logger = logging.getLogger(__name__)

_FLUFF_TERMS = {
    "amazing",
    "best",
    "breakthrough",
    "game-changing",
    "incredible",
    "massive potential",
    "must-have",
    "perfect",
    "revolutionary",
}
_KEY_SIGNAL_TYPES = {
    "subgenre",
    "trope",
    "audience",
    "promise",
    "tone",
    "setting",
    "relationship_dynamic",
    "problem_angle",
    "solution_angle",
}


class SummaryService:
    """Compose evidence-backed summaries from persisted ranking artifacts."""

    def __init__(self, depth_score_service: DepthScoreService | None = None) -> None:
        self._depth_score_service = depth_score_service or DepthScoreService()

    def build_run_summary_report(
        self,
        *,
        session: Session,
        run_id: UUID,
        top_k: int = 5,
    ) -> RunSummaryReport:
        """Build the final summary report for a scored research run."""
        run = session.scalar(
            select(ResearchRun)
            .where(ResearchRun.id == run_id)
            .options(
                selectinload(ResearchRun.niche_hypotheses).selectinload(NicheHypothesis.niche_scores),
                selectinload(ResearchRun.niche_hypotheses).selectinload(NicheHypothesis.primary_signal_cluster),
            )
        )
        if run is None:
            raise ValueError(f"Research run {run_id} was not found.")

        ranked_hypotheses = sorted(
            [hypothesis for hypothesis in run.niche_hypotheses if hypothesis.rank_position is not None],
            key=lambda item: (item.rank_position or 999999, -(item.overall_score or 0.0), item.hypothesis_label),
        )[:top_k]
        cluster_map = self._load_cluster_map(session=session, hypotheses=ranked_hypotheses)
        summaries = [
            self._build_hypothesis_summary(hypothesis=hypothesis, cluster_map=cluster_map)
            for hypothesis in ranked_hypotheses
        ]

        logger.info(
            "Run summary report built.",
            extra={
                "stage": "summary_report_built",
                "run_id": str(run_id),
                "summary_count": len(summaries),
            },
        )
        return RunSummaryReport(
            run_id=run.id,
            seed_niche=run.seed_niche,
            generated_at=datetime.now(UTC),
            depth_score=to_depth_score_snapshot(self._depth_score_service.calculate_for_run(session=session, run=run)),
            top_niche_opportunities=summaries,
        )

    def build_export_rows(self, *, report: RunSummaryReport) -> list[dict[str, object]]:
        """Flatten report summaries into row-oriented export records."""
        rows: list[dict[str, object]] = []
        for item in report.top_niche_opportunities:
            rows.append(
                {
                    "run_id": str(report.run_id),
                    "seed_niche": report.seed_niche,
                    "generated_at": report.generated_at.isoformat(),
                    "rank_position": item.rank_position,
                    "niche_label": item.niche_label,
                    "audience": item.audience or "",
                    "promise": item.promise or "",
                    "key_signals": "; ".join(signal.label for signal in item.key_signals),
                    "supporting_providers": "; ".join(item.source_agreement.supporting_providers),
                    "source_count": item.source_agreement.source_count,
                    "evidence_count": item.source_agreement.evidence_count,
                    "source_agreement_score": item.source_agreement.agreement_score,
                    "competition_density": item.competition_density.density_score,
                    "competition_fallback_used": item.competition_density.fallback_used,
                    "competition_limitations": "; ".join(item.competition_density.limitations),
                    "discovery_score": item.score_breakdown.discovery_score,
                    "opportunity_score": item.score_breakdown.opportunity_score,
                    "competition_score": item.score_breakdown.competition_score,
                    "confidence_score": item.score_breakdown.confidence_score,
                    "final_score": item.score_breakdown.final_score,
                    "why_it_may_work": " | ".join(item.why_it_may_work),
                    "why_it_may_fail": " | ".join(item.why_it_may_fail),
                    "risk_flags": "; ".join(item.risk_flags),
                    "next_validation_queries": " | ".join(item.next_validation_queries),
                    "rationale_summary": item.rationale_summary or "",
                }
            )
        return rows

    def _load_cluster_map(
        self,
        *,
        session: Session,
        hypotheses: Iterable[NicheHypothesis],
    ) -> dict[UUID, SignalCluster]:
        cluster_ids: set[UUID] = set()
        for hypothesis in hypotheses:
            rationale = dict(hypothesis.rationale_json or {})
            for component in rationale.get("components", []):
                cluster_id = component.get("cluster_id")
                if isinstance(cluster_id, str):
                    cluster_ids.add(UUID(cluster_id))
        if not cluster_ids:
            return {}
        clusters = list(session.scalars(select(SignalCluster).where(SignalCluster.id.in_(cluster_ids))))
        return {cluster.id: cluster for cluster in clusters}

    def _build_hypothesis_summary(
        self,
        *,
        hypothesis: NicheHypothesis,
        cluster_map: dict[UUID, SignalCluster],
    ) -> NicheOpportunitySummary:
        rationale = dict(hypothesis.rationale_json or {})
        components = [component for component in rationale.get("components", []) if isinstance(component, dict)]
        components_by_type = defaultdict(list)
        for component in components:
            signal_type = str(component.get("signal_type", "")).strip()
            if signal_type:
                components_by_type[signal_type].append(component)

        scores = {score.score_type: score for score in hypothesis.niche_scores}
        discovery_evidence = dict((scores.get("discovery_score").evidence_json if scores.get("discovery_score") else {}) or {})
        opportunity_evidence = dict((scores.get("opportunity_score").evidence_json if scores.get("opportunity_score") else {}) or {})
        competition_evidence = dict((scores.get("competition_score").evidence_json if scores.get("competition_score") else {}) or {})
        confidence_evidence = dict((scores.get("confidence_score").evidence_json if scores.get("confidence_score") else {}) or {})
        competition_features = dict(competition_evidence.get("competition_features", {}) or {})

        audience = self._first_component_label(components_by_type, "audience")
        promise = self._first_component_label(components_by_type, "promise") or self._first_component_label(components_by_type, "solution_angle")
        key_signals = self._build_key_signals(components=components, cluster_map=cluster_map)
        source_agreement = SourceAgreementSnapshot(
            source_count=hypothesis.source_count,
            evidence_count=hypothesis.evidence_count,
            supporting_providers=[str(item) for item in rationale.get("supporting_providers", [])],
            agreement_score=self._as_score(discovery_evidence.get("source_agreement")),
            repeated_appearance_score=self._as_score(discovery_evidence.get("repeated_appearance")),
            single_source_dependence_penalty=self._as_score(confidence_evidence.get("single_source_dependence_penalty")),
        )
        competition_density = CompetitionDensitySnapshot(
            density_score=self._as_score(competition_evidence.get("competition_density")),
            relevant_item_count=self._as_int(competition_features.get("relevant_item_count")),
            incumbent_dominance=self._as_score(competition_features.get("incumbent_dominance")),
            review_rating_footprint=self._as_score(competition_features.get("review_rating_footprint")),
            recency_distribution=self._as_score(competition_features.get("recency_distribution")),
            series_dominance=self._as_score(competition_features.get("series_dominance")),
            direct_match_density=self._as_score(competition_features.get("direct_match_density")),
            evidence_coverage=self._as_ratio(competition_features.get("evidence_coverage")),
            fallback_used=bool(competition_features.get("fallback_used", False)),
            limitations=self._normalize_limitations(competition_features.get("limitations", [])),
        )
        score_breakdown = SummaryScoreBreakdown(
            discovery_score=self._score_value(scores, "discovery_score"),
            opportunity_score=self._score_value(scores, "opportunity_score"),
            competition_score=self._score_value(scores, "competition_score"),
            confidence_score=self._score_value(scores, "confidence_score"),
            final_score=self._score_value(scores, "final_score"),
        )

        summary = NicheOpportunitySummary(
            hypothesis_id=hypothesis.id,
            rank_position=hypothesis.rank_position or 1,
            niche_label=hypothesis.hypothesis_label,
            audience=audience,
            promise=promise,
            key_signals=key_signals,
            source_agreement=source_agreement,
            competition_density=competition_density,
            score_breakdown=score_breakdown,
            why_it_may_work=self._build_positive_reasons(
                hypothesis_label=hypothesis.hypothesis_label,
                audience=audience,
                promise=promise,
                source_agreement=source_agreement,
                competition_density=competition_density,
                key_signals=key_signals,
                opportunity_evidence=opportunity_evidence,
            ),
            why_it_may_fail=self._build_failure_reasons(
                source_agreement=source_agreement,
                competition_density=competition_density,
                opportunity_evidence=opportunity_evidence,
                key_signals=key_signals,
            ),
            risk_flags=self._build_risk_flags(
                source_agreement=source_agreement,
                competition_density=competition_density,
                opportunity_evidence=opportunity_evidence,
            ),
            next_validation_queries=self._build_validation_queries(
                niche_label=hypothesis.hypothesis_label,
                audience=audience,
                promise=promise,
                key_signals=key_signals,
            ),
            rationale_summary=self._build_rationale_summary(
                hypothesis_label=hypothesis.hypothesis_label,
                audience=audience,
                promise=promise,
                source_agreement=source_agreement,
                competition_density=competition_density,
                key_signals=key_signals,
            ),
            traceability={
                "primary_cluster_id": str(hypothesis.primary_cluster_id),
                "supporting_source_item_ids": [str(item) for item in rationale.get("supporting_source_item_ids", [])],
                "supporting_source_titles": [str(item) for item in rationale.get("supporting_source_titles", [])],
            },
        )
        self._ensure_no_fluff(summary)
        return summary

    def _build_key_signals(
        self,
        *,
        components: list[dict[str, Any]],
        cluster_map: dict[UUID, SignalCluster],
    ) -> list[SignalSummary]:
        ordered: list[SignalSummary] = []
        seen_keys: set[tuple[str, str]] = set()
        for component in components:
            signal_type = str(component.get("signal_type", "")).strip()
            label = str(component.get("label", "")).strip()
            if signal_type not in _KEY_SIGNAL_TYPES or not label:
                continue
            key = (signal_type, label)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            aliases: list[str] = []
            cluster_id = component.get("cluster_id")
            if isinstance(cluster_id, str):
                cluster = cluster_map.get(UUID(cluster_id))
                if cluster is not None:
                    aliases = list(cluster.aliases_json or [])
            ordered.append(
                SignalSummary(
                    signal_type=signal_type,
                    label=label,
                    aliases=aliases,
                    source_count=self._as_int(component.get("source_count")),
                    item_count=self._as_int(component.get("item_count")),
                    avg_confidence=self._as_ratio(component.get("avg_confidence")),
                )
            )
        return ordered

    @staticmethod
    def _first_component_label(components_by_type: dict[str, list[dict[str, Any]]], signal_type: str) -> str | None:
        component = next(iter(components_by_type.get(signal_type, [])), None)
        if component is None:
            return None
        label = str(component.get("label", "")).strip()
        return label or None

    def _build_positive_reasons(
        self,
        *,
        hypothesis_label: str,
        audience: str | None,
        promise: str | None,
        source_agreement: SourceAgreementSnapshot,
        competition_density: CompetitionDensitySnapshot,
        key_signals: list[SignalSummary],
        opportunity_evidence: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if source_agreement.source_count >= 2:
            reasons.append(f"The label shows support across {source_agreement.source_count} providers, which reduces single-source bias.")
        if audience and self._as_score(opportunity_evidence.get("audience_clarity")) >= 60.0:
            reasons.append(f"The audience signal is explicit: {audience}.")
        if promise and self._as_score(opportunity_evidence.get("promise_strength")) >= 60.0:
            reasons.append(f"The promise is explicit enough to test directly: {promise}.")
        trope_or_angle = next(
            (signal.label for signal in key_signals if signal.signal_type in {"trope", "solution_angle", "problem_angle"}),
            None,
        )
        if trope_or_angle:
            reasons.append(f"The niche has a concrete hook rather than a broad surface label: {trope_or_angle}.")
        if competition_density.density_score <= 55.0:
            reasons.append("Competition density is not yet showing a saturated result set in the available evidence.")
        if not reasons:
            reasons.append(f"The current evidence suggests {hypothesis_label} is specific enough to validate with focused market queries.")
        return reasons[:4]

    def _build_failure_reasons(
        self,
        *,
        source_agreement: SourceAgreementSnapshot,
        competition_density: CompetitionDensitySnapshot,
        opportunity_evidence: dict[str, Any],
        key_signals: list[SignalSummary],
    ) -> list[str]:
        reasons: list[str] = []
        if competition_density.density_score >= 65.0:
            reasons.append("Competition density is elevated, so discoverability may be harder than the signal volume suggests.")
        if competition_density.fallback_used:
            reasons.append("Competition evidence is incomplete, so the crowding read is only a cautious proxy.")
        if source_agreement.source_count <= 1:
            reasons.append("Most of the evidence comes from one source, so the niche may be less stable than it looks.")
        if self._as_score(opportunity_evidence.get("genericness_penalty")) >= 30.0:
            reasons.append("The positioning still reads somewhat generic, which can weaken click-through and conversion.")
        if self._as_score(opportunity_evidence.get("audience_clarity")) < 50.0:
            reasons.append("Audience definition is weak, so messaging may drift too broad.")
        if not any(signal.signal_type in {"trope", "solution_angle", "problem_angle"} for signal in key_signals):
            reasons.append("The current signal set lacks a strong problem, trope, or solution hook.")
        return reasons[:4]

    def _build_risk_flags(
        self,
        *,
        source_agreement: SourceAgreementSnapshot,
        competition_density: CompetitionDensitySnapshot,
        opportunity_evidence: dict[str, Any],
    ) -> list[str]:
        flags: list[str] = []
        if competition_density.density_score >= 65.0:
            flags.append("high_competition_density")
        if competition_density.fallback_used:
            flags.append("public_evidence_sparse")
        if source_agreement.source_count <= 1:
            flags.append("single_source_dependence")
        if self._as_score(opportunity_evidence.get("genericness_penalty")) >= 30.0:
            flags.append("generic_positioning")
        if self._as_score(opportunity_evidence.get("audience_clarity")) < 50.0:
            flags.append("weak_audience_definition")
        if self._as_score(opportunity_evidence.get("promise_strength")) < 50.0:
            flags.append("weak_promise_strength")
        return flags

    def _build_validation_queries(
        self,
        *,
        niche_label: str,
        audience: str | None,
        promise: str | None,
        key_signals: list[SignalSummary],
    ) -> list[str]:
        queries = [niche_label]
        if audience:
            queries.append(f"{niche_label} for {audience}")
        if promise:
            queries.append(f"{niche_label} {promise}")
        high_signal = next(
            (signal.label for signal in key_signals if signal.signal_type in {"trope", "setting", "solution_angle", "problem_angle"}),
            None,
        )
        if high_signal and high_signal not in niche_label:
            queries.append(f"{niche_label} {high_signal}")

        normalized: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = " ".join(query.split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized[:4]

    def _build_rationale_summary(
        self,
        *,
        hypothesis_label: str,
        audience: str | None,
        promise: str | None,
        source_agreement: SourceAgreementSnapshot,
        competition_density: CompetitionDensitySnapshot,
        key_signals: list[SignalSummary],
    ) -> str:
        signal_bits = [signal.label for signal in key_signals[:3]]
        parts = [f"{hypothesis_label} is backed by {source_agreement.evidence_count} relevant items"]
        if source_agreement.supporting_providers:
            parts.append(f"across {len(source_agreement.supporting_providers)} providers")
        if audience:
            parts.append(f"with a visible audience signal for {audience}")
        if promise:
            parts.append(f"and an explicit promise around {promise}")
        if signal_bits:
            parts.append(f"plus supporting signals such as {', '.join(signal_bits)}")
        if competition_density.fallback_used:
            parts.append("while competition density remains a cautious proxy because public evidence is thin")
        elif competition_density.density_score >= 65.0:
            parts.append("but the competition read is already crowded")
        return " ".join(parts) + "."

    @staticmethod
    def _score_value(scores: dict[str, Any], score_type: str) -> float:
        score = scores.get(score_type)
        if score is None:
            return 0.0
        return round(float(score.score_value or 0.0), 1)

    @staticmethod
    def _as_score(value: Any) -> float:
        try:
            return round(max(0.0, min(100.0, float(value))), 1)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_ratio(value: Any) -> float:
        try:
            return round(max(0.0, min(1.0, float(value))), 2)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_limitations(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = " ".join(value.split()).strip()
            return [cleaned] if cleaned else []
        if isinstance(value, (list, tuple, set)):
            limitations: list[str] = []
            seen: set[str] = set()
            for item in value:
                cleaned = " ".join(str(item).split()).strip()
                if not cleaned or cleaned in seen:
                    continue
                seen.add(cleaned)
                limitations.append(cleaned)
            return limitations
        cleaned = " ".join(str(value).split()).strip()
        return [cleaned] if cleaned else []

    @staticmethod
    def _ensure_no_fluff(summary: NicheOpportunitySummary) -> None:
        rendered = " ".join(
            [
                *(summary.why_it_may_work or []),
                *(summary.why_it_may_fail or []),
                summary.rationale_summary or "",
            ]
        ).lower()
        for term in _FLUFF_TERMS:
            if term in rendered:
                raise ValueError(f"Summary output included forbidden fluffy language: {term}")
