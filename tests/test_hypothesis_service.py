from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.models import (
    ExtractedSignal,
    NicheHypothesis,
    ResearchRun,
    ResearchRunStatus,
    SourceItem,
    SourceItemStatus,
    User,
    UserStatus,
)
from app.schemas.evidence import ExtractedSignalCreate, SourceItemCreate
from app.services.clustering import ClusteringService
from app.services.hypotheses import NicheHypothesisService


def _make_run(session, *, seed_niche: str = "romance") -> ResearchRun:
    user = User(email=f"{seed_niche}@hypothesis.test", status=UserStatus.ACTIVE)
    session.add(user)
    session.flush()

    run = ResearchRun(
        user_id=user.id,
        seed_niche=seed_niche,
        title=seed_niche.title(),
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
            query_text="research query",
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
) -> ExtractedSignal:
    signal = ExtractedSignal(
        **ExtractedSignalCreate(
            run_id=run_id,
            source_item_id=source_item_id,
            signal_type=signal_type,
            signal_value=signal_value,
            normalized_value=normalized_value,
            confidence=confidence,
            extraction_method="rule:test",
            evidence_span=f"title: {signal_value}",
        ).model_dump(exclude_none=True)
    )
    session.add(signal)
    session.flush()
    return signal


def test_hypothesis_service_builds_coherent_fiction_micro_niche(session_factory) -> None:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    with session_factory() as session:
        run = _make_run(session, seed_niche="romance")
        source_item_1 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="r1", title="Enemies to Lovers Small Town Romance")
        source_item_2 = _make_source_item(session, run_id=run.id, provider_name="open_library", dedupe_key="r2", title="Heartfelt Small Town Romance for Women Over 40")

        extracted_signals = [
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.95),
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="trope", signal_value="Enemies to Lovers", normalized_value="enemies to lovers", confidence=0.92),
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="setting", signal_value="Small Town", normalized_value="small town", confidence=0.80),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.90),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="audience", signal_value="Women Over 40", normalized_value="women over 40", confidence=0.84),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="tone", signal_value="Heartfelt", normalized_value="heartfelt", confidence=0.78),
        ]

        clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
        hypotheses = hypothesis_service.generate_and_persist(session=session, run_id=run.id)
        session.commit()

        persisted = list(session.scalars(select(NicheHypothesis).where(NicheHypothesis.run_id == run.id)))

    labels = {hypothesis.hypothesis_label for hypothesis in persisted}

    assert len(hypotheses) >= 1
    assert "enemies to lovers small town romance" in labels
    primary = next(hypothesis for hypothesis in persisted if hypothesis.hypothesis_label == "enemies to lovers small town romance")
    assert primary.evidence_count == 2
    assert primary.source_count == 2
    assert primary.rationale_json["components"][0]["signal_type"] == "subgenre"
    assert any(component["signal_type"] == "trope" for component in primary.rationale_json["components"])
    assert primary.rationale_json["supporting_source_titles"]
    assert primary.rationale_json["assembly_version"] == "hypothesis_v2"


def test_hypothesis_service_rejects_generic_anchor_only_clusters(session_factory, caplog) -> None:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    caplog.set_level(logging.INFO, logger="app.services.hypotheses.service")

    with session_factory() as session:
        run = _make_run(session, seed_niche="romance")
        source_item = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="g1", title="Small Town Romance")

        extracted_signals = [
            _make_signal(session, run_id=run.id, source_item_id=source_item.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.95),
            _make_signal(session, run_id=run.id, source_item_id=source_item.id, signal_type="setting", signal_value="Small Town", normalized_value="small town", confidence=0.80),
        ]

        clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
        hypotheses = hypothesis_service.generate_and_persist(session=session, run_id=run.id)

    assert hypotheses == []
    rejection_logs = [record for record in caplog.records if getattr(record, "stage", "") == "niche_hypothesis_rejected"]
    assert rejection_logs
    assert rejection_logs[0].anchor_label == "small town romance"
    assert rejection_logs[0].reason_code in {
        "fiction_branch_missing_secondary",
        "fiction_branch_not_specific_enough",
        "no_viable_branches",
    }


