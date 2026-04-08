"""Evidence-backed niche hypothesis generation over signal clusters."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import logging
from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ExtractedSignal, NicheHypothesis, SignalCluster, SourceItem
from app.db.repositories.niche_hypotheses import NicheHypothesisRepository
from app.schemas.evidence import NicheHypothesisCreate, NicheHypothesisStatus

logger = logging.getLogger(__name__)

_PRIMARY_SIGNAL_TYPES = ("subgenre", "problem_angle")
_SECONDARY_PRIORITY = {
    "trope": 0,
    "solution_angle": 0,
    "audience": 1,
    "promise": 2,
    "tone": 3,
    "setting": 4,
    "relationship_dynamic": 4,
}
_GENERIC_VALUES = {
    "audience": {"everyone", "anyone", "readers", "book lovers"},
    "promise": {"guide", "system", "plan", "method"},
    "tone": {"emotional"},
}


@dataclass(frozen=True, slots=True)
class ClusterContext:
    """Cluster with its supporting evidence context."""

    cluster: SignalCluster
    source_item_ids: frozenset[UUID]
    source_items: tuple[SourceItem, ...]
    provider_names: frozenset[str]
    average_confidence: float


class NicheHypothesisService:
    """Build coherent, evidence-backed niche hypotheses from clusters."""

    def generate_and_persist(
        self,
        *,
        session: Session,
        run_id: UUID,
    ) -> list[NicheHypothesis]:
        """Generate niche hypotheses for one run and persist them."""
        cluster_contexts = self._load_cluster_contexts(session=session, run_id=run_id)
        if not cluster_contexts:
            return []

        payloads = self._assemble_payloads(run_id=run_id, cluster_contexts=cluster_contexts)
        if not payloads:
            logger.info(
                "Niche hypothesis generation skipped.",
                extra={
                    "stage": "niche_hypotheses_skipped",
                    "run_id": str(run_id),
                    "reason": "no_coherent_candidates",
                },
            )
            return []

        hypotheses = NicheHypothesisRepository(session).bulk_create(payloads)
        logger.info(
            "Niche hypotheses generated.",
            extra={
                "stage": "niche_hypotheses_generated",
                "run_id": str(run_id),
                "hypothesis_count": len(hypotheses),
            },
        )
        return hypotheses

    def _load_cluster_contexts(
        self,
        *,
        session: Session,
        run_id: UUID,
    ) -> dict[UUID, ClusterContext]:
        clusters = list(
            session.scalars(
                select(SignalCluster)
                .where(SignalCluster.run_id == run_id)
                .options(selectinload(SignalCluster.extracted_signals).selectinload(ExtractedSignal.source_item))
            )
        )
        contexts: dict[UUID, ClusterContext] = {}
        for cluster in clusters:
            source_items_by_id: dict[UUID, SourceItem] = {}
            confidence_values: list[float] = []
            provider_names: set[str] = set()
            for signal in cluster.extracted_signals:
                confidence_values.append(signal.confidence)
                if signal.source_item is not None:
                    source_items_by_id.setdefault(signal.source_item.id, signal.source_item)
                    provider_names.add(signal.source_item.provider_name)
            contexts[cluster.id] = ClusterContext(
                cluster=cluster,
                source_item_ids=frozenset(source_items_by_id),
                source_items=tuple(source_items_by_id.values()),
                provider_names=frozenset(provider_names),
                average_confidence=round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
            )
        return contexts

    def _assemble_payloads(
        self,
        *,
        run_id: UUID,
        cluster_contexts: dict[UUID, ClusterContext],
    ) -> list[NicheHypothesisCreate]:
        contexts_by_type: dict[str, list[ClusterContext]] = defaultdict(list)
        for context in cluster_contexts.values():
            contexts_by_type[context.cluster.signal_type].append(context)

        payload_by_label: dict[str, NicheHypothesisCreate] = {}
        score_by_label: dict[str, tuple[int, int, float]] = {}

        for primary_type in _PRIMARY_SIGNAL_TYPES:
            for anchor in contexts_by_type.get(primary_type, []):
                assembled = self._assemble_from_anchor(anchor=anchor, contexts_by_type=contexts_by_type)
                if assembled is None:
                    continue
                label = assembled.hypothesis_label
                quality_key = (
                    assembled.evidence_count,
                    assembled.source_count,
                    float(assembled.rationale_json.get("anchor_avg_confidence", 0.0)),
                )
                if label not in payload_by_label or quality_key > score_by_label[label]:
                    payload_by_label[label] = assembled
                    score_by_label[label] = quality_key

        return sorted(
            payload_by_label.values(),
            key=lambda payload: (-payload.evidence_count, -payload.source_count, payload.hypothesis_label),
        )

    def _assemble_from_anchor(
        self,
        *,
        anchor: ClusterContext,
        contexts_by_type: dict[str, list[ClusterContext]],
    ) -> NicheHypothesisCreate | None:
        optional_components: dict[str, tuple[ClusterContext, float]] = {}
        for signal_type in sorted(_SECONDARY_PRIORITY, key=_SECONDARY_PRIORITY.get):
            selected = self._select_related_component(anchor=anchor, candidate_contexts=contexts_by_type.get(signal_type, []))
            if selected is not None:
                optional_components[signal_type] = selected

        if anchor.cluster.signal_type == "subgenre":
            label = self._build_fiction_label(anchor=anchor, optional_components=optional_components)
        else:
            label = self._build_nonfiction_label(anchor=anchor, optional_components=optional_components)

        if label is None or self._reject_hypothesis(anchor=anchor, optional_components=optional_components, label=label):
            return None

        supporting_source_items = self._collect_supporting_source_items(anchor=anchor, optional_components=optional_components)
        provider_names = sorted({item.provider_name for item in supporting_source_items})
        rationale_json = self._build_rationale(
            anchor=anchor,
            optional_components=optional_components,
            label=label,
            supporting_source_items=supporting_source_items,
            provider_names=provider_names,
        )
        summary = self._build_summary(anchor=anchor, optional_components=optional_components, label=label)

        return NicheHypothesisCreate(
            run_id=anchor.cluster.run_id,
            primary_cluster_id=anchor.cluster.id,
            hypothesis_label=label,
            summary=summary,
            rationale_json=rationale_json,
            evidence_count=len(supporting_source_items),
            source_count=len(provider_names),
            status=NicheHypothesisStatus.IDENTIFIED,
        )

    def _select_related_component(
        self,
        *,
        anchor: ClusterContext,
        candidate_contexts: Sequence[ClusterContext],
    ) -> tuple[ClusterContext, float] | None:
        best_context: ClusterContext | None = None
        best_score = 0.0
        best_ratio = 0.0

        for candidate in candidate_contexts:
            if candidate.cluster.id == anchor.cluster.id:
                continue
            if self._is_generic(candidate.cluster.signal_type, candidate.cluster.canonical_label):
                continue

            shared_items = anchor.source_item_ids & candidate.source_item_ids
            if not shared_items:
                continue
            ratio = len(shared_items) / max(len(anchor.source_item_ids), 1)
            min_ratio = 1.0 if len(anchor.source_item_ids) == 1 else 0.5
            if ratio < min_ratio:
                continue
            if self._is_redundant_component(anchor_label=anchor.cluster.canonical_label, component_label=candidate.cluster.canonical_label):
                continue

            score = ratio * 0.60 + candidate.average_confidence * 0.25 + min(1.0, candidate.cluster.source_count / 2.0) * 0.15
            if score > best_score:
                best_context = candidate
                best_score = score
                best_ratio = ratio

        if best_context is None:
            return None
        return best_context, round(best_ratio, 2)

    def _build_fiction_label(
        self,
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
    ) -> str | None:
        base_label = anchor.cluster.canonical_label
        trope = optional_components.get("trope")
        setting = optional_components.get("setting")

        label = base_label
        if trope is not None:
            label = f"{trope[0].cluster.canonical_label} {label}"
        elif setting is not None and not self._is_redundant_component(anchor_label=label, component_label=setting[0].cluster.canonical_label):
            label = f"{label} in {setting[0].cluster.canonical_label}"

        return " ".join(label.split())

    def _build_nonfiction_label(
        self,
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
    ) -> str | None:
        label = anchor.cluster.canonical_label
        solution = optional_components.get("solution_angle")
        audience = optional_components.get("audience")

        if solution is not None:
            label = f"{label} {solution[0].cluster.canonical_label}"
        if audience is not None:
            label = f"{label} for {audience[0].cluster.canonical_label}"

        return " ".join(label.split())

    def _reject_hypothesis(
        self,
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
        label: str,
    ) -> bool:
        if len(label.split()) < 2:
            return True
        if self._is_generic(anchor.cluster.signal_type, anchor.cluster.canonical_label):
            return True

        meaningful_secondary_types = [
            signal_type
            for signal_type in optional_components
            if signal_type in {"trope", "audience", "promise", "tone", "setting", "relationship_dynamic", "solution_angle"}
        ]
        if not meaningful_secondary_types:
            return True

        if anchor.cluster.signal_type == "subgenre" and "trope" not in optional_components and "audience" not in optional_components:
            strong_contextual = "tone" in optional_components or "setting" in optional_components
            if not strong_contextual:
                return True
        if anchor.cluster.signal_type == "problem_angle" and "solution_angle" not in optional_components:
            return True
        return False

    def _build_rationale(
        self,
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
        label: str,
        supporting_source_items: Sequence[SourceItem],
        provider_names: Sequence[str],
    ) -> dict[str, object]:
        component_payloads = [
            {
                "signal_type": anchor.cluster.signal_type,
                "cluster_id": str(anchor.cluster.id),
                "label": anchor.cluster.canonical_label,
                "source_count": anchor.cluster.source_count,
                "item_count": anchor.cluster.item_count,
                "avg_confidence": round(anchor.average_confidence, 2),
                "saturation_score": round(anchor.cluster.saturation_score, 1),
                "novelty_score": round(anchor.cluster.novelty_score, 1),
                "role": "primary",
            }
        ]
        for signal_type, (component, cooccurrence_ratio) in sorted(optional_components.items(), key=lambda item: _SECONDARY_PRIORITY[item[0]]):
            shared_items = sorted(str(item_id) for item_id in (anchor.source_item_ids & component.source_item_ids))
            component_payloads.append(
                {
                    "signal_type": signal_type,
                    "cluster_id": str(component.cluster.id),
                    "label": component.cluster.canonical_label,
                    "source_count": component.cluster.source_count,
                    "item_count": component.cluster.item_count,
                    "avg_confidence": round(component.average_confidence, 2),
                    "saturation_score": round(component.cluster.saturation_score, 1),
                    "novelty_score": round(component.cluster.novelty_score, 1),
                    "cooccurrence_ratio": cooccurrence_ratio,
                    "shared_source_item_ids": shared_items,
                    "role": "secondary",
                }
            )

        example_source_items = supporting_source_items[:3]
        return {
            "assembly_version": "hypothesis_v1",
            "hypothesis_kind": "fiction" if anchor.cluster.signal_type == "subgenre" else "nonfiction",
            "label": label,
            "anchor_avg_confidence": round(anchor.average_confidence, 2),
            "components": component_payloads,
            "supporting_source_item_ids": [str(item.id) for item in supporting_source_items],
            "supporting_source_titles": [item.title for item in example_source_items],
            "supporting_providers": list(provider_names),
            "example_assemblies": [
                {
                    "source_item_id": str(item.id),
                    "title": item.title,
                    "provider_name": item.provider_name,
                }
                for item in example_source_items
            ],
        }

    def _build_summary(
        self,
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
        label: str,
    ) -> str:
        summary_parts = [f"Primary anchor: {anchor.cluster.canonical_label}."]
        if "trope" in optional_components:
            summary_parts.append(f"Trope support: {optional_components['trope'][0].cluster.canonical_label}.")
        if "solution_angle" in optional_components:
            summary_parts.append(f"Solution angle: {optional_components['solution_angle'][0].cluster.canonical_label}.")
        if "audience" in optional_components:
            summary_parts.append(f"Audience signal: {optional_components['audience'][0].cluster.canonical_label}.")
        if "promise" in optional_components:
            summary_parts.append(f"Promise signal: {optional_components['promise'][0].cluster.canonical_label}.")
        return f"{label}. {' '.join(summary_parts)}".strip()

    @staticmethod
    def _collect_supporting_source_items(
        *,
        anchor: ClusterContext,
        optional_components: dict[str, tuple[ClusterContext, float]],
    ) -> list[SourceItem]:
        supporting_items: dict[UUID, SourceItem] = {item.id: item for item in anchor.source_items}
        for component, _ratio in optional_components.values():
            shared_items = anchor.source_item_ids & component.source_item_ids
            for item in component.source_items:
                if item.id in shared_items:
                    supporting_items[item.id] = item
        return sorted(supporting_items.values(), key=lambda item: (item.provider_name, item.title.lower()))

    @staticmethod
    def _is_redundant_component(*, anchor_label: str, component_label: str) -> bool:
        anchor_tokens = set(anchor_label.split())
        component_tokens = set(component_label.split())
        if not anchor_tokens or not component_tokens:
            return False
        overlap_ratio = len(anchor_tokens & component_tokens) / len(component_tokens)
        return overlap_ratio >= 0.75

    @staticmethod
    def _is_generic(signal_type: str, label: str) -> bool:
        return label in _GENERIC_VALUES.get(signal_type, set())
