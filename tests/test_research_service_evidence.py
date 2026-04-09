from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.api.dependencies import CurrentUser
from app.db.models import (
    ExtractedSignal,
    KeywordCandidate,
    NicheHypothesis,
    NicheScore,
    Opportunity,
    ResearchRun,
    ResearchRunStatus,
    SignalCluster,
    SourceItem,
    SourceItemQueryLink,
    SourceItemStatus,
    SourceQuery,
    ProviderFailureRecord,
)
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
    subtitle: str | None = None,
    description_text: str | None = None,
) -> RawSourceItem:
    return RawSourceItem(
        provider_name=provider_name,
        query_text=query_text,
        query_kind="books",
        dedupe_key=dedupe_key,
        provider_item_id=dedupe_key,
        source_url=f"https://example.test/{dedupe_key}",
        title=title,
        subtitle=subtitle,
        authors=["Author One"],
        categories=categories,
        description_text=description_text or f"Description for {title}",
        content_text="\n".join(
            part
            for part in [
                title,
                subtitle or "",
                " ".join(categories),
                description_text or f"Description for {title}",
            ]
            if part
        ),
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


def make_multi_query_traceability_batch() -> ProviderSearchBatchResult:
    first_query = ProviderQuery(text="romance books", kind="books", priority=95, tags=("books",))
    second_query = ProviderQuery(text="best romance books", kind="best_of", priority=90, tags=("best_of",))
    first_result = ProviderQueryResult(
        provider_name="google_books",
        query=first_query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text=first_query.text,
                dedupe_key="g1",
                title="Enemies to Lovers Small Town Romance",
                categories=["Romance", "Enemies to Lovers", "Small Town Romance"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=first_query.text,
                dedupe_key="g2",
                title="Heartfelt Small Town Romance for Women Over 40",
                categories=["Romance", "Small Town Romance", "Women Over 40"],
            ),
        ],
    )
    second_result = ProviderQueryResult(
        provider_name="google_books",
        query=second_query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text=second_query.text,
                dedupe_key="g1",
                title="Enemies to Lovers Small Town Romance",
                categories=["Romance", "Enemies to Lovers", "Small Town Romance"],
            ),
        ],
    )
    return ProviderSearchBatchResult(
        seed_niche="romance",
        queries=[first_query, second_query],
        results=[first_result, second_result],
        failures=[],
    )


