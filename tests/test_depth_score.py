from __future__ import annotations

from uuid import UUID

from app.db.models import ResearchRunStatus
from app.db.repositories.research_run_depth import ResearchRunDepthMetrics
from app.services.depth_score import calculate_depth_score


def test_depth_score_is_zero_when_no_source_items_exist() -> None:
    metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        source_queries_count=6,
        extracted_signals_count=12,
        signal_clusters_count=5,
        niche_hypotheses_count=3,
        provider_failures_count=2,
        evidence_provider_count=2,
    )

    score = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED_NO_EVIDENCE, metrics=metrics)

    assert score.score == 0.0
    assert score.evidence_volume == 0.0
    assert score.signal_depth == 0.0
    assert score.cluster_diversity == 0.0
    assert score.hypothesis_support == 0.0


def test_completed_no_evidence_score_is_capped_even_when_metrics_are_non_zero() -> None:
    metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        source_queries_count=8,
        source_items_count=3,
        extracted_signals_count=10,
        signal_clusters_count=4,
        niche_hypotheses_count=1,
        provider_failures_count=1,
        evidence_provider_count=1,
    )

    score = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED_NO_EVIDENCE, metrics=metrics)

    assert score.score <= 10.0
    assert score.score >= 0.0


def test_provider_failures_reduce_depth_score() -> None:
    baseline_metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000003"),
        source_queries_count=8,
        source_items_count=12,
        extracted_signals_count=30,
        signal_clusters_count=8,
        niche_hypotheses_count=4,
        provider_failures_count=0,
        evidence_provider_count=2,
    )
    degraded_metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000004"),
        source_queries_count=8,
        source_items_count=12,
        extracted_signals_count=30,
        signal_clusters_count=8,
        niche_hypotheses_count=4,
        provider_failures_count=4,
        evidence_provider_count=2,
    )

    baseline = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED, metrics=baseline_metrics)
    degraded = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED, metrics=degraded_metrics)

    assert baseline.score > degraded.score
    assert degraded.failure_adjustment > baseline.failure_adjustment
    assert degraded.metrics.query_success_rate is not None
    assert degraded.metrics.query_success_rate < 1.0


def test_depth_score_rewards_evidence_and_signal_depth() -> None:
    shallow_metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000005"),
        source_queries_count=2,
        source_items_count=2,
        extracted_signals_count=2,
        signal_clusters_count=1,
        niche_hypotheses_count=1,
        provider_failures_count=0,
        evidence_provider_count=1,
    )
    deep_metrics = ResearchRunDepthMetrics(
        run_id=UUID("00000000-0000-0000-0000-000000000006"),
        source_queries_count=8,
        source_items_count=12,
        extracted_signals_count=30,
        signal_clusters_count=8,
        niche_hypotheses_count=4,
        provider_failures_count=0,
        evidence_provider_count=2,
    )

    shallow = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED, metrics=shallow_metrics)
    deep = calculate_depth_score(run_status=ResearchRunStatus.COMPLETED, metrics=deep_metrics)

    assert deep.score > shallow.score
    assert deep.query_breadth > shallow.query_breadth
    assert deep.evidence_volume > shallow.evidence_volume
    assert deep.signal_depth > shallow.signal_depth
    assert deep.cluster_diversity > shallow.cluster_diversity
