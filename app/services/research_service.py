"""Synchronous research service for local niche analysis."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import CurrentUser
from app.core.errors import RunNotFoundError
from app.db.models import (
    Competitor,
    CompetitorStatus,
    ExtractedSignal,
    KeywordCandidate,
    KeywordCandidateStatus,
    KeywordMetrics,
    KeywordMetricsStatus,
    NicheHypothesis,
    Opportunity,
    OpportunityStatus,
    ResearchRun,
    ResearchRunStatus,
    SourceItem,
    TrendMetrics,
    TrendMetricsStatus,
)
from app.db.repositories.source_items import SourceItemRepository
from app.schemas.evidence import SourceItemCreate, SourceItemStatus
from app.schemas.research import CancelRunData, CreateResearchRunRequest, ResearchProgress
from app.services.providers import (
    BookSignal,
    ProviderRegistry,
    ProviderSearchBatchResult,
    build_enabled_providers,
)
from app.services.clustering import ClusteringService
from app.services.extraction import RuleBasedExtractionService
from app.services.hypotheses import NicheHypothesisService
from app.services.ranking import KeywordBlueprint, build_keyword_blueprints
from app.services.scoring import HypothesisRankingService
from app.services.shared import (
    ListResult,
    ensure_user,
    resolve_user_id,
    to_research_run,
    to_research_run_details,
    to_research_run_list_item,
)

logger = logging.getLogger(__name__)


class ResearchService:
    """Application service that creates and reads persisted research runs."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        export_storage_path: str,
        provider_registry: ProviderRegistry | None = None,
        extraction_service: RuleBasedExtractionService | None = None,
        clustering_service: ClusteringService | None = None,
        hypothesis_service: NicheHypothesisService | None = None,
        ranking_service: HypothesisRankingService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._export_storage_path = export_storage_path
        self._provider_registry = provider_registry or ProviderRegistry(build_enabled_providers(("google_books", "open_library")))
        self._extraction_service = extraction_service or RuleBasedExtractionService()
        self._clustering_service = clustering_service or ClusteringService()
        self._hypothesis_service = hypothesis_service or NicheHypothesisService()
        self._ranking_service = ranking_service or HypothesisRankingService()

    def create_run(self, *, current_user: CurrentUser, payload: CreateResearchRunRequest):
        """Persist a research run and execute the synchronous local research pipeline."""
        research_run = self._create_running_run(current_user=current_user, payload=payload)
        logger.info(
            "Research run started.",
            extra={
                "run_id": str(research_run.id),
                "seed_niche": payload.seed_niche,
                "stage": "run_started",
            },
        )

        try:
            batch = self._collect_raw_evidence(payload.seed_niche)
            logger.info(
                "Provider fan-out completed.",
                extra={
                    "run_id": str(research_run.id),
                    "seed_niche": payload.seed_niche,
                    "stage": "provider_fan_out_completed",
                    "query_count": len(batch.queries),
                    "provider_count": len(batch.provider_names),
                    "raw_item_count": batch.total_item_count,
                    "failure_count": len(batch.failures),
                },
            )
            if batch.failures:
                logger.warning(
                    "Provider fan-out completed with partial failures.",
                    extra={
                        "run_id": str(research_run.id),
                        "seed_niche": payload.seed_niche,
                        "stage": "provider_partial_failure",
                        "failure_count": len(batch.failures),
                        "providers_with_failures": sorted({failure.provider_name for failure in batch.failures}),
                    },
                )

            completed_run = self._process_run_with_evidence(
                run_id=research_run.id,
                payload=payload,
                batch=batch,
            )
            logger.info(
                "Research run completed.",
                extra={
                    "run_id": str(completed_run.id),
                    "seed_niche": payload.seed_niche,
                    "stage": "run_completed",
                    "status": completed_run.status.value,
                },
            )
            return to_research_run(completed_run)
        except Exception as exc:
            self._mark_run_failed(run_id=research_run.id, message=str(exc))
            logger.exception(
                "Research run failed.",
                extra={
                    "run_id": str(research_run.id),
                    "seed_niche": payload.seed_niche,
                    "stage": "run_failed",
                },
            )
            raise

    def list_runs(self, *, current_user: CurrentUser, status, limit: int, offset: int) -> ListResult:
        """List persisted runs for the current user."""
        with self._session_factory() as session:
            user_id = resolve_user_id(current_user)
            statement = (
                select(ResearchRun)
                .where(ResearchRun.user_id == user_id)
                .order_by(ResearchRun.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if status is not None:
                statement = statement.where(ResearchRun.status == ResearchRunStatus(status.value if hasattr(status, "value") else status))

            count_statement = select(ResearchRun).where(ResearchRun.user_id == user_id)
            if status is not None:
                count_statement = count_statement.where(
                    ResearchRun.status == ResearchRunStatus(status.value if hasattr(status, "value") else status)
                )

            runs = list(session.scalars(statement))
            total = len(list(session.scalars(count_statement)))
            items = [to_research_run_list_item(session, run) for run in runs]
            return ListResult(items=items, total=total, limit=limit, offset=offset)

    def get_run(self, *, current_user: CurrentUser, run_id: UUID):
        """Return a persisted research run detail payload."""
        with self._session_factory() as session:
            run = self._load_owned_run(session, current_user, run_id)
            return to_research_run_details(session, run)

    def get_progress(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchProgress:
        """Return the derived progress payload for a research run."""
        with self._session_factory() as session:
            run = self._load_owned_run(session, current_user, run_id)
            return to_research_run_details(session, run).progress

    def cancel_run(self, *, current_user: CurrentUser, run_id: UUID) -> CancelRunData:
        """Mark a run as cancelled when it still exists."""
        with self._session_factory() as session:
            run = self._load_owned_run(session, current_user, run_id)
            run.status = ResearchRunStatus.CANCELLED
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            session.commit()
            return CancelRunData(run_id=run.id, status="cancelled")

    def _load_owned_run(self, session: Session, current_user: CurrentUser, run_id: UUID) -> ResearchRun:
        run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == resolve_user_id(current_user)))
        if run is None:
            raise RunNotFoundError(str(run_id))
        return run

    def _create_running_run(self, *, current_user: CurrentUser, payload: CreateResearchRunRequest) -> ResearchRun:
        """Create and commit the initial running research run record."""
        with self._session_factory() as session:
            user = ensure_user(session, current_user)
            now = datetime.now(UTC)
            research_run = ResearchRun(
                user_id=user.id,
                seed_niche=payload.seed_niche,
                config_json=payload.config.model_dump(),
                title=payload.seed_niche.title(),
                status=ResearchRunStatus.RUNNING,
                started_at=now,
            )
            session.add(research_run)
            session.commit()
            session.refresh(research_run)
            return research_run

    def _collect_raw_evidence(self, seed_niche: str) -> ProviderSearchBatchResult:
        """Collect standardized raw evidence through the provider registry."""
        return self._provider_registry.search(seed_niche)

    def _process_run_with_evidence(
        self,
        *,
        run_id: UUID,
        payload: CreateResearchRunRequest,
        batch: ProviderSearchBatchResult,
    ) -> ResearchRun:
        """Persist raw evidence, materialize the current ranking flow, and complete the run."""
        with self._session_factory() as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                raise RunNotFoundError(str(run_id))

            persisted_source_items = self._persist_raw_evidence(session=session, run=run, batch=batch)
            logger.info(
                "Raw evidence persisted.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "raw_evidence_persisted",
                    "source_item_count": len(persisted_source_items),
                    "provider_breakdown": dict(Counter(item.provider_name for item in persisted_source_items)),
                },
            )
            extracted_signals = self._extract_signals(session=session, run=run, source_items=persisted_source_items)
            logger.info(
                "Extracted signals persisted.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "extracted_signals_persisted",
                    "signal_count": len(extracted_signals),
                    "signal_type_breakdown": dict(Counter(signal.signal_type for signal in extracted_signals)),
                },
            )
            clustering_result = self._cluster_signals(session=session, run=run, extracted_signals=extracted_signals)
            logger.info(
                "Signal clusters persisted.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "signal_clusters_persisted",
                    "cluster_count": len(clustering_result.clusters),
                    "assignment_count": len(clustering_result.assignments),
                    "assignment_reason_breakdown": dict(Counter(assignment.reason.value for assignment in clustering_result.assignments)),
                },
            )
            hypotheses = self._generate_niche_hypotheses(session=session, run=run)
            logger.info(
                "Niche hypotheses persisted.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "niche_hypotheses_persisted",
                    "hypothesis_count": len(hypotheses),
                },
            )
            ranked_hypotheses = self._rank_niche_hypotheses(session=session, run=run)
            logger.info(
                "Niche hypothesis scores persisted.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "niche_scores_persisted",
                    "ranked_hypothesis_count": len(ranked_hypotheses),
                },
            )

            book_signals = self._source_items_to_book_signals(persisted_source_items)
            keyword_blueprints = self._build_keyword_blueprints(
                seed_niche=payload.seed_niche,
                max_candidates=payload.config.max_candidates,
                book_signals=book_signals,
            )
            logger.info(
                "Keyword blueprints built from persisted evidence.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "keyword_blueprints_built",
                    "blueprint_count": len(keyword_blueprints),
                    "source_item_count": len(persisted_source_items),
                },
            )

            self._materialize_pipeline(
                session=session,
                run=run,
                blueprints=keyword_blueprints[: payload.config.top_k],
                book_signals=book_signals,
            )
            run.status = ResearchRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(run)
            return run

    def _persist_raw_evidence(
        self,
        *,
        session: Session,
        run: ResearchRun,
        batch: ProviderSearchBatchResult,
    ) -> list[SourceItem]:
        """Persist standardized raw evidence items for a research run."""
        repository = SourceItemRepository(session)
        persisted_items: list[SourceItem] = []

        for provider_name in sorted({item.provider_name for item in batch.all_items}):
            provider_items = [item for item in batch.all_items if item.provider_name == provider_name]
            existing_dedupe_keys = repository.list_existing_dedupe_keys(
                run_id=run.id,
                provider_name=provider_name,
                dedupe_keys=[item.dedupe_key for item in provider_items],
            )
            payloads: list[SourceItemCreate] = []
            for raw_item in provider_items:
                if raw_item.dedupe_key in existing_dedupe_keys:
                    continue
                payloads.append(
                    SourceItemCreate(
                        run_id=run.id,
                        provider_name=raw_item.provider_name,
                        query_text=raw_item.query_text,
                        query_kind=raw_item.query_kind,
                        provider_item_id=raw_item.provider_item_id,
                        dedupe_key=raw_item.dedupe_key,
                        source_url=raw_item.source_url,
                        title=raw_item.title,
                        subtitle=raw_item.subtitle,
                        authors_json=list(raw_item.authors),
                        categories_json=list(raw_item.categories),
                        description_text=raw_item.description_text,
                        content_text=raw_item.content_text,
                        published_date_raw=raw_item.published_date_raw,
                        average_rating=raw_item.average_rating,
                        rating_count=raw_item.rating_count,
                        review_count=raw_item.review_count,
                        raw_payload_json=dict(raw_item.raw_payload),
                        status=SourceItemStatus.FETCHED,
                    )
                )
            if payloads:
                persisted_items.extend(repository.bulk_create(payloads))

        return persisted_items

    def _extract_signals(
        self,
        *,
        session: Session,
        run: ResearchRun,
        source_items: list[SourceItem],
    ) -> list[ExtractedSignal]:
        """Extract and persist rule-based signals from persisted raw evidence."""
        if not source_items:
            logger.info(
                "No source items available for extraction.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "extracted_signals_skipped",
                    "reason": "no_source_items",
                },
            )
            return []
        return self._extraction_service.extract_and_persist(session=session, source_items=source_items)

    def _cluster_signals(
        self,
        *,
        session: Session,
        run: ResearchRun,
        extracted_signals: list[ExtractedSignal],
    ):
        """Cluster extracted signals into explainable canonical groups."""
        if not extracted_signals:
            logger.info(
                "No extracted signals available for clustering.",
                extra={
                    "run_id": str(run.id),
                    "seed_niche": run.seed_niche,
                    "stage": "signal_clusters_skipped",
                    "reason": "no_extracted_signals",
                },
            )
            return self._clustering_service.cluster_and_persist(session=session, extracted_signals=())
        return self._clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)

    def _generate_niche_hypotheses(
        self,
        *,
        session: Session,
        run: ResearchRun,
    ) -> list[NicheHypothesis]:
        """Generate evidence-backed niche hypotheses from persisted signal clusters."""
        return self._hypothesis_service.generate_and_persist(session=session, run_id=run.id)

    def _rank_niche_hypotheses(
        self,
        *,
        session: Session,
        run: ResearchRun,
    ) -> list[NicheHypothesis]:
        """Rank persisted niche hypotheses and persist explainable score breakdowns."""
        return self._ranking_service.rank_and_persist(session=session, run_id=run.id)

    @staticmethod
    def _source_items_to_book_signals(source_items: list[SourceItem]) -> list[BookSignal]:
        """Bridge persisted raw evidence into the current ranking-compatible shape."""
        signals: list[BookSignal] = []
        for item in source_items:
            published_year = None
            if item.published_date_raw:
                year_candidate = item.published_date_raw[:4]
                published_year = int(year_candidate) if year_candidate.isdigit() else None
            signals.append(
                BookSignal(
                    title=item.title,
                    authors=list(item.authors_json),
                    categories=list(item.categories_json),
                    review_count=item.review_count,
                    average_rating=item.average_rating,
                    published_year=published_year,
                    source=item.provider_name,
                    source_url=item.source_url,
                )
            )
        return signals

    def _mark_run_failed(self, *, run_id: UUID, message: str) -> None:
        """Mark a research run as failed in its own transaction."""
        with self._session_factory() as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                return
            run.status = ResearchRunStatus.FAILED
            run.error_message = message
            run.updated_at = datetime.now(UTC)
            run.completed_at = datetime.now(UTC)
            session.commit()

    def _build_keyword_blueprints(self, *, seed_niche: str, max_candidates: int, book_signals: list[BookSignal]) -> list[KeywordBlueprint]:
        return build_keyword_blueprints(seed_niche, book_signals, max_candidates)

    def _materialize_pipeline(
        self,
        *,
        session: Session,
        run: ResearchRun,
        blueprints: list[KeywordBlueprint],
        book_signals: list[BookSignal],
    ) -> None:
        now = datetime.now(UTC)
        for blueprint in blueprints:
            keyword = KeywordCandidate(
                run_id=run.id,
                keyword_text=blueprint.keyword_text,
                status=KeywordCandidateStatus.ACCEPTED if blueprint.demand_score >= 70 else KeywordCandidateStatus.REVIEWED,
                notes=blueprint.summary,
            )
            session.add(keyword)
            session.flush()

            search_volume = int(blueprint.demand_score * 90 + max(1, blueprint.evidence_count) * 140)
            trend_30d = round((blueprint.trend_score - 50.0) / 3.5, 1)
            trend_90d = round(trend_30d * 1.6, 1)
            opportunity_score = round(
                blueprint.demand_score * 0.28
                + blueprint.trend_score * 0.12
                + blueprint.intent_score * 0.17
                + blueprint.hook_score * 0.15
                + blueprint.monetization_score * 0.14
                + (100.0 - blueprint.competition_score) * 0.14,
                1,
            )

            session.add(
                KeywordMetrics(
                    run_id=run.id,
                    keyword_candidate_id=keyword.id,
                    provider_name="hybrid_public_signals",
                    status=KeywordMetricsStatus.COLLECTED,
                    search_volume=search_volume,
                    competition_score=round(blueprint.competition_score, 1),
                    cpc_usd=round(blueprint.cpc_usd, 2),
                    collected_at=now,
                )
            )
            session.add(
                TrendMetrics(
                    run_id=run.id,
                    keyword_candidate_id=keyword.id,
                    provider_name="hybrid_public_signals",
                    status=TrendMetricsStatus.COLLECTED,
                    trend_score=round(blueprint.trend_score, 1),
                    trend_change_30d=trend_30d,
                    trend_change_90d=trend_90d,
                    seasonality_score=round(blueprint.seasonality_score, 1),
                    collected_at=now,
                )
            )

            competitors = self._pick_competitors(blueprint.keyword_text, book_signals)
            for signal in competitors:
                session.add(
                    Competitor(
                        run_id=run.id,
                        keyword_candidate_id=keyword.id,
                        competitor_name=signal.title,
                        marketplace=signal.source,
                        source_url=signal.source_url,
                        status=CompetitorStatus.ANALYZED,
                        average_rating=signal.average_rating,
                        review_count=signal.review_count,
                    )
                )

            session.add(
                Opportunity(
                    run_id=run.id,
                    keyword_candidate_id=keyword.id,
                    title=blueprint.keyword_text.title(),
                    summary=blueprint.summary,
                    status=OpportunityStatus.RANKED if opportunity_score >= 65 else OpportunityStatus.IDENTIFIED,
                    demand_score=round(blueprint.demand_score, 1),
                    trend_score=round(blueprint.trend_score, 1),
                    intent_score=round(blueprint.intent_score, 1),
                    hook_score=round(blueprint.hook_score, 1),
                    monetization_score=round(blueprint.monetization_score, 1),
                    competition_score=round(blueprint.competition_score, 1),
                    opportunity_score=opportunity_score,
                    rationale_json={
                        "rationale_summary": blueprint.summary,
                        "positives": blueprint.positives,
                        "risks": blueprint.risks,
                        "landing_page_angles": blueprint.landing_page_angles,
                        "market_snapshot": {
                            "search_volume": search_volume,
                            "average_rating": blueprint.average_rating,
                            "review_count": blueprint.review_count or self._review_count(book_signals),
                            "competitor_count": len(competitors),
                            "seasonality_score": round(blueprint.seasonality_score, 1),
                            "cpc_usd": round(blueprint.cpc_usd, 2),
                        },
                        "signal_evidence": {
                            "provider_coverage": blueprint.provider_coverage,
                            "evidence_count": blueprint.evidence_count,
                        },
                    },
                )
            )

        session.flush()

    def _pick_competitors(self, keyword_text: str, book_signals: list[BookSignal]) -> list[BookSignal]:
        keyword_tokens = set(keyword_text.lower().split())
        matching = [
            signal
            for signal in book_signals
            if keyword_tokens.intersection(set(" ".join([signal.title, *signal.categories]).lower().split()))
        ]
        return matching[:3]

    @staticmethod
    def _average_rating(book_signals: list[BookSignal]) -> float | None:
        ratings = [signal.average_rating for signal in book_signals if signal.average_rating is not None]
        if not ratings:
            return None
        return round(sum(ratings) / len(ratings), 2)

    @staticmethod
    def _review_count(book_signals: list[BookSignal]) -> int:
        return sum(signal.review_count or 0 for signal in book_signals)