def make_self_help_quality_batch() -> ProviderSearchBatchResult:
    query = ProviderQuery(text="self-help books", kind="books")
    result = ProviderQueryResult(
        provider_name="google_books",
        query=query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="s1",
                title="God Help the Child",
                categories=["Literary Fiction", "Novel"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="s2",
                title="Self Help Books",
                categories=["Self Help", "Personal Growth"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="s3",
                title="Greatest Self Help Book",
                categories=["Self Help", "Personal Growth"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="s4",
                title="Self Confidence and Self Esteem Workbook for Women",
                categories=["Self Help", "Self Confidence", "Self Esteem", "Women", "Workbook"],
                description_text="A practical workbook for women who want to rebuild self confidence and self esteem.",
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="s5",
                title="Burnout Recovery Workbook for Busy Professionals",
                categories=["Self Help", "Burnout Recovery", "Busy Professionals", "Workbook"],
                description_text="A workbook for busy professionals dealing with burnout and stress.",
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="s6",
                title="Depression and Anxiety Relief Journal",
                categories=["Self Help", "Anxiety", "Journal"],
                description_text="A guided journal for young adults dealing with anxiety and depression.",
            ),
        ],
    )
    return ProviderSearchBatchResult(
        seed_niche="self-help",
        queries=[query],
        results=[result],
        failures=[],
    )


def make_self_help_live_failure_like_batch() -> ProviderSearchBatchResult:
    query = ProviderQuery(text="self-help books", kind="books")
    result = ProviderQueryResult(
        provider_name="google_books",
        query=query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="sl1",
                title="The Self Help Book",
                categories=["Self Help", "Personal Growth"],
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="sl2",
                title="The Self Help Compulsion",
                categories=["Self Help", "Psychology"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="sl3",
                title="God Help the Child",
                categories=["Self Help", "Personal Growth"],
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="sl4",
                title="Greatest Self Help Book",
                categories=["Self Help", "Personal Growth"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="sl5",
                title="Ten Days to Self Esteem",
                categories=["Self Help", "Self Esteem"],
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="sl6",
                title="Self Confidence and Self Esteem Workbook for Women",
                categories=["Self Help", "Self Confidence", "Self Esteem", "Women", "Workbook"],
                description_text="A practical workbook for women who want to rebuild self confidence and self esteem.",
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="sl7",
                title="Burnout Recovery Workbook for Busy Professionals",
                categories=["Self Help", "Burnout Recovery", "Busy Professionals", "Workbook"],
                description_text="A workbook for busy professionals dealing with burnout and stress.",
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="sl8",
                title="Depression and Anxiety Relief Journal",
                categories=["Self Help", "Anxiety", "Journal"],
                description_text="A guided journal for young adults dealing with anxiety and depression.",
            ),
        ],
    )
    return ProviderSearchBatchResult(
        seed_niche="self-help",
        queries=[query],
        results=[result],
        failures=[],
    )


def make_rich_romance_batch() -> ProviderSearchBatchResult:
    query = ProviderQuery(text="romance books", kind="books")
    result = ProviderQueryResult(
        provider_name="google_books",
        query=query,
        items=[
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="rr1",
                title="Friends to Lovers Small Town Romance for Women Over 40",
                categories=["Romance", "Friends to Lovers", "Small Town Romance", "Women Over 40"],
                description_text="A heartfelt romance for women over 40 in a small town.",
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="rr2",
                title="Humorous Small Town Romance",
                categories=["Romance", "Small Town Romance", "Humorous"],
                description_text="A humorous small-town love story.",
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="rr3",
                title="Opposites Attract Contemporary Romance",
                categories=["Romance", "Contemporary Romance", "Opposites Attract"],
                description_text="A steamy opposites attract contemporary romance.",
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="rr4",
                title="Steamy Contemporary Romance in a Small Town",
                categories=["Romance", "Contemporary Romance", "Steamy", "Small Town"],
                description_text="A steamy contemporary romance set in a small town.",
            ),
            make_raw_item(
                provider_name="google_books",
                query_text=query.text,
                dedupe_key="rr5",
                title="Sweet Paranormal Romance for Young Adults",
                categories=["Romance", "Paranormal Romance", "Sweet", "Young Adults"],
                description_text="A sweet paranormal romance for young adults.",
            ),
            make_raw_item(
                provider_name="open_library",
                query_text=query.text,
                dedupe_key="rr6",
                title="Young Adult Paranormal Romance",
                categories=["Romance", "Paranormal Romance", "Young Adult"],
                description_text="A young adult paranormal romance adventure.",
            ),
        ],
    )
    return ProviderSearchBatchResult(
        seed_niche="romance",
        queries=[query],
        results=[result],
        failures=[],
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
    assert created_run.depth_score is not None
    assert created_run.depth_score.score > 0.0
    assert created_run.depth_score.source_items_count == 2
    assert created_run.depth_score.extracted_signals_count == (extracted_signal_count or 0)
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
        failures = list(session.scalars(select(ProviderFailureRecord).where(ProviderFailureRecord.run_id == created_run.id)))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED
    assert created_run.depth_score is not None
    assert created_run.depth_score.provider_failures_count == 1
    assert (source_item_count or 0) == 2
    assert len(failures) == 1
    assert failures[0].provider_name == "open_library"
    assert failures[0].query_text == "romance books"
    assert failures[0].error_type == "ProviderSearchError"
    assert failures[0].message == "timed out"
    assert failures[0].retryable is True


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
    assert created_run.depth_score is not None
    assert created_run.depth_score.score == 0.0
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
        failures = list(session.scalars(select(ProviderFailureRecord).where(ProviderFailureRecord.run_id == created_run.id)))

    assert run is not None
    assert run.status == ResearchRunStatus.COMPLETED_NO_EVIDENCE
    assert created_run.depth_score is not None
    assert created_run.depth_score.score == 0.0
    assert run.error_message == "No persisted source evidence was collected from the configured providers."
    assert len(failures) == 1
    assert failures[0].provider_name == "google_books"


def test_research_service_preserves_query_level_traceability_for_deduped_source_items(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_multi_query_traceability_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    with session_factory() as session:
        source_items = list(session.scalars(select(SourceItem).where(SourceItem.run_id == created_run.id).order_by(SourceItem.dedupe_key)))
        source_queries = list(session.scalars(select(SourceQuery).where(SourceQuery.run_id == created_run.id).order_by(SourceQuery.query_text)))
        links = list(session.scalars(select(SourceItemQueryLink).order_by(SourceItemQueryLink.created_at)))
        g1 = next(item for item in source_items if item.dedupe_key == "g1")
        g1_query_texts = sorted(
            session.scalars(
                select(SourceQuery.query_text)
                .join(SourceItemQueryLink, SourceItemQueryLink.source_query_id == SourceQuery.id)
                .where(SourceItemQueryLink.source_item_id == g1.id)
            )
        )

    assert len(source_items) == 2
    assert len(source_queries) == 2
    assert len(links) == 3
    assert [query.query_text for query in source_queries] == ["best romance books", "romance books"]
    assert g1.query_text == "romance books"
    assert g1_query_texts == ["best romance books", "romance books"]


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


def test_research_service_depth_score_penalizes_provider_failures(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    clean_service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch()),
    )
    degraded_service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_batch(include_failure=True)),
    )

    clean_run = clean_service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )
    degraded_run = degraded_service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 5}),
    )

    assert clean_run.depth_score is not None
    assert degraded_run.depth_score is not None
    assert clean_run.depth_score.score > degraded_run.depth_score.score
    assert degraded_run.depth_score.provider_failures_count == 1
    assert degraded_run.depth_score.breakdown.failure_adjustment > 0.0


