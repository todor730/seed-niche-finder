from __future__ import annotations

from sqlalchemy import select

from app.db.models import ExtractedSignal, ResearchRun, ResearchRunStatus, SignalCluster, SourceItem, SourceItemStatus, User, UserStatus
from app.schemas.evidence import ExtractedSignalCreate, SourceItemCreate
from app.services.clustering import ClusteringService


def _make_run(session) -> ResearchRun:
    user = User(email="cluster@test.local", status=UserStatus.ACTIVE)
    session.add(user)
    session.flush()

    run = ResearchRun(
        user_id=user.id,
        seed_niche="romance",
        title="Romance",
        status=ResearchRunStatus.RUNNING,
        config_json={"max_candidates": 20, "top_k": 5},
    )
    session.add(run)
    session.flush()
    return run


def _make_source_item(session, *, run_id, provider_name: str, dedupe_key: str, title: str) -> SourceItem:
    source_item = SourceItem(
        **SourceItemCreate(
            run_id=run_id,
            provider_name=provider_name,
            query_text="romance books",
            query_kind="books",
            provider_item_id=dedupe_key,
            dedupe_key=dedupe_key,
            source_url=f"https://example.test/{dedupe_key}",
            title=title,
            authors_json=["Author One"],
            categories_json=["Romance"],
            description_text=title,
            content_text=title,
            raw_payload_json={"title": title},
            status=SourceItemStatus.EXTRACTED,
        ).model_dump(exclude_none=True)
    )
    session.add(source_item)
    session.flush()
    return source_item


def _make_signal(
    session,
    *,
    run_id,
    source_item_id,
    signal_type: str,
    signal_value: str,
    normalized_value: str,
    confidence: float,
    extraction_method: str = "rule:test",
) -> ExtractedSignal:
    signal = ExtractedSignal(
        **ExtractedSignalCreate(
            run_id=run_id,
            source_item_id=source_item_id,
            signal_type=signal_type,
            signal_value=signal_value,
            normalized_value=normalized_value,
            confidence=confidence,
            extraction_method=extraction_method,
            evidence_span=f"title: {signal_value}",
        ).model_dump(exclude_none=True)
    )
    session.add(signal)
    session.flush()
    return signal


def test_clustering_service_groups_signals_by_type_with_explainable_assignments(session_factory) -> None:
    service = ClusteringService()

    with session_factory() as session:
        run = _make_run(session)
        source_item_1 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="s1", title="Small Town Romance")
        source_item_2 = _make_source_item(session, run_id=run.id, provider_name="open_library", dedupe_key="s2", title="Romance Small Town")
        source_item_3 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="s3", title="Enemies to Lovers")

        signals = [
            _make_signal(
                session,
                run_id=run.id,
                source_item_id=source_item_1.id,
                signal_type="subgenre",
                signal_value="Small Town Romance",
                normalized_value="small town romance",
                confidence=0.95,
            ),
            _make_signal(
                session,
                run_id=run.id,
                source_item_id=source_item_2.id,
                signal_type="subgenre",
                signal_value="Romance Small Town",
                normalized_value="romance small town",
                confidence=0.82,
            ),
            _make_signal(
                session,
                run_id=run.id,
                source_item_id=source_item_3.id,
                signal_type="trope",
                signal_value="Enemies to Lovers",
                normalized_value="enemies to lovers",
                confidence=0.90,
            ),
        ]

        result = service.cluster_and_persist(session=session, extracted_signals=signals)
        session.commit()

        clusters = list(session.scalars(select(SignalCluster).where(SignalCluster.run_id == run.id)))
        persisted_signals = list(session.scalars(select(ExtractedSignal).where(ExtractedSignal.run_id == run.id)))
        persisted_items = list(session.scalars(select(SourceItem).where(SourceItem.run_id == run.id)))

    subgenre_clusters = [cluster for cluster in clusters if cluster.signal_type == "subgenre"]
    trope_clusters = [cluster for cluster in clusters if cluster.signal_type == "trope"]

    assert len(result.clusters) == 2
    assert len(subgenre_clusters) == 1
    assert len(trope_clusters) == 1
    assert subgenre_clusters[0].canonical_label == "small town romance"
    assert "Romance Small Town" in subgenre_clusters[0].aliases_json
    assert subgenre_clusters[0].source_count == 2
    assert subgenre_clusters[0].item_count == 2
    assert subgenre_clusters[0].avg_confidence >= 0.88
    assert subgenre_clusters[0].saturation_score >= 0.0
    assert subgenre_clusters[0].novelty_score >= 0.0
    assert all(signal.cluster_id is not None for signal in persisted_signals)
    assert all(item.status == SourceItemStatus.CLUSTERED for item in persisted_items)
    assert any(assignment.reason.value == "token_reorder_match" for assignment in result.assignments)
    assert any(assignment.reason.value == "new_cluster" for assignment in result.assignments)


def test_clustering_service_keeps_distinct_signal_types_separate(session_factory) -> None:
    service = ClusteringService()

    with session_factory() as session:
        run = _make_run(session)
        source_item_1 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="a1", title="Dark Romance")
        source_item_2 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="a2", title="Dark")

        signals = [
            _make_signal(
                session,
                run_id=run.id,
                source_item_id=source_item_1.id,
                signal_type="subgenre",
                signal_value="Dark Romance",
                normalized_value="dark romance",
                confidence=0.94,
            ),
            _make_signal(
                session,
                run_id=run.id,
                source_item_id=source_item_2.id,
                signal_type="tone",
                signal_value="Dark",
                normalized_value="dark",
                confidence=0.88,
            ),
        ]

        result = service.cluster_and_persist(session=session, extracted_signals=signals)

    labels = {(cluster.signal_type, cluster.canonical_label) for cluster in result.clusters}
    assert labels == {("subgenre", "dark romance"), ("tone", "dark")}
