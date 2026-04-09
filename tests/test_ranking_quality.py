from __future__ import annotations

from app.services.providers import BookSignal
from app.services.ranking import build_keyword_blueprints


def _book_signal(*, title: str, categories: list[str], source: str) -> BookSignal:
    return BookSignal(
        title=title,
        authors=["Author One"],
        categories=categories,
        review_count=12,
        average_rating=4.2,
        published_year=2024,
        source=source,
        source_url=f"https://example.test/{title.lower().replace(' ', '-')}",
    )


def test_build_keyword_blueprints_filters_false_positive_and_generic_self_help_terms() -> None:
    book_signals = [
        _book_signal(title="God Help the Child", categories=["Literary Fiction", "Novel"], source="google_books"),
        _book_signal(title="Self Help Books", categories=["Self Help", "Personal Growth"], source="google_books"),
        _book_signal(title="Greatest Self Help Book", categories=["Self Help", "Personal Growth"], source="open_library"),
        _book_signal(
            title="Self Confidence and Self Esteem Workbook for Women",
            categories=["Self Help", "Self Confidence", "Self Esteem", "Women", "Workbook"],
            source="google_books",
        ),
        _book_signal(
            title="Burnout Recovery Workbook for Busy Professionals",
            categories=["Self Help", "Burnout Recovery", "Busy Professionals", "Workbook"],
            source="open_library",
        ),
    ]

    blueprints = build_keyword_blueprints("self-help", book_signals, max_candidates=10)
    keyword_texts = {blueprint.keyword_text for blueprint in blueprints}

    assert "god help the child" not in keyword_texts
    assert "self help" not in keyword_texts
    assert "self help books" not in keyword_texts
    assert "greatest self help book" not in keyword_texts
    assert "burnout recovery" in keyword_texts
    assert "self confidence" in keyword_texts or "self esteem" in keyword_texts
    assert "women" not in keyword_texts
    assert "workbook" not in keyword_texts

    burnout_blueprint = next(blueprint for blueprint in blueprints if blueprint.keyword_text == "burnout recovery")
    assert "problem focus burnout" in burnout_blueprint.summary.lower()
    assert any("solution to burnout" in angle.lower() for angle in burnout_blueprint.landing_page_angles)


def test_build_keyword_blueprints_rejects_live_self_help_title_artifacts() -> None:
    book_signals = [
        _book_signal(title="The Self Help Book", categories=["Self Help", "Personal Growth"], source="google_books"),
        _book_signal(title="The Self Help Compulsion", categories=["Self Help", "Psychology"], source="open_library"),
        _book_signal(title="God Help the Child", categories=["Self Help", "Personal Growth"], source="google_books"),
        _book_signal(title="Greatest Self Help Book", categories=["Self Help", "Personal Growth"], source="open_library"),
        _book_signal(title="Ten Days to Self Esteem", categories=["Self Help", "Self Esteem"], source="google_books"),
        _book_signal(
            title="Self Confidence and Self Esteem Workbook for Women",
            categories=["Self Help", "Self Confidence", "Self Esteem", "Women", "Workbook"],
            source="open_library",
        ),
        _book_signal(
            title="Burnout Recovery Workbook for Busy Professionals",
            categories=["Self Help", "Burnout Recovery", "Busy Professionals", "Workbook"],
            source="google_books",
        ),
    ]

    blueprints = build_keyword_blueprints("self-help", book_signals, max_candidates=10)
    keyword_texts = {blueprint.keyword_text for blueprint in blueprints}

    assert "the self help book" not in keyword_texts
    assert "the self help compulsion" not in keyword_texts
    assert "god help the child" not in keyword_texts
    assert "greatest self help book" not in keyword_texts
    assert "self help" not in keyword_texts
    assert "self help books" not in keyword_texts
    assert "ten days to self esteem" not in keyword_texts
    assert any(keyword in keyword_texts for keyword in {"self confidence and self esteem", "self confidence", "self esteem"})
    assert "burnout recovery" in keyword_texts
    assert "busy professionals" not in keyword_texts
