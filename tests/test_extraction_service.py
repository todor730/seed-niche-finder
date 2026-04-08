from __future__ import annotations

from sqlalchemy import select

from app.db.models import ExtractedSignal, ResearchRun, ResearchRunStatus, SourceItem, SourceItemStatus, User, UserStatus
from app.schemas.evidence import SourceItemCreate
from app.services.extraction import RuleBasedExtractionService
from app.services.extraction.normalization import build_evidence_span, normalize_signal_value


def _make_run(session) -> ResearchRun:
    user = User(email="extractor@test.local", status=UserStatus.ACTIVE)
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


def _make_source_item(session, *, run_id, title: str, subtitle: str | None = None, description: str | None = None, categories: list[str] | None = None) -> SourceItem:
    source_item = SourceItem(
        **SourceItemCreate(
            run_id=run_id,
            provider_name="google_books",
            query_text="romance books",
            query_kind="books",
            provider_item_id=title.lower().replace(" ", "-"),
            dedupe_key=title.lower().replace(" ", "-"),
            source_url="https://example.test/book",
            title=title,
            subtitle=subtitle,
            authors_json=["Author One"],
            categories_json=categories or [],
            description_text=description,
            content_text="\n".join(part for part in [title, subtitle or "", description or ""] if part),
            published_date_raw="2024-01-01",
            average_rating=4.4,
            rating_count=42,
            raw_payload_json={"title": title},
            status=SourceItemStatus.FETCHED,
        ).model_dump(exclude_none=True)
    )
    session.add(source_item)
    session.flush()
    return source_item


def test_normalization_helpers_build_stable_labels_and_spans() -> None:
    assert normalize_signal_value("Enemies-to-Lovers") == "enemies to lovers"
    assert normalize_signal_value("  Small/Town   Romance ") == "small town romance"
    assert build_evidence_span(field_name="title", source_text="Enemies to Lovers Romance", start=0, end=18) == (
        "title: Enemies to Lovers Romance"
    )


def test_rule_based_extraction_extracts_romance_signals(session_factory) -> None:
    extractor = RuleBasedExtractionService()

    with session_factory() as session:
        run = _make_run(session)
        source_item = _make_source_item(
            session,
            run_id=run.id,
            title="Enemies to Lovers Small-Town Romance",
            subtitle="A heartfelt love story for women over 40",
            description=(
                "Set in a small town, this heartfelt second chance romance helps readers find hope after heartbreak."
            ),
            categories=["Romance", "Small Town Romance", "Second Chance Romance"],
        )

        signals = extractor.extract_and_persist(session=session, source_items=[source_item])
        session.commit()

        persisted_signals = list(session.scalars(select(ExtractedSignal).where(ExtractedSignal.source_item_id == source_item.id)))
        session.refresh(source_item)

    signal_lookup = {(signal.signal_type, signal.normalized_value): signal for signal in signals}

    assert source_item.status == SourceItemStatus.EXTRACTED
    assert len(persisted_signals) == len(signals)
    assert ("trope", "enemies to lovers") in signal_lookup
    assert ("subgenre", "small town romance") in signal_lookup
    assert ("audience", "women over 40") in signal_lookup
    assert ("setting", "small town") in signal_lookup
    assert ("tone", "heartfelt") in signal_lookup
    assert ("problem_angle", "heartbreak") in signal_lookup
    assert signal_lookup[("trope", "enemies to lovers")].confidence >= 0.9
    assert signal_lookup[("trope", "enemies to lovers")].extraction_method == "rule:trope:keyword_v1"
    assert signal_lookup[("audience", "women over 40")].evidence_span is not None


def test_rule_based_extraction_extracts_nonfiction_problem_solution_and_promise(session_factory) -> None:
    extractor = RuleBasedExtractionService()

    with session_factory() as session:
        run = _make_run(session)
        source_item = _make_source_item(
            session,
            run_id=run.id,
            title="Overcome Burnout",
            subtitle="A step-by-step guide for busy professionals",
            description=(
                "This workbook helps you build calmer workdays using a simple habit system and practical weekly plan."
            ),
            categories=["Self Help", "Burnout Recovery", "Workbook"],
        )

        signals = extractor.extract_and_persist(session=session, source_items=[source_item])

    signal_lookup = {(signal.signal_type, signal.normalized_value): signal for signal in signals}

    assert ("problem_angle", "burnout") in signal_lookup
    assert ("audience", "busy professionals") in signal_lookup
    assert ("solution_angle", "workbook") in signal_lookup
    assert ("solution_angle", "habit system") in signal_lookup
    assert ("promise", "build calmer workdays") in signal_lookup


def test_rule_based_extraction_deduplicates_repeated_matches_per_item(session_factory) -> None:
    extractor = RuleBasedExtractionService()

    with session_factory() as session:
        run = _make_run(session)
        source_item = _make_source_item(
            session,
            run_id=run.id,
            title="Dark Romance in a Small Town",
            subtitle="A dark romance for readers who crave danger",
            description="This dark romance returns to the same small town with dark secrets.",
            categories=["Dark Romance", "Small Town Romance"],
        )

        signals = extractor.extract_and_persist(session=session, source_items=[source_item])

    dark_romance_signals = [signal for signal in signals if signal.signal_type == "subgenre" and signal.normalized_value == "dark romance"]
    small_town_setting_signals = [signal for signal in signals if signal.signal_type == "setting" and signal.normalized_value == "small town"]

    assert len(dark_romance_signals) == 1
    assert len(small_town_setting_signals) == 1
    assert dark_romance_signals[0].confidence > 0.95


def test_rule_based_extraction_uses_semantic_normalization_for_duplicate_variants(session_factory) -> None:
    extractor = RuleBasedExtractionService()

    with session_factory() as session:
        run = _make_run(session)
        source_item = _make_source_item(
            session,
            run_id=run.id,
            title="Enemy-to-Lovers Small Town Romnace",
            subtitle="A cozy romance for YA readers",
            description="This small town romances story brings enemy to lovers tension to a warm-hearted community.",
            categories=["Small-Town Romance"],
        )

        signals = extractor.extract_and_persist(session=session, source_items=[source_item])

    trope_signals = [signal for signal in signals if signal.signal_type == "trope"]
    subgenre_signals = [signal for signal in signals if signal.signal_type == "subgenre"]
    audience_signals = [signal for signal in signals if signal.signal_type == "audience"]
    tone_signals = [signal for signal in signals if signal.signal_type == "tone"]

    assert any(signal.normalized_value == "enemies to lovers" for signal in trope_signals)
    assert len([signal for signal in subgenre_signals if signal.normalized_value == "small town romance"]) == 1
    assert any(signal.normalized_value == "young adults" for signal in audience_signals)
    assert any(signal.normalized_value == "heartfelt" for signal in tone_signals)
