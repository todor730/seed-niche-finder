"""Types for explainable signal clustering."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ClusterAssignmentReason(StrEnum):
    """Deterministic reasons for assigning a signal to a cluster."""

    EXACT_NORMALIZED_MATCH = "exact_normalized_match"
    TOKEN_REORDER_MATCH = "token_reorder_match"
    HIGH_TOKEN_SIMILARITY = "high_token_similarity"
    SMALL_TYPO_VARIANT = "small_typo_variant"
    FUTURE_SIMILARITY_HOOK = "future_similarity_hook"
    NEW_CLUSTER = "new_cluster"


class SimilarityHook(Protocol):
    """Future extension point for embeddings or semantic similarity."""

    def score(self, *, signal_type: str, left: str, right: str) -> float | None:
        """Return a similarity score in the 0..1 range, or None when unsupported."""


@dataclass(frozen=True, slots=True)
class SimilarityDecision:
    """Similarity result between one signal and one cluster label."""

    matched: bool
    score: float
    reason: ClusterAssignmentReason


@dataclass(slots=True)
class ClusterAssignment:
    """Explainable assignment of one extracted signal to one cluster."""

    signal_id: UUID
    cluster_key: str
    reason: ClusterAssignmentReason
    similarity_score: float


@dataclass(slots=True)
class ClusterCandidate:
    """In-memory cluster candidate before persistence."""

    run_id: UUID
    signal_type: str
    canonical_label: str
    signal_ids: list[UUID] = field(default_factory=list)
    source_item_ids: set[UUID] = field(default_factory=set)
    provider_names: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)
    normalized_variants: set[str] = field(default_factory=set)
    normalized_value_counts: Counter[str] = field(default_factory=Counter)
    normalized_value_confidence: dict[str, float] = field(default_factory=dict)
    confidence_sum: float = 0.0


@dataclass(frozen=True, slots=True)
class PersistedClusterSummary:
    """Compact summary of a persisted signal cluster."""

    cluster_id: UUID
    signal_type: str
    canonical_label: str
    source_count: int
    item_count: int
    avg_confidence: float
    saturation_score: float
    novelty_score: float


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    """Full clustering output for one run."""

    clusters: tuple[PersistedClusterSummary, ...]
    assignments: tuple[ClusterAssignment, ...]
