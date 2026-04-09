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
    "audience": {"everyone", "anyone", "readers", "book lovers", "women"},
    "promise": {"guide", "system", "plan", "method"},
    "tone": {"emotional"},
}
_GENERIC_NONFICTION_SOLUTIONS = {"guide", "method", "plan", "system"}
_SPECIFIC_FICTION_AUDIENCES = {"young adults", "new adults", "teens", "women over 40"}
_MAX_COMPONENT_CANDIDATES = {
    "trope": 2,
    "solution_angle": 1,
    "audience": 1,
    "promise": 1,
    "tone": 2,
    "setting": 2,
    "relationship_dynamic": 1,
}
_MAX_FICTION_BRANCHES_PER_ANCHOR = 4


@dataclass(frozen=True, slots=True)
class ClusterContext:
    """Cluster with its supporting evidence context."""

    cluster: SignalCluster
    source_item_ids: frozenset[UUID]
    source_items: tuple[SourceItem, ...]
    provider_names: frozenset[str]
    average_confidence: float


@dataclass(frozen=True, slots=True)
class ComponentCandidate:
    """A ranked component candidate linked to one anchor."""

    context: ClusterContext
    cooccurrence_ratio: float
    selection_score: float
    shared_source_item_ids: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class HypothesisBranch:
    """A candidate branch assembled from one anchor plus secondary signals."""

    label: str
    selected_components: dict[str, ComponentCandidate]
    component_signature: tuple[tuple[str, str], ...]
    branch_score: float


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
        score_by_label: dict[str, tuple[int, int, float, float]] = {}

        for primary_type in _PRIMARY_SIGNAL_TYPES:
            for anchor in contexts_by_type.get(primary_type, []):
                candidate_components = self._select_related_components(anchor=anchor, contexts_by_type=contexts_by_type)
                assembled_payloads = self._assemble_from_anchor(
                    anchor=anchor,
                    candidate_components=candidate_components,
                )
                for assembled in assembled_payloads:
                    label = assembled.hypothesis_label
                    quality_key = (
                        assembled.evidence_count,
                        assembled.source_count,
                        float(assembled.rationale_json.get("anchor_avg_confidence", 0.0)),
                        float(assembled.rationale_json.get("branch_score", 0.0)),
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
        candidate_components: dict[str, list[ComponentCandidate]],
    ) -> list[NicheHypothesisCreate]:
        if anchor.cluster.signal_type == "subgenre":
            branches = self._build_fiction_branches(anchor=anchor, candidate_components=candidate_components)
        else:
            branches = self._build_nonfiction_branches(anchor=anchor, candidate_components=candidate_components)

        if not branches:
            self._log_hypothesis_rejection(
                anchor=anchor,
                candidate_components=candidate_components,
                selected_components={},
                proposed_label=anchor.cluster.canonical_label,
                reason_code="no_viable_branches",
            )
            return []

        payloads: list[NicheHypothesisCreate] = []
        for branch in branches:
            reason_code = self._reject_hypothesis(anchor=anchor, selected_components=branch.selected_components, label=branch.label)
            if reason_code is not None:
                self._log_hypothesis_rejection(
                    anchor=anchor,
                    candidate_components=candidate_components,
                    selected_components=branch.selected_components,
                    proposed_label=branch.label,
                    reason_code=reason_code,
                )
                continue

            supporting_source_items = self._collect_supporting_source_items(
                anchor=anchor,
                selected_components=branch.selected_components,
            )
            provider_names = sorted({item.provider_name for item in supporting_source_items})
            rationale_json = self._build_rationale(
                anchor=anchor,
                selected_components=branch.selected_components,
                label=branch.label,
                supporting_source_items=supporting_source_items,
                provider_names=provider_names,
                component_signature=branch.component_signature,
                branch_score=branch.branch_score,
            )
            summary = self._build_summary(anchor=anchor, selected_components=branch.selected_components, label=branch.label)

            payloads.append(
                NicheHypothesisCreate(
                    run_id=anchor.cluster.run_id,
                    primary_cluster_id=anchor.cluster.id,
                    hypothesis_label=branch.label,
                    summary=summary,
                    rationale_json=rationale_json,
                    evidence_count=len(supporting_source_items),
                    source_count=len(provider_names),
                    status=NicheHypothesisStatus.IDENTIFIED,
                )
            )

        return payloads

    def _select_related_components(
        self,
        *,
        anchor: ClusterContext,
        contexts_by_type: dict[str, list[ClusterContext]],
    ) -> dict[str, list[ComponentCandidate]]:
        ranked_by_type: dict[str, list[ComponentCandidate]] = {}
        for signal_type in sorted(_SECONDARY_PRIORITY, key=_SECONDARY_PRIORITY.get):
            candidates = self._rank_related_components(
                anchor=anchor,
                signal_type=signal_type,
                candidate_contexts=contexts_by_type.get(signal_type, []),
            )
            if candidates:
                ranked_by_type[signal_type] = candidates[: _MAX_COMPONENT_CANDIDATES.get(signal_type, 1)]
        return ranked_by_type

    def _rank_related_components(
        self,
        *,
        anchor: ClusterContext,
        signal_type: str,
        candidate_contexts: Sequence[ClusterContext],
    ) -> list[ComponentCandidate]:
        ranked: list[ComponentCandidate] = []
        min_ratio = self._minimum_ratio_for_component(anchor=anchor, signal_type=signal_type)

        for candidate in candidate_contexts:
            if candidate.cluster.id == anchor.cluster.id:
                continue
            if self._is_generic(candidate.cluster.signal_type, candidate.cluster.canonical_label):
                continue
            if self._is_redundant_component(anchor_label=anchor.cluster.canonical_label, component_label=candidate.cluster.canonical_label):
                continue

            shared_items = anchor.source_item_ids & candidate.source_item_ids
            if not shared_items:
                continue

            ratio = len(shared_items) / max(len(anchor.source_item_ids), 1)
            if ratio < min_ratio:
                continue

            score = (
                ratio * 0.55
                + candidate.average_confidence * 0.20
                + min(1.0, candidate.cluster.item_count / 4.0) * 0.15
                + min(1.0, candidate.cluster.source_count / 2.0) * 0.10
            )
            ranked.append(
                ComponentCandidate(
                    context=candidate,
                    cooccurrence_ratio=round(ratio, 2),
                    selection_score=round(score, 3),
                    shared_source_item_ids=frozenset(shared_items),
                )
            )

        return sorted(
            ranked,
            key=lambda candidate: (
                -candidate.selection_score,
                -candidate.cooccurrence_ratio,
                -candidate.context.cluster.item_count,
                candidate.context.cluster.canonical_label,
            ),
        )

    def _build_fiction_branches(
        self,
        *,
        anchor: ClusterContext,
        candidate_components: dict[str, list[ComponentCandidate]],
    ) -> list[HypothesisBranch]:
        branch_by_signature: dict[tuple[tuple[str, str], ...], HypothesisBranch] = {}

        def add_branch(selected_components: dict[str, ComponentCandidate]) -> None:
            label = self._build_fiction_label(anchor=anchor, selected_components=selected_components)
            if label is None:
                return
            component_signature = self._component_signature(selected_components)
            branch_score = self._branch_score(anchor=anchor, selected_components=selected_components)
            branch = HypothesisBranch(
                label=label,
                selected_components=dict(selected_components),
                component_signature=component_signature,
                branch_score=branch_score,
            )
            current = branch_by_signature.get(component_signature)
            if current is None or branch.branch_score > current.branch_score:
                branch_by_signature[component_signature] = branch

        trope_candidates = candidate_components.get("trope", [])
        tone_candidates = candidate_components.get("tone", [])
        setting_candidates = candidate_components.get("setting", [])
        audience_candidates = candidate_components.get("audience", [])
        promise_candidates = candidate_components.get("promise", [])
        relationship_candidates = candidate_components.get("relationship_dynamic", [])

        preferred_audience = audience_candidates[:1]
        preferred_promise = promise_candidates[:1]
        preferred_relationship = relationship_candidates[:1]

        for trope in trope_candidates:
            selected = {"trope": trope}
            if preferred_audience:
                selected["audience"] = preferred_audience[0]
            if preferred_promise:
                selected["promise"] = preferred_promise[0]
            if preferred_relationship:
                selected["relationship_dynamic"] = preferred_relationship[0]
            add_branch(selected)

            for tone in tone_candidates[:1]:
                add_branch({**selected, "tone": tone})

        for tone in tone_candidates:
            selected = {"tone": tone}
            if preferred_audience:
                selected["audience"] = preferred_audience[0]
            if preferred_promise:
                selected["promise"] = preferred_promise[0]
            add_branch(selected)

        for setting in setting_candidates:
            selected = {"setting": setting}
            if preferred_audience:
                selected["audience"] = preferred_audience[0]
            add_branch(selected)

            if trope_candidates:
                add_branch({"trope": trope_candidates[0], "setting": setting, **selected})

        if preferred_audience and self._is_specific_fiction_audience(preferred_audience[0].context.cluster.canonical_label):
            add_branch({"audience": preferred_audience[0]})

        return sorted(
            branch_by_signature.values(),
            key=lambda branch: (-branch.branch_score, branch.label),
        )[:_MAX_FICTION_BRANCHES_PER_ANCHOR]

    def _build_nonfiction_branches(
        self,
        *,
        anchor: ClusterContext,
        candidate_components: dict[str, list[ComponentCandidate]],
    ) -> list[HypothesisBranch]:
        selected_components: dict[str, ComponentCandidate] = {}
        for signal_type in ("solution_angle", "audience", "promise"):
            if candidate_components.get(signal_type):
                selected_components[signal_type] = candidate_components[signal_type][0]

        label = self._build_nonfiction_label(anchor=anchor, selected_components=selected_components)
        if label is None:
            return []

        return [
            HypothesisBranch(
                label=label,
                selected_components=selected_components,
                component_signature=self._component_signature(selected_components),
                branch_score=self._branch_score(anchor=anchor, selected_components=selected_components),
            )
        ]

    def _build_fiction_label(
        self,
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
    ) -> str | None:
        base_label = anchor.cluster.canonical_label
        trope = selected_components.get("trope")
        setting = selected_components.get("setting")
        tone = selected_components.get("tone")
        audience = selected_components.get("audience")

        label = base_label
        if trope is not None:
            label = f"{trope.context.cluster.canonical_label} {label}"
        elif setting is not None and not self._is_redundant_component(
            anchor_label=label,
            component_label=setting.context.cluster.canonical_label,
        ):
            label = f"{setting.context.cluster.canonical_label} {label}"
        elif tone is not None and not self._is_redundant_component(
            anchor_label=label,
            component_label=tone.context.cluster.canonical_label,
        ):
            label = f"{tone.context.cluster.canonical_label} {label}"
        elif audience is not None and self._is_specific_fiction_audience(audience.context.cluster.canonical_label):
            label = f"{audience.context.cluster.canonical_label} {label}"

        return " ".join(label.split())

    def _build_nonfiction_label(
        self,
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
    ) -> str | None:
        label = anchor.cluster.canonical_label
        solution = selected_components.get("solution_angle")
        audience = selected_components.get("audience")

        if solution is not None:
            label = f"{label} {solution.context.cluster.canonical_label}"
        if audience is not None:
            label = f"{label} for {audience.context.cluster.canonical_label}"

        return " ".join(label.split())

    def _reject_hypothesis(
        self,
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
        label: str,
    ) -> str | None:
        if len(label.split()) < 2:
            return "label_too_short"
        if self._is_generic(anchor.cluster.signal_type, anchor.cluster.canonical_label):
            return "generic_anchor"

        if anchor.cluster.signal_type == "subgenre":
            if not selected_components:
                return "fiction_branch_missing_secondary"

            trope = selected_components.get("trope")
            tone = selected_components.get("tone")
            setting = selected_components.get("setting")
            audience = selected_components.get("audience")
            relationship = selected_components.get("relationship_dynamic")

            has_specific_audience = audience is not None and self._is_specific_fiction_audience(audience.context.cluster.canonical_label)
            if trope is None and tone is None and setting is None and relationship is None and not has_specific_audience:
                return "fiction_branch_not_specific_enough"

            if trope is None and tone is not None and tone.cooccurrence_ratio < 0.5 and setting is None and not has_specific_audience:
                return "tone_branch_support_too_weak"

            if trope is None and setting is not None and setting.cooccurrence_ratio < 0.5 and tone is None and not has_specific_audience:
                return "setting_branch_support_too_weak"

            return None

        solution = selected_components.get("solution_angle")
        audience = selected_components.get("audience")
        promise = selected_components.get("promise")
        if solution is None:
            return "nonfiction_missing_solution"
        solution_label = solution.context.cluster.canonical_label
        if solution_label in _GENERIC_NONFICTION_SOLUTIONS and audience is None and promise is None:
            return "generic_solution_without_support"
        if solution_label in _GENERIC_NONFICTION_SOLUTIONS and audience is not None:
            audience_label = audience.context.cluster.canonical_label
            if self._is_generic("audience", audience_label) or len(audience_label.split()) < 2:
                return "generic_audience_for_generic_solution"
        return None

    def _build_rationale(
        self,
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
        label: str,
        supporting_source_items: Sequence[SourceItem],
        provider_names: Sequence[str],
        component_signature: tuple[tuple[str, str], ...],
        branch_score: float,
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
        for signal_type, candidate in sorted(selected_components.items(), key=lambda item: _SECONDARY_PRIORITY[item[0]]):
            component_payloads.append(
                {
                    "signal_type": signal_type,
                    "cluster_id": str(candidate.context.cluster.id),
                    "label": candidate.context.cluster.canonical_label,
                    "source_count": candidate.context.cluster.source_count,
                    "item_count": candidate.context.cluster.item_count,
                    "avg_confidence": round(candidate.context.average_confidence, 2),
                    "saturation_score": round(candidate.context.cluster.saturation_score, 1),
                    "novelty_score": round(candidate.context.cluster.novelty_score, 1),
                    "cooccurrence_ratio": candidate.cooccurrence_ratio,
                    "selection_score": candidate.selection_score,
                    "shared_source_item_ids": sorted(str(item_id) for item_id in candidate.shared_source_item_ids),
                    "role": "secondary",
                }
            )

        example_source_items = supporting_source_items[:3]
        return {
            "assembly_version": "hypothesis_v2",
            "hypothesis_kind": "fiction" if anchor.cluster.signal_type == "subgenre" else "nonfiction",
            "label": label,
            "anchor_avg_confidence": round(anchor.average_confidence, 2),
            "branch_score": round(branch_score, 3),
            "component_signature": [[signal_type, label_value] for signal_type, label_value in component_signature],
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
        selected_components: dict[str, ComponentCandidate],
        label: str,
    ) -> str:
        summary_parts = [f"Primary anchor: {anchor.cluster.canonical_label}."]
        if "trope" in selected_components:
            summary_parts.append(f"Trope support: {selected_components['trope'].context.cluster.canonical_label}.")
        if "tone" in selected_components:
            summary_parts.append(f"Tone support: {selected_components['tone'].context.cluster.canonical_label}.")
        if "setting" in selected_components:
            summary_parts.append(f"Setting support: {selected_components['setting'].context.cluster.canonical_label}.")
        if "solution_angle" in selected_components:
            summary_parts.append(f"Solution angle: {selected_components['solution_angle'].context.cluster.canonical_label}.")
        if "audience" in selected_components:
            summary_parts.append(f"Audience signal: {selected_components['audience'].context.cluster.canonical_label}.")
        if "promise" in selected_components:
            summary_parts.append(f"Promise signal: {selected_components['promise'].context.cluster.canonical_label}.")
        return f"{label}. {' '.join(summary_parts)}".strip()

    @staticmethod
    def _collect_supporting_source_items(
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
    ) -> list[SourceItem]:
        supporting_items: dict[UUID, SourceItem] = {item.id: item for item in anchor.source_items}
        for candidate in selected_components.values():
            for item in candidate.context.source_items:
                if item.id in candidate.shared_source_item_ids:
                    supporting_items[item.id] = item
        return sorted(supporting_items.values(), key=lambda item: (item.provider_name, item.title.lower()))

    def _log_hypothesis_rejection(
        self,
        *,
        anchor: ClusterContext,
        candidate_components: dict[str, list[ComponentCandidate]],
        selected_components: dict[str, ComponentCandidate],
        proposed_label: str,
        reason_code: str,
    ) -> None:
        logger.info(
            "Niche hypothesis branch rejected.",
            extra={
                "stage": "niche_hypothesis_rejected",
                "run_id": str(anchor.cluster.run_id),
                "anchor_signal_type": anchor.cluster.signal_type,
                "anchor_label": anchor.cluster.canonical_label,
                "proposed_label": proposed_label,
                "reason_code": reason_code,
                "candidate_components_by_type": {
                    signal_type: [
                        {
                            "label": candidate.context.cluster.canonical_label,
                            "cooccurrence_ratio": candidate.cooccurrence_ratio,
                            "selection_score": candidate.selection_score,
                            "item_count": candidate.context.cluster.item_count,
                        }
                        for candidate in candidates
                    ]
                    for signal_type, candidates in candidate_components.items()
                },
                "selected_components": {
                    signal_type: {
                        "label": candidate.context.cluster.canonical_label,
                        "cooccurrence_ratio": candidate.cooccurrence_ratio,
                        "selection_score": candidate.selection_score,
                    }
                    for signal_type, candidate in selected_components.items()
                },
            },
        )

    def _minimum_ratio_for_component(self, *, anchor: ClusterContext, signal_type: str) -> float:
        if len(anchor.source_item_ids) <= 1:
            return 1.0
        if signal_type in {"trope", "tone", "setting", "relationship_dynamic"}:
            return 0.4
        if signal_type == "audience":
            return 0.5
        return 0.5

    def _component_signature(
        self,
        selected_components: dict[str, ComponentCandidate],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (signal_type, candidate.context.cluster.canonical_label)
                for signal_type, candidate in selected_components.items()
            )
        )

    def _branch_score(
        self,
        *,
        anchor: ClusterContext,
        selected_components: dict[str, ComponentCandidate],
    ) -> float:
        secondary_score = sum(candidate.selection_score for candidate in selected_components.values())
        return round(anchor.average_confidence + secondary_score, 3)

    @staticmethod
    def _is_specific_fiction_audience(label: str) -> bool:
        return label in _SPECIFIC_FICTION_AUDIENCES

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