def test_research_service_suppresses_generic_and_false_positive_self_help_outputs(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_self_help_quality_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="self-help", config={"max_candidates": 20, "top_k": 10}),
    )

    with session_factory() as session:
        keywords = list(
            session.scalars(select(KeywordCandidate).where(KeywordCandidate.run_id == created_run.id).order_by(KeywordCandidate.keyword_text))
        )
        opportunities = list(
            session.scalars(select(Opportunity).where(Opportunity.run_id == created_run.id).order_by(Opportunity.title))
        )

    keyword_texts = {keyword.keyword_text for keyword in keywords}
    opportunity_titles = {opportunity.title.lower() for opportunity in opportunities}

    assert "god help the child" not in keyword_texts
    assert "self help" not in keyword_texts
    assert "self help books" not in keyword_texts
    assert "greatest self help book" not in keyword_texts
    assert "anxiety journal for young adults" in keyword_texts
    assert any(keyword in keyword_texts for keyword in {"burnout workbook for busy professionals", "burnout recovery workbook for busy professionals"})
    assert any(
        keyword in keyword_texts
        for keyword in {"self confidence workbook", "self esteem workbook", "confidence workbook"}
    )
    assert len(opportunity_titles) == len(opportunities)
    assert "god help the child" not in opportunity_titles
    assert "self help" not in opportunity_titles
    assert len(opportunity_titles) >= 3


