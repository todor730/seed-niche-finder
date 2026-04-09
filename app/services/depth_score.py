"""Explainable runtime depth scoring for research runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import ResearchRun, ResearchRunStatus
from app.db.repositories import ResearchRunDepthMetrics, ResearchRunDepthRepository


@dataclass(slots=True)
class DepthScoreResult:
    """Runtime-computed depth score with explainable factors and raw metrics."""

    score: float
    query_breadth: float
    provider_coverage: float
    evidence_volume: float
    signal_depth: float
    cluster_diversity: float
    hypothesis_support: float
    failure_adjustment: float
    metrics: ResearchRunDepthMetrics


def calculate_depth_score(
    *,
    run_status: ResearchRunStatus,
    metrics: ResearchRunDepthMetrics,
) -> DepthScoreResult:
    """Calculate a bounded 0..100 depth score from persisted evidence metrics."""
    if metrics.source_items_count <= 0:
        return DepthScoreResult(
            score=0.0,
            query_breadth=0.0,
            provider_coverage=0.0,
            evidence_volume=0.0,
            signal_depth=0.0,
            cluster_diversity=0.0,
            hypothesis_support=0.0,
            failure_adjustment=_failure_adjustment(metrics),
            metrics=metrics,
        )

    query_success_rate = metrics.query_success_rate or 0.0
    query_breadth = round(
        (
            0.7 * _saturating_score(metrics.attempted_queries_count, target=8.0)
            + 0.3 * _ratio_to_score(query_success_rate)
        ),
        1,
    )
    provider_coverage = round(_saturating_score(metrics.evidence_provider_count, target=2.0), 1)
    evidence_volume = round(_saturating_score(metrics.source_items_count, target=12.0), 1)

    signals_per_item = metrics.extracted_signals_count / max(metrics.source_items_count, 1)
    signal_depth = round(
        (
            0.65 * _saturating_score(signals_per_item, target=3.0)
            + 0.35 * _saturating_score(metrics.extracted_signals_count, target=24.0)
        ),
        1,
    )

    clusters_per_item = metrics.signal_clusters_count / max(metrics.source_items_count, 1)
    cluster_diversity = round(
        (
            0.6 * _saturating_score(metrics.signal_clusters_count, target=8.0)
            + 0.4 * _saturating_score(clusters_per_item, target=0.6)
        ),
        1,
    )

    if metrics.niche_hypotheses_count <= 0:
        hypothesis_support = 0.0
    else:
        items_per_hypothesis = metrics.source_items_count / max(metrics.niche_hypotheses_count, 1)
        hypothesis_support = round(
            (
                0.5 * _saturating_score(metrics.niche_hypotheses_count, target=4.0)
                + 0.5 * _saturating_score(items_per_hypothesis, target=3.0)
            ),
            1,
        )

    failure_adjustment = _failure_adjustment(metrics)
    weighted_score = (
        0.18 * query_breadth
        + 0.14 * provider_coverage
        + 0.22 * evidence_volume
        + 0.16 * signal_depth
        + 0.14 * cluster_diversity
        + 0.16 * hypothesis_support
    )
    final_score = max(0.0, min(100.0, round(weighted_score - failure_adjustment, 1)))
    if run_status == ResearchRunStatus.COMPLETED_NO_EVIDENCE:
        final_score = min(final_score, 10.0)

    return DepthScoreResult(
        score=final_score,
        query_breadth=query_breadth,
        provider_coverage=provider_coverage,
        evidence_volume=evidence_volume,
        signal_depth=signal_depth,
        cluster_diversity=cluster_diversity,
        hypothesis_support=hypothesis_support,
        failure_adjustment=failure_adjustment,
        metrics=metrics,
    )


class DepthScoreService:
    """Service wrapper around aggregate run metrics and the depth-score formula."""

    def calculate_for_run(
        self,
        *,
        session: Session,
        run: ResearchRun,
    ) -> DepthScoreResult:
        """Return the runtime-computed depth score for one run."""
        repository = ResearchRunDepthRepository(session)
        metrics = repository.get_metrics(run.id)
        return calculate_depth_score(run_status=run.status, metrics=metrics)

    def calculate_for_runs(
        self,
        *,
        session: Session,
        runs: Iterable[ResearchRun],
    ) -> dict[UUID, DepthScoreResult]:
        """Return runtime-computed depth scores for many runs."""
        run_list = list(runs)
        if not run_list:
            return {}

        repository = ResearchRunDepthRepository(session)
        metrics_map = repository.get_metrics_for_runs([run.id for run in run_list])
        return {
            run.id: calculate_depth_score(
                run_status=run.status,
                metrics=metrics_map.get(run.id, ResearchRunDepthMetrics(run_id=run.id)),
            )
            for run in run_list
        }


def _failure_adjustment(metrics: ResearchRunDepthMetrics) -> float:
    """Return a bounded penalty for noisy or failure-heavy evidence collection."""
    attempts = metrics.attempted_queries_count
    if attempts <= 0:
        return 0.0
    failure_rate = metrics.provider_failures_count / attempts
    penalty = failure_rate * 15.0
    if metrics.provider_failures_count >= 3:
        penalty += 5.0
    return round(min(20.0, penalty), 1)


def _ratio_to_score(value: float) -> float:
    """Scale a 0..1 ratio into a 0..100 bounded score."""
    return round(max(0.0, min(100.0, value * 100.0)), 1)


def _saturating_score(value: float, *, target: float) -> float:
    """Map a non-negative value into a 0..100 score using an explainable saturation target."""
    if target <= 0:
        return 0.0
    bounded = max(0.0, min(1.0, value / target))
    return round(bounded * 100.0, 1)
