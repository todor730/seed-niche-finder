from __future__ import annotations

from uuid import uuid4

from app.db.models import SourceItem, SourceItemStatus
from app.services.scoring import CompetitionDensityModel


def _make_source_item(
    *,
    title: str,
    provider_name: str,
    review_count: int | None = None,
    rating_count: int | None = None,
    average_rating: float | None = None,
    published_date_raw: str | None = None,
    categories: list[str] | None = None,
    query_text: str = "romance books",
) -> SourceItem:
    return SourceItem(
        run_id=uuid4(),
        provider_name=provider_name,
        query_text=query_text,
        query_kind="books",
        provider_item_id=str(uuid4()),
        dedupe_key=str(uuid4()),
        source_url="https://example.test/book",
        title=title,
        subtitle=None,
        authors_json=["Author One"],
        categories_json=categories or ["Romance"],
        description_text=title,
        content_text=title,
        published_date_raw=published_date_raw,
        average_rating=average_rating,
        rating_count=rating_count,
        review_count=review_count,
        raw_payload_json={"title": title},
        status=SourceItemStatus.CLUSTERED,
    )


def test_competition_density_model_detects_crowded_niche_signals() -> None:
    model = CompetitionDensityModel()
    source_items = [
        _make_source_item(
            title="Enemies to Lovers Small Town Romance Book 1",
            provider_name="google_books",
            review_count=1400,
            rating_count=2100,
            average_rating=4.6,
            published_date_raw="2025-09-10",
            categories=["Romance", "Small Town Romance"],
        ),
        _make_source_item(
            title="Enemies to Lovers Small Town Romance Book 2",
            provider_name="open_library",
            review_count=1200,
            rating_count=1800,
            average_rating=4.5,
            published_date_raw="2024-08-01",
            categories=["Romance", "Small Town Romance"],
        ),
        _make_source_item(
            title="Heartfelt Enemies to Lovers Small Town Romance Series",
            provider_name="google_books",
            review_count=900,
            rating_count=1300,
            average_rating=4.4,
            published_date_raw="2026-01-12",
            categories=["Romance", "Small Town Romance"],
        ),
    ]

    assessment = model.assess(
        hypothesis_label="enemies to lovers small town romance",
        source_items=source_items,
        component_labels=["small town romance", "enemies to lovers", "heartfelt"],
    )

    assert assessment.density_score >= 60.0
    assert assessment.features.relevant_item_count == 3
    assert assessment.features.fallback_used is False
    assert assessment.features.incumbent_dominance > 50.0
    assert assessment.features.review_rating_footprint > 50.0
    assert assessment.features.series_dominance > 0.0
    assert assessment.features.direct_match_density > 60.0


def test_competition_density_model_uses_honest_fallback_when_public_evidence_is_thin() -> None:
    model = CompetitionDensityModel()
    source_items = [
        _make_source_item(
            title="Burnout Workbook for Busy Professionals",
            provider_name="google_books",
            published_date_raw=None,
            categories=["Self Help", "Burnout"],
            query_text="burnout books",
        ),
        _make_source_item(
            title="Burnout Guide for Professionals",
            provider_name="google_books",
            published_date_raw=None,
            categories=["Self Help", "Burnout"],
            query_text="burnout books",
        ),
    ]

    assessment = model.assess(
        hypothesis_label="burnout workbook for busy professionals",
        source_items=source_items,
        component_labels=["burnout", "workbook", "busy professionals"],
    )

    assert assessment.features.fallback_used is True
    assert assessment.features.evidence_coverage < 0.5
    assert 40.0 <= assessment.density_score <= 65.0
    assert "limitations" in assessment.evidence_json
    assert assessment.evidence_json["limitations"] == [
        "Public-only provider evidence may understate true marketplace competition when review/rating or catalog breadth signals are sparse."
    ]
