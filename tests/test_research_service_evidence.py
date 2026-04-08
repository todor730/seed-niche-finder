from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.api.dependencies import CurrentUser
from app.db.models import ExtractedSignal, KeywordCandidate, NicheHypothesis, NicheScore, Opportunity, ResearchRun, ResearchRunStatus, SignalCluster, SourceItem, SourceItemStatus
from app.schemas.research import CreateResearchRunRequest
from app.services.providers import ProviderFailure, ProviderQuery, ProviderQueryResult, ProviderSearchBatchResult, RawSourceItem
from app.services.research_service import ResearchService


class FakeProviderRegistry:
    def __init__(self, batch: ProviderSearchBatchResult | None = None, *, error: Exception | None = None) -> None:
        self._batch = batch
        self._error = error

    def search(self, seed_niche: str) -> ProviderSearchBatchResult:
        if self._error is not None:
            raise self._error
        assert self._batch is not None
        return self._batch


def make_raw_item(
    *,
    provider_name: str,
    query_text: str,
    dedupe_key: str,
    title: str,
    categories: list[str],
) -> RawSourceItem:
    return RawSourceItem(
        provider_name=provider_name,
        query_text=query_text,
        query_kind="books",
        dedupe_key=dedupe_key,
        provider_item_id=dedupe_key,
        source_url=f"https://example.test/{dedupe_key}",
        title=title,
        authors=["Author One"],
        categories=categories,
        description_text=f"Description for {title}",
        content_text=f"{title}\n{' '.join(categories)}",
        published_date_raw="2024-01-01",
        average_rating=4.2,
        rating_count=12,
        review_count=None,
        raw_payload={"id": dedupe_key, "title": title},
    )


def make_batch(*, include_failure: bool = False) -> ProviderSearchBatchResult:
    query = ProviderQuery(text="romance books", kind="books")
    result = ProviderQueryResult(
        provider_name="google_books",
        query=query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text="romance books",
                dedupe_key="g1",
                title="Enemies to Lovers Small Town Romance",
                categories=["Romance", "Enemies to Lovers", "Small Town Romance"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text="romance books",
                dedupe_key="g2",
                title="Heartfelt Small Town Romance for Women Over 40",
                categories=["Romance", "Small Town Romance", "Women Over 40"],
            ),
        ],
    )
    failures = []
    if include_failure:
        failures.append(
            ProviderFailure(
                provider_name="open_library",
                query=query,
                error_type="ProviderSearchError",
                message="timed out",
                retryable=True,
                occurred_at=datetime.now(UTC),
            )
        )
    return ProviderSearchBatchResult(
        seed_niche="romance",
        queries=[query],
        results=[result],
        failures=failures,
    )


def make_empty_batch(*, include_failure: bool = False) -> ProviderSearchBatchResult:
    query = ProviderQuery(text="romance books", kind="books")
    failures = []
    if include_failure:
        failures.append(
            ProviderFailure(
                provider_name="google_books",
                query=query,
                error_type="ProviderSearchError",
                message="timed out",
                retryable=True,
                occurred_at=datetime.now(UTC),
            )
        )
    return ProviderSearchBatchResult(
        seed_niche="romance",
        queries=[query],
        results=[],
        failures=failures,
    )


