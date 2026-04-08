from __future__ import annotations

import httpx

import app.services.providers as provider_module
from app.services.providers import GoogleBooksProvider, OpenLibraryProvider, ProviderQuery, ProviderRequestPolicy


def test_google_books_search_normalizes_to_standard_raw_source_item(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": "g123",
                "volumeInfo": {
                    "title": "  Example Romance  ",
                    "subtitle": " A Novel ",
                    "authors": [" A. Author ", "A. Author", ""],
                    "categories": ["Romance", "Contemporary Romance"],
                    "description": "  A sample description.  ",
                    "publishedDate": "2024-05-01",
                    "averageRating": 4.5,
                    "ratingsCount": 87,
                    "infoLink": "https://books.google.test/item",
                },
            },
            {
                "id": "skip-me",
                "volumeInfo": {"title": "   "},
            },
        ]
    }

    monkeypatch.setattr(provider_module, "_request_json", lambda **_: payload)

    result = GoogleBooksProvider().search(
        client=httpx.Client(),
        query=ProviderQuery(text="romance books", kind="books"),
        policy=ProviderRequestPolicy(),
    )

    assert result.provider_name == "google_books"
    assert len(result.items) == 1

    item = result.items[0]
    assert item.query_text == "romance books"
    assert item.query_used == "romance books"
    assert item.provider_item_id == "g123"
    assert item.source_identifier == "g123"
    assert item.source_url == "https://books.google.test/item"
    assert item.title == "Example Romance"
    assert item.subtitle == "A Novel"
    assert item.authors == ["A. Author"]
    assert item.categories == ["Romance", "Contemporary Romance"]
    assert item.description_text == "A sample description."
    assert item.published_date_raw == "2024-05-01"
    assert item.average_rating == 4.5
    assert item.rating_count == 87
    assert item.review_count is None
    assert item.dedupe_key == "g123"
    assert item.content_text.startswith("Example Romance")


def test_open_library_search_normalizes_missing_fields_honestly(monkeypatch) -> None:
    payload = {
        "docs": [
            {
                "key": "/works/OL123W",
                "title": " Example Romance ",
                "subtitle": " A Novel ",
                "author_name": [" A. Author ", ""],
                "subject": ["Romance", "Contemporary Romance", "Romance"],
                "first_publish_year": 2019,
            },
            {
                "title": "   ",
                "key": "/works/skip",
            },
        ]
    }

    monkeypatch.setattr(provider_module, "_request_json", lambda **_: payload)

    result = OpenLibraryProvider().search(
        client=httpx.Client(),
        query=ProviderQuery(text="romance books", kind="books"),
        policy=ProviderRequestPolicy(),
    )

    assert result.provider_name == "open_library"
    assert len(result.items) == 1

    item = result.items[0]
    assert item.query_text == "romance books"
    assert item.provider_item_id == "/works/OL123W"
    assert item.source_url == "https://openlibrary.org/works/OL123W"
    assert item.title == "Example Romance"
    assert item.subtitle == "A Novel"
    assert item.authors == ["A. Author"]
    assert item.categories == ["Romance", "Contemporary Romance"]
    assert item.description_text is None
    assert item.published_date_raw == "2019"
    assert item.average_rating is None
    assert item.rating_count is None
    assert item.review_count is None
    assert item.dedupe_key == "/works/OL123W"
    assert "Example Romance" in item.content_text


def test_provider_normalization_never_accepts_non_http_urls() -> None:
    provider = GoogleBooksProvider()
    query = ProviderQuery(text="romance", kind="seed")
    normalized = provider._normalize_item(
        query=query,
        item={
            "id": "g124",
            "volumeInfo": {
                "title": "Example Romance",
                "infoLink": "javascript:alert(1)",
            },
        },
    )

    assert normalized is not None
    assert normalized.source_url is None
