"""Aggregate repository queries for research-run depth metrics."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ExtractedSignal, NicheHypothesis, ProviderFailureRecord, SignalCluster, SourceItem, SourceQuery


@dataclass(slots=True)
class ResearchRunDepthMetrics:
    """Honest aggregate metrics used to calculate a run depth score."""

    run_id: UUID
    source_queries_count: int = 0
    source_items_count: int = 0
    extracted_signals_count: int = 0
    signal_clusters_count: int = 0
    niche_hypotheses_count: int = 0
    provider_failures_count: int = 0
    evidence_provider_count: int = 0

    @property
    def successful_queries_count(self) -> int:
        """Successful persisted queries currently equal the stored source query count."""
        return self.source_queries_count

    @property
    def attempted_queries_count(self) -> int:
        """Best-effort attempted query count from persisted success and failure traces."""
        return self.successful_queries_count + self.provider_failures_count

    @property
    def query_success_rate(self) -> float | None:
        """Return a bounded success ratio when attempts are traceable."""
        attempts = self.attempted_queries_count
        if attempts <= 0:
            return None
        return self.successful_queries_count / attempts


class ResearchRunDepthRepository:
    """Thin aggregate persistence access for run-level depth metrics."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_metrics(self, run_id: UUID) -> ResearchRunDepthMetrics:
        """Return aggregate depth metrics for one run."""
        return self.get_metrics_for_runs([run_id]).get(run_id, ResearchRunDepthMetrics(run_id=run_id))

    def get_metrics_for_runs(self, run_ids: list[UUID]) -> dict[UUID, ResearchRunDepthMetrics]:
        """Return aggregate depth metrics for many runs."""
        if not run_ids:
            return {}

        metrics = {run_id: ResearchRunDepthMetrics(run_id=run_id) for run_id in run_ids}

        for run_id, count in self.session.execute(
            select(SourceQuery.run_id, func.count(SourceQuery.id))
            .where(SourceQuery.run_id.in_(run_ids))
            .group_by(SourceQuery.run_id)
        ).all():
            metrics[run_id].source_queries_count = int(count or 0)

        for run_id, count, provider_count in self.session.execute(
            select(
                SourceItem.run_id,
                func.count(SourceItem.id),
                func.count(func.distinct(SourceItem.provider_name)),
            )
            .where(SourceItem.run_id.in_(run_ids))
            .group_by(SourceItem.run_id)
        ).all():
            metrics[run_id].source_items_count = int(count or 0)
            metrics[run_id].evidence_provider_count = int(provider_count or 0)

        for run_id, count in self.session.execute(
            select(ExtractedSignal.run_id, func.count(ExtractedSignal.id))
            .where(ExtractedSignal.run_id.in_(run_ids))
            .group_by(ExtractedSignal.run_id)
        ).all():
            metrics[run_id].extracted_signals_count = int(count or 0)

        for run_id, count in self.session.execute(
            select(SignalCluster.run_id, func.count(SignalCluster.id))
            .where(SignalCluster.run_id.in_(run_ids))
            .group_by(SignalCluster.run_id)
        ).all():
            metrics[run_id].signal_clusters_count = int(count or 0)

        for run_id, count in self.session.execute(
            select(NicheHypothesis.run_id, func.count(NicheHypothesis.id))
            .where(NicheHypothesis.run_id.in_(run_ids))
            .group_by(NicheHypothesis.run_id)
        ).all():
            metrics[run_id].niche_hypotheses_count = int(count or 0)

        for run_id, count in self.session.execute(
            select(ProviderFailureRecord.run_id, func.count(ProviderFailureRecord.id))
            .where(ProviderFailureRecord.run_id.in_(run_ids))
            .group_by(ProviderFailureRecord.run_id)
        ).all():
            metrics[run_id].provider_failures_count = int(count or 0)

        return metrics