def test_research_service_persists_source_items_and_keeps_current_flow(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    with session_factory() as session:
        run = session.get(ResearchRun, UUID(str(created_run.id)))
        source_items = list(session.scalars(select(SourceItem).where(SourceItem.run_id == created_run.id)))
        extracted_signal_count = session.scalar(
            select(func.count()).select_from(ExtractedSignal).where(ExtractedSignal.run_id == created_run.id)
        )
        signal_cluster_count = session.scalar(
            select(func.count()).select_from(SignalCluster).where(SignalCluster.run_id == created_run.id)
        )
        niche_hypothesis_count = session.scalar(
            select(func.count()).select_from(NicheHypothesis).where(NicheHypothesis.run_id == created_run.id)
        )
        niche_score_count = session.scalar(
            select(func.count()).select_from(NicheScore).where(NicheScore.run_id == created_run.id)
        )
        ranked_hypotheses = list(session.scalars(select(NicheHypothesis).where(NicheHypothesis.run_id == created_run.id)))
        keyword_count = session.scalar(select(func.count()).select_from(KeywordCandidate).where(KeywordCandidate.run_id == created_run.id))
        opportunity_count = session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.run_id == created_run.id))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED
    assert len(source_items) == 2
    assert {item.provider_name for item in source_items} == {"google_books"}
    assert {item.query_text for item in source_items} == {"romance books"}
    assert all(item.raw_payload_json for item in source_items)
    assert all(item.status == SourceItemStatus.CLUSTERED for item in source_items)
    assert (extracted_signal_count or 0) >= 2
    assert (signal_cluster_count or 0) >= 1
    assert (niche_hypothesis_count or 0) >= 1
    assert (niche_score_count or 0) >= 5
    assert all(hypothesis.overall_score is not None for hypothesis in ranked_hypotheses)
    assert all(hypothesis.rank_position is not None for hypothesis in ranked_hypotheses)
    assert (keyword_count or 0) >= 1
    assert (opportunity_count or 0) >= 1


def test_research_service_handles_partial_provider_failure_and_persists_available_items(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch(include_failure=True)),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    with session_factory() as session:
        run = session.get(ResearchRun, UUID(str(created_run.id)))
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem).where(SourceItem.run_id == created_run.id))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED
    assert (source_item_count or 0) == 2


def test_research_service_completes_without_evidence_and_does_not_materialize_synthetic_results(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_empty_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    with session_factory() as session:
        run = session.get(ResearchRun, UUID(str(created_run.id)))
        source_item_count = session.scalar(select(func.count()).select_from(SourceItem).where(SourceItem.run_id == created_run.id))
        extracted_signal_count = session.scalar(
            select(func.count()).select_from(ExtractedSignal).where(ExtractedSignal.run_id == created_run.id)
        )
        cluster_count = session.scalar(
            select(func.count()).select_from(SignalCluster).where(SignalCluster.run_id == created_run.id)
        )
        hypothesis_count = session.scalar(
            select(func.count()).select_from(NicheHypothesis).where(NicheHypothesis.run_id == created_run.id)
        )
        keyword_count = session.scalar(select(func.count()).select_from(KeywordCandidate).where(KeywordCandidate.run_id == created_run.id))
        opportunity_count = session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.run_id == created_run.id))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED_NO_EVIDENCE
    assert run.error_message == "No persisted source evidence was collected from the configured providers."
    assert (source_item_count or 0) == 0
    assert (extracted_signal_count or 0) == 0
    assert (cluster_count or 0) == 0
    assert (hypothesis_count or 0) == 0
    assert (keyword_count or 0) == 0
    assert (opportunity_count or 0) == 0


def test_research_service_marks_partial_failure_only_run_as_completed_without_evidence(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_empty_batch(include_failure=True)),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    with session_factory() as session:
        run = session.get(ResearchRun, UUID(str(created_run.id)))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED_NO_EVIDENCE
    assert run.error_message == "No persisted source evidence was collected from the configured providers."


def test_research_service_marks_run_failed_when_provider_registry_raises(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(error=RuntimeError("provider registry crashed")),
    )

    try:
        service.create_run(
            current_user=current_user,
            payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
        )
    except RuntimeError as exc:
        assert "provider registry crashed" in str(exc)
    else:  # pragma: no cover - defensive branch
        raise AssertionError("Expected provider registry failure to be raised.")

    with session_factory() as session:
        runs = list(session.scalars(select(ResearchRun).order_by(ResearchRun.created_at.desc())))
        assert runs
        assert runs[0].status == ResearchRunStatus.FAILED
        assert runs[0].error_message == "provider registry crashed"