def test_research_service_filters_observed_live_self_help_failure_pattern(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_self_help_live_failure_like_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="self-help", config={"max_candidates": 20, "top_k": 10}),
    )

    with session_factory() as session:
        keywords = list(
            session.scalars(select(KeywordCandidate).where(KeywordCandidate.run_id == created_run.id).order_by(KeywordCandidate.keyword_text))
        )
        opportunities = list(
            session.scalars(select(Opportunity).where(Opportunity.run_id == created_run.id).order_by(Opportunity.title))
        )

    keyword_texts = {keyword.keyword_text for keyword in keywords}
    opportunity_titles = {opportunity.title.lower() for opportunity in opportunities}

    assert "the self help book" not in keyword_texts
    assert "the self help compulsion" not in keyword_texts
    assert "god help the child" not in keyword_texts
    assert "greatest self help book" not in keyword_texts
    assert "self help" not in keyword_texts
    assert "self help books" not in keyword_texts
    assert "ten days to self esteem" not in keyword_texts
    assert "anxiety journal for young adults" in keyword_texts
    assert any(keyword in keyword_texts for keyword in {"burnout workbook for busy professionals", "burnout recovery workbook for busy professionals"})
    assert any(
        keyword in keyword_texts
        for keyword in {"self confidence workbook", "self esteem workbook", "confidence workbook"}
    )
    assert "busy professionals" not in keyword_texts

    assert "the self help book" not in opportunity_titles
    assert "the self help compulsion" not in opportunity_titles
    assert "god help the child" not in opportunity_titles
    assert "greatest self help book" not in opportunity_titles
    assert "self help" not in opportunity_titles
    assert "busy professionals" not in opportunity_titles
    assert len(opportunity_titles) >= 3


def test_research_service_materializes_multiple_distinct_romance_micro_niches(
    session_factory,
    workspace: Path,
    current_user: CurrentUser,
) -> None:
    service = ResearchService(
        session_factory,
        export_storage_path=str(workspace / "exports"),
        provider_registry=FakeProviderRegistry(make_rich_romance_batch()),
    )

    created_run = service.create_run(
        current_user=current_user,
        payload=CreateResearchRunRequest(seed_niche="romance", config={"max_candidates": 20, "top_k": 10}),
    )

    with session_factory() as session:
        keywords = list(
            session.scalars(select(KeywordCandidate).where(KeywordCandidate.run_id == created_run.id).order_by(KeywordCandidate.keyword_text))
        )
        opportunities = list(
            session.scalars(select(Opportunity).where(Opportunity.run_id == created_run.id).order_by(Opportunity.title))
        )
        hypotheses = list(
            session.scalars(select(NicheHypothesis).where(NicheHypothesis.run_id == created_run.id).order_by(NicheHypothesis.hypothesis_label))
        )

    keyword_texts = {keyword.keyword_text for keyword in keywords}
    opportunity_titles = {opportunity.title.lower() for opportunity in opportunities}
    hypothesis_labels = {hypothesis.hypothesis_label for hypothesis in hypotheses}

    assert 4 <= len(hypotheses) <= 8
    assert len(keyword_texts) == len(keywords)
    assert len(opportunity_titles) == len(opportunities)
    assert "friends to lovers small town romance" in hypothesis_labels
    assert "humorous small town romance" in hypothesis_labels
    assert "opposites attract contemporary romance" in hypothesis_labels
    assert "young adults paranormal romance" in hypothesis_labels or "sweet paranormal romance" in hypothesis_labels
    assert keyword_texts == hypothesis_labels
    assert "friends to lovers small town romance" in keyword_texts
    assert "humorous small town romance" in keyword_texts
    assert "opposites attract contemporary romance" in keyword_texts
    assert "young adults paranormal romance" in keyword_texts or "sweet paranormal romance" in keyword_texts
    assert "friends to lovers small town romance" in opportunity_titles
    assert "humorous small town romance" in opportunity_titles
    assert "opposites attract contemporary romance" in opportunity_titles
