"""Explainable clustering service over extracted signals."""

from __future__ import annotations

from collections import Counter, defaultdict
import logging
from typing import Sequence

from sqlalchemy.orm import Session

from app.db.models import ExtractedSignal, SignalCluster, SourceItemStatus
from app.db.repositories.extracted_signals import ExtractedSignalRepository
from app.db.repositories.signal_clusters import SignalClusterRepository
from app.db.repositories.source_items import SourceItemRepository
from app.schemas.evidence import SignalClusterCreate
from app.services.clustering.similarity import compare_labels
from app.services.clustering.types import (
    ClusterAssignment,
    ClusterAssignmentReason,
    ClusterCandidate,
    ClusteringResult,
    PersistedClusterSummary,
    SimilarityHook,
)
from app.services.extraction.normalization import clean_text

logger = logging.getLogger(__name__)


class ClusteringService:
    """Deterministic, debug-friendly clustering over extracted signals."""

    def __init__(self, *, future_similarity_hook: SimilarityHook | None = None) -> None:
        self._future_similarity_hook = future_similarity_hook

    def cluster_and_persist(
        self,
        *,
        session: Session,
        extracted_signals: Sequence[ExtractedSignal],
    ) -> ClusteringResult:
        """Build, persist, and assign signal clusters for one research run."""
        if not extracted_signals:
            return ClusteringResult(clusters=(), assignments=())

        candidates, assignments = self._build_candidates(extracted_signals)
        persisted_clusters = self._persist_clusters(session=session, candidates=candidates)
        self._assign_signals_to_clusters(
            session=session,
            persisted_clusters=persisted_clusters,
            candidates=candidates,
            assignments=assignments,
        )
        self._mark_source_items_clustered(session=session, extracted_signals=extracted_signals)

        cluster_summaries = tuple(
            PersistedClusterSummary(
                cluster_id=cluster.id,
                signal_type=cluster.signal_type,
                canonical_label=cluster.canonical_label,
                source_count=cluster.source_count,
                item_count=cluster.item_count,
                avg_confidence=round(cluster.avg_confidence, 2),
                saturation_score=round(cluster.saturation_score, 1),
                novelty_score=round(cluster.novelty_score, 1),
            )
            for cluster in persisted_clusters
        )

        logger.info(
            "Signal clustering completed.",
            extra={
                "stage": "signal_clustering_completed",
                "run_id": str(extracted_signals[0].run_id),
                "signal_count": len(extracted_signals),
                "cluster_count": len(cluster_summaries),
                "assignment_reason_breakdown": dict(Counter(assignment.reason.value for assignment in assignments)),
            },
        )
        return ClusteringResult(clusters=cluster_summaries, assignments=tuple(assignments))

    def _build_candidates(
        self,
        extracted_signals: Sequence[ExtractedSignal],
    ) -> tuple[dict[str, ClusterCandidate], list[ClusterAssignment]]:
        candidates: dict[str, ClusterCandidate] = {}
        assignments: list[ClusterAssignment] = []
        grouped_by_type: dict[str, list[ExtractedSignal]] = defaultdict(list)
        for signal in extracted_signals:
            grouped_by_type[signal.signal_type].append(signal)

        for signal_type, type_signals in grouped_by_type.items():
            ordered_signals = sorted(
                type_signals,
                key=lambda signal: (-signal.confidence, signal.normalized_value, str(signal.id)),
            )
            type_candidates: dict[str, ClusterCandidate] = {}
            for signal in ordered_signals:
                candidate, reason, similarity_score = self._assign_signal_to_candidate(
                    signal=signal,
                    type_candidates=type_candidates,
                )
                candidate.signal_ids.append(signal.id)
                candidate.source_item_ids.add(signal.source_item_id)
                candidate.normalized_value_counts[signal.normalized_value] += 1
                candidate.normalized_value_confidence[signal.normalized_value] = (
                    candidate.normalized_value_confidence.get(signal.normalized_value, 0.0) + signal.confidence
                )
                provider_name = getattr(signal.source_item, "provider_name", None)
                if provider_name:
                    candidate.provider_names.add(provider_name)
                surface_alias = clean_text(signal.signal_value)
                if surface_alias and surface_alias.lower() != candidate.canonical_label:
                    candidate.aliases.setdefault(surface_alias.lower(), surface_alias)
                if signal.normalized_value != candidate.canonical_label:
                    candidate.normalized_variants.add(signal.normalized_value)
                candidate.confidence_sum += signal.confidence
                assignments.append(
                    ClusterAssignment(
                        signal_id=signal.id,
                        cluster_key=f"{signal.signal_type}:{candidate.canonical_label}",
                        reason=reason,
                        similarity_score=similarity_score,
                    )
                )
            candidates.update(type_candidates)
        return candidates, assignments

    def _assign_signal_to_candidate(
        self,
        *,
        signal: ExtractedSignal,
        type_candidates: dict[str, ClusterCandidate],
    ) -> tuple[ClusterCandidate, ClusterAssignmentReason, float]:
        best_candidate: ClusterCandidate | None = None
        best_reason = ClusterAssignmentReason.NEW_CLUSTER
        best_score = 0.0

        for candidate in type_candidates.values():
            for candidate_label in {candidate.canonical_label, *candidate.normalized_variants}:
                decision = compare_labels(
                    left=signal.normalized_value,
                    right=candidate_label,
                    future_hook=self._future_similarity_hook,
                    signal_type=signal.signal_type,
                )
                if not decision.matched:
                    continue
                if decision.score > best_score:
                    best_candidate = candidate
                    best_reason = decision.reason
                    best_score = decision.score

        if best_candidate is not None:
            return best_candidate, best_reason, best_score

        cluster_key = f"{signal.signal_type}:{signal.normalized_value}"
        new_candidate = ClusterCandidate(
            run_id=signal.run_id,
            signal_type=signal.signal_type,
            canonical_label=signal.normalized_value,
        )
        type_candidates[cluster_key] = new_candidate
        return new_candidate, ClusterAssignmentReason.NEW_CLUSTER, 1.0

    def _persist_clusters(
        self,
        *,
        session: Session,
        candidates: dict[str, ClusterCandidate],
    ) -> list[SignalCluster]:
        repository = SignalClusterRepository(session)
        payloads: list[SignalClusterCreate] = []

        total_items_by_type = Counter(candidate.signal_type for candidate in candidates.values())
        for candidate in candidates.values():
            canonical_label = self._choose_canonical_label(candidate)
            aliases = self._build_aliases(candidate=candidate, canonical_label=canonical_label)
            item_count = len(candidate.source_item_ids)
            source_count = len(candidate.provider_names)
            avg_confidence = candidate.confidence_sum / max(len(candidate.signal_ids), 1)
            saturation_score = self._compute_saturation_score(
                item_count=item_count,
                source_count=source_count,
                avg_confidence=avg_confidence,
                type_cluster_count=total_items_by_type[candidate.signal_type],
            )
            novelty_score = self._compute_novelty_score(
                canonical_label=canonical_label,
                aliases=aliases,
                saturation_score=saturation_score,
            )
            payloads.append(
                SignalClusterCreate(
                    run_id=candidate.run_id,
                    signal_type=candidate.signal_type,
                    canonical_label=canonical_label,
                    aliases_json=aliases,
                    source_count=source_count,
                    item_count=item_count,
                    avg_confidence=round(avg_confidence, 2),
                    saturation_score=round(saturation_score, 1),
                    novelty_score=round(novelty_score, 1),
                )
            )

        return repository.bulk_create(payloads) if payloads else []

    def _assign_signals_to_clusters(
        self,
        *,
        session: Session,
        persisted_clusters: Sequence[SignalCluster],
        candidates: dict[str, ClusterCandidate],
        assignments: Sequence[ClusterAssignment],
    ) -> None:
        repository = ExtractedSignalRepository(session)
        cluster_lookup = {(cluster.signal_type, cluster.canonical_label): cluster.id for cluster in persisted_clusters}
        assignment_signal_ids: dict[str, list] = defaultdict(list)
        for assignment in assignments:
            assignment_signal_ids[assignment.cluster_key].append(assignment.signal_id)

        for cluster_key, signal_ids in assignment_signal_ids.items():
            signal_type, canonical_label = cluster_key.split(":", maxsplit=1)
            cluster_id = cluster_lookup.get((signal_type, canonical_label))
            if cluster_id is None:
                candidate = candidates.get(cluster_key)
                if candidate is None:
                    continue
                chosen_label = self._choose_canonical_label(candidate)
                cluster_id = cluster_lookup[(signal_type, chosen_label)]
            repository.bulk_assign_cluster(extracted_signal_ids=signal_ids, cluster_id=cluster_id)

    def _mark_source_items_clustered(
        self,
        *,
        session: Session,
        extracted_signals: Sequence[ExtractedSignal],
    ) -> None:
        source_item_ids = sorted({signal.source_item_id for signal in extracted_signals}, key=str)
        if not source_item_ids:
            return
        SourceItemRepository(session).bulk_update_status(
            source_item_ids=source_item_ids,
            status=SourceItemStatus.CLUSTERED,
        )

    @staticmethod
    def _choose_canonical_label(candidate: ClusterCandidate) -> str:
        counts = candidate.normalized_value_counts or Counter({candidate.canonical_label: 1})
        return min(
            counts,
            key=lambda label: (
                -counts[label],
                -candidate.normalized_value_confidence.get(label, 0.0),
                len(label.split()),
                len(label),
                label,
            ),
        )

    @staticmethod
    def _build_aliases(*, candidate: ClusterCandidate, canonical_label: str) -> list[str]:
        aliases = dict(candidate.aliases)
        for normalized_variant in candidate.normalized_variants:
            if normalized_variant != canonical_label:
                aliases.setdefault(normalized_variant.lower(), normalized_variant)
        return sorted(aliases.values(), key=lambda value: (len(value.split()), len(value), value.lower()))

    @staticmethod
    def _compute_saturation_score(
        *,
        item_count: int,
        source_count: int,
        avg_confidence: float,
        type_cluster_count: int,
    ) -> float:
        density_component = min(45.0, item_count * 14.0)
        source_component = min(30.0, source_count * 15.0)
        confidence_component = avg_confidence * 20.0
        scarcity_penalty = max(0.0, 10.0 - type_cluster_count * 2.0)
        return max(0.0, min(100.0, density_component + source_component + confidence_component - scarcity_penalty))

    @staticmethod
    def _compute_novelty_score(
        *,
        canonical_label: str,
        aliases: Sequence[str],
        saturation_score: float,
    ) -> float:
        token_count = len(canonical_label.split())
        specificity_bonus = min(22.0, token_count * 5.5)
        alias_bonus = min(12.0, len(aliases) * 3.0)
        rarity_component = max(0.0, 100.0 - saturation_score)
        return max(0.0, min(100.0, rarity_component * 0.65 + specificity_bonus + alias_bonus))
