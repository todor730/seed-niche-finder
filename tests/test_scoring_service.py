from __future__ import annotations

from sqlalchemy import select

from app.db.models import (
    ExtractedSignal,
    NicheHypothesis,
    NicheHypothesisStatus,
    NicheScore,
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
from app.services.scoring import CompetitionDensityModel, HypothesisRankingService, RankingCalibration


def _make_run(session, *, seed_niche: str = "romance") -> ResearchRun:
    user = User(email=f"{seed_niche}@scoring.test", status=UserStatus.ACTIVE)
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


def _build_rankable_run(session) -> ResearchRun:
    clustering_service = ClusteringService()
    hypothesis_service = NicheHypothesisService()

    run = _make_run(session, seed_niche="romance")

    # Strong, specific, cross-provider hypothesis
    source_item_1 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="r1", title="Enemies to Lovers Small Town Romance")
    source_item_2 = _make_source_item(session, run_id=run.id, provider_name="open_library", dedupe_key="r2", title="Heartfelt Small Town Romance for Women Over 40")

    # Weaker, generic hypothesis
    source_item_3 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="r3", title="Dark Romance")
    source_item_4 = _make_source_item(session, run_id=run.id, provider_name="google_books", dedupe_key="r4", title="Dark Romance")

    extracted_signals = [
        _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.95),
        _make_signal(session, run_id=run.id, source_item_id=source_item_1.id, signal_type="trope", signal_value="Enemies to Lovers", normalized_value="enemies to lovers", confidence=0.92),
        _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="subgenre", signal_value="Small Town Romance", normalized_value="small town romance", confidence=0.90),
        _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="audience", signal_value="Women Over 40", normalized_value="women over 40", confidence=0.84),
        _make_signal(session, run_id=run.id, source_item_id=source_item_2.id, signal_type="tone", signal_value="Heartfelt", normalized_value="heartfelt", confidence=0.78),
        _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="subgenre", signal_value="Dark Romance", normalized_value="dark romance", confidence=0.92),
        _make_signal(session, run_id=run.id, source_item_id=source_item_3.id, signal_type="audience", signal_value="Young Adults", normalized_value="young adults", confidence=0.73),
        _make_signal(session, run_id=run.id, source_item_id=source_item_4.id, signal_type="subgenre", signal_value="Dark Romance", normalized_value="dark romance", confidence=0.91),
        _make_signal(session, run_id=run.id, source_item_id=source_item_4.id, signal_type="tone", signal_value="Dark", normalized_value="dark", confidence=0.86),
    ]

    clustering_service.cluster_and_persist(session=session, extracted_signals=extracted_signals)
    hypothesis_service.generate_and_persist(session=session, run_id=run.id)
    return run


def test_scoring_service_persists_explainable_breakdown_and_ranks_hypotheses(session_factory) -> None:
    ranking_service = HypothesisRankingService()

    with session_factory() as session:
        run = _build_rankable_run(session)
        ranked = ranking_service.rank_and_persist(session=session, run_id=run.id)
        session.commit()

        hypotheses = list(session.scalars(select(NicheHypothesis).where(NicheHypothesis.run_id == run.id).order_by(NicheHypothesis.rank_position.asc())))
        scores = list(session.scalars(select(NicheScore).where(NicheScore.run_id == run.id)))

    assert len(ranked) == 2
    assert len(hypotheses) == 2
    assert len(scores) == 10
    assert hypotheses[0].hypothesis_label == "enemies to lovers small town romance"
    assert hypotheses[0].overall_score is not None
    assert hypotheses[0].rank_position == 1
    assert hypotheses[0].status == NicheHypothesisStatus.SCORED
    assert hypotheses[1].rank_position == 2
    assert hypotheses[0].overall_score > hypotheses[1].overall_score

    score_types = {(score.niche_hypothesis_id, score.score_type) for score in scores}
    assert all(score_type in {"discovery_score", "opportunity_score", "competition_score", "confidence_score", "final_score"} for _id, score_type in score_types)
    final_score = next(score for score in scores if score.niche_hypothesis_id == hypotheses[0].id and score.score_type == "final_score")
    competition_score = next(score for score in scores if score.niche_hypothesis_id == hypotheses[0].id and score.score_type == "competition_score")
    assert "component_scores" in final_score.evidence_json
    assert "competition_features" in competition_score.evidence_json
    assert "direct_match_density" in competition_score.evidence_json["competition_features"]
    assert final_score.weight == 1.0


def test_scoring_service_supports_calibration_hooks(session_factory) -> None:
    ranking_service = HypothesisRankingService(
        calibration=RankingCalibration(
            discovery_weight=0.15,
            opportunity_weight=0.20,
            competition_inverse_weight=0.15,
            confidence_weight=0.50,
        )
    )

    with session_factory() as session:
        run = _build_rankable_run(session)
        ranking_service.rank_and_persist(session=session, run_id=run.id)
        session.commit()
        hypotheses = list(session.scalars(select(NicheHypothesis).where(NicheHypothesis.run_id == run.id)))
        scores = list(session.scalars(select(NicheScore).where(NicheScore.run_id == run.id, NicheScore.score_type == "final_score")))

    assert len(hypotheses) == 2
    assert len(scores) == 2
    assert all(score.evidence_json["component_weights"]["confidence"] == 0.5 for score in scores)


def test_scoring_service_accepts_custom_competition_model(session_factory) -> None:
    class FixedCompetitionModel(CompetitionDensityModel):
        def assess(self, *, hypothesis_label: str, source_items, component_labels):
            assessment = super().assess(
                hypothesis_label=hypothesis_label,
                source_items=source_items,
                component_labels=component_labels,
            )
            return type(assessment)(
                density_score=88.0,
                rationale=assessment.rationale,
                evidence_json={**assessment.evidence_json, "forced": True},
                features=assessment.features,
            )

    ranking_service = HypothesisRankingService(competition_model=FixedCompetitionModel())

    with session_factory() as session:
        run = _build_rankable_run(session)
        ranking_service.rank_and_persist(session=session, run_id=run.id)
        session.commit()
        competition_scores = list(
            session.scalars(select(NicheScore).where(NicheScore.run_id == run.id, NicheScore.score_type == "competition_score"))
        )

    assert competition_scores
    assert all(score.evidence_json["competition_density"] == 88.0 for score in competition_scores)
    assert all(score.evidence_json["competition_features"]["forced"] is True for score in competition_scores)