def test_hypothesis_service_branches_rich_romance_input_without_near_duplicate_spam(session_factory) -> None:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    with session_factory() as session:
        run = _make_run(session, seed_niche="romance")

        source_item_1 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="google_books",
            dedupe_key="rr1",
            title="Friends to Lovers Small Town Romance",
        )
        source_item_2 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="open_library",
            dedupe_key="rr2",
            title="Humorous Small Town Romance",
        )
        source_item_3 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="google_books",
            dedupe_key="rr3",
            title="Opposites Attract Contemporary Romance",
        )
        source_item_4 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="open_library",
            dedupe_key="rr4",
            title="Steamy Contemporary Romance in a Small Town",
        )
        source_item_5 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="google_books",
            dedupe_key="rr5",
            title="Sweet Paranormal Romance for Young Adults",
        )
        source_item_6 = _make_source_item(
            session,
            run_id=run.id,
            provider_name="open_library",
            dedupe_key="rr6",
            title="Young Adult Paranormal Romance",
        )

        extracted_signals = [
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.95),
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="trope", signal_value="Friends to Lovers", normalized_value="friends to lovers", confidence=0.92),
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="audience", signal_value="Women Over 40", normalized_value="women over 40", confidence=0.83),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.91),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="tone", signal_value="Humorous", normalized_value="humorous", confidence=0.82),
            _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="subgenre", signal_value="Contemporary Romance", normalized_value="contemporary romance", confidence=0.94),
            _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="trope", signal_value="Opposites Attract", normalized_value="opposites attract", confidence=0.88),
            _make_signal(session, run_id=run.id, source_item_id=source_item_4.id, signal_type="subgenre", signal_value="Contemporary Romance", normalized_value="contemporary romance", confidence=0.89),
            _make_signal(session, run_id=run.id, source_item_id=source_item_4.id, signal_type="tone", signal_value="Steamy", normalized_value="steamy", confidence=0.81),
            _make_signal(session, run_id=run.id, source_item_id=source_item_4.id, signal_type="setting", signal_value="Small Town", normalized_value="small town", confidence=0.78),
            _make_signal(session, run_id=run.id, source_item_id=source_item_5.id, signal_type="subgenre", signal_value="Paranormal Romance", normalized_value="paranormal romance", confidence=0.93),
            _make_signal(session, run_id=run.id, source_item_id=source_item_5.id, signal_type="tone", signal_value="Sweet", normalized_value="sweet", confidence=0.84),
            _make_signal(session, run_id=run.id, source_item_id=source_item_5.id, signal_type="audience", signal_value="Young Adults", normalized_value="young adults", confidence=0.87),
            _make_signal(session, run_id=run.id, source_item_id=source_item_6.id, signal_type="subgenre", signal_value="Paranormal Romance", normalized_value="paranormal romance", confidence=0.90),
            _make_signal(session, run_id=run.id, source_item_id=source_item_6.id, signal_type="audience", signal_value="Young Adults", normalized_value="young adults", confidence=0.85),
        ]

        clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
        hypotheses = hypothesis_service.generate_and_persist(session=session, run_id=run.id)

    labels = {hypothesis.hypothesis_label for hypothesis in hypotheses}

    assert 4 <= len(hypotheses) <= 8
    assert len(labels) == len(hypotheses)
    assert "friends to lovers small town romance" in labels
    assert "humorous small town romance" in labels
    assert "opposites attract contemporary romance" in labels
    assert "young adults paranormal romance" in labels or "sweet paranormal romance" in labels
    assert "small town contemporary romance" not in labels or "opposites attract contemporary romance" in labels
    assert all("romance" in label for label in labels)


def test_hypothesis_service_exposes_anchor_diagnostics_for_branch_analysis(session_factory) -> None:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    with session_factory() as session:
        run = _make_run(session, seed_niche="romance")
        source_item_1 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="dx1", title="Friends to Lovers Small Town Romance")
        source_item_2 = _make_source_item(session, run_id=run.id, provider_name="open_library", dedupe_key="dx2", title="Humorous Small Town Romance")
        source_item_3 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="dx3", title="Opposites Attract Contemporary Romance")

        extracted_signals = [
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.95),
            _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="trope", signal_value="Friends to Lovers", normalized_value="friends to lovers", confidence=0.92),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.90),
            _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="tone", signal_value="Humorous", normalized_value="humorous", confidence=0.82),
            _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="subgenre", signal_value="Contemporary Romance", normalized_value="contemporary romance", confidence=0.94),
            _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="trope", signal_value="Opposites Attract", normalized_value="opposites attract", confidence=0.88),
        ]

        clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
        persisted = hypothesis_service.generate_and_persist(session=session, run_id=run.id)
        diagnostics = hypothesis_service.diagnose_run(session=session, run_id=run.id)

    assert diagnostics.persisted_hypothesis_count == len(persisted)
    assert diagnostics.fiction_anchors
    small_town = next(anchor for anchor in diagnostics.fiction_anchors if anchor.anchor_label == "small town romance")
    assert small_town.raw_branch_count >= small_town.post_dedupe_branch_count >= 1
    assert "trope" in small_town.candidate_components_by_type
    assert any(branch.label == "friends to lovers small town romance" for branch in small_town.raw_branches)
    assert any(branch.label == "humorous small town romance" for branch in small_town.post_dedupe_branches)
    assert all(branch.reject_reason_code is None for branch in small_town.post_dedupe_branches)


def test_hypothesis_service_builds_nonfiction_problem_solution_hypothesis(session_factory) -> None:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    with session_factory() as session:
        run = _make_run(session, seed_niche="burnout")
        source_item = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="n1", title="Burnout Workbook for Busy Professionals")

        extracted_signals = [
            _make_signal(session, run_id=run.id, source_item_id=source_item.id, signal_type="problem_angle", signal_value="Burnout", normalized_value="burnout", confidence=0.94),
            _make_signal(session, run_id=run.id, source_item_id=source_item.id, signal_type="solution_angle", signal_value="Workbook", normalized_value="workbook", confidence=0.91),
            _make_signal(session, run_id=run.id, source_item_id=source_item.id, signal_type="audience", signal_value="Busy Professionals", normalized_value="busy professionals", confidence=0.82),
        ]

        clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
        hypotheses = hypothesis_service.generate_and_persist(session=session, run_id=run.id)

    assert len(hypotheses) == 1
    assert hypotheses[0].hypothesis_label == "burnout workbook for busy professionals"
